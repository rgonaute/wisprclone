import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform == "win32",
                                reason="fcntl is POSIX-only; runs on macOS CI")


def test_first_acquire_succeeds(tmp_path):
    from wisprclone_mac.single_instance import SingleInstance
    assert SingleInstance(tmp_path / "wc.lock").acquire() is True


def test_second_instance_is_blocked(tmp_path):
    from wisprclone_mac.single_instance import SingleInstance
    a = SingleInstance(tmp_path / "wc.lock")
    b = SingleInstance(tmp_path / "wc.lock")
    assert a.acquire() is True
    assert b.acquire() is False
