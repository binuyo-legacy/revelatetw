"""Slide transition maths (headless-safe, no Qt imports).

The projection window (ui.ProjectionWindow) asks this module what to draw at time t. Everything
here is pure: easing, direction mapping, chorus detection, interrupt timing and the per-frame
layout of the outgoing and incoming frames. The painter only applies the numbers it gets back.
"""
from __future__ import annotations

import re
from typing import Optional

ANIMATED = ("fade", "slide", "kinetic")
CUT = ("none", "instant")            # no animation: the new frame replaces the old one at once
FRAME_MS = 16                        # about 60 fps timer tick
INTERRUPT_MS = 120                   # a change that arrives mid-transition finishes this fast
KINETIC_SCALE_FROM = 1.03            # incoming frame starts slightly zoomed and settles to 1.0
KINETIC_ALPHA_FROM = 0.6             # and fades in from partial opacity (slight fade)

_CHORUS = re.compile(r"(?<![\w-])chorus\b")   # 'Chorus', 'Chorus 2'; not 'Pre-chorus'


def is_valid_transition(name: str) -> bool:
    return name in ANIMATED or name in CUT


def is_cut(style: str, duration_ms: int) -> bool:
    """True when the change should be an instant cut (no animation frames at all)."""
    return style not in ANIMATED or duration_ms <= 0


def direction_for(prev: Optional[tuple], new: tuple) -> int:
    """+1 = forward (new enters from the right), -1 = backward (enters from the left).

    prev and new are (group, index): group is the song or the kind of slide (verse, sermon,
    blank). Moving to an earlier slide in the same group is backward; anything else is forward.
    """
    if prev is None or prev[0] != new[0]:
        return 1
    return -1 if new[1] < prev[1] else 1


def is_chorus(section: str) -> bool:
    return bool(_CHORUS.search((section or "").strip().lower()))


def effective_style(theme_transition: str, prev_section: str, new_section: str) -> str:
    """Pick the motion for one change.

    Entering a chorus from another section uses kinetic when the theme is slide or kinetic.
    A theme set to fade keeps its cross-fade (the operator chose fade on purpose).
    """
    if theme_transition in CUT:
        return "none"
    if theme_transition not in ANIMATED:
        return "none"
    if theme_transition in ("slide", "kinetic") and is_chorus(new_section) \
            and (prev_section or "").strip().lower() != (new_section or "").strip().lower():
        return "kinetic"
    return theme_transition


def progress(elapsed_ms: float, duration_ms: float) -> float:
    if duration_ms <= 0:
        return 1.0
    return min(1.0, max(0.0, elapsed_ms / duration_ms))


def ease_out_cubic(t: float) -> float:
    t = min(1.0, max(0.0, t))
    return 1.0 - (1.0 - t) ** 3


def interrupt_duration(duration_ms: int) -> int:
    """Duration for a change that lands while a transition is still running."""
    return min(int(duration_ms), INTERRUPT_MS)


def compose_layout(style: str, t: float, direction: int, width: float) -> dict:
    """Where the outgoing (old_*) and incoming (new_*) frames sit at progress t in 0..1.

    dx is a horizontal offset in pixels, alpha is opacity 0..1, scale is around the centre.
    fade: old stays opaque underneath, new fades in on top (a cross-fade).
    slide: old pushed out opposite to direction, new pushed in from direction's side.
    kinetic: slide, the old fades out, the new fades in from partial opacity while scaling 1.03 -> 1.0.
    """
    e = ease_out_cubic(t)
    d = 1 if direction >= 0 else -1
    if style == "fade":
        return {"old_dx": 0.0, "old_alpha": 1.0, "old_scale": 1.0,
                "new_dx": 0.0, "new_alpha": e, "new_scale": 1.0}
    if style == "slide":
        return {"old_dx": -d * width * e, "old_alpha": 1.0, "old_scale": 1.0,
                "new_dx": d * width * (1.0 - e), "new_alpha": 1.0, "new_scale": 1.0}
    if style == "kinetic":
        return {"old_dx": -d * width * e, "old_alpha": 1.0 - e, "old_scale": 1.0,
                "new_dx": d * width * (1.0 - e),
                "new_alpha": KINETIC_ALPHA_FROM + (1.0 - KINETIC_ALPHA_FROM) * e,
                "new_scale": KINETIC_SCALE_FROM - (KINETIC_SCALE_FROM - 1.0) * e}
    return {"old_dx": 0.0, "old_alpha": 1.0, "old_scale": 1.0,
            "new_dx": 0.0, "new_alpha": 1.0, "new_scale": 1.0}
