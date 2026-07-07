# WisprClone for macOS — Design

**Date:** 2026-07-07
**Status:** Approved (design). Fable 5 audited twice → **GO**.
**Scope:** v1 = Apple Silicon only. Side-by-side with the existing Windows app.

---

## 1. Goal & constraints

Port WisprClone (offline push-to-talk dictation: global hotkey → record mic →
local faster-whisper transcription → paste into the focused field, preserving
the clipboard) to macOS, **without changing the Windows version**.

**Hard constraints**

- Every file under `wisprclone/` stays **byte-for-byte unchanged**. The macOS
  port lives side-by-side as a separate `wisprclone_mac/` package that reuses
  the shared core **by import**.
- v1 targets **Apple Silicon only**. Intel is dropped: ctranslate2 no longer
  ships macOS `x86_64` wheels, PyInstaller cannot build a `universal2` binary
  from non-universal extension wheels, and `large-v3`/CPU on Intel is unusably
  slow.
- Backend stays **faster-whisper / ctranslate2 on CPU (`int8`)** — no
  whisper.cpp. (A Metal backend is a possible future follow-up, out of scope.)
- Deliverable: an **unsigned `WisprClone.app` in a `.dmg`**, but the port must
  be **runnable-from-source and smoke-tested first**, then packaged.

**Success criteria**

- On an Apple Silicon Mac, holding the hotkey and speaking pastes transcribed
  text (English and Hebrew) into the focused app, restoring the prior clipboard.
- Missing macOS permissions degrade gracefully and visibly — never silently.
- The Windows app and its build are untouched and still pass their suite.

---

## 2. Module map — what is shared vs. Mac-specific

Verified import-clean on non-Windows (all Windows-only imports are
function-local, so importing these modules on macOS triggers no win32 import):

**Reused unchanged, imported from `wisprclone`:**
`app` (AppController), `tray` (Qt QSystemTrayIcon), `audio` (sounddevice),
`hotkey` (pynput), `transcriber` (ctranslate2; its only Windows tie —
`cuda_paths` — is a guarded no-op when the `nvidia` package is absent),
`history`, `textcleanup`, `runtime_setup`, and `windows.MainWindow` (the
settings/history GUI — misleading filename, but pure PySide6).

**Windows-only, needing a Mac sibling:** `paste`, `single_instance`, `config`
(paths + defaults), and the entry point `__main__`. `cuda_paths` is irrelevant
on Mac.

**Key consequence — the base-model degradation trap:** `transcriber`'s fallback
chain ends at `("base","cpu","int8")`. A Mac left on the Windows default
(`device="cuda"`) would fail both CUDA attempts (no CUDA on macOS) and silently
degrade to the **base** model. Therefore the Mac config **must** default to
`cpu`/`int8` so the chain's first entry is `(medium, cpu, int8)`.

---

## 3. New package: `wisprclone_mac/`

### 3.1 `pasteboard.py` — `MacPaster`

Reimplements the clipboard-preserving paste using **NSPasteboard** (via
`pyobjc-framework-Cocoa`), not `pbcopy`/`pbpaste` (which corrupt Hebrew when
`LANG` is unset — the case for GUI-launched bundles — and cannot distinguish an
empty clipboard from a non-text one).

Behavior contract (pinned by tests):

- **Missing Accessibility** → `paste_text` returns `False` **before touching the
  pasteboard**, so `AppController` (`app.py:67-69`) runs its existing copy-only
  fallback. This reuses the injected `elevated_check` seam (`paste.py:9,17-18`):
  on Mac, `elevated_check = lambda: not AXIsProcessTrusted()`.
- **Get text:** read `NSPasteboard.generalPasteboard()`; if it holds no text
  type (`types()` has no string type), return `None` (mirrors the Windows
  `None` semantics so images/files are never clobbered on restore).
