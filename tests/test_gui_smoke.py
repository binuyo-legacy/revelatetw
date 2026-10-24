import os
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt6.QtWidgets")

from revelatetw.approval import ApprovalQueue
from revelatetw.songs import Slide, Song
from revelatetw.theme import Theme
from revelatetw.ui import OperatorWindow, ProjectionWindow


from PyQt6.QtWidgets import QApplication

_APP = QApplication.instance() or QApplication([])   # one app for the whole module; never collected


@pytest.fixture
def window(tmp_path):
    proj = ProjectionWindow()
    win = OperatorWindow(ApprovalQueue(None), Theme(), proj, songs_dir=str(tmp_path / "songs"))
    return win, proj


def test_live_pill_toggles_projection_and_state(window):
    win, proj = window
    assert not win.output.on and not proj.isVisible()  # fresh start: projection hidden
    win.toggle_output()
    assert win.output.on and win.live_pill.text().endswith("LIVE")
    win.toggle_output()
    assert not win.output.on and win.live_pill.text().endswith("OFF") and not proj.isVisible()


def test_song_send_direct_and_step(window):
    win, proj = window
    song = Song(title="T", slides=[Slide("Verse 1", ["a"]), Slide("Chorus", ["b"])])
    win._song_sel = song
    win._show_slide_list(song.slides, win.slide_now_list)
    win.song_direct.setChecked(True)
    win._send_slide()
    assert win._kind == "song" and win._song_live == (song, 0)
    win.step_song(+1)
    assert win._song_live[1] == 1
    win.step_song(+1)                       # past the end: stays on the last slide
    assert win._song_live[1] == 1
    win.step_song(-1)
    assert win._song_live[1] == 0


def test_song_waits_for_approval_when_not_direct(window):
    win, _ = window
    song = Song(title="T", slides=[Slide("Verse 1", ["a"])])
    win._song_sel = song
    win._show_slide_list(song.slides, win.slide_now_list)
    win.song_direct.setChecked(False)
    win._send_slide()
    assert win._song_live is None and win._song_pending == (song, 0)
    win.approve_pending_song()
    assert win._song_live == (song, 0)


def test_sermon_slide_needs_title(window):
    win, _ = window
    win.show_sermon_slide()
    assert win._sermon_live is None
    win.sermon_title.setText("Faith in action")
    win.show_sermon_slide()
    assert win._kind == "sermon" and win._sermon_live.title == "Faith in action"
