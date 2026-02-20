"""Full flow test: Playbook Engine + Journal Writer + Expression Evaluator."""

import asyncio
from datetime import datetime

from agent.db.database import Database
from agent.playbook_engine import PlaybookEngine, PlaybookInstance
from agent.journal_writer import JournalWriter
from agent.playbook_eval import ExpressionContext, evaluate_condition, evaluate_expr
from agent.models.playbook import (
    Playbook, PlaybookConfig, PlaybookState, Phase, Transition,
    CheckCondition, CheckRule, TransitionAction, TradeAction,
    DynamicExpr, PositionManagementRule, ModifySLAction, TrailSLAction,
    PartialCloseAction, PhaseTimeout, PhaseTransitionRef, PlaybookVariable,
    IndicatorConfig,
)
from agent.models.journal import TradeJournalEntry, MarketContext
from agent.models.strategy import RiskConfig, Autonomy


async def test_full_flow():
    db = Database("data/test_flow.db")
    await db.connect()

    print("=" * 60)
    print("  FULL FLOW TEST: Playbook Engine + Journal Writer")
    print("=" * 60)

    # =========================================================
    # Step 1: Create a realistic playbook (what AI would build)
    # =========================================================
    print("\n--- Step 1: Create SMC OTE Playbook ---")

    config = PlaybookConfig(
        id="smc-ote-reentry",
        name="SMC OTE Re-Entry Strategy",
        description="H4 bullish structure + OTE pullback + M15 RSI trigger",
        symbols=["XAUUSD"],
        autonomy=Autonomy.SEMI_AUTO,
        indicators=[
            IndicatorConfig(id="h4_smc_structure", name="SMC_Structure", timeframe="H4", params={}),
            IndicatorConfig(id="h4_atr", name="ATR", timeframe="H4", params={"period": 14}),
            IndicatorConfig(id="m15_rsi", name="RSI", timeframe="M15", params={"period": 14}),
        ],
        variables={
            "structure_break_price": PlaybookVariable(type="float", default=0.0),
            "initial_sl": PlaybookVariable(type="float", default=0.0),
            "entry_price": PlaybookVariable(type="float", default=0.0),
        },
        phases={
            "idle": Phase(
                description="Wait for H4 bullish structure",
                evaluate_on=["H4"],
                transitions=[
                    Transition(
                        to="wait_pullback_long",
                        conditions=CheckCondition(type="AND", rules=[
                            CheckRule(left="ind.h4_smc_structure.trend", operator="==", right="1", description="Bullish structure"),
                        ]),
                        actions=[
                            TransitionAction(set_var="structure_break_price", expr="ind.h4_smc_structure.ref_high"),
                        ],
                    ),
                ],
            ),
            "wait_pullback_long": Phase(
                description="Wait for price to pull back into OTE zone",
                evaluate_on=["H4", "M15"],
                timeout=PhaseTimeout(bars=20, timeframe="H4", to="idle"),
                transitions=[
                    Transition(
                        to="entry_ready_long",
                        conditions=CheckCondition(type="AND", rules=[
                            CheckRule(left="_price", operator="<=", right="ind.h4_smc_structure.ote_top", description="Price in OTE zone (below top)"),
                            CheckRule(left="_price", operator=">=", right="ind.h4_smc_structure.ote_bottom", description="Price in OTE zone (above bottom)"),
                        ]),
                    ),
                ],
            ),
            "entry_ready_long": Phase(
                description="Wait for M15 RSI trigger in OTE zone",
                evaluate_on=["M15"],
                timeout=PhaseTimeout(bars=10, timeframe="M15", to="idle"),
                transitions=[
                    Transition(
                        to="in_position_long",
                        conditions=CheckCondition(type="AND", rules=[
                            CheckRule(left="ind.m15_rsi.value", operator=">", right="30", description="RSI crossed above 30"),
                            CheckRule(left="prev.m15_rsi.value", operator="<=", right="30", description="RSI was below 30 last bar"),
                        ]),
                        actions=[
                            TransitionAction(set_var="entry_price", expr="_price"),
                            TransitionAction(set_var="initial_sl", expr="ind.h4_smc_structure.strong_low - ind.h4_atr.value * 0.5"),
                            TransitionAction(open_trade=TradeAction(
                                direction="BUY",
                                lot=DynamicExpr(expr="risk.max_lot"),
                                sl=DynamicExpr(expr="ind.h4_smc_structure.strong_low - ind.h4_atr.value * 0.5"),
                                tp=DynamicExpr(expr="_price + (_price - (ind.h4_smc_structure.strong_low - ind.h4_atr.value * 0.5)) * 3"),
                            )),
                        ],
                    ),
                ],
            ),
            "in_position_long": Phase(
                description="Manage open long position",
                evaluate_on=["M15"],
                on_trade_closed=PhaseTransitionRef(to="idle"),
                position_management=[
                    PositionManagementRule(
                        name="breakeven_at_1rr",
                        once=True,
                        when=CheckCondition(type="AND", rules=[
                            CheckRule(left="_price", operator=">=", right="var.entry_price + (var.entry_price - var.initial_sl)", description="Price at 1R profit"),
                        ]),
                        modify_sl=ModifySLAction(expr="var.entry_price + ind.h4_atr.value * 0.1"),
                    ),
                    PositionManagementRule(
                        name="partial_close_at_2rr",
                        once=True,
                        when=CheckCondition(type="AND", rules=[
                            CheckRule(left="_price", operator=">=", right="var.entry_price + (var.entry_price - var.initial_sl) * 2", description="Price at 2R profit"),
                        ]),
                        partial_close=PartialCloseAction(pct=50),
                    ),
                    PositionManagementRule(
                        name="trailing_stop",
                        continuous=True,
                        when=CheckCondition(type="AND", rules=[
                            CheckRule(left="_price", operator=">=", right="var.entry_price + (var.entry_price - var.initial_sl) * 2", description="Past 2R"),
                        ]),
                        trail_sl=TrailSLAction(distance=DynamicExpr(expr="ind.h4_atr.value")),
                    ),
                ],
            ),
        },
        initial_phase="idle",
        risk=RiskConfig(max_lot=0.1, max_daily_trades=5, max_drawdown_pct=3.0, max_open_positions=2),
    )

    playbook = Playbook(name=config.name, description_nl="SMC OTE strategy", config=config, enabled=True)
    pb_id = await db.create_playbook(playbook)
    playbook.id = pb_id
    print(f"  Created playbook id={pb_id}: {config.name}")
    print(f"  Phases: {list(config.phases.keys())}")
    print(f"  Indicators: {[i.id for i in config.indicators]}")
    print(f"  Variables: {list(config.variables.keys())}")

    # Verify DB round-trip
    pb_loaded = await db.get_playbook(pb_id)
    assert pb_loaded.config.id == "smc-ote-reentry"
    assert len(pb_loaded.config.phases) == 4
    assert len(pb_loaded.config.indicators) == 3
    print(f"  DB round-trip: OK (phases={len(pb_loaded.config.phases)}, indicators={len(pb_loaded.config.indicators)})")

    # =========================================================
    # Step 2: Test expression evaluator with realistic data
    # =========================================================
    print("\n--- Step 2: Expression Evaluator ---")

    ctx = ExpressionContext(
        indicators={
            "h4_smc_structure": {"trend": 1.0, "strong_low": 2720.0, "ref_high": 2780.0, "equilibrium": 2750.0, "ote_top": 2765.0, "ote_bottom": 2755.0},
            "h4_atr": {"value": 15.0},
            "m15_rsi": {"value": 32.0},
        },
        prev_indicators={"m15_rsi": {"value": 28.0}},
        variables={"entry_price": 2760.0, "initial_sl": 2712.5},
        price=2760.0,
        risk={"max_lot": 0.1, "max_daily_trades": 5, "max_drawdown_pct": 3.0, "max_open_positions": 2},
    )

    # SL: strong_low - ATR * 0.5 = 2720 - 7.5 = 2712.5
    sl = evaluate_expr("ind.h4_smc_structure.strong_low - ind.h4_atr.value * 0.5", ctx)
    print(f"  SL expr: strong_low(2720) - ATR(15)*0.5 = {sl}")
    assert abs(sl - 2712.5) < 0.01

    # TP: price + (price - sl) * 3 = 2760 + 47.5*3 = 2902.5
    tp = evaluate_expr("_price + (_price - (ind.h4_smc_structure.strong_low - ind.h4_atr.value * 0.5)) * 3", ctx)
    print(f"  TP expr: price(2760) + risk(47.5)*3 = {tp}")
    assert abs(tp - 2902.5) < 0.01

    # 1R level: entry + (entry - sl) = 2760 + 47.5 = 2807.5
    one_r = evaluate_expr("var.entry_price + (var.entry_price - var.initial_sl)", ctx)
    print(f"  1R level: entry(2760) + risk(47.5) = {one_r}")
    assert abs(one_r - 2807.5) < 0.01

    # Breakeven SL: entry + ATR * 0.1 = 2760 + 1.5 = 2761.5
    be_sl = evaluate_expr("var.entry_price + ind.h4_atr.value * 0.1", ctx)
    print(f"  BE SL: entry(2760) + ATR(15)*0.1 = {be_sl}")
    assert abs(be_sl - 2761.5) < 0.01

    print("  All expressions: PASSED")

    # =========================================================
    # Step 3: Test phase transitions
    # =========================================================
    print("\n--- Step 3: Phase Transitions ---")

    instance = PlaybookInstance(playbook, "XAUUSD")
    assert instance.state.current_phase == "idle"
    print(f"  Initial phase: {instance.state.current_phase}")

    # idle -> wait_pullback_long (bullish structure)
    idle_phase = config.phases["idle"]
    transition = idle_phase.transitions[0]
    cond = transition.conditions.model_dump()

    ctx_bullish = ExpressionContext(
        indicators={"h4_smc_structure": {"trend": 1.0, "ref_high": 2780.0}},
        price=2760.0,
    )
    result = evaluate_condition(cond, ctx_bullish)
    assert result is True
    print(f"  idle->wait_pullback (trend==1): {result}")

    for action in transition.actions:
        if action.set_var and action.expr:
            val = evaluate_expr(action.expr, ctx_bullish)
            instance.set_variable(action.set_var, val)
            print(f"  Set {action.set_var} = {val}")

    instance.transition_to("wait_pullback_long")
    assert instance.state.current_phase == "wait_pullback_long"
    print(f"  Transitioned to: {instance.state.current_phase}")

    # wait_pullback -> entry_ready (price in OTE)
    wp_phase = config.phases["wait_pullback_long"]
    wp_cond = wp_phase.transitions[0].conditions.model_dump()
    ctx_ote = ExpressionContext(
        indicators={"h4_smc_structure": {"ote_top": 2765.0, "ote_bottom": 2755.0}},
        price=2760.0,
    )
    result = evaluate_condition(wp_cond, ctx_ote)
    assert result is True
    print(f"  wait_pullback->entry_ready (price in OTE): {result}")

    # Price NOT in OTE
    ctx_no_ote = ExpressionContext(
        indicators={"h4_smc_structure": {"ote_top": 2765.0, "ote_bottom": 2755.0}},
        price=2770.0,
    )
    result_no = evaluate_condition(wp_cond, ctx_no_ote)
    assert result_no is False
    print(f"  Price above OTE (2770): {result_no} (correctly rejected)")

    instance.transition_to("entry_ready_long")
    print(f"  Transitioned to: {instance.state.current_phase}")

    # entry_ready -> in_position (RSI cross above 30)
    er_phase = config.phases["entry_ready_long"]
    er_cond = er_phase.transitions[0].conditions.model_dump()

    ctx_entry = ExpressionContext(
        indicators={"m15_rsi": {"value": 32.0}},
        prev_indicators={"m15_rsi": {"value": 28.0}},
        price=2760.0,
    )
    result = evaluate_condition(er_cond, ctx_entry)
    assert result is True
    print(f"  entry_ready->in_position (RSI cross >30): {result}")

    # No cross (both above 30)
    ctx_no_cross = ExpressionContext(
        indicators={"m15_rsi": {"value": 35.0}},
        prev_indicators={"m15_rsi": {"value": 32.0}},
        price=2760.0,
    )
    result_no = evaluate_condition(er_cond, ctx_no_cross)
    assert result_no is False
    print(f"  No cross (both above 30): {result_no} (correctly rejected)")

    instance.transition_to("in_position_long")
    print(f"  Transitioned to: {instance.state.current_phase}")
    print("  All transitions: PASSED")

    # =========================================================
    # Step 4: Test position management rules
    # =========================================================
    print("\n--- Step 4: Position Management Rules ---")

    ip_phase = config.phases["in_position_long"]

    # Breakeven at 1R
    be_rule = ip_phase.position_management[0]
    be_cond = be_rule.when.model_dump()
    ctx_1r = ExpressionContext(
        variables={"entry_price": 2760.0, "initial_sl": 2712.5},
        price=2808.0,
        indicators={"h4_atr": {"value": 15.0}},
    )
    result = evaluate_condition(be_cond, ctx_1r)
    assert result is True
    new_sl = evaluate_expr(be_rule.modify_sl.expr, ctx_1r)
    print(f"  Breakeven at 1R (price=2808): fires={result}, new_sl={new_sl}")
    assert abs(new_sl - 2761.5) < 0.01

    # Partial close at 2R
    pc_rule = ip_phase.position_management[1]
    pc_cond = pc_rule.when.model_dump()
    ctx_2r = ExpressionContext(
        variables={"entry_price": 2760.0, "initial_sl": 2712.5},
        price=2856.0,
    )
    result = evaluate_condition(pc_cond, ctx_2r)
    assert result is True
    print(f"  Partial close at 2R (price=2856): fires={result}, close {pc_rule.partial_close.pct}%")

    # Trailing stop
    trail_rule = ip_phase.position_management[2]
    trail_cond = trail_rule.when.model_dump()
    result = evaluate_condition(trail_cond, ctx_2r)
    assert result is True
    ctx_trail = ExpressionContext(
        indicators={"h4_atr": {"value": 15.0}},
        variables={"entry_price": 2760.0, "initial_sl": 2712.5},
        price=2856.0,
    )
    distance = evaluate_expr(trail_rule.trail_sl.distance.expr, ctx_trail)
    print(f"  Trailing stop past 2R: fires={result}, distance={distance}")

    # Pre-1R (should NOT fire)
    ctx_pre1r = ExpressionContext(
        variables={"entry_price": 2760.0, "initial_sl": 2712.5},
        price=2770.0,
    )
    result = evaluate_condition(be_cond, ctx_pre1r)
    assert result is False
    print(f"  Breakeven pre-1R (price=2770): fires={result} (correctly skipped)")

    print("  All management rules: PASSED")

    # =========================================================
    # Step 5: Test journal writer
    # =========================================================
    print("\n--- Step 5: Journal Writer ---")

    class MockDataManager:
        def __init__(self):
            self._indicators = {}
            self._ticks = {}
        def get_tick(self, symbol):
            return None
        def get_cached_indicator(self, symbol, tf, iid):
            return None

    mock_dm = MockDataManager()
    jw = JournalWriter(db, mock_dm)

    j_id = await jw.on_trade_opened(
        trade_id=1, signal_id=1, strategy_id=0, playbook_db_id=pb_id,
        symbol="XAUUSD", direction="BUY", lot=0.1,
        open_price=2760.0, sl=2712.5, tp=2902.5, ticket=12345,
        playbook_phase="entry_ready_long",
        variables_at_entry={"entry_price": 2760.0, "initial_sl": 2712.5},
        entry_conditions={"h4_structure": "bullish", "rsi_cross": "above_30"},
    )
    print(f"  Opened journal entry: id={j_id}")

    await jw.on_management_event(12345, "breakeven_at_1rr", "modify_sl", {"old_sl": 2712.5, "new_sl": 2761.5}, "in_position_long")
    await jw.on_management_event(12345, "partial_close_at_2rr", "partial_close", {"pct": 50}, "in_position_long")
    await jw.on_management_event(12345, "trailing_stop", "trail_sl", {"new_sl": 2840.0, "distance": 15.0}, "in_position_long")
    print("  Added 3 management events")

    await jw.on_trade_closed(
        ticket=12345, close_price=2850.0, pnl=90.0,
        exit_reason="tp_hit", sl_final=2840.0, tp_final=2902.5,
        symbol="XAUUSD",
    )
    print("  Closed journal entry")

    entry = await db.get_journal_entry(j_id)
    print(f"  Outcome: {entry.outcome}")
    print(f"  PnL: ${entry.pnl}")
    print(f"  PnL pips: {entry.pnl_pips}")
    print(f"  R:R achieved: {entry.rr_achieved}")
    print(f"  Exit reason: {entry.exit_reason}")
    print(f"  Duration: {entry.duration_seconds}s")
    print(f"  SL: {entry.sl_initial} -> {entry.sl_final}")
    print(f"  Management events: {len(entry.management_events)}")
    for evt in entry.management_events:
        print(f"    - {evt.rule_name}: {evt.action} {evt.details}")
    print(f"  Entry conditions: {entry.entry_conditions}")
    print(f"  Phase at entry: {entry.playbook_phase_at_entry}")
    print(f"  Variables: {entry.variables_at_entry}")

    assert entry.outcome == "win"
    assert entry.pnl == 90.0
    assert entry.exit_reason == "tp_hit"
    assert len(entry.management_events) == 3
    assert entry.sl_final == 2840.0
    print("  Journal write/read: PASSED")

    # =========================================================
    # Step 6: Test analytics
    # =========================================================
    print("\n--- Step 6: Analytics ---")

    analytics = await db.get_journal_analytics(playbook_db_id=pb_id)
    print(f"  Total trades: {analytics['total_trades']}")
    print(f"  Win rate: {analytics['win_rate']}%")
    print(f"  Avg PnL: ${analytics['avg_pnl']}")
    print(f"  Total PnL: ${analytics['total_pnl']}")
    print(f"  Exit reasons: {analytics['exit_reasons']}")

    assert analytics["total_trades"] == 1
    assert analytics["win_rate"] == 100.0
    assert analytics["total_pnl"] == 90.0

    cond_analytics = await db.get_journal_condition_analytics(playbook_db_id=pb_id)
    print(f"  Condition analytics: {len(cond_analytics)} conditions tracked")
    for ca in cond_analytics:
        print(f"    - {ca['condition']}: {ca['total']} trades, {ca['win_rate']}% win")

    print("  Analytics: PASSED")

    # =========================================================
    # Step 7: Test state persistence
    # =========================================================
    print("\n--- Step 7: State Persistence ---")

    state = PlaybookState(
        playbook_id=pb_id, symbol="XAUUSD",
        current_phase="in_position_long",
        variables={"entry_price": 2760.0, "initial_sl": 2712.5, "sl": 2840.0},
        bars_in_phase=15,
        phase_timeframe_bars={"M15": 15},
        fired_once_rules=["breakeven_at_1rr", "partial_close_at_2rr"],
        open_ticket=12345, open_direction="BUY",
    )
    await db.save_playbook_state(state)
    print(f"  Saved: phase={state.current_phase}, bars={state.bars_in_phase}")

    state2 = await db.get_playbook_state(pb_id, "XAUUSD")
    assert state2.current_phase == "in_position_long"
    assert state2.variables["entry_price"] == 2760.0
    assert state2.bars_in_phase == 15
    assert "breakeven_at_1rr" in state2.fired_once_rules
    assert state2.open_ticket == 12345
    print(f"  Loaded: phase={state2.current_phase}, ticket={state2.open_ticket}")
    print(f"  Fired rules: {state2.fired_once_rules}")

    state2.current_phase = "idle"
    state2.open_ticket = None
    state2.fired_once_rules = []
    await db.save_playbook_state(state2)
    state3 = await db.get_playbook_state(pb_id, "XAUUSD")
    assert state3.current_phase == "idle"
    assert state3.open_ticket is None
    print(f"  Updated: phase={state3.current_phase}, ticket={state3.open_ticket}")
    print("  State persistence: PASSED")

    # =========================================================
    # Step 8: Test timeout
    # =========================================================
    print("\n--- Step 8: Phase Timeout ---")

    instance2 = PlaybookInstance(playbook, "XAUUSD")
    instance2.transition_to("wait_pullback_long")
    for i in range(20):
        instance2.state.bars_in_phase += 1
        instance2.state.phase_timeframe_bars["H4"] = instance2.state.phase_timeframe_bars.get("H4", 0) + 1

    wp_phase = config.phases["wait_pullback_long"]
    tf_bars = instance2.state.phase_timeframe_bars.get(wp_phase.timeout.timeframe, 0)
    timed_out = tf_bars >= wp_phase.timeout.bars
    print(f"  After 20 H4 bars: timeout={timed_out}")
    assert timed_out is True

    instance2.transition_to(wp_phase.timeout.to)
    assert instance2.state.current_phase == "idle"
    print(f"  Timed out to: {instance2.state.current_phase}")
    print("  Timeout: PASSED")

    # =========================================================
    # Step 9: on_trade_closed transition
    # =========================================================
    print("\n--- Step 9: on_trade_closed ---")

    instance3 = PlaybookInstance(playbook, "XAUUSD")
    instance3.transition_to("in_position_long")
    instance3.state.open_ticket = 99999
    print(f"  Before: phase={instance3.state.current_phase}")

    phase = instance3.current_phase
    assert phase.on_trade_closed is not None
    instance3.state.open_ticket = None
    instance3.transition_to(phase.on_trade_closed.to)
    assert instance3.state.current_phase == "idle"
    print(f"  After: phase={instance3.state.current_phase}")
    print("  on_trade_closed: PASSED")

    # Cleanup
    await db.delete_playbook(pb_id)
    await db._db.execute("DELETE FROM trade_journal")
    await db._db.commit()
    await db.disconnect()

    print("\n" + "=" * 60)
    print("  ALL 9 TESTS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_full_flow())
