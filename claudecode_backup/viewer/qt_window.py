"""Native desktop window using PySide6 + QWebEngineView.

No HTTP server, no port. A custom ``app://`` URL scheme is registered with
Qt's WebEngine; ``fetch()`` calls from the page are intercepted and served
directly by Python file I/O. The viewer is read-only — the handler only
exposes ``GET``-style routes.

Lifecycle is the natural Qt one: close the window → ``QApplication`` exits
cleanly → process ends. No heartbeat hack required.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QUrl
from PySide6.QtWebEngineCore import (
    QWebEnginePage,
    QWebEngineProfile,
    QWebEngineUrlRequestJob,
    QWebEngineUrlScheme,
    QWebEngineUrlSchemeHandler,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QFileDialog, QMainWindow

from .. import config
from ..paths import iter_project_dirs, iter_session_files, project_cwd
from ..session import first_user_text, parse_session, session_to_dict


SCHEME_NAME = b"app"
SCHEME_HOST = "local"  # all URLs look like app://local/...
VIEWER_DIR = Path(__file__).parent
TEMPLATES_DIR = VIEWER_DIR / "templates"
STATIC_DIR = VIEWER_DIR / "static"

_MIME = {
    ".html": b"text/html; charset=utf-8",
    ".css": b"text/css; charset=utf-8",
    ".js": b"application/javascript; charset=utf-8",
    ".json": b"application/json; charset=utf-8",
    ".svg": b"image/svg+xml",
    ".png": b"image/png",
    ".ico": b"image/x-icon",
    ".woff2": b"font/woff2",
}


def _mime_for(path: Path) -> bytes:
    return _MIME.get(path.suffix.lower(), b"application/octet-stream")


def register_scheme() -> None:
    """Must be called before ``QApplication`` is created."""
    scheme = QWebEngineUrlScheme(SCHEME_NAME)
    scheme.setSyntax(QWebEngineUrlScheme.Syntax.Host)
    # Treat ``app://`` like a normal HTTP-style scheme. ``LocalScheme`` would
    # block any cross-origin fetch (including loading vendored JS via the
    # same scheme in some Qt builds), so stick with Secure + Cors.
    # Treat ``app://`` like a normal HTTP-style scheme. ``LocalScheme`` would
    # block cross-origin behaviour; ``FetchApiAllowed`` is the magic flag
    # that lets ``fetch()`` see this scheme at all.
    scheme.setFlags(
        QWebEngineUrlScheme.Flag.SecureScheme
        | QWebEngineUrlScheme.Flag.CorsEnabled
        | QWebEngineUrlScheme.Flag.FetchApiAllowed
    )
    QWebEngineUrlScheme.registerScheme(scheme)


class AppSchemeHandler(QWebEngineUrlSchemeHandler):
    """Handle every ``app://local/...`` request the page makes."""

    def __init__(self, projects_dir: Path, only_project: str | None) -> None:
        super().__init__()
        self.projects_dir = projects_dir.resolve()
        self.only_project = only_project

    # ------------------------------------------------------------------ Qt hook
    def requestStarted(self, job: QWebEngineUrlRequestJob) -> None:
        url = job.requestUrl()
        path = url.path() or "/"
        method = bytes(job.requestMethod()).decode("ascii", "replace").upper()
        try:
            data, mime = self._dispatch(path, method)
        except FileNotFoundError as exc:
            print(f"[scheme] 404 {url.toString()}  ({exc})", file=sys.stderr)
            job.fail(QWebEngineUrlRequestJob.Error.UrlNotFound)
            return
        except PermissionError as exc:
            print(f"[scheme] 403 {url.toString()}  ({exc})", file=sys.stderr)
            job.fail(QWebEngineUrlRequestJob.Error.RequestDenied)
            return
        except Exception as exc:  # noqa: BLE001
            import traceback
            print(f"[scheme] 500 {url.toString()}  ({exc!r})", file=sys.stderr)
            traceback.print_exc()
            job.fail(QWebEngineUrlRequestJob.Error.RequestFailed)
            return

        print(
            f"[scheme] 200 {url.toString()}  ({len(data)} bytes, {mime.decode()})",
            file=sys.stderr,
        )
        # ``QBuffer`` parented to the job stays alive until the job is finished.
        buf = QBuffer(parent=job)
        buf.setData(QByteArray(data))
        buf.open(QIODevice.OpenModeFlag.ReadOnly)
        job.reply(QByteArray(mime), buf)

    # ------------------------------------------------------------------ routes
    def _dispatch(self, path: str, method: str = "GET") -> tuple[bytes, bytes]:
        if path in ("/", "/index.html"):
            return self._read(TEMPLATES_DIR / "index.html"), _MIME[".html"]

        if path.startswith("/static/"):
            rel = path[len("/static/") :]
            target = (STATIC_DIR / rel).resolve()
            # Refuse anything that escapes the static dir.
            try:
                target.relative_to(STATIC_DIR.resolve())
            except ValueError:
                raise PermissionError(path)
            return self._read(target), _mime_for(target)

        if path == "/api/config":
            return self._json({"heartbeat": False}), _MIME[".json"]

        if path == "/api/projects-dir":
            if method == "POST":
                picked = self._pick_projects_dir()
                return self._json({"path": picked}), _MIME[".json"]
            return self._json({"path": str(self.projects_dir)}), _MIME[".json"]

        if path == "/api/projects":
            return self._json(self._list_projects()), _MIME[".json"]

        # /api/projects/<name>/sessions
        if path.startswith("/api/projects/") and path.endswith("/sessions"):
            name = path[len("/api/projects/") : -len("/sessions")]
            return self._json(self._list_sessions(name)), _MIME[".json"]

        # /api/projects/<name>/sessions/<sid>
        if path.startswith("/api/projects/") and "/sessions/" in path:
            head, sid = path.rsplit("/sessions/", 1)
            name = head[len("/api/projects/") :]
            return self._json(self._get_session(name, sid)), _MIME[".json"]

        raise FileNotFoundError(path)

    # ----------------------------------------------------------------- helpers
    @staticmethod
    def _read(path: Path) -> bytes:
        return path.read_bytes()

    @staticmethod
    def _json(payload) -> bytes:
        return json.dumps(payload, ensure_ascii=False).encode("utf-8")

    def _allowed(self, name: str) -> bool:
        return self.only_project is None or name == self.only_project

    def _project_dir(self, name: str) -> Path:
        if not self._allowed(name):
            raise FileNotFoundError(name)
        target = (self.projects_dir / name).resolve()
        try:
            target.relative_to(self.projects_dir)
        except ValueError:
            raise PermissionError(name)
        if not target.is_dir():
            raise FileNotFoundError(name)
        return target

    def _pick_projects_dir(self) -> str | None:
        """Open a native folder picker; on accept, switch + persist. None on cancel."""
        chosen = QFileDialog.getExistingDirectory(
            None,
            "选择 Claude Code 的 projects 目录",
            str(self.projects_dir),
        )
        if not chosen:
            return None
        new_path = Path(chosen).resolve()
        if not new_path.is_dir():
            return None
        self.projects_dir = new_path
        config.set_projects_dir(new_path)
        return str(new_path)

    def _list_projects(self) -> list[dict]:
        out = []
        for p in iter_project_dirs(self.projects_dir):
            if not self._allowed(p.name):
                continue
            sessions = list(iter_session_files(p))
            if not sessions:
                continue
            out.append({
                "name": p.name,
                "cwd": project_cwd(p),
                "session_count": len(sessions),
            })
        out.sort(key=lambda x: x["name"].lower())
        return out

    def _list_sessions(self, name: str) -> list[dict]:
        proj = self._project_dir(name)
        out = []
        for s in iter_session_files(proj):
            session = parse_session(s)
            mtime = datetime.fromtimestamp(
                s.stat().st_mtime, tz=timezone.utc
            ).astimezone()
            out.append({
                "session_id": session.session_id,
                "title": first_user_text(session),
                "message_count": len(session.messages),
                "last_modified": mtime.isoformat(),
                "first_timestamp": (
                    session.messages[0].timestamp if session.messages else ""
                ),
            })
        out.sort(key=lambda x: x["last_modified"], reverse=True)
        return out

    def _get_session(self, name: str, sid: str) -> dict:
        proj = self._project_dir(name)
        candidate = (proj / f"{sid}.jsonl").resolve()
        try:
            candidate.relative_to(proj)
        except ValueError:
            raise PermissionError(sid)
        if not candidate.is_file():
            raise FileNotFoundError(sid)
        return session_to_dict(parse_session(candidate))