- **Set text + paste + restore:** set the string, synthesize **Cmd+V** via
  pynput's `keyboard.Controller`, wait briefly, then restore the previous text
  **only if** (a) the previous value was text (not `None`) and (b) the
  pasteboard `changeCount()` is unchanged since our write — a race-free guard
  that beats the Windows string-compare (avoids clobbering content the target
  app placed on the clipboard).
- **Unicode/Hebrew** is native to NSString — no locale dependency.

### 3.2 `single_instance.py` — `SingleInstance`

`fcntl.flock(LOCK_EX | LOCK_NB)` on a lock file in the Mac app dir. The kernel
releases the lock on process death (including crash/SIGKILL), so there is no
stale-lock problem. The file descriptor is held for the process lifetime
(referenced from the `QApplication`, mirroring how the Windows build keeps its
mutex handle alive). Second instance: `flock` raises → `acquire()` returns
`False`.

### 3.3 `config.py` — `MacConfig`

`@dataclass class MacConfig(Config)` subclassing the existing dataclass (no
field duplication). Overrides:

- **Field defaults:** `device="cpu"`, `compute_type="int8"`, `model="medium"`,
  `hotkey="alt_r"` (Right Option — a natural, low-conflict push-to-talk on Mac).
- **Path defaults:** override `load`/`save` so their default path is the Mac
  location, `~/Library/Application Support/wisprclone/config.json`, rather than
  the baked-in Windows `CONFIG_PATH`. (`Config.load` uses `cls(**known)` and
  `cls.__dataclass_fields__`, so the subclass loads correctly.)

`APP_DIR = ~/Library/Application Support/wisprclone`; `logs/`, `history.json`,
and the single-instance lock file all live under it.

### 3.4 `permissions.py` — startup preflight

Checks the three TCC permissions this app needs, each of which otherwise fails
**silently**, and surfaces missing ones via a **QMessageBox** (not a tray toast
— those don't render for unsigned/from-source apps). Permission → API table:

| Permission | Check | Request/prompt | Symptom if missing |
|---|---|---|---|
| Accessibility (post Cmd+V) | `AXIsProcessTrusted()` | `AXIsProcessTrustedWithOptions({prompt:true})` | synthetic paste silently dropped |
| Input Monitoring (hotkey event tap) | `CGPreflightListenEventAccess()` | `CGRequestListenEventAccess()` | hotkey dead; `HotkeyCapture` hangs at "Press keys…" |
| Microphone | attempt/AVCaptureDevice status | system prompt on first mic use | recording is all-zeros silence |

`AXIsProcessTrusted` does **not** cover Input Monitoring — both are checked.
Because macOS caches the trust result per process launch, the dialog copy says
**"grant the permission, then relaunch WisprClone,"** and the app re-checks on
next launch rather than silently running un-trusted.

### 3.5 `__main__.py` — Mac entry point

Mirrors the Windows entry, with Mac wiring. **Order matters:**

1. `runtime_setup.configure(APP_DIR/"logs")`
2. `SingleInstance().acquire()` (Mac flock)
3. `QApplication(...)` — must exist before any QMessageBox
4. **permission preflight** (needs QApplication)
5. invoker → `MacConfig.load()` → recorder/transcriber/`MacPaster` →
   controller → tray → hotkey listener → background model warm-up

No CUDA path setup. The `notify` wrapper **tees to stderr** (so feedback is
visible in the from-source milestone) and **rewrites "Ctrl+V" → "Cmd+V"** before
display (keeps shared `app.py:69,72` byte-identical). The mirrored
download-notice string is corrected to **~1.5 GB** for the `medium` model.
`_model_is_cached`'s `~/.cache/huggingface/hub` path is kept as-is (correct on
macOS too — do not "fix" it to `~/Library/Caches`).

### 3.6 Dependencies — `requirements-mac.txt`

