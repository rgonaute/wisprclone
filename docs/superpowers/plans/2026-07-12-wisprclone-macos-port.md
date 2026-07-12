# WisprClone macOS Port Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a macOS (Apple Silicon) build of WisprClone as a side-by-side `wisprclone_mac/` package that reuses the Windows core by import, without changing any existing file.

**Architecture:** A new top-level package `wisprclone_mac/` imports the OS-neutral shared modules from `wisprclone` (`app`, `tray`, `audio`, `hotkey`, `transcriber`, `history`, `textcleanup`, `runtime_setup`, `windows.MainWindow`) and supplies only the Mac-specific pieces: NSPasteboard-based paste with an Accessibility gate, an `fcntl.flock` single-instance guard, a `MacConfig` dataclass subclass with CPU/int8/medium defaults and Application-Support paths, a permission preflight, and a Mac entry point. Packaging builds an unsigned `.app`/`.dmg` via PyInstaller.

**Tech Stack:** Python 3.12+, faster-whisper/ctranslate2 (CPU int8), PySide6, pynput, pyobjc (transitive via pynput, declared), PyInstaller, `hdiutil`.

## Global Constraints

Every task below inherits these. Values are copied verbatim from the spec (`docs/superpowers/specs/2026-07-07-wisprclone-macos-port-design.md`).

- **Every file under `wisprclone/` stays byte-for-byte unchanged.** Never edit, never rename. All Mac code lives under `wisprclone_mac/`, `macbuild/`, `tests/mac/`.
- **Target: Apple Silicon only.** No universal2, no Intel.
- **Backend:** faster-whisper / ctranslate2 on `device="cpu"`, `compute_type="int8"`. No whisper.cpp.
- **Mac defaults:** `model="medium"`, `device="cpu"`, `compute_type="int8"`, `hotkey="alt_r"`.
- **Mac app dir:** `~/Library/Application Support/wisprclone` (config, logs, history, lock file).
- **Bundle identity (fixed):** `CFBundleIdentifier = com.wisprclone.mac`; sign with a **stable self-signed identity** so TCC grants survive rebuilds.
- **Info.plist:** `LSUIElement = 1`, `NSMicrophoneUsageDescription`, `LSMinimumSystemVersion = 12.0`.
- **pyobjc frameworks we import are declared** in `requirements-mac.txt`: `pyobjc-framework-Cocoa`, `pyobjc-framework-Quartz`, `pyobjc-framework-ApplicationServices`.
- **Dropped vs. Windows:** `pywin32`, `nvidia-*`.
- **Packaging:** `.dmg` via `hdiutil create` (no `create-dmg`/Homebrew dep). Model-download notice says **~1.5 GB** (medium).
- **CI import-smoke** runs with `QT_QPA_PLATFORM=offscreen`.
- **Import discipline:** platform-only imports (`fcntl`, `AppKit`, `Quartz`, `ApplicationServices`, `pynput.keyboard.Controller`) are **function-local**, so every module imports cleanly on the Windows dev box and the shared test suite runs there. No module under `wisprclone_mac/` may import PySide6, AppKit, or `fcntl` at module top — except `wisprclone_mac/__main__.py`, which is never imported by the test suite.

---

### Task 1: Package scaffold + `MacConfig`

**Files:**
- Create: `wisprclone_mac/__init__.py` (empty)
- Create: `wisprclone_mac/config.py`
- Create: `requirements-mac.txt`
- Create: `tests/mac/__init__.py` (empty)
- Test: `tests/mac/test_config.py`

**Interfaces:**
- Consumes: `wisprclone.config.Config` (dataclass), `wisprclone.transcriber.Transcriber` (for the guard test).
- Produces: `wisprclone_mac.config.MacConfig` (subclass of `Config`), module constants `MAC_APP_DIR: Path`, `MAC_CONFIG_PATH: Path`. `MacConfig.load(path=MAC_CONFIG_PATH) -> MacConfig` and `MacConfig.save(self, path=MAC_CONFIG_PATH) -> None`.

- [ ] **Step 1: Create the package scaffold and requirements file**

Create empty `wisprclone_mac/__init__.py` and empty `tests/mac/__init__.py`.

Create `requirements-mac.txt`:

```
faster-whisper>=1.0.0
sounddevice>=0.4.6
numpy>=1.24
pynput>=1.7.6
PySide6==6.11.1
pyobjc-framework-Cocoa
pyobjc-framework-Quartz
pyobjc-framework-ApplicationServices
```

- [ ] **Step 2: Write the failing test**

Create `tests/mac/test_config.py`:

