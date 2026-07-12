from __future__ import annotations


def format_notice(message: str) -> str:
    """Rewrite Windows-centric paste hints for macOS. AppController (app.py) is
    shared and frozen, so it emits 'press Ctrl+V'; fix it at display time."""
    return message.replace("Ctrl+V", "Cmd+V")