`faster-whisper`, `sounddevice`, `numpy`, `pynput`, `PySide6` (pinned to an
exact version so `LSMinimumSystemVersion` is truthful), plus the pyobjc
frameworks we import directly: `pyobjc-framework-Cocoa` (NSPasteboard),
`pyobjc-framework-Quartz` (CGEvent access checks), `pyobjc-framework-
ApplicationServices` (`AXIsProcessTrusted`). These already install transitively
via pynput; declaring them makes the dependency honest and robust to a future
pynput change. **Dropped vs. Windows:** `pywin32`, `nvidia-*`.

---

## 4. Packaging — `macbuild/` (parallel to `winbuild/`)

- **`wisprclone-mac.spec`** — PyInstaller `.app` bundle. Collects **both**
  `wisprclone` and `wisprclone_mac`. `info_plist` sets:
  - `CFBundleIdentifier = com.wisprclone.mac` (**fixed** — TCC keys grants on
    bundle-ID + signing requirement together; a drifting ID re-breaks
    permissions every build).
  - `LSUIElement = 1` (menu-bar/tray-only agent; no Dock icon, no app menu).
  - `NSMicrophoneUsageDescription` (without it, TCC SIGKILLs the app on first
    mic access).
  - `LSMinimumSystemVersion` matching the pinned PySide6 wheel's floor.
- **`build.sh`** (runs on a Mac): clean venv → `requirements-mac.txt` →
  PyInstaller → **codesign with a stable self-signed identity** (so TCC grants
  survive rebuilds) → `.dmg` via **`hdiutil create`** (no `create-dmg`/Homebrew
  dependency) with install notes covering Gatekeeper (unsigned → open via
  System Settings → Privacy & Security).
- **Staged:** runnable-from-source + manual smoke first, then `.app`/`.dmg`.

---

## 5. Testing

`tests/mac/`, mirroring the Windows unit-test pattern. Platform-agnostic tests
run on the existing Windows dev box and in CI by fully mocking AppKit/pynput:

- **`MacPaster`** — mocked NSPasteboard + Controller: Hebrew round-trip;
  non-text previous clipboard → `None` → no restore; `changeCount` unchanged →
  restore, changed → no restore; missing-Accessibility → `False` before any
  pasteboard write.
- **`single_instance`** — real FD on an APFS temp dir: first `acquire()`
  succeeds, second fails.
- **`MacConfig`** — Application-Support paths; `cpu`/`int8`/`medium`/`alt_r`
  defaults; the base-degradation guard (default config's first fallback entry is
  `medium`, not `base`).
- **notify wrapper** — "Ctrl+V" → "Cmd+V" rewrite (pure Python; strongest
  guardrail).

**CI:** add a `macos-latest` (Apple Silicon) GitHub Actions job — unit tests +
an import-smoke of `wisprclone_mac`, with `QT_QPA_PLATFORM=offscreen` so
Qt/QSystemTrayIcon construction doesn't hang headless. TCC/mic can't be tested
headless → they stay in a manual smoke checklist (like the Windows Task 9).

---

## 6. Known tradeoffs of the "Windows-untouched" constraint

- The `"press Ctrl+V"` string is hardcoded in shared `app.py`; handled by
  rewriting it in the Mac notify wrapper rather than editing `app.py`.
- Some entry-point wiring (`_MainThreadInvoker`, controller/tray/listener setup)
  is duplicated between the two `__main__` files rather than shared — accepted
  to keep `wisprclone/` byte-for-byte frozen.

---

## 7. Process

Superpowers **brainstorming → writing-plans → subagent-driven-development**.
**Fable 5 (`claude-fable-5`) owns the implementation** (implementer + reviewer)
and signed off this design — same process used for the Windows build. Plan
prerequisites to lock before building: fixed bundle-ID/min-OS/codesign identity;
the MacPaster restore contract (§3.1); the preflight API mapping (§3.4);
final pyobjc declaration (§3.6); and confirmation the flock + mocked-AppKit
tests run on the Windows dev box and macOS CI.
