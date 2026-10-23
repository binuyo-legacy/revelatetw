"""Output routing (spec F5).

Projector and window outputs are real Qt windows (see ui.py). NDI and virtual camera are
stubs: NDI is license-gated (spec section 10) and off by default; the virtual camera needs
a DirectShow / Media Foundation driver component that is not part of this scaffold.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class OutputSink(Protocol):
    name: str
    def push_frame(self, rgba: bytes, width: int, height: int) -> None: ...
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

    def push_frame(self, rgba: bytes, width: int, height: int) -> None:
        if not self.enabled:
            raise RuntimeError("NDI output is disabled until the licence review is complete")
        raise NotImplementedError("NDI SDK sender not implemented in scaffold")

    def close(self) -> None:
        pass


class VirtualCameraSink:
    """Stub. Real build: DirectShow + Media Foundation virtual camera (spec F5)."""
    name = "virtual_camera"

    def push_frame(self, rgba: bytes, width: int, height: int) -> None:
        raise NotImplementedError("virtual camera driver not implemented in scaffold")

    def close(self) -> None:
        pass