```python
from pathlib import Path

from wisprclone_mac.config import MacConfig, MAC_APP_DIR, MAC_CONFIG_PATH


def test_mac_defaults_are_cpu_int8_medium_altr():
    c = MacConfig()
    assert c.device == "cpu"
    assert c.compute_type == "int8"
    assert c.model == "medium"
    assert c.hotkey == "alt_r"


def test_mac_paths_under_application_support():
    assert MAC_APP_DIR.parts[-3:] == ("Library", "Application Support", "wisprclone")
    assert MAC_CONFIG_PATH == MAC_APP_DIR / "config.json"


def test_first_fallback_is_medium_not_base():
    # The transcriber chain ends at ("base","cpu","int8"); a default cpu/int8
    # config must make the FIRST attempt the medium model, or Mac silently
    # degrades to base.
    from wisprclone.transcriber import Transcriber
    chain = Transcriber(MacConfig())._fallback_chain()
    assert chain[0] == ("medium", "cpu", "int8")


def test_load_missing_file_uses_mac_defaults(tmp_path):
    c = MacConfig.load(tmp_path / "nope.json")
    assert c.device == "cpu" and c.model == "medium"


def test_save_then_load_roundtrip_keeps_mac_defaults(tmp_path):
    p = tmp_path / "config.json"
    MacConfig(vocab_hint="Kubernetes").save(p)
    loaded = MacConfig.load(p)
    assert loaded.vocab_hint == "Kubernetes"
    assert loaded.device == "cpu"
    assert isinstance(loaded, MacConfig)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/mac/test_config.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'wisprclone_mac.config'`

- [ ] **Step 4: Write the implementation**

Create `wisprclone_mac/config.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from wisprclone.config import Config

MAC_APP_DIR = Path.home() / "Library" / "Application Support" / "wisprclone"
MAC_CONFIG_PATH = MAC_APP_DIR / "config.json"


@dataclass
class MacConfig(Config):
    """Config with macOS-appropriate defaults. Overrides only the fields whose
    Windows defaults are wrong on Mac; everything else is inherited. The cpu/int8
    defaults are load-bearing: the transcriber fallback chain ends at
    ("base","cpu","int8"), so a cuda default would silently degrade Mac to base."""

    hotkey: str = "alt_r"          # Right Option — low-conflict push-to-talk
    model: str = "medium"          # large-v3 is too slow on CPU
    device: str = "cpu"            # no CUDA on macOS
    compute_type: str = "int8"

    @classmethod
    def load(cls, path: Path = MAC_CONFIG_PATH) -> "MacConfig":
        return super().load(path)

    def save(self, path: Path = MAC_CONFIG_PATH) -> None:
        super().save(path)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/mac/test_config.py -q`
Expected: PASS (5 passed)

- [ ] **Step 6: Commit**

```bash
git add wisprclone_mac/__init__.py wisprclone_mac/config.py requirements-mac.txt tests/mac/__init__.py tests/mac/test_config.py
git commit -m "feat(mac): MacConfig with cpu/int8/medium defaults + Application Support paths"
```

---

### Task 2: `single_instance.py` (flock guard)

**Files:**
- Create: `wisprclone_mac/single_instance.py`
- Test: `tests/mac/test_single_instance.py`

**Interfaces:**
- Produces: `wisprclone_mac.single_instance.SingleInstance(lock_path: Path)` with `acquire() -> bool` (True for the first holder, False if another process holds the lock). The FD is kept on the instance for the process lifetime.

- [ ] **Step 1: Write the failing test**

Create `tests/mac/test_single_instance.py`:

```python
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform == "win32",
                                reason="fcntl is POSIX-only; runs on macOS CI")


def test_first_acquire_succeeds(tmp_path):
    from wisprclone_mac.single_instance import SingleInstance
    assert SingleInstance(tmp_path / "wc.lock").acquire() is True


def test_second_instance_is_blocked(tmp_path):
    from wisprclone_mac.single_instance import SingleInstance
    a = SingleInstance(tmp_path / "wc.lock")
    b = SingleInstance(tmp_path / "wc.lock")
    assert a.acquire() is True
    assert b.acquire() is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/mac/test_single_instance.py -q`
Expected on macOS: FAIL — `ModuleNotFoundError: No module named 'wisprclone_mac.single_instance'`. On Windows: 2 skipped (acceptable — this task is verified on macOS/CI).

- [ ] **Step 3: Write the implementation**

Create `wisprclone_mac/single_instance.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/mac/test_single_instance.py -q`
Expected on macOS: PASS (2 passed). On Windows: 2 skipped.

- [ ] **Step 5: Commit**

```bash
git add wisprclone_mac/single_instance.py tests/mac/test_single_instance.py
git commit -m "feat(mac): fcntl.flock single-instance guard"
```

---

