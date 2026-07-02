# WisprClone Windows Dictation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a minimal Windows tray app that transcribes speech to text locally (English + Hebrew) on a global push-to-talk hotkey and pastes the result into the focused field.

**Architecture:** A single Qt event loop owns the tray icon and windows. A background `pynput` listener detects the (user-configurable) hotkey; audio capture (`sounddevice`) and transcription (`faster-whisper`) run off the main thread. A framework-agnostic `AppController` state machine (idle→recording→transcribing→idle) wires the pieces and is fully unit-testable with injected fakes.

**Tech Stack:** Python 3.10+, faster-whisper, sounddevice, numpy, pynput, PySide6, pywin32, pytest.

## Global Constraints

- **Python 3.10+** (uses `X | None` and `list[...]` annotations).
- **Windows-only** runtime (paste + elevation checks are Win32).
- Transcription models are **multilingual only**; default `large-v3`. Never offer `.en` or `distil-*` variants (they break Hebrew).
- **Never log transcript or clipboard content** to console or file. App logs may record events/errors only.
- GPU default: `device="cuda"`, `compute_type="float16"`. On CUDA failure fall back to `device="cpu"`, `compute_type="int8"`, `model="base"`.
- Language default `"auto"` → passed to faster-whisper as `language=None`.
- A hotkey is a **set of key tokens** serialized to a canonical `"+"`-joined sorted string (e.g. `"ctrl_r"`, `"alt_l+ctrl_l+space"`).
- All user data lives under `%APPDATA%\wisprclone\` (`config.json`, `history.json`).
- Every module uses relative imports within the `wisprclone` package.

---

### Task 1: Project scaffold + `config.py`

**Files:**
- Create: `wisprclone/__init__.py` (empty)
- Create: `wisprclone/config.py`
- Create: `requirements.txt`
- Create: `pytest.ini`
- Test: `tests/test_config.py`
- Create: `tests/__init__.py` (empty)

**Interfaces:**
- Produces: `Config` dataclass with fields `hotkey: str`, `trigger_mode: str`, `input_device: str | None`, `model: str`, `device: str`, `compute_type: str`, `language: str`, `vocab_hint: str`, `remove_fillers: bool`, `auto_paste: bool`, `history_cap: int`. Classmethod `Config.load(path=CONFIG_PATH) -> Config`; method `save(path=CONFIG_PATH) -> None`. Module constants `APP_DIR: Path`, `CONFIG_PATH: Path`.

- [ ] **Step 1: Create `requirements.txt`**

```
faster-whisper>=1.0.0
sounddevice>=0.4.6
numpy>=1.24
pynput>=1.7.6
PySide6>=6.6.0
pywin32>=306
nvidia-cublas-cu12
nvidia-cudnn-cu12
pytest>=8.0
```

- [ ] **Step 2: Create `pytest.ini`**

```ini
[pytest]
testpaths = tests
```

- [ ] **Step 3: Create empty package files**

Create `wisprclone/__init__.py` and `tests/__init__.py`, both empty.

- [ ] **Step 4: Write the failing test** — `tests/test_config.py`

```python
import json
from wisprclone.config import Config


def test_defaults():
    c = Config()
    assert c.hotkey == "ctrl_r"
    assert c.trigger_mode == "hold"
    assert c.model == "large-v3"
    assert c.device == "cuda"
    assert c.compute_type == "float16"
    assert c.language == "auto"
    assert c.vocab_hint == ""
    assert c.remove_fillers is False
    assert c.auto_paste is True
    assert c.history_cap == 100
    assert c.input_device is None


def test_save_load_roundtrip(tmp_path):
    p = tmp_path / "config.json"
    c = Config(hotkey="alt_l+space", language="he", vocab_hint="report, PayPal")
    c.save(p)
    loaded = Config.load(p)
    assert loaded.hotkey == "alt_l+space"
    assert loaded.language == "he"
    assert loaded.vocab_hint == "report, PayPal"


def test_load_missing_returns_defaults(tmp_path):
    loaded = Config.load(tmp_path / "nope.json")
    assert loaded.hotkey == "ctrl_r"


def test_load_corrupt_returns_defaults(tmp_path):
    p = tmp_path / "config.json"
    p.write_text("{ not valid json", encoding="utf-8")
    assert Config.load(p).model == "large-v3"


def test_load_ignores_unknown_keys(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"hotkey": "f13", "legacy_field": 1}), encoding="utf-8")
    loaded = Config.load(p)
    assert loaded.hotkey == "f13"
```

- [ ] **Step 5: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'wisprclone.config'`).

- [ ] **Step 6: Implement `wisprclone/config.py`**

```python
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

APP_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "wisprclone"
CONFIG_PATH = APP_DIR / "config.json"


@dataclass
class Config:
    hotkey: str = "ctrl_r"
    trigger_mode: str = "hold"          # "hold" | "toggle"
    input_device: str | None = None     # None = system default input
    model: str = "large-v3"             # multilingual only
    device: str = "cuda"                # "cuda" | "cpu"
    compute_type: str = "float16"       # "float16" | "int8"
    language: str = "auto"              # "auto" | "en" | "he"
    vocab_hint: str = ""
    remove_fillers: bool = False        # English-only filler removal
    auto_paste: bool = True
    history_cap: int = 100

    @classmethod
    def load(cls, path: Path = CONFIG_PATH) -> "Config":
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            known = {k: data[k] for k in cls.__dataclass_fields__ if k in data}
            return cls(**known)
        except (FileNotFoundError, json.JSONDecodeError, TypeError, ValueError):
            return cls()

    def save(self, path: Path = CONFIG_PATH) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
```

- [ ] **Step 7: Run test to verify it passes**

Run: `python -m pytest tests/test_config.py -v`
Expected: PASS (5 passed).

- [ ] **Step 8: Commit**

```bash
git add requirements.txt pytest.ini wisprclone/__init__.py wisprclone/config.py tests/__init__.py tests/test_config.py
git commit -m "feat: project scaffold and config module"
```

---

### Task 2: `textcleanup.py`

**Files:**
- Create: `wisprclone/textcleanup.py`
- Test: `tests/test_textcleanup.py`

