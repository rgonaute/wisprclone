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
