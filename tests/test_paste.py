from wisprclone.paste import Paster


class FakeClipboard:
    def __init__(self, initial=None):
        self._text = initial
        self.history = []

    def get_text(self):
        return self._text

    def set_text(self, text):
        self._text = text
        self.history.append(text)


class FakeSender:
    def __init__(self):
        self.pasted = 0

    def ctrl_v(self):
        self.pasted += 1


def test_normal_paste_sends_ctrl_v_and_restores_clipboard():
    clip = FakeClipboard(initial="OLD")
    sender = FakeSender()
    p = Paster(clipboard=clip, sender=sender, elevated_check=lambda: False)
    assert p.paste_text("NEW") is True
    assert sender.pasted == 1
    assert clip.get_text() == "OLD"          # restored
    assert "NEW" in clip.history            # was set during paste


def test_elevated_target_skips_paste_and_leaves_text():
    clip = FakeClipboard(initial="OLD")
    sender = FakeSender()
    p = Paster(clipboard=clip, sender=sender, elevated_check=lambda: True)
    assert p.paste_text("NEW") is False
    assert sender.pasted == 0
    assert clip.get_text() == "NEW"          # left on clipboard for manual paste


def test_restore_skipped_when_no_previous_clipboard():
    clip = FakeClipboard(initial=None)
    p = Paster(clipboard=clip, sender=FakeSender(), elevated_check=lambda: False)
    p.paste_text("NEW")
    assert clip.get_text() == "NEW"          # nothing to restore to
