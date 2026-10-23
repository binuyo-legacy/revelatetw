import os

import pytest

from revelatetw.theme import Theme
from revelatetw import transitions as tr

# --- offscreen smoke test of the window state machine (needs PyQt6) ------------------------
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QApplication  # noqa: E402
from revelatetw.songs import Slide, Song  # noqa: E402
from revelatetw.ui import ProjectionWindow  # noqa: E402

_APP = QApplication.instance() or QApplication([])


def _song(*labels):
    slides = [Slide(label=l, lines=[f"line {i}"]) for i, l in enumerate(labels)]
    return Song(id="s1", title="Test", artist="", slides=slides), slides


def _live_window(transition="slide", ms=400):
    w = ProjectionWindow()
    w.show_theme(Theme(transition=transition, transition_ms=ms))
    w._live = True          # headless: skip showFullScreen, the state machine is what we test
    return w


def test_slide_change_starts_animation_and_settles():
    w = _live_window()
    song, slides = _song("Verse 1", "Chorus", "Verse 2")
    w.show_song_slide(slides[0], song, 0, 3)
    assert w._anim is not None                   # blank -> first slide animates from the background
    w._stop_anim()
    w.show_song_slide(slides[0], song, 0, 3)     # same content again: no animation
    assert w._anim is None
    w.show_song_slide(slides[1], song, 1, 3)
    assert w._anim is not None and w._anim["style"] == "kinetic" and w._anim["dir"] == 1
    w.show_song_slide(slides[0], song, 0, 3)     # interrupt mid-animation: replaced, short duration
    assert w._anim["dur"] == tr.INTERRUPT_MS and w._anim["dir"] == -1
    w._stop_anim()


def test_zero_ms_or_none_is_instant_cut():
    w = _live_window(ms=0)
    song, slides = _song("Verse 1", "Verse 2")
    w.show_song_slide(slides[0], song, 0, 2)
    w.show_song_slide(slides[1], song, 1, 2)
    assert w._anim is None
    w2 = _live_window(transition="none", ms=400)
    w2.show_song_slide(slides[0], song, 0, 2)
    w2.show_song_slide(slides[1], song, 1, 2)
    assert w2._anim is None


def test_animation_state_resets_on_output_off():
    w = _live_window()
    song, slides = _song("Verse 1", "Verse 2")
    w.show_song_slide(slides[0], song, 0, 2)
    w.show_song_slide(slides[1], song, 1, 2)
    assert w._anim is not None
    w.reset_animation()                          # what hideEvent does when output goes OFF
    assert w._anim is None and not w._timer.isActive() and not w._live


def test_offscreen_composite_paints_background_and_text():
    from PyQt6.QtGui import QImage, QPainter
    w = _live_window(transition="fade", ms=400)
    w.resize(320, 180)
    song, slides = _song("Verse 1", "Verse 2")
    w.show_song_slide(slides[0], song, 0, 2)
    w.show_song_slide(slides[1], song, 1, 2)
    img = QImage(320, 180, QImage.Format.Format_RGB32)
    p = QPainter(img)
    w._paint_anim(p, img.rect(), 0.5)            # mid-transition frame
    p.end()
    assert img.pixelColor(2, 2).alpha() == 255 and img.width() == 320
    w._stop_anim()