**Interfaces:**
- Produces: `clean_text(raw: str, remove_fillers: bool = False) -> str`.

- [ ] **Step 1: Write the failing test** — `tests/test_textcleanup.py`

```python
from wisprclone.textcleanup import clean_text


def test_strips_bracketed_noise_tags():
    assert clean_text("hello [BLANK_AUDIO] world") == "hello world"
    assert clean_text("hi (music) there") == "hi there"


def test_strips_nospeech_token():
    assert clean_text("text <|nospeech|> more") == "text more"


def test_collapses_whitespace():
    assert clean_text("a    b\n\nc") == "a b c"


def test_fillers_removed_when_enabled():
    assert clean_text("so um this uh works", remove_fillers=True) == "so this works"


def test_fillers_kept_when_disabled():
    assert clean_text("so um this works", remove_fillers=False) == "so um this works"


def test_space_before_punctuation_fixed_when_fillers_enabled():
    assert clean_text("hello um , world", remove_fillers=True) == "hello, world"


def test_hebrew_passes_through_unchanged():
    hebrew = "שלום עולם מה שלומך"
    assert clean_text(hebrew) == hebrew


def test_trims_and_returns_empty_for_noise_only():
    assert clean_text("  [SILENCE]  ") == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_textcleanup.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `wisprclone/textcleanup.py`**

```python
import re

_NOISE_TERMS = (
    "BLANK_AUDIO|SILENCE|music|applause|laughter|laughing|noise|inaudible|"
    "indistinct|coughing|cough|breathing|inhale|exhale|sigh|sighs|wind|static|"
    "background noise|unintelligible"
)
_NOISE_TAGS = re.compile(r"[\[\(]\s*(?:" + _NOISE_TERMS + r")\s*[\]\)]", re.IGNORECASE)
_NOSPEECH = re.compile(r"<\|nospeech\|>")
_FILLERS = re.compile(
    r"(?i)(^|[\s,.;:!?])(?:uh+|um+|umm+|uhm+|erm+|hmm+)(?=$|[\s,.;:!?])[,.;:!?]?"
)
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([,.;:!?])")
_MULTISPACE = re.compile(r"\s+")


def clean_text(raw: str, remove_fillers: bool = False) -> str:
    text = _NOSPEECH.sub(" ", raw)
    text = _NOISE_TAGS.sub(" ", text)
    if remove_fillers:
        text = _FILLERS.sub(r"\1", text)
        text = _SPACE_BEFORE_PUNCT.sub(r"\1", text)
    text = _MULTISPACE.sub(" ", text)
    return text.strip()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_textcleanup.py -v`
Expected: PASS (8 passed).

- [ ] **Step 5: Commit**

```bash
git add wisprclone/textcleanup.py tests/test_textcleanup.py
git commit -m "feat: language-agnostic transcript cleanup"
```

---

### Task 3: `history.py`

**Files:**
- Create: `wisprclone/history.py`
- Test: `tests/test_history.py`

**Interfaces:**
- Produces: `HistoryEntry` dataclass (`text: str`, `timestamp: str`, `duration: float`, `language: str`, `model: str`). `HistoryStore(path: Path, cap: int = 100)` with `entries: list[HistoryEntry]`, `add(entry: HistoryEntry) -> None`, `clear() -> None`.

- [ ] **Step 1: Write the failing test** — `tests/test_history.py`

```python
from wisprclone.history import HistoryEntry, HistoryStore


def _entry(text):
    return HistoryEntry(text=text, timestamp="2026-07-02T10:00:00",
                        duration=1.0, language="en", model="large-v3")


def test_add_prepends_newest_first(tmp_path):
    store = HistoryStore(tmp_path / "h.json")
    store.add(_entry("first"))
    store.add(_entry("second"))
    assert [e.text for e in store.entries] == ["second", "first"]


def test_cap_prunes_oldest(tmp_path):
    store = HistoryStore(tmp_path / "h.json", cap=2)
    for t in ["a", "b", "c"]:
        store.add(_entry(t))
    assert [e.text for e in store.entries] == ["c", "b"]


def test_persistence_roundtrip(tmp_path):
    p = tmp_path / "h.json"
    HistoryStore(p).add(_entry("שלום"))
    reloaded = HistoryStore(p)
    assert reloaded.entries[0].text == "שלום"


def test_clear(tmp_path):
    p = tmp_path / "h.json"
    store = HistoryStore(p)
    store.add(_entry("x"))
    store.clear()
    assert store.entries == []
    assert HistoryStore(p).entries == []


def test_corrupt_file_loads_empty(tmp_path):
    p = tmp_path / "h.json"
    p.write_text("garbage", encoding="utf-8")
    assert HistoryStore(p).entries == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_history.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `wisprclone/history.py`**

```python
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class HistoryEntry:
    text: str
    timestamp: str      # ISO 8601
    duration: float
    language: str
    model: str


class HistoryStore:
    def __init__(self, path: Path, cap: int = 100):
        self.path = Path(path)
        self.cap = cap
        self.entries: list[HistoryEntry] = self._load()

    def _load(self) -> list[HistoryEntry]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return [HistoryEntry(**e) for e in data]
        except (FileNotFoundError, json.JSONDecodeError, TypeError, ValueError):
            return []

    def add(self, entry: HistoryEntry) -> None:
        self.entries.insert(0, entry)
        del self.entries[self.cap:]
        self._save()

    def clear(self) -> None:
        self.entries = []
        self._save()

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps([asdict(e) for e in self.entries], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_history.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add wisprclone/history.py tests/test_history.py
git commit -m "feat: capped local transcription history"
```

---

### Task 4: `hotkey.py` (key-set model, listener, capture)

**Files:**
- Create: `wisprclone/hotkey.py`
- Test: `tests/test_hotkey.py`

**Interfaces:**
- Produces:
  - `key_token(key) -> str` — normalizes a pynput key (or any object with `.name`/`.char`) to a lowercase token.
  - `parse_hotkey(s: str) -> frozenset[str]`
  - `format_hotkey(tokens) -> str` — canonical `"+"`-joined sorted string.
  - `HotkeyListener(hotkey_str, trigger_mode, on_start, on_stop)` with `press(key)`, `release(key)`, `start()`, `stop()`.
  - `HotkeyCapture(on_captured)` with `press(key)`, `release(key)`, `start()`, `stop()`.

