"""
Test Custom Indicators via ZMQ Bridge
======================================
Connects directly to the TradeAgent EA's ZMQ REP socket and queries
each custom indicator to verify data is flowing correctly.

Prerequisites:
  - MT5 running with TradeAgent EA attached to a chart
  - EA's ZMQ REP socket on port 5555
  - All custom indicators compiled (.ex5) and installed in MT5 Indicators folder:
      * SMC_Structure
      * OB & FVG Indicator
      * Nadaraya Watson Envelope Indicator
      * tpo
      * Kernel Awesome Oscillator

Usage:
    python scripts/test_custom_indicators.py
    python scripts/test_custom_indicators.py --symbol EURUSD --timeframe M15
"""

import argparse
import json
import sys
import time

import zmq

# MT5 EMPTY_VALUE (DBL_MAX) — indicator buffers use this for "no data"
EMPTY_VALUE_THRESHOLD = 1.0e300

ZMQ_TIMEOUT_MS = 15000  # 15 seconds (custom indicators may need time to load)

# Global socket reference for reconnection
_socket_info = {"socket": None, "ctx": None, "address": None}


def send_command(socket: zmq.Socket, command: str, params: dict | None = None) -> dict:
    """Send a JSON command to the EA and return the parsed response.
    Handles ZMQ timeouts by reconnecting the socket."""
    payload = {"command": command}
    if params:
        payload["params"] = params
    try:
        socket.send_string(json.dumps(payload))
        response = socket.recv_string()
        return json.loads(response)
    except zmq.error.Again:
        # Timeout — reconnect the socket to reset REQ/REP state
        print(f"  [ZMQ timeout on {command} — reconnecting socket]")
        info = _socket_info
        socket.close()
        new_socket = info["ctx"].socket(zmq.REQ)
        new_socket.setsockopt(zmq.RCVTIMEO, ZMQ_TIMEOUT_MS)
        new_socket.setsockopt(zmq.SNDTIMEO, ZMQ_TIMEOUT_MS)
        new_socket.setsockopt(zmq.LINGER, 0)
        new_socket.connect(info["address"])
        info["socket"] = new_socket
        return {"success": False, "error": f"ZMQ timeout on {command} (EA may be busy)"}


def is_empty_value(val) -> bool:
    """Check if a value is MT5's EMPTY_VALUE (no data at this bar)."""
    if val is None:
        return True
    try:
        return abs(float(val)) > EMPTY_VALUE_THRESHOLD
    except (TypeError, ValueError):
        return True


def format_value(val, name: str = "") -> str:
    """Format a buffer value for display."""
    if val is None:
        return "null"
    if is_empty_value(val):
        return "EMPTY"
    fv = float(val)
    # Type/color buffers are small integers
    if name in ("trend", "ob_type", "fvg_type", "fvg_filled", "fvg_reversed",
                 "swing_high_clr", "swing_low_clr"):
        return str(int(fv))
    # Price-level buffers
    if abs(fv) > 10:
        return f"{fv:.5f}"
    return f"{fv:.8f}"


def test_ping(socket: zmq.Socket) -> bool:
    """Verify EA is responsive."""
    print("=" * 70)
    print("PING TEST")
    print("=" * 70)
    resp = send_command(socket, "PING")
    if resp.get("success"):
        print("  EA responded: pong")
        return True
    else:
        print(f"  FAILED: {resp.get('error', 'No response')}")
        return False


def test_tick(socket: zmq.Socket, symbol: str) -> bool:
    """Verify symbol is available and we can get tick data."""
    print(f"\nGET_TICK — {symbol}")
    print("-" * 50)
    resp = send_command(socket, "GET_TICK", {"symbol": symbol})
    if resp.get("success"):
        d = resp["data"]
        print(f"  Bid: {d['bid']}  Ask: {d['ask']}  Spread: {d.get('spread', 'N/A')}")
        print(f"  Time: {d['timestamp']}")
        return True
    else:
        print(f"  FAILED: {resp.get('error')}")
        return False


