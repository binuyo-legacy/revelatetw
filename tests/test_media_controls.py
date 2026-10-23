"""Media playback controls: pure state mapping (always) and projection pause/restart logic with a
stubbed player (no Qt multimedia backend needed)."""
from revelatetw.output_state import media_controls_state


def test_disabled_when_not_a_video():
    st = media_controls_state("image", True, False, False, False)
    assert st["enabled"] is False and "video" in st["pause_tip"].lower()


def test_disabled_when_nothing_projected():
    st = media_controls_state("video", True, False, False, False)
    assert st["enabled"] is False and "Project" in st["restart_tip"]


def test_disabled_when_output_off_or_blank():
    assert media_controls_state("video", False, False, True, False)["enabled"] is False
    assert media_controls_state("video", True, True, True, False)["enabled"] is False


def test_enabled_while_video_projected_and_labels_toggle():
    st = media_controls_state("video", True, False, True, False)
    assert st["enabled"] is True and st["pause_text"] == "Pause video"
    st = media_controls_state("video", True, False, True, True)
    assert st["enabled"] is True and st["pause_text"] == "Resume video"
    assert "Resume" in st["pause_tip"]


class _StubPlayer:
    def __init__(self):
        self.calls = []

    def pause(self): self.calls.append("pause")
    def play(self): self.calls.append("play")
    def setPosition(self, ms): self.calls.append(("pos", ms))



def _make():
    # Bind the real methods from ProjectionWindow onto a plain object with a stub player.
    from revelatetw.ui import ProjectionWindow
    o = type("P", (), {})()
    o._player = _StubPlayer()
    o._video_active = True
    o._video_paused = False
    o._video_loop = False
    for name in ("has_playing_video", "is_video_paused", "pause_video", "resume_video",
                 "toggle_video_pause", "restart_video", "_rewind_and_play"):
        setattr(o, name, getattr(ProjectionWindow, name).__get__(o))
    return o


def test_pause_resume_toggle_calls_player_and_is_idempotent():
    o = _make()
    assert o.pause_video() is True and o.is_video_paused()
    assert o.pause_video() is False                       # already paused: no-op
    assert o.resume_video() is True and not o.is_video_paused()
    assert o.resume_video() is False                      # not paused: no-op
    o.toggle_video_pause(); assert o.is_video_paused()
    o.toggle_video_pause(); assert not o.is_video_paused()
    assert o._player.calls == ["pause", "play", "pause", "play"]


def test_restart_rewinds_to_zero_and_clears_paused():
    o = _make()
    o.pause_video()
    assert o.restart_video() is True
    assert o._player.calls[-2:] == [("pos", 0), "play"]
    assert not o.is_video_paused()


def test_controls_are_noops_without_a_video():
    o = _make()
    o._video_active = False
    assert o.pause_video() is False and o.resume_video() is False and o.restart_video() is False
    assert o._player.calls == []
