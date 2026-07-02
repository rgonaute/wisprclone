import os

import wisprclone.cuda_paths as cp


def test_prepends_dirs_and_is_idempotent(monkeypatch):
    monkeypatch.setattr(cp, "_done", False)
    fake = [r"X:\fake\cublas\bin", r"X:\fake\cudnn\bin"]
    monkeypatch.setattr(cp, "cuda_bin_dirs", lambda: fake)
    monkeypatch.setenv("PATH", r"C:\existing")

    added = cp.ensure_cuda_on_path()
    assert added == fake
    expected_prefix = os.pathsep.join(fake) + os.pathsep
    assert os.environ["PATH"].startswith(expected_prefix)

    # Second call is a no-op — PATH is not prepended twice.
    frozen = os.environ["PATH"]
    assert cp.ensure_cuda_on_path() == []
    assert os.environ["PATH"] == frozen


def test_no_dirs_leaves_path_unchanged(monkeypatch):
    monkeypatch.setattr(cp, "_done", False)
    monkeypatch.setattr(cp, "cuda_bin_dirs", lambda: [])
    monkeypatch.setenv("PATH", r"C:\existing")
    assert cp.ensure_cuda_on_path() == []
    assert os.environ["PATH"] == r"C:\existing"