class _LoggingPage(QWebEnginePage):
    """Surface JS console messages and load errors to the terminal."""

    def javaScriptConsoleMessage(self, level, message, line, source_id):  # noqa: D401
        try:
            tag = level.name  # PySide6 enum
        except AttributeError:
            tag = str(level)
        print(f"[js {tag}] {source_id}:{line}  {message}", file=sys.stderr)


def run_window(
    projects_dir: Path,
    only_project: str | None,
    width: int = 1280,
    height: int = 820,
) -> int:
    # Enable remote DevTools (open http://127.0.0.1:9222 in another browser).
    import os
    os.environ.setdefault("QTWEBENGINE_REMOTE_DEBUGGING", "9222")

    register_scheme()
    qt_app = QApplication(sys.argv[:1])
    qt_app.setApplicationName("claudecode-backup viewer")

    handler = AppSchemeHandler(projects_dir, only_project)
    profile = QWebEngineProfile.defaultProfile()
    # Keep a reference on the profile so the handler isn't GC'd.
    profile.installUrlSchemeHandler(SCHEME_NAME, handler)
    profile._cb_handler = handler  # type: ignore[attr-defined]

    view = QWebEngineView()
    page = _LoggingPage(profile, view)
    view.setPage(page)
    view.setUrl(QUrl(f"app://{SCHEME_HOST}/index.html"))

    title = "claudecode-backup viewer"
    if only_project:
        title += f" — {only_project}"
    window = QMainWindow()
    window.setWindowTitle(title)
    window.resize(width, height)
    window.setCentralWidget(view)
    window.show()

    return qt_app.exec()
