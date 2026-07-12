from pathlib import Path

from wisprclone_mac.config import MacConfig, MAC_APP_DIR, MAC_CONFIG_PATH


def test_mac_defaults_are_cpu_int8_medium_altr():
    c = MacConfig()
    assert c.device == "cpu"
    assert c.compute_type == "int8"
    assert c.model == "medium"
    assert c.hotkey == "alt_r"


def test_mac_paths_under_application_support():
    assert MAC_APP_DIR.parts[-3:] == ("Library", "Application Support", "wisprclone")
    assert MAC_CONFIG_PATH == MAC_APP_DIR / "config.json"


def test_first_fallback_is_medium_not_base():
    # The transcriber chain ends at ("base","cpu","int8"); a default cpu/int8
    # config must make the FIRST attempt the medium model, or Mac silently
    # degrades to base.
    from wisprclone.transcriber import Transcriber
    chain = Transcriber(MacConfig())._fallback_chain()
    assert chain[0] == ("medium", "cpu", "int8")


def test_load_missing_file_uses_mac_defaults(tmp_path):
    c = MacConfig.load(tmp_path / "nope.json")
    assert c.device == "cpu" and c.model == "medium"


def test_save_then_load_roundtrip_keeps_mac_defaults(tmp_path):
    p = tmp_path / "config.json"
    MacConfig(vocab_hint="Kubernetes").save(p)
    loaded = MacConfig.load(p)
    assert loaded.vocab_hint == "Kubernetes"
    assert loaded.device == "cpu"
    assert isinstance(loaded, MacConfig)