def test_indicator(
    socket: zmq.Socket,
    symbol: str,
    timeframe: str,
    indicator_name: str,
    display_name: str,
    params: dict,
    count: int = 5,
    max_retries: int = 5,
) -> dict:
    """
    Test a single custom indicator. Returns a result dict with status info.
    Retries up to max_retries times with increasing delays if indicator is loading.
    """
    print(f"\n{'=' * 70}")
    print(f"  {display_name}")
    print(f"  Name: {indicator_name} | Path: {params.get('path', indicator_name)}")
    print(f"  Symbol: {symbol} | TF: {timeframe} | Bars: {count}")
    print(f"  Buffers requested: {params.get('buffers', 'auto')}")
    print(f"{'=' * 70}")

    full_params = dict(params)
    full_params["symbol"] = symbol
    full_params["timeframe"] = timeframe

    result = {
        "name": indicator_name,
        "display": display_name,
        "success": False,
        "error": None,
        "buffers_with_data": 0,
        "buffers_total": 0,
        "bars_returned": 0,
    }

    resp = None
    for attempt in range(max_retries + 1):
        resp = send_command(
            socket,
            "GET_INDICATOR",
            {
                "symbol": symbol,
                "timeframe": timeframe,
                "name": indicator_name,
                "params": full_params,
                "count": count,
            },
        )

        if resp.get("success"):
            break

        error = resp.get("error", "Unknown error")
        err_lower = error.lower()
        retryable = "still loading" in err_lower or "not ready" in err_lower or "barscalculated" in err_lower
        if retryable and attempt < max_retries:
            wait = 3 + attempt * 2  # 3s, 5s, 7s, 9s, 11s
            print(f"  Attempt {attempt + 1}: Indicator not ready, waiting {wait}s...")
            time.sleep(wait)
            continue

        # Non-retryable error or max retries exhausted
        result["error"] = error
        print(f"\n  ERROR: {error}")
        if attempt == max_retries:
            print(f"  Gave up after {max_retries + 1} attempts.")
        return result

    data = resp.get("data", [])
    result["bars_returned"] = len(data)
    result["success"] = True

    if not data:
        print("\n  WARNING: Success but no data returned (empty array)")
        return result

    # Analyze buffers
    buffer_names = list(data[0].keys()) if data else []
    result["buffers_total"] = len(buffer_names)

    # Check each buffer across all bars
    buffer_stats = {}
    for buf_name in buffer_names:
        values = [bar.get(buf_name) for bar in data]
        non_empty = [v for v in values if not is_empty_value(v)]
        buffer_stats[buf_name] = {
            "values": values,
            "non_empty_count": len(non_empty),
            "total_count": len(values),
            "has_data": len(non_empty) > 0,
        }

    buffers_with_data = sum(1 for s in buffer_stats.values() if s["has_data"])
    result["buffers_with_data"] = buffers_with_data

    # Print results
    print(f"\n  Bars returned: {len(data)}")
    print(f"  Buffers: {len(buffer_names)} total, {buffers_with_data} with data")
    print()

    # Print buffer values in a table
    # Header
    col_width = 18
    header = f"  {'Buffer':<22}"
    for i in range(len(data)):
        header += f"{'Bar ' + str(i):>{col_width}}"
    print(header)
    print(f"  {'-' * 22}" + ("-" * col_width) * len(data))

    for buf_name in buffer_names:
        stats = buffer_stats[buf_name]
        status = "OK" if stats["has_data"] else "EMPTY"
        row = f"  {buf_name:<20} "
        if not stats["has_data"]:
            row += f"{'-- all EMPTY --':>{col_width * len(data)}}"
        else:
            for val in stats["values"]:
                formatted = format_value(val, buf_name)
                row += f"{formatted:>{col_width}}"
        # Add status marker
        marker = " [OK]" if stats["has_data"] else " [NO DATA]"
        row += marker
        print(row)

    # Summary line
    print()
    if buffers_with_data == len(buffer_names):
        print(f"  RESULT: ALL {len(buffer_names)} buffers have data")
    elif buffers_with_data > 0:
        empty_bufs = [n for n, s in buffer_stats.items() if not s["has_data"]]
        print(f"  RESULT: {buffers_with_data}/{len(buffer_names)} buffers have data")
        print(f"  Empty buffers: {', '.join(empty_bufs)}")
        print(f"  NOTE: Some buffers being EMPTY is normal (e.g., swing highs only")
        print(f"        appear at specific bars, fill buffers may be unused)")
    else:
        print(f"  RESULT: NO DATA in any buffer — indicator may not be loaded or")
        print(f"          the path/name might be wrong")

    return result


