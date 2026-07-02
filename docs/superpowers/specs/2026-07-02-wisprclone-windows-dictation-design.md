# WisprClone — Windows Local Dictation App

**Date:** 2026-07-02
**Status:** Design approved, pending spec review
**Reference:** SpeakType (macOS, Swift/WhisperKit) — this is a fresh Windows build inspired by it, not a port.

## 1. Summary

A minimal, privacy-first Windows dictation utility. Hold a hotkey, speak, and the
spoken text is transcribed locally and pasted into whatever field is focused. Runs
from the system tray. Supports **English and Hebrew** with automatic language
detection from a single shortcut. All transcription is on-device (GPU-accelerated
via NVIDIA CUDA); nothing leaves the machine after the one-time model download.

Explicitly a lean personal tool: none of SpeakType's monetization, trial,
auto-updater, onboarding, stats, or console-logging bloat is carried over.

## 2. Goals & Non-Goals

### Goals
- One global push-to-talk hotkey: hold → record → release → transcribe → auto-paste.
- **User-configurable hotkey set via press-to-capture** in the app: the user clicks
  "Set hotkey", presses the key(s), and the app records exactly that. Supports a single
  key (e.g. Right Ctrl) or a combination (e.g. Ctrl+Alt+Space).
- Local transcription with `faster-whisper` (`large-v3`, multilingual).
- English + Hebrew, single shortcut, automatic per-utterance language detection.
- Optional tray override to pin the language (Auto / English / Hebrew).
- Optional vocabulary hint (`initial_prompt`) to improve recognition of the user's
  common English terms spoken inside Hebrew sentences.
- Light local history of past transcriptions (view, copy, clear).
- Tiny settings UI (hotkey, microphone, model, language, vocab hint, toggles).
- Clipboard save/restore around the synthetic paste (don't clobber the user's clipboard).

### Non-Goals (the "bloat" we deliberately drop)
- Licensing, Pro gating, trials (Polar.sh).
- Auto-updater / installer machinery.
- Onboarding flow, stats dashboards, ambient/animated UI, custom fonts.
- Telemetry or any logging of transcript/clipboard content.
- Cloud sync, accounts.
- Standalone `.exe` packaging is **out of core scope** (noted as an optional later step).

## 3. Known Limitations (expectations set with the user)

- **Intra-sentence code-switching is best-effort.** Whisper detects one dominant
  language per utterance and transcribes the whole segment in that language's script.
  English words embedded in a Hebrew sentence are often transliterated into Hebrew
  letters or mistranscribed. The vocabulary hint improves recognition of *specific
  listed terms* but does not make arbitrary code-switching reliable. `large-v3` is
  the best Whisper model for this but is still imperfect.
- **Elevated (admin) target windows.** Windows UIPI blocks synthetic input from a
  normal-privilege process into an elevated window. When paste fails there, we leave
  the text on the clipboard and notify the user to press Ctrl+V manually.
- **First run downloads the model** (~1.5 GB for `large-v3`) from HuggingFace to a
  local cache. Fully offline thereafter.

## 4. Architecture

Single Qt event loop (main thread) owns the tray icon and all windows. The global
hotkey runs on a background `pynput` listener thread; audio capture and transcription
run on worker threads. Cross-thread events marshal back to the main thread via Qt
signals so UI state stays consistent.

```
   pynput listener (bg thread)          Qt main thread (event loop)
   ┌───────────────────┐               ┌───────────────────────────────┐
   │ hold hotkey  →────────signal──────▶ AppController (state machine)  │
   │ release hotkey →──────signal──────▶  idle→recording→transcribing   │
   └───────────────────┘               │        │             ▲        │
                                        │        ▼             │        │
   Recorder (sounddevice) ◀─────────────┘   Transcriber (worker thread) │
        captures 16k mono float32          faster-whisper (CUDA/CPU)    │
                                              │ cleaned text            │
                                              ▼                         │
                                    Paster (clipboard + Ctrl+V) ────────┘
                                    HistoryStore (append)
                                    QSystemTrayIcon + Settings/History windows
```

### State machine (`AppController`)
`idle → recording → transcribing → idle`

- **idle:** hotkey armed, model warm in the background.
- **recording:** hotkey held; `Recorder` streaming to buffer; tray icon = recording.
- **transcribing:** hotkey released; buffer sent to `Transcriber`; tray icon = busy.
- On result: `Paster` pastes, `HistoryStore` logs, return to idle.
- Empty/silence result → skip paste and history, return to idle.

## 5. Components (one file each, single responsibility)

