"""Find what content-block types the parser falls back to ``raw`` on."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from claudecode_backup.paths import (  # noqa: E402
    default_projects_dir,
    iter_project_dirs,
    iter_session_files,
    read_jsonl,
)


def main() -> int:
    types: Counter = Counter()
    samples: dict[str, list] = {}
    for proj in iter_project_dirs(default_projects_dir()):
        for s in iter_session_files(proj):
            for event in read_jsonl(s):
                if event.get("type") not in {"user", "assistant"}:
                    continue
                msg = event.get("message") or {}
                content = msg.get("content")
                if not isinstance(content, list):
                    continue
                for b in content:
                    if not isinstance(b, dict):
                        types["<not-a-dict>"] += 1
                        continue
                    t = b.get("type", "<missing>")
                    if t in {"text", "tool_use", "tool_result", "thinking"}:
                        continue
                    types[t] += 1
                    if len(samples.setdefault(t, [])) < 2:
                        samples[t].append({k: (str(v)[:200] if not isinstance(v, (dict, list)) else "...") for k, v in b.items()})
    print("Unhandled block types:")
    for t, n in types.most_common():
        print(f"  {t!r}: {n}")
    print("\nSamples:")
    for t, items in samples.items():
        print(f"\n  type = {t!r}:")
        for s in items:
            print(f"    {json.dumps(s, ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
