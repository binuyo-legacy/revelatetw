"""Live output switch. ON = the projection window is shown; OFF = it is hidden, so another app
(for example a fullscreen slide deck on a single-monitor setup) can take the projector.
"""
from __future__ import annotations


class LiveOutputState:
    def __init__(self, on: bool = True):
        self._on = bool(on)

    @property
    def on(self) -> bool:
        return self._on

    def set(self, on: bool) -> bool:
        self._on = bool(on)
        return self._on

    def toggle(self) -> bool:
        return self.set(not self._on)

    def pill_text(self) -> str:
        return "\u25cf LIVE" if self._on else "\u25cb OFF"
