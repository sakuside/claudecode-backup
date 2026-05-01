"""`claudecode-backup watch` — mirror ~/.claude/projects to a backup directory."""
from __future__ import annotations

import shutil
import threading
import time
from pathlib import Path
from typing import Callable

from rich.console import Console
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from .paths import ensure_dir, relativize


class _Mirror(FileSystemEventHandler):
    """Mirror file create/modify/move/delete events into ``dest``."""

    def __init__(
        self,
        source: Path,
        dest: Path,
        console: Console,
        log: Callable[[str], None] | None = None,
    ) -> None:
        self.source = source.resolve()
        self.dest = dest.resolve()
        self.console = console
        self._log = log or (lambda msg: console.log(msg))
        # Coalesce rapid bursts on a single jsonl into one copy.
        self._pending: dict[Path, float] = {}
        self._lock = threading.Lock()

    def _dest_for(self, src_path: Path) -> Path | None:
        try:
            rel = relativize(src_path, self.source)
        except ValueError:
            return None
        return self.dest / rel

    def _schedule(self, src_path: Path) -> None:
        with self._lock:
            self._pending[src_path] = time.monotonic()

    def _maybe_copy(self, src_path: Path) -> None:
        dst = self._dest_for(src_path)
        if dst is None:
            return
        try:
            if src_path.is_dir():
                ensure_dir(dst)
                self._log(f"[dim]mkdir[/] {dst}")
                return
            if not src_path.exists():
                return
            ensure_dir(dst.parent)
            shutil.copy2(src_path, dst)
            self._log(f"[green]sync[/]  {src_path.name}")
        except (OSError, PermissionError) as exc:
            self._log(f"[red]error[/] {src_path}: {exc}")

    def flush_pending(self, settle_seconds: float = 0.4) -> None:
        now = time.monotonic()
        ready: list[Path] = []
        with self._lock:
            for path, ts in list(self._pending.items()):
                if now - ts >= settle_seconds:
                    ready.append(path)
                    del self._pending[path]
        for path in ready:
            self._maybe_copy(path)

    # watchdog hooks -------------------------------------------------------
    def on_created(self, event: FileSystemEvent) -> None:
        self._schedule(Path(event.src_path))

    def on_modified(self, event: FileSystemEvent) -> None:
        self._schedule(Path(event.src_path))

    def on_moved(self, event: FileSystemEvent) -> None:
        old_dst = self._dest_for(Path(event.src_path))
        new_src = Path(event.dest_path)
        if old_dst and old_dst.exists():
            try:
                if old_dst.is_dir():
                    shutil.rmtree(old_dst)
                else:
                    old_dst.unlink()
                self._log(f"[yellow]rm[/]    {old_dst}")
            except OSError as exc:
                self._log(f"[red]error[/] removing {old_dst}: {exc}")
        self._schedule(new_src)

    def on_deleted(self, event: FileSystemEvent) -> None:
        dst = self._dest_for(Path(event.src_path))
        if not dst or not dst.exists():
            return
        try:
            if dst.is_dir():
                shutil.rmtree(dst)
            else:
                dst.unlink()
            self._log(f"[yellow]rm[/]    {dst}")
        except OSError as exc:
            self._log(f"[red]error[/] removing {dst}: {exc}")


def _initial_sync(source: Path, dest: Path, console: Console) -> int:
    """Copy everything that exists right now. Returns count of files copied."""
    files = [p for p in source.rglob("*") if p.is_file()]
    if not files:
        return 0

    from rich.progress import (
        BarColumn,
        Progress,
        TextColumn,
        TimeElapsedColumn,
    )

    copied = 0
    with Progress(
        TextColumn("[bold blue]初始同步"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("sync", total=len(files))
        for src in files:
            try:
                rel = relativize(src, source)
            except ValueError:
                progress.advance(task)
                continue
            dst = dest / rel
            ensure_dir(dst.parent)
            try:
                if not dst.exists() or src.stat().st_mtime > dst.stat().st_mtime:
                    shutil.copy2(src, dst)
                    copied += 1
            except OSError as exc:
                console.log(f"[red]error[/] {src}: {exc}")
            progress.advance(task)
    return copied


def run(source: Path, dest: Path, console: Console) -> None:
    if not source.is_dir():
        raise FileNotFoundError(f"source not found: {source}")
    ensure_dir(dest)

    copied = _initial_sync(source, dest, console)
    console.print(f"[bold]初始同步完成[/]: 复制 {copied} 个文件")
    console.print(f"[bold]监听[/] {source} → {dest}    (Ctrl+C 退出)")

    handler = _Mirror(source, dest, console)
    observer = Observer()
    observer.schedule(handler, str(source), recursive=True)
    observer.start()
    try:
        while True:
            time.sleep(0.5)
            handler.flush_pending()
    except KeyboardInterrupt:
        console.print("\n[bold yellow]停止监听[/]")
    finally:
        observer.stop()
        observer.join()
        handler.flush_pending(settle_seconds=0.0)
