import re
import wisprclone


def test_version_is_semver():
    assert re.fullmatch(r"\d+\.\d+\.\d+", wisprclone.__version__)
