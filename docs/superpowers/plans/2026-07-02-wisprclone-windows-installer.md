# WisprClone Windows Installer — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Package the existing WisprClone tray app as an installable Windows program (`WisprClone-Setup.exe`) with GPU support, Start Menu entry, uninstaller, and optional auto-start.

**Architecture:** A few small app-code changes make the app safe when frozen (console-safe streams, single-instance guard). PyInstaller (`--onedir`) freezes it into `dist/WisprClone/`, explicitly bundling the CUDA cuBLAS/cuDNN DLLs. Inno Setup wraps that into a per-user installer. A `build.ps1` orchestrates a clean venv → PyInstaller → ISCC.

**Tech Stack:** Python 3.14, PyInstaller (one-folder, windowed), Inno Setup, PySide6, faster-whisper/ctranslate2, Pillow (icon).

## Global Constraints

- Python 3.14; Windows-only runtime. Build in a **fresh venv**, not global site-packages.
- Multilingual models only, default `large-v3`; never log transcript/clipboard content.
- Frozen build is **windowed** (`console=False`): `sys.stdout`/`sys.stderr` are `None` — never assume they exist.
- Bundle CUDA DLLs preserving the `nvidia/cublas/bin` + `nvidia/cudnn/bin` layout so `cuda_paths.ensure_cuda_on_path()` finds them via `sys._MEIPASS`.
- Single-instance mutex name is exactly `Local\WisprClone`; the Inno `AppMutex` must match it verbatim.
- Per-user install to `%LOCALAPPDATA%\Programs\WisprClone`, `PrivilegesRequired=lowest` (no admin).
- Auto-start via `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`, value name `WisprClone`, quoted exe path, gated on the install-time `startup` task (default checked).
- Prune `nvblas64_12.dll`; exclude `onnxruntime`, `pytest`, `tkinter` from the bundle.
- Config/history/model cache stay under `%APPDATA%\wisprclone` and the HF cache — never bundled, never deleted except via the optional uninstall purge task.
- Version is single-sourced from `wisprclone/__init__.py:__version__` (semver `MAJOR.MINOR.PATCH`).

---

### Task 1: Version single-source + split dev requirements

**Files:**
- Modify: `wisprclone/__init__.py`
- Create: `requirements-dev.txt`
- Modify: `requirements.txt`
- Test: `tests/test_version.py`

**Interfaces:**
- Produces: `wisprclone.__version__: str` (semver).

- [ ] **Step 1: Write the failing test** — `tests/test_version.py`

```python
import re
import wisprclone


def test_version_is_semver():
    assert re.fullmatch(r"\d+\.\d+\.\d+", wisprclone.__version__)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_version.py -v`
Expected: FAIL (`AttributeError: module 'wisprclone' has no attribute '__version__'`).

- [ ] **Step 3: Add the version** — set the entire contents of `wisprclone/__init__.py` to:

```python
__version__ = "1.0.0"
```

- [ ] **Step 4: Split requirements** — set `requirements.txt` to (remove the `pytest` line):

```
faster-whisper>=1.0.0
sounddevice>=0.4.6
numpy>=1.24
pynput>=1.7.6
PySide6>=6.6.0
pywin32>=306
nvidia-cublas-cu12
nvidia-cudnn-cu12
```

Create `requirements-dev.txt`:

```
-r requirements.txt
pytest>=8.0
```

- [ ] **Step 5: Run test to verify it passes, then full suite**

Run: `python -m pytest -v`
Expected: PASS (all green, including the new version test).

- [ ] **Step 6: Commit**

```bash
git add wisprclone/__init__.py requirements.txt requirements-dev.txt tests/test_version.py
git commit -m "feat: single-source __version__ and split dev requirements"
```

---

### Task 2: Single-instance guard

**Files:**
- Create: `wisprclone/single_instance.py`
- Test: `tests/test_single_instance.py`

**Interfaces:**
- Produces: `SingleInstance(name="Local\\WisprClone", _create=None)` with `acquire() -> bool` (True if this is the only instance; False if one is already running). Keeps the mutex handle alive on the instance. `_create` is an injectable callable `(name) -> (handle, last_error)`.