| Module | Responsibility | Depends on |
|---|---|---|
| `config.py` | `Config` dataclass + JSON load/save at `%APPDATA%\wisprclone\config.json`. Fields: `hotkey`, `trigger_mode` (hold/toggle), `input_device`, `model` (`large-v3`), `device` (cuda/cpu), `compute_type`, `language` (auto/en/he), `vocab_hint` (str), `remove_fillers` (bool, en-only), `history_cap` (int), `auto_paste` (bool). | — |
| `audio.py` | `Recorder` — open selected input device, capture 16 kHz mono float32 into a buffer; `start()`/`stop()→np.ndarray`. | sounddevice, numpy |
| `transcriber.py` | `Transcriber` — lazy-load `WhisperModel` (kept warm), `transcribe(samples)→str`. Passes `language` (None if auto) and `initial_prompt=vocab_hint`. Applies `clean_text()`. | faster-whisper |
| `textcleanup.py` | `clean_text(raw, remove_fillers)` — strip noise tags (`[BLANK_AUDIO]`, `(music)`, etc., language-agnostic), collapse whitespace/space-before-punctuation. English filler-word removal only when `remove_fillers` and text is Latin-script. | — (stdlib re) |
| `paste.py` | `Paster` — Win32: snapshot clipboard → set text → `SendInput` Ctrl+V → restore clipboard if unchanged. Detect UIPI paste failure → keep text on clipboard + signal notice. | pywin32 / ctypes |
| `hotkey.py` | A hotkey is a **set of keys**. `parse_hotkey(str)→frozenset` / `format_hotkey(frozenset)→str` (canonical, e.g. `"ctrl_r"` or `"alt_l+ctrl_l+space"`). `HotkeyListener` — pynput global listener tracking currently-held keys; fires `on_start` when the held set covers the target (hold-to-talk default, or toggle), `on_stop` when any target key is released. `HotkeyCapture` — records the maximal simultaneously-held key set for the press-to-capture UI. Both capture and runtime matching use pynput, so they stay consistent. | pynput |
| `history.py` | `HistoryStore` — append/list/clear entries `{text, timestamp, duration, language, model}` to `history.json`, pruned to `history_cap`. | — |
| `tray.py` | `Tray` — `QSystemTrayIcon` + menu: status line, Language submenu (Auto/English/Hebrew), Open Settings, Open History, Quit. Icon reflects state. | PySide6 |
| `windows.py` | `MainWindow` — tabbed Qt window: **Settings** (a **"Set hotkey" press-to-capture button** driven by `HotkeyCapture`, mic dropdown, model, language, vocab hint, toggles) and **History** (list with copy + clear). Renders RTL/bidi text natively. | PySide6, hotkey.py |
| `app.py` | `AppController` — owns state machine + `Config`; instantiates services; wires hotkey→record→transcribe→paste→history; manages model warm-up and CUDA→CPU fallback. | all above |
| `__main__.py` | Entry point: build `QApplication`, `AppController`, run tray. `python -m wisprclone`. | — |

## 6. GPU / Model Configuration

- Default: `device="cuda"`, `compute_type="float16"`, `model="large-v3"` (multilingual).
- CUDA DLLs (cuBLAS + cuDNN 9 for CUDA 12) provided via pip
  (`nvidia-cublas-cu12`, `nvidia-cudnn-cu12`) to avoid a manual CUDA install.
  **Setup risk:** CTranslate2 must find these DLLs on PATH; if CUDA init fails at
  startup we log the reason (to app log, never transcript content) and fall back.
- Fallback: `device="cpu"`, `compute_type="int8"`, `model="base"` + tray notification.
- Model dropdown offers only multilingual models (`large-v3`, `medium`, `small`,
  `base`). No `.en` or `distil-*` variants — they would silently break Hebrew.

## 7. Language Handling

- Default `language="auto"` → passed as `language=None` to faster-whisper; Whisper
  detects per utterance. One shortcut covers both English and Hebrew.
- Tray Language submenu and Settings let the user pin `en` or `he` for short/ambiguous
  clips where auto-detect is unreliable.
- `vocab_hint` string → `initial_prompt`. Improves recognition of the listed English
  terms inside Hebrew speech. Empty by default.
- Hebrew is Unicode; clipboard + Ctrl+V paste and Qt display handle RTL automatically.
  No special-casing needed in `paste.py`.

## 8. Error Handling

| Condition | Behavior |
|---|---|
| CUDA unavailable / init fails | Fall back to CPU `int8` `base`; tray balloon notice. |
| Selected mic missing/changed | Tray notice; open Settings; stay idle. |
| Empty/silence transcription | No paste, no history entry; return to idle. |
| Paste into elevated window (UIPI) | Text stays on clipboard; notify "copied — press Ctrl+V". |
| Model download fails (offline first run) | Tray notice with the reason; stay idle. |
| Config file corrupt/missing | Recreate from defaults. |

## 9. Testing

- **Unit (pytest):**
  - `textcleanup.clean_text` — noise-tag stripping, whitespace, filler removal on/off,
    Hebrew text passes through untouched.
  - `config` — round-trip save/load, defaults, corrupt-file recovery.
  - `history` — append, cap/prune, clear.
  - `hotkey` — key-string parse/format.
- **Manual smoke checklist:** record→transcribe→paste in English; same in Hebrew;
  mixed EN-in-HE with a vocab hint; language pin override; clipboard restore; paste
  into a normal app; paste into an elevated app (expect the fallback notice).
- **Optional end-to-end:** transcribe a bundled short sample WAV and assert non-empty
  cleaned text (guarded so it skips when the model isn't downloaded / no GPU).

## 10. Project Layout

```
wisprclone/
├── wisprclone/
│   ├── __main__.py
│   ├── app.py
│   ├── config.py
│   ├── audio.py
│   ├── transcriber.py
│   ├── textcleanup.py
│   ├── paste.py
│   ├── hotkey.py
│   ├── history.py
│   ├── tray.py
│   └── windows.py
├── tests/
│   ├── test_textcleanup.py
│   ├── test_config.py
│   ├── test_history.py
│   └── test_hotkey.py
├── docs/superpowers/specs/2026-07-02-wisprclone-windows-dictation-design.md
├── requirements.txt
└── README.md
```

## 11. Defaults Summary

| Setting | Default |
|---|---|
| Hotkey | Hold **Right Ctrl** (push-to-talk); user-configurable via press-to-capture (single key or combo) |
| Trigger mode | Hold-to-talk (toggle available) |
| Model | `large-v3` (multilingual) |
| Device / compute | `cuda` / `float16` (fallback `cpu` / `int8` / `base`) |
| Language | `auto` |
| Vocabulary hint | empty |
| Remove fillers (English only) | off |
| Auto-paste | on |
| History cap | 100 entries |
