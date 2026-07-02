import numpy as np
from wisprclone.audio import Recorder


def test_empty_stop_returns_empty_float32():
    rec = Recorder()
    out = rec.stop()
    assert out.dtype == np.float32
    assert out.size == 0


def test_callback_frames_are_concatenated_and_flattened():
    rec = Recorder()
    rec._frames = []
    rec._callback(np.ones((100, 1), dtype=np.float32), 100, None, None)
    rec._callback(np.zeros((50, 1), dtype=np.float32), 50, None, None)
    out = rec.stop()
    assert out.shape == (150,)
    assert out.dtype == np.float32
    assert out[0] == 1.0 and out[-1] == 0.0
