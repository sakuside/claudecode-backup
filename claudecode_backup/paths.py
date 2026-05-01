"""Helpers for locating and parsing Claude Code's project storage."""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator


def default_projects_dir() -> Path:
    """`~/.claude/projects` — the directory Claude Code writes session jsonl into."""
    return Path.home() / ".claude" / "projects"


def encode_project_path(project_path: str) -> str:
    """Replicate Claude Code's directory-name encoding.

    Claude Code replaces every path separator (``:``, ``\\``, ``/``) and any
    leading dot with ``-``. This is lossy — there is no faithful inverse — but
    we never need to decode: the original ``cwd`` is recorded inside each
    jsonl event.
    """
    encoded = re.sub(r"[:\\/]", "-", project_path)
    if encoded.startswith("."):
        encoded = "-" + encoded[1:]
    return encoded


def iter_session_files(project_dir: Path) -> Iterator[Path]:
    """Yield ``*.jsonl`` files directly inside a project directory."""
    if not project_dir.is_dir():
        return
    for child in sorted(project_dir.iterdir()):
        if child.is_file() and child.suffix == ".jsonl":
            yield child


def iter_project_dirs(projects_dir: Path) -> Iterator[Path]:
    """Yield top-level project directories under ``~/.claude/projects``."""
    if not projects_dir.is_dir():
        return
    for child in sorted(projects_dir.iterdir()):
        if child.is_dir():
            yield child


@dataclass
class SessionInfo:
    path: Path
    session_id: str
    cwd: str | None
    last_modified: datetime
    message_count: int


def read_jsonl(path: Path) -> Iterator[dict]:
    """Iterate JSON objects from a jsonl file, skipping malformed lines."""
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def summarize_session(path: Path) -> SessionInfo:
    """Walk a session jsonl once and pull out lightweight metadata."""
    cwd: str | None = None
    count = 0
    for event in read_jsonl(path):
        if event.get("type") in {"user", "assistant"}:
            count += 1
        if cwd is None and isinstance(event.get("cwd"), str):
            cwd = event["cwd"]
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).astimezone()
    return SessionInfo(
        path=path,
        session_id=path.stem,
        cwd=cwd,
        last_modified=mtime,
        message_count=count,
    )


def project_cwd(project_dir: Path) -> str | None:
    """Best-effort lookup of the original ``cwd`` for a project directory."""
    for session in iter_session_files(project_dir):
        for event in read_jsonl(session):
            cwd = event.get("cwd")
            if isinstance(cwd, str) and cwd:
                return cwd
    return None


def safe_filename(name: str) -> str:
    """Strip characters that are illegal in Windows filenames."""
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .") or "untitled"


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def relativize(child: Path, base: Path) -> Path:
    """Like ``Path.relative_to`` but normalizes drive-letter case on Windows."""
    try:
        return child.resolve().relative_to(base.resolve())
    except ValueError:
        # Fallback: walk strings (handles symlinked / case-mismatched paths).
        cs = os.path.normcase(str(child.resolve()))
        bs = os.path.normcase(str(base.resolve()))
        if cs.startswith(bs):
            return Path(str(child.resolve())[len(str(base.resolve())) :].lstrip("/\\"))
        raise


def format_iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def parse_remap(spec: str) -> tuple[str, str]:
    """Parse ``--remap-path old=new``; raises ``ValueError`` if malformed."""
    if "=" not in spec:
        raise ValueError(f"Expected 'old=new', got {spec!r}")
    old, new = spec.split("=", 1)
    old, new = old.strip(), new.strip()
    if not old or not new:
        raise ValueError(f"Both sides must be non-empty: {spec!r}")
    return old, new


def apply_remaps(value: str, remaps: Iterable[tuple[str, str]]) -> str:
    """Apply a sequence of literal old→new substitutions to a string."""
    for old, new in remaps:
        if value == old or value.startswith(old):
            value = new + value[len(old) :]
    return value