def probe_buffers(
    socket: zmq.Socket,
    symbol: str,
    timeframe: str,
    indicator_name: str,
    path: str,
    max_buffers: int = 20,
    max_retries: int = 5,
) -> int:
    """
    Probe an unknown indicator to discover how many buffers it has.
    Requests max_buffers named buf0..bufN and checks which return data.
    """
    print(f"\n  Probing {indicator_name} for buffer count (up to {max_buffers})...")

    buf_names = [f"buf{i}" for i in range(max_buffers)]

    resp = None
    for attempt in range(max_retries + 1):
        resp = send_command(
            socket,
            "GET_INDICATOR",
            {
                "symbol": symbol,
                "timeframe": timeframe,
                "name": indicator_name,
                "params": {
                    "path": path,
                    "buffer_names": buf_names,
                    "buffers": max_buffers,
                },
                "count": 10,  # Read 10 bars to have a good sample
            },
        )

        if resp.get("success"):
            break

        error = resp.get("error", "Unknown")
        err_lower = error.lower()
        retryable = "still loading" in err_lower or "not ready" in err_lower or "barscalculated" in err_lower
        if retryable and attempt < max_retries:
            wait = 3 + attempt * 2
            print(f"  Attempt {attempt + 1}: Indicator not ready, waiting {wait}s...")
            time.sleep(wait)
            continue

        print(f"  Probe FAILED: {error}")
        if attempt == max_retries:
            print(f"  Gave up after {max_retries + 1} attempts.")
        return 0

    if not resp or not resp.get("success"):
        return 0

    data = resp.get("data", [])
    if not data:
        print("  Probe returned empty data")
        return 0

    # Find highest buffer index that has any non-empty data across all bars
    highest_with_data = -1
    for bar in data:
        for i in range(max_buffers):
            key = f"buf{i}"
            val = bar.get(key)
            if val is not None and not is_empty_value(val):
                highest_with_data = max(highest_with_data, i)

    buffer_count = highest_with_data + 1
    print(f"  Detected {buffer_count} active buffers (highest index with data: {highest_with_data})")

    # Print sample values for the discovered buffers
    if buffer_count > 0:
        print(f"\n  Buffer sample (bar 0):")
        for i in range(min(buffer_count, max_buffers)):
            key = f"buf{i}"
            val = data[0].get(key)
            formatted = format_value(val)
            has_any = any(not is_empty_value(bar.get(key)) for bar in data)
            status = "data" if has_any else "empty"
            print(f"    buf{i}: {formatted} ({status})")

    return buffer_count


# ─── Indicator definitions ────────────────────────────────────────────

INDICATORS = [
    {
        "name": "SMC_Structure",
        "display": "SMC Structure (Smart Money Concepts)",
        "params": {
            "path": "SMC_Structure",
            "buffer_names": [
                "swing_high", "swing_high_clr", "swing_low", "swing_low_clr",
                "trend", "strong_low", "strong_high", "ref_high", "ref_low",
                "equilibrium", "ote_top", "ote_bottom",
            ],
            "buffers": 12,
        },
    },
    {
        "name": "OB_FVG",
        "display": "Order Blocks & Fair Value Gaps",
        "params": {
            "path": "OB & FVG Indicator",
            "buffer_names": [
                "zz1_up", "zz1_down", "zz2_up", "zz2_down",
                "zz3_up", "zz3_down", "combined_all", "combined_partial",
                "ob_upper", "ob_lower", "overlap_upper", "overlap_lower",
                "ob_type", "ob_time", "hline_upper", "hline_lower",
                "fvg_upper", "fvg_lower", "fvg_filled", "fvg_type", "fvg_reversed",
            ],
            "buffers": 21,
        },
    },
    {
        "name": "NW_Envelope",
        "display": "Nadaraya-Watson Envelope",
        "params": {
            "path": "Nadaraya Watson Envelope Indicator",
            "buffer_names": [
                "upper_far_fill_hi", "upper_far_fill_lo",
                "upper_near_fill_hi", "upper_near_fill_lo",
                "lower_near_fill_hi", "lower_near_fill_lo",
                "lower_far_fill_hi", "lower_far_fill_lo",
                "nw_bullish", "nw_bearish",
                "upper_far", "upper_avg", "upper_near",
                "lower_near", "lower_avg", "lower_far",
            ],
            "buffers": 16,
        },
    },
]


