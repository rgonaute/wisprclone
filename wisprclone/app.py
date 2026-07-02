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
        try:
            self.recorder.start()
        except Exception as exc:  # e.g. mic unplugged / device name stale
            self._notify(f"Microphone unavailable: {exc}")
            self._set_state("idle")

    def stop_and_transcribe(self) -> None:
        if self.state != "recording":
            return
        try:
            samples = self.recorder.stop()
        except Exception as exc:
            self._notify(f"Recording error: {exc}")
            self._set_state("idle")
            return
        self._set_state("transcribing")
        duration = float(len(samples)) / 16000.0
        if self.run_async:
            threading.Thread(target=self._do_transcribe, args=(samples, duration),
                             daemon=True).start()
        else:
            self._do_transcribe(samples, duration)

    def _do_transcribe(self, samples, duration: float) -> None:
        # Everything runs under try/finally so the state ALWAYS returns to idle,
        # even if paste or history raises (e.g. Windows clipboard access denied);
        # otherwise the hotkey would stay wedged in "transcribing" until restart.
        try:
            text = self.transcriber.transcribe(samples)
            if not text:
                return

            if self.config.auto_paste:
                pasted = self.paster.paste_text(text)
                if not pasted:
                    self._notify("Copied to clipboard — press Ctrl+V to paste.")
            else:
                self.paster.copy_only(text)
                self._notify("Copied to clipboard — press Ctrl+V to paste.")

            self.history.add(HistoryEntry(
                text=text,
                timestamp=datetime.now(timezone.utc).isoformat(),
                duration=duration,
                language=self.config.language,
                model=self.config.model,
            ))
        except Exception as exc:  # never log transcript content; message only
            self._notify(f"Dictation failed: {exc}")
        finally:
            self._set_state("idle")
