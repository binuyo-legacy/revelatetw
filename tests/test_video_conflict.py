"""Video conflict: a non-video projection must stop a playing video; media-video must not stop itself.

Runs offscreen with a real ProjectionWindow, but the QMediaPlayer and QVideoWidget are replaced by
stubs (injected before _ensure_video runs), so no Qt multimedia backend is needed.
"""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from revelatetw.detection import Candidate  # noqa: E402
from revelatetw.output_state import media_controls_state  # noqa: E402
from revelatetw.sermon import SermonInfo  # noqa: E402
from revelatetw.songs import Slide  # noqa: E402
from revelatetw.ui import ProjectionWindow  # noqa: E402

_APP = QApplication.instance() or QApplication([])


class _StubPlayer:
    def __init__(self):
        self.calls = []

    def stop(self): self.calls.append("stop")
    def pause(self): self.calls.append("pause")
    def play(self): self.calls.append("play")
    def setPosition(self, ms): self.calls.append(("pos", ms))
    def setSource(self, url): self.calls.append("source")


class _StubWidget:
    def __init__(self):
        self.shown = False

    def setGeometry(self, rect): pass
    def show(self): self.shown = True
    def hide(self): self.shown = False


def _playing_projection():
    """A ProjectionWindow with a 'playing' video (stub player and widget), not on a live output."""
    w = ProjectionWindow()
    w._player = _StubPlayer()
    w._video_widget = _StubWidget()
    w._video_widget.show()
    w._video_active = True
    w._video_paused = False
    w._video_loop = False
    w._video_error = ""
    return w


def _candidate():
    return Candidate(reference="John 3:16", book_id=43, book_name="John", chapter=3, verse=16,
                     translation="KJV", text="For God so loved the world", confidence=100,
                     match_type="exact", snippet="For God so loved the world", id="c1")


def _slide():
    return Slide(label="Verse 1", lines=["Amazing grace"])


def _count_signals(w):
    hits = []
    w.video_state_changed.connect(lambda: hits.append(1))
    return hits


def test_verse_projection_stops_video():
    w = _playing_projection()
    hits = _count_signals(w)
    w.show_verse(_candidate())
    assert "stop" in w._player.calls
    assert w._video_widget.shown is False
    assert w.has_playing_video() is False
    assert hits, "video_state_changed must fire so the Media buttons re-disable"


def test_song_and_sermon_projection_stop_video():
    w = _playing_projection()
    w.show_song_slide(_slide(), None, 0, 1)
    assert w.has_playing_video() is False and w._video_widget.shown is False

    w = _playing_projection()
    w.show_sermon(SermonInfo(title="Grace", speaker="Pastor X", reference="Eph 2:8"), "Church")
    assert w.has_playing_video() is False and w._video_widget.shown is False


def test_blank_stops_video():
    w = _playing_projection()
    hits = _count_signals(w)
    w.show_blank()
    assert "stop" in w._player.calls and w.has_playing_video() is False
    assert hits


def test_media_video_does_not_stop_itself():
    """Re-setting the same media-video key must not stop the video it is playing."""
    w = _playing_projection()
    w._set_content(None, ("media-video", "/x/clip.mp4", False), ("media",), 0, "")
    assert "stop" not in w._player.calls
    assert w.has_playing_video() is True


def test_verse_then_video_then_verse_leaves_no_ghost_video():
    w = _playing_projection()
    w.show_verse(_candidate())                           # verse -> video stopped
    assert w.has_playing_video() is False
    w._video_active = True                               # a new video starts playing
    w._video_widget.show()
    w._set_content(None, ("media-video", "/x/clip.mp4", False), ("media",), 0, "")
    assert w.has_playing_video() is True                 # media keeps the screen
    w.show_verse(_candidate())                           # then a verse replaces it
    assert w.has_playing_video() is False and w._video_widget.shown is False


def test_button_state_resets_after_verse_replaces_video():
    """The Media buttons are driven by has_playing_video; after a verse they must be disabled."""
    w = _playing_projection()
    before = media_controls_state("video", True, False, w.has_playing_video(), w.is_video_paused())
    assert before["enabled"] is True
    w.show_verse(_candidate())
    after = media_controls_state("verse", True, False, w.has_playing_video(), w.is_video_paused())
    assert after["enabled"] is False


def test_video_error_emits_state_change():
    w = _playing_projection()
    hits = _count_signals(w)
    w._on_video_error()
    assert hits
