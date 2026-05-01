"""Typer-based CLI entrypoint for ``claudecode-backup``."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console

from . import __version__
from .paths import default_projects_dir, parse_remap

# UTF-8 console — Windows defaults to GBK and will mangle Chinese output
# unless we force a UTF-8 wrapper around stdout.
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

console = Console()

app = typer.Typer(
    help="备份 / 导出 / 导入 Claude Code 对话记录",
    add_completion=False,
    no_args_is_help=True,
    rich_markup_mode="rich",
)


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"claudecode-backup {__version__}")
        raise typer.Exit()


@app.callback()
def _root(
    version: bool = typer.Option(
        False, "--version", callback=_version_callback, is_eager=True,
        help="显示版本号并退出",
    ),
) -> None:
    """claudecode-backup CLI."""


def _projects_option() -> Path:
    return typer.Option(
        default_projects_dir(),
        "--projects-dir",
        help="Claude Code 项目目录 (默认 ~/.claude/projects)",
    )


@app.command("list", help="列出所有项目和会话数量、最后更新时间")
def list_cmd(
    projects_dir: Path = _projects_option(),
) -> None:
    from .lister import run

    run(projects_dir, console)


@app.command("watch", help="实时监听 ~/.claude/projects/，文件变动时同步到备份目录")
def watch_cmd(
    backup_dir: Path = typer.Argument(..., help="备份目录"),
    projects_dir: Path = _projects_option(),
) -> None:
    from .watcher import run

    try:
        run(projects_dir, backup_dir, console)
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(code=1)


@app.command("export", help="导出会话为目录或 zip 包")
def export_cmd(
    output: Path = typer.Option(..., "--output", "-o", help="输出路径"),
    fmt: str = typer.Option(
        "jsonl",
        "--format",
        "-f",
        case_sensitive=False,
        help="输出格式: jsonl | md | html",
    ),
    all_projects: bool = typer.Option(
        False, "--all", help="导出所有项目"
    ),
    project: Optional[str] = typer.Option(
        None,
        "--project",
        help="导出指定项目 (可填路径如 G:\\backup 或编码后的目录名 G--backup)",
    ),
    zip_output: bool = typer.Option(
        False, "--zip", help="打包为 zip (默认输出目录)。--all 时强烈建议开启"
    ),
    projects_dir: Path = _projects_option(),
) -> None:
    fmt = fmt.lower()
    if fmt not in {"jsonl", "md", "html"}:
        console.print(f"[red]未知格式: {fmt}[/]")
        raise typer.Exit(code=2)
    if all_projects and project is not None:
        console.print("[red]--all 与 --project 互斥[/]")
        raise typer.Exit(code=2)
    # Treat ``-o file.zip`` as implicit --zip for convenience.
    if output.suffix.lower() == ".zip":
        zip_output = True

    from .exporter import run

    try:
        run(
            projects_dir=projects_dir,
            output=output,
            fmt=fmt,
            all_projects=all_projects,
            project=project,
            zip_output=zip_output,
            console=console,
        )
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(code=1)


@app.command("serve", help="启动本地 Web 查看器，像 Claude Code 聊天界面一样浏览历史")
def serve_cmd(
    project: Optional[str] = typer.Option(
        None,
        "--project",
        help="只显示指定项目 (路径如 G:\\backup 或编码后目录名 G--backup)",
    ),
    host: str = typer.Option("127.0.0.1", "--host", help="监听地址"),
    port: int = typer.Option(8765, "--port", "-p", help="监听端口"),
    no_browser: bool = typer.Option(
        False, "--no-browser", help="启动后不自动打开浏览器"
    ),
    projects_dir: Path = _projects_option(),
) -> None:
    only = None
    if project is not None:
        from .paths import encode_project_path

        # Accept both raw paths and pre-encoded directory names.
        candidate = projects_dir / project
        only = candidate.name if candidate.is_dir() else encode_project_path(project)
        if not (projects_dir / only).is_dir():
            console.print(f"[red]找不到项目目录: {projects_dir / only}[/]")
            raise typer.Exit(code=1)

    from .viewer.server import serve

    serve(
        projects_dir=projects_dir,
        host=host,
        port=port,
        only_project=only,
        open_browser=not no_browser,
    )


@app.command("app", help="作为桌面应用启动 (PySide6 / WebEngine 窗口)")
def app_cmd(
    project: Optional[str] = typer.Option(
        None,
        "--project",
        help="只显示指定项目 (路径如 G:\\backup 或编码后目录名 G--backup)",
    ),
    width: int = typer.Option(1280, "--width", help="窗口宽度 px"),
    height: int = typer.Option(820, "--height", help="窗口高度 px"),
    projects_dir: Path = _projects_option(),
) -> None:
    # Prefer a persisted dir from the user config when the caller didn't
    # override --projects-dir. Lets a packaged .exe remember "where my
    # .claude lives" across runs after the user picks via the UI.
    from . import config as user_config

    if projects_dir == default_projects_dir():
        persisted = user_config.get_projects_dir()
        if persisted is not None:
            projects_dir = persisted

    only = None
    if project is not None:
        from .paths import encode_project_path

        candidate = projects_dir / project
        only = candidate.name if candidate.is_dir() else encode_project_path(project)
        if not (projects_dir / only).is_dir():
            console.print(f"[red]找不到项目目录: {projects_dir / only}[/]")
            raise typer.Exit(code=1)

    try:
        from .viewer.qt_window import run_window
    except ImportError as exc:
        console.print(
            f"[red]缺少 PySide6: {exc}[/]\n"
            "请运行: [bold]pip install PySide6[/]"
        )
        raise typer.Exit(code=1)

    code = run_window(
        projects_dir=projects_dir,
        only_project=only,
        width=width,
        height=height,
    )
    raise typer.Exit(code=code)


@app.command("import", help="从备份目录或 zip 还原到 ~/.claude/projects/")
def import_cmd(
    source: Path = typer.Argument(..., help="备份目录或 .zip 文件"),
    target: Path = _projects_option(),
    remap_path: List[str] = typer.Option(
        [],
        "--remap-path",
        help='跨电脑路径映射，格式 "旧路径=新路径"，可重复',
    ),
) -> None:
    try:
        remaps = [parse_remap(s) for s in remap_path]
    except ValueError as exc:
        console.print(f"[red]--remap-path 错误: {exc}[/]")
        raise typer.Exit(code=2)

    from .importer import run

    try:
        run(source=source, target=target, remap_specs=remaps, console=console)
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
