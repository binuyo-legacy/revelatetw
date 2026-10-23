"""Output routing (spec F5).

Routes for feeding OBS / streaming / recording software from the projection output:

  1. Window capture (default, no extra software): the projection window is borderless and
     titled 'RevelateTW output'. In OBS add a 'Window Capture' source and pick it. Works on
     any Windows PC. See SETUP.md.
  2. Virtual camera (optional): VirtualCameraSink sends RGB frames through pyvirtualcam to
     the OBS Virtual Camera driver (free, installed with OBS 26+). Install with
     `pip install pyvirtualcam` and start the virtual camera once in OBS.
  3. NDI: gated. Needs the NDI SDK (licence review, spec section 10). Not shipped.

Spout (GPU texture sharing) is not used; SpoutGL would need a Spout-capable OBS
plugin, and window capture covers the same case without it.

Frames are plain RGB bytes so the Qt widget and any sink share one format.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol

PROJECTION_WINDOW_TITLE = "RevelateTW output"


class OutputSink(Protocol):
    name: str
    def push_frame(self, rgb: bytes, width: int, height: int) -> None: ...
    def close(self) -> None: ...


@dataclass
class ResolutionOption:
    width: int
    height: int
    fps: int = 30


RESOLUTIONS = [ResolutionOption(1920, 1080, 30), ResolutionOption(1280, 720, 30),
               ResolutionOption(1920, 1080, 60)]   # 60 fps on capable hardware only


class NDISink:
    """Gated: spec section 10 requires NDI licence review before this ships."""
    name = "ndi"
    enabled = False  # feature flag

    def push_frame(self, rgb: bytes, width: int, height: int) -> None:
        raise RuntimeError("NDI output is disabled until the licence review is complete. "
                           "Use the OBS window capture route (SETUP.md).")

    def close(self) -> None:
        pass


class VirtualCameraSink:
    """Feeds the OBS Virtual Camera via pyvirtualcam (optional dependency)."""
    name = "virtual_camera"

    def __init__(self, width: int = 1920, height: int = 1080, fps: int = 30):
        import pyvirtualcam  # lazy: raises ImportError if not installed
        self._cam = pyvirtualcam.Camera(width=width, height=height, fps=fps, fmt=pyvirtualcam.PixelFormat.RGB)
        self.width, self.height = width, height

    @property
    def device(self) -> str:
        return self._cam.device

    def push_frame(self, rgb: bytes, width: int, height: int) -> None:
        if (width, height) != (self.width, self.height):
            raise ValueError(f"frame is {width}x{height}, camera is {self.width}x{self.height}")
        self._cam.send(_as_array(rgb, width, height))
        self._cam.sleep_until_next_frame()

    def close(self) -> None:
        self._cam.close()


def _as_array(rgb: bytes, width: int, height: int):
    import numpy as np
    return np.frombuffer(rgb, dtype=np.uint8).reshape(height, width, 3)


def virtual_camera_available() -> bool:
    try:
        import pyvirtualcam  # noqa: F401
        return True
    except ImportError:
        return False


def grab_rgb(widget) -> Optional[tuple[bytes, int, int]]:
    """Render a Qt widget to RGB bytes for a sink. Needs PyQt6 and a running app."""
    from PyQt6.QtGui import QImage
    pix = widget.grab()
    img = pix.toImage().convertToFormat(QImage.Format.Format_RGB888)
    w, h = img.width(), img.height()
    ptr = img.constBits()
    ptr.setsize(img.sizeInBytes())
    # Rows are padded to 4 bytes; strip the padding so the layout is tight width*3.
    stride = img.bytesPerLine()
    raw = bytes(ptr)
    if stride != w * 3:
        raw = b"".join(raw[r * stride:r * stride + w * 3] for r in range(h))
    return raw, w, h