**Note:** `press`/`release` are the testable core; `start`/`stop` just attach a real `pynput.keyboard.Listener` that forwards to them.

- [ ] **Step 1: Write the failing test** — `tests/test_hotkey.py`

```python
from wisprclone.hotkey import (
    HotkeyCapture,
    HotkeyListener,
    format_hotkey,
    key_token,
    parse_hotkey,
)


class FakeKey:
    """Stand-in for pynput Key/KeyCode."""
    def __init__(self, name=None, char=None):
        self.name = name
        self.char = char


def test_key_token_from_named_key():
    assert key_token(FakeKey(name="ctrl_r")) == "ctrl_r"


def test_key_token_from_char():
    assert key_token(FakeKey(char="V")) == "v"


def test_parse_and_format_roundtrip():
    assert parse_hotkey("alt_l+ctrl_l+space") == frozenset({"alt_l", "ctrl_l", "space"})
    assert format_hotkey({"space", "ctrl_l", "alt_l"}) == "alt_l+ctrl_l+space"


def test_hold_mode_fires_start_then_stop():
    events = []
    lis = HotkeyListener("ctrl_r", "hold",
                         on_start=lambda: events.append("start"),
                         on_stop=lambda: events.append("stop"))
    lis.press(FakeKey(name="ctrl_r"))
    lis.press(FakeKey(name="ctrl_r"))   # auto-repeat must not re-fire
    lis.release(FakeKey(name="ctrl_r"))
    assert events == ["start", "stop"]


def test_hold_mode_combo_requires_all_keys():
    events = []
    lis = HotkeyListener("alt_l+space", "hold",
                         on_start=lambda: events.append("start"),
                         on_stop=lambda: events.append("stop"))
    lis.press(FakeKey(name="alt_l"))
    assert events == []                 # not covered yet
    lis.press(FakeKey(name="space"))
    assert events == ["start"]          # covered now
    lis.release(FakeKey(name="space"))
    assert events == ["start", "stop"]  # releasing any target key stops


def test_toggle_mode_flips_on_each_full_press():
    events = []
    lis = HotkeyListener("ctrl_r", "toggle",
                         on_start=lambda: events.append("start"),
                         on_stop=lambda: events.append("stop"))
    lis.press(FakeKey(name="ctrl_r"))
    lis.release(FakeKey(name="ctrl_r"))
    lis.press(FakeKey(name="ctrl_r"))
    lis.release(FakeKey(name="ctrl_r"))
    assert events == ["start", "stop"]


def test_capture_records_maximal_combo():
    captured = []
    cap = HotkeyCapture(on_captured=captured.append)
    cap.press(FakeKey(name="ctrl_l"))
    cap.press(FakeKey(name="alt_l"))
    cap.release(FakeKey(name="alt_l"))
    cap.release(FakeKey(name="ctrl_l"))
    assert captured == ["alt_l+ctrl_l"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_hotkey.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `wisprclone/hotkey.py`**

```python
from __future__ import annotations

from typing import Callable, Iterable

from pynput import keyboard


def key_token(key) -> str:
    name = getattr(key, "name", None)
    if name:
        return str(name).lower()
    char = getattr(key, "char", None)
    if char:
        return str(char).lower()
    return str(key).lower()


def parse_hotkey(s: str) -> frozenset[str]:
    return frozenset(t.strip().lower() for t in s.split("+") if t.strip())


def format_hotkey(tokens: Iterable[str]) -> str:
    return "+".join(sorted(tokens))


class HotkeyListener:
    def __init__(self, hotkey_str: str, trigger_mode: str,
                 on_start: Callable[[], None], on_stop: Callable[[], None]):
        self.target = parse_hotkey(hotkey_str)
        self.trigger_mode = trigger_mode
        self.on_start = on_start
        self.on_stop = on_stop
        self._held: set[str] = set()
        self._active = False
        self._was_covered = False
        self._listener = None

    def _covered(self) -> bool:
        return bool(self.target) and self.target <= self._held

    def press(self, key) -> None:
        self._held.add(key_token(key))
        if self._covered() and not self._was_covered:
            self._was_covered = True
            if self.trigger_mode == "hold":
                self._active = True
                self.on_start()
            else:  # toggle
                self._active = not self._active
                (self.on_start if self._active else self.on_stop)()

    def release(self, key) -> None:
        self._held.discard(key_token(key))
        if not self._covered() and self._was_covered:
            self._was_covered = False
            if self.trigger_mode == "hold" and self._active:
                self._active = False
                self.on_stop()

    def start(self) -> None:
        self._listener = keyboard.Listener(on_press=self.press, on_release=self.release)
        self._listener.start()

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()
            self._listener = None


class HotkeyCapture:
    def __init__(self, on_captured: Callable[[str], None]):
        self.on_captured = on_captured
        self._held: set[str] = set()
        self._max: set[str] = set()
        self._listener = None

    def press(self, key) -> None:
        self._held.add(key_token(key))
        if len(self._held) > len(self._max):
            self._max = set(self._held)

    def release(self, key) -> None:
        self._held.discard(key_token(key))
        if not self._held and self._max:
            captured = format_hotkey(self._max)
            self._max = set()
            self.on_captured(captured)
            self.stop()

    def start(self) -> None:
        self._listener = keyboard.Listener(on_press=self.press, on_release=self.release)
        self._listener.start()

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()
            self._listener = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_hotkey.py -v`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
git add wisprclone/hotkey.py tests/test_hotkey.py
git commit -m "feat: configurable hotkey with combo-aware listener and capture"
```

---

### Task 5: `audio.py`

**Files:**
- Create: `wisprclone/audio.py`
- Test: `tests/test_audio.py`

**Interfaces:**
- Produces: `Recorder(device=None)` with class const `SAMPLE_RATE = 16000`, methods `start() -> None`, `stop() -> np.ndarray` (1-D float32, empty array if nothing captured), and internal `_callback(indata, frames, time_info, status)` used by the sounddevice stream.

