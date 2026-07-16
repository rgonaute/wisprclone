from __future__ import annotations

import sys


def format_notice(message: str) -> str:
    """Rewrite Windows-centric paste hints for macOS. AppController (app.py) is
    shared and frozen, so it emits 'press Ctrl+V'; fix it at display time."""
    return message.replace("Ctrl+V", "Cmd+V")


def _make_notify(tray_ref: dict, stderr=None):
    """Tee a notice to stderr and the tray toast. format_notice runs ONCE, up
    front, so the console and the toast show the same (Cmd+V) text. Lives here
    (not __main__) so it stays importable without PySide6 — the Windows CI job
    runs the suite with no Qt installed."""
    def notify(msg: str) -> None:
        text = format_notice(msg)
        (stderr or sys.stderr).write(f"[wisprclone] {text}\n")
        tray = tray_ref["tray"]
        if tray is not None:
            tray.notify(text)
    return notify
