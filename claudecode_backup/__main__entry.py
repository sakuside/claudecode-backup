"""Entry point for the packaged ``claudecode-backup-viewer.exe``.

PyInstaller bundles this single script. It launches the desktop viewer
directly without going through the typer CLI — avoids dragging argparse
output onto end users.
"""
from __future__ import annotations

import sys
from pathlib import Path

from claudecode_backup import config as user_config
from claudecode_backup.paths import default_projects_dir
from claudecode_backup.viewer.qt_window import run_window


def main() -> int:
    persisted = user_config.get_projects_dir()
    projects_dir: Path = persisted or default_projects_dir()
    # If neither default nor persisted exists, still launch — the user can
    # pick a folder via the "更换" link in the UI.
    return run_window(projects_dir=projects_dir, only_project=None)


if __name__ == "__main__":
    sys.exit(main())
