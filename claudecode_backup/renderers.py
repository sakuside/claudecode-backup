"""Render Claude Code session jsonl into Markdown / HTML."""
from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path

from .session import iter_turns


def _format_ts(ts: str) -> str:
    if not ts:
        return ""
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    except ValueError:
        return ts


def render_markdown(path: Path) -> str:
    lines: list[str] = [f"# Claude Code 会话: `{path.stem}`", ""]
    for ts, role, text in iter_turns(path):
        emoji = {"user": "🧑", "assistant": "🤖"}.get(role, "•")
        lines.append(f"## {emoji} {role}  ·  {_format_ts(ts)}")
        lines.append("")
        lines.append(text)
        lines.append("")
        lines.append("---")
        lines.append("")
    return "\n".join(lines)


def render_html(path: Path) -> str:
    body: list[str] = []
    for ts, role, text in iter_turns(path):
        body.append(
            f'<section class="msg {html.escape(role)}">'
            f'<header><span class="role">{html.escape(role)}</span>'
            f'<span class="ts">{html.escape(_format_ts(ts))}</span></header>'
            f"<pre>{html.escape(text)}</pre>"
            f"</section>"
        )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>Claude Code 会话 {html.escape(path.stem)}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
    "Microsoft YaHei", sans-serif; max-width: 920px; margin: 2em auto;
    padding: 0 1em; color: #222; }}
  h1 {{ border-bottom: 2px solid #444; padding-bottom: .3em; }}
  section.msg {{ border: 1px solid #ddd; border-radius: 6px; margin: 1em 0;
    overflow: hidden; }}
  section.msg header {{ padding: .5em 1em; display: flex; justify-content:
    space-between; font-size: .9em; }}
  section.msg.user header {{ background: #eef6ff; }}
  section.msg.assistant header {{ background: #f3f0ff; }}
  section.msg .role {{ font-weight: 600; text-transform: uppercase;
    letter-spacing: .05em; }}
  section.msg .ts {{ color: #666; }}
  section.msg pre {{ margin: 0; padding: 1em; white-space: pre-wrap;
    word-wrap: break-word; font-family: ui-monospace, "Cascadia Mono",
    Consolas, monospace; font-size: .92em; line-height: 1.5; }}
</style>
</head>
<body>
<h1>Claude Code 会话: <code>{html.escape(path.stem)}</code></h1>
{''.join(body)}
</body>
</html>
"""
