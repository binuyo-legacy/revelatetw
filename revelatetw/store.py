"""Verse store: reads verses from a SQLite translation pack.

Pack format (spec section 8), simplified for the scaffold:
  meta(key TEXT PRIMARY KEY, value TEXT)  -- id, name, language, license, attribution, version
  verses(book_id INT, chapter INT, verse INT, text TEXT, PRIMARY KEY(book_id, chapter, verse))

TODO (not in scaffold): Ed25519 manifest signature + checksum verification on install and load,
entitlement checks, FTS5 index. The scaffold loads unsigned packs and says so in the UI.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable, Iterator, Optional

from .books import BOOK_BY_NAME
from .paths import resolve_data_arg


class VerseStore:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self.meta = dict(conn.execute("SELECT key, value FROM meta").fetchall())

    @property
    def translation_id(self) -> str:
        return self.meta.get("id", "UNKNOWN")

    @classmethod
    def open(cls, path: str | Path) -> "VerseStore":
        conn = sqlite3.connect(str(path), check_same_thread=False)
        return cls(conn)

    @classmethod
    def from_json(cls, path: str | Path) -> "VerseStore":
        """Build an in-memory store from a JSON file (used for dev samples)."""
        data = json.loads(Path(resolve_data_arg(path)).read_text(encoding="utf-8"))
        verses = []
        for v in data["verses"]:
            book_id = v.get("book_id") or BOOK_BY_NAME[v["book"].lower()]
            verses.append((book_id, v["chapter"], v["verse"], v["text"]))
        meta = {k: data[k] for k in ("id", "name", "language", "license", "attribution") if k in data}
        return cls._build(":memory:", meta, verses)

    @classmethod
    def write_pack(cls, path: str | Path, meta: dict, verses: Iterable[tuple[int, int, int, str]]) -> None:
        cls._build(str(path), meta, list(verses))._conn.close()

    @classmethod
    def _build(cls, target: str, meta: dict, verses: list[tuple[int, int, int, str]]) -> "VerseStore":
        conn = sqlite3.connect(target, check_same_thread=False)
        conn.executescript(
            "DROP TABLE IF EXISTS meta; DROP TABLE IF EXISTS verses;"
            "CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);"
            "CREATE TABLE verses(book_id INT, chapter INT, verse INT, text TEXT,"
            " PRIMARY KEY(book_id, chapter, verse));")
        try:
            conn.executemany("INSERT INTO meta VALUES (?, ?)", [(k, str(v)) for k, v in meta.items()])
            conn.executemany("INSERT INTO verses VALUES (?, ?, ?, ?)", verses)
            conn.commit()
        except Exception:
            conn.close()
            raise
        return cls(conn)

    def get(self, book_id: int, chapter: int, verse: int) -> Optional[str]:
        row = self._conn.execute(
            "SELECT text FROM verses WHERE book_id=? AND chapter=? AND verse=?",
            (book_id, chapter, verse)).fetchone()
        return row[0] if row else None

    def chapters(self, book_id: int) -> list[int]:
        return [r[0] for r in self._conn.execute(
            "SELECT DISTINCT chapter FROM verses WHERE book_id=? ORDER BY chapter", (book_id,))]

    def verse_numbers(self, book_id: int, chapter: int) -> list[int]:
        return [r[0] for r in self._conn.execute(
            "SELECT verse FROM verses WHERE book_id=? AND chapter=? ORDER BY verse", (book_id, chapter))]

    def neighbour(self, book_id: int, chapter: int, verse: int, delta: int) -> Optional[int]:
        """Next (+1) or previous (-1) verse number inside the same chapter, or None."""
        nums = self.verse_numbers(book_id, chapter)
        if verse not in nums:
            return None
        i = nums.index(verse) + delta
        return nums[i] if 0 <= i < len(nums) else None

    def items(self) -> Iterator[tuple[tuple[int, int, int], str]]:
        for b, c, v, t in self._conn.execute("SELECT book_id, chapter, verse, text FROM verses"):
            yield (b, c, v), t


# ---------------------------------------------------------------- app settings (JSON)
import dataclasses as _dc
import logging as _logging

APP_VERSION = "0.2.0"
_log = _logging.getLogger(__name__)


INPUT_GAIN_RANGE_DB = (-60.0, 20.0)   # also the range of the gain box on the Live screen


def _clamp_gain(value) -> float:
    """Gain in dB, limited to INPUT_GAIN_RANGE_DB. Anything that is not a finite number becomes 0 dB."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.0
    if v != v or v in (float("inf"), float("-inf")):
        return 0.0
    lo, hi = INPUT_GAIN_RANGE_DB
    return min(hi, max(lo, v))


