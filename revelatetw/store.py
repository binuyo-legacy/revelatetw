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
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        verses = []
        for v in data["verses"]:
            book_id = v.get("book_id") or BOOK_BY_NAME[v["book"].lower()]
            verses.append((book_id, v["chapter"], v["verse"], v["text"]))
        meta = {k: data[k] for k in ("id", "name", "language", "license", "attribution") if k in data}
        return cls._build(":memory:", meta, verses)

    @classmethod
    def write_pack(cls, path: str | Path, meta: dict, verses: Iterable[tuple[int, int, int, str]]) -> None:
        cls._build(str(path), meta, list(verses))

    @classmethod
    def _build(cls, target: str, meta: dict, verses: list[tuple[int, int, int, str]]) -> "VerseStore":
        conn = sqlite3.connect(target, check_same_thread=False)
        conn.executescript(
            "DROP TABLE IF EXISTS meta; DROP TABLE IF EXISTS verses;"
            "CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);"
            "CREATE TABLE verses(book_id INT, chapter INT, verse INT, text TEXT,"
            " PRIMARY KEY(book_id, chapter, verse));")
        conn.executemany("INSERT INTO meta VALUES (?, ?)", [(k, str(v)) for k, v in meta.items()])
        conn.executemany("INSERT INTO verses VALUES (?, ?, ?, ?)", verses)
        conn.commit()
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
