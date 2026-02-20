"""Live market data endpoints."""

from fastapi import APIRouter, Depends

from agent.api.auth import get_current_user

router = APIRouter(prefix="/api", tags=["market"])


@router.get("/market/{symbol}")
async def get_market_data(symbol: str, user: str = Depends(get_current_user)):
    """Get current price and indicator snapshot for a symbol."""
    from agent.api.main import app_state
    bridge = app_state["bridge"]

    tick = await bridge.get_tick(symbol)
    if not tick:
        return {"symbol": symbol, "connected": False}

    return {
        "symbol": symbol,
        "connected": True,
        "bid": tick.bid,
        "ask": tick.ask,
        "spread": tick.spread,
        "timestamp": tick.timestamp.isoformat(),
    }


@router.get("/account")
async def get_account(user: str = Depends(get_current_user)):
    """Get MT5 account info."""
    from agent.api.main import app_state
    account = await app_state["bridge"].get_account()
    if not account:
        return {"connected": False}
    return {
        "connected": True,
        "balance": account.balance,
        "equity": account.equity,
        "margin": account.margin,
        "free_margin": account.free_margin,
        "margin_level": account.margin_level,
        "profit": account.profit,
    }
