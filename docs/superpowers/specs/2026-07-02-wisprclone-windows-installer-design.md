# WisprClone — Windows Installable Program (Packaging) Design

**Date:** 2026-07-02
**Status:** Design approved (user), reviewed by Fable 5 ("sound with changes"), pending spec review
**Depends on:** the GPU PATH fix (commit 9c92e46) — GPU inference must actually work before packaging.

## 1. Summary

Package the existing `python -m wisprclone` tray app as a normal installable
Windows program: a PyInstaller one-folder build wrapped in an Inno Setup
installer producing `WisprClone-Setup.exe`. After install it behaves like any
desktop app — Start Menu entry, entry in Add/Remove Programs with an
uninstaller, optional auto-start at login, an icon, and no terminal/console
window. GPU support (large-v3 on CUDA int8) is preserved by bundling the CUDA
runtime DLLs.

## 2. Goals / Non-Goals

### Goals
- One-folder PyInstaller build → `WisprClone.exe`, windowed (no console), tray only.
- Inno Setup installer: per-user install to `%LOCALAPPDATA%\Programs\WisprClone`
  (no admin/UAC), Start Menu shortcut, optional Desktop shortcut, Add/Remove
  Programs entry + uninstaller.
- Install-time checkbox "Start WisprClone when Windows starts" (default on) →
  `HKCU\…\Run` entry.
- GPU preserved: bundle cuBLAS + cuDNN; the app finds them via `sys._MEIPASS`.
- Single-instance lock so auto-start + manual launch don't run two copies.
- App icon + exe version/publisher metadata, versioned from one source.
- Windowed-mode runtime hardening (no-console `stdout`/`stderr`, logging, faulthandler).
- Config/history/model cache stay in their current per-user locations (survive
  install/upgrade/uninstall).

### Non-Goals
- Code signing (installer stays unsigned; SmartScreen one-time prompt accepted).
- Machine-wide (all-users) install.
- Bundling the Whisper model (downloaded on first run, as today).
- Auto-update (out of scope; a manual re-run of a new installer upgrades in place).

## 3. Prerequisite (done)

GPU inference was broken (model constructed on CUDA but inference raised
`cublas64_12.dll not found`). Fixed in commit 9c92e46:
`cuda_paths.ensure_cuda_on_path()` prepends the cuBLAS/cuDNN bin dirs to `PATH`
(dev: `nvidia.__path__`; frozen: `sys._MEIPASS/nvidia`), and the real model
factory runs a 1s warm-up inference so a backend failure triggers the CPU
fallback instead of a false "GPU ready". Verified live on the GTX 1070.

## 4. Build Pipeline (architecture)

```
clean venv (pinned deps + PyInstaller)
        │
        ▼
PyInstaller (packaging/wisprclone.spec)  ──►  dist/WisprClone/        (one-folder app)
   · windowed, icon, version-file                WisprClone.exe
   · bundle nvidia cuBLAS/cuDNN DLLs             _internal/…  (deps + nvidia/{cublas,cudnn}/bin)
   · hidden imports + data (silero VAD, hf_xet, av.libs)
        │
        ▼
Inno Setup ISCC (packaging/installer.iss) ──►  dist/WisprClone-Setup.exe
   · per-user install, Start Menu, uninstaller
   · optional Desktop icon + "start at login" task
   · delete old Startup\WisprClone.vbs; AppMutex
```

`packaging/build.ps1` runs the whole chain and prints the final installer path.

## 5. App Code Changes (for the frozen build)

These are small, live in the app, and are unit-tested where testable.

| Change | File | Why |
|---|---|---|
| `__version__ = "1.0.0"` single source | `wisprclone/__init__.py` | drives exe version-file + Inno `AppVersion` |
| Console-safe streams: if `sys.stdout is None` (windowed), redirect `stdout`/`stderr` to `%APPDATA%\wisprclone\logs\wisprclone.log`; set `HF_HUB_DISABLE_PROGRESS_BARS=1`; enable `faulthandler` into the log | new `wisprclone/runtime_setup.py`, called first in `main()` | tqdm/ctranslate2 write to stderr; `None` streams raise in a no-console app. Also gives a crash log for native Qt/CUDA faults. |
| Single-instance guard: named mutex `Local\WisprClone` via `ctypes` `CreateMutexW`; if `ERROR_ALREADY_EXISTS`, exit early | new `wisprclone/single_instance.py`, called in `main()` | auto-start + double-click would otherwise run two global hotkey hooks → double paste |
| "Loading model… (first run downloads ~3 GB, one time)" tray notice at warm start | `wisprclone/__main__.py` `_safe_warm` | first-run download is silent for minutes otherwise |

`cuda_paths.py` already supports the frozen path (`sys._MEIPASS/nvidia`).

## 6. PyInstaller Spec (`packaging/wisprclone.spec`)

- **Entry:** a tiny `packaging/entry.py` that does `from wisprclone.__main__ import main; main()` (PyInstaller wants a script, not `-m`).
- **Mode:** one-folder (`COLLECT`), `console=False`, `icon=packaging/wisprclone.ico`, `version='packaging/version_info.txt'`, name `WisprClone`.
- **Binaries (CUDA):** add the installed `nvidia/cublas/bin` and `nvidia/cudnn/bin`
  DLLs, preserving the `nvidia/cublas/bin` + `nvidia/cudnn/bin` relative layout
  under the bundle so `sys._MEIPASS/nvidia/...` resolves. Prune `nvblas64_12.dll`.
  (Measured: cublas bin ~736 MB, cudnn bin ~1011 MB.)
