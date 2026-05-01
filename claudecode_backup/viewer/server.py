"""Flask app exposing projects + sessions for the browser-based viewer."""
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, abort, jsonify, render_template, request

from ..paths import (
    iter_project_dirs,
    iter_session_files,
    project_cwd,
)
from ..session import first_user_text, parse_session, session_to_dict


class HeartbeatTracker:
    """Thread-safe last-seen timestamp + idle-timeout watchdog.

    Used by ``app`` mode to know when the user closed the window: the page
    sends ``POST /api/heartbeat`` every few seconds, and a watchdog thread
    triggers shutdown when the gap exceeds ``timeout``.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last: float | None = None
        self._closed = False

    def beat(self) -> None:
        with self._lock:
            self._last = time.monotonic()

    def explicit_close(self) -> None:
        with self._lock:
            self._closed = True

    def expired(self, timeout: float) -> bool:
        with self._lock:
            if self._closed:
                return True
            if self._last is None:
                return False
            return time.monotonic() - self._last > timeout

    def started(self) -> bool:
        with self._lock:
            return self._last is not None


def create_app(
    projects_dir: Path,
    only_project: str | None = None,
    heartbeat: HeartbeatTracker | None = None,
) -> Flask:
    """Build a Flask app rooted at ``projects_dir``.

    ``only_project`` (an encoded directory name) restricts the sidebar to a
    single project — useful for the "先拿一个项目做测试" entry point.
    ``heartbeat`` enables the ``/api/heartbeat`` + ``/api/shutdown`` endpoints
    used by ``app`` (window) mode.
    """
    app = Flask(
        __name__,
        template_folder=str(Path(__file__).parent / "templates"),
        static_folder=str(Path(__file__).parent / "static"),
    )
    app.config["projects_dir"] = projects_dir.resolve()
    app.config["only_project"] = only_project
    app.config["heartbeat_enabled"] = heartbeat is not None

    def _allowed(name: str) -> bool:
        if only_project is None:
            return True
        return name == only_project

    def _project_path(name: str) -> Path:
        if not _allowed(name):
            abort(404)
        target = (app.config["projects_dir"] / name).resolve()
        # Refuse anything that escapes the projects root.
        try:
            target.relative_to(app.config["projects_dir"])
        except ValueError:
            abort(400)
        if not target.is_dir():
            abort(404)
        return target

    @app.get("/")
    def index() -> str:
        return render_template("index.html")

    @app.get("/api/projects")
    def list_projects():
        out = []
        for p in iter_project_dirs(app.config["projects_dir"]):
            if not _allowed(p.name):
                continue
            sessions = list(iter_session_files(p))
            if not sessions:
                continue
            out.append(
                {
                    "name": p.name,
                    "cwd": project_cwd(p),
                    "session_count": len(sessions),
                }
            )
        out.sort(key=lambda x: x["name"].lower())
        return jsonify(out)

    @app.get("/api/projects/<name>/sessions")
    def list_sessions(name: str):
        proj_dir = _project_path(name)
        out = []
        for s in iter_session_files(proj_dir):
            session = parse_session(s)
            mtime = datetime.fromtimestamp(
                s.stat().st_mtime, tz=timezone.utc
            ).astimezone()
            out.append(
                {
                    "session_id": session.session_id,
                    "title": first_user_text(session),
                    "message_count": len(session.messages),
                    "last_modified": mtime.isoformat(),
                    "first_timestamp": (
                        session.messages[0].timestamp if session.messages else ""
                    ),
                }
            )
        out.sort(key=lambda x: x["last_modified"], reverse=True)
        return jsonify(out)

    @app.get("/api/projects/<name>/sessions/<sid>")
    def get_session(name: str, sid: str):
        proj_dir = _project_path(name)
        # `sid` is untrusted — only allow looking up a direct child file.
        candidate = proj_dir / f"{sid}.jsonl"
        try:
            candidate.resolve().relative_to(proj_dir.resolve())
        except ValueError:
            abort(400)
        if not candidate.is_file():
            abort(404)
        return jsonify(session_to_dict(parse_session(candidate)))

    @app.get("/api/config")
    def api_config():
        # Lets the frontend decide whether to enable heartbeat polling.
        return jsonify({"heartbeat": app.config["heartbeat_enabled"]})

    if heartbeat is not None:
        @app.post("/api/heartbeat")
        def api_heartbeat():
            heartbeat.beat()
            return ("", 204)

        @app.post("/api/shutdown")
        def api_shutdown():
            heartbeat.explicit_close()
            return ("", 204)

    return app


def serve(
    projects_dir: Path,
    host: str,
    port: int,
    only_project: str | None,
    open_browser: bool,
) -> None:
    app = create_app(projects_dir, only_project=only_project)
    url = f"http://{host}:{port}/"
    print(f"\n  claudecode-backup viewer\n  → {url}\n  (Ctrl+C 退出)\n")
    if open_browser:
        import threading
        import webbrowser

        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    # Disable the noisy default reloader when serving locally.
    app.run(host=host, port=port, debug=False, use_reloader=False)
