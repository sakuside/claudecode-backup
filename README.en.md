# claudecode-backup

> 🇬🇧 **English** (current) · [🇨🇳 中文](README.md)

**claudecode-backup** is a small toolkit for [Claude Code](https://claude.com/claude-code) conversation history:

1. Back up / export / import / migrate the jsonl sessions under `~/.claude/projects/` between machines
2. Ship a Claude.ai-styled light-theme desktop viewer (PySide6 + WebEngine) so you can browse history like a chat app

![Main view](docs/images/main.png)

---

## Quick start

### GUI viewer (most common)

For the packaged Windows distribution: double-click `claudecode-backup-viewer.exe`. On first launch, if the default `~/.claude/projects/` doesn't exist, click **更换** ("Change") in the sidebar and pick the right folder.

From source:

```bash
pip install -e .
claudecode-backup app
```

### CLI subcommands

```bash
claudecode-backup list                       # list every project + session
claudecode-backup watch D:\backups\claude    # live mirror to a backup dir
claudecode-backup export --all -o backup.zip # export everything as zip
claudecode-backup export --project G--backup --format md -o ./out
claudecode-backup import backup.zip --remap-path "G:\backup=D:\new"
claudecode-backup serve                      # browser-based viewer (HTTP)
claudecode-backup app                        # desktop viewer (recommended)
```

---

## GUI viewer

| Feature | Notes |
|---------|-------|
| Project picker | Top-left dropdown, all projects sorted alphabetically |
| Session switching | Click in sidebar, ordered by mtime descending |
| Font size | Top-right `A- 14px A+`, 11–22 px, persisted in localStorage |
| Image jump | Sessions with images get a `📷 N images` button — click to cycle |
| Switch data source | "更换" link in sidebar opens a Windows folder dialog; persisted to `%APPDATA%\claudecode-backup\config.json` |
| Collapsible cards | THINKING / TOOL_USE / TOOL_RESULT collapsed by default |
| Code highlighting | highlight.js (atom-one-light) |
| Markdown | marked.js + GFM tables / lists / blockquotes |

### Design highlights

- **Read-only** — every API endpoint is `GET`; no mutation paths
- **Offline** — marked.js and highlight.js are vendored under `static/vendor/`; no network calls
- **No ports** — a custom `app://` URL scheme has Python serve requests directly, no sockets
- **Native window** — closing the window quits cleanly; no Edge `--app` heartbeat-detection hack

---

## Install

Requires Python ≥ 3.9.

```bash
git clone <repo>
cd claudecode-backup
pip install -e .
```

Dependencies: `typer` / `rich` / `watchdog` / `flask` / `PySide6`

---

## CLI subcommand reference

### `list` — list every project

```bash
claudecode-backup list
```

Prints a table: encoded project dir, original cwd, session count, total messages, last-modified time.

### `watch` — live backup

```bash
claudecode-backup watch D:\backups\claude
```

Performs an initial full sync, then uses watchdog to mirror incremental changes from `~/.claude/projects/` to your backup directory. `Ctrl+C` to stop. Schedule it via Task Scheduler / cron / systemd to run on boot.

### `export` — export sessions

```bash
# Full archive as zip (raw jsonl — best for re-importing later)
claudecode-backup export --all -o claudecode-backup-2026-04-30.zip

# Single project as Markdown (rendered chronologically)
claudecode-backup export --project "G:\backup" --format md -o ./out

# Single project as HTML
claudecode-backup export --project G--backup --format html -o ./out --zip
```

`--project` accepts three forms:
- Encoded directory name (`G--backup`)
- Original path (`G:\backup`)
- Absolute path to any directory containing jsonl files

When `-o` ends in `.zip`, packing is enabled automatically.

### `import` — restore on another machine

```bash
claudecode-backup import backup.zip \
  --remap-path "G:\backup=D:\projects\backup"
```

`--remap-path` does two things at once:
1. Rewrites the `cwd` field in every jsonl event (prefix match)
2. Renames the top-level project directory using Claude Code's encoding rule (`G:\backup` → `G--backup`)

`--remap-path` can be repeated.

### `serve` — browser viewer

```bash
claudecode-backup serve --port 8765
```

Spins up a Flask server. Same UI as `app`, but over HTTP — useful for LAN access (add `--host 0.0.0.0`).

### `app` — desktop viewer (recommended)

```bash
claudecode-backup app
claudecode-backup app --project F--EMG-filiter-Predict
claudecode-backup app --width 1600 --height 1000
```

Native PySide6 + QtWebEngine window. No port, closing the window exits.

---

## Building the .exe

```bash
pip install pyinstaller
pyinstaller claudecode-backup-viewer.spec
```

Output lands in `dist/claudecode-backup-viewer/` (~460 MB, mostly PySide6 + Chromium runtime). Ship the whole folder.

> **Don't** use `--onefile` — `QtWebEngineProcess.exe` can't find its resources from the temp extraction directory and crashes immediately.

---

## File locations

| Path | What |
|------|------|
| `%USERPROFILE%\.claude\projects\` | Claude Code's default data source |
| `%APPDATA%\claudecode-backup\config.json` | User config (persisted projects_dir) |
| `dist\claudecode-backup-viewer\` | PyInstaller artifact |

The GUI resolves the projects dir in this order: `--projects-dir` CLI flag → `config.json` → default `~/.claude/projects/`.

---

## FAQ

**Q: Will it modify my conversation history?**
No. Among all CLI subcommands and the GUI, only `import` writes to a target directory (that's its job). Everything else is strictly read-only.

**Q: Does it phone home?**
No. Every static asset (marked.js, highlight.js) is vendored in the package. Zero outbound network traffic.

**Q: Why is the bundle 460 MB?**
PySide6 + Chromium runtime is genuinely that large. If you can accept the slight tradeoff of using Edge / Chrome's `--app` window mode, see [`window.py`](claudecode_backup/viewer/window.py) — that path produces a ~30 MB bundle but depends on a system-installed Chromium browser.

**Q: Will Chinese / non-ASCII paths break things?**
No. All file I/O is UTF-8.

---

## License

MIT
