"""`claudecode-backup export` — pack sessions into a directory or zip."""
from __future__ import annotations

import shutil
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
    encode_project_path,
    ensure_dir,
    iter_project_dirs,
    iter_session_files,
)
from .renderers import render_html, render_markdown


def _resolve_project_dir(projects_dir: Path, project: str) -> Path:
    """Map a user-supplied ``--project`` value to its on-disk directory.

    Accepts: a directory name (``G--backup``), an absolute project path
    (``G:\\backup``), or an existing path on disk.
    """
    candidate = projects_dir / project
    if candidate.is_dir():
        return candidate
    encoded = projects_dir / encode_project_path(project)
    if encoded.is_dir():
        return encoded
    raw = Path(project)
    if raw.is_dir():
        return raw
    raise FileNotFoundError(
        f"找不到项目目录: {project}  (尝试过 {candidate} 和 {encoded})"
    )


def _render_one(src: Path, dst: Path, fmt: str) -> None:
    if fmt == "jsonl":
        ensure_dir(dst.parent)
        shutil.copy2(src, dst)
    elif fmt == "md":
        ensure_dir(dst.parent)
        dst.write_text(render_markdown(src), encoding="utf-8")
    elif fmt == "html":
        ensure_dir(dst.parent)
        dst.write_text(render_html(src), encoding="utf-8")
    else:
        raise ValueError(f"unknown format: {fmt}")


def _output_name(session: Path, fmt: str) -> str:
    return session.stem + {"jsonl": ".jsonl", "md": ".md", "html": ".html"}[fmt]


def _gather(
    projects_dir: Path,
    all_projects: bool,
    project: str | None,
) -> list[tuple[Path, Path]]:
    """Return ``(project_dir, session_file)`` pairs to export."""
    pairs: list[tuple[Path, Path]] = []
    if all_projects:
        for proj_dir in iter_project_dirs(projects_dir):
            for session in iter_session_files(proj_dir):
                pairs.append((proj_dir, session))
    elif project is not None:
        proj_dir = _resolve_project_dir(projects_dir, project)
        for session in iter_session_files(proj_dir):
            pairs.append((proj_dir, session))
    return pairs


def run(
    projects_dir: Path,
    output: Path,
    fmt: str,
    all_projects: bool,
    project: str | None,
    zip_output: bool,
    console: Console,
) -> None:
    if not all_projects and project is None:
        raise ValueError("必须指定 --all 或 --project <路径>")

    pairs = _gather(projects_dir, all_projects, project)
    if not pairs:
        console.print("[yellow]没有可导出的会话[/]")
        return

    # When --all is set we keep ``<project>/<session.ext>`` layout; for a
    # single project we drop the redundant outer dir.
    def rel_for(proj_dir: Path, session: Path) -> Path:
        name = _output_name(session, fmt)
        return Path(proj_dir.name) / name if all_projects else Path(name)

    progress_cols = (
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
    )

    if zip_output:
        ensure_dir(output.parent)
        scratch_root = output.with_suffix(output.suffix + ".tmp")
        if scratch_root.exists():
            shutil.rmtree(scratch_root)
        ensure_dir(scratch_root)
        try:
            with Progress(*progress_cols, console=console) as progress:
                task = progress.add_task("渲染会话", total=len(pairs))
                for proj_dir, session in pairs:
                    rel = rel_for(proj_dir, session)
                    _render_one(session, scratch_root / rel, fmt)
                    progress.advance(task)

            files = [p for p in scratch_root.rglob("*") if p.is_file()]
            with Progress(*progress_cols, console=console) as progress:
                task = progress.add_task("打包 zip", total=len(files))
                with zipfile.ZipFile(
                    output, "w", compression=zipfile.ZIP_DEFLATED
                ) as zf:
                    for f in files:
                        zf.write(f, arcname=f.relative_to(scratch_root))
                        progress.advance(task)
        finally:
            shutil.rmtree(scratch_root, ignore_errors=True)
        console.print(f"[bold green]✓[/] 已导出 {len(pairs)} 个会话 → {output}")
        return

    ensure_dir(output)
    with Progress(*progress_cols, console=console) as progress:
        task = progress.add_task("导出会话", total=len(pairs))
        for proj_dir, session in pairs:
            rel = rel_for(proj_dir, session)
            _render_one(session, output / rel, fmt)
            progress.advance(task)
    console.print(f"[bold green]✓[/] 已导出 {len(pairs)} 个会话 → {output}")
