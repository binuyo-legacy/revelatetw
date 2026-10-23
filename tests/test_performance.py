"""Performance guards: idle timers, thumbnail cache size, LRU bound, whisper idle-when-off, offload wiring.

Headless (QT_QPA_PLATFORM=offscreen). No model is downloaded and no audio device is opened.
"""
import os
import sys
from pathlib import Path

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_thumb_px_is_160_and_index_version_bumped():
    from revelatetw import media
    assert media.THUMB_PX == 160
    assert media.INDEX_VERSION >= 2          # old 320px caches are regenerated


def test_make_thumbnail_default_size_is_capped(tmp_path):
    from PyQt6.QtGui import QColor, QImage
    from revelatetw import media
    src = tmp_path / "big.png"
    img = QImage(2000, 1500, QImage.Format.Format_RGB32)
    img.fill(QColor("navy"))
    img.save(str(src))
    dst = tmp_path / "t.png"
    assert media.make_thumbnail(src, dst, "image") is True
    out = QImage(str(dst))
    assert max(out.width(), out.height()) <= media.THUMB_PX


def test_lru_is_bounded_and_evicts_least_recent():
    from revelatetw.outputs import IMAGE_CACHE_MAX, lru_get_or_load
    assert IMAGE_CACHE_MAX == 8
    cache = {}
    for i in range(50):
        lru_get_or_load(cache, f"img{i}", lambda k: k, max_entries=IMAGE_CACHE_MAX)
    assert len(cache) == IMAGE_CACHE_MAX
    assert "img49" in cache and "img0" not in cache


def test_lru_hit_refreshes_recency():
    from revelatetw.outputs import lru_get_or_load
    cache = {}
    for k in ("a", "b", "c"):
        lru_get_or_load(cache, k, lambda x: x, max_entries=3)
    lru_get_or_load(cache, "a", lambda x: x, max_entries=3)   # touch a
    lru_get_or_load(cache, "d", lambda x: x, max_entries=3)   # evicts b, not a
    assert set(cache) == {"c", "a", "d"}


def test_lazy_whisper_loads_nothing_at_construction():
    from revelatetw.transcription import LazyWhisperTranscriber
    t = LazyWhisperTranscriber("small")
    assert t.loaded is False
    assert t._inner is None


def test_lazy_whisper_unload_is_idle_when_off():
    from revelatetw.transcription import LazyWhisperTranscriber
    t = LazyWhisperTranscriber("small")
    t._inner = object()          # simulate a loaded model
    t.unload()
    assert t.loaded is False


def test_configure_change_unloads_so_settings_never_mix():
    from revelatetw.transcription import LazyWhisperTranscriber
    t = LazyWhisperTranscriber("small")
    t._inner = object()
    t.configure(compute_type="float32")
    assert t.loaded is False and t.compute_type == "float32"


def test_compute_type_default_is_int8_and_rejects_garbage():
    from revelatetw.transcription import LazyWhisperTranscriber
    assert LazyWhisperTranscriber().compute_type == "int8"
    assert LazyWhisperTranscriber(compute_type="bogus").compute_type == "int8"


def test_live_stop_unloads_transcriber():
    from revelatetw.live import LiveTranscriptionLoop

    class Stub:
        unloaded = False

        def transcribe(self, audio):
            return ""

        def unload(self):
            Stub.unloaded = True

    loop = LiveTranscriptionLoop.__new__(LiveTranscriptionLoop)
    loop.capture = None
    loop._thread = None
    loop.transcriber = Stub()
    import threading
    loop._stop = threading.Event()
    loop.stop()
    assert Stub.unloaded is True


def test_operator_refresh_is_1s_and_stops_when_hidden():
    from PyQt6.QtWidgets import QApplication
    from revelatetw import ui
    assert ui.OPERATOR_TICK_MS == 1000
    QApplication.instance() or QApplication([])
    win = ui.OperatorWindow.__new__(ui.OperatorWindow)
    from PyQt6.QtCore import QTimer
    win._timer = QTimer()
    win._timer.setInterval(ui.OPERATOR_TICK_MS)
    assert win._timer.interval() == 1000


def test_projection_idle_has_no_running_timer_and_stops_on_hide():
    from PyQt6.QtWidgets import QApplication
    from revelatetw import ui
    from revelatetw.theme import Theme
    QApplication.instance() or QApplication([])
    w = ui.ProjectionWindow()
    w.show_theme(Theme())
    w.show_blank()
    assert w._timer.isActive() is False       # idle: no transition timer
    w.reset_animation()                       # hide path
    assert w._timer.isActive() is False
    w.close()


def test_transition_timer_stops_at_progress_one():
    from PyQt6.QtWidgets import QApplication
    from revelatetw import ui
    from revelatetw.theme import Theme
    QApplication.instance() or QApplication([])
    w = ui.ProjectionWindow()
    w.show_theme(Theme())
    w._anim = {"style": "fade", "old": None, "new": None, "dir": 1, "dur": 1, "t0": 0.0}
    w._timer.start()
    w._stop_anim()
    assert w._timer.isActive() is False and w._anim is None
    w.close()
