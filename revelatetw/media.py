"""Media library (EasyWorship-style): images and videos the operator projects.

A folder (default data/media, changeable in Settings > Output) is scanned for image and video
files. Each file becomes a MediaItem with name, type, duration (videos, via ffprobe when it is
installed) and a thumbnail. Results are cached in an index JSON inside the folder, so a rescan
only probes and thumbnails files that are new or changed.

Headless-safe: this module imports no Qt at import time. Thumbnails use PyQt6 (QImageReader)
for images and ffmpeg (optional) for video first frames, both only when called.
"""
from __future__ import annotations

import hashlib
import json
import math
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".gif")
VIDEO_EXTS = (".mp4", ".mkv", ".webm", ".mov")
INDEX_NAME = ".revelatetw-media-index.json"
THUMB_DIR_NAME = ".thumbs"
THUMB_PX = 320
INDEX_VERSION = 1
DEFAULT_MEDIA_FOLDER = "data/media"


def media_kind(path) -> Optional[str]:
    """'image', 'video', or None for files that are not media (case-insensitive extension)."""
    ext = Path(path).suffix.lower()
    if ext in IMAGE_EXTS:
        return "image"
    if ext in VIDEO_EXTS:
        return "video"
    return None


def format_duration(seconds: float) -> str:
    total = int(round(seconds))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


@dataclass
class MediaItem:
    path: str                          # full path to the file on disk
    name: str                          # file name without extension, shown on the card
    kind: str                          # "image" | "video"
    size: int = 0
    mtime: float = 0.0
    duration_s: Optional[float] = None  # videos only; None = unknown (no ffprobe or probe failed)
    thumb: str = ""                    # path to a cached thumbnail, "" when there is none

    @property
    def is_video(self) -> bool:
        return self.kind == "video"

    @property
    def type_label(self) -> str:
        return "VIDEO" if self.is_video else "IMAGE"

    def duration_label(self) -> str:
        if not self.is_video:
            return ""
        return format_duration(self.duration_s) if self.duration_s is not None else "length unknown"


# --- ffprobe (optional) ---------------------------------------------------------------------

def ffprobe_path() -> Optional[str]:
    return shutil.which("ffprobe")


def parse_duration_output(text: str) -> Optional[float]:
    """ffprobe prints one number (seconds) for format=duration. Anything else is unknown."""
    try:
        value = float((text or "").strip().splitlines()[0])
    except (ValueError, IndexError):
        return None
    return value if math.isfinite(value) and value > 0 else None