**Note:** `start()`/`stop()` touch hardware; the unit test exercises buffer accumulation by driving `_callback` directly (no device needed, since `stop()` only touches the stream when one exists).

- [ ] **Step 1: Write the failing test** — `tests/test_audio.py`

```python
import numpy as np
from wisprclone.audio import Recorder


def test_empty_stop_returns_empty_float32():
    rec = Recorder()
    out = rec.stop()
    assert out.dtype == np.float32
    assert out.size == 0


def test_callback_frames_are_concatenated_and_flattened():
    rec = Recorder()
    rec._frames = []
    rec._callback(np.ones((100, 1), dtype=np.float32), 100, None, None)
    rec._callback(np.zeros((50, 1), dtype=np.float32), 50, None, None)
    out = rec.stop()
    assert out.shape == (150,)
    assert out.dtype == np.float32
    assert out[0] == 1.0 and out[-1] == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_audio.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `wisprclone/audio.py`**

```python
from __future__ import annotations

import numpy as np
import sounddevice as sd


class Recorder:
    SAMPLE_RATE = 16000

    def __init__(self, device: str | int | None = None):
        self.device = device
        self._frames: list[np.ndarray] = []
        self._stream = None

    def _callback(self, indata, frames, time_info, status) -> None:
        self._frames.append(indata.copy())

    def start(self) -> None:
        self._frames = []
        self._stream = sd.InputStream(
            samplerate=self.SAMPLE_RATE,
            channels=1,
            dtype="float32",
            device=self.device,
            callback=self._callback,
        )
        self._stream.start()

    def stop(self) -> np.ndarray:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        if not self._frames:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(self._frames, axis=0).flatten().astype(np.float32)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_audio.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add wisprclone/audio.py tests/test_audio.py
git commit -m "feat: microphone recorder capturing 16kHz mono float32"
```

---

### Task 6: `transcriber.py`

**Files:**
- Create: `wisprclone/transcriber.py`
- Test: `tests/test_transcriber.py`

**Interfaces:**
- Consumes: `Config` (Task 1), `clean_text` (Task 2).
- Produces: `Transcriber(config, model_factory=None)` with attributes `used_fallback: bool`, methods `load() -> None`, `transcribe(samples) -> str`. `model_factory` is a zero-arg callable returning an object with `transcribe(samples, language=..., initial_prompt=...) -> (segments_iterable, info)`, where each segment has a `.text` attribute. Default factory builds a real `faster_whisper.WhisperModel` from config; on any exception it mutates config to the CPU fallback (`device="cpu"`, `compute_type="int8"`, `model="base"`), sets `used_fallback=True`, and retries once.

- [ ] **Step 1: Write the failing test** — `tests/test_transcriber.py`

```python
from wisprclone.config import Config
from wisprclone.transcriber import Transcriber


class FakeSegment:
    def __init__(self, text):
        self.text = text


class FakeModel:
    def __init__(self):
        self.calls = []

    def transcribe(self, samples, language=None, initial_prompt=None):
        self.calls.append({"language": language, "initial_prompt": initial_prompt})
        return ([FakeSegment("hello "), FakeSegment("world")], object())


def test_auto_language_maps_to_none():
    model = FakeModel()
    t = Transcriber(Config(language="auto"), model_factory=lambda: model)
    t.transcribe([0.0])
    assert model.calls[0]["language"] is None


def test_explicit_language_passed_through():
    model = FakeModel()
    t = Transcriber(Config(language="he"), model_factory=lambda: model)
    t.transcribe([0.0])
    assert model.calls[0]["language"] == "he"


def test_vocab_hint_passed_as_initial_prompt():
    model = FakeModel()
    t = Transcriber(Config(vocab_hint="report, PayPal"), model_factory=lambda: model)
    t.transcribe([0.0])
    assert model.calls[0]["initial_prompt"] == "report, PayPal"


def test_empty_vocab_hint_becomes_none():
    model = FakeModel()
    t = Transcriber(Config(vocab_hint=""), model_factory=lambda: model)
    t.transcribe([0.0])
    assert model.calls[0]["initial_prompt"] is None


def test_result_is_joined_and_cleaned():
    t = Transcriber(Config(), model_factory=lambda: FakeModel())
    assert t.transcribe([0.0]) == "hello world"


def test_cuda_failure_falls_back_to_cpu():
    attempts = {"n": 0}

    def factory():
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise RuntimeError("CUDA unavailable")
        return FakeModel()

    cfg = Config(device="cuda", compute_type="float16", model="large-v3")
    t = Transcriber(cfg, model_factory=factory)
    t.load()
    assert t.used_fallback is True
    assert cfg.device == "cpu"
    assert cfg.compute_type == "int8"
    assert cfg.model == "base"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_transcriber.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `wisprclone/transcriber.py`**

```python
from __future__ import annotations

from typing import Callable, Optional

from .config import Config
from .textcleanup import clean_text


class Transcriber:
    def __init__(self, config: Config, model_factory: Optional[Callable[[], object]] = None):
        self.config = config
        self._model = None
        self.used_fallback = False
        self._model_factory = model_factory or self._default_factory

    def _default_factory(self):
        from faster_whisper import WhisperModel
        return WhisperModel(
            self.config.model,
            device=self.config.device,
            compute_type=self.config.compute_type,
        )

    def load(self) -> None:
        if self._model is not None:
            return
        try:
            self._model = self._model_factory()
        except Exception:
            self.config.device = "cpu"
            self.config.compute_type = "int8"
            self.config.model = "base"
            self.used_fallback = True
            self._model = self._model_factory()

    def transcribe(self, samples) -> str:
        self.load()
        language = None if self.config.language == "auto" else self.config.language
        initial_prompt = self.config.vocab_hint or None
        segments, _info = self._model.transcribe(
            samples,
            language=language,
            initial_prompt=initial_prompt,
        )
        raw = " ".join(seg.text for seg in segments)
        return clean_text(raw, remove_fillers=self.config.remove_fillers)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_transcriber.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add wisprclone/transcriber.py tests/test_transcriber.py
git commit -m "feat: faster-whisper transcriber with language routing and CPU fallback"
```

