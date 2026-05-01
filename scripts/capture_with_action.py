"""Take a screenshot after running JS in the viewer via Qt DevTools.

The viewer enables a remote DevTools server on port 9222. We connect over
WebSocket, send JS via ``Runtime.evaluate``, then call the existing
``take_screenshots`` helper to capture the result.
"""
from __future__ import annotations

import json
import socket
import sys
import time
from pathlib import Path
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent))
from take_screenshots import capture, find_window  # noqa: E402

try:
    from websocket import create_connection  # type: ignore
except ImportError:
    print("pip install websocket-client", file=sys.stderr)
    sys.exit(2)


def find_target_ws() -> str:
    raw = urlopen("http://127.0.0.1:9222/json").read()
    targets = json.loads(raw)
    for t in targets:
        if t.get("type") == "page":
            return t["webSocketDebuggerUrl"]
    raise RuntimeError("no page target found in DevTools")


def evaluate(ws_url: str, expr: str) -> None:
    ws = create_connection(ws_url, timeout=5)
    try:
        ws.send(json.dumps({
            "id": 1,
            "method": "Runtime.evaluate",
            "params": {"expression": expr, "awaitPromise": True},
        }))
        ws.recv()
    finally:
        ws.close()


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: capture_with_action.py <out.png> <js-expression>", file=sys.stderr)
        return 2
    out = Path(sys.argv[1])
    expr = sys.argv[2]
    ws_url = find_target_ws()
    evaluate(ws_url, expr)
    time.sleep(0.4)
    hwnd = find_window("claudecode-backup viewer")
    if not hwnd:
        print("window not found", file=sys.stderr)
        return 1
    capture(hwnd, out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
