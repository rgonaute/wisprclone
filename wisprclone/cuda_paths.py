"""Put the NVIDIA CUDA runtime DLLs (cuBLAS, cuDNN) on the Windows DLL search
path so ctranslate2 can load them at inference time.

ctranslate2 loads cuBLAS/cuDNN by bare filename via LoadLibrary, which ignores
`os.add_dll_directory` — only PATH is consulted. In a normal pip install the
`nvidia-*-cu12` packages drop the DLLs under
`site-packages/nvidia/{cublas,cudnn}/bin`, but nothing adds those to PATH; in a
frozen (PyInstaller) build they are bundled under the app dir. This finds them
in both cases and prepends them to PATH once, before the model is constructed.

Without this the CUDA model *constructs* fine but the first *inference* raises
`Library cublas64_12.dll is not found or cannot be loaded`.
"""
from __future__ import annotations

import os
import sys

_done = False


def _candidate_bases():
    if getattr(sys, "frozen", False):
        # PyInstaller onedir: bundled data lives under sys._MEIPASS.
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
        yield os.path.join(base, "nvidia")
    else:
        try:
            import nvidia  # namespace package; __file__ is None, use __path__
        except Exception:
            return
        for path in getattr(nvidia, "__path__", []):
            yield path


def cuda_bin_dirs() -> list[str]:
    """Existing cuBLAS/cuDNN `bin` directories, in load order."""
    dirs: list[str] = []
    for base in _candidate_bases():
        for sub in ("cublas", "cudnn"):
            d = os.path.join(base, sub, "bin")
            if os.path.isdir(d) and d not in dirs:
                dirs.append(d)
    return dirs


def ensure_cuda_on_path() -> list[str]:
    """Prepend the CUDA DLL directories to PATH (idempotent). Returns dirs added."""
    global _done
    if _done:
        return []
    _done = True
    dirs = cuda_bin_dirs()
    if dirs:
        os.environ["PATH"] = os.pathsep.join(dirs) + os.pathsep + os.environ.get("PATH", "")
    return dirs