### Task 3: `permissions.py` (preflight)

**Files:**
- Create: `wisprclone_mac/permissions.py`
- Test: `tests/mac/test_permissions.py`

**Interfaces:**
- Produces:
  - `accessibility_ok() -> bool` (wraps `AXIsProcessTrusted`, lazy import, returns False on any failure)
  - `input_monitoring_ok() -> bool` (wraps `CGPreflightListenEventAccess`, lazy import, returns False on any failure)
  - `missing_permissions(accessibility: bool, input_monitoring: bool) -> list[str]`
  - `permission_message(missing: list[str]) -> str`
  - `preflight(show_dialog: Callable[[str], None], ax_check=accessibility_ok, im_check=input_monitoring_ok) -> list[str]`

- [ ] **Step 1: Write the failing test**

Create `tests/mac/test_permissions.py`:

```python
from wisprclone_mac.permissions import (
    missing_permissions, permission_message, preflight,
)


def test_no_missing_when_all_granted():
    assert missing_permissions(True, True) == []


def test_lists_both_when_neither_granted():
    assert missing_permissions(False, False) == ["Accessibility", "Input Monitoring"]


def test_lists_only_input_monitoring():
    assert missing_permissions(True, False) == ["Input Monitoring"]


def test_message_names_missing_and_says_relaunch():
    msg = permission_message(["Accessibility"])
    assert "Accessibility" in msg
    assert "relaunch" in msg.lower()


def test_preflight_shows_dialog_and_returns_missing():
    shown = []
    missing = preflight(shown.append, ax_check=lambda: False, im_check=lambda: True)
    assert missing == ["Accessibility"]
    assert len(shown) == 1 and "Accessibility" in shown[0]


def test_preflight_is_silent_when_all_ok():
    shown = []
    missing = preflight(shown.append, ax_check=lambda: True, im_check=lambda: True)
    assert missing == []
    assert shown == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/mac/test_permissions.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'wisprclone_mac.permissions'`

- [ ] **Step 3: Write the implementation**

Create `wisprclone_mac/permissions.py`:

```python
from __future__ import annotations

from typing import Callable

# Permission name -> why WisprClone needs it (shown to the user).
_REASON = {
    "Accessibility": "paste transcribed text (synthetic Cmd+V)",
    "Input Monitoring": "detect the global push-to-talk hotkey",
}


def accessibility_ok() -> bool:
    """True if the process is trusted to post synthetic events (Accessibility)."""
    try:
        from ApplicationServices import AXIsProcessTrusted
        return bool(AXIsProcessTrusted())
    except Exception:
        return False


def input_monitoring_ok() -> bool:
    """True if the process may listen to the keyboard event tap (Input
    Monitoring). This is a DIFFERENT permission from Accessibility."""
    try:
        from Quartz import CGPreflightListenEventAccess
        return bool(CGPreflightListenEventAccess())
    except Exception:
        return False


def missing_permissions(accessibility: bool, input_monitoring: bool) -> list[str]:
    missing = []
    if not accessibility:
        missing.append("Accessibility")
    if not input_monitoring:
        missing.append("Input Monitoring")
    return missing


def permission_message(missing: list[str]) -> str:
    lines = ["WisprClone needs these macOS permissions to work:", ""]
    for name in missing:
        lines.append(f"  • {name} — to {_REASON[name]}")
    lines += [
        "",
        "Open System Settings → Privacy & Security, enable WisprClone under "
        "each item above, then relaunch WisprClone.",
    ]
    return "\n".join(lines)


def preflight(show_dialog: Callable[[str], None],
              ax_check: Callable[[], bool] = accessibility_ok,
              im_check: Callable[[], bool] = input_monitoring_ok) -> list[str]:
    """Check permissions; if any are missing, call show_dialog with an
    explanatory message. Returns the list of missing permission names."""
    missing = missing_permissions(ax_check(), im_check())
    if missing:
        show_dialog(permission_message(missing))
    return missing
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/mac/test_permissions.py -q`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add wisprclone_mac/permissions.py tests/mac/test_permissions.py
git commit -m "feat(mac): permission preflight (Accessibility + Input Monitoring)"
```

---

### Task 4: `pasteboard.py` (`MacPaster`)

**Files:**
- Create: `wisprclone_mac/pasteboard.py`
- Test: `tests/mac/test_pasteboard.py`

**Interfaces:**
- Consumes: `wisprclone_mac.permissions.accessibility_ok`.
- Produces: `wisprclone_mac.pasteboard.MacPaster(pasteboard=None, sender=None, trust_check=None, sleep=0.15)` implementing the `Paster` protocol that `AppController` expects: `paste_text(text: str) -> bool` and `copy_only(text: str) -> None`. Collaborators (all injectable for tests):
  - `pasteboard`: object with `get_text() -> str | None`, `set_text(str) -> None`, `change_count() -> int` (default `NSPasteboardText`).
  - `sender`: object with `cmd_v() -> None` (default `PynputSender`).
  - `trust_check`: `() -> bool`, True when Accessibility-trusted (default `accessibility_ok`).

- [ ] **Step 1: Write the failing test**

Create `tests/mac/test_pasteboard.py`:

```python
from wisprclone_mac.pasteboard import MacPaster


