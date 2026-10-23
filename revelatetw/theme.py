"""Theme model (spec F3): frames, backgrounds, colours, typography, layouts, transitions.

Themes are JSON, so export/import between machines is a file copy.

Schema v2 (this file) adds: accent_color (gold chips and frame), dim_color (footer and secondary
text), church_line (top line of the sermon info slide), image_scrim (darkening over image
backgrounds) and schema_version. Background images are file names inside data/backgrounds
(relative, never absolute). Files written before v2 have no schema_version: they load with
the defaults above, and their accent follows reference_color so the look does not change.
"""
from __future__ import annotations

import json
import re
import shutil
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Optional

SCHEMA_VERSION = 2
TRANSITIONS = ("fade", "slide", "kinetic", "none", "instant")  # spec F3 presets; none/instant = cut
LAYOUTS = ("full", "lower_third")
FRAMES = ("none", "thin", "double", "gold_rule")
BACKGROUND_KINDS = ("solid", "linear", "radial", "image", "video")

DEFAULT_GOLD = "#D4A017"
NAVY = "#1E1B4B"
MIDNIGHT = "#0F0B2E"
DEFAULT_DIM = "#A9A4C8"
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp")

# Background images live here. The app folder is found from this file, so it works from a checkout.
BACKGROUNDS_DIR = Path(__file__).resolve().parent.parent / "data" / "backgrounds"


def is_hex_color(value: str) -> bool:
    return bool(re.fullmatch(r"#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{8})", str(value)))


def safe_background_name(image_path: str) -> bool:
    """A background image must be a plain relative file name inside the backgrounds folder."""
    p = (image_path or "").strip()
    if not p or p.startswith(("/", "\\")) or ":" in p or "\\" in p:
        return False
    return ".." not in Path(p).parts and not Path(p).is_absolute()


def resolve_background_image(image_path: Optional[str], folder: Optional[Path] = None) -> Optional[Path]:
    """Full path of a background image, or None when unset, unsafe or missing (renderer falls back)."""
    if not image_path or not safe_background_name(image_path):
        return None
    path = (folder or BACKGROUNDS_DIR) / image_path
    return path if path.is_file() else None


@dataclass
class Background:
    kind: str = "linear"                        # linear (vertical gradient, default) | solid | image | radial | video
    colors: list[str] = field(default_factory=lambda: [NAVY, MIDNIGHT])
    image_path: Optional[str] = None            # file name inside data/backgrounds
    video_path: Optional[str] = None


@dataclass
class Theme:
    name: str = "Midnight Gold"
    background: Background = field(default_factory=Background)
    text_color: str = "#F5F3FF"
    reference_color: str = DEFAULT_GOLD
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
    # --- schema v2 ---
    schema_version: int = SCHEMA_VERSION
    accent_color: str = DEFAULT_GOLD            # gold chips, frame, section labels
    dim_color: str = DEFAULT_DIM                # footer text and secondary lines
    church_line: str = ""                       # small line at the top of the sermon info slide
    image_scrim: float = 0.4                    # darkening over image backgrounds (0 to 0.9)

    # --- portable file format ---------------------------------------------------
    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Theme":
        """Tolerant loader: unknown keys are ignored so newer theme files still open.

        Legacy (schema v1) files have no schema_version and no accent_color: the accent takes
        the old reference colour so those themes look the same, and the v2 fields get defaults.
        """
        known = {f.name for f in fields(cls)}
        bg_known = {f.name for f in fields(Background)}
        bg_raw = data.get("background") or {}
        bg = Background(**{k: v for k, v in bg_raw.items() if k in bg_known})
        values = {k: v for k, v in data.items()
                  if k in known and k not in ("background", "schema_version")}
        if "accent_color" not in data:
            values["accent_color"] = str(data.get("reference_color", DEFAULT_GOLD))
        return cls(background=bg, schema_version=SCHEMA_VERSION, **values)

    @staticmethod
    def is_legacy_data(data: dict) -> bool:
        """True for theme JSON written before schema v2."""
        return "schema_version" not in data

    def problems(self) -> list[str]:
        """Human-readable list of anything the renderer cannot draw. Empty means valid."""
        errs = []
        if self.background.kind not in BACKGROUND_KINDS:
            errs.append(f"background.kind must be one of {BACKGROUND_KINDS}")
        if self.background.kind in ("solid", "linear", "radial") and not self.background.colors:
            errs.append("background.colors needs at least one colour")
        if self.background.kind == "image":
            if not self.background.image_path:
                errs.append("image background needs an image file from data/backgrounds")
            elif not safe_background_name(self.background.image_path):
                errs.append("background image must be a file name inside data/backgrounds "
                            "(no absolute paths or ..)")
        for c in [*self.background.colors, self.text_color, self.reference_color,
                  self.accent_color, self.dim_color]:
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
        if not (0.0 <= float(self.image_scrim) <= 0.9):
            errs.append("image_scrim must be between 0 and 0.9")
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


def import_background_image(source: str | Path, folder: Optional[Path] = None) -> str:
    """Copy a picked image into data/backgrounds and return its relative file name.

    Keeps themes portable: the theme stores only the name, never the user's own folder.
    """
    src = Path(source)
    if src.suffix.lower() not in IMAGE_EXTS:
        raise ValueError(f"background must be one of {IMAGE_EXTS}")
    dest_dir = folder or BACKGROUNDS_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)
    name, n = src.name, 1
    while (dest_dir / name).exists() and (dest_dir / name).read_bytes() != src.read_bytes():
        name = f"{src.stem}-{n}{src.suffix}"
        n += 1
    if not (dest_dir / name).exists():
        shutil.copy2(src, dest_dir / name)
    return name


def ready_made_themes() -> list[Theme]:
    """Starting looks. Spec requires six at launch; these are the first pass."""
    return [
        Theme(name="Midnight Gold"),
        Theme(name="Sanctuary Light", background=Background("solid", ["#F8F5EC"]),
              text_color="#1E1B4B", reference_color="#4C1D95", accent_color="#4C1D95",
              dim_color="#5B5680", frame="thin"),
        Theme(name="Royal Indigo", background=Background("linear", ["#1E1B4B", "#4C1D95"]),
              frame="double"),
        Theme(name="Dawn Radial", background=Background("radial", ["#4C1D95", "#0F0B2E"]),
              frame="none", layout="lower_third", transition="slide"),
        Theme(name="Plain Black", background=Background("solid", ["#000000"]), frame="none",
              font_size_px=72, transition="kinetic"),
        Theme(name="Lower Third Gold", background=Background("solid", ["#00000000"]),
              layout="lower_third", font_size_px=44, frame="gold_rule", shadow=True),
    ]