- **Data files:** `collect_data_files("faster_whisper")` (Silero VAD onnx asset).
- **Hidden imports:** `hf_xet` (lazy native; huggingface_hub 1.x uses it).
- **Excludes:** `onnxruntime` (only used by VAD, which the app never invokes with
  `vad_filter=True`) — documented tradeoff; verify large-v3 still loads. Also
  exclude `pytest`, `tkinter`.
- **`av`:** rely on hooks-contrib to gather `av.libs` FFmpeg DLLs; verify present.

## 7. Inno Setup Script (`packaging/installer.iss`)

- `AppId` = a fixed GUID; `AppName=WisprClone`; `AppVersion` from `__version__`;
  `AppPublisher=rgonaute`; `WizardStyle=modern`.
- `PrivilegesRequired=lowest`, `DefaultDirName={localappdata}\Programs\WisprClone`,
  `DefaultGroupName=WisprClone`.
- `[Files]`: `dist\WisprClone\*` (recursive), the one-folder output.
- `[Icons]`: Start Menu `{group}\WisprClone`; Desktop icon under a `desktopicon` task.
- `[Tasks]`: `desktopicon` (unchecked default); `startup` (checked default).
- `[Registry]`: `HKCU Software\Microsoft\Windows\CurrentVersion\Run`, value
  `WisprClone` = `"{app}\WisprClone.exe"` (quoted), `Tasks: startup`,
  `Flags: uninsdeletevalue`.
- `[InstallDelete]`: remove `{userstartup}\WisprClone.vbs` (the old dev launcher)
  and any hand-made copy.
- `[Setup] AppMutex=Local\WisprClone` (matches the app's mutex) so an upgrade
  prompts to close the running tray app instead of failing on locked files.
- Optional `[Tasks] purgedata` (unchecked) + `[UninstallDelete]` to remove
  `%APPDATA%\wisprclone` and the HF model cache on uninstall (default: keep).
- `Compression=lzma2` (normal — not max; the payload is ~2.5 GB and max is slow +
  RAM-hungry). If the compressed installer exceeds ~2.1 GB, set `DiskSpanning=yes`.

## 8. Build environment

- Build in a **fresh venv** (not the polluted global site-packages) with pinned
  versions in `packaging/requirements-build.txt`: ctranslate2 4.8.0,
  faster-whisper 1.2.1, PySide6 6.11.1, huggingface_hub 1.21.0, hf_xet 1.5.1,
  av 18.0.0, numpy 2.4.4, pynput 1.8.2, sounddevice 0.5.5,
  nvidia-cublas-cu12 12.9.2.10, nvidia-cudnn-cu12 9.23.2.1, pywin32 311, plus
  latest `pyinstaller` + `pyinstaller-hooks-contrib`. (Runtime `requirements.txt`
  gets `pytest` split out into a separate dev list.)
- Python 3.14 is supported by current PyInstaller — no downgrade.
- Inno Setup installed via `winget install JRSoftware.InnoSetup` if absent;
  `iscc` invoked by the build script.

## 9. Sizes & first-run (set expectations)

- Installed program: ~2.3–2.6 GB (CUDA DLLs ~1.75 GB dominate).
- `WisprClone-Setup.exe`: ~1–1.4 GB (CUDA compresses well).
- First run downloads large-v3 to the HF cache: ~2.9 GB, one time; tray notifies.

## 10. Testing

- **Unit (pytest, CI-safe):** `single_instance` mutex logic (mock `ctypes` calls /
  test the "already running" decision), version string present/consistent,
  existing `cuda_paths` tests. The frozen build, Qt UI, and GPU remain
  manual-smoke (unchanged policy).
- **Build smoke:** build completes; `iscc` produces the installer.
- **Manual install smoke checklist (on this machine), in order:**
  1. Run `WisprClone-Setup.exe` → installs without admin prompt; Start Menu +
     Add/Remove entry appear.
  2. Launch from Start Menu → tray icon appears, no console window.
  3. Hold hotkey, speak → text pastes, and it is on **GPU** (tray toast says
     cuda/int8 AND a dictation actually pastes — not just the toast).
  4. Hebrew dictation works in the frozen build (tokenizer data present).
  5. Reboot → auto-starts to tray (if the task was checked).
  6. Launch a second copy → no-ops (single instance), no double paste.
  7. Old `Startup\WisprClone.vbs` is gone.
  8. Uninstall → app removed; `%APPDATA%\wisprclone` config preserved (unless
     purge task chosen); reinstall keeps settings.
  9. Windows Defender scan of the built exe/installer is clean (unsigned +
     keyboard-hook combo is a known false-positive risk).

## 11. Known caveats

- **SmartScreen:** unsigned → "unrecognized app" prompt on first run
  (More info → Run anyway). One-time, per download.
- **Defender false-positive risk:** unsigned PyInstaller exe + global keyboard
  hook. Test before relying; if flagged, an exclusion or (later) code-signing
  resolves it.
- **Auto-start cost:** loads large-v3 into VRAM at every login (deliberate) —
  slows logon slightly and holds GPU memory while running.

## 12. Deliverables

```
packaging/
├── entry.py                    # PyInstaller entry: calls wisprclone.main()
├── wisprclone.spec             # PyInstaller build spec
├── wisprclone.ico              # generated app icon (committed)
├── make_icon.py                # regenerates the icon (PIL)
├── version_info.txt            # generated from __version__
├── installer.iss               # Inno Setup script
├── requirements-build.txt      # pinned build deps
└── build.ps1                   # venv → PyInstaller → ISCC → WisprClone-Setup.exe
wisprclone/
├── __init__.py                 # + __version__
├── runtime_setup.py            # console-safe streams + logging + faulthandler
└── single_instance.py          # named-mutex single-instance guard
```
Build outputs (`dist/`, `build/`, `.venv-build/`) are gitignored.