class FakePasteboard:
    def __init__(self, initial=None):
        self.value = initial
        self._count = 0

    def get_text(self):
        return self.value

    def set_text(self, text):
        self.value = text
        self._count += 1

    def change_count(self):
        return self._count


class FakeSender:
    def __init__(self):
        self.calls = 0

    def cmd_v(self):
        self.calls += 1


def _paster(prev=None, trusted=True):
    pb = FakePasteboard(prev)
    sender = FakeSender()
    p = MacPaster(pasteboard=pb, sender=sender, trust_check=lambda: trusted, sleep=0)
    return p, pb, sender


def test_returns_false_and_touches_nothing_when_not_trusted():
    p, pb, sender = _paster(prev="old", trusted=False)
    assert p.paste_text("hi") is False
    assert sender.calls == 0
    assert pb.value == "old"


def test_sends_cmd_v_and_restores_previous_text():
    p, pb, sender = _paster(prev="old", trusted=True)
    assert p.paste_text("שלום") is True   # Hebrew "shalom"
    assert sender.calls == 1
    assert pb.value == "old"


def test_text_is_on_pasteboard_at_the_moment_paste_fires():
    pb = FakePasteboard("old")

    class RecordingSender:
        def __init__(self, pb):
            self.pb = pb
            self.at_paste = None

        def cmd_v(self):
            self.at_paste = self.pb.value

    sender = RecordingSender(pb)
    MacPaster(pasteboard=pb, sender=sender, trust_check=lambda: True,
              sleep=0).paste_text("שלום")
    assert sender.at_paste == "שלום"


def test_does_not_restore_when_previous_was_nontext():
    p, pb, sender = _paster(prev=None, trusted=True)
    assert p.paste_text("hi") is True
    assert pb.value == "hi"   # never restored to None -> images/files kept safe


def test_does_not_restore_when_clipboard_changed_during_paste():
    pb = FakePasteboard("old")

    class ClobberSender:
        def __init__(self, pb):
            self.pb = pb

        def cmd_v(self):
            self.pb.set_text("target app copied this")

    MacPaster(pasteboard=pb, sender=ClobberSender(pb), trust_check=lambda: True,
              sleep=0).paste_text("hi")
    assert pb.value == "target app copied this"


def test_copy_only_sets_text_without_pasting():
    p, pb, sender = _paster(prev="x", trusted=True)
    p.copy_only("data")
    assert pb.value == "data"
    assert sender.calls == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/mac/test_pasteboard.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'wisprclone_mac.pasteboard'`

- [ ] **Step 3: Write the implementation**

Create `wisprclone_mac/pasteboard.py`:

```python
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
        # No Accessibility -> synthetic Cmd+V is silently dropped by macOS. Bail
        # BEFORE touching the pasteboard so AppController falls back to copy-only
        # (and we never set-then-fail-to-restore, wiping the user's clipboard).
        if not self.trust_check():
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/mac/test_pasteboard.py -q`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add wisprclone_mac/pasteboard.py tests/mac/test_pasteboard.py
git commit -m "feat(mac): NSPasteboard paste with Accessibility gate + changeCount restore"
```

---

### Task 5: `notice.py` + Mac entry point `__main__.py`

**Files:**
- Create: `wisprclone_mac/notice.py`
- Create: `wisprclone_mac/__main__.py`
- Test: `tests/mac/test_notice.py`

**Interfaces:**
- Produces: `wisprclone_mac.notice.format_notice(message: str) -> str` (rewrites "Ctrl+V" → "Cmd+V"); `wisprclone_mac.__main__.main() -> int`.
- Consumes: `MacConfig`, `MAC_APP_DIR`, `MAC_CONFIG_PATH`, `MacPaster`, `SingleInstance`, `permissions.preflight`, and shared `wisprclone` modules.

`notice.py` is a separate tiny module (no PySide6 import) so its test runs on the Windows CI job, which does not install PySide6. `__main__.py` is never imported by the pytest suite — it is exercised only by the macOS import-smoke and manual runs.

- [ ] **Step 1: Write the failing test**

Create `tests/mac/test_notice.py`:

