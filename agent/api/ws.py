"""WebSocket handler for live updates."""

import asyncio
import json
from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger

from agent.api.auth import verify_token

router = APIRouter()


class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WS client connected ({len(self.active_connections)} total)")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"WS client disconnected ({len(self.active_connections)} total)")

    async def broadcast(self, message: dict):
        """Send message to all connected clients."""
        data = json.dumps(message, default=str)
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(data)
            except Exception:
                disconnected.append(connection)
        for conn in disconnected:
            self.disconnect(conn)


ws_manager = ConnectionManager()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = ""):
    """WebSocket endpoint for live updates. Authenticate via ?token=JWT."""
    # Verify JWT
    if not token or not verify_token(token):
        await websocket.close(code=4001, reason="Unauthorized")
        return

    await ws_manager.connect(websocket)
    try:
        while True:
            # Keep connection alive, handle client messages
            data = await websocket.receive_text()
            # Client can send ping/pong or commands
            if data == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


# Helper functions for broadcasting events

async def broadcast_tick(symbol: str, bid: float, ask: float):
    await ws_manager.broadcast({
        "type": "tick",
        "symbol": symbol,
        "bid": bid,
        "ask": ask,
        "timestamp": datetime.now().isoformat(),
    })


async def broadcast_signal(signal_data: dict):
    await ws_manager.broadcast({
        "type": "signal",
        **signal_data,
    })


async def broadcast_trade(trade_data: dict):
    await ws_manager.broadcast({
        "type": "trade",
        **trade_data,
    })


async def broadcast_strategy_update(strategy_id: int, enabled: bool):
    await ws_manager.broadcast({
        "type": "strategy_update",
        "strategy_id": strategy_id,
        "enabled": enabled,
    })
