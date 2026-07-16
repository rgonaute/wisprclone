from __future__ import annotations

import time
from typing import Callable, Optional

from .permissions import accessibility_ok


class MacPaster:
    """Clipboard-preserving paste for macOS. Mirrors the Windows Paster contract
    (paste_text/copy_only) but uses NSPasteboard + a changeCount()-based restore
    guard instead of a string compare, and gates on Accessibility trust."""

    def __init__(self, pasteboard=None, sender=None,
                 trust_check: Optional[Callable[[], bool]] = None,
                 sleep: float = 0.15):
        self.pb = pasteboard or NSPasteboardText()
        self.sender = sender or PynputSender()
        self.trust_check = trust_check or accessibility_ok
        self._sleep = sleep

    def paste_text(self, text: str) -> bool:
        # No Accessibility -> synthetic Cmd+V is silently dropped by macOS.
        # AppController reacts to False with a "press Cmd+V to paste" notice but
        # does NOT copy anything itself, so leave the dictation on the pasteboard
        # here (copy-only semantics: one write, no save/restore) and report
        # failure without sending Cmd+V.
        if not self.trust_check():
            self.pb.set_text(text)
            return False
        previous = self.pb.get_text()          # None if non-text (image/file)
        self.pb.set_text(text)
        count = self.pb.change_count()
        self.sender.cmd_v()
        time.sleep(self._sleep)                 # let the target app read it
        # Restore only if the previous content was text AND nothing else wrote to
        # the pasteboard while we pasted (a clipboard manager or the target app).
        if previous is not None and self.pb.change_count() == count:
            self.pb.set_text(previous)
        return True

    def copy_only(self, text: str) -> None:
        self.pb.set_text(text)


class NSPasteboardText:
    """Thin NSPasteboard wrapper. AppKit is imported lazily so this module loads
    on non-macOS (dev box / CI) where tests inject a fake instead."""

    @staticmethod
    def _pb():
        from AppKit import NSPasteboard
        return NSPasteboard.generalPasteboard()

    def get_text(self) -> Optional[str]:
        from AppKit import NSPasteboardTypeString
        pb = self._pb()
        types = pb.types()
        if types is None or NSPasteboardTypeString not in types:
            return None
        value = pb.stringForType_(NSPasteboardTypeString)
        return None if value is None else str(value)

    def set_text(self, text: str) -> None:
        from AppKit import NSPasteboardTypeString
        pb = self._pb()
        pb.clearContents()
        pb.setString_forType_(text, NSPasteboardTypeString)

    def change_count(self) -> int:
        return int(self._pb().changeCount())


class PynputSender:
    def cmd_v(self) -> None:
        from pynput.keyboard import Controller, Key
        kb = Controller()
        with kb.pressed(Key.cmd):
            kb.press("v")
            kb.release("v")