- [ ] **Step 1: Write the failing test** — `tests/test_single_instance.py`

```python
from wisprclone.single_instance import SingleInstance, ERROR_ALREADY_EXISTS


def test_first_instance_acquires():
    si = SingleInstance(_create=lambda name: (1234, 0))
    assert si.acquire() is True
    assert si._handle == 1234


def test_second_instance_detected():
    si = SingleInstance(_create=lambda name: (5678, ERROR_ALREADY_EXISTS))
    assert si.acquire() is False


def test_uses_given_name():
    seen = {}
    def create(name):
        seen["name"] = name
        return (1, 0)
    SingleInstance(name="Local\\Foo", _create=create).acquire()
    assert seen["name"] == "Local\\Foo"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_single_instance.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement** — `wisprclone/single_instance.py`

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_single_instance.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add wisprclone/single_instance.py tests/test_single_instance.py
git commit -m "feat: single-instance mutex guard"
```

---

### Task 3: Console-safe runtime setup

**Files:**
- Create: `wisprclone/runtime_setup.py`
- Test: `tests/test_runtime_setup.py`

**Interfaces:**
- Produces: `configure(log_dir) -> Path` (creates the log dir, sets `HF_HUB_DISABLE_PROGRESS_BARS`, redirects `None` std streams to a log file, enables faulthandler). `_needs_redirect(stdout, stderr) -> bool`.

- [ ] **Step 1: Write the failing test** — `tests/test_runtime_setup.py`

```python
import os
from wisprclone.runtime_setup import configure, _needs_redirect


def test_needs_redirect_true_when_stream_none():
    assert _needs_redirect(None, object()) is True
    assert _needs_redirect(object(), None) is True


def test_needs_redirect_false_when_both_present():
    assert _needs_redirect(object(), object()) is False


def test_configure_creates_logdir_and_sets_env(tmp_path, monkeypatch):
    monkeypatch.delenv("HF_HUB_DISABLE_PROGRESS_BARS", raising=False)
    log_dir = tmp_path / "logs"
    path = configure(log_dir)
    assert log_dir.is_dir()
    assert os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] == "1"
    assert str(path).startswith(str(log_dir))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_runtime_setup.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement** — `wisprclone/runtime_setup.py`

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_runtime_setup.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add wisprclone/runtime_setup.py tests/test_runtime_setup.py
git commit -m "feat: console-safe runtime setup for windowed frozen build"
```

---

### Task 4: Wire runtime setup + single instance + download notice into main()

**Files:**
- Modify: `wisprclone/__main__.py`

**Interfaces:**
- Consumes: `configure` (Task 3), `SingleInstance` (Task 2), `ensure_cuda_on_path` (existing), `APP_DIR` (existing).

- [ ] **Step 1: Update the top of `main()`** — in `wisprclone/__main__.py`, replace the current opening of `main()`:

```python
def main() -> int:
    from .cuda_paths import ensure_cuda_on_path
    ensure_cuda_on_path()  # CUDA DLLs on PATH before any model load

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # tray app keeps running with no window
```

with:

```python
def main() -> int:
    from .config import APP_DIR
    from .runtime_setup import configure
    configure(APP_DIR / "logs")  # console-safe streams + logging (windowed build)

    from .single_instance import SingleInstance
    instance = SingleInstance()
    if not instance.acquire():
        return 0  # another copy is already running; do nothing

    from .cuda_paths import ensure_cuda_on_path
    ensure_cuda_on_path()  # CUDA DLLs on PATH before any model load

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # tray app keeps running with no window
    app._wisprclone_instance = instance  # keep the mutex handle alive for the app's life
```

- [ ] **Step 2: Add a first-run download notice** — in `wisprclone/__main__.py`, change the start of `_safe_warm` from:

```python
def _safe_warm(transcriber: Transcriber, tray_ref) -> None:
    try:
        transcriber.load()
```

to:

```python
def _safe_warm(transcriber: Transcriber, tray_ref) -> None:
    try:
        _on_main_thread(lambda: tray_ref["tray"].notify(
            "Loading model… first run downloads ~3 GB (one time)."))
        transcriber.load()
```

