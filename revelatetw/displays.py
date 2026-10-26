"""Display listing for the live output (standalone fullscreen window on a chosen monitor).

Pure data plus a thin Qt adapter. Tests pass stub screens; the GUI passes QScreen objects.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Optional


@dataclass(frozen=True)
class DisplayInfo:
    index: int
    name: str
    x: int
    y: int
    width: int
    height: int
    primary: bool = False

    @property
    def label(self) -> str:
        tag = " (primary)" if self.primary else ""
        return f"{self.index + 1}: {self.name} {self.width}\u00d7{self.height}{tag}"


def displays_from_screens(screens: Iterable[Any], primary: Optional[Any] = None) -> list[DisplayInfo]:
    """screens: objects with name() and geometry() (a QScreen or a stub). primary: the primary one."""
    primary_name = primary.name() if primary is not None else None
    out: list[DisplayInfo] = []
    for i, screen in enumerate(screens):
        g = screen.geometry()
        name = str(screen.name())
        out.append(DisplayInfo(index=i, name=name, x=int(g.x()), y=int(g.y()),
                               width=int(g.width()), height=int(g.height()),
                               primary=primary_name is not None and name == primary_name))
    return out


def list_displays() -> list[DisplayInfo]:
    """Monitors known to Qt right now. Empty when no Qt application is running."""
    try:
        from PyQt6.QtGui import QGuiApplication
    except ImportError:
        return []
    if QGuiApplication.instance() is None:
        return []
    return displays_from_screens(QGuiApplication.screens(), QGuiApplication.primaryScreen())


# Display layout modes. Windows reports a duplicated (mirrored) screen with every display at the
# same origin; an extended layout puts each monitor at its own position on the virtual desktop.
MODE_SINGLE = "single"
MODE_DUPLICATED = "duplicated"
MODE_EXTENDED = "extended"


def output_mode(displays: list[DisplayInfo]) -> str:
    """single: one monitor. duplicated: several monitors sharing one origin (same picture).
    extended: several monitors at different positions (each has its own desktop)."""
    if len(displays) < 2:
        return MODE_SINGLE
    origins = {(d.x, d.y) for d in displays}
    return MODE_DUPLICATED if len(origins) == 1 else MODE_EXTENDED


def is_secondary(displays: list[DisplayInfo], d: DisplayInfo) -> bool:
    """True for the monitor that is not the operator's main screen (the primary, or index 0 when none is flagged)."""
    if any(x.primary for x in displays):
        return not d.primary
    return d.index != 0


def default_output_index(displays: list[DisplayInfo]) -> int:
    """The output monitor picked at startup: the second display in extended mode, otherwise the first."""
    if output_mode(displays) == MODE_EXTENDED:
        for d in displays:
            if is_secondary(displays, d):
                return d.index
    return 0


def mode_note(displays: list[DisplayInfo]) -> str:
    mode = output_mode(displays)
    if mode == MODE_EXTENDED:
        return "extended: the output goes fullscreen on the second monitor"
    if mode == MODE_DUPLICATED:
        return "duplicated: same picture on every monitor, output opens minimized"
    return "one monitor: output opens minimized so it does not cover this window"


def should_fullscreen(displays: list[DisplayInfo], target: int) -> bool:
    """Automatic placement rule: fullscreen only on a secondary monitor in extended mode.
    Everywhere else the output stays minimized (the operator can still pick fullscreen from the menu)."""
    if output_mode(displays) != MODE_EXTENDED:
        return False
    if target < 0 or target >= len(displays):
        return False
    return is_secondary(displays, displays[target])
