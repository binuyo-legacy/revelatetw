import pytest

from revelatetw.theme import TRANSITIONS, Theme
from revelatetw import transitions as tr


def test_transition_validation_accepts_none_and_instant():
    assert "none" in TRANSITIONS and "instant" in TRANSITIONS
    for name in ("fade", "slide", "kinetic", "none", "instant"):
        t = Theme(transition=name)
        assert not [p for p in t.problems() if "transition" in p], name
    assert any("transition must be one of" in p for p in Theme(transition="spin").problems())
    assert tr.is_valid_transition("instant") and tr.is_valid_transition("kinetic")
    assert not tr.is_valid_transition("spin")


def test_cut_for_none_instant_and_zero_ms():
    assert tr.is_cut("none", 400) and tr.is_cut("instant", 400)
    assert tr.is_cut("fade", 0)
    assert not tr.is_cut("fade", 400)
    assert tr.effective_style("instant", "", "Chorus") == "none"


def test_direction_forward_and_backward():
    assert tr.direction_for(None, ("song", 0)) == 1
    assert tr.direction_for(("song", 2), ("song", 3)) == 1       # forward
    assert tr.direction_for(("song", 3), ("song", 2)) == -1      # backward
    assert tr.direction_for(("song", 2), ("song", 2)) == 1       # same index: treated as forward
    assert tr.direction_for(("song", 3), ("verse", 0)) == 1      # group change: forward


def test_chorus_detection_and_kinetic_mapping():
    assert tr.is_chorus("Chorus") and tr.is_chorus("chorus 2")
    assert not tr.is_chorus("Pre-chorus") and not tr.is_chorus("Verse 1")
    assert tr.effective_style("slide", "Verse 1", "Chorus") == "kinetic"
    assert tr.effective_style("slide", "Chorus", "Chorus") == "slide"   # same section: no kinetic
    assert tr.effective_style("fade", "Verse 1", "Chorus") == "fade"    # fade stays fade


def test_easing_and_progress_bounds():
    assert tr.progress(0, 400) == 0.0
    assert tr.progress(1000, 400) == 1.0
    assert tr.progress(10, 0) == 1.0
    assert tr.ease_out_cubic(0) == 0 and tr.ease_out_cubic(1) == 1
    assert tr.ease_out_cubic(0.5) > 0.5                                  # ease-out front-loads motion


def test_fade_crossfade_layout():
    start = tr.compose_layout("fade", 0.0, 1, 1920)
    end = tr.compose_layout("fade", 1.0, 1, 1920)
    assert start["new_alpha"] == 0 and end["new_alpha"] == 1
    assert start["old_alpha"] == 1 and start["old_dx"] == 0


def test_slide_direction_follows_nav():
    fwd = tr.compose_layout("slide", 0.0, 1, 1000)
    back = tr.compose_layout("slide", 0.0, -1, 1000)
    assert fwd["new_dx"] == 1000 and back["new_dx"] == -1000     # forward enters from the right
    assert fwd["old_dx"] == 0 and back["old_dx"] == 0
    end = tr.compose_layout("slide", 1.0, 1, 1000)
    assert end["new_dx"] == 0 and end["old_dx"] == -1000         # old pushed out to the left


def test_kinetic_scale_and_fade():
    start = tr.compose_layout("kinetic", 0.0, 1, 1000)
    end = tr.compose_layout("kinetic", 1.0, 1, 1000)
    assert start["new_scale"] == pytest.approx(tr.KINETIC_SCALE_FROM)
    assert end["new_scale"] == pytest.approx(1.0)
    assert start["new_alpha"] == pytest.approx(tr.KINETIC_ALPHA_FROM) and end["new_alpha"] == 1
    assert start["old_alpha"] == 1 and end["old_alpha"] == 0


def test_interrupt_is_fast_and_never_longer():
    assert tr.interrupt_duration(400) == tr.INTERRUPT_MS
    assert tr.interrupt_duration(50) == 50


def test_timer_tick_is_about_60fps():
    assert 15 <= tr.FRAME_MS <= 17


