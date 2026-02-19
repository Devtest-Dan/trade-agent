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
    emoji = "🟢" if "LONG" in signal.direction.value else "🔴"
    msg = (
        f"{emoji} <b>{signal.direction.value}</b> {signal.symbol}\n"
        f"Strategy: {signal.strategy_name}\n"
        f"Price: {signal.price_at_signal:.2f}\n"
        f"Status: {signal.status.value}"
    )
    if signal.ai_reasoning:
        msg += f"\n\n{signal.ai_reasoning}"
    await send_telegram(msg)