```python
from wisprclone_mac.notice import format_notice


def test_rewrites_ctrl_v_to_cmd_v():
    assert format_notice("Copied to clipboard — press Ctrl+V to paste.") == \
        "Copied to clipboard — press Cmd+V to paste."


def test_leaves_unrelated_text_untouched():
    assert format_notice("Settings saved.") == "Settings saved."
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/mac/test_notice.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'wisprclone_mac.notice'`

- [ ] **Step 3: Write `notice.py`**

Create `wisprclone_mac/notice.py`:

```python
from __future__ import annotations


def format_notice(message: str) -> str:
    """Rewrite Windows-centric paste hints for macOS. AppController (app.py) is
    shared and frozen, so it emits 'press Ctrl+V'; fix it at display time."""
    return message.replace("Ctrl+V", "Cmd+V")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/mac/test_notice.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Write `__main__.py`**

Create `wisprclone_mac/__main__.py`:

```python
from __future__ import annotations

import sys
import threading
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication, QMessageBox

from wisprclone.app import AppController
from wisprclone.audio import Recorder
from wisprclone.history import HistoryStore
from wisprclone.hotkey import HotkeyListener
from wisprclone.runtime_setup import configure
from wisprclone.transcriber import Transcriber
from wisprclone.tray import Tray
from wisprclone.windows import MainWindow

from . import permissions
from .config import MAC_APP_DIR, MAC_CONFIG_PATH, MacConfig
from .notice import format_notice
from .pasteboard import MacPaster
from .single_instance import SingleInstance


class _MainThreadInvoker(QObject):
    """Marshal a callable from a background thread onto the Qt event loop, via a
    queued signal connection (see the Windows entry for the full rationale)."""

    _invoke = Signal(object)

    def __init__(self):
        super().__init__()
        self._invoke.connect(self._run)

    def _run(self, fn):
        fn()

    def post(self, fn):
        self._invoke.emit(fn)


_invoker: "_MainThreadInvoker | None" = None


def _on_main_thread(fn):
    _invoker.post(fn)


def _model_is_cached(model: str) -> bool:
    hub = Path.home() / ".cache" / "huggingface" / "hub"
    return any(hub.glob(f"models--Systran--faster-whisper-{model}"))


def main() -> int:
    configure(MAC_APP_DIR / "logs")

    instance = SingleInstance(MAC_APP_DIR / "wisprclone.lock")
    if not instance.acquire():
        return 0  # another copy is already running

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app._wisprclone_instance = instance  # keep the flock FD alive for app lifetime

    # QMessageBox needs a QApplication, so the preflight runs after it is created.
    def show_dialog(text: str) -> None:
        QMessageBox.warning(None, "WisprClone — permissions needed", text)

    permissions.preflight(show_dialog)

    global _invoker
    _invoker = _MainThreadInvoker()

    config = MacConfig.load()
    history = HistoryStore(MAC_APP_DIR / "history.json", cap=config.history_cap)
    recorder = Recorder(device=config.input_device)
    transcriber = Transcriber(config)
    paster = MacPaster()

    window_ref = {"win": None}
    tray_ref = {"tray": None}

    def notify(msg: str) -> None:
        sys.stderr.write(f"[wisprclone] {msg}\n")
        tray = tray_ref["tray"]
        if tray is not None:
            tray.notify(format_notice(msg))

    controller = AppController(
        config, recorder, transcriber, paster, history,
        notify=lambda msg: _on_main_thread(lambda: notify(msg)),
        on_state=lambda state: _on_main_thread(lambda: tray_ref["tray"].set_state(state)),
        run_async=True,
    )

    listener_ref = {"listener": None}

    def restart_listener():
        if listener_ref["listener"]:
            listener_ref["listener"].stop()
        lis = HotkeyListener(
            config.hotkey, config.trigger_mode,
            on_start=lambda: _on_main_thread(controller.start_recording),
            on_stop=lambda: _on_main_thread(controller.stop_and_transcribe),
        )
        lis.start()
        listener_ref["listener"] = lis

    def on_save(cfg: MacConfig):
        cfg.save(MAC_CONFIG_PATH)
        recorder.device = cfg.input_device
        if transcriber.ensure_current():
            notify("Model will reload on your next dictation.")
        restart_listener()
        notify("Settings saved.")

    def open_settings():
        if window_ref["win"] is None:
            window_ref["win"] = MainWindow(config, history, on_save)
        window_ref["win"].setCurrentIndex(0)
        window_ref["win"].show()
        window_ref["win"].raise_()
        window_ref["win"].activateWindow()

    def open_history():
        open_settings()
        window_ref["win"].setCurrentIndex(1)

    def on_language_change(code: str):
        config.language = code
        config.save(MAC_CONFIG_PATH)

    tray_ref["tray"] = Tray(
        config,
        on_language_change=on_language_change,
        open_settings=open_settings,
        open_history=open_history,
        quit_fn=app.quit,
    )

    restart_listener()

    threading.Thread(target=lambda: _safe_warm(transcriber, notify),
                     daemon=True).start()

    return app.exec()


