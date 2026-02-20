"""Telegram notifications for trading signals (optional)."""

import httpx
from loguru import logger

from agent.config import settings
from agent.models.signal import Signal


async def send_telegram(message: str):
    """Send a message via Telegram bot."""
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        return

    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    try:
        async with httpx.AsyncClient() as client:
            await client.post(url, json={
                "chat_id": settings.telegram_chat_id,
                "text": message,
                "parse_mode": "HTML",
            })
    except Exception as e:
        logger.error(f"Telegram send failed: {e}")


async def notify_signal(signal: Signal):
    """Send signal notification to Telegram."""
    direction = signal.direction.value if hasattr(signal.direction, 'value') else str(signal.direction)
    status = signal.status.value if hasattr(signal.status, 'value') else str(signal.status)
    emoji = "🟢" if "LONG" in direction or "BUY" in direction else "🔴"
    msg = (
        f"{emoji} <b>{direction}</b> {signal.symbol}\n"
        f"Strategy: {signal.strategy_name}\n"
        f"Price: {signal.price_at_signal:.2f}\n"
        f"Status: {status}"
    )
    if signal.ai_reasoning:
        msg += f"\n\n{signal.ai_reasoning}"
    await send_telegram(msg)


async def notify_trade_opened(symbol: str, direction: str, lot: float, price: float, sl: float | None, tp: float | None, ticket: int):
    """Send trade opened notification to Telegram."""
    emoji = "🟢" if "BUY" in direction or "LONG" in direction else "🔴"
    msg = (
        f"{emoji} <b>TRADE OPENED</b>\n"
        f"{direction} {symbol} x{lot}\n"
        f"Price: {price:.2f}\n"
        f"SL: {sl:.2f if sl else 'None'} | TP: {tp:.2f if tp else 'None'}\n"
        f"Ticket: #{ticket}"
    )
    await send_telegram(msg)


async def notify_management_event(symbol: str, action: str, details: dict):
    """Send position management notification to Telegram."""
    msg = f"⚙️ <b>{action.upper()}</b> {symbol}\n"
    for k, v in details.items():
        if isinstance(v, float):
            msg += f"{k}: {v:.2f}\n"
        else:
            msg += f"{k}: {v}\n"
    await send_telegram(msg)
