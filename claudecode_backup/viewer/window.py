"""Run the viewer as a desktop app — Flask in the main thread, browser in
``--app`` mode, lifecycle driven by a heartbeat from the page.

Why heartbeat instead of ``proc.wait()``? Chromium-based browsers in
``--app`` mode usually fork a child and the parent process exits within
~100 ms, so ``proc.wait()`` returns immediately even though the window
is alive. Instead we let the page itself tell us when it's gone:

- The frontend POSTs ``/api/heartbeat`` every 3 seconds.
- On ``pagehide`` (close, navigate away) it fires ``/api/shutdown``
  via ``navigator.sendBeacon``.
- A watchdog thread here calls ``os._exit`` once we've seen at least
  one heartbeat AND the gap since the last one exceeded the timeout.
"""
from __future__ import annotations

import logging
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser
from contextlib import closing
from pathlib import Path

from .server import HeartbeatTracker, create_app


HEARTBEAT_TIMEOUT = 8.0      # idle gap before we assume the window is gone
INITIAL_GRACE = 30.0         # don't shut down until first heartbeat (or grace expires)


def _find_free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_http(host: str, port: int, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with closing(socket.create_connection((host, port), timeout=0.2)):
                return
        except OSError:
            time.sleep(0.05)
    raise RuntimeError(f"Flask 启动超时: {host}:{port}")


def _find_browser() -> tuple[str, str] | None:
    candidates: list[tuple[str, str]] = []
    if sys.platform == "win32":
        roots = [
            os.environ.get("ProgramFiles", r"C:\Program Files"),
            os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
            os.environ.get("LOCALAPPDATA", ""),
        ]
        rel = [
            ("Edge", r"Microsoft\Edge\Application\msedge.exe"),
            ("Chrome", r"Google\Chrome\Application\chrome.exe"),
        ]
        for name, suffix in rel:
            for base in roots:
                if not base:
                    continue
                p = Path(base) / suffix
                if p.exists():
                    candidates.append((name, str(p)))
    elif sys.platform == "darwin":
        candidates = [
            ("Chrome", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            ("Edge", "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
        ]
    else:
        for exe in ("google-chrome", "chromium", "microsoft-edge", "chromium-browser"):
            found = shutil.which(exe)
            if found:
                candidates.append((exe, found))
    for name, path in candidates:
        if Path(path).exists():
            return name, path
    return None


def _launch_browser(url: str, width: int, height: int) -> tuple[Path | None, str]:
    """Launch Edge/Chrome in ``--app`` mode. Returns ``(user_data_dir, name)``.

    Falls back to the system default browser if no Chromium build is found.
    """
    found = _find_browser()
    if found is None:
        webbrowser.open(url)
        return None, "default browser"

    name, exe = found
    user_data = Path(tempfile.mkdtemp(prefix="claudecode-backup-app-"))
    args = [
        exe,
        f"--app={url}",
        f"--user-data-dir={user_data}",
        f"--window-size={width},{height}",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    # Detach: we don't care when the browser process exits, only when the
    # heartbeat dies. close_fds keeps us from holding pipe handles open.
    creationflags = 0
    if sys.platform == "win32":
        creationflags = (
            subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
            | subprocess.DETACHED_PROCESS  # type: ignore[attr-defined]
        )
    subprocess.Popen(
        args,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        creationflags=creationflags,
    )
    return user_data, name


def _watchdog(tracker: HeartbeatTracker, cleanup_dir: Path | None) -> None:
    started_at = time.monotonic()
    while True:
        time.sleep(0.5)
        if not tracker.started():
            # Still waiting for the first beat; if the user never opens the
            # window, we'll bail out after the grace period.
            if time.monotonic() - started_at > INITIAL_GRACE:
                print("[claudecode-backup] 窗口未连接，退出。", file=sys.stderr)
                _shutdown(cleanup_dir, code=1)
                return
            continue
        if tracker.expired(HEARTBEAT_TIMEOUT):
            _shutdown(cleanup_dir, code=0)
            return


def _shutdown(cleanup_dir: Path | None, code: int) -> None:
    if cleanup_dir is not None:
        shutil.rmtree(cleanup_dir, ignore_errors=True)
    # ``os._exit`` because Flask's dev-server doesn't have a clean shutdown
    # hook outside a request context, and we just want the process gone.
    os._exit(code)


def run_window(
    projects_dir: Path,
    only_project: str | None,
    width: int = 1280,
    height: int = 820,
) -> int:
    tracker = HeartbeatTracker()
    flask_app = create_app(projects_dir, only_project=only_project, heartbeat=tracker)
    port = _find_free_port()
    url = f"http://127.0.0.1:{port}/"

    # Silence Werkzeug's request log noise — the browser pings every 3s.
    logging.getLogger("werkzeug").setLevel(logging.ERROR)

    # Bring the browser up after Flask is bound; do this on a short delay
    # so the watchdog can start before any requests come in.
    def _delayed_launch() -> None:
        try:
            _wait_for_http("127.0.0.1", port)
        except RuntimeError as exc:
            print(f"[claudecode-backup] {exc}", file=sys.stderr)
            os._exit(1)
        ud, name = _launch_browser(url, width, height)
        print(f"[claudecode-backup] 启动窗口 ({name}) → {url}")
        threading.Thread(
            target=_watchdog, args=(tracker, ud), daemon=True
        ).start()

    threading.Thread(target=_delayed_launch, daemon=True).start()

    # Flask in the foreground — its run loop is the program's lifecycle.
    try:
        flask_app.run(
            host="127.0.0.1", port=port, debug=False, use_reloader=False
        )
    except KeyboardInterrupt:
        pass
    return 0
