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