def probe_duration(path, ffprobe: Optional[str] = None) -> Optional[float]:
    """Length of a video in seconds, or None when ffprobe is missing or the file will not probe."""
    exe = ffprobe or ffprobe_path()
    if not exe:
        return None
    try:
        r = subprocess.run([exe, "-v", "error", "-show_entries", "format=duration",
                            "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
                           capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    return parse_duration_output(r.stdout)


# --- thumbnails ------------------------------------------------------------------------------

def thumb_name(file_name: str, size: int, mtime: float) -> str:
    """Thumbnail file name keyed on name, size and mtime: a changed file gets a new thumbnail."""
    digest = hashlib.sha1(f"{file_name}|{size}|{mtime}".encode("utf-8")).hexdigest()[:16]
    return f"{digest}.jpg"


def make_thumbnail(src: Path, dst: Path, kind: str, px: int = THUMB_PX) -> bool:
    """Write a JPEG thumbnail. Images use Qt; videos use ffmpeg's first frame when available.

    Returns False when no thumbnail could be made (the card then shows a placeholder).
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    if kind == "image":
        try:
            from PyQt6.QtCore import Qt
            from PyQt6.QtGui import QImageReader
        except ImportError:
            return False
        reader = QImageReader(str(src))
        reader.setAutoTransform(True)
        img = reader.read()
        if img.isNull():
            return False
        img = img.scaled(px, px, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        return bool(img.save(str(dst), "JPG", 85))
    if kind == "video":
        exe = shutil.which("ffmpeg")
        if not exe:
            return False
        try:
            r = subprocess.run([exe, "-v", "error", "-y", "-i", str(src), "-frames:v", "1",
                                "-vf", f"scale={px}:-2", str(dst)],
                               capture_output=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            return False
        return r.returncode == 0 and dst.exists() and dst.stat().st_size > 0
    return False


# --- scanning, cache, search, import ---------------------------------------------------------

class MediaLibrary:
    """The media folder, its index cache and the thumbnails under it.

    probe and make_thumb are injectable so tests can count calls without ffmpeg or Qt.
    """

    def __init__(self, folder, probe: Optional[Callable[[Path], Optional[float]]] = None,
                 make_thumb: Optional[Callable[[Path, Path, str], bool]] = None):
        self.folder = Path(folder)
        self._probe = probe or probe_duration
        self._make_thumb = make_thumb or make_thumbnail
        self.items: list[MediaItem] = []
        self.probe_calls = 0          # diagnostics: how many ffprobe runs this library made
        self.thumb_calls = 0          # diagnostics: how many thumbnails this library tried to make

    @property
    def index_path(self) -> Path:
        return self.folder / INDEX_NAME

    @property
    def thumb_dir(self) -> Path:
        return self.folder / THUMB_DIR_NAME

    # index file ------------------------------------------------------------------------------
    def _read_index(self) -> dict[str, dict]:
        try:
            raw = json.loads(self.index_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(raw, dict) or raw.get("version") != INDEX_VERSION:
            return {}
        entries = raw.get("items")
        if not isinstance(entries, list):
            return {}
        return {e["file"]: e for e in entries if isinstance(e, dict) and "file" in e}

    def _write_index(self) -> None:
        entries = [{"file": Path(it.path).name, "size": it.size, "mtime": it.mtime,
                    "kind": it.kind, "duration_s": it.duration_s,
                    "thumb": Path(it.thumb).name if it.thumb else ""} for it in self.items]
        payload = {"version": INDEX_VERSION, "items": entries}
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            tmp = self.index_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            tmp.replace(self.index_path)
        except OSError:
            pass   # the cache is an optimisation; the scan result is still in memory

    def load_cached(self) -> list[MediaItem]:
        """Show the last scan without touching the disk tree (fast startup). No probes, no thumbs."""
        self.items = self._items_from_entries(self._read_index(), only_existing=True)
        return self.items

    def _items_from_entries(self, cached: dict[str, dict], only_existing: bool) -> list[MediaItem]:
        out = []
        for name, e in sorted(cached.items(), key=lambda kv: kv[0].lower()):
            kind = e.get("kind")
            path = self.folder / name
            if kind not in ("image", "video") or media_kind(path) != kind:
                continue
            if only_existing and not path.is_file():
                continue
            thumb = self.thumb_dir / e["thumb"] if e.get("thumb") else None
            out.append(MediaItem(path=str(path), name=Path(name).stem, kind=kind,
                                 size=int(e.get("size") or 0), mtime=float(e.get("mtime") or 0.0),
                                 duration_s=e.get("duration_s") if kind == "video" else None,
                                 thumb=str(thumb) if thumb and thumb.is_file() else ""))
        return out

    # scan ------------------------------------------------------------------------------------
    def rescan(self) -> list[MediaItem]:
        """Walk the folder (top level only). Unchanged files reuse their cached duration and thumbnail."""
        self.folder.mkdir(parents=True, exist_ok=True)
        cached = self._read_index()
        items: list[MediaItem] = []
        for p in sorted(self.folder.iterdir(), key=lambda x: x.name.lower()):
            kind = media_kind(p)
            if kind is None or not p.is_file():
                continue
            st = p.stat()
            prev = cached.get(p.name)
            if prev and prev.get("kind") == kind and prev.get("size") == st.st_size \
                    and prev.get("mtime") == st.st_mtime:
                item = self._items_from_entries({p.name: prev}, only_existing=False)[0]
                item.path = str(p)
                if not item.thumb:
                    item = self._fresh(p, kind, st)   # thumbnail missing or deleted: rebuild it
            else:
                item = self._fresh(p, kind, st)
            items.append(item)
        self.items = items
        self._write_index()
        return items

    def _fresh(self, p: Path, kind: str, st) -> MediaItem:
        duration = None
        if kind == "video":
            self.probe_calls += 1
            duration = self._probe(p)
        thumb = ""
        dst = self.thumb_dir / thumb_name(p.name, st.st_size, st.st_mtime)
        if dst.is_file() and dst.stat().st_size > 0:
            thumb = str(dst)
        else:
            self.thumb_calls += 1
            self.thumb_dir.mkdir(parents=True, exist_ok=True)
            try:
                ok = self._make_thumb(p, dst, kind)
            except Exception:  # a broken file must not stop the whole scan
                ok = False
            if ok and dst.is_file():
                thumb = str(dst)
        return MediaItem(path=str(p), name=p.stem, kind=kind, size=st.st_size, mtime=st.st_mtime,
                         duration_s=duration, thumb=thumb)

    # import ----------------------------------------------------------------------------------
    def import_files(self, sources: Iterable) -> tuple[list[Path], list[str]]:
        """Copy files into the media folder. Returns (copied paths, skipped names that are not media)."""
        self.folder.mkdir(parents=True, exist_ok=True)
        copied: list[Path] = []
        skipped: list[str] = []
        for src in sources:
            src = Path(src)
            if media_kind(src) is None or not src.is_file():
                skipped.append(src.name)
                continue
            dst = unique_path(self.folder, src.name)
            shutil.copy2(src, dst)
            copied.append(dst)
        return copied, skipped


def unique_path(folder: Path, file_name: str) -> Path:
    """'clip.mp4' -> 'clip (2).mp4' when the name is taken. Never overwrites a file."""
    candidate = folder / file_name
    stem, suffix = Path(file_name).stem, Path(file_name).suffix
    n = 2
    while candidate.exists():
        candidate = folder / f"{stem} ({n}){suffix}"
        n += 1
    return candidate


def filter_items(items: Iterable[MediaItem], text: str = "", kind: str = "all") -> list[MediaItem]:
    """Name search (every word must appear in the name, case-insensitive) plus All/Images/Videos."""
    words = [w for w in (text or "").lower().split() if w]
    want = {"image": "image", "images": "image", "video": "video", "videos": "video"}.get((kind or "all").lower())
    out = []
    for it in items:
        if want and it.kind != want:
            continue
        name = it.name.lower()
        if all(w in name for w in words):
            out.append(it)
    return out
