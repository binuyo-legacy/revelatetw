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


def media_controls_state(media_kind: str | None, output_on: bool, blank: bool,
                         projected: bool, paused: bool) -> dict:
    """Enable state and labels for the Pause/Resume and Restart video buttons (Media tab).

    Enabled only while a video is actually projected on an output that is ON and not blanked.
    Otherwise the tooltip says why, so the operator is never left guessing.
    """
    if media_kind != "video":
        reason = "Pause and restart work on projected videos only. Select a video and click Project."
    elif not projected:
        reason = "No video is projected. Select a video and click Project first."
    elif not output_on:
        reason = "Live output is OFF. Turn it on (O) to control the video."
    elif blank:
        reason = "Output is blanked. Unblank (B) to control the video."
    else:
        reason = ""
    enabled = not reason
    pause_text = "Resume video" if paused else "Pause video"
    if enabled:
        pause_tip = ("Resume the projected video from where it paused" if paused
                     else "Pause the projected video (it stays paused until you resume)")
        restart_tip = "Restart the projected video from the beginning and play it"
    else:
        pause_tip = restart_tip = reason
    return {"enabled": enabled, "pause_text": pause_text, "pause_tip": pause_tip,
            "restart_tip": restart_tip}
