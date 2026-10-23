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
