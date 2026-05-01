"""Pull one full ``image`` content block to see its source structure."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from claudecode_backup.paths import (  # noqa: E402
    default_projects_dir,
    iter_project_dirs,
    iter_session_files,
    read_jsonl,
)


def main() -> int:
    for proj in iter_project_dirs(default_projects_dir()):
        for s in iter_session_files(proj):
            for event in read_jsonl(s):
                msg = event.get("message") or {}
                content = msg.get("content")
                if not isinstance(content, list):
                    continue
                for b in content:
                    if isinstance(b, dict) and b.get("type") == "image":
                        # Strip any base64 payload to keep output readable.
                        src = b.get("source")
                        printable = {"type": "image"}
                        if isinstance(src, dict):
                            redacted = {}
                            for k, v in src.items():
                                if isinstance(v, str) and len(v) > 60:
                                    redacted[k] = v[:60] + f"...({len(v)} chars)"
                                else:
                                    redacted[k] = v
                            printable["source"] = redacted
                        else:
                            printable["source"] = repr(src)[:200]
                        print(json.dumps(printable, ensure_ascii=False, indent=2))
                        print(f"  (from {s.name})")
                        return 0
    print("(no image block found)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
