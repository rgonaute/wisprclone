from wisprclone.hotkey import (
    HotkeyCapture,
    HotkeyListener,
    format_hotkey,
    key_token,
    parse_hotkey,
)


class FakeKey:
    """Stand-in for pynput Key/KeyCode."""
    def __init__(self, name=None, char=None):
        self.name = name
        self.char = char


def test_key_token_from_named_key():
    assert key_token(FakeKey(name="ctrl_r")) == "ctrl_r"


def test_key_token_from_char():
    assert key_token(FakeKey(char="V")) == "v"


def test_parse_and_format_roundtrip():
    assert parse_hotkey("alt_l+ctrl_l+space") == frozenset({"alt_l", "ctrl_l", "space"})
    assert format_hotkey({"space", "ctrl_l", "alt_l"}) == "alt_l+ctrl_l+space"


def test_hold_mode_fires_start_then_stop():
    events = []
    lis = HotkeyListener("ctrl_r", "hold",
                         on_start=lambda: events.append("start"),
                         on_stop=lambda: events.append("stop"))
    lis.press(FakeKey(name="ctrl_r"))
    lis.press(FakeKey(name="ctrl_r"))   # auto-repeat must not re-fire
    lis.release(FakeKey(name="ctrl_r"))
    assert events == ["start", "stop"]


def test_hold_mode_combo_requires_all_keys():
    events = []
    lis = HotkeyListener("alt_l+space", "hold",
                         on_start=lambda: events.append("start"),
                         on_stop=lambda: events.append("stop"))
    lis.press(FakeKey(name="alt_l"))
    assert events == []                 # not covered yet
    lis.press(FakeKey(name="space"))
    assert events == ["start"]          # covered now
    lis.release(FakeKey(name="space"))
    assert events == ["start", "stop"]  # releasing any target key stops


def test_toggle_mode_flips_on_each_full_press():
    events = []
    lis = HotkeyListener("ctrl_r", "toggle",
                         on_start=lambda: events.append("start"),
                         on_stop=lambda: events.append("stop"))
    lis.press(FakeKey(name="ctrl_r"))
    lis.release(FakeKey(name="ctrl_r"))
    lis.press(FakeKey(name="ctrl_r"))
    lis.release(FakeKey(name="ctrl_r"))
    assert events == ["start", "stop"]


def test_capture_records_maximal_combo():
    captured = []
    cap = HotkeyCapture(on_captured=captured.append)
    cap.press(FakeKey(name="ctrl_l"))
    cap.press(FakeKey(name="alt_l"))
    cap.release(FakeKey(name="alt_l"))
    cap.release(FakeKey(name="ctrl_l"))
    assert captured == ["alt_l+ctrl_l"]
