"""Live output switch. ON = the projection window is shown; OFF = it is hidden, so another app
(for example a fullscreen slide deck on a single-monitor setup) can take the projector.

pill_state() is the single source for the LIVE pill: text, the 'on' property the stylesheet keys
on (green when "true", dimmed red when "false"), and the tooltip. The window calls it every time
the output changes, so the colour always matches the real output state.
"""
from __future__ import annotations


def pill_state(on: bool) -> dict:
    if on:
        return {"text": "\u25cf LIVE", "on": "true",
                "tooltip": "Live output ON: click to hide the projection window (O)"}
    return {"text": "\u25cb OFF", "on": "false",
            "tooltip": "Live output OFF: projection window hidden. Click to show (O)"}


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
        return pill_state(self._on)["text"]

    def pill(self) -> dict:
        return pill_state(self._on)
