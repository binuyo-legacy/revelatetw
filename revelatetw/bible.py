"""Bible translations: a registry of installed versions, lazy verse lookup, and user imports.

Layout:
  data/bible/<ID>.sqlite   bundled public-domain packs (KJV, ASV). Same schema as VerseStore packs.
  data/sample_kjv.json     offline fallback (9 dev verses). Used only when no KJV pack is installed.
  data/bible/<ID>.sqlite   also created by Settings > Bible > Add translation (user's own licensed JSON).

Every pack is opened lazily (on first lookup) and cached. Lookups hit the (book_id, chapter, verse)
primary key, so a single verse costs one indexed SQLite read.
"""
from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .books import BOOK_BY_ID, BOOK_BY_NAME
from .store import VerseStore

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BIBLE_DIR = REPO_ROOT / "data" / "bible"
SAMPLE_JSON = REPO_ROOT / "data" / "sample_kjv.json"
PACK_SUFFIX = ".sqlite"
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{1,15}$")
REQUIRED_IMPORT_KEYS = ("id", "name", "language", "license", "verses")
# Bundled ids cannot be replaced by an import (keeps KJV/ASV meaning what the bundle says).
RESERVED_IDS = {"KJV", "ASV"}
PREFERRED_ORDER = ("KJV", "ASV")


class BibleImportError(ValueError):
    """Raised with a plain-language message when a translation file is not usable."""


@dataclass(frozen=True)
class Translation:
    id: str
    name: str
    license: str
    path: str            # the file it is read from ("" for the sample fallback)
    bundled: bool        # True for files shipped with the app
    fallback: bool = False  # True only for the 9-verse offline sample

    @property
    def label(self) -> str:
        return f"{self.id} - {self.name}" + (" (sample)" if self.fallback else "")


class BibleLibrary:
    """Registry of installed translations with lazy, cached lookups. Thread-safe for reads."""

    def __init__(self, folder: Path | str | None = None, sample_json: Path | str | None = None):
        self.folder = Path(folder) if folder else DEFAULT_BIBLE_DIR
        self.sample_json = Path(sample_json) if sample_json else SAMPLE_JSON
        self._stores: dict[str, VerseStore] = {}
        self._lock = threading.RLock()

    # --- registry ----------------------------------------------------------------------
    def installed(self) -> list[Translation]:
        """Every usable translation, KJV/ASV first. The sample is listed only if no KJV pack exists."""
        out: list[Translation] = []
        if self.folder.is_dir():
            for p in sorted(self.folder.glob(f"*{PACK_SUFFIX}")):
                try:
                    meta = VerseStore.open(p).meta
                except Exception:          # a damaged pack must not break the operator screen
                    continue
                tid = str(meta.get("id") or p.stem)
                out.append(Translation(tid, str(meta.get("name") or tid), str(meta.get("license", "")),
                                       str(p), bundled=tid in RESERVED_IDS))
        if not any(t.id == "KJV" for t in out) and self.sample_json.is_file():
            out.append(Translation("KJV", "King James Version (sample)", "Public domain",
                                   str(self.sample_json), bundled=True, fallback=True))
        rank = {tid: i for i, tid in enumerate(PREFERRED_ORDER)}
        out.sort(key=lambda t: (rank.get(t.id, len(rank)), t.id))
        return out

    def ids(self) -> list[str]:
        return [t.id for t in self.installed()]

    def has(self, tid: str) -> bool:
        return any(t.id == tid for t in self.installed())

    def default_id(self) -> str:
        ids = self.ids()
        return ids[0] if ids else "KJV"

    def resolve(self, tid: str) -> str:
        """Return tid if installed, else the default id (never raises)."""
        return tid if self.has(tid) else self.default_id()

    # --- lookup --------------------------------------------------------------------------
    def store(self, tid: str) -> Optional[VerseStore]:
        with self._lock:
            if tid in self._stores:
                return self._stores[tid]
            match = next((t for t in self.installed() if t.id == tid), None)
            if match is None:
                return None
            store = (VerseStore.from_json(match.path) if match.fallback else VerseStore.open(match.path))
            self._stores[tid] = store
            return store

    def get(self, tid: str, book_id: int, chapter: int, verse: int) -> Optional[str]:
        """Verse text in translation tid, or None if the translation or the verse is missing."""
        store = self.store(tid)
        return store.get(book_id, chapter, verse) if store is not None else None

    def get_or_default(self, tid: str, book_id: int, chapter: int, verse: int) -> tuple[str, Optional[str]]:
        """(text, translation id actually used). Falls back to the default translation when tid lacks the verse."""
        text = self.get(tid, book_id, chapter, verse)
        if text is not None:
            return text, tid
        for other in self.ids():
            if other != tid:
                text = self.get(other, book_id, chapter, verse)
                if text is not None:
                    return text, other
        return "", None

    def close(self) -> None:
        with self._lock:
            for s in self._stores.values():
                try:
                    s._conn.close()
                except Exception:
                    pass
            self._stores.clear()


