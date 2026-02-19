"""ZMQ Bridge — connects to MT5 Expert Advisor via ZeroMQ."""

import asyncio
import json
import time
from datetime import datetime
from typing import Any, Callable

import zmq
import zmq.asyncio
from loguru import logger

from agent.config import settings
from agent.models.market import Bar, IndicatorValue, Tick
from agent.models.trade import AccountInfo, Position


class ZMQBridge:
    def __init__(self):
        self.ctx = zmq.asyncio.Context()
        self.req_socket: zmq.asyncio.Socket | None = None
        self.sub_socket: zmq.asyncio.Socket | None = None
        self._connected = False
        self._tick_callbacks: list[Callable] = []
        self._tick_task: asyncio.Task | None = None
        self._req_lock = asyncio.Lock()

    async def connect(self):
        """Connect to MT5 EA's ZMQ sockets."""
        try:
            # REQ socket for commands
            self.req_socket = self.ctx.socket(zmq.REQ)
            self.req_socket.setsockopt(zmq.RCVTIMEO, 5000)  # 5s timeout
            self.req_socket.setsockopt(zmq.SNDTIMEO, 5000)
            self.req_socket.setsockopt(zmq.LINGER, 0)
            self.req_socket.connect(settings.zmq_rep_address)

            # SUB socket for tick stream
            self.sub_socket = self.ctx.socket(zmq.SUB)
            self.sub_socket.setsockopt(zmq.RCVTIMEO, 1000)
            self.sub_socket.setsockopt(zmq.LINGER, 0)
            self.sub_socket.connect(settings.zmq_pub_address)
            self.sub_socket.subscribe(b"")  # subscribe to all

            self._connected = True
            logger.info(
                f"ZMQ connected — REQ: {settings.zmq_rep_address}, SUB: {settings.zmq_pub_address}"
            )
        except Exception as e:
            logger.error(f"ZMQ connection failed: {e}")
            self._connected = False
            raise

    async def disconnect(self):
        """Close all ZMQ sockets."""
        if self._tick_task and not self._tick_task.done():
            self._tick_task.cancel()
            try:
                await self._tick_task
            except asyncio.CancelledError:
                pass
        if self.req_socket:
            self.req_socket.close()
        if self.sub_socket:
            self.sub_socket.close()
        self.ctx.term()
        self._connected = False
        logger.info("ZMQ disconnected")

    @property
    def connected(self) -> bool:
        return self._connected

    async def _send_command(self, command: str, params: dict[str, Any] = {}) -> dict:
        """Send a command to the EA and return the response."""
        if not self._connected or not self.req_socket:
            raise ConnectionError("ZMQ not connected")

        payload = json.dumps({"command": command, **params})

        async with self._req_lock:
            try:
                await self.req_socket.send_string(payload)
                response = await self.req_socket.recv_string()
                return json.loads(response)
            except zmq.error.Again:
                logger.warning(f"ZMQ timeout on command: {command}")
                # Reset socket on timeout
                self.req_socket.close()
                self.req_socket = self.ctx.socket(zmq.REQ)
                self.req_socket.setsockopt(zmq.RCVTIMEO, 5000)
                self.req_socket.setsockopt(zmq.SNDTIMEO, 5000)
                self.req_socket.setsockopt(zmq.LINGER, 0)
                self.req_socket.connect(settings.zmq_rep_address)
                return {"success": False, "error": "Timeout"}
            except Exception as e:
                logger.error(f"ZMQ command error ({command}): {e}")
                return {"success": False, "error": str(e)}

    # --- Market Data ---

    async def get_tick(self, symbol: str) -> Tick | None:
        resp = await self._send_command("GET_TICK", {"symbol": symbol})
        if not resp.get("success", False):
            return None
        return Tick(
            symbol=resp["symbol"],
            bid=resp["bid"],
            ask=resp["ask"],
            spread=resp.get("spread", resp["ask"] - resp["bid"]),
            timestamp=datetime.fromisoformat(resp["timestamp"]),
        )

    async def get_bars(
        self, symbol: str, timeframe: str, count: int = 100
    ) -> list[Bar]:
        resp = await self._send_command(
            "GET_BARS", {"symbol": symbol, "timeframe": timeframe, "count": count}
        )
        if not resp.get("success", False):
            return []
        return [
            Bar(
                symbol=symbol,
                timeframe=timeframe,
                time=datetime.fromisoformat(b["time"]),
                open=b["open"],
                high=b["high"],
                low=b["low"],
                close=b["close"],
                volume=b.get("volume", 0),
            )
            for b in resp.get("bars", [])
        ]

    async def get_indicator(
        self,
        symbol: str,
        timeframe: str,
        name: str,
        params: dict[str, Any],
        count: int = 3,
    ) -> dict[str, list[float]]:
        """Get indicator values from MT5. Returns dict of buffer_name → list[float]."""
        resp = await self._send_command(
            "GET_INDICATOR",
            {
                "symbol": symbol,
                "timeframe": timeframe,
                "indicator": name,
                "params": params,
                "count": count,
            },
        )
        if not resp.get("success", False):
            logger.warning(
                f"Indicator failed: {name} on {symbol}/{timeframe}: {resp.get('error')}"
            )
            return {}
        return resp.get("values", {})

    # --- Trading ---

    async def open_order(
        self,
        symbol: str,
        order_type: str,
        lot: float,
        sl: float | None = None,
        tp: float | None = None,
    ) -> dict:
        params: dict[str, Any] = {
            "symbol": symbol,
            "type": order_type,
            "lot": lot,
        }
        if sl is not None:
            params["sl"] = sl
        if tp is not None:
            params["tp"] = tp
        return await self._send_command("OPEN_ORDER", params)

    async def close_order(self, ticket: int) -> dict:
        return await self._send_command("CLOSE_ORDER", {"ticket": ticket})

    async def modify_order(
        self, ticket: int, sl: float | None = None, tp: float | None = None
    ) -> dict:
        params: dict[str, Any] = {"ticket": ticket}
        if sl is not None:
            params["sl"] = sl
        if tp is not None:
            params["tp"] = tp
        return await self._send_command("MODIFY_ORDER", params)

    async def get_positions(self) -> list[Position]:
        resp = await self._send_command("GET_POSITIONS")
        if not resp.get("success", False):
            return []
        return [
            Position(
                ticket=p["ticket"],
                symbol=p["symbol"],
                direction="BUY" if p["type"] == 0 else "SELL",
                lot=p["lot"],
                open_price=p["open_price"],
                current_price=p.get("current_price", 0),
                sl=p.get("sl"),
                tp=p.get("tp"),
                pnl=p.get("pnl", 0),
                open_time=datetime.fromisoformat(p["open_time"]),
            )
            for p in resp.get("positions", [])
        ]

    async def get_account(self) -> AccountInfo | None:
        resp = await self._send_command("GET_ACCOUNT")
        if not resp.get("success", False):
            return None
        return AccountInfo(
            balance=resp["balance"],
            equity=resp["equity"],
            margin=resp["margin"],
            free_margin=resp["free_margin"],
            margin_level=resp.get("margin_level"),
            profit=resp.get("profit", 0),
        )

    async def get_history(
        self, from_date: str, to_date: str
    ) -> list[dict]:
        resp = await self._send_command(
            "GET_HISTORY", {"from_date": from_date, "to_date": to_date}
        )
        if not resp.get("success", False):
            return []
        return resp.get("orders", [])

    async def subscribe_symbols(self, symbols: list[str]) -> bool:
        resp = await self._send_command("SUBSCRIBE", {"symbols": symbols})
        return resp.get("success", False)

    # --- Tick Stream ---

    def on_tick(self, callback: Callable):
        """Register a callback for incoming ticks."""
        self._tick_callbacks.append(callback)

    async def start_tick_listener(self):
        """Start listening for ticks on the SUB socket."""
        self._tick_task = asyncio.create_task(self._tick_loop())

    async def _tick_loop(self):
        """Background loop that reads ticks from PUB socket."""
        logger.info("Tick listener started")
        while self._connected:
            try:
                if self.sub_socket is None:
                    break
                msg = await self.sub_socket.recv_string()
                data = json.loads(msg)
                tick = Tick(
                    symbol=data["symbol"],
                    bid=data["bid"],
                    ask=data["ask"],
                    spread=data.get("spread", data["ask"] - data["bid"]),
                    timestamp=datetime.fromisoformat(data["timestamp"]),
                )
                for cb in self._tick_callbacks:
                    try:
                        result = cb(tick)
                        if asyncio.iscoroutine(result):
                            await result
                    except Exception as e:
                        logger.error(f"Tick callback error: {e}")
            except zmq.error.Again:
                continue  # timeout, no tick available
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Tick loop error: {e}")
                await asyncio.sleep(1)
        logger.info("Tick listener stopped")

    # --- Health Check ---

    async def ping(self) -> bool:
        """Check if EA is responding."""
        resp = await self._send_command("GET_ACCOUNT")
        return resp.get("success", False)
