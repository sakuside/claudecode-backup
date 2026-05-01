"""`claudecode-backup import` — restore sessions back into ~/.claude/projects."""
from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Iterable

from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    TextColumn,
    TimeElapsedColumn,
)

from .paths import (
    apply_remaps,
    encode_project_path,
    ensure_dir,
    relativize,
)


def _extract_zip(zip_path: Path, into: Path) -> Path:
    """Extract a zip into ``into`` and return the directory to walk."""
    ensure_dir(into)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(into)
    return into


def _rewrite_jsonl(
    src: Path, dst: Path, remaps: list[tuple[str, str]]
) -> None:
    """Copy ``src`` to ``dst``, rewriting ``cwd`` in each event by ``remaps``."""
    ensure_dir(dst.parent)
    if not remaps:
        shutil.copy2(src, dst)
        return
    with src.open("r", encoding="utf-8", errors="replace") as fin, dst.open(
        "w", encoding="utf-8", newline="\n"
    ) as fout:
        for line in fin:
            stripped = line.strip()
            if not stripped:
                fout.write(line)
                continue
            try:
                obj = json.loads(stripped)
            except json.JSONDecodeError:
                fout.write(line)
                continue
            cwd = obj.get("cwd")
            if isinstance(cwd, str) and cwd:
                obj["cwd"] = apply_remaps(cwd, remaps)
            fout.write(json.dumps(obj, ensure_ascii=False))
            fout.write("\n")


def _rename_project_dir(
    name: str, remaps: Iterable[tuple[str, str]]
) -> str:
    """If a remap matches the project's encoded directory name, rewrite it.

    Each remap is also applied to the *encoded* form of the source path, so
    a user can write ``--remap-path C:\\old=D:\\new`` and have both the
    directory name and every ``cwd`` field updated consistently.
    """
    for old, new in remaps:
        old_enc = encode_project_path(old)
        new_enc = encode_project_path(new)
        if name == old_enc or name.startswith(old_enc):
            return new_enc + name[len(old_enc) :]
    return name


def run(
    source: Path,
    target: Path,
    remap_specs: list[tuple[str, str]],
    console: Console,
) -> None:
    if not source.exists():
        raise FileNotFoundError(f"source not found: {source}")
    ensure_dir(target)

    cleanup: Path | None = None
    if source.is_file() and source.suffix.lower() == ".zip":
        scratch = Path(tempfile.mkdtemp(prefix="claudecode-backup-"))
        cleanup = scratch
        walk_root = _extract_zip(source, scratch)
        console.print(f"[dim]解压 {source.name} → {walk_root}[/]")
    elif source.is_dir():
        walk_root = source
    else:
        raise ValueError(f"source 必须是目录或 .zip 文件: {source}")

    try:
        files = [p for p in walk_root.rglob("*.jsonl") if p.is_file()]
        if not files:
            console.print("[yellow]source 内没有 .jsonl 会话文件[/]")
            return

        with Progress(
            TextColumn("[bold blue]导入会话"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("import", total=len(files))
            for f in files:
                rel = relativize(f, walk_root)
                # Rewrite the (encoded) project directory name on the way in.
                parts = list(rel.parts)
                if len(parts) >= 2:
                    parts[0] = _rename_project_dir(parts[0], remap_specs)
                    rel = Path(*parts)
                _rewrite_jsonl(f, target / rel, remap_specs)
                progress.advance(task)

        console.print(
            f"[bold green]✓[/] 已导入 {len(files)} 个会话 → {target}"
        )
    finally:
        if cleanup is not None:
            shutil.rmtree(cleanup, ignore_errors=True)
