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
BACKGROUND_KINDS = ("solid", "linear", "radial", "image", "video")


def is_hex_color(value: str) -> bool:
    import re
    return bool(re.fullmatch(r"#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{8})", str(value)))


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

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Theme":
        """Tolerant loader: unknown keys are ignored so newer theme files still open."""
        known = {f.name for f in fields(cls)}
        bg_known = {f.name for f in fields(Background)}
        bg_raw = data.get("background") or {}
        bg = Background(**{k: v for k, v in bg_raw.items() if k in bg_known})
        values = {k: v for k, v in data.items() if k in known and k != "background"}
        return cls(background=bg, **values)

    def problems(self) -> list[str]:
        """Human-readable list of anything the renderer cannot draw. Empty means valid."""
        errs = []
        if self.background.kind not in BACKGROUND_KINDS:
            errs.append(f"background.kind must be one of {BACKGROUND_KINDS}")
        if self.background.kind in ("solid", "linear", "radial") and not self.background.colors:
            errs.append("background.colors needs at least one colour")
        for c in [*self.background.colors, self.text_color, self.reference_color]:
            if not is_hex_color(c):
                errs.append(f"colour {c!r} is not #RRGGBB or #RRGGBBAA")
        if self.transition not in TRANSITIONS:
            errs.append(f"transition must be one of {TRANSITIONS}")
        if self.frame not in FRAMES:
            errs.append(f"frame must be one of {FRAMES}")
        if self.layout not in LAYOUTS:
            errs.append(f"layout must be one of {LAYOUTS}")
        if not (12 <= self.font_size_px <= 300):
            errs.append("font_size_px must be between 12 and 300")
        if not (0 <= self.transition_ms <= 5000):
            errs.append("transition_ms must be between 0 and 5000")
        if not (100 <= self.font_weight <= 900):
            errs.append("font_weight must be between 100 and 900")
        return errs

    def validate(self) -> None:
        errs = self.problems()
        if errs:
            raise ValueError("invalid theme: " + "; ".join(errs))

    def save(self, path: str | Path) -> None:
        self.validate()
        Path(path).write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "Theme":
        theme = cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
        theme.validate()
        return theme


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
