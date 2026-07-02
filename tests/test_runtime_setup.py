import os
from wisprclone.runtime_setup import configure, _needs_redirect


def test_needs_redirect_true_when_stream_none():
    assert _needs_redirect(None, object()) is True
    assert _needs_redirect(object(), None) is True


def test_needs_redirect_false_when_both_present():
    assert _needs_redirect(object(), object()) is False


def test_configure_creates_logdir_and_sets_env(tmp_path, monkeypatch):
    monkeypatch.delenv("HF_HUB_DISABLE_PROGRESS_BARS", raising=False)
    log_dir = tmp_path / "logs"
    path = configure(log_dir)
    assert log_dir.is_dir()
    assert os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] == "1"
    assert str(path).startswith(str(log_dir))
