"""Parse a Claude Code session jsonl into structured messages.

Used by both the Markdown/HTML renderers and the viewer's HTTP API. A
"message" here is one user or assistant turn whose content has been
flattened from Claude Code's nested block format into a list of blocks
the UI can render directly.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from .paths import read_jsonl


@dataclass
class Block:
    """One renderable unit inside a turn."""

    type: str  # "text" | "tool_use" | "tool_result" | "thinking" | "image" | "raw"
    text: str = ""
    name: str | None = None  # for tool_use
    input: Any = None  # for tool_use
    tool_use_id: str | None = None  # for tool_result
    is_error: bool = False  # for tool_result
    media_type: str | None = None  # for image: e.g. "image/png"
    data: str | None = None  # for image: base64 payload (or url for source.type="url")


@dataclass
class Message:
    uuid: str
    role: str  # "user" | "assistant"
    timestamp: str
    blocks: list[Block] = field(default_factory=list)


@dataclass
class Session:
    session_id: str
    cwd: str | None
    messages: list[Message]


def _result_to_text(content: Any) -> str:
    """Flatten the polymorphic ``tool_result.content`` into displayable text."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out: list[str] = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    out.append(block.get("text", ""))
                else:
                    out.append(json.dumps(block, ensure_ascii=False))
            else:
                out.append(str(block))
        return "\n".join(out)
    return json.dumps(content, ensure_ascii=False)


def _content_to_blocks(content: Any) -> list[Block]:
    if content is None:
        return []
    if isinstance(content, str):
        return [Block(type="text", text=content)]
    if not isinstance(content, list):
        return [Block(type="raw", text=json.dumps(content, ensure_ascii=False))]

    blocks: list[Block] = []
    for raw in content:
        if not isinstance(raw, dict):
            blocks.append(Block(type="raw", text=str(raw)))
            continue
        btype = raw.get("type")
        if btype == "text":
            blocks.append(Block(type="text", text=raw.get("text", "")))
        elif btype == "tool_use":
            blocks.append(
                Block(
                    type="tool_use",
                    name=raw.get("name", "tool"),
                    input=raw.get("input"),
                    tool_use_id=raw.get("id"),
                )
            )
        elif btype == "tool_result":
            blocks.append(
                Block(
                    type="tool_result",
                    text=_result_to_text(raw.get("content")),
                    tool_use_id=raw.get("tool_use_id"),
                    is_error=bool(raw.get("is_error")),
                )
            )
        elif btype == "thinking":
            blocks.append(
                Block(type="thinking", text=raw.get("thinking", ""))
            )
        elif btype == "image":
            src = raw.get("source") or {}
            if isinstance(src, dict):
                stype = src.get("type")
                if stype == "base64":
                    blocks.append(
                        Block(
                            type="image",
                            media_type=src.get("media_type") or "image/png",
                            data=src.get("data") or "",
                        )
                    )
                elif stype == "url":
                    blocks.append(
                        Block(
                            type="image",
                            media_type=src.get("media_type"),
                            # Use ``data`` to carry the URL; the frontend
                            # decides between base64 and url by ``media_type``
                            # presence + value.
                            data=src.get("url") or "",
                            text="url",
                        )
                    )
                else:
                    blocks.append(
                        Block(type="raw", text=json.dumps(raw, ensure_ascii=False))
                    )
            else:
                blocks.append(
                    Block(type="raw", text=json.dumps(raw, ensure_ascii=False))
                )
        else:
            blocks.append(
                Block(type="raw", text=json.dumps(raw, ensure_ascii=False))
            )
    return blocks


def parse_session(path: Path) -> Session:
    """Parse one ``.jsonl`` file into a :class:`Session`."""
    cwd: str | None = None
    messages: list[Message] = []
    for event in read_jsonl(path):
        if cwd is None and isinstance(event.get("cwd"), str):
            cwd = event["cwd"]
        if event.get("type") not in {"user", "assistant"}:
            continue
        msg = event.get("message") or {}
        role = msg.get("role") or event["type"]
        blocks = _content_to_blocks(msg.get("content"))
        if not blocks:
            continue
        messages.append(
            Message(
                uuid=event.get("uuid") or "",
                role=role,
                timestamp=event.get("timestamp") or "",
                blocks=blocks,
            )
        )
    return Session(session_id=path.stem, cwd=cwd, messages=messages)


def session_to_dict(session: Session) -> dict:
    """JSON-serializable shape for the viewer's HTTP API."""
    return {
        "session_id": session.session_id,
        "cwd": session.cwd,
        "messages": [
            {
                "uuid": m.uuid,
                "role": m.role,
                "timestamp": m.timestamp,
                "blocks": [
                    {
                        "type": b.type,
                        "text": b.text,
                        "name": b.name,
                        "input": b.input,
                        "tool_use_id": b.tool_use_id,
                        "is_error": b.is_error,
                        "media_type": b.media_type,
                        "data": b.data,
                    }
                    for b in m.blocks
                ],
            }
            for m in session.messages
        ],
    }


def first_user_text(session: Session, max_len: int = 80) -> str:
    """Return a snippet of the first user message — used as a session title."""
    for m in session.messages:
        if m.role != "user":
            continue
        for b in m.blocks:
            if b.type == "text" and b.text.strip():
                snippet = b.text.strip().splitlines()[0]
                return snippet[:max_len] + ("…" if len(snippet) > max_len else "")
    return "(空会话)"


def iter_turns(path: Path) -> Iterator[tuple[str, str, str]]:
    """Backwards-compatible helper: ``(timestamp, role, plain_text)`` per turn.

    Used by the markdown/html renderers so we don't keep two copies of the
    flatten-blocks logic.
    """
    session = parse_session(path)
    for m in session.messages:
        chunks: list[str] = []
        for b in m.blocks:
            if b.type == "text":
                chunks.append(b.text)
            elif b.type == "tool_use":
                try:
                    rendered = json.dumps(b.input, ensure_ascii=False, indent=2)
                except (TypeError, ValueError):
                    rendered = str(b.input)
                chunks.append(f"[tool_use: {b.name}]\n{rendered}")
            elif b.type == "tool_result":
                tag = "[tool_result error]" if b.is_error else "[tool_result]"
                chunks.append(f"{tag}\n{b.text}")
            elif b.type == "thinking":
                chunks.append(f"[thinking]\n{b.text}")
            else:
                chunks.append(b.text)
        text = "\n\n".join(c for c in chunks if c)
        if text.strip():
            yield m.timestamp, m.role, text
