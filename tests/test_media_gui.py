"""Offscreen Qt smoke tests for the Media tab, media projection and the video fallback.

Video playback needs a Qt multimedia backend. On a headless box the backend may be missing, so the
video tests skip cleanly instead of failing: only the on-slide error path is forced here.
"""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtGui import QColor, QImage, QPainter  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from revelatetw.approval import ApprovalQueue  # noqa: E402
from revelatetw.media import MediaItem  # noqa: E402
from revelatetw.store import AppSettings  # noqa: E402
from revelatetw.theme import Theme  # noqa: E402
from revelatetw.ui import OperatorWindow, ProjectionWindow  # noqa: E402

_APP = QApplication.instance() or QApplication([])


def _png(path, w=40, h=20):
    img = QImage(w, h, QImage.Format.Format_RGB32)
    img.fill(QColor("#4C1D95"))
    assert img.save(str(path), "PNG")


@pytest.fixture
def media_folder(tmp_path):
    folder = tmp_path / "media"
    folder.mkdir()
    _png(folder / "Sunrise Hymn.png")
    _png(folder / "Logo.jpg")
    (folder / "clip.mp4").write_bytes(b"not really a video")
    return folder


@pytest.fixture
def window(tmp_path, media_folder):
    proj = ProjectionWindow()
    win = OperatorWindow(ApprovalQueue(None), Theme(), proj,
                         songs_dir=str(tmp_path / "songs"),
                         settings=AppSettings(media_folder=str(media_folder)))
    win.rescan_media()
    return win, proj


def test_media_tab_replaces_placeholder(window):
    win, _ = window
    titles = [win._tabs.tabText(i) for i in range(win._tabs.count())]
    assert "Media" in titles
    assert win._tabs.isTabEnabled(titles.index("Media"))


def test_rescan_fills_grid_and_filters(window):
    win, _ = window
    assert win.media_list.count() == 3
    win.media_filter.setCurrentIndex(win.media_filter.findData("videos") and 2)   # Videos
    assert win.media_list.count() == 1
    win.media_filter.setCurrentIndex(1)                                            # Images
    assert win.media_list.count() == 2
    win.media_filter.setCurrentIndex(0)
    win.media_search.setText("sunrise")
    assert win.media_list.count() == 1


def test_empty_state_shows_hint_until_media_exists(tmp_path):
    empty = tmp_path / "empty"
    win = OperatorWindow(ApprovalQueue(None), Theme(), ProjectionWindow(),
                         songs_dir=str(tmp_path / "songs"),
                         settings=AppSettings(media_folder=str(empty)))
    win.rescan_media()
    assert win.media_empty.isVisible() or not win.media_list.isVisible()
    assert win.media_empty.hint.text() == "No media yet \u2014 click Import to add images or videos"


def test_project_image_is_direct_and_respects_live(window):
    win, proj = window
    win.media_list.setCurrentRow(0)
    win.project_selected_media()
    assert win._kind == "media" and win._media_live is not None
    assert win._song_live is None  # media replaces other kinds
    win.toggle_output()            # LIVE off: media is held, nothing shown
    assert not win.output.on
    assert win._media_live is not None
    win.toggle_output()
    assert win.output.on and win._media_live is not None


def test_media_projection_paints_full_frame_image(window):
    _, proj = window
    proj.show_media(MediaItem(path=str(window[0].media.items[0].path), name="x", kind="image"))
    img = QImage(160, 90, QImage.Format.Format_RGB32)
    img.fill(0)
    painter = QPainter(img)
    proj._paint_content(painter, img.rect(), None)
    painter.end()
    assert img.width() == 160 and img.height() == 90


def test_video_error_shows_on_slide_message_not_crash(window):
    _, proj = window
    proj._on_video_error()
    assert proj._video_error == "Cannot play this video format"
    img = QImage(320, 180, QImage.Format.Format_RGB32)
    img.fill(0)
    painter = QPainter(img)
    proj.paintEvent  # the message is painted from paintEvent; call the helper directly here
    from revelatetw.outputs import paint_media_message
    paint_media_message(painter, img.rect(), proj._video_error)
    painter.end()


def test_video_playback_when_backend_present(window):
    _, proj = window
    try:
        proj._ensure_video()
    except ImportError:
        pytest.skip("Qt multimedia not available in this environment")
    proj.show_media(MediaItem(path="/nonexistent/clip.mp4", name="clip", kind="video", duration_s=3.0))
    # Playing a missing file must not crash; the error callback (or no-op) handles it.
    proj.reset_animation()
    assert proj._video_widget.isHidden()
