"""Take screenshots of the running ``claudecode-backup viewer`` window.

Finds the window by title with the Win32 ``FindWindowW`` API, brings it
to the foreground, and captures it via ``PIL.ImageGrab``. Used to
produce illustrations for the user manual.

Run this AFTER launching the app and waiting for it to be visible::

    python scripts/take_screenshots.py docs/images/main.png
"""
from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes
from pathlib import Path

from PIL import ImageGrab


# Match the OS DPI scaling so ``GetWindowRect`` returns physical pixels
# (otherwise Pillow's screen capture and the bbox disagree on a HiDPI display).
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_DPI_AWARE
except (AttributeError, OSError):
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except (AttributeError, OSError):
        pass

user32 = ctypes.windll.user32
user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.FindWindowW.restype = wintypes.HWND
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
SW_RESTORE = 9


def find_window(partial_title: str) -> int:
    """Walk top-level windows; return the first whose title contains the substring."""
    matches: list[int] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, lparam):
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        if partial_title in buf.value:
            matches.append(hwnd)
        return True

    user32.EnumWindows(cb, 0)
    return matches[0] if matches else 0


HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
user32.SetWindowPos.argtypes = [
    wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
    ctypes.c_int, ctypes.c_int, ctypes.c_uint,
]


def capture(hwnd: int, out: Path) -> None:
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    user32.ShowWindow(hwnd, SW_RESTORE)
    # SetForegroundWindow gets blocked when called from a non-foreground
    # process. Briefly toggle TOPMOST instead so the window paints on top
    # for the screenshot, then drop it back to a normal z-order.
    flags = SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW
    user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, flags)
    time.sleep(0.6)
    bbox = (rect.left, rect.top, rect.right, rect.bottom)
    img = ImageGrab.grab(bbox=bbox, all_screens=True)
    user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, flags)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "PNG")
    print(f"saved {out}  ({img.size[0]}x{img.size[1]})")


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("screenshot.png")
    title_substring = sys.argv[2] if len(sys.argv) > 2 else "claudecode-backup viewer"
    hwnd = find_window(title_substring)
    if not hwnd:
        print(f"window with title containing {title_substring!r} not found", file=sys.stderr)
        return 1
    capture(hwnd, out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
