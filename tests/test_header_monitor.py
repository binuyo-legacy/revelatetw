import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt6.QtWidgets")

from revelatetw import monitor as mon  # noqa: E402
from revelatetw.approval import ApprovalQueue  # noqa: E402
from revelatetw.theme import Theme  # noqa: E402
from revelatetw.ui import HEADER_TICK_MS, MicWaveWidget, OperatorWindow, ProjectionWindow, SysChipWidget  # noqa: E402

from PyQt6.QtWidgets import QApplication  # noqa: E402

_APP = QApplication.instance() or QApplication([])
RATE = 16000


def _tone(db: float, seconds: float = 0.5, rate: int = RATE) -> np.ndarray:
    """Sine block whose RMS is `db` dBFS."""
    amp = (10 ** (db / 20.0)) * np.sqrt(2.0)
    t = np.arange(int(rate * seconds)) / rate
    return (amp * np.sin(2 * np.pi * 440 * t)).astype(np.float32)


# ---- AudioMonitor: level, threshold, hysteresis --------------------------------------------

def test_audio_inactive_is_free_and_measures_nothing():
    m = mon.AudioMonitor()
    assert m.feed(_tone(-20)) == 0
    assert m.frames_processed == 0 and m.level == 0.0 and not m.signal_present


def test_level_mapping_floor_and_ceiling():
    assert mon.level_from_db(-70) == 0.0
    assert mon.level_from_db(0) == 1.0
    assert 0.4 < mon.level_from_db(-30) < 0.6


def test_frames_are_66ms_not_per_buffer():
    m = mon.AudioMonitor()
    m.set_active(True)
    n = m.feed(_tone(-20, seconds=1.0))          # 1 s of audio -> ~15 frames
    assert 14 <= n <= 16
    assert m.frames_processed == n


def test_partial_frames_carry_over_between_blocks():
    m = mon.AudioMonitor()
    m.set_active(True)
    block = _tone(-20, seconds=0.03)              # 480 samples; frame is ~1056 samples
    assert m.feed(block) == 0
    assert m.feed(block) == 0
    assert m.feed(block) == 1                     # third block completes a frame


def test_signal_present_hysteresis():
    m = mon.AudioMonitor()
    m.set_active(True)
    m.feed(_tone(-30, seconds=0.3))               # loud: above ON_DB
    assert m.signal_present
    m.feed(_tone(-45, seconds=0.3))               # between OFF and ON: stays on
    assert m.signal_present
    m.feed(_tone(-55, seconds=0.5))               # quiet for several frames: drops
    assert not m.signal_present


def test_brief_dip_does_not_drop_signal():
    m = mon.AudioMonitor()
    m.set_active(True)
    m.feed(_tone(-30, seconds=0.3))
    m.feed(_tone(-60, seconds=0.066))             # one quiet frame only
    assert m.signal_present


def test_peak_hold_and_drain():
    m = mon.AudioMonitor()
    m.set_active(True)
    m.feed(np.concatenate([_tone(-20, 0.3), _tone(-60, 0.3)]))
    peak = m.drain_peak()
    assert peak > 0.5                             # the loud part is held
    assert m.drain_peak() < peak                  # then it falls back to the current level


def test_set_active_false_clears_state():
    m = mon.AudioMonitor()
    m.set_active(True)
    m.feed(_tone(-20, 0.3))
    m.set_active(False)
    assert m.level == 0.0 and not m.signal_present and m.feed(_tone(-20, 0.3)) == 0


# ---- SystemMonitor: psutil sampling (mocked) ------------------------------------------------

def test_sample_system_uses_psutil(monkeypatch):
    class FakePsutil:
        @staticmethod
        def cpu_percent(interval=None):
            assert interval is None               # never blocks the sampler
            return 23.0

        @staticmethod
        def virtual_memory():
            class V:
                percent = 41.0
            return V()

    monkeypatch.setattr(mon, "psutil", FakePsutil)
    assert mon.sample_system() == (23.0, 41.0)


def test_sample_system_without_psutil(monkeypatch):
    monkeypatch.setattr(mon, "psutil", None)
    assert mon.sample_system() == (None, None)


@pytest.mark.parametrize("pct,band", [(None, "none"), (10, "green"), (59.9, "green"),
                                      (60, "amber"), (85, "amber"), (85.1, "red"), (99, "red")])