- [ ] **Step 3: Verify it imports and the suite still passes**

Run: `python -c "import wisprclone.__main__; print('import ok')"`
Expected: `import ok`

Run: `python -m pytest -q`
Expected: all pass (no unit tests cover `main()` wiring; this is the regression guard).

- [ ] **Step 4: Commit**

```bash
git add wisprclone/__main__.py
git commit -m "feat: wire runtime setup, single-instance guard, and download notice into main"
```

---

### Task 5: App icon

**Files:**
- Create: `winbuild/make_icon.py`
- Create (generated, committed): `winbuild/wisprclone.ico`
- Test: `tests/test_icon.py`

**Interfaces:**
- Produces: `winbuild/wisprclone.ico` (multi-size Windows icon). `make_icon.build(path)`.

- [ ] **Step 1: Write the failing test** — `tests/test_icon.py`

```python
from pathlib import Path

import pytest


def test_make_icon_produces_valid_ico(tmp_path):
    Image = pytest.importorskip("PIL.Image")  # CI has no Pillow -> skip cleanly
    from winbuild.make_icon import build
    out = tmp_path / "x.ico"
    build(out)
    assert out.exists()
    with Image.open(out) as im:
        assert im.format == "ICO"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_icon.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'winbuild.make_icon'`).
(Note: `winbuild/` needs an `__init__.py` for this import — create an empty `winbuild/__init__.py`.)

- [ ] **Step 3: Implement** — create empty `winbuild/__init__.py`, then `winbuild/make_icon.py`:

```python
"""Generate the WisprClone app icon (a simple mic dot on a dark rounded square)."""
from pathlib import Path

from PIL import Image, ImageDraw


def build(path) -> Path:
    path = Path(path)
    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # dark rounded background
    d.rounded_rectangle([8, 8, size - 8, size - 8], radius=48, fill=(15, 18, 31, 255))
    # microphone body (rounded pill)
    d.rounded_rectangle([104, 60, 152, 150], radius=24, fill=(0, 255, 132, 255))
    # stand
    d.arc([84, 120, 172, 190], start=0, end=180, width=10, fill=(0, 255, 132, 255))
    d.line([128, 190, 128, 210], width=10, fill=(0, 255, 132, 255))
    d.line([104, 212, 152, 212], width=10, fill=(0, 255, 132, 255))
    img.save(path, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return path


if __name__ == "__main__":
    out = build(Path(__file__).with_name("wisprclone.ico"))
    print("wrote", out)
```

- [ ] **Step 4: Run test to verify it passes, then generate the committed icon**

Run: `python -m pytest tests/test_icon.py -v`
Expected: PASS.

Run: `python winbuild/make_icon.py`
Expected: prints `wrote .../winbuild/wisprclone.ico`.

- [ ] **Step 5: Commit**

```bash
git add winbuild/__init__.py winbuild/make_icon.py winbuild/wisprclone.ico tests/test_icon.py
git commit -m "feat: generate app icon"
```

---

### Task 6: PyInstaller entry, version resource, and spec

**Files:**
- Create: `winbuild/entry.py`
- Create: `winbuild/gen_version_info.py`
- Create: `winbuild/wisprclone.spec`

**Interfaces:**
- Consumes: `wisprclone.__main__:main`, `wisprclone.__version__`, `winbuild/wisprclone.ico`.
- Produces: (when built) `dist/WisprClone/WisprClone.exe` plus `_internal/` with bundled deps and `_internal/nvidia/{cublas,cudnn}/bin`.

- [ ] **Step 1: Create the entry script** — `winbuild/entry.py`:

```python
import sys

from wisprclone.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Create the version-resource generator** — `winbuild/gen_version_info.py`:

```python
"""Write a PyInstaller version resource (version_info.txt) from wisprclone.__version__."""
from pathlib import Path

import wisprclone

