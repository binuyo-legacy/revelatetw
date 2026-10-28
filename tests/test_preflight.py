"""Pre-service checklist logic. Pure Python: no Qt, no audio hardware."""
import math

import pytest

from revelatetw.displays import DisplayInfo
from revelatetw.preflight import (ACTION_AUDIO_SETUP, ACTION_TOGGLE_OUTPUT, INFO, OK, SOUND_HEARD_DB, SUBLINE,
                                  WARN, headline, heard_sound, preflight)

MAIN = DisplayInfo(0, "Laptop", 0, 0, 1920, 1080, primary=True)
PROJ = DisplayInfo(1, "Projector", 1920, 0, 1920, 1080)
MIRROR = DisplayInfo(1, "Projector", 0, 0, 1920, 1080)


def run(**over):
    args = dict(live_available=True, dev=False, mic_on=True, mic_name="Headset Mic", devices_found=True,
                capture_error="", sound_heard=True, displays=[MAIN, PROJ], target_display=1, output_on=True)
    args.update(over)
    return {c.key: c for c in preflight(**args)}


def test_everything_ready():
    checks = run()
    assert [c.state for c in checks.values()] == [OK, OK, OK, OK]
    assert list(checks) == ["mic", "sound", "projector", "output"]
    assert headline(list(checks.values())) == "Ready. Waiting for the sermon"
    assert "Headset Mic" in checks["mic"].text
    assert "Projector" in checks["projector"].text


def test_no_microphone_warns_and_offers_audio_settings():
    c = run(mic_on=False, devices_found=False)
    assert c["mic"].state == WARN and c["mic"].action == ACTION_AUDIO_SETUP
    assert "No microphone found" in c["mic"].text
    assert "sound" not in c                         # no sound check without a listening mic
    assert headline(list(c.values())) == "Getting ready"


def test_microphone_that_failed_shows_the_reason():
    c = run(mic_on=False, capture_error="Mic failed, back to text feed: device busy")
    assert c["mic"].state == WARN and "device busy" in c["mic"].text and c["mic"].action


def test_microphone_not_listening_without_a_reason_still_explains():
    c = run(mic_on=False)
    assert c["mic"].state == WARN and c["mic"].text


def test_no_live_audio_in_a_normal_session_is_a_warning():
    c = run(live_available=False, mic_on=False)
    assert c["mic"].state == WARN and "not available" in c["mic"].text


def test_dev_feed_session_is_informational_not_a_fault():
    c = run(live_available=False, dev=True, mic_on=False)
    assert c["mic"].state == INFO and c["mic"].action == ""


def test_silence_is_info_until_sound_is_heard():
    assert run(sound_heard=False)["sound"].state == INFO
    assert run(sound_heard=True)["sound"].state == OK


@pytest.mark.parametrize("peak,expected", [
    (-120.0, False), (-60.0, False), (SOUND_HEARD_DB - 0.1, False), (SOUND_HEARD_DB, True),
    (-30.0, True), (0.0, True), (None, False), (math.nan, False)])
def test_heard_sound_threshold(peak, expected):
    assert heard_sound(peak) is expected


def test_single_screen_is_informational():
    c = run(displays=[MAIN], target_display=0)["projector"]
    assert c.state == INFO and "One screen" in c.text and c.action == ACTION_AUDIO_SETUP


def test_mirrored_screens_are_ok():
    c = run(displays=[MAIN, MIRROR], target_display=1)["projector"]
    assert c.state == OK and "mirrored" in c.text


def test_output_pointing_at_the_operators_own_screen_warns():
    c = run(displays=[MAIN, PROJ], target_display=0)["projector"]
    assert c.state == WARN and "your own screen" in c.text and c.action == ACTION_AUDIO_SETUP


def test_no_displays_warns():
    assert run(displays=[], target_display=0)["projector"].state == WARN


def test_target_display_out_of_range_warns_instead_of_crashing():
    c = run(displays=[MAIN, PROJ], target_display=7)["projector"]
    assert c.state == WARN


def test_output_off_is_info_with_a_button():
    c = run(output_on=False)["output"]
    assert c.state == INFO and c.action == ACTION_TOGGLE_OUTPUT and "OFF" in c.text


def test_output_off_alone_does_not_make_the_headline_a_warning():
    # Output always starts OFF by design; that must not look like a fault.
    assert headline(list(run(output_on=False).values())) == "Ready. Waiting for the sermon"


def test_every_action_has_a_label_and_nothing_else_does():
    for kw in (dict(), dict(mic_on=False, devices_found=False), dict(output_on=False),
               dict(displays=[MAIN], target_display=0), dict(displays=[MAIN, PROJ], target_display=0)):
        for c in run(**kw).values():
            assert bool(c.action) == bool(c.action_label), c


def test_subline_states_the_approval_rule():
    assert "Nothing reaches the projector until you approve" in SUBLINE
