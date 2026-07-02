import numpy as np
from wisprclone.app import AppController
from wisprclone.config import Config


class FakeRecorder:
    def __init__(self, samples, raise_on_start=None):
        self._samples = samples
        self._raise_on_start = raise_on_start
        self.started = False

    def start(self):
        if self._raise_on_start:
            raise self._raise_on_start
        self.started = True

    def stop(self):
        return self._samples


class FakeTranscriber:
    def __init__(self, text, error=None):
        self._text = text
        self._error = error

    def transcribe(self, samples):
        if self._error:
            raise self._error
        return self._text


class FakePaster:
    def __init__(self, result=True, raise_on_paste=None):
        self.result = result
        self._raise_on_paste = raise_on_paste
        self.pasted = []

    def paste_text(self, text):
        if self._raise_on_paste:
            raise self._raise_on_paste
        self.pasted.append(text)
        return self.result

    def copy_only(self, text):
        self.copied = getattr(self, "copied", [])
        self.copied.append(text)


class FakeHistory:
    def __init__(self):
        self.entries = []

    def add(self, entry):
        self.entries.append(entry)


def _controller(text="hello", samples=None, paste_result=True, error=None):
    samples = np.ones(16000, dtype=np.float32) if samples is None else samples
    notes = []
    states = []
    ctrl = AppController(
        Config(),
        FakeRecorder(samples),
        FakeTranscriber(text, error=error),
        FakePaster(result=paste_result),
        FakeHistory(),
        notify=notes.append,
        on_state=states.append,
        run_async=False,
    )
    return ctrl, notes, states


def test_happy_path_pastes_and_records_history():
    ctrl, notes, states = _controller(text="hello world")
    ctrl.start_recording()
    assert ctrl.state == "recording"
    ctrl.stop_and_transcribe()
    assert ctrl.state == "idle"
    assert ctrl.paster.pasted == ["hello world"]
    assert ctrl.history.entries[0].text == "hello world"
    assert states == ["recording", "transcribing", "idle"]


def test_empty_transcription_skips_paste_and_history():
    ctrl, notes, states = _controller(text="")
    ctrl.start_recording()
    ctrl.stop_and_transcribe()
    assert ctrl.paster.pasted == []
    assert ctrl.history.entries == []
    assert ctrl.state == "idle"


def test_elevated_paste_failure_notifies_user():
    ctrl, notes, states = _controller(text="hi", paste_result=False)
    ctrl.start_recording()
    ctrl.stop_and_transcribe()
    assert any("Ctrl+V" in n for n in notes)
    assert ctrl.history.entries[0].text == "hi"   # still logged


def test_auto_paste_disabled_copies_without_pasting():
    ctrl, notes, states = _controller(text="hi there")
    ctrl.config.auto_paste = False
    ctrl.start_recording()
    ctrl.stop_and_transcribe()
    assert ctrl.paster.pasted == []
    assert ctrl.paster.copied == ["hi there"]
    assert any("Ctrl+V" in n for n in notes)
    assert ctrl.history.entries[0].text == "hi there"


def test_transcription_error_notifies_and_returns_to_idle():
    ctrl, notes, states = _controller(error=RuntimeError("boom"))
    ctrl.start_recording()
    ctrl.stop_and_transcribe()
    assert ctrl.state == "idle"
    assert notes  # some error message surfaced
    assert ctrl.history.entries == []


def test_stop_without_recording_is_ignored():
    ctrl, notes, states = _controller()
    ctrl.stop_and_transcribe()   # never started
    assert ctrl.state == "idle"
    assert ctrl.paster.pasted == []


def test_double_start_stays_in_recording_once():
    ctrl, notes, states = _controller()
    ctrl.start_recording()
    ctrl.start_recording()
    assert states.count("recording") == 1


def test_paste_exception_returns_to_idle():
    # Windows clipboard contention (OpenClipboard "access denied") must not
    # wedge the app in "transcribing" — it must recover to idle.
    import numpy as np
    ctrl = AppController(
        Config(),
        FakeRecorder(np.ones(16000, dtype=np.float32)),
        FakeTranscriber("hello"),
        FakePaster(raise_on_paste=OSError("clipboard access denied")),
        FakeHistory(),
        notify=[].append,
        on_state=[].append,
        run_async=False,
    )
    ctrl.start_recording()
    ctrl.stop_and_transcribe()
    assert ctrl.state == "idle"


def test_recorder_start_failure_returns_to_idle_and_notifies():
    import numpy as np
    notes = []
    ctrl = AppController(
        Config(),
        FakeRecorder(np.ones(16000, dtype=np.float32),
                     raise_on_start=OSError("no default input device")),
        FakeTranscriber("hello"),
        FakePaster(),
        FakeHistory(),
        notify=notes.append,
        on_state=[].append,
        run_async=False,
    )
    ctrl.start_recording()
    assert ctrl.state == "idle"
    assert any("Microphone" in n for n in notes)
