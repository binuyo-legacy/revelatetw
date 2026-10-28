"""Input gain on the Live screen: the gain box drives the audio capture and is remembered.

Runs headless (QT_QPA_PLATFORM=offscreen) and is skipped when PyQt6 is not installed.
Settings and capture tests are in test_input_gain.py.
"""
import os

import pytest

from revelatetw.store import INPUT_GAIN_RANGE_DB, AppSettings, load_settings

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
qtw = pytest.importorskip("PyQt6.QtWidgets")

from revelatetw.approval import ApprovalQueue
from revelatetw.theme import Theme
from revelatetw.ui import OperatorWindow, ProjectionWindow

_APP = qtw.QApplication.instance() or qtw.QApplication([])


class _FakeCapture:
    def __init__(self):
        self.gains = []

    def set_gain(self, db):
        self.gains.append(db)


class _FakeLive:
    def __init__(self):
        self.starts = []
        self.capture = None
        self.transcriber = None

    def start_mic(self, dev, **kw):
        self.starts.append(kw)
        self.capture = _FakeCapture()

    def use_text_feed(self):
        self.capture = None

    def meter(self):
        return {"peak_db": -120.0, "rms_db": -120.0}


def _window(tmp_path, settings=None, live=None, settings_path=None):
    return OperatorWindow(ApprovalQueue(None), Theme(), ProjectionWindow(), live=live,
                          songs_dir=str(tmp_path / "songs"), settings=settings,
                          settings_path=settings_path)


def test_box_starts_at_the_saved_gain(tmp_path):
    w = _window(tmp_path, settings=AppSettings(input_gain_db=-12.5))
    assert w.gain.value() == -12.5
    assert w.gain.minimum() == INPUT_GAIN_RANGE_DB[0] and w.gain.maximum() == INPUT_GAIN_RANGE_DB[1]


def test_changing_the_box_updates_the_running_capture(tmp_path):
    live = _FakeLive()
    w = _window(tmp_path, live=live)
    live.capture = _FakeCapture()
    w.gain.setValue(9.0)
    assert live.capture.gains == [9.0]
    assert w.settings.input_gain_db == 9.0


def test_changing_the_box_with_no_capture_open_does_not_fail(tmp_path):
    w = _window(tmp_path)                     # live=None: no audio in this session
    w.gain.setValue(4.0)
    assert w.settings.input_gain_db == 4.0


def test_every_mic_start_uses_the_saved_gain(tmp_path):
    live = _FakeLive()
    w = _window(tmp_path, settings=AppSettings(input_gain_db=6.0), live=live)
    from revelatetw.audio import InputDevice as D
    w._devices = [D(1, "Mic", 1, 48000, "Windows WASAPI")]
    w._open_mic_chain()
    assert live.starts and live.starts[-1]["gain_db"] == 6.0
    w.gain.setValue(-3.0)
    w._open_mic_chain()                        # e.g. after the watchdog moved to another input
    assert live.starts[-1]["gain_db"] == -3.0


def test_gain_is_saved_once_after_the_operator_stops(tmp_path):
    path = tmp_path / "settings.json"
    w = _window(tmp_path, settings_path=str(path))
    for v in (1.0, 2.0, 3.0, 4.0):             # holding the arrow key
        w.gain.setValue(v)
    assert not path.exists()                   # still waiting
    assert w._gain_save_timer.isActive()
    w._gain_save_timer.stop()
    w._save_settings()                         # what the timer does when it fires
    assert load_settings(path).input_gain_db == 4.0


def test_closing_right_after_a_change_still_saves(tmp_path):
    path = tmp_path / "settings.json"
    w = _window(tmp_path, settings_path=str(path))
    w.gain.setValue(8.0)
    w.close()
    assert load_settings(path).input_gain_db == 8.0


def test_settings_changed_elsewhere_moves_the_box_and_the_capture(tmp_path):
    live = _FakeLive()
    w = _window(tmp_path, live=live)
    live.capture = _FakeCapture()
    w.settings.input_gain_db = 11.0
    w._on_setting_changed("input_gain_db")
    assert w.gain.value() == 11.0 and live.capture.gains == [11.0]