def main():
    parser = argparse.ArgumentParser(description="Test custom indicators via ZMQ")
    parser.add_argument("--symbol", default="XAUUSD", help="Symbol to test (default: XAUUSD)")
    parser.add_argument("--timeframe", default="H1", help="Timeframe (default: H1)")
    parser.add_argument("--port", type=int, default=5555, help="ZMQ REP port (default: 5555)")
    parser.add_argument("--count", type=int, default=5, help="Bars to read per indicator (default: 5)")
    parser.add_argument("--only", help="Test only this indicator (e.g., SMC_Structure)")
    args = parser.parse_args()

    address = f"tcp://127.0.0.1:{args.port}"

    print()
    print("=" * 70)
    print("  CUSTOM INDICATOR TEST SUITE")
    print(f"  Target: {address}")
    print(f"  Symbol: {args.symbol}  Timeframe: {args.timeframe}  Bars: {args.count}")
    print("=" * 70)

    # Connect to ZMQ
    ctx = zmq.Context()
    socket = ctx.socket(zmq.REQ)
    socket.setsockopt(zmq.RCVTIMEO, ZMQ_TIMEOUT_MS)
    socket.setsockopt(zmq.SNDTIMEO, ZMQ_TIMEOUT_MS)
    socket.setsockopt(zmq.LINGER, 0)

    try:
        socket.connect(address)
    except Exception as e:
        print(f"\nFailed to connect to {address}: {e}")
        print("Make sure MT5 is running with TradeAgent EA attached.")
        sys.exit(1)

    # Store socket info for reconnection on timeout
    _socket_info["socket"] = socket
    _socket_info["ctx"] = ctx
    _socket_info["address"] = address

    def get_socket():
        """Get current socket (may have been reconnected after timeout)."""
        return _socket_info["socket"]

    # 1. Ping
    try:
        if not test_ping(get_socket()):
            print("\nEA not responding. Is TradeAgent EA running on a chart?")
            sys.exit(1)
    except zmq.error.Again:
        print(f"\nTimeout connecting to {address}")
        print("Make sure MT5 is running with TradeAgent EA attached.")
        sys.exit(1)

    # 2. Verify symbol
    if not test_tick(get_socket(), args.symbol):
        print(f"\nCannot get tick for {args.symbol}. Is it in Market Watch?")
        sys.exit(1)

    # 3. Test each custom indicator
    results = []
    indicators = INDICATORS
    if args.only:
        indicators = [i for i in INDICATORS if i["name"].lower() == args.only.lower()]
        if not indicators:
            print(f"\nIndicator '{args.only}' not found. Available:")
            for ind in INDICATORS:
                print(f"  - {ind['name']}")
            sys.exit(1)

    for ind in indicators:
        if ind.get("probe"):
            # Unknown buffer structure — probe first
            print(f"\n{'=' * 70}")
            print(f"  {ind['display']}")
            print(f"  Path: {ind['params']['path']}")
            print(f"  Buffer structure: UNKNOWN — probing...")
            print(f"{'=' * 70}")

            buf_count = probe_buffers(
                get_socket(), args.symbol, args.timeframe,
                ind["name"], ind["params"]["path"],
            )

            if buf_count > 0:
                # Re-test with discovered buffers
                probe_params = dict(ind["params"])
                probe_params["buffer_names"] = [f"buf{i}" for i in range(buf_count)]
                probe_params["buffers"] = buf_count
                result = test_indicator(
                    get_socket(), args.symbol, args.timeframe,
                    ind["name"], ind["display"],
                    probe_params, args.count,
                )
                results.append(result)
            else:
                results.append({
                    "name": ind["name"],
                    "display": ind["display"],
                    "success": False,
                    "error": "Buffer probe found 0 active buffers",
                    "buffers_with_data": 0,
                    "buffers_total": 0,
                    "bars_returned": 0,
                })
        else:
            result = test_indicator(
                get_socket(), args.symbol, args.timeframe,
                ind["name"], ind["display"],
                ind["params"], args.count,
            )
            results.append(result)

    # 4. Summary
    print(f"\n\n{'=' * 70}")
    print("  SUMMARY")
    print(f"{'=' * 70}")
    print(f"\n  {'Indicator':<35} {'Status':<12} {'Buffers':<15} {'Bars'}")
    print(f"  {'-' * 35} {'-' * 12} {'-' * 15} {'-' * 5}")

    passed = 0
    failed = 0
    for r in results:
        if r["success"] and r["buffers_with_data"] > 0:
            status = "PASS"
            passed += 1
        elif r["success"] and r["buffers_with_data"] == 0:
            status = "NO DATA"
            failed += 1
        else:
            status = "FAIL"
            failed += 1

        buf_info = f"{r['buffers_with_data']}/{r['buffers_total']}" if r["success"] else "N/A"
        bars_info = str(r["bars_returned"]) if r["success"] else "N/A"
        print(f"  {r['display']:<35} {status:<12} {buf_info:<15} {bars_info}")

        if r.get("error"):
            print(f"    Error: {r['error']}")

    print(f"\n  Total: {passed} passed, {failed} failed out of {len(results)}")
    print()

    # Cleanup
    get_socket().close()
    ctx.term()

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
