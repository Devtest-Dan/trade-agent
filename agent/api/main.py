"""FastAPI application factory and lifespan management."""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from agent.ai_service import AIService
from agent.api.auth import (
    UserCreate,
    UserLogin,
    TokenResponse,
    create_token,
    hash_password,
    verify_password,
)
from agent.bridge import ZMQBridge
from agent.config import settings
from agent.data_manager import DataManager
from agent.db.database import Database
from agent.journal_writer import JournalWriter
from agent.notifications import notify_signal, notify_trade_opened, notify_management_event, send_telegram
from agent.playbook_engine import PlaybookEngine
from agent.risk_manager import RiskManager
from agent.strategy_engine import StrategyEngine
from agent.indicator_processor import IndicatorProcessor
from agent.trade_executor import TradeExecutor

# Global app state — accessible from route handlers
app_state: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic."""
    logger.info("Starting Trade Agent...")

    # Initialize database
    db = Database()
    await db.connect()

    # Initialize ZMQ bridge
    bridge = ZMQBridge()
    try:
        await bridge.connect()
        mt5_connected = True
    except Exception as e:
        logger.warning(f"MT5 not connected: {e}. Running in offline mode.")
        mt5_connected = False

    # Initialize components
    data_manager = DataManager(bridge)
    ai_service = AIService()
    risk_manager = RiskManager()
    strategy_engine = StrategyEngine(data_manager)
    trade_executor = TradeExecutor(bridge, risk_manager)
    playbook_engine = PlaybookEngine(data_manager)
    journal_writer = JournalWriter(db, data_manager)
    indicator_processor = IndicatorProcessor(ai_service)

    # Wire up callbacks
    from agent.api.ws import broadcast_signal, broadcast_tick, broadcast_trade

    async def on_signal(signal):
        """Handle new signal from strategy engine."""
        # Save to DB
        signal.id = await db.create_signal(signal)

        # Get strategy
        strategy = await db.get_strategy(signal.strategy_id)
        if not strategy:
            return

        # Risk check
        positions = await bridge.get_positions() if mt5_connected else []
        account = await bridge.get_account() if mt5_connected else None
        decision = risk_manager.check_signal(signal, strategy, positions, account)

        # Execute based on decision
        result = await trade_executor.process_signal(signal, strategy, decision)
        await db.update_signal_status(result.id, result.status, result.ai_reasoning)

        # Notify via Telegram
        await notify_signal(result)

        # Broadcast to WebSocket clients
        await broadcast_signal({
            "id": result.id,
            "strategy_id": result.strategy_id,
            "strategy_name": result.strategy_name,
            "symbol": result.symbol,
            "direction": result.direction.value,
            "status": result.status.value,
            "price": result.price_at_signal,
            "reasoning": result.ai_reasoning,
        })

    async def on_playbook_signal(signal):
        """Handle new signal from playbook engine."""
        signal.id = await db.create_signal(signal)

        # Notify via Telegram
        await notify_signal(signal)

        # Broadcast to WebSocket clients
        await broadcast_signal({
            "id": signal.id,
            "strategy_id": signal.strategy_id,
            "playbook_db_id": signal.playbook_db_id,
            "strategy_name": signal.strategy_name,
            "symbol": signal.symbol,
            "direction": signal.direction.value,
            "status": signal.status.value,
            "price": signal.price_at_signal,
            "reasoning": signal.ai_reasoning,
            "playbook_phase": signal.playbook_phase,
        })

    async def on_playbook_trade_action(trade_data):
        """Handle trade action from playbook engine."""
        signal = trade_data["signal"]
        playbook_id = trade_data["playbook_id"]
        direction = trade_data["direction"]
        lot = trade_data["lot"]
        sl = trade_data["sl"]
        tp = trade_data["tp"]
        symbol = trade_data["symbol"]

        # Get playbook for autonomy check
        playbook = await db.get_playbook(playbook_id)
        if not playbook:
            return

        from agent.models.strategy import Autonomy, Strategy, StrategyConfig, RiskConfig

        # Create a lightweight strategy object for the trade executor
        strategy = Strategy(
            id=0,
            name=playbook.config.name,
            description_nl=playbook.description_nl,
            config=StrategyConfig(
                id=playbook.config.id,
                name=playbook.config.name,
                description="",
                symbols=playbook.config.symbols,
                autonomy=playbook.config.autonomy,
                risk=playbook.config.risk,
            ),
            enabled=True,
        )

        # Risk check
        positions = await bridge.get_positions() if mt5_connected else []
        account = await bridge.get_account() if mt5_connected else None
        decision = risk_manager.check_signal(signal, strategy, positions, account)

        if not decision.approved:
            signal.status = "rejected"
            signal.ai_reasoning = f"Risk blocked: {decision.reason}"
            await db.update_signal_status(signal.id, signal.status, signal.ai_reasoning)
            return

        # Execute trade
        if playbook.config.autonomy.value == "signal_only":
            return  # Signal already emitted

        result = await bridge.open_order(
            symbol=symbol, order_type=direction, lot=lot, sl=sl, tp=tp
        )

        if result.get("success"):
            ticket = result.get("ticket", 0)
            from agent.models.trade import Trade
            from datetime import datetime

            trade = Trade(
                signal_id=signal.id,
                strategy_id=0,
                playbook_db_id=playbook_id,
                symbol=symbol,
                direction=direction,
                lot=lot,
                open_price=signal.price_at_signal,
                sl=sl,
                tp=tp,
                ticket=ticket,
                open_time=datetime.now(),
            )
            trade.id = await db.create_trade(trade)

            risk_manager.record_trade(0)

            # Notify playbook engine of trade open
            playbook_engine.notify_trade_opened(
                playbook_id, ticket, direction, signal.price_at_signal, sl, tp, lot
            )

            # Journal entry
            journal_id = await journal_writer.on_trade_opened(
                trade_id=trade.id,
                signal_id=signal.id,
                strategy_id=0,
                playbook_db_id=playbook_id,
                symbol=symbol,
                direction=direction,
                lot=lot,
                open_price=signal.price_at_signal,
                sl=sl,
                tp=tp,
                ticket=ticket,
                playbook_phase=trade_data.get("phase_at_entry", ""),
                variables_at_entry=trade_data.get("variables_at_entry", {}),
                entry_conditions=trade_data.get("entry_snapshot", {}),
                playbook_config=playbook.config,
            )

            # Notify via Telegram
            await notify_trade_opened(symbol, direction, lot, signal.price_at_signal, sl, tp, ticket)

            await broadcast_trade({
                "id": trade.id,
                "symbol": symbol,
                "direction": direction,
                "lot": lot,
                "price": signal.price_at_signal,
                "ticket": ticket,
                "playbook_id": playbook_id,
            })

            signal.status = "executed"
            await db.update_signal_status(signal.id, signal.status)

    async def on_playbook_management(event):
        """Handle position management event from playbook engine."""
        ticket = event.get("ticket")
        action = event.get("action")
        playbook_id = event.get("playbook_id")

        if action == "modify_sl":
            new_sl = event.get("new_sl")
            if ticket and new_sl:
                await trade_executor.modify_position(ticket, sl=new_sl)
                await journal_writer.on_management_event(
                    ticket, event.get("rule", ""), "modify_sl",
                    {"new_sl": new_sl}, event.get("phase", "")
                )
                await notify_management_event(event.get("symbol", ""), "modify_sl", {"new_sl": new_sl, "ticket": ticket})

        elif action == "modify_tp":
            new_tp = event.get("new_tp")
            if ticket and new_tp:
                await trade_executor.modify_position(ticket, tp=new_tp)
                await journal_writer.on_management_event(
                    ticket, event.get("rule", ""), "modify_tp",
                    {"new_tp": new_tp}, event.get("phase", "")
                )
                await notify_management_event(event.get("symbol", ""), "modify_tp", {"new_tp": new_tp, "ticket": ticket})

        elif action == "trail_sl":
            distance = event.get("distance")
            if ticket and distance:
                tick = data_manager.get_tick(event.get("symbol", ""))
                if tick:
                    instance = playbook_engine.get_instance(playbook_id)
                    if instance and instance.state.open_direction == "BUY":
                        new_sl = tick.bid - distance
                    else:
                        new_sl = tick.ask + distance
                    # Only trail in profitable direction
                    positions = await bridge.get_positions()
                    for pos in positions:
                        if pos.ticket == ticket:
                            if instance and instance.state.open_direction == "BUY":
                                if pos.sl is None or new_sl > pos.sl:
                                    await trade_executor.modify_position(ticket, sl=new_sl)
                                    await journal_writer.on_management_event(
                                        ticket, event.get("rule", ""), "trail_sl",
                                        {"new_sl": new_sl, "distance": distance},
                                        event.get("phase", ""),
                                    )
                            else:
                                if pos.sl is None or new_sl < pos.sl:
                                    await trade_executor.modify_position(ticket, sl=new_sl)
                                    await journal_writer.on_management_event(
                                        ticket, event.get("rule", ""), "trail_sl",
                                        {"new_sl": new_sl, "distance": distance},
                                        event.get("phase", ""),
                                    )
                            break

        elif action == "partial_close":
            pct = event.get("pct", 0)
            if ticket and pct > 0:
                await trade_executor.partial_close(ticket, pct)
                await journal_writer.on_management_event(
                    ticket, event.get("rule", ""), "partial_close",
                    {"pct": pct}, event.get("phase", "")
                )
                await notify_management_event(event.get("symbol", ""), "partial_close", {"pct": pct, "ticket": ticket})

    async def on_playbook_state_change(state):
        """Persist playbook state to DB."""
        await db.save_playbook_state(state)

    async def on_trade(trade):
        trade.id = await db.create_trade(trade)
        await broadcast_trade({
            "id": trade.id,
            "symbol": trade.symbol,
            "direction": trade.direction,
            "lot": trade.lot,
            "price": trade.open_price,
            "ticket": trade.ticket,
        })

    async def on_tick(tick):
        await data_manager.on_tick(tick)
        await broadcast_tick(tick.symbol, tick.bid, tick.ask)

    # Wire strategy engine callbacks
    strategy_engine.on_signal(on_signal)
    trade_executor.on_trade(on_trade)
    data_manager.on_bar_close(strategy_engine.evaluate_on_bar_close)

    # Wire playbook engine callbacks
    playbook_engine.on_signal(on_playbook_signal)
    playbook_engine.on_trade_action(on_playbook_trade_action)
    playbook_engine.on_management_event(on_playbook_management)
    playbook_engine.on_state_change(on_playbook_state_change)
    data_manager.on_bar_close(playbook_engine.evaluate_on_bar_close)

    if mt5_connected:
        bridge.on_tick(on_tick)
        await bridge.start_tick_listener()

    # Load enabled strategies from DB
    strategies = await db.list_strategies()
    for s in strategies:
        if s.enabled:
            strategy_engine.load_strategy(s)
            for symbol in s.config.symbols:
                await data_manager.initialize(symbol, s.config.timeframes_used)

    # Load enabled playbooks from DB
    playbooks = await db.list_playbooks()
    for p in playbooks:
        if p.enabled and p.id is not None:
            # Load saved state
            state = None
            for symbol in p.config.symbols:
                state = await db.get_playbook_state(p.id, symbol)
                # Initialize data for playbook timeframes
                tfs = set()
                for ind in p.config.indicators:
                    tfs.add(ind.timeframe)
                for phase in p.config.phases.values():
                    tfs.update(phase.evaluate_on)
                await data_manager.initialize(symbol, list(tfs))
            playbook_engine.load_playbook(p, state)

    # Store in app state
    app_state.update({
        "db": db,
        "bridge": bridge,
        "data_manager": data_manager,
        "ai_service": ai_service,
        "risk_manager": risk_manager,
        "strategy_engine": strategy_engine,
        "trade_executor": trade_executor,
        "playbook_engine": playbook_engine,
        "journal_writer": journal_writer,
        "indicator_processor": indicator_processor,
        "mt5_connected": mt5_connected,
    })

    logger.info(f"Trade Agent ready. MT5 connected: {mt5_connected}")
    yield

    # Shutdown
    logger.info("Shutting down Trade Agent...")
    if mt5_connected:
        await bridge.disconnect()
    await db.disconnect()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Trade Agent API",
        description="AI-powered trading agent with MT5 integration",
        version="0.2.0",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost:3000", "*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Auth routes (no prefix needed)
    @app.post("/api/auth/register", response_model=TokenResponse)
    async def register(req: UserCreate):
        db = app_state["db"]
        existing = await db.get_setting(f"user:{req.username}")
        if existing:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="Username already exists")
        await db.set_setting(f"user:{req.username}", {
            "username": req.username,
            "password_hash": hash_password(req.password),
        })
        token = create_token(req.username)
        return TokenResponse(access_token=token)

    @app.post("/api/auth/login", response_model=TokenResponse)
    async def login(req: UserLogin):
        db = app_state["db"]
        user_data = await db.get_setting(f"user:{req.username}")
        if not user_data or not verify_password(req.password, user_data["password_hash"]):
            from fastapi import HTTPException
            raise HTTPException(status_code=401, detail="Invalid credentials")
        token = create_token(req.username)
        return TokenResponse(access_token=token)

    @app.get("/api/health")
    async def health():
        return {
            "status": "ok",
            "mt5_connected": app_state.get("mt5_connected", False),
            "kill_switch": app_state.get("risk_manager", RiskManager()).kill_switch_active,
        }

    # Include routers
    from agent.api.strategies import router as strategies_router
    from agent.api.signals import router as signals_router
    from agent.api.trades import router as trades_router
    from agent.api.market import router as market_router
    from agent.api.settings_routes import router as settings_router
    from agent.api.ws import router as ws_router
    from agent.api.playbooks import router as playbooks_router
    from agent.api.journal import router as journal_router
    from agent.api.backtest import router as backtest_router
    from agent.api.indicators import router as indicators_router

    app.include_router(strategies_router)
    app.include_router(signals_router)
    app.include_router(trades_router)
    app.include_router(indicators_router)
    app.include_router(market_router)
    app.include_router(settings_router)
    app.include_router(ws_router)
    app.include_router(playbooks_router)
    app.include_router(journal_router)
    app.include_router(backtest_router)

    return app
