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
from agent.risk_manager import RiskManager
from agent.strategy_engine import StrategyEngine
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

    strategy_engine.on_signal(on_signal)
    trade_executor.on_trade(on_trade)
    data_manager.on_bar_close(strategy_engine.evaluate_on_bar_close)

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

    # Store in app state
    app_state.update({
        "db": db,
        "bridge": bridge,
        "data_manager": data_manager,
        "ai_service": ai_service,
        "risk_manager": risk_manager,
        "strategy_engine": strategy_engine,
        "trade_executor": trade_executor,
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
        version="0.1.0",
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

    app.include_router(strategies_router)
    app.include_router(signals_router)
    app.include_router(trades_router)
    app.include_router(market_router)
    app.include_router(settings_router)
    app.include_router(ws_router)

    return app