def _safe_warm(transcriber: Transcriber, notify) -> None:
    try:
        if _model_is_cached(transcriber.config.model):
            _on_main_thread(lambda: notify("Loading model…"))
        else:
            _on_main_thread(lambda: notify(
                "Downloading model (~1.5 GB, one time)…"))
        transcriber.load()
        if transcriber.used_fallback and transcriber.active_mode:
            model, device, compute_type = transcriber.active_mode
            msg = f"Using {model} on {device} ({compute_type})."
            _on_main_thread(lambda m=msg: notify(m))
    except Exception as exc:
        msg = f"Model load failed: {exc}"
        _on_main_thread(lambda m=msg: notify(m))


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 6: Verify the entry point imports cleanly**

On macOS (or the dev box with PySide6 installed):

Run: `QT_QPA_PLATFORM=offscreen python -c "import wisprclone_mac.__main__; print('import ok')"`
Expected: `import ok` (no exception). This confirms all cross-package imports resolve and no platform-only import leaked to module top.

- [ ] **Step 7: Run the full Mac suite**

Run: `python -m pytest tests/mac -q`
Expected: PASS (on Windows: single_instance tests skipped; all others pass).

- [ ] **Step 8: Commit**

```bash
git add wisprclone_mac/notice.py wisprclone_mac/__main__.py tests/mac/test_notice.py
git commit -m "feat(mac): entry point wiring + Ctrl->Cmd notice rewrite"
```

---

### Task 6: Packaging — `macbuild/`

**Files:**
- Create: `macbuild/entry.py`
- Create: `macbuild/requirements-build-mac.txt`
- Create: `macbuild/wisprclone-mac.spec`
- Create: `macbuild/build.sh`

**Interfaces:** none (build tooling). This task has no unit test — its deliverable is a `.app`/`.dmg`, verified by running `build.sh` on an Apple Silicon Mac (part of the manual smoke, Task 8).

- [ ] **Step 1: Create the frozen entry point**

Create `macbuild/entry.py`:

```python
import sys

from wisprclone_mac.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Create the build requirements (pinned)**

Create `macbuild/requirements-build-mac.txt`:

```
faster-whisper==1.2.1
ctranslate2==4.8.0
sounddevice==0.5.5
numpy==2.4.4
pynput==1.8.2
PySide6==6.11.1
pyobjc-framework-Cocoa==11.1
pyobjc-framework-Quartz==11.1
pyobjc-framework-ApplicationServices==11.1
huggingface_hub==1.21.0
hf_xet==1.5.1
av==18.0.0
pyinstaller==6.21.0
pyinstaller-hooks-contrib==2026.6
```

Note for the implementer: if `pip install` resolves a different PySide6 patch than 6.11.1 on the build Mac, update BOTH this pin and `LSMinimumSystemVersion` in the spec to match that wheel's macOS floor, so the min-version claim stays truthful.

- [ ] **Step 3: Create the PyInstaller spec**

Create `macbuild/wisprclone-mac.spec`:

```python
# -*- mode: python ; coding: utf-8 -*-
import os

from PyInstaller.utils.hooks import collect_data_files

# PyInstaller resolves relative paths against the spec dir (SPECPATH), not cwd.
here = SPECPATH                  # …/macbuild
repo = os.path.dirname(here)     # repo root: holds wisprclone/ and wisprclone_mac/

datas = collect_data_files("faster_whisper")  # Silero VAD asset, etc.