@_dc.dataclass
class AppSettings:
    """Operator settings, saved as JSON. Unknown keys are ignored; bad values fall back to defaults."""
    # General
    startup_live_on: bool = True          # open with live output ON
    check_updates: bool = False           # privacy: the check only runs when you ask (About)
    check_updates_on_startup: bool = False  # optional: check GitHub Releases once at startup
    bible_translation: str = "KJV"        # translation id shown on the Verses tab
    language: str = "en"
    # Output
    output_display: int = 0               # index into the display list
    default_resolution: str = "auto"      # "auto" or "WIDTHxHEIGHT"
    borderless_fullscreen: bool = True
    virtual_camera: bool = False          # OBS / virtual camera readiness flag (see ui notes)
    media_folder: str = ""               # empty = data/media next to the app
    ffmpeg_dir: str = ""                 # optional folder holding ffmpeg/ffprobe (empty = bundled, then PATH)
    # Audio
    input_device_name: str = ""           # remembered by name (indexes change between boots)
    wasapi_loopback: bool = False         # list WASAPI loopback (mixing desk output) devices
    noise_gate_db: float = -45.0          # RMS gate threshold, -80..-10
    input_gain_db: float = 0.0            # input gain applied to the capture, -60..20 dB
    # Transcription
    model_size: str = "small"             # tiny | base | small | medium | large | large-v3
    yoruba_advisory_dismissed: bool = False  # one-time Yoruba live detection advisory dismissed
    whisper_language: str = "en"
    compute_type: str = "int8"            # faster-whisper: int8 (default) | int8_float32 | float32
    cpu_threads: int = 0                  # 0 = automatic
    detection_threshold: int = 60         # paraphrase threshold 0-100
    # Detection
    paraphrase_threshold: int = 60        # same knob as --paraphrase-threshold
    dedupe_minutes: float = 5.0
    auto_approve: bool = False            # OFF by default; bypasses operator approval

    def clean(self) -> "AppSettings":
        """Coerce every field to a valid value."""
        d = AppSettings()
        self.startup_live_on = bool(self.startup_live_on)
        self.check_updates = bool(self.check_updates)
        self.check_updates_on_startup = bool(self.check_updates_on_startup)
        self.bible_translation = str(self.bible_translation or d.bible_translation).strip() or d.bible_translation
        self.language = str(self.language or d.language)
        self.output_display = max(0, int(self.output_display or 0))
        res = str(self.default_resolution or "auto")
        self.default_resolution = res if res == "auto" or "x" in res.lower() else "auto"
        self.borderless_fullscreen = bool(self.borderless_fullscreen)
        self.virtual_camera = bool(self.virtual_camera)
        self.media_folder = str(self.media_folder or "").strip()
        self.ffmpeg_dir = str(self.ffmpeg_dir or "").strip()
        self.input_device_name = str(self.input_device_name or "")
        self.wasapi_loopback = bool(self.wasapi_loopback)
        self.noise_gate_db = min(-10.0, max(-80.0, float(self.noise_gate_db)))
        self.input_gain_db = _clamp_gain(self.input_gain_db)
        self.model_size = self.model_size if self.model_size in ("tiny", "base", "small", "medium", "large", "large-v3") \
            else d.model_size
        self.yoruba_advisory_dismissed = bool(self.yoruba_advisory_dismissed)
        self.whisper_language = str(self.whisper_language or d.whisper_language)
        self.compute_type = self.compute_type if self.compute_type in ("int8", "int8_float32", "float32") \
            else d.compute_type
        self.cpu_threads = min(64, max(0, int(self.cpu_threads or 0)))
        self.detection_threshold = min(100, max(0, int(self.detection_threshold)))
        self.paraphrase_threshold = min(100, max(0, int(self.paraphrase_threshold)))
        self.dedupe_minutes = min(60.0, max(0.0, float(self.dedupe_minutes)))
        self.auto_approve = bool(self.auto_approve)
        return self


def load_settings(path) -> AppSettings:
    """Read the JSON settings file. Missing or corrupt file gives defaults (never raises)."""
    p = Path(path)
    if not p.exists():
        return AppSettings()
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("settings root is not an object")
    except (OSError, ValueError) as exc:
        _log.warning("settings file %s unreadable, using defaults: %s", p, exc)
        return AppSettings()
    known = {f.name for f in _dc.fields(AppSettings)}
    return AppSettings(**{k: v for k, v in raw.items() if k in known}).clean()


def save_settings(path, settings: AppSettings) -> None:
    """Write the settings JSON (atomic replace so a crash never leaves half a file)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(_dc.asdict(settings.clean()), indent=2), encoding="utf-8")
    tmp.replace(p)
