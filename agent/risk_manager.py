"""Risk Manager — enforces per-strategy and global risk limits."""

from datetime import date, datetime
from typing import Any

from loguru import logger

from agent.models.signal import Signal, SignalDirection
from agent.models.strategy import Autonomy, RiskConfig, Strategy
from agent.models.trade import AccountInfo, Position


class RiskDecision:
    def __init__(self, approved: bool, reason: str = "", action: str = "pass"):
        self.approved = approved
        self.reason = reason
        self.action = action  # "pass", "block", "kill" (pause strategy)


class RiskManager:
    def __init__(self):
        # Global limits
        self.max_total_lots: float = 1.0
        self.max_account_drawdown_pct: float = 10.0
        self.daily_loss_limit: float = 500.0
        self.kill_switch_active: bool = False

        # Per-strategy daily trade counts
        self._daily_trades: dict[int, int] = {}
        self._last_reset_date: date = date.today()

        # Track initial balance for drawdown calculation
        self._initial_balance: float | None = None

    def check_signal(
        self,
        signal: Signal,
        strategy: Strategy,
        positions: list[Position],
        account: AccountInfo | None,
    ) -> RiskDecision:
        """Check if a signal passes all risk rules."""
        autonomy = strategy.config.autonomy
        risk = strategy.config.risk

        # Reset daily counters if new day
        today = date.today()
        if today != self._last_reset_date:
            self._daily_trades.clear()
            self._last_reset_date = today

        # Kill switch check
        if self.kill_switch_active:
            return RiskDecision(False, "Kill switch is active", "block")

        # Exit signals always pass (we want to allow closing)
        if signal.direction in (SignalDirection.EXIT_LONG, SignalDirection.EXIT_SHORT):
            return RiskDecision(True, "Exit signal — always allowed")

        # Signal-only mode: log everything, block nothing
        if autonomy == Autonomy.SIGNAL_ONLY:
            return RiskDecision(True, "Signal-only mode — user decides")

        # --- Risk Checks for Semi-Auto and Full-Auto ---

        # 1. Max lot size
        if risk.max_lot <= 0:
            return RiskDecision(False, f"Max lot is 0 — trading disabled", "block")

        # 2. Max daily trades
        sid = signal.strategy_id
        daily_count = self._daily_trades.get(sid, 0)
        if daily_count >= risk.max_daily_trades:
            return RiskDecision(
                False,
                f"Daily trade limit reached ({daily_count}/{risk.max_daily_trades})",
                "block",
            )

        # 3. Max open positions (per strategy)
        strategy_positions = [p for p in positions if True]  # All positions for now
        if len(strategy_positions) >= risk.max_open_positions:
            return RiskDecision(
                False,
                f"Max open positions reached ({len(strategy_positions)}/{risk.max_open_positions})",
                "block",
            )

        # 4. Max total exposure (global)
        total_lots = sum(p.lot for p in positions)
        if total_lots + risk.max_lot > self.max_total_lots:
            return RiskDecision(
                False,
                f"Total exposure would exceed limit ({total_lots + risk.max_lot:.2f}/{self.max_total_lots})",
                "block",
            )

        # 5. Drawdown check
        if account:
            if self._initial_balance is None:
                self._initial_balance = account.balance

            drawdown_pct = 0.0
            if self._initial_balance > 0:
                drawdown_pct = (
                    (self._initial_balance - account.equity) / self._initial_balance
                ) * 100

            # Per-strategy drawdown
            if drawdown_pct > risk.max_drawdown_pct:
                action = "kill" if autonomy == Autonomy.FULL_AUTO else "block"
                return RiskDecision(
                    False,
                    f"Drawdown {drawdown_pct:.1f}% exceeds limit {risk.max_drawdown_pct}%",
                    action,
                )

            # Global drawdown
            if drawdown_pct > self.max_account_drawdown_pct:
                return RiskDecision(
                    False,
                    f"Account drawdown {drawdown_pct:.1f}% exceeds global limit {self.max_account_drawdown_pct}%",
                    "kill",
                )

        # 6. Spread check (basic — can be enhanced later)
        # Skipped for MVP, will add in Phase 2

        # All checks passed
        return RiskDecision(True, "All risk checks passed")

    def record_trade(self, strategy_id: int):
        """Record that a trade was made for daily counting."""
        self._daily_trades[strategy_id] = self._daily_trades.get(strategy_id, 0) + 1

    def activate_kill_switch(self):
        """Activate global kill switch."""
        self.kill_switch_active = True
        logger.warning("KILL SWITCH ACTIVATED — all trading halted")

    def deactivate_kill_switch(self):
        """Deactivate global kill switch."""
        self.kill_switch_active = False
        logger.info("Kill switch deactivated")

    def update_global_limits(
        self,
        max_total_lots: float | None = None,
        max_account_drawdown_pct: float | None = None,
        daily_loss_limit: float | None = None,
    ):
        if max_total_lots is not None:
            self.max_total_lots = max_total_lots
        if max_account_drawdown_pct is not None:
            self.max_account_drawdown_pct = max_account_drawdown_pct
        if daily_loss_limit is not None:
            self.daily_loss_limit = daily_loss_limit