a = Analysis(
    [os.path.join(here, "entry.py")],
    pathex=[repo],
    binaries=[],
    datas=datas,
    hiddenimports=["hf_xet"],
    excludes=["onnxruntime", "pytest", "tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True,
    name="WisprClone", console=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="WisprClone")
app = BUNDLE(
    coll,
    name="WisprClone.app",
    icon=None,
    bundle_identifier="com.wisprclone.mac",
    info_plist={
        "LSUIElement": True,                       # menu-bar/tray-only agent
        "NSMicrophoneUsageDescription":
            "WisprClone records your voice to transcribe it into text.",
        "LSMinimumSystemVersion": "12.0",
        "CFBundleShortVersionString": "1.0.0",
        "CFBundleVersion": "1.0.0",
    },
)
```

- [ ] **Step 4: Create the build script**

Create `macbuild/build.sh`:

```bash
#!/usr/bin/env bash
# Build WisprClone.app + WisprClone.dmg on Apple Silicon macOS.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="$(dirname "$here")"
cd "$repo"

venv=".venv-build-mac"
rm -rf "$venv"
python3 -m venv "$venv"
py="$venv/bin/python"

"$py" -m pip install --upgrade pip
"$py" -m pip install -r macbuild/requirements-build-mac.txt

rm -rf build dist
"$py" -m PyInstaller --clean --noconfirm macbuild/wisprclone-mac.spec

test -d "dist/WisprClone.app" || { echo "PyInstaller output missing"; exit 1; }

# Stable self-signed identity so TCC (Accessibility/Input Monitoring/Mic) grants
# survive rebuilds. Create it once in Keychain Access (login keychain) as a
# code-signing certificate named exactly "WisprClone Self-Signed", or override
# via WISPRCLONE_CODESIGN_ID. Falls back to ad-hoc "-" (permissions re-prompt
# every build) so the build still succeeds without a cert.
identity="${WISPRCLONE_CODESIGN_ID:-WisprClone Self-Signed}"
if security find-identity -v -p codesigning | grep -q "$identity"; then
  sign="$identity"
else
  echo "WARNING: signing identity '$identity' not found; using ad-hoc (-)." >&2
  echo "         TCC permissions will re-prompt on every rebuild." >&2
  sign="-"
fi
codesign --force --deep --options runtime \
  --identifier com.wisprclone.mac \
  --sign "$sign" "dist/WisprClone.app"

# Build the .dmg with hdiutil (no create-dmg/Homebrew dependency).
rm -f dist/WisprClone.dmg
staging="$(mktemp -d)"
cp -R "dist/WisprClone.app" "$staging/"
ln -s /Applications "$staging/Applications"
hdiutil create -volname "WisprClone" -srcfolder "$staging" -ov \
  -format UDZO "dist/WisprClone.dmg"
rm -rf "$staging"

echo "Built dist/WisprClone.dmg"
echo "Unsigned/self-signed: first launch, open via System Settings ->"
echo "Privacy & Security -> Open Anyway, then grant Accessibility, Input"
echo "Monitoring, and Microphone, and relaunch."
```

- [ ] **Step 5: Make the script executable and commit**

```bash
chmod +x macbuild/build.sh
git add macbuild/
git commit -m "build(mac): PyInstaller .app spec + self-signed .dmg build script"
```

(The actual build is run on an Apple Silicon Mac during the Task 8 smoke; do not attempt it on Windows.)

---

### Task 7: macOS CI job

**Files:**
- Modify: `.github/workflows/ci.yml`

**Interfaces:** none. Adds a second job; leaves the existing `test` (windows-latest) job untouched.

- [ ] **Step 1: Add the macOS job**

Append this job under `jobs:` in `.github/workflows/ci.yml` (do not modify the existing `test` job):

```yaml
  test-macos:
    runs-on: macos-latest   # Apple Silicon
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install test dependencies
        # pynput pulls the pyobjc frameworks transitively on macOS; PySide6 is
        # needed only for the entry-point import-smoke. faster-whisper is NOT
        # installed (imported lazily; exercised in the manual smoke checklist).
        run: python -m pip install --upgrade pip numpy pynput sounddevice pytest PySide6

      - name: Verify pyobjc frameworks resolve
        run: python -c "import AppKit, Quartz, ApplicationServices; print('pyobjc ok')"

      - name: Run tests
        run: python -m pytest -q

      - name: Entry-point import smoke
        env:
          QT_QPA_PLATFORM: offscreen
        run: python -c "import wisprclone_mac.__main__; print('import ok')"
```

- [ ] **Step 2: Validate YAML locally**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('yaml ok')"`
Expected: `yaml ok` (install PyYAML first if needed: `pip install pyyaml`).

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci(mac): add macos-latest job (tests + pyobjc + import smoke)"
```

- [ ] **Step 4: Push the branch and confirm CI is green**

```bash
git push -u origin macos-port
```
Then confirm both `test` and `test-macos` jobs pass on the pushed branch before proceeding.

---

### Task 8: Docs + manual smoke checklist

**Files:**
- Create: `docs/superpowers/mac-smoke-checklist.md`
- Modify: `README.md` (append a "macOS (Apple Silicon)" section)

**Interfaces:** none.

- [ ] **Step 1: Write the manual smoke checklist**

Create `docs/superpowers/mac-smoke-checklist.md`:

```markdown
# WisprClone macOS Manual Smoke Checklist

Run on an Apple Silicon Mac. CI cannot cover TCC/mic/paste — this is that gate.

## From source (do this first)
1. `python3 -m venv .venv && source .venv/bin/activate`
2. `pip install -r requirements-mac.txt`
3. `python -m wisprclone_mac`
4. On first launch a permissions dialog lists Accessibility + Input Monitoring.
   Grant both in System Settings -> Privacy & Security (and Microphone when
   prompted), then relaunch.
5. Tray dot icon appears; no Dock icon expected only for the .app build (from
   source a Dock icon is normal).
6. Hold Right Option, speak English -> text pastes into the focused app; the
   previous clipboard is restored afterward.
7. Repeat in Hebrew (tray Language -> Hebrew or Auto) -> Hebrew pastes correctly
   (verifies NSPasteboard Unicode).
8. Turn OFF Accessibility, dictate -> you get a "Copied to clipboard - press
   Cmd+V to paste." notice and the text is on the clipboard (NOT lost). Re-grant.
9. Launch a second `python -m wisprclone_mac` -> it exits immediately (single
   instance); no double paste.
10. Settings: change model/mic/hotkey, Save -> persists across restart
    (`~/Library/Application Support/wisprclone/config.json`).

## Packaged .app / .dmg
11. `bash macbuild/build.sh` -> produces `dist/WisprClone.dmg`.
12. Open the .dmg, drag WisprClone to Applications. First launch: right-click ->
    Open, or System Settings -> Privacy & Security -> Open Anyway (unsigned).
13. Grant Accessibility + Input Monitoring + Microphone; relaunch.
14. Repeat steps 6-10 against the installed .app. Confirm NO Dock icon
    (LSUIElement) and the mic prompt shows the usage string.
15. Rebuild with `build.sh` and relaunch -> permissions are NOT re-prompted
    (confirms the stable self-signed identity + fixed bundle id).
```

- [ ] **Step 2: Append the README section**

Add to `README.md` (after the existing Windows content — do not remove anything):

```markdown
## macOS (Apple Silicon)

Run from source:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-mac.txt
python -m wisprclone_mac
```

On first launch, grant **Accessibility**, **Input Monitoring**, and
**Microphone** in System Settings → Privacy & Security, then relaunch. Default
push-to-talk is **Right Option**; default model is **medium** on CPU.

Build an app bundle + disk image (on an Apple Silicon Mac):

```bash
bash macbuild/build.sh    # -> dist/WisprClone.dmg
```

The `.app` is unsigned/self-signed: on first launch use right-click → Open (or
System Settings → Privacy & Security → Open Anyway). See
`docs/superpowers/mac-smoke-checklist.md` for the full manual test.
```

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/mac-smoke-checklist.md README.md
git commit -m "docs(mac): manual smoke checklist + README macOS section"
```

---

## Self-Review

**Spec coverage** — every spec section maps to a task:
- §2 shared/neutral reuse → imports in Task 5's `__main__`; base-degradation guard test in Task 1.
- §3.1 MacPaster (NSPasteboard, Accessibility gate, changeCount, non-text=None, Cmd+V) → Task 4.
- §3.2 flock single-instance → Task 2.
- §3.3 MacConfig (paths + cpu/int8/medium/alt_r, load/save overrides) → Task 1.
- §3.4 permission preflight (two distinct APIs, relaunch copy) → Task 3; QMessageBox wiring + ordering (QApplication before preflight) → Task 5.
- §3.5 entry point (stderr tee, Ctrl→Cmd, ~1.5 GB string, no CUDA) → Task 5 + `notice.py`.
- §3.6 requirements-mac.txt with declared pyobjc frameworks → Task 1.
- §4 packaging (spec, fixed bundle id, LSUIElement, mic usage string, min-OS, stable self-signed identity, hdiutil) → Task 6.
- §5 tests + macos-latest CI with offscreen + pyobjc check → Tasks 1–5 + Task 7.
- §6 tradeoffs (Ctrl→Cmd wrapper, invoker duplication) → Task 5.
- §7 process/prereqs (fixed bundle id, restore contract, API mapping, pyobjc decision, tests run on dev box) → all locked above.

**Placeholder scan** — no TBD/TODO; every code step contains complete code; no "handle edge cases" hand-waves.

**Type consistency** — `MacConfig`, `MAC_APP_DIR`, `MAC_CONFIG_PATH`, `SingleInstance(lock_path).acquire()`, `MacPaster(pasteboard, sender, trust_check, sleep).paste_text/copy_only`, `accessibility_ok`/`input_monitoring_ok`/`missing_permissions`/`permission_message`/`preflight`, and `format_notice` are used with identical names/signatures across Tasks 1–7. `MacPaster` satisfies the `paster.paste_text(text)->bool` / `paster.copy_only(text)` contract `AppController` calls in `wisprclone/app.py`.
