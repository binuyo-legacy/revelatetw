"""Theme model (spec F3): frames, backgrounds, colours, typography, layouts, transitions.

Themes are JSON, so export/import between machines is a file copy. Assets (images,
video) are referenced by relative path in the portable bundle (not implemented yet).
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Optional

TRANSITIONS = ("fade", "slide", "kinetic")       # spec F3 transition presets
LAYOUTS = ("full", "lower_third")
FRAMES = ("none", "thin", "double", "gold_rule")


@dataclass
class Background:
    kind: str = "solid"                         # solid | linear | radial | image | video
    colors: list[str] = field(default_factory=lambda: ["#0F0B2E"])
    image_path: Optional[str] = None
    video_path: Optional[str] = None


@dataclass
class Theme:
    name: str = "Midnight Gold"
    background: Background = field(default_factory=Background)
    text_color: str = "#F5F3FF"
    reference_color: str = "#D4A017"
    font_family: str = "Georgia"
    font_size_px: int = 64
    font_weight: int = 400
    line_height: float = 1.3
    shadow: bool = True
    outline_px: int = 0
    frame: str = "gold_rule"
    frame_inset_px: int = 80
    layout: str = "full"
    transition: str = "fade"
    transition_ms: int = 400
    translation_accents: dict[str, str] = field(default_factory=dict)  # per-translation colour

    # --- portable file format ---------------------------------------------------
    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    @classmethod
    def from_dict(cls, data: dict) -> "Theme":
        known = {f.name for f in fields(cls)}
        bg = Background(**data.get("background", {}))
        values = {k: v for k, v in data.items() if k in known and k != "background"}
        return cls(background=bg, **values)

    def save(self, path: str | Path) -> None:
        Path(path).write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "Theme":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def ready_made_themes() -> list[Theme]:
    """Starting looks. Spec requires six at launch; these are the first pass."""
    return [
        Theme(name="Midnight Gold"),
        Theme(name="Sanctuary Light", background=Background("solid", ["#F8F5EC"]),
              text_color="#1E1B4B", reference_color="#4C1D95", frame="thin"),
        Theme(name="Royal Indigo", background=Background("linear", ["#1E1B4B", "#4C1D95"]),
              frame="double"),
        Theme(name="Dawn Radial", background=Background("radial", ["#4C1D95", "#0F0B2E"]),
              frame="none", layout="lower_third", transition="slide"),
        Theme(name="Plain Black", background=Background("solid", ["#000000"]), frame="none",
              font_size_px=72, transition="kinetic"),
        Theme(name="Lower Third Gold", background=Background("solid", ["#00000000"]),
              layout="lower_third", font_size_px=44, frame="gold_rule", shadow=True),
    ]
