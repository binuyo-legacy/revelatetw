"""Verses tab: the "Getting ready" card, plus the tab names and Ctrl+1..4 shortcuts.

Runs headless (QT_QPA_PLATFORM=offscreen) and is skipped when PyQt6 is not installed.
The checklist rules themselves are tested without Qt in test_preflight.py.
"""
import os
import time
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
qtw = pytest.importorskip("PyQt6.QtWidgets")

from revelatetw.approval import ApprovalQueue
from revelatetw.audio import InputDevice
from revelatetw.theme import Theme
from revelatetw.ui import OperatorWindow, ProjectionWindow

_APP = qtw.QApplication.instance() or qtw.QApplication([])


class _Live:
    def __init__(self, peak=-120.0):
        self.peak = peak
        self.capture = None
        self.transcriber = None

    def start_mic(self, dev, **kw):
        pass

    def use_text_feed(self):
        pass

    def meter(self):
        return {"peak_db": self.peak, "rms_db": self.peak}


@pytest.fixture
def no_audio_devices(monkeypatch):
    import revelatetw.audio as A
    monkeypatch.setattr(A, "list_input_devices", lambda: [])


def _window(tmp_path, live=None, pipeline=None, dev=False):
    return OperatorWindow(ApprovalQueue(None), Theme(), ProjectionWindow(), live=live, pipeline=pipeline,
                          songs_dir=str(tmp_path / "songs"), dev=dev)


def _texts(win):
    return [lab.text() for lab in win.checklist.findChildren(qtw.QLabel) if lab.objectName() == "checkText"]


def _button(win, label):
    return next(b for b in win.checklist.findChildren(qtw.QPushButton) if b.text() == label)


def test_card_is_shown_before_anything_is_heard(tmp_path, no_audio_devices):
    w = _window(tmp_path)
    assert not w.checklist.isHidden()
    assert w.check_title.text() == "Getting ready"        # live audio is not available: a warning
    assert any("Output is OFF" in t for t in _texts(w))   # output always starts off


def test_card_hides_once_the_first_words_are_transcribed(tmp_path, no_audio_devices):
    pipe = SimpleNamespace(history=[], last_latency_ms=0)
    w = _window(tmp_path, pipeline=pipe)
    assert not w.checklist.isHidden()
    pipe.history.append((time.time(), "turn with me to John chapter three", []))
    w.refresh()
    assert w.checklist.isHidden()


def test_no_microphone_warns_and_the_button_opens_audio_settings(tmp_path, no_audio_devices):
    w = _window(tmp_path, live=_Live())
    assert w.check_title.text() == "Getting ready"
    assert any("No microphone found" in t for t in _texts(w))
    assert not w.btn_setup.isChecked()
    _button(w, "Open audio settings").click()
    assert w.btn_setup.isChecked() and not w.setup_box.isHidden()


def test_turn_output_on_button_switches_the_output_and_the_card_follows(tmp_path, no_audio_devices):
    w = _window(tmp_path)
    assert not w.output.on
    _button(w, "Turn output on").click()
    assert w.output.on
    assert any("Output is ON" in t for t in _texts(w))
    assert not any(b.text() == "Turn output on" for b in w.checklist.findChildren(qtw.QPushButton))


def test_sound_check_latches_after_the_first_sound(tmp_path):
    live = _Live(peak=-120.0)
    w = _window(tmp_path, live=live)
    w._mic_on = True
    w._mic_dev = InputDevice(1, "Headset Mic", 1, 48000, "Windows WASAPI")
    w._devices = [w._mic_dev]
    w.refresh()
    assert any("No sound yet" in t for t in _texts(w))
    live.peak = -30.0
    w.refresh()
    assert any("Hearing sound" in t for t in _texts(w))
    live.peak = -120.0                                     # the preacher pauses
    w.refresh()
    assert any("Hearing sound" in t for t in _texts(w))


def test_card_is_not_rebuilt_when_nothing_changed(tmp_path, no_audio_devices):
    w = _window(tmp_path)
    first = w.check_rows.itemAt(0).widget()
    for _ in range(3):
        w.refresh()
    assert w.check_rows.itemAt(0).widget() is first


def test_dev_feed_session_is_not_reported_as_a_fault(tmp_path, no_audio_devices):
    w = _window(tmp_path, live=_Live(), dev=True)
    w.btn_source_dev.setChecked(True)
    w.refresh()
    assert any("Dev text feed" in t for t in _texts(w))
    assert not any("No microphone found" in t for t in _texts(w))


# --- tabs -----------------------------------------------------------------------------------

def test_tab_names_and_order(tmp_path, no_audio_devices):
    w = _window(tmp_path)
    titles = [w._tabs.tabText(i) for i in range(w._tabs.count())]
    assert titles[0] == "Verses" and titles[-1] == "Settings" and "Media" in titles
    assert w._tabs.tabText(w._settings_index) == "Settings"
    assert "Ctrl+1" in w._tabs.tabToolTip(0)


def test_ctrl_number_switches_tabs_and_ignores_bad_indexes(tmp_path, no_audio_devices):
    w = _window(tmp_path)
    w._goto_tab(2)
    assert w._tabs.currentIndex() == 2
    w._goto_tab(99)
    w._goto_tab(-1)
    assert w._tabs.currentIndex() == 2
    w._goto_tab(0)
    assert w._tabs.currentIndex() == 0
