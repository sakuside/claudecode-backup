"""Persistent user-level config for claudecode-backup.

A tiny JSON file under the user's home dir that remembers things across
runs — currently just ``projects_dir`` (so users on a different machine
can pick a non-default ``.claude/projects`` location once and have it
stick).

Resolution order at startup:
  1. Explicit ``--projects-dir`` CLI flag (or ``--project`` lookups, etc.)
  2. ``projects_dir`` from this config file (if present and exists)
  3. The platform default ``~/.claude/projects``
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


def _config_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA")
        if base:
            return Path(base) / "claudecode-backup"
    return Path.home() / ".claudecode-backup"


def config_path() -> Path:
    return _config_dir() / "config.json"


def load() -> dict[str, Any]:
    p = config_path()
    if not p.is_file():
        return {}
    try:
        with p.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save(data: dict[str, Any]) -> None:
    p = config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    tmp.replace(p)


def get_projects_dir() -> Path | None:
    """Return the persisted projects dir, if any and it still exists."""
    data = load()
    raw = data.get("projects_dir")
    if not isinstance(raw, str):
        return None
    p = Path(raw)
    return p if p.is_dir() else None


def set_projects_dir(path: Path) -> None:
    data = load()
    data["projects_dir"] = str(path)
    save(data)
