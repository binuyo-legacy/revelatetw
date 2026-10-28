"""Pre-service checklist: is the microphone listening, is sound arriving, which screen is the
projector, and is the output on.

Pure Python (no Qt) so it is unit-tested. The Verses tab shows the result as a "Getting ready" card
until the first words are transcribed (see OperatorWindow._update_checklist).

Each check is one of three states:
  ok    nothing to do
  warn  something is wrong and the service will not work properly until it is fixed
  info  worth knowing, not a fault (for example the output is off until the operator turns it on)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .displays import (DisplayInfo, MODE_DUPLICATED, MODE_EXTENDED, MODE_SINGLE, output_mode,
                       should_fullscreen)

OK, WARN, INFO = "ok", "warn", "info"

# What pressing a check's button does. The window maps these to real actions.
ACTION_AUDIO_SETUP = "audio_setup"       # open the Audio & display section
ACTION_TOGGLE_OUTPUT = "toggle_output"   # same as the LIVE pill

# A peak level above this (in dB, relative to full scale) means the microphone is picking up sound.
# Silence reads about -120 dB, room noise about -60 dB, speech from a few feet away well above -40 dB.
SOUND_HEARD_DB = -55.0


@dataclass(frozen=True)
class Check:
    key: str                 # mic | sound | projector | output
    state: str               # ok | warn | info
    text: str
    action: str = ""         # "" or one of the ACTION_* values
    action_label: str = ""


def heard_sound(peak_db: Optional[float]) -> bool:
    """True when a level reading shows real sound (not silence, and not a missing/invalid reading)."""
    if peak_db is None or peak_db != peak_db:      # None or NaN
        return False
    return peak_db >= SOUND_HEARD_DB


def _mic_check(*, live_available: bool, dev: bool, mic_on: bool, mic_name: str,
               devices_found: bool, capture_error: str) -> Check:
    if not live_available:
        if dev:
            return Check("mic", INFO, "Dev text feed: type sentences in the box under the transcript.")
        return Check("mic", WARN, "Live listening is not available in this session.")
    if mic_on:
        return Check("mic", OK, f"Listening to {mic_name}" if mic_name else "Listening to the microphone")
    if not devices_found:
        return Check("mic", WARN, "No microphone found. Plug one in, then press Rescan.",
                     ACTION_AUDIO_SETUP, "Open audio settings")
    return Check("mic", WARN, capture_error or "The microphone is not listening.",
                 ACTION_AUDIO_SETUP, "Open audio settings")


def _projector_check(displays: list[DisplayInfo], target: int) -> Check:
    mode = output_mode(displays)
    if not displays:
        return Check("projector", WARN, "No display found.", ACTION_AUDIO_SETUP, "Choose display")
    if mode == MODE_SINGLE:
        return Check("projector", INFO,
                     "One screen only. Connect the projector and press Rescan for a fullscreen output.",
                     ACTION_AUDIO_SETUP, "Choose display")
    if mode == MODE_DUPLICATED:
        return Check("projector", OK, "Screens are mirrored: the projector shows this screen.")
    if 0 <= target < len(displays) and should_fullscreen(displays, target):
        return Check("projector", OK, f"Projector: {displays[target].label}")
    name = displays[target].label if 0 <= target < len(displays) else "an unknown screen"
    return Check("projector", WARN, f"Output is set to {name}, which is your own screen. "
                                     "Choose the projector.", ACTION_AUDIO_SETUP, "Choose display")


def _output_check(output_on: bool) -> Check:
    if output_on:
        return Check("output", OK, "Output is ON: the projector shows what you approve.")
    return Check("output", INFO, "Output is OFF: nothing is on the projector yet. Press O when you are ready.",
                 ACTION_TOGGLE_OUTPUT, "Turn output on")


def preflight(*, live_available: bool, dev: bool, mic_on: bool, mic_name: str, devices_found: bool,
              capture_error: str, sound_heard: bool, displays: list[DisplayInfo], target_display: int,
              output_on: bool) -> list[Check]:
    """The checklist, in the order the operator should look at it."""
    checks = [_mic_check(live_available=live_available, dev=dev, mic_on=mic_on, mic_name=mic_name,
                         devices_found=devices_found, capture_error=capture_error)]
    if mic_on:
        if sound_heard:
            checks.append(Check("sound", OK, "Hearing sound."))
        else:
            checks.append(Check("sound", INFO, "No sound yet. Speak into the microphone to check the level."))
    checks.append(_projector_check(displays, target_display))
    checks.append(_output_check(output_on))
    return checks


def headline(checks: list[Check]) -> str:
    """Card title: asks for attention while any check is a warning, otherwise says the app is ready."""
    if any(c.state == WARN for c in checks):
        return "Getting ready"
    return "Ready. Waiting for the sermon"


SUBLINE = "Verses the app hears appear in the Approval Queue. Nothing reaches the projector until you approve it."
