"""Trade history and open positions endpoints."""

from fastapi import APIRouter, Depends

from agent.api.auth import get_current_user

router = APIRouter(prefix="/api/trades", tags=["trades"])


@router.get("")
async def list_trades(
    strategy_id: int | None = None,
    symbol: str | None = None,
    limit: int = 50,
    offset: int = 0,
    user: str = Depends(get_current_user),
):
    from agent.api.main import app_state
    trades = await app_state["db"].list_trades(
        strategy_id=strategy_id, symbol=symbol, limit=limit, offset=offset
    )
    return [
        {
            "id": t.id,
            "signal_id": t.signal_id,
            "strategy_id": t.strategy_id,
            "symbol": t.symbol,
            "direction": t.direction,
            "lot": t.lot,
            "open_price": t.open_price,
            "close_price": t.close_price,
            "sl": t.sl,
            "tp": t.tp,
            "pnl": t.pnl,
            "ticket": t.ticket,
            "open_time": str(t.open_time) if t.open_time else None,
            "close_time": str(t.close_time) if t.close_time else None,
        }
        for t in trades
    ]


@router.get("/open")
async def get_open_positions(user: str = Depends(get_current_user)):
    from agent.api.main import app_state
    bridge = app_state["bridge"]
    positions = await bridge.get_positions()
    return [
        {
            "ticket": p.ticket,
            "symbol": p.symbol,
            "direction": p.direction,
            "lot": p.lot,
            "open_price": p.open_price,
            "current_price": p.current_price,
            "sl": p.sl,
            "tp": p.tp,
            "pnl": p.pnl,
            "open_time": str(p.open_time),
        }
        for p in positions
    ]
