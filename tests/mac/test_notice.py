import io

from wisprclone_mac.notice import format_notice


def test_rewrites_ctrl_v_to_cmd_v():
    assert format_notice("Copied to clipboard — press Ctrl+V to paste.") == \
        "Copied to clipboard — press Cmd+V to paste."


def test_leaves_unrelated_text_untouched():
    assert format_notice("Settings saved.") == "Settings saved."


class FakeTray:
    def __init__(self):
        self.messages = []

    def notify(self, msg):
        self.messages.append(msg)


def test_notify_tees_the_same_rewritten_text_to_stderr_and_tray():
    from wisprclone_mac.notice import _make_notify

    err = io.StringIO()
    tray = FakeTray()
    notify = _make_notify({"tray": tray}, stderr=err)
    notify("Copied to clipboard — press Ctrl+V to paste.")
    assert tray.messages == ["Copied to clipboard — press Cmd+V to paste."]
    assert err.getvalue() == \
        "[wisprclone] Copied to clipboard — press Cmd+V to paste.\n"


def test_notify_writes_stderr_even_before_the_tray_exists():
    from wisprclone_mac.notice import _make_notify

    err = io.StringIO()
    notify = _make_notify({"tray": None}, stderr=err)
    notify("Settings saved.")
    assert err.getvalue() == "[wisprclone] Settings saved.\n"
