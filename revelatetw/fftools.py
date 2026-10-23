"""Find ffmpeg and ffprobe for the Media tab (durations and video thumbnails).

Lookup order, per tool (ffmpeg and ffprobe are resolved separately):
  1. bundled: the app's own bin folder (revelatetw/assets/bin/), or next to the package,
     or the PyInstaller unpack folder when frozen. Ship the binaries in the installer and
     users never see the word ffmpeg.
  2. settings: the 'ffmpeg_dir' folder chosen in Settings > Output (its own folder or its bin/).
  3. system: whatever is on PATH.
  4. none: video details show as "length unknown" and placeholder thumbnails. Never a crash.

The result is cached after the first lookup. Changing the settings folder clears the cache.

Headless-safe: no Qt import here.
"""
from __future__ import annotations

import logging
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

_log = logging.getLogger(__name__)

PACKAGE_DIR = Path(__file__).resolve().parent
BUNDLED_BIN_DIR = PACKAGE_DIR / "assets" / "bin"
_NOT_FOUND_TEXT_ASCII = "ffmpeg: not found, video details unavailable"  # shown in Settings > Output

SOURCE_BUNDLED = "bundled"
SOURCE_SETTINGS = "settings"
SOURCE_SYSTEM = "system"


def _exe_names(tool: str) -> tuple[str, str]:
    return (f"{tool}.exe", tool)


@dataclass(frozen=True)
class ToolPath:
    path: Optional[str]     # full path to the executable, or None when not found
    source: Optional[str]   # SOURCE_BUNDLED | SOURCE_SETTINGS | SOURCE_SYSTEM | None


@dataclass(frozen=True)
class Tools:
    ffmpeg: ToolPath
    ffprobe: ToolPath

    @property
    def found(self) -> bool:
        return self.ffmpeg.path is not None or self.ffprobe.path is not None


def bundled_dirs() -> list[Path]:
    """Folders searched first: assets/bin, the package folder, and the PyInstaller unpack folder."""
    dirs = [BUNDLED_BIN_DIR, PACKAGE_DIR]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        dirs.append(Path(meipass) / "revelatetw" / "assets" / "bin")
        dirs.append(Path(meipass) / "revelatetw")
    return dirs


def _find_in_dirs(tool: str, dirs: list[Path]) -> Optional[str]:
    for d in dirs:
        for name in _exe_names(tool):
            candidate = d / name
            try:
                if candidate.is_file():
                    return str(candidate)
            except OSError:
                continue
    return None


def _resolve_one(tool: str, bundled: list[Path], configured: Optional[Path],
                 which: Callable[[str], Optional[str]]) -> ToolPath:
    hit = _find_in_dirs(tool, bundled)
    if hit:
        return ToolPath(hit, SOURCE_BUNDLED)
    if configured is not None:
        hit = _find_in_dirs(tool, [configured, configured / "bin"])
        if hit:
            return ToolPath(hit, SOURCE_SETTINGS)
    system = which(tool)
    if system:
        return ToolPath(system, SOURCE_SYSTEM)
    return ToolPath(None, None)


def locate(bundled: Optional[list[Path]] = None, configured_dir: str | Path | None = None,
           which: Callable[[str], Optional[str]] = shutil.which) -> Tools:
    """Run the lookup without touching the cache. Parameters exist so tests can use fakes."""
    dirs = list(bundled) if bundled is not None else bundled_dirs()
    conf = Path(configured_dir) if configured_dir else None
    return Tools(ffmpeg=_resolve_one("ffmpeg", dirs, conf, which),
                 ffprobe=_resolve_one("ffprobe", dirs, conf, which))


_cache: Optional[Tools] = None
_configured_dir: Optional[str] = None
_locate_calls = 0   # diagnostics and tests: how many real lookups ran


def set_configured_dir(folder: str | Path | None) -> None:
    """Remember the Settings > Output ffmpeg folder. Clears the cache so the next lookup uses it."""
    global _configured_dir
    new = str(folder).strip() if folder else ""
    if new != (_configured_dir or ""):
        _configured_dir = new or None
        reset_cache()


def get_tools(refresh: bool = False) -> Tools:
    """The resolved ffmpeg and ffprobe, cached after the first call."""
    global _cache, _locate_calls
    if _cache is None or refresh:
        _locate_calls += 1
        _cache = locate(configured_dir=_configured_dir)
        _log.info("ffmpeg lookup: %s", status_text(_cache))
    return _cache


def reset_cache() -> None:
    global _cache
    _cache = None


def ffmpeg_path() -> Optional[str]:
    return get_tools().ffmpeg.path


def ffprobe_path() -> Optional[str]:
    return get_tools().ffprobe.path


def _source_label(src: Optional[str]) -> str:
    return {SOURCE_BUNDLED: "bundled", SOURCE_SETTINGS: "settings folder", SOURCE_SYSTEM: "system"}.get(src or "", "")


def status_text(tools: Optional[Tools] = None) -> str:
    """One line for Settings > Output, e.g. 'ffmpeg: bundled' or 'ffmpeg: not found, video details unavailable'."""
    t = tools or get_tools()
    if not t.found:
        return _NOT_FOUND_TEXT_ASCII
    if t.ffmpeg.path and t.ffprobe.path and t.ffmpeg.source == t.ffprobe.source:
        return f"ffmpeg: {_source_label(t.ffmpeg.source)}"
    if t.ffmpeg.path and t.ffprobe.path:
        return (f"ffmpeg: {_source_label(t.ffmpeg.source)} (ffmpeg), "
                f"{_source_label(t.ffprobe.source)} (ffprobe)")
    if t.ffmpeg.path:
        return f"ffmpeg: {_source_label(t.ffmpeg.source)}, ffprobe not found (video length unknown)"
    return f"ffprobe: {_source_label(t.ffprobe.source)}, ffmpeg not found (video thumbnails unavailable)"
