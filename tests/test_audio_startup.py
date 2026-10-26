"""Regression tests: the header wave goes live on the default input at startup, and a dead
or erroring capture is reported and moved to the next input instead of staying grey."""
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from revelatetw.audio import AudioCapture, InputDevice  # noqa: E402
import revelatetw.audio as A  # noqa: E402


class _Cap:
    def __init__(self, error=None, stalled=False):
        self.error = error
        self._stalled = stalled
        self.blocks = 0

    def stalled(self, after_s=3.0):
        return self._stalled


def test_stalled_and_error_flags_default_quiet():
    dev = InputDevice(1, "Mic", 1, 48000, "Windows WASAPI")
    cap = AudioCapture.__new__(AudioCapture)
    cap.device = dev
    cap.blocks = 0
    cap.error = None
    cap.started_at = 0.0
    cap._stream = None
    assert cap.stalled() is False          # no stream open: nothing to stall


def test_pick_format_falls_back_when_native_rejected():
    dev = InputDevice(1, "Mixer", 32, 44100, "Windows WASAPI")
    cap = AudioCapture(dev)                # real init: open_channels = min(32, 2) = 2, rate = 44100

    class _SD:
        def __init__(self):
            self.tried = []

        def check_input_settings(self, **kw):
            self.tried.append((kw["channels"], kw["samplerate"]))
            if kw["channels"] != 1 or kw["samplerate"] != 48000:
                raise RuntimeError("unsupported")

    sd = _SD()
    ch, rate = cap._pick_format(sd, None)
    assert (ch, rate) == (1, 48000)        # 2ch refused at 44.1k and 48k, then 1ch at 48k passes
    assert sd.tried[0] == (2, 44100)


def test_startup_starts_mic_on_default_input_when_shown():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from revelatetw.approval import ApprovalQueue
    from revelatetw.theme import Theme
    from revelatetw.ui import OperatorWindow, ProjectionWindow

    class _Live:
        def __init__(self):
            self.calls = []
            self.capture = None
            self.transcriber = None

        def start_mic(self, dev, **kw):
            self.calls.append(dev.name)

        def use_text_feed(self):
            pass

        def meter(self):
            return {"peak_db": -120.0, "rms_db": -120.0}

    devs = [InputDevice(1, "Headset Mic", 1, 48000, "Windows WASAPI"),
            InputDevice(2, "Speakers (loopback)", 2, 48000, "Windows WASAPI", loopback=True)]
    orig_list, orig_default = A.list_input_devices, A.default_input_index
    A.list_input_devices = lambda: devs
    A.default_input_index = lambda: 1
    try:
        live = _Live()
        w = OperatorWindow(ApprovalQueue(None), Theme(), ProjectionWindow(), pipeline=None,
                           live=live, songs_dir=tempfile.mkdtemp())
        w.show()
        app.processEvents()
        assert live.calls and live.calls[0] == "Headset Mic"
        assert w._mic_on is True
        assert w.btn_source_mic.isChecked()
        assert "Listening" in w.source_status.text()
        w.hide()
    finally:
        A.list_input_devices, A.default_input_index = orig_list, orig_default


def test_failed_capture_moves_to_next_input():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from revelatetw.approval import ApprovalQueue
    from revelatetw.theme import Theme
    from revelatetw.ui import OperatorWindow, ProjectionWindow

    class _Live:
        def __init__(self):
            self.calls = []
            self.capture = _Cap(error="device unplugged")
            self.transcriber = None

        def start_mic(self, dev, **kw):
            self.calls.append(dev.name)
            self.capture = _Cap()

        def use_text_feed(self):
            pass

        def meter(self):
            return {"peak_db": -120.0, "rms_db": -120.0}

    devs = [InputDevice(1, "USB Interface", 2, 48000, "Windows WASAPI"),
            InputDevice(2, "Built-in Mic", 1, 48000, "Windows WASAPI")]
    orig_list, orig_default = A.list_input_devices, A.default_input_index
    A.list_input_devices = lambda: devs
    A.default_input_index = lambda: 1
    try:
        live = _Live()
        w = OperatorWindow(ApprovalQueue(None), Theme(), ProjectionWindow(), pipeline=None,
                           live=live, songs_dir=tempfile.mkdtemp())
        w.show()
        app.processEvents()
        w._mic_dev = devs[0]
        w._mic_on = True
        live.capture = _Cap(error="device unplugged")
        assert w._check_capture() is True
        assert "USB Interface" in w._failed_devices
        assert live.calls[-1] == "Built-in Mic"
        assert "Built-in Mic" in w.source_status.text()
        w.hide()
    finally:
        A.list_input_devices, A.default_input_index = orig_list, orig_default