---

### Task 7: `paste.py`

**Files:**
- Create: `wisprclone/paste.py`
- Test: `tests/test_paste.py`

**Interfaces:**
- Produces:
  - `Paster(clipboard=None, sender=None, elevated_check=None)` with `paste_text(text: str) -> bool`. Returns `True` if it sent a synthetic paste, `False` if the foreground window is elevated (text left on clipboard for manual paste).
  - `clipboard` object needs `get_text() -> str | None` and `set_text(text: str) -> None`.
  - `sender` object needs `ctrl_v() -> None`.
  - `elevated_check` is a zero-arg callable `() -> bool`.
  - Concrete Win32 defaults: `Win32Clipboard`, `Win32Sender`, `foreground_is_elevated()`.

**Note:** `paste_text` branching is unit-tested with fakes. The Win32 concrete classes are covered by the manual smoke checklist (Task 10).

- [ ] **Step 1: Write the failing test** — `tests/test_paste.py`

```python
from wisprclone.paste import Paster


class FakeClipboard:
    def __init__(self, initial=None):
        self._text = initial
        self.history = []

    def get_text(self):
        return self._text

    def set_text(self, text):
        self._text = text
        self.history.append(text)


class FakeSender:
    def __init__(self):
        self.pasted = 0

    def ctrl_v(self):
        self.pasted += 1


def test_normal_paste_sends_ctrl_v_and_restores_clipboard():
    clip = FakeClipboard(initial="OLD")
    sender = FakeSender()
    p = Paster(clipboard=clip, sender=sender, elevated_check=lambda: False)
    assert p.paste_text("NEW") is True
    assert sender.pasted == 1
    assert clip.get_text() == "OLD"          # restored
    assert "NEW" in clip.history            # was set during paste


def test_elevated_target_skips_paste_and_leaves_text():
    clip = FakeClipboard(initial="OLD")
    sender = FakeSender()
    p = Paster(clipboard=clip, sender=sender, elevated_check=lambda: True)
    assert p.paste_text("NEW") is False
    assert sender.pasted == 0
    assert clip.get_text() == "NEW"          # left on clipboard for manual paste


def test_restore_skipped_when_no_previous_clipboard():
    clip = FakeClipboard(initial=None)
    p = Paster(clipboard=clip, sender=FakeSender(), elevated_check=lambda: False)
    p.paste_text("NEW")
    assert clip.get_text() == "NEW"          # nothing to restore to
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_paste.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `wisprclone/paste.py`**

```python
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
        time.sleep(0.05)
        if previous is not None and self.clipboard.get_text() == text:
            self.clipboard.set_text(previous)
        return True


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
    kernel32 = ctypes.windll.kernel32

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
    return kernel32.GetLastError() == ERROR_ACCESS_DENIED
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_paste.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add wisprclone/paste.py tests/test_paste.py
git commit -m "feat: clipboard-preserving paste with UIPI elevation fallback"
```

---

### Task 8: `app.py` (AppController state machine)

**Files:**
- Create: `wisprclone/app.py`
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: `Config` (Task 1); `Recorder` (Task 5) — `start()`, `stop()->samples`; `Transcriber` (Task 6) — `transcribe(samples)->str`; `Paster` (Task 7) — `paste_text(text)->bool`; `HistoryStore`/`HistoryEntry` (Task 3) — `add(entry)`.
- Produces: `AppController(config, recorder, transcriber, paster, history, notify=None, on_state=None, run_async=False)` with attributes `state: str` (`"idle"|"recording"|"transcribing"`), methods `start_recording() -> None`, `stop_and_transcribe() -> None`. `notify(message: str)` and `on_state(state: str)` are optional callables. With `run_async=False` transcription runs synchronously (used by tests); with `run_async=True` it runs on a `threading.Thread`.

- [ ] **Step 1: Write the failing test** — `tests/test_app.py`

```python
import numpy as np
from wisprclone.app import AppController
from wisprclone.config import Config


class FakeRecorder:
    def __init__(self, samples):
        self._samples = samples
        self.started = False

    def start(self):
        self.started = True

    def stop(self):
        return self._samples


class FakeTranscriber:
    def __init__(self, text, error=None):
        self._text = text
        self._error = error

    def transcribe(self, samples):
        if self._error:
            raise self._error
        return self._text


class FakePaster:
    def __init__(self, result=True):
        self.result = result
        self.pasted = []

    def paste_text(self, text):
        self.pasted.append(text)
        return self.result


class FakeHistory:
    def __init__(self):
        self.entries = []

    def add(self, entry):
        self.entries.append(entry)


def _controller(text="hello", samples=None, paste_result=True, error=None):
    samples = np.ones(16000, dtype=np.float32) if samples is None else samples
    notes = []
    states = []
    ctrl = AppController(
        Config(),
        FakeRecorder(samples),
        FakeTranscriber(text, error=error),
        FakePaster(result=paste_result),
        FakeHistory(),
        notify=notes.append,
        on_state=states.append,
        run_async=False,
    )
    return ctrl, notes, states


def test_happy_path_pastes_and_records_history():
    ctrl, notes, states = _controller(text="hello world")
    ctrl.start_recording()
    assert ctrl.state == "recording"
    ctrl.stop_and_transcribe()
    assert ctrl.state == "idle"
    assert ctrl.paster.pasted == ["hello world"]
    assert ctrl.history.entries[0].text == "hello world"
    assert states == ["recording", "transcribing", "idle"]


def test_empty_transcription_skips_paste_and_history():
    ctrl, notes, states = _controller(text="")
    ctrl.start_recording()
    ctrl.stop_and_transcribe()
    assert ctrl.paster.pasted == []
    assert ctrl.history.entries == []
    assert ctrl.state == "idle"


def test_elevated_paste_failure_notifies_user():
    ctrl, notes, states = _controller(text="hi", paste_result=False)
    ctrl.start_recording()
    ctrl.stop_and_transcribe()
    assert any("Ctrl+V" in n for n in notes)
    assert ctrl.history.entries[0].text == "hi"   # still logged


