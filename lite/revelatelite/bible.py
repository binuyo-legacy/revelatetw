"""Offline Bible access over the bundled .sqlite packs (plain sqlite3, read-only).

Pack schema: verses(book_id, chapter, verse, text), meta(key, value). book_id is 1..66.
Only one pack is kept open at a time to stay light on 2GB machines.
"""
import os
import re
import sqlite3
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
from revelatetw.books import BOOKS, name_forms  # noqa: E402

from . import paths  # noqa: E402

_MARKS = re.compile(r"[\u24b6-\u24e9]\s?")      # circled letters used as footnote marks (Yoruba pack)


def clean_text(text):
    """Display text: remove footnote marks, tidy odd spaces. Wording is never changed."""
    text = _MARKS.sub("", text)
    text = text.replace("\u202f", " ").replace("\u00a0", " ")
    return re.sub(r"\s+", " ", text).strip()


def _book_lookup():
    out = {}
    for b in BOOKS:
        for form in name_forms(b.book_id):
            out[form] = b.book_id
    return out


_BOOK_LOOKUP = _book_lookup()


def book_name(book_id):
    return BOOKS[book_id - 1].name


def find_book(text):
    key = re.sub(r"\s+", " ", text.lower().replace(".", " ")).strip()
    return _BOOK_LOOKUP.get(key)


_REF = re.compile(r"^\s*(.+?)\s*(\d+)\s*(?:[:. ]\s*(\d+)\s*(?:[-\u2013]\s*(\d+))?)?\s*$")


def parse_reference(text):
    """'John 3:16', 'rom 8:28', '1 cor 13:4', 'ps 23:1-3', 'John 3' -> (book, chapter, v1, v2).
    A chapter alone means verse 1. Returns None when it cannot be read."""
    m = _REF.match(text or "")
    if not m:
        return None
    book = find_book(m.group(1))
    if book is None:
        return None
    chapter = int(m.group(2))
    v1 = int(m.group(3)) if m.group(3) else 1
    v2 = int(m.group(4)) if m.group(4) else v1
    if v2 < v1 or chapter < 1 or v1 < 1:
        return None
    return book, chapter, v1, v2


def format_reference(book, chapter, v1, v2):
    verses = str(v1) if v1 == v2 else "%d-%d" % (v1, v2)
    return "%s %d:%s" % (book_name(book), chapter, verses)


class BibleStore:
    def __init__(self, directory=None):
        self.directory = directory or paths.bible_dir()
        self._conn = None
        self._open = None

    def translations(self):
        if not os.path.isdir(self.directory):
            return []
        return sorted(f[:-7] for f in os.listdir(self.directory) if f.endswith(".sqlite"))

    def _db(self, translation):
        if self._open != translation:
            self.close()
            path = os.path.join(self.directory, translation + ".sqlite").replace("\\", "/")
            if not os.path.isfile(path):
                raise KeyError("no such translation: " + translation)
            self._conn = sqlite3.connect("file:" + path + "?mode=ro", uri=True)
            self._open = translation
        return self._conn

    def close(self):
        if self._conn is not None:
            self._conn.close()
        self._conn = None
        self._open = None

    def meta(self, translation, key):
        row = self._db(translation).execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def full_name(self, translation):
        return self.meta(translation, "name") or translation

    def credit(self, translation):
        """Attribution line to show for licensed packs; '' for public domain."""
        lic = self.meta(translation, "license") or ""
        if "public" in lic.lower() or not lic:
            return ""
        return self.meta(translation, "attribution") or lic

    def short_credit(self, translation):
        """One short line for the projector (first sentence of the credit)."""
        c = self.credit(translation)
        return c.split(". Source")[0].strip() if c else ""

    def verse(self, translation, book, chapter, verse):
        row = self._db(translation).execute(
            "SELECT text FROM verses WHERE book_id=? AND chapter=? AND verse=?",
            (book, chapter, verse)).fetchone()
        return clean_text(row[0]) if row else None

    def last_verse(self, translation, book, chapter):
        row = self._db(translation).execute(
            "SELECT MAX(verse) FROM verses WHERE book_id=? AND chapter=?", (book, chapter)).fetchone()
        return row[0] or 0

    def last_chapter(self, translation, book):
        row = self._db(translation).execute(
            "SELECT MAX(chapter) FROM verses WHERE book_id=?", (book,)).fetchone()
        return row[0] or 0

    def passage(self, translation, book, chapter, v1, v2):
        """Text for v1..v2. One verse: plain text. Range: each verse prefixed with its number.
        Stops at the end of the chapter. None if the first verse does not exist."""
        rows = self._db(translation).execute(
            "SELECT verse, text FROM verses WHERE book_id=? AND chapter=? AND verse BETWEEN ? AND ? "
            "ORDER BY verse", (book, chapter, v1, v2)).fetchall()
        if not rows or rows[0][0] != v1:
            return None
        if v1 == v2:
            return clean_text(rows[0][1])
        return " ".join("%d %s" % (v, clean_text(t)) for v, t in rows)

    def step(self, translation, book, chapter, verse, delta):
        """Next (delta=1) or previous (-1) verse, crossing chapter and book edges. None at the ends."""
        if delta > 0:
            if verse < self.last_verse(translation, book, chapter):
                return book, chapter, verse + 1
            if chapter < self.last_chapter(translation, book):
                return book, chapter + 1, 1
            return (book + 1, 1, 1) if book < 66 else None
        if verse > 1:
            return book, chapter, verse - 1
        if chapter > 1:
            return book, chapter - 1, max(1, self.last_verse(translation, book, chapter - 1))
        if book > 1:
            lc = self.last_chapter(translation, book - 1)
            return book - 1, lc, max(1, self.last_verse(translation, book - 1, lc))
        return None

    def search(self, translation, words, limit=50):
        """Verses containing every word (case-insensitive). Returns [(book, chapter, verse, text)]."""
        words = [w for w in re.split(r"\s+", words.strip()) if w]
        if not words:
            return []
        cond = " AND ".join("text LIKE ? ESCAPE '\\'" for _ in words)
        args = ["%" + w.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%" for w in words]
        rows = self._db(translation).execute(
            "SELECT book_id, chapter, verse, text FROM verses WHERE " + cond +
            " ORDER BY book_id, chapter, verse LIMIT ?", args + [limit]).fetchall()
        return [(b, c, v, clean_text(t)) for b, c, v, t in rows]