TEMPLATE = """\
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({maj}, {min}, {pat}, 0),
    prodvers=({maj}, {min}, {pat}, 0),
    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'rgonaute'),
      StringStruct('FileDescription', 'WisprClone — offline dictation'),
      StringStruct('FileVersion', '{ver}'),
      StringStruct('InternalName', 'WisprClone'),
      StringStruct('OriginalFilename', 'WisprClone.exe'),
      StringStruct('ProductName', 'WisprClone'),
      StringStruct('ProductVersion', '{ver}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""


def build(path) -> Path:
    maj, min_, pat = wisprclone.__version__.split(".")
    text = TEMPLATE.format(maj=maj, min=min_, pat=pat, ver=wisprclone.__version__)
    Path(path).write_text(text, encoding="utf-8")
    return Path(path)


if __name__ == "__main__":
    out = build(Path(__file__).with_name("version_info.txt"))
    print("wrote", out)
```

- [ ] **Step 3: Create the PyInstaller spec** — `winbuild/wisprclone.spec` (run from the repo root: `pyinstaller winbuild/wisprclone.spec`):

```python
# -*- mode: python ; coding: utf-8 -*-
import os

from PyInstaller.utils.hooks import collect_data_files
import nvidia  # provided by nvidia-cublas-cu12 / nvidia-cudnn-cu12

# Bundle the CUDA DLLs, preserving nvidia/<lib>/bin layout so
# cuda_paths.ensure_cuda_on_path() finds them via sys._MEIPASS at runtime.
cuda_binaries = []
for base in list(nvidia.__path__):
    for sub in ("cublas", "cudnn"):
        bindir = os.path.join(base, sub, "bin")
        if os.path.isdir(bindir):
            for fn in os.listdir(bindir):
                if fn.lower().endswith(".dll") and fn.lower() != "nvblas64_12.dll":
                    cuda_binaries.append((os.path.join(bindir, fn), f"nvidia/{sub}/bin"))

datas = collect_data_files("faster_whisper")  # Silero VAD asset, etc.

a = Analysis(
    ['winbuild/entry.py'],
    pathex=['.'],
    binaries=cuda_binaries,
    datas=datas,
    hiddenimports=['hf_xet'],
    excludes=['onnxruntime', 'pytest', 'tkinter'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True,
    name='WisprClone', console=False,
    icon='winbuild/wisprclone.ico', version='winbuild/version_info.txt',
)
coll = COLLECT(exe, a.binaries, a.datas, name='WisprClone')
```

- [ ] **Step 4: Verify the helper scripts run** (full PyInstaller build happens in Task 8 under the clean venv)

Run: `python winbuild/gen_version_info.py`
Expected: prints `wrote .../winbuild/version_info.txt`.

Run: `python -c "import ast; ast.parse(open('winbuild/wisprclone.spec').read()); print('spec parses')"`
Expected: `spec parses`.

- [ ] **Step 5: Commit**

```bash
git add winbuild/entry.py winbuild/gen_version_info.py winbuild/wisprclone.spec winbuild/version_info.txt
git commit -m "feat: PyInstaller entry, version resource, and build spec"
```

---

### Task 7: Inno Setup installer script

**Files:**
- Create: `winbuild/installer.iss`

**Interfaces:**
- Consumes: `dist/WisprClone/` (Task 8 build output), `wisprclone.__version__`.
- Produces: (when compiled) `dist/WisprClone-Setup.exe`.

- [ ] **Step 1: Create the installer script** — `winbuild/installer.iss` (`{#Version}` is passed by `build.ps1` via `/DVersion=`):

```iss
#ifndef Version
  #define Version "1.0.0"
#endif

[Setup]
AppId={{8F3B1C42-1E7A-4C9E-9E1D-WISPRCLONE001}
AppName=WisprClone
AppVersion={#Version}
AppPublisher=rgonaute
WizardStyle=modern
DefaultDirName={localappdata}\Programs\WisprClone
DefaultGroupName=WisprClone
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=WisprClone-Setup
Compression=lzma2
SolidCompression=yes
AppMutex=Local\WisprClone
UninstallDisplayIcon={app}\WisprClone.exe

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked
Name: "startup"; Description: "Start WisprClone when Windows starts"
Name: "purgedata"; Description: "On uninstall, also delete settings, history, and the downloaded model"; Flags: unchecked

[Files]
Source: "..\dist\WisprClone\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\WisprClone"; Filename: "{app}\WisprClone.exe"
Name: "{group}\Uninstall WisprClone"; Filename: "{uninstallexe}"
Name: "{userdesktop}\WisprClone"; Filename: "{app}\WisprClone.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "WisprClone"; ValueData: """{app}\WisprClone.exe"""; Tasks: startup; Flags: uninsdeletevalue

[InstallDelete]
; Remove the old dev launcher so it doesn't double-launch alongside the installed app.
Type: files; Name: "{userstartup}\WisprClone.vbs"

[Run]
Filename: "{app}\WisprClone.exe"; Description: "Launch WisprClone"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\wisprclone"; Tasks: purgedata
Type: filesandordirs; Name: "{userappdata}\wisprclone"; Tasks: purgedata
```

- [ ] **Step 2: Verify the script is present and well-formed** (compilation happens in Task 8)

Run: `python -c "t=open('winbuild/installer.iss',encoding='utf-8').read(); assert 'AppMutex=Local\\\\WisprClone' in t and 'PrivilegesRequired=lowest' in t; print('iss ok')"`
Expected: `iss ok`

- [ ] **Step 3: Commit**

```bash
git add winbuild/installer.iss
git commit -m "feat: Inno Setup installer script"
```

---

### Task 8: Build orchestration script + gitignore + docs, and produce the installer

**Files:**
- Create: `winbuild/requirements-build.txt`
- Create: `winbuild/build.ps1`
- Modify: `.gitignore`
- Modify: `README.md`

**Interfaces:**
- Consumes: everything above.
- Produces: `dist/WisprClone-Setup.exe`.

- [ ] **Step 1: Pinned build requirements** — `winbuild/requirements-build.txt`:

```
faster-whisper==1.2.1
ctranslate2==4.8.0
sounddevice==0.5.5
numpy==2.4.4
pynput==1.8.2
PySide6==6.11.1
pywin32==311
huggingface_hub==1.21.0
hf_xet==1.5.1
av==18.0.0
nvidia-cublas-cu12==12.9.2.10
nvidia-cudnn-cu12==9.23.2.1
pillow
pyinstaller
pyinstaller-hooks-contrib
```

- [ ] **Step 2: Build script** — `winbuild/build.ps1`:

```powershell
# Build WisprClone-Setup.exe: clean venv -> PyInstaller -> Inno Setup.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot   # repo root
Set-Location $root

$venv = ".venv-build"
if (Test-Path $venv) { Remove-Item -Recurse -Force $venv }
py -3.14 -m venv $venv
$py = Join-Path $venv "Scripts\python.exe"

& $py -m pip install --upgrade pip
& $py -m pip install -r winbuild\requirements-build.txt

# Generate version resource + icon from the single-source version.
& $py winbuild\gen_version_info.py
& $py winbuild\make_icon.py

# Clean prior build output, then freeze.
if (Test-Path build) { Remove-Item -Recurse -Force build }
if (Test-Path dist)  { Remove-Item -Recurse -Force dist }
& $py -m PyInstaller --clean --noconfirm winbuild\wisprclone.spec

if (-not (Test-Path "dist\WisprClone\WisprClone.exe")) { throw "PyInstaller output missing" }

# Read version for the installer.
$ver = (& $py -c "import wisprclone; print(wisprclone.__version__)").Trim()

# Locate Inno Setup compiler (install if missing).
$iscc = Get-Command iscc -ErrorAction SilentlyContinue
if (-not $iscc) {
  $candidate = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
  if (-not (Test-Path $candidate)) { winget install -e --id JRSoftware.InnoSetup --accept-source-agreements --accept-package-agreements }
  $iscc = $candidate
} else { $iscc = $iscc.Source }

& $iscc "/DVersion=$ver" winbuild\installer.iss

Write-Host "Built dist\WisprClone-Setup.exe"
```

- [ ] **Step 3: Ignore build outputs** — append to `.gitignore`:

```
.venv-build/
build/
dist/
winbuild/version_info.txt
```

(Note: `winbuild/version_info.txt` is generated by the build; it was committed in Task 6 as a smoke artifact — remove it from tracking now: `git rm --cached winbuild/version_info.txt`.)

- [ ] **Step 4: Document install** — add to `README.md` under a new "Install (packaged)" section:

```markdown
## Install (packaged Windows program)

Download `WisprClone-Setup.exe` and run it (Windows SmartScreen will show
"unrecognized app" for the unsigned installer — More info → Run anyway).
It installs per-user (no admin), adds a Start Menu entry, and — if you leave
the checkbox ticked — starts automatically at login. First launch downloads
the model (~3 GB, one time); the tray shows "Loading model…".

Uninstall from Settings → Apps, or the Start Menu "Uninstall WisprClone".
Your settings/history/model are kept unless you tick "also delete settings…"
during uninstall.

### Building the installer yourself
```
powershell -ExecutionPolicy Bypass -File winbuild\build.ps1
```
Produces `dist\WisprClone-Setup.exe` (~1–1.4 GB; installed size ~2.3–2.6 GB).
```

- [ ] **Step 5: Run the full build**

Run: `powershell -ExecutionPolicy Bypass -File winbuild\build.ps1`
Expected: ends with `Built dist\WisprClone-Setup.exe`; the file exists. (This is long — clean venv install + freezing ~2.5 GB + compressing. Watch for: PyInstaller output missing, ISCC not found, `av.libs`/`hf_xet` warnings.)

- [ ] **Step 6: Verify the frozen app bundled CUDA**

Run: `python -c "import os; p='dist/WisprClone/_internal/nvidia/cublas/bin'; print('cuBLAS bundled:', os.path.isdir(p) and any(f.endswith('.dll') for f in os.listdir(p)))"`
Expected: `cuBLAS bundled: True`

- [ ] **Step 7: Commit**

```bash
git rm --cached winbuild/version_info.txt
git add winbuild/requirements-build.txt winbuild/build.ps1 .gitignore README.md
git commit -m "feat: build orchestration, gitignore build outputs, install docs"
```

---

### Task 9: Manual install smoke (user-run — requires the real machine)

**Not automatable.** After Task 8 produces `dist\WisprClone-Setup.exe`, the user runs the checklist from the spec (§10), in order. Record pass/fail per item; any failure returns to systematic debugging.

- [ ] Run `WisprClone-Setup.exe` → installs with no admin prompt; Start Menu + Add/Remove entries appear.
- [ ] Launch from Start Menu → tray icon appears, **no console window**.
- [ ] Hold hotkey, speak → text pastes, tray shows cuda/int8 **and a dictation actually pastes** (not just the toast).
- [ ] Hebrew dictation works in the frozen build.
- [ ] Reboot → auto-starts to tray (if `startup` task was checked).
- [ ] Launch a second copy → no-ops (single instance); no double paste.
- [ ] Old `Startup\WisprClone.vbs` is gone.
- [ ] Uninstall → app removed; `%APPDATA%\wisprclone` config preserved (no purge); reinstall keeps settings.
- [ ] Windows Defender scan of the built exe/installer is clean.

---

## Self-Review Notes

- **Spec coverage:** version single-source (T1), single-instance + `AppMutex` (T2, wired T4, installer T7), console-safe streams/logging/faulthandler + download notice (T3, T4), icon + version metadata (T5, T6), PyInstaller onedir + CUDA bundling + excludes + hidden imports/data (T6), per-user installer + Start Menu + uninstaller + autostart task + delete old .vbs + purge option (T7), clean-venv build orchestration + winget Inno install + sizes/docs + gitignore (T8), manual smoke incl. the "GPU-toast-lies" check and Defender (T9). CUDA PATH prerequisite already shipped (9c92e46).
- **Placeholder scan:** none — every file has complete content; build/installer tasks verified by artifact-existence + the manual smoke (Qt/frozen/GPU are not unit-testable, per policy).
- **Type/name consistency:** mutex name `Local\WisprClone` identical in `single_instance.py`, `main()`, and `installer.iss AppMutex`; `__version__` semver drives `gen_version_info.py` and Inno `/DVersion`; bundled CUDA path `nvidia/{cublas,cudnn}/bin` matches `cuda_paths._candidate_bases()` frozen branch (`sys._MEIPASS/nvidia`).
```
