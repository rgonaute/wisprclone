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
    log_path = log_dir / "wisprclone.log"

    file_stream = None
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_stream = open(log_path, "a", encoding="utf-8", buffering=1)
    except Exception:
        file_stream = None

    if _needs_redirect(sys.stdout, sys.stderr):
        # Never let libraries writing to a None stream crash a windowed app;
        # fall back to os.devnull if the log file could not be opened.
        stream = file_stream or open(os.devnull, "w", encoding="utf-8")
        if sys.stdout is None:
            sys.stdout = stream
        if sys.stderr is None:
            sys.stderr = stream

    if file_stream is not None:
        try:
            faulthandler.enable(file_stream)
        except Exception:
            pass

    return log_path
