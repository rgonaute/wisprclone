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
    t = Transcriber(Config(language="auto"), model_factory=lambda m, d, c: model)
    t.transcribe([0.0])
    assert model.calls[0]["language"] is None


def test_explicit_language_passed_through():
    model = FakeModel()
    t = Transcriber(Config(language="he"), model_factory=lambda m, d, c: model)
    t.transcribe([0.0])
    assert model.calls[0]["language"] == "he"


def test_vocab_hint_passed_as_initial_prompt():
    model = FakeModel()
    t = Transcriber(Config(vocab_hint="report, PayPal"), model_factory=lambda m, d, c: model)
    t.transcribe([0.0])
    assert model.calls[0]["initial_prompt"] == "report, PayPal"


def test_empty_vocab_hint_becomes_none():
    model = FakeModel()
    t = Transcriber(Config(vocab_hint=""), model_factory=lambda m, d, c: model)
    t.transcribe([0.0])
    assert model.calls[0]["initial_prompt"] is None


def test_result_is_joined_and_cleaned():
    t = Transcriber(Config(), model_factory=lambda m, d, c: FakeModel())
    assert t.transcribe([0.0]) == "hello world"


def test_ensure_current_resets_after_model_change():
    cfg = Config(model="large-v3")
    t = Transcriber(cfg, model_factory=lambda m, d, c: FakeModel())
    t.load()
    assert t.ensure_current() is False       # nothing changed
    cfg.model = "small"
    assert t.ensure_current() is True         # change detected -> model dropped
    assert t._model is None
    assert t.ensure_current() is False        # already dropped


def test_float16_unsupported_retries_gpu_int8_same_model():
    # e.g. GTX 10xx: float16 raises, but the GPU is fine with int8.
    cfg = Config(device="cuda", compute_type="float16", model="large-v3")

    def factory(model, device, compute_type):
        if compute_type == "float16":
            raise ValueError("float16 compute type not supported on this device")
        return FakeModel()

    t = Transcriber(cfg, model_factory=factory)
    t.load()
    assert t.used_fallback is True
    assert t.active_mode == ("large-v3", "cuda", "int8")
    # config is NOT mutated by fallback — it still reflects the user's request.
    assert (cfg.model, cfg.device, cfg.compute_type) == ("large-v3", "cuda", "float16")


def test_falls_back_to_cpu_when_cuda_unavailable():
    cfg = Config(device="cuda", compute_type="float16", model="large-v3")

    def factory(model, device, compute_type):
        if device == "cuda":
            raise RuntimeError("no CUDA-capable device is detected")
        return FakeModel()

    t = Transcriber(cfg, model_factory=factory)
    t.load()
    assert t.used_fallback is True
    assert t.active_mode == ("base", "cpu", "int8")
    assert (cfg.model, cfg.device, cfg.compute_type) == ("large-v3", "cuda", "float16")


def test_no_fallback_when_first_attempt_succeeds():
    cfg = Config(device="cuda", compute_type="float16", model="large-v3")
    t = Transcriber(cfg, model_factory=lambda m, d, c: FakeModel())
    t.load()
    assert t.used_fallback is False
    assert t.active_mode == ("large-v3", "cuda", "float16")


def test_load_raises_when_every_attempt_fails():
    cfg = Config(device="cuda", compute_type="float16", model="large-v3")

    def factory(model, device, compute_type):
        raise RuntimeError("total failure")

    t = Transcriber(cfg, model_factory=factory)
    try:
        t.load()
        assert False, "expected load() to raise when all fallbacks fail"
    except RuntimeError as exc:
        assert "total failure" in str(exc)


def test_ensure_current_ignores_fallback_difference():
    # After a fallback the loaded mode differs from config, but that is NOT a
    # user config change, so ensure_current must not trigger a reload.
    cfg = Config(device="cuda", compute_type="float16", model="large-v3")

    def factory(model, device, compute_type):
        if compute_type == "float16":
            raise ValueError("no float16")
        return FakeModel()

    t = Transcriber(cfg, model_factory=factory)
    t.load()
    assert t.active_mode == ("large-v3", "cuda", "int8")
    assert t.ensure_current() is False  # config unchanged since load -> no reload
