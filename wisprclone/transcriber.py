from __future__ import annotations

import threading
from typing import Callable, Optional

from .config import Config
from .textcleanup import clean_text


class Transcriber:
    def __init__(self, config: Config, model_factory: Optional[Callable[..., object]] = None):
        self.config = config
        self._model = None
        self.used_fallback = False
        self._loaded = None        # (model, device, compute_type) actually running
        self._requested = None     # (model, device, compute_type) the user asked for
        self._lock = threading.Lock()
        self._model_factory = model_factory or self._default_factory

    def _default_factory(self, model, device, compute_type):
        from faster_whisper import WhisperModel
        return WhisperModel(model, device=device, compute_type=compute_type)

    def load(self):
        """Build the model (once), trying the fallback chain. Returns the model.

        Does NOT mutate `self.config` — the config reflects what the user asked
        for; `active_mode` reflects what actually loaded (which may differ after
        a fallback). The returned reference lets callers hold the model even if
        `ensure_current()` nulls `self._model` concurrently."""
        model = self._model
        if model is not None:
            return model
        with self._lock:
            model = self._model
            if model is not None:  # another thread finished loading while we waited
                return model
            requested = (self.config.model, self.config.device, self.config.compute_type)
            last_exc: Optional[Exception] = None
            for model, device, compute_type in self._fallback_chain():
                try:
                    built = self._model_factory(model, device, compute_type)
                except Exception as exc:  # try the next combination in the chain
                    last_exc = exc
                    continue
                self._model = built
                self._requested = requested
                self._loaded = (model, device, compute_type)
                self.used_fallback = self._loaded != requested
                return self._model
            raise last_exc if last_exc is not None else RuntimeError("Model failed to load")

    def _fallback_chain(self):
        """Ordered (model, device, compute_type) attempts: the user's request
        first, then graceful degradation. Many older NVIDIA GPUs (e.g. GTX 10xx
        / Pascal) cannot do efficient float16, so retry on the GPU with int8 —
        keeping the requested model — before dropping to CPU."""
        model = self.config.model
        chain = [(model, self.config.device, self.config.compute_type)]
        if self.config.device == "cuda" and self.config.compute_type != "int8":
            chain.append((model, "cuda", "int8"))
        chain.append(("base", "cpu", "int8"))
        unique = []
        for combo in chain:
            if combo not in unique:
                unique.append(combo)
        return unique

    @property
    def active_mode(self):
        """(model, device, compute_type) actually loaded, or None if not loaded."""
        return self._loaded

    def ensure_current(self) -> bool:
        """Drop the loaded model if the user's requested config changed since it
        was loaded, so the next transcribe() rebuilds it. Compares against what
        the user requested (not what loaded), so a fallback never looks like a
        change. Returns True if a reload was triggered."""
        current = (self.config.model, self.config.device, self.config.compute_type)
        if self._model is not None and self._requested is not None and self._requested != current:
            with self._lock:
                self._model = None
                self._loaded = None
                self.used_fallback = False
            return True
        return False

    def transcribe(self, samples) -> str:
        model = self.load()  # local reference — safe even if the model is dropped concurrently
        language = None if self.config.language == "auto" else self.config.language
        initial_prompt = self.config.vocab_hint or None
        segments, _info = model.transcribe(
            samples,
            language=language,
            initial_prompt=initial_prompt,
        )
        raw = " ".join(seg.text for seg in segments)
        return clean_text(raw, remove_fillers=self.config.remove_fillers)
