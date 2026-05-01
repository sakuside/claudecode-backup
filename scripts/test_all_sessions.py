"""End-to-end sanity check for every project / session in ~/.claude/projects/.

For each session we exercise the same code path the Qt scheme handler uses:
  parse_session(path) → session_to_dict(...) → json.dumps(..., ensure_ascii=False)

Any exception, oversized payload, or unknown event type gets reported. We
also surface block-type stats so we can spot anything the renderer doesn't
yet handle (e.g. image, document, attachment).

Usage::

    python scripts/test_all_sessions.py                      # all projects
    python scripts/test_all_sessions.py --project G--birthday
    python scripts/test_all_sessions.py --limit 1            # smallest only
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from collections import Counter
from pathlib import Path

# Make the package importable when run from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from claudecode_backup.paths import (  # noqa: E402
    default_projects_dir,
    iter_project_dirs,
    iter_session_files,
    read_jsonl,
)
from claudecode_backup.session import parse_session, session_to_dict  # noqa: E402


def collect_event_types(path: Path) -> Counter:
    """Top-level ``type`` values present in a jsonl, for diagnostics."""
    c: Counter = Counter()
    for event in read_jsonl(path):
        c[event.get("type", "<missing>")] += 1
    return c


def collect_block_types(parsed) -> Counter:
    c: Counter = Counter()
    for m in parsed.messages:
        for b in m.blocks:
            c[b.type] += 1
    return c


def test_session(path: Path) -> dict:
    """Return a result dict; ``status`` is 'ok' / 'parse_fail' / 'serialize_fail'."""
    info = {
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "status": "ok",
        "messages": 0,
        "block_types": {},
        "event_types": {},
        "json_size": 0,
        "elapsed_ms": 0.0,
        "error": None,
    }
    t0 = time.perf_counter()
    try:
        parsed = parse_session(path)
    except Exception as exc:  # noqa: BLE001
        info["status"] = "parse_fail"
        info["error"] = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
        info["elapsed_ms"] = (time.perf_counter() - t0) * 1000
        return info
    info["messages"] = len(parsed.messages)
    info["block_types"] = dict(collect_block_types(parsed))
    info["event_types"] = dict(collect_event_types(path))
    try:
        encoded = json.dumps(session_to_dict(parsed), ensure_ascii=False).encode("utf-8")
    except Exception as exc:  # noqa: BLE001
        info["status"] = "serialize_fail"
        info["error"] = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
        info["elapsed_ms"] = (time.perf_counter() - t0) * 1000
        return info
    info["json_size"] = len(encoded)
    info["elapsed_ms"] = (time.perf_counter() - t0) * 1000
    return info


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--projects-dir", default=str(default_projects_dir()))
    p.add_argument("--project", help="Restrict to one encoded project name")
    p.add_argument("--limit", type=int, help="Cap number of sessions tested")
    p.add_argument("--smallest-first", action="store_true", default=False)
    args = p.parse_args()

    projects_dir = Path(args.projects_dir)
    sessions: list[Path] = []
    for proj in iter_project_dirs(projects_dir):
        if args.project and proj.name != args.project:
            continue
        for s in iter_session_files(proj):
            sessions.append(s)
    if args.smallest_first:
        sessions.sort(key=lambda x: x.stat().st_size)
    if args.limit is not None:
        sessions = sessions[: args.limit]

    if not sessions:
        print("(no sessions matched)")
        return 0

    print(f"Testing {len(sessions)} session(s)")
    print(f"{'STATUS':14}{'MSG':>5} {'SIZE':>10} {'JSON':>10} {'MS':>7}  PATH")
    print("-" * 100)

    fails: list[dict] = []
    aggregate_blocks: Counter = Counter()
    aggregate_events: Counter = Counter()
    total_json = 0
    total_msgs = 0
    biggest_json = 0

    for path in sessions:
        info = test_session(path)
        rel = path.relative_to(projects_dir)
        size_kb = info["size_bytes"] / 1024
        json_kb = info["json_size"] / 1024
        marker = "OK" if info["status"] == "ok" else f"FAIL: {info['status']}"
        print(
            f"{marker:14}{info['messages']:>5} "
            f"{size_kb:>9.1f}K {json_kb:>9.1f}K {info['elapsed_ms']:>6.1f}  {rel}"
        )
        if info["status"] != "ok":
            fails.append(info)
        else:
            for k, v in info["block_types"].items():
                aggregate_blocks[k] += v
            for k, v in info["event_types"].items():
                aggregate_events[k] += v
            total_json += info["json_size"]
            total_msgs += info["messages"]
            biggest_json = max(biggest_json, info["json_size"])

    print("-" * 100)
    print(
        f"OK: {len(sessions) - len(fails)}/{len(sessions)}, "
        f"FAIL: {len(fails)}, "
        f"messages: {total_msgs}, JSON total: {total_json/1024/1024:.1f} MB, "
        f"biggest: {biggest_json/1024/1024:.2f} MB"
    )
    print(f"block types : {dict(aggregate_blocks)}")
    print(f"event types : {dict(aggregate_events)}")

    for f in fails:
        print(f"\n=== FAIL: {f['path']} ===")
        print(f["error"])

    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
