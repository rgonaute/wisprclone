from __future__ import annotations

import faulthandler
import os
import sys
from pathlib import Path


def _needs_redirect(stdout, stderr) -> bool:
    return stdout is None or stderr is None


def configure(log_dir) -> Path:
    """Prepare a windowed (no-console) frozen app for safe operation:
    - ensure a log directory and return the log file path;
    - disable HuggingFace progress bars (they write to a possibly-None stderr);
    - redirect None std streams to the log file;
    - route native crashes to the log via faulthandler.
    Safe to call in dev too (streams present -> only env + faulthandler)."""
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "wisprclone.log"

    if _needs_redirect(sys.stdout, sys.stderr):
        stream = open(log_path, "a", encoding="utf-8", buffering=1)
        if sys.stdout is None:
            sys.stdout = stream
        if sys.stderr is None:
            sys.stderr = stream

    try:
        faulthandler.enable(open(log_path, "a", encoding="utf-8"))
    except Exception:
        pass

    return log_path
