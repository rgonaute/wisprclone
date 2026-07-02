from __future__ import annotations

ERROR_ALREADY_EXISTS = 183


class SingleInstance:
    """Named-mutex single-instance guard. `acquire()` returns True for the first
    instance and False if another instance already holds the mutex. The handle
    is kept for the process lifetime (releasing it frees the name)."""

    def __init__(self, name: str = "Local\\WisprClone", _create=None):
        self.name = name
        self._create = _create or self._win32_create
        self._handle = None

    @staticmethod
    def _win32_create(name):
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.CreateMutexW(None, False, name)
        return handle, kernel32.GetLastError()

    def acquire(self) -> bool:
        self._handle, last_error = self._create(self.name)
        return last_error != ERROR_ALREADY_EXISTS
