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
