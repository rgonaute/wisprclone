from __future__ import annotations

from pathlib import Path


class SingleInstance:
    """Advisory-lock single-instance guard using fcntl.flock. The kernel releases
    the lock when the process dies (including crashes), so there are no stale
    locks. Keep the SingleInstance object alive for the process lifetime (its FD
    holds the lock)."""

    def __init__(self, lock_path: Path):
        self.lock_path = Path(lock_path)
        self._fd = None

    def acquire(self) -> bool:
        import fcntl
        import os

        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR, 0o644)
        try:
            fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:  # BlockingIOError when another process holds it
            os.close(self._fd)
            self._fd = None
            return False
