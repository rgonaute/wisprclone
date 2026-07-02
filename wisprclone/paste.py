from __future__ import annotations

import time
from typing import Callable, Optional


class Paster:
    def __init__(self, clipboard=None, sender=None,
                 elevated_check: Optional[Callable[[], bool]] = None):
        self.clipboard = clipboard or Win32Clipboard()
        self.sender = sender or Win32Sender()
        self.elevated_check = elevated_check or foreground_is_elevated

    def paste_text(self, text: str) -> bool:
        previous = self.clipboard.get_text()
        self.clipboard.set_text(text)
        if self.elevated_check():
            return False
        self.sender.ctrl_v()
        # Give the target app time to read the clipboard before we restore it;
        # slower apps (Electron, RDP) can otherwise paste the restored content.
        time.sleep(0.15)
        if previous is not None and self.clipboard.get_text() == text:
            self.clipboard.set_text(previous)
        return True

    def copy_only(self, text: str) -> None:
        """Place text on the clipboard without sending a synthetic paste."""
        self.clipboard.set_text(text)


class Win32Clipboard:
    def get_text(self) -> Optional[str]:
        import win32clipboard
        win32clipboard.OpenClipboard()
        try:
            import win32con
            if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
                return win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
            return None
        finally:
            win32clipboard.CloseClipboard()

    def set_text(self, text: str) -> None:
        import win32clipboard
        import win32con
        win32clipboard.OpenClipboard()
        try:
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
        finally:
            win32clipboard.CloseClipboard()


class Win32Sender:
    def ctrl_v(self) -> None:
        import ctypes

        VK_CONTROL = 0x11
        VK_V = 0x56
        KEYEVENTF_KEYUP = 0x0002
        user32 = ctypes.windll.user32
        user32.keybd_event(VK_CONTROL, 0, 0, 0)
        user32.keybd_event(VK_V, 0, 0, 0)
        user32.keybd_event(VK_V, 0, KEYEVENTF_KEYUP, 0)
        user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)


def foreground_is_elevated() -> bool:
    """True if the foreground window belongs to a process we cannot query
    (usually an elevated/admin process), which blocks synthetic input via UIPI."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    ERROR_ACCESS_DENIED = 5

    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return False
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if handle:
        kernel32.CloseHandle(handle)
        return False
    return ctypes.get_last_error() == ERROR_ACCESS_DENIED
