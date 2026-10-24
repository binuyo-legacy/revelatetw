"""Where the bundled data and assets live.

From a checkout that is the repo root. From a PyInstaller build it is the unpack folder
(sys._MEIPASS), which is where --add-data puts 'data' and 'revelatetw/assets'. Every bundled
path in the package is built from bundle_root() so the app works no matter which folder it
was started from.
"""
from __future__ import annotations

import sys
from pathlib import Path


def bundle_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent.parent


def bundled(*parts: str) -> Path:
    """A path under the bundle root, e.g. bundled('data', 'sample_kjv.json')."""
    return bundle_root().joinpath(*parts)


def resolve_data_arg(path: str | Path) -> str:
    """Turn a user-given data path into a real one.

    Absolute paths and paths that exist from the current folder are returned unchanged.
    Otherwise a relative path such as 'data/sample_kjv.json' is looked up under the bundle root,
    so a packaged exe started from any folder still finds its bundled files.
    """
    p = Path(path)
    if p.is_absolute() or p.exists():
        return str(path)
    candidate = bundle_root() / p
    return str(candidate) if candidate.exists() else str(path)