def parse_book(value) -> int:
    """Accept a book id (int or digit string) or an English book name. Raises BibleImportError."""
    if isinstance(value, bool):
        raise BibleImportError("book must be a name or a book number 1-66")
    if isinstance(value, int) or (isinstance(value, str) and value.strip().isdigit()):
        n = int(value)
        if n in BOOK_BY_ID:
            return n
        raise BibleImportError(f"book number {n} is not in 1-66")
    if isinstance(value, str) and value.strip().lower() in BOOK_BY_NAME:
        return BOOK_BY_NAME[value.strip().lower()]
    raise BibleImportError(f"unknown book name {value!r} (use the English name, e.g. 'John')")


def import_translation(json_path: Path | str, folder: Path | str | None = None) -> Translation:
    """Import a user's own licensed translation JSON into data/bible as <id>.sqlite.

    Documented format (see SETUP.md, 'Add a translation'):
      {"id": "MYTR", "name": "My Translation", "language": "en",
       "license": "Licensed to Grace Church, 2026 (text owner: ...)",
       "verses": [{"book": "John", "chapter": 3, "verse": 16, "text": "..."}]}
    Nothing is bundled from copyrighted sources: the file is the user's own.
    """
    src = Path(json_path)
    try:
        raw = json.loads(src.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise BibleImportError(f"could not read {src.name} as JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise BibleImportError("the file must be a JSON object with id, name, language, license and verses")
    missing = [k for k in REQUIRED_IMPORT_KEYS if k not in raw]
    if missing:
        raise BibleImportError("missing field(s): " + ", ".join(missing))
    tid = str(raw["id"]).strip()
    if not ID_RE.match(tid):
        raise BibleImportError("id must be 2-16 letters, digits, '-' or '_' (for example NKJV or MYTR)")
    if tid.upper() in RESERVED_IDS:
        raise BibleImportError(f"{tid} is a bundled translation name; pick another id")
    name = str(raw["name"]).strip()
    license_text = str(raw["license"]).strip()
    if not name:
        raise BibleImportError("name cannot be empty")
    if not license_text:
        raise BibleImportError("license cannot be empty: say who licensed the text and for what use")
    if not isinstance(raw["verses"], list) or not raw["verses"]:
        raise BibleImportError("verses must be a non-empty list")

    rows: list[tuple[int, int, int, str]] = []
    seen: set[tuple[int, int, int]] = set()
    for i, v in enumerate(raw["verses"], start=1):
        if not isinstance(v, dict):
            raise BibleImportError(f"verse #{i} is not an object")
        try:
            book_id = parse_book(v.get("book"))
            chapter = int(v.get("chapter"))
            verse = int(v.get("verse"))
        except (TypeError, ValueError, BibleImportError) as exc:
            raise BibleImportError(f"verse #{i}: {exc}") from exc
        text = str(v.get("text", "")).strip()
        if chapter < 1 or verse < 1:
            raise BibleImportError(f"verse #{i}: chapter and verse must be 1 or more")
        if not text:
            raise BibleImportError(f"verse #{i} ({BOOK_BY_ID[book_id].name} {chapter}:{verse}) has no text")
        key = (book_id, chapter, verse)
        if key in seen:
            raise BibleImportError(f"duplicate verse {BOOK_BY_ID[book_id].name} {chapter}:{verse}")
        seen.add(key)
        rows.append((book_id, chapter, verse, text))

    out_dir = Path(folder) if folder else DEFAULT_BIBLE_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{tid}{PACK_SUFFIX}"
    meta = {"id": tid, "name": name, "language": str(raw["language"]).strip() or "en",
            "license": license_text, "attribution": str(raw.get("attribution", "")).strip(),
            "version": "1"}
    tmp = target.with_suffix(".tmp")
    if tmp.exists():
        tmp.unlink()
    VerseStore.write_pack(tmp, meta, rows)
    tmp.replace(target)
    return Translation(tid, name, license_text, str(target), bundled=False)


def remove_user_translation(tid: str, folder: Path | str | None = None) -> bool:
    """Delete a user-imported pack. Bundled ids are never removed."""
    if tid.upper() in RESERVED_IDS:
        return False
    target = (Path(folder) if folder else DEFAULT_BIBLE_DIR) / f"{tid}{PACK_SUFFIX}"
    if target.is_file():
        target.unlink()
        return True
    return False