def test_transcription_error_notifies_and_returns_to_idle():
    ctrl, notes, states = _controller(error=RuntimeError("boom"))
    ctrl.start_recording()
    ctrl.stop_and_transcribe()
    assert ctrl.state == "idle"
    assert notes  # some error message surfaced
    assert ctrl.history.entries == []


def test_stop_without_recording_is_ignored():
    ctrl, notes, states = _controller()
    ctrl.stop_and_transcribe()   # never started
    assert ctrl.state == "idle"
    assert ctrl.paster.pasted == []


def test_double_start_stays_in_recording_once():
    ctrl, notes, states = _controller()
    ctrl.start_recording()
    ctrl.start_recording()
    assert states.count("recording") == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_app.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `wisprclone/app.py`**

```python
from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Callable, Optional

from .config import Config
from .history import HistoryEntry


class AppController:
    def __init__(self, config: Config, recorder, transcriber, paster, history,
                 notify: Optional[Callable[[str], None]] = None,
                 on_state: Optional[Callable[[str], None]] = None,
                 run_async: bool = False):
        self.config = config
        self.recorder = recorder
        self.transcriber = transcriber
        self.paster = paster
        self.history = history
        self._notify = notify or (lambda msg: None)
        self._on_state = on_state or (lambda state: None)
        self.run_async = run_async
        self.state = "idle"

    def _set_state(self, state: str) -> None:
        self.state = state
        self._on_state(state)

    def start_recording(self) -> None:
        if self.state != "idle":
            return
        self._set_state("recording")
        self.recorder.start()

    def stop_and_transcribe(self) -> None:
        if self.state != "recording":
            return
        samples = self.recorder.stop()
        self._set_state("transcribing")
        duration = float(len(samples)) / 16000.0
        if self.run_async:
            threading.Thread(target=self._do_transcribe, args=(samples, duration),
                             daemon=True).start()
        else:
            self._do_transcribe(samples, duration)

    def _do_transcribe(self, samples, duration: float) -> None:
        try:
            text = self.transcriber.transcribe(samples)
        except Exception as exc:  # never log transcript content; message only
            self._notify(f"Transcription failed: {exc}")
            self._set_state("idle")
            return

        if not text:
            self._set_state("idle")
            return

        pasted = self.paster.paste_text(text)
        if not pasted:
            self._notify("Copied to clipboard — press Ctrl+V to paste.")

        self.history.add(HistoryEntry(
            text=text,
            timestamp=datetime.now(timezone.utc).isoformat(),
            duration=duration,
            language=self.config.language,
            model=self.config.model,
        ))
        self._set_state("idle")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_app.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -v`
Expected: PASS (all tasks 1-8 green).

- [ ] **Step 6: Commit**

```bash
git add wisprclone/app.py tests/test_app.py
git commit -m "feat: AppController state machine wiring record/transcribe/paste/history"
```

---

### Task 9: Tray + Settings/History windows (`tray.py`, `windows.py`)

**Files:**
- Create: `wisprclone/windows.py`
- Create: `wisprclone/tray.py`
- (No unit test — Qt UI is verified via the Task 10 manual smoke checklist.)

**Interfaces:**
- Consumes: `Config`, `HistoryStore`, `HotkeyCapture`, `format_hotkey`, `AppController`, `sounddevice` device list.
- Produces:
  - `MainWindow(config, history, on_save)` — `QTabWidget` with Settings + History tabs. `on_save(config)` called when the user saves settings. Has `show_settings()` and `show_history()`.
  - `Tray(controller, config, history, on_language_change, open_settings, open_history, quit_fn)` — builds a `QSystemTrayIcon`; `set_state(state)` swaps the tooltip/icon; `notify(message)` shows a balloon.

- [ ] **Step 1: Implement `wisprclone/windows.py`**

