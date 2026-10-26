"""Output window placement: single / duplicated / extended displays, the startup state, and the monitor menu."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt6.QtWidgets")

from revelatetw.displays import (DisplayInfo, MODE_DUPLICATED, MODE_EXTENDED, MODE_SINGLE,  # noqa: E402
                                 default_output_index, mode_note, output_mode, should_fullscreen)


def d(i, x, y, w=1920, h=1080, primary=False):
    return DisplayInfo(index=i, name=f"DP-{i}", x=x, y=y, width=w, height=h, primary=primary)


# --- pure rules -----------------------------------------------------------------------------

def test_mode_single_when_one_monitor():
    assert output_mode([d(0, 0, 0, primary=True)]) == MODE_SINGLE
    assert output_mode([]) == MODE_SINGLE


def test_mode_duplicated_when_all_monitors_share_origin():
    # Windows duplicate mode: both displays at (0,0), same picture
    assert output_mode([d(0, 0, 0, primary=True), d(1, 0, 0, 1280, 720)]) == MODE_DUPLICATED


def test_mode_extended_when_monitors_at_different_positions():
    assert output_mode([d(0, 0, 0, primary=True), d(1, 1920, 0, 1280, 720)]) == MODE_EXTENDED


def test_extended_second_monitor_goes_fullscreen_automatically():
    disp = [d(0, 0, 0, primary=True), d(1, 1920, 0, 1280, 720)]
    assert default_output_index(disp) == 1
    assert should_fullscreen(disp, 1) is True
    assert should_fullscreen(disp, 0) is False        # the operator's own screen never gets the auto fullscreen


def test_single_and_duplicated_never_auto_fullscreen():
    single = [d(0, 0, 0, primary=True)]
    dup = [d(0, 0, 0, primary=True), d(1, 0, 0, 1280, 720)]
    for layout in (single, dup):
        assert default_output_index(layout) == 0
        assert should_fullscreen(layout, 0) is False
        assert should_fullscreen(layout, 1) is False


def test_extended_without_primary_flag_uses_index_zero_as_operator_screen():
    disp = [d(0, 0, 0), d(1, 1920, 0)]
    assert default_output_index(disp) == 1
    assert should_fullscreen(disp, 1) is True
    assert should_fullscreen(disp, 0) is False


def test_mode_note_wording():
    single = [d(0, 0, 0, primary=True)]
    dup = [d(0, 0, 0, primary=True), d(1, 0, 0)]
    ext = [d(0, 0, 0, primary=True), d(1, 1920, 0)]
    assert "one monitor" in mode_note(single)
    assert "duplicated" in mode_note(dup)
    assert "extended" in mode_note(ext)


def test_out_of_range_target_is_never_fullscreen():
    assert should_fullscreen([d(0, 0, 0), d(1, 1920, 0)], 5) is False


# --- GUI: startup state, menu, placement ----------------------------------------------------

from PyQt6.QtCore import QRect, Qt  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

_APP = QApplication.instance() or QApplication([])


@pytest.fixture
def window(tmp_path, monkeypatch):
    from revelatetw import ui
    from revelatetw.approval import ApprovalQueue
    from revelatetw.theme import Theme

    def set_layout(layout):
        monkeypatch.setattr(ui, "list_displays", lambda: layout)

    set_layout([d(0, 0, 0, primary=True)])            # default test layout: one monitor
    proj = ui.ProjectionWindow()
    win = ui.OperatorWindow(ApprovalQueue(None), Theme(), proj, songs_dir=str(tmp_path / "songs"))
    win.set_layout = set_layout
    return win, proj


def test_startup_projection_window_is_never_shown_or_fullscreen(window):
    win, proj = window
    assert not win.output.on
    assert not proj.isVisible()
    assert not proj.isFullScreen()


def test_single_monitor_live_on_is_minimized_not_fullscreen(window):
    win, proj = window
    win.toggle_output()
    assert win.output.on
    assert proj.isMinimized()
    assert not proj.isFullScreen()
    win.toggle_output()
    assert not proj.isVisible()


def test_duplicated_monitors_live_on_is_minimized(window):
    win, proj = window
    win.set_layout([d(0, 0, 0, primary=True), d(1, 0, 0, 1280, 720)])
    win._populate_displays(0)
    win.toggle_output()
    assert proj.isMinimized() and not proj.isFullScreen()


def test_extended_second_monitor_live_on_goes_fullscreen_there(window):
    win, proj = window
    win.set_layout([d(0, 0, 0, primary=True), d(1, 1920, 0, 1280, 720)])
    win._populate_displays()                          # startup pick: the second monitor
    assert win.display_box.currentIndex() == 1
    win.toggle_output()
    assert proj.isFullScreen()
    assert proj.geometry() == QRect(1920, 0, 1280, 720)


def test_menu_lists_monitors_and_marks_active(window):
    win, _ = window
    win.set_layout([d(0, 0, 0, primary=True), d(1, 1920, 0, 1280, 720)])
    win._populate_displays(0)
    texts = [a.text() for a in win._output_menu().actions()]
    assert any(t.startswith("Mode: extended") for t in texts)
    assert any(t.startswith("Show on Monitor 1") and "(active)" in t for t in texts)
    assert any(t.startswith("Show on Monitor 2") and "(active)" not in t for t in texts)


def test_menu_pick_puts_output_on_chosen_monitor_fullscreen(window):
    win, proj = window
    win.set_layout([d(0, 0, 0, primary=True), d(1, 1920, 0, 1280, 720)])
    win._populate_displays(0)
    win._output_on_monitor(1)
    assert win.output.on and proj.isFullScreen()
    assert win.display_box.currentIndex() == 1
    assert proj.geometry() == QRect(1920, 0, 1280, 720)


def test_menu_minimize_action_only_when_output_on(window):
    win, proj = window
    labels = [a.text() for a in win._output_menu().actions()]
    assert "Minimize output window" in labels
    off_action = [a for a in win._output_menu().actions() if a.text() == "Minimize output window"][0]
    assert not off_action.isEnabled()
    win.toggle_output()
    on_action = [a for a in win._output_menu().actions() if a.text() == "Minimize output window"][0]
    assert on_action.isEnabled()


def test_projection_right_click_emits_context_menu_request(window):
    from PyQt6.QtGui import QContextMenuEvent
    from PyQt6.QtCore import QPoint
    win, proj = window
    seen = []
    proj.context_menu_requested.connect(lambda p: seen.append(p))
    proj.contextMenuEvent(QContextMenuEvent(QContextMenuEvent.Reason.Mouse, QPoint(5, 5), QPoint(50, 60)))
    assert seen and seen[0] == QPoint(50, 60)
