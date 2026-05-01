"""`claudecode-backup list` — print a table of projects and sessions."""
from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.table import Table

from .paths import (
    format_iso,
    iter_project_dirs,
    iter_session_files,
    project_cwd,
    summarize_session,
)


def run(projects_dir: Path, console: Console) -> None:
    if not projects_dir.is_dir():
        console.print(f"[yellow]projects directory not found: {projects_dir}[/]")
        return

    table = Table(
        title=f"Claude Code 项目 ({projects_dir})",
        title_style="bold cyan",
        show_lines=False,
    )
    table.add_column("项目目录", style="cyan", overflow="fold")
    table.add_column("原始 cwd", style="green", overflow="fold")
    table.add_column("会话数", justify="right")
    table.add_column("消息总数", justify="right")
    table.add_column("最后更新", style="magenta")

    total_sessions = 0
    total_messages = 0
    for project_dir in iter_project_dirs(projects_dir):
        sessions = list(iter_session_files(project_dir))
        if not sessions:
            continue
        infos = [summarize_session(p) for p in sessions]
        msg_count = sum(i.message_count for i in infos)
        last = max(i.last_modified for i in infos)
        cwd = project_cwd(project_dir) or "[dim](未知)[/]"
        table.add_row(
            project_dir.name,
            cwd,
            str(len(sessions)),
            str(msg_count),
            format_iso(last),
        )
        total_sessions += len(sessions)
        total_messages += msg_count

    console.print(table)
    console.print(
        f"[bold]共 {table.row_count} 个项目 / {total_sessions} 个会话 / "
        f"{total_messages} 条消息[/]"
    )
