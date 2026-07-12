from wisprclone_mac.pasteboard import MacPaster


class FakePasteboard:
    def __init__(self, initial=None):
        self.value = initial
        self._count = 0

    def get_text(self):
        return self.value

    def set_text(self, text):
        self.value = text
        self._count += 1

    def change_count(self):
        return self._count


class FakeSender:
    def __init__(self):
        self.calls = 0

    def cmd_v(self):
        self.calls += 1


def _paster(prev=None, trusted=True):
    pb = FakePasteboard(prev)
    sender = FakeSender()
    p = MacPaster(pasteboard=pb, sender=sender, trust_check=lambda: trusted, sleep=0)
    return p, pb, sender


def test_returns_false_and_touches_nothing_when_not_trusted():
    p, pb, sender = _paster(prev="old", trusted=False)
    assert p.paste_text("hi") is False
    assert sender.calls == 0
    assert pb.value == "old"


def test_sends_cmd_v_and_restores_previous_text():
    p, pb, sender = _paster(prev="old", trusted=True)
    assert p.paste_text("שלום") is True   # Hebrew "shalom"
    assert sender.calls == 1
    assert pb.value == "old"


def test_text_is_on_pasteboard_at_the_moment_paste_fires():
    pb = FakePasteboard("old")

    class RecordingSender:
        def __init__(self, pb):
            self.pb = pb
            self.at_paste = None

        def cmd_v(self):
            self.at_paste = self.pb.value

    sender = RecordingSender(pb)
    MacPaster(pasteboard=pb, sender=sender, trust_check=lambda: True,
              sleep=0).paste_text("שלום")
    assert sender.at_paste == "שלום"


def test_does_not_restore_when_previous_was_nontext():
    p, pb, sender = _paster(prev=None, trusted=True)
    assert p.paste_text("hi") is True
    assert pb.value == "hi"   # never restored to None -> images/files kept safe


def test_does_not_restore_when_clipboard_changed_during_paste():
    pb = FakePasteboard("old")

    class ClobberSender:
        def __init__(self, pb):
            self.pb = pb

        def cmd_v(self):
            self.pb.set_text("target app copied this")

    MacPaster(pasteboard=pb, sender=ClobberSender(pb), trust_check=lambda: True,
              sleep=0).paste_text("hi")
    assert pb.value == "target app copied this"


def test_copy_only_sets_text_without_pasting():
    p, pb, sender = _paster(prev="x", trusted=True)
    p.copy_only("data")
    assert pb.value == "data"
    assert sender.calls == 0
