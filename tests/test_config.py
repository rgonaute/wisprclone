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