def test_band_thresholds(pct, band):
    assert mon.band_for(pct) == band


# ---- widgets -------------------------------------------------------------------------------

def test_wave_push_updates_history_and_repaints():
    w = MicWaveWidget()
    w.push(0.8, 0.9, True)
    assert w._history[-1] == pytest.approx(0.8) and w._state == "live" and w._present
    assert len(w._history) == 24


def test_wave_turns_red_under_high_cpu():
    w = MicWaveWidget()
    w.push(0.5, 0.5, True)
    w.set_load_band("red")
    assert w.bar_color().name() == "#ef4444"
    w.set_load_band("amber")
    assert w.bar_color().name() == "#f59e0b"
    w.set_load_band("green")
    assert w.bar_color().name() == "#facc15"


def test_wave_flat_states_and_labels():
    w = MicWaveWidget()
    w.set_detection_off()
    assert w._state == "off" and w.label_text() == "PASTOR MIC" and w.isVisible() is False
    assert all(v == 0.0 for v in w._history)
    w.set_no_mic()
    assert w.label_text() == "NO MIC"
    w.grab()                                       # paints the flat no-mic state without error
    w.set_detection_off()
    w.grab()                                       # flat dimmed state


def test_wave_is_fixed_size_and_chip_too():
    w, c = MicWaveWidget(), SysChipWidget()
    assert w.minimumWidth() == w.maximumWidth() == w.width()
    assert c.minimumWidth() == c.maximumWidth() == c.width()


def test_chip_values_and_band():
    c = SysChipWidget()
    c.set_values(23.0, 41.0)
    assert c.cpu_band() == "green"
    c.set_values(91.0, 41.0)
    assert c.cpu_band() == "red"
    c.grab()


# ---- window wiring -------------------------------------------------------------------------

@pytest.fixture
def win(tmp_path):
    proj = ProjectionWindow()
    w = OperatorWindow(ApprovalQueue(None), Theme(), proj, songs_dir=str(tmp_path / "songs"))
    yield w
    w.hide()


class _FakeLive:
    def __init__(self):
        self.mic_calls = []

    def start_mic(self, dev, **kw):
        self.mic_calls.append(kw)

    def use_text_feed(self):
        pass


def test_header_timer_stopped_when_hidden_and_detection_off(win):
    win.show()
    _APP.processEvents()
    assert win._timer.isActive()
    assert win.sys_mon.isRunning()
    assert not win._header_timer.isActive()        # detection off: no 5 fps timer
    win.hide()
    assert not win._timer.isActive() and not win._header_timer.isActive()
    assert not win.sys_mon.isRunning()
    assert not win.audio_mon.active


def test_header_timer_runs_only_visible_and_live(win):
    win.live = _FakeLive()
    win._devices = [object()]
    win.show()
    _APP.processEvents()
    assert not win._header_timer.isActive()        # live not started yet
    win._mic_on = True
    win._refresh_header_state()
    assert win._header_timer.isActive()
    assert win._header_timer.interval() == HEADER_TICK_MS == 200     # 5 fps
    assert win.audio_mon.active
    win._mic_on = False
    win._refresh_header_state()
    assert not win._header_timer.isActive() and not win.audio_mon.active
    win._mic_on = True
    win._refresh_header_state()
    win.hide()
    assert not win._header_timer.isActive() and not win.audio_mon.active
    assert not win.sys_mon.isRunning()


def test_tap_passed_to_start_mic(win, monkeypatch):
    class Dev:
        name = "USB Mic"
    win.live = _FakeLive()
    win._devices = [Dev()]
    win.source_box.setCurrentIndex(1)
    win._apply_source()
    kw = win.live.mic_calls[-1]
    assert kw["tap"] == win.audio_mon.feed


def test_sys_sample_signal_updates_chip_and_wave(win):
    win.show()
    _APP.processEvents()
    win._on_sys_sampled(92.0, 50.0)                # the queued signal lands on the main thread
    assert win.sys_chip._cpu == 92.0 and win.sys_chip._ram == 50.0
    assert win.wave._load == "red"


def test_wave_widget_lives_in_header_only(win):
    win.show()
    _APP.processEvents()
    assert win.wave.parent() is not None
    # exactly one wave and one chip in the window
    assert len(win.findChildren(MicWaveWidget)) == 1
    assert len(win.findChildren(SysChipWidget)) == 1
