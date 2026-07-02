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


def test_ensure_current_resets_after_model_change():
    cfg = Config(model="large-v3")
    t = Transcriber(cfg, model_factory=lambda: FakeModel())
    t.load()
    assert t.ensure_current() is False       # nothing changed
    cfg.model = "small"
    assert t.ensure_current() is True         # change detected -> model dropped
    assert t._model is None
    assert t.ensure_current() is False        # already dropped


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
