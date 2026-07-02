from pathlib import Path

import pytest


def test_make_icon_produces_valid_ico(tmp_path):
    Image = pytest.importorskip("PIL.Image")  # CI has no Pillow -> skip cleanly
    from winbuild.make_icon import build
    out = tmp_path / "x.ico"
    build(out)
    assert out.exists()
    with Image.open(out) as im:
        assert im.format == "ICO"
