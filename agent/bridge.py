"""ZMQ Bridge — connects to MT5 Expert Advisor via ZeroMQ."""

import asyncio
import json
from datetime import datetime
from typing import Any, Callable

import zmq
import zmq.asyncio
from loguru import logger

from agent.config import settings
from agent.models.market import Bar, Tick
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
            self.req_socket = self.ctx.socket(zmq.REQ)
            self.req_socket.setsockopt(zmq.RCVTIMEO, 5000)
            self.req_socket.setsockopt(zmq.SNDTIMEO, 5000)
            self.req_socket.setsockopt(zmq.LINGER, 0)
            self.req_socket.connect(settings.zmq_rep_address)

            self.sub_socket = self.ctx.socket(zmq.SUB)
            self.sub_socket.setsockopt(zmq.RCVTIMEO, 1000)
            self.sub_socket.setsockopt(zmq.LINGER, 0)
            self.sub_socket.connect(settings.zmq_pub_address)
            self.sub_socket.subscribe(b"")

            self._connected = True
            logger.info(
                f"ZMQ connected — REQ: {settings.zmq_rep_address}, SUB: {settings.zmq_pub_address}"
            )
        except Exception as e:
            logger.error(f"ZMQ connection failed: {e}")
            self._connected = False
            raise

    async def disconnect(self):
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

    async def _send_command(self, command: str, params: dict[str, Any] | None = None) -> dict:
        """Send a command to the EA and return the response.

        EA expects: {"command": "CMD", "params": {...}}
        EA returns: {"success": true, "data": {...}} or {"success": false, "error": "..."}
        """
        if not self._connected or not self.req_socket:
            raise ConnectionError("ZMQ not connected")

        payload: dict[str, Any] = {"command": command}
        if params:
            payload["params"] = params

        async with self._req_lock:
            try:
                await self.req_socket.send_string(json.dumps(payload))
                response = await self.req_socket.recv_string()
                return json.loads(response)
            except zmq.error.Again:
                logger.warning(f"ZMQ timeout on command: {command}")
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
        d = resp["data"]
        return Tick(
            symbol=d["symbol"],
            bid=d["bid"],
            ask=d["ask"],
            spread=d.get("spread", d["ask"] - d["bid"]),
            timestamp=datetime.fromisoformat(d["timestamp"]),
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
            for b in resp.get("data", [])
        ]

    async def get_indicator(
        self,
        symbol: str,
        timeframe: str,
        name: str,
        params: dict[str, Any],
        count: int = 3,
    ) -> dict[str, list[float]]:
        """Get indicator values from MT5. Returns dict of buffer_name -> list[float]."""
        resp = await self._send_command(
            "GET_INDICATOR",
            {
                "symbol": symbol,
                "timeframe": timeframe,
                "name": name.upper(),
                "params": params,
                "count": count,
            },
        )
        if not resp.get("success", False):
            logger.warning(
                f"Indicator failed: {name} on {symbol}/{timeframe}: {resp.get('error')}"
            )
            return {}
        # EA returns data as array of objects like [{"value": 53.7}, {"value": 53.1}]
        # or [{"k": 45, "d": 42}, ...] for multi-output indicators
        data = resp.get("data", [])
        if not data:
            return {}
        # Transpose: [{k: v1}, {k: v2}] -> {k: [v1, v2]}
        result: dict[str, list[float]] = {}
        for item in data:
            if isinstance(item, dict):
                for key, val in item.items():
                    if key not in result:
                        result[key] = []
                    result[key].append(float(val))
        return result

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
        resp = await self._send_command("OPEN_ORDER", params)
        if resp.get("success"):
            d = resp.get("data", {})
            return {"success": True, "ticket": d.get("ticket", 0)}
        return {"success": False, "error": resp.get("error", "Unknown")}

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
                direction="BUY" if p.get("type", 0) == 0 else "SELL",
                lot=p["lot"],
                open_price=p["open_price"],
                current_price=p.get("current_price", 0),
                sl=p.get("sl"),
                tp=p.get("tp"),
                pnl=p.get("pnl", 0),
                open_time=datetime.fromisoformat(p["open_time"]),
            )
            for p in resp.get("data", [])
        ]

    async def get_account(self) -> AccountInfo | None:
        resp = await self._send_command("GET_ACCOUNT")
        if not resp.get("success", False):
            return None
        d = resp["data"]
        return AccountInfo(
            balance=d["balance"],
            equity=d["equity"],
            margin=d["margin"],
            free_margin=d["free_margin"],
            margin_level=d.get("margin_level"),
            profit=d.get("profit", 0),
        )

    async def get_history(self, from_date: str, to_date: str) -> list[dict]:
        resp = await self._send_command(
            "GET_HISTORY", {"from_date": from_date, "to_date": to_date}
        )
        if not resp.get("success", False):
            return []
        return resp.get("data", [])

    async def partial_close_order(self, ticket: int, lot: float) -> dict:
        """Partial close by opening an opposite position for the given lot size.

        For MT5 netting accounts, this effectively reduces the position size.
        """
        # First get the position to know its direction
        positions = await self.get_positions()
        target = None
        for pos in positions:
            if pos.ticket == ticket:
                target = pos
                break

        if not target:
            return {"success": False, "error": f"Position {ticket} not found"}

        opposite = "SELL" if target.direction == "BUY" else "BUY"
        return await self.open_order(
            symbol=target.symbol,
            order_type=opposite,
            lot=lot,
        )

    async def subscribe_symbols(self, symbols: list[str]) -> bool:
        resp = await self._send_command("SUBSCRIBE", {"symbols": symbols})
        return resp.get("success", False)

    # --- Tick Stream ---

    def on_tick(self, callback: Callable):
        self._tick_callbacks.append(callback)

    async def start_tick_listener(self):
        self._tick_task = asyncio.create_task(self._tick_loop())

    async def _tick_loop(self):
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
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Tick loop error: {e}")
                await asyncio.sleep(1)
        logger.info("Tick listener stopped")

    # --- Health Check ---

    async def ping(self) -> bool:
        resp = await self._send_command("PING")
        return resp.get("success", False)