```python
from __future__ import annotations

from typing import Callable

import sounddevice as sd
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QPushButton, QTabWidget, QTextEdit, QVBoxLayout, QWidget,
)

from .config import Config
from .history import HistoryStore
from .hotkey import HotkeyCapture

_MODELS = ["large-v3", "medium", "small", "base"]   # multilingual only
_LANGUAGES = [("Auto", "auto"), ("English", "en"), ("Hebrew", "he")]


def _input_device_names() -> list[str]:
    names = []
    try:
        for dev in sd.query_devices():
            if dev.get("max_input_channels", 0) > 0:
                names.append(dev["name"])
    except Exception:
        pass
    return names


class MainWindow(QTabWidget):
    def __init__(self, config: Config, history: HistoryStore,
                 on_save: Callable[[Config], None]):
        super().__init__()
        self.config = config
        self.history = history
        self.on_save = on_save
        self._capture = None
        self.setWindowTitle("WisprClone")
        self.resize(460, 420)
        self.addTab(self._build_settings(), "Settings")
        self.addTab(self._build_history(), "History")

    # --- Settings tab ---
    def _build_settings(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        row = QHBoxLayout()
        self.hotkey_label = QLabel(self.config.hotkey)
        set_btn = QPushButton("Set hotkey")
        set_btn.clicked.connect(self._begin_capture)
        row.addWidget(QLabel("Hotkey:"))
        row.addWidget(self.hotkey_label, 1)
        row.addWidget(set_btn)
        layout.addLayout(row)

        self.trigger_box = QComboBox()
        self.trigger_box.addItems(["hold", "toggle"])
        self.trigger_box.setCurrentText(self.config.trigger_mode)
        layout.addWidget(QLabel("Trigger mode:"))
        layout.addWidget(self.trigger_box)

        self.mic_box = QComboBox()
        self.mic_box.addItem("System default", None)
        for name in _input_device_names():
            self.mic_box.addItem(name, name)
        if self.config.input_device:
            i = self.mic_box.findData(self.config.input_device)
            if i >= 0:
                self.mic_box.setCurrentIndex(i)
        layout.addWidget(QLabel("Microphone:"))
        layout.addWidget(self.mic_box)

        self.model_box = QComboBox()
        self.model_box.addItems(_MODELS)
        self.model_box.setCurrentText(self.config.model)
        layout.addWidget(QLabel("Model (multilingual):"))
        layout.addWidget(self.model_box)

        self.lang_box = QComboBox()
        for label, code in _LANGUAGES:
            self.lang_box.addItem(label, code)
        i = self.lang_box.findData(self.config.language)
        self.lang_box.setCurrentIndex(max(0, i))
        layout.addWidget(QLabel("Language:"))
        layout.addWidget(self.lang_box)

        layout.addWidget(QLabel("Vocabulary hint (English terms you say in Hebrew):"))
        self.vocab_edit = QLineEdit(self.config.vocab_hint)
        layout.addWidget(self.vocab_edit)

        self.fillers_chk = QCheckBox("Remove English filler words (um, uh)")
        self.fillers_chk.setChecked(self.config.remove_fillers)
        layout.addWidget(self.fillers_chk)

        self.autopaste_chk = QCheckBox("Auto-paste after transcription")
        self.autopaste_chk.setChecked(self.config.auto_paste)
        layout.addWidget(self.autopaste_chk)

        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._save)
        layout.addWidget(save_btn)
        layout.addStretch(1)
        return w

    def _begin_capture(self) -> None:
        self.hotkey_label.setText("Press keys…")
        self._capture = HotkeyCapture(on_captured=self._on_captured)
        self._capture.start()

    def _on_captured(self, hotkey: str) -> None:
        # Called from the pynput thread; Qt label update is simple text, safe enough here.
        self.config.hotkey = hotkey
        self.hotkey_label.setText(hotkey)

    def _save(self) -> None:
        self.config.trigger_mode = self.trigger_box.currentText()
        self.config.input_device = self.mic_box.currentData()
        self.config.model = self.model_box.currentText()
        self.config.language = self.lang_box.currentData()
        self.config.vocab_hint = self.vocab_edit.text().strip()
        self.config.remove_fillers = self.fillers_chk.isChecked()
        self.config.auto_paste = self.autopaste_chk.isChecked()
        self.config.hotkey = self.hotkey_label.text()
        self.on_save(self.config)

    # --- History tab ---
    def _build_history(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        self.history_list = QListWidget()
        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self._refresh_history()
        self.history_list.currentRowChanged.connect(self._show_preview)

        btns = QHBoxLayout()
        copy_btn = QPushButton("Copy selected")
        copy_btn.clicked.connect(self._copy_selected)
        clear_btn = QPushButton("Clear all")
        clear_btn.clicked.connect(self._clear_history)
        btns.addWidget(copy_btn)
        btns.addWidget(clear_btn)

        layout.addWidget(self.history_list, 2)
        layout.addWidget(self.preview, 1)
        layout.addLayout(btns)
        return w

    def _refresh_history(self) -> None:
        self.history_list.clear()
        for e in self.history.entries:
            self.history_list.addItem(f"[{e.timestamp[:19]}] {e.text[:60]}")

    def _show_preview(self, row: int) -> None:
        if 0 <= row < len(self.history.entries):
            self.preview.setPlainText(self.history.entries[row].text)

    def _copy_selected(self) -> None:
        from PySide6.QtWidgets import QApplication
        row = self.history_list.currentRow()
        if 0 <= row < len(self.history.entries):
            QApplication.clipboard().setText(self.history.entries[row].text)

    def _clear_history(self) -> None:
        self.history.clear()
        self._refresh_history()
        self.preview.clear()

    def showEvent(self, event):  # refresh history each time the window is shown
        self._refresh_history()
        super().showEvent(event)
```

- [ ] **Step 2: Implement `wisprclone/tray.py`**

```python
from __future__ import annotations

from typing import Callable

from PySide6.QtGui import QAction, QActionGroup, QIcon, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

_STATE_TOOLTIP = {
    "idle": "WisprClone — ready",
    "recording": "WisprClone — recording…",
    "transcribing": "WisprClone — transcribing…",
}
_STATE_COLOR = {
    "idle": "#3e435e",
    "recording": "#fb2c36",
    "transcribing": "#fdc20e",
}


def _dot_icon(hex_color: str) -> QIcon:
    pix = QPixmap(16, 16)
    pix.fill(0)  # transparent
    from PySide6.QtGui import QColor, QPainter
    painter = QPainter(pix)
    painter.setBrush(QColor(hex_color))
    painter.setPen(QColor(hex_color))
    painter.drawEllipse(2, 2, 12, 12)
    painter.end()
    return QIcon(pix)


class Tray:
    def __init__(self, config, on_language_change: Callable[[str], None],
                 open_settings: Callable[[], None], open_history: Callable[[], None],
                 quit_fn: Callable[[], None]):
        self.config = config
        self.icon = QSystemTrayIcon(_dot_icon(_STATE_COLOR["idle"]))
        self.icon.setToolTip(_STATE_TOOLTIP["idle"])
        menu = QMenu()

        lang_menu = menu.addMenu("Language")
        group = QActionGroup(lang_menu)
        group.setExclusive(True)
        for label, code in [("Auto", "auto"), ("English", "en"), ("Hebrew", "he")]:
            act = QAction(label, lang_menu, checkable=True)
            act.setChecked(config.language == code)
            act.triggered.connect(lambda _checked, c=code: on_language_change(c))
            group.addAction(act)
            lang_menu.addAction(act)

        menu.addAction("Settings", open_settings)
        menu.addAction("History", open_history)
        menu.addSeparator()
        menu.addAction("Quit", quit_fn)
        self.icon.setContextMenu(menu)
        self.icon.show()

    def set_state(self, state: str) -> None:
        self.icon.setIcon(_dot_icon(_STATE_COLOR.get(state, _STATE_COLOR["idle"])))
        self.icon.setToolTip(_STATE_TOOLTIP.get(state, "WisprClone"))

    def notify(self, message: str) -> None:
        self.icon.showMessage("WisprClone", message, QSystemTrayIcon.Information, 4000)
```

- [ ] **Step 3: Confirm the package imports cleanly (headless)**

Run: `python -c "import wisprclone.tray, wisprclone.windows; print('ok')"`
Expected: prints `ok` (imports succeed; no window is shown).

- [ ] **Step 4: Commit**

```bash
git add wisprclone/windows.py wisprclone/tray.py
git commit -m "feat: system tray, settings and history windows"
```

