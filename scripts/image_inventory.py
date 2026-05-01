"""Per-session count of image blocks, sorted by count descending."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from claudecode_backup.paths import (  # noqa: E402
    default_projects_dir,
    iter_project_dirs,
    iter_session_files,
)
from claudecode_backup.session import parse_session  # noqa: E402


def main() -> int:
    rows = []
    for proj in iter_project_dirs(default_projects_dir()):
        for s in iter_session_files(proj):
            session = parse_session(s)
            count = sum(1 for m in session.messages for b in m.blocks if b.type == "image")
            if count == 0:
                continue
            # Find message indices for the first few image blocks (1-based).
            indices = []
            for i, m in enumerate(session.messages, start=1):
                if any(b.type == "image" for b in m.blocks):
                    indices.append(i)
                    if len(indices) >= 5:
                        break
            rows.append((count, proj.name, session.cwd or "?", s.stem, indices, len(session.messages)))
    rows.sort(reverse=True)
    print(f"{'IMG':>4}  {'TOTAL_MSG':>9}  {'CWD':<55}  FIRST_IMG_AT_MSG  SESSION_ID")
    print("-" * 130)
    for count, name, cwd, sid, indices, total in rows:
        cwd_short = cwd if len(cwd) <= 53 else cwd[:50] + "..."
        idx_str = ", ".join(f"#{i}" for i in indices) + ("..." if len(indices) >= 5 else "")
        print(f"{count:>4}  {total:>9}  {cwd_short:<55}  {idx_str:<24}  {sid}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
