"""Live screen: the collapsible Audio & display section and the single status line.

Runs headless like the other GUI tests (QT_QPA_PLATFORM=offscreen).
"""
import os
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QApplication

from revelatetw.approval import ApprovalQueue
from revelatetw.theme import Theme
from revelatetw.ui import OperatorWindow, ProjectionWindow

_APP = QApplication.instance() or QApplication([])


def _make(tmp_path):
    return OperatorWindow(ApprovalQueue(None), Theme(), ProjectionWindow(), songs_dir=str(tmp_path / "songs"))


@pytest.fixture
def win(tmp_path, monkeypatch):
    """A window whose audio input is healthy (the normal case at a church)."""
    monkeypatch.setattr(OperatorWindow, "_populate_devices",
                        lambda self: self.source_status.setText("Listening: Test Mic"))
    return _make(tmp_path)


def test_setup_section_is_collapsed_when_audio_is_healthy(win):
    assert win.setup_box.isHidden()
    assert not win.setup_summary.isHidden()
    assert not win.btn_setup.isChecked()
    assert win.btn_setup.text().endswith("▸")


def test_toggle_swaps_section_and_summary(win):
    win.btn_setup.setChecked(True)
    assert not win.setup_box.isHidden() and win.setup_summary.isHidden()
    assert win.btn_setup.text().endswith("▾")
    win.btn_setup.setChecked(False)
    assert win.setup_box.isHidden() and not win.setup_summary.isHidden()


def test_setup_controls_live_inside_the_section(win):
    for name in ("display_box", "btn_rescan", "device_box", "gain", "meter", "source_status"):
        assert win.setup_box.isAncestorOf(getattr(win, name)), name


def test_summary_names_mic_and_display_without_warning(win):
    win.refresh()
    text = win.setup_summary.text()
    assert "Test Mic" in text
    assert "⚠" not in text
    assert win.setup_box.isHidden()


def test_a_problem_opens_the_section_once(win):
    win.source_status.setText("Mic failed at startup: no device")
    win.refresh()
    assert "⚠" in win.setup_summary.text()
    assert win.btn_setup.isChecked()
    win.btn_setup.setChecked(False)          # the operator closes it...
    win.refresh()
    assert not win.btn_setup.isChecked()     # ...and it stays closed
    assert "⚠" in win.setup_summary.text()   # the warning sign remains in the summary


def test_no_audio_outside_dev_mode_starts_open(tmp_path):
    w = _make(tmp_path)                      # live=None, not --dev: "Live audio not available"
    assert w.btn_setup.isChecked()
    assert "⚠" in w.setup_summary.text()


def test_status_line_says_when_output_is_off(win):
    win.refresh()
    assert not win.output.on
    assert win.footer_proj.text().startswith("Output off")
    assert win.footer_proj.objectName() == "footerWarn"
    win.toggle_output()
    assert win.footer_proj.text() in ("Projecting", "Blanked", "Idle")
    assert win.footer_proj.objectName() in ("footerOk", "footer")


def test_auto_approve_is_amber_in_the_status_bar(win):
    win.settings.auto_approve = True
    win._apply_auto_label()
    assert win.status_auto.objectName() == "footerWarn"
    assert "ON" in win.status_auto.text()
    win.settings.auto_approve = False
    win._apply_auto_label()
    assert win.status_auto.objectName() == "footer"


@pytest.mark.parametrize("name", ["transcriber_label", "latency_label", "auto_label", "cleared_label",
                                  "tile_feed", "tile_audio", "footer_sync"])
def test_duplicate_status_widgets_are_gone(win, name):
    assert not hasattr(win, name)


def test_status_bar_still_carries_the_session_status(win):
    for name in ("status_transcriber", "status_latency", "status_auto", "status_cleared"):
        assert getattr(win, name).text(), name


def test_approve_is_the_primary_button(win):
    assert win.btn_approve.objectName() == "approve"
    assert win.btn_reject.objectName() == "reject"
    assert win.btn_hold.objectName() == "subtle" and win.btn_blank.objectName() == "subtle"
    assert win.list.objectName() == "queueList"