---

### Task 10: Entry point, README, manual smoke checklist

**Files:**
- Create: `wisprclone/__main__.py`
- Create: `README.md`
- Modify: `docs/superpowers/plans/2026-07-02-wisprclone-windows-dictation.md` (check off the smoke items as run)

**Interfaces:**
- Consumes: everything. Wires `QApplication` → `Config.load()` → services → `AppController(run_async=True)` → `HotkeyListener` (real, via `start()`) → `Tray`. Marshals hotkey/worker callbacks onto the Qt thread with `QTimer.singleShot(0, ...)`.

- [ ] **Step 1: Implement `wisprclone/__main__.py`**

```python
from __future__ import annotations

import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from .app import AppController
from .audio import Recorder
from .config import CONFIG_PATH, Config
from .history import HistoryStore
from .hotkey import HotkeyListener
from .paste import Paster
from .tray import Tray
from .transcriber import Transcriber
from .windows import MainWindow


def _on_main_thread(fn):
    """Marshal a call from a background thread onto the Qt event loop."""
    QTimer.singleShot(0, fn)


def main() -> int:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # tray app keeps running with no window

    from .config import APP_DIR
    config = Config.load()
    history = HistoryStore(APP_DIR / "history.json", cap=config.history_cap)
    recorder = Recorder(device=config.input_device)
    transcriber = Transcriber(config)
    paster = Paster()

    window_ref = {"win": None}
    tray_ref = {"tray": None}

    controller = AppController(
        config, recorder, transcriber, paster, history,
        notify=lambda msg: _on_main_thread(lambda: tray_ref["tray"].notify(msg)),
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

    def on_save(cfg: Config):
        cfg.save(CONFIG_PATH)
        recorder.device = cfg.input_device
        restart_listener()
        tray_ref["tray"].notify("Settings saved.")

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
        config.save(CONFIG_PATH)

    tray_ref["tray"] = Tray(
        config,
        on_language_change=on_language_change,
        open_settings=open_settings,
        open_history=open_history,
        quit_fn=app.quit,
    )

    restart_listener()

    # Warm the model in the background so the first transcription isn't slow.
    import threading
    threading.Thread(target=lambda: _safe_warm(transcriber, tray_ref),
                     daemon=True).start()

    return app.exec()


def _safe_warm(transcriber: Transcriber, tray_ref) -> None:
    try:
        transcriber.load()
        if transcriber.used_fallback:
            _on_main_thread(lambda: tray_ref["tray"].notify(
                "GPU unavailable — using CPU (base model)."))
    except Exception as exc:
        _on_main_thread(lambda: tray_ref["tray"].notify(f"Model load failed: {exc}"))


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Write `README.md`**

```markdown
# WisprClone

Minimal, offline Windows dictation. Hold a hotkey, speak, and the text is
transcribed locally (English + Hebrew) and pasted into the focused field.

## Requirements
- Windows 10/11, Python 3.10+
- NVIDIA GPU recommended (CUDA). Falls back to CPU automatically.

## Install
```
pip install -r requirements.txt
```
First run downloads the `large-v3` model (~1.5 GB) once, then runs fully offline.

## Run
```
python -m wisprclone
```
A tray icon appears. Hold **Right Ctrl** (default) to dictate, release to paste.
Open **Settings** from the tray to set your own hotkey (single key or combo),
pick a microphone, choose a model, set the language, or add a vocabulary hint.

## Language
Default is auto-detect — one hotkey handles both English and Hebrew. Use the tray
**Language** menu to pin English or Hebrew if auto-detect misfires on short clips.
Mixing English words inside a Hebrew sentence is best-effort (a Whisper limitation);
the vocabulary hint improves recognition of the specific English terms you list.

## Tests
```
python -m pytest
```
```

- [ ] **Step 3: Run the full unit suite one more time**

Run: `python -m pytest -v`
Expected: PASS (all green).

- [ ] **Step 4: Manual smoke checklist** (requires a real Windows box with mic + GPU)

Run: `python -m wisprclone`, then verify:
- [ ] Tray icon appears; right-click shows Language / Settings / History / Quit.
- [ ] Hold Right Ctrl, say an English sentence, release → text pastes into Notepad.
- [ ] Say a Hebrew sentence → Hebrew text pastes correctly (RTL renders fine).
- [ ] Add a vocabulary hint (e.g. `report, PayPal`), speak a Hebrew sentence using those English words → they are recognized more reliably.
- [ ] Open Settings → "Set hotkey" → press Ctrl+Alt+Space → label updates → Save → new combo works.
- [ ] Switch tray Language to Hebrew → short Hebrew clips transcribe as Hebrew.
- [ ] Clipboard: copy something, dictate, confirm your original clipboard is restored after paste.
- [ ] Run app **without** a GPU (or force `device=cpu` in config) → tray notifies CPU fallback and still works.
- [ ] Focus an elevated (admin) window → dictate → tray shows "press Ctrl+V" and text is on the clipboard.
- [ ] History tab lists entries; Copy selected and Clear all work.

- [ ] **Step 5: Commit**

```bash
git add wisprclone/__main__.py README.md docs/superpowers/plans/2026-07-02-wisprclone-windows-dictation.md
git commit -m "feat: app entry point, README, and manual smoke checklist"
```

---

## Self-Review Notes

- **Spec coverage:** dictation loop (Tasks 5,6,7,8), configurable capture hotkey incl. combos (Task 4 + 9), English+Hebrew auto-detect + tray override (Tasks 6,9), vocab hint (Tasks 1,6,9), history (Tasks 3,9), settings UI (Task 9), clipboard restore + UIPI fallback (Task 7), CUDA→CPU fallback (Task 6 + 10), error handling (Tasks 6,7,8,10), tests (every logic task). Non-goals (licensing/trial/updater/telemetry) are absent by construction.
- **Placeholder scan:** no TBD/TODO; every code step has complete code.
- **Type consistency:** `HistoryEntry` fields, `AppController` ctor signature, `Paster.paste_text` bool return, `Transcriber.transcribe` signature, and hotkey token-set model are used identically across tasks.
```
