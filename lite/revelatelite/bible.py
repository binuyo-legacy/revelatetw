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


_REF = re.compile(r"^\s*(.+?)\s*(\d+)\s*(?:[:. ]\s*(\d*)\s*(?:[-\u2013]\s*(\d+))?)?\s*$")


_BARE_ORDINAL = re.compile(r"^\s*[123]\.?\s*$")


def _is_bare_ordinal(text):
    """True for a lone ordinal prefix with no book name yet ('1', '1 ', '2', '3.').

    This is a book being typed, never a chapter: '1' alone must not be read as
    chapter 1 of an empty book, so typing (autocomplete, arrow navigation) can
    treat the number plus the book name that follows as ONE book component.
    """
    return bool(_BARE_ORDINAL.match(text or ""))


def _has_chapter_number(text):
    """True when the typed text already carries a chapter number.

    'john 3' and '1 john 3' have one; 'joh', '1' and '1 jo' do not. The ordinal
    prefix of a numbered book ('1 John') is part of the book, never a chapter,
    which a plain digit search would mistake it for.
    """
    t = (text or "").strip()
    if _is_bare_ordinal(t):
        return False
    # A verse already typed ('1 john 3:16'): there IS a chapter number.
    if ":" in t:
        return True
    words = t.replace(".", " ").split()
    if not words:
        return False
    # a trailing number after a recognisable book is the chapter
    last = words[-1]
    if not last.isdigit():
        return False
    return find_book(" ".join(words[:-1])) is not None


def parse_reference(text):
    """'John 3:16', 'rom 8:28', '1 cor 13:4', 'ps 23:1-3', 'John 3' -> (book, chapter, v1, v2).
    A chapter alone means verse 1; a book name alone ('John') means chapter 1 verse 1.
    A lone ordinal ('1') is a book being typed, not a chapter: it returns None.
    Returns None when it cannot be read."""
    if _is_bare_ordinal(text):
        return None
    m = _REF.match(text or "")
    if not m:
        book = find_book(text or "")
        return (book, 1, 1, 1) if book else None
    book = find_book(m.group(1))
    if book is None:
        return None
    chapter = int(m.group(2))
    v1 = int(m.group(3)) if m.group(3) else 1
    v2 = int(m.group(4)) if m.group(4) else v1
    if v2 < v1 or chapter < 1 or v1 < 1:
        return None
    return book, chapter, v1, v2


def _norm(text):
    return re.sub(r"\s+", " ", text.lower().replace(".", " ")).strip()


def suggest_books(prefix, limit=8):
    """Book names whose spelling starts with what was typed ('jo' -> Job, Joel, John...)."""
    key = _norm(prefix)
    if not key:
        return []
    first, rest = [], []
    for b in BOOKS:
        if b.name.lower().startswith(key):
            first.append(b.name)
        elif any(f.startswith(key) for f in name_forms(b.book_id)):
            rest.append(b.name)
    return (first + rest)[:limit]


_PARTIAL = re.compile(r"^\s*(.*?)\s*(\d+)\s*(?::\s*(\d*))?\s*$")


def suggest(text, store=None, translation=None, limit=8):
    """Typing help. Returns strings to show in a drop-down while the user types.
      'jo'        -> book names ('Job ', 'Joel ', 'John ', ...)
      'john'      -> chapters ('John 1:', 'John 2:', ...)
      'john 3'    -> chapters starting with 3 ('John 3:')
      'john 3:1'  -> verses ('John 3:1', 'John 3:10', ...)
    A suggestion ending in ' ' is a book (keep typing), ending in ':' a chapter, otherwise a
    complete verse. Chapter/verse counts come from the selected translation; without one,
    no numbers are offered."""
    text = text or ""
    if not text.strip():
        return []
    # A lone ordinal ('1', '2', '3') is a book prefix, never a chapter number:
    # offer the numbered books ("1 Samuel ", "1 John ", ...). Without this the
    # partial-reference regex below reads the digit as a chapter of an empty
    # book and returns nothing, so the suggestion list (and the highlight that
    # follows from accepting one) never shows for numbered books.
    if _is_bare_ordinal(text):
        return [n + " " for n in suggest_books(text, limit)]
    m = _PARTIAL.match(text)
    if not m:
        book = find_book(text)
        if book is None:
            return [n + " " for n in suggest_books(text, limit)]
        return _chapters(book, "", store, translation, limit)
    book = find_book(m.group(1))
    if book is None:
        return []
    if m.group(3) is None and ":" not in text:
        return _chapters(book, m.group(2), store, translation, limit)
    if store is None or translation is None:
        return []
    ch = int(m.group(2))
    typed = m.group(3) or ""
    out = []
    for v in range(1, store.last_verse(translation, book, ch) + 1):
        if str(v).startswith(typed):
            out.append("%s %d:%d" % (book_name(book), ch, v))
            if len(out) >= max(limit, 200):
                break
    return out


def _chapters(book, typed, store, translation, limit):
    if store is None or translation is None:
        return []
    out = []
    for c in range(1, store.last_chapter(translation, book) + 1):
        if str(c).startswith(typed):
            out.append("%s %d:" % (book_name(book), c))
            if len(out) >= max(limit, 200):
                break
    return out


def check_reference(store, translation, parsed):
    """Range check for a parsed reference (book, chapter, v1, v2) in one translation.

    Returns None when it exists, else (kind, message, fix) where kind is 'book',
    'chapter' or 'verse' and fix is the nearest valid (book, chapter, v1, v2) or None.
    Never raises: this is the single place that decides 'out of range', so typing,
    Enter and Look up all give the same answer.
    """
    book, ch, v1, v2 = parsed
    name = book_name(book)
    last_c = store.last_chapter(translation, book)
    if last_c < 1:
        return ("book", "%s is not in %s." % (name, translation), None)
    if ch > last_c:
        return ("chapter", "Chapter %d isn't in %s (1-%d)." % (ch, name, last_c), (book, last_c, 1, 1))
    last_v = store.last_verse(translation, book, ch)
    if v1 > last_v:
        return ("verse", "Verse %d isn't in %s %d (1-%d)." % (v1, name, ch, last_v), (book, ch, last_v, last_v))
    return None


def partial_problem(store, translation, text):
    """While typing: the out-of-range message for what is typed so far, or None.
    Only whole numbers already typed count ('psalms 15' is fine, it may become 150);
    a number is judged wrong only when NO longer number could make it valid, i.e.
    it is already above the limit (every longer number is bigger still)."""
    m = _PARTIAL.match(text or "")
    if not m or _is_bare_ordinal(text) or not _has_chapter_number(text):
        return None
    book = find_book(m.group(1))
    if book is None:
        return None
    parsed = (book, int(m.group(2)), int(m.group(3)) if m.group(3) else 1, 1)
    if parsed[1] < 1 or parsed[2] < 1:
        return None
    bad = check_reference(store, translation, parsed)
    return bad[1] if bad else None


def format_reference(book, chapter, v1, v2):
    verses = str(v1) if v1 == v2 else "%d-%d" % (v1, v2)
    return "%s %d:%s" % (book_name(book), chapter, verses)


class BibleStore:
    def __init__(self, directory=None, user_directory=None):
        """directory: bundled packs. user_directory: packs the church imported (None = the default
        per-user folder, looked up lazily and only if it exists). A bundled pack always wins on a name clash."""
        self.directory = directory or paths.bible_dir()
        self._user_directory = user_directory
        self._conn = None
        self._open = None

    @property
    def user_directory(self):
        return self._user_directory or paths.user_bible_dir()

    def _pack_path(self, translation):
        for d in (self.directory, self.user_directory):
            p = os.path.join(d, translation + ".sqlite")
            if os.path.isfile(p):
                return p
        return None

    def translations(self):
        found = set()
        for d in (self.directory, self.user_directory):
            if os.path.isdir(d):
                found.update(f[:-7] for f in os.listdir(d) if f.endswith(".sqlite"))
        return sorted(found)

    def is_user_imported(self, translation):
        """True only for a pack in the user folder that the importer marked user_imported (never a bundled one)."""
        p = os.path.join(self.user_directory, translation + ".sqlite")
        if not os.path.isfile(p) or os.path.isfile(os.path.join(self.directory, translation + ".sqlite")):
            return False
        return self.meta(translation, "user_imported") == "1"

    def _db(self, translation):
        if self._open != translation:
            self.close()
            path = self._pack_path(translation)
            if path is None:
                raise KeyError("no such translation: " + translation)
            path = path.replace("\\", "/")
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

    def available_books(self, translation):
        """Book ids (1..66, canonical order) that this pack actually has verses for."""
        rows = self._db(translation).execute("SELECT DISTINCT book_id FROM verses ORDER BY book_id").fetchall()
        return [r[0] for r in rows if r[0] and 1 <= r[0] <= 66]

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


# ---------------- keyboard segment editing (book / chapter / verse) ----------------
SEGMENTS = ("book", "chapter", "verse")


def reference_spans(book, chapter, v1, v2):
    """Character spans (start, end) of each part of format_reference(...):
    'John 3:16' -> book (0,4), chapter (5,6), verse (7,9). A range like '28-30' is one verse part."""
    text = format_reference(book, chapter, v1, v2)
    b_end = len(book_name(book))
    c_end = b_end + 1 + len(str(chapter))
    return {"book": (0, b_end), "chapter": (b_end + 1, c_end), "verse": (c_end + 1, len(text))}


def adjust_reference(store, translation, cur, segment, delta):
    """Move ONE part of a reference up (+1) or down (-1). cur = (book, chapter, v1, v2).
    book    -> neighbouring book, chapter 1 verse 1
    chapter -> neighbouring chapter, same verse number if it exists there, else verse 1
    verse   -> neighbouring verse (a range becomes a single verse, starting from its first verse)
    Never wraps and never spills into another part. Returns (new_cur or None, message)."""
    book, ch, v1, _v2 = cur
    if segment == "book":
        nb = book + delta
        if nb < 1:
            return None, "That is the first book."
        if nb > 66:
            return None, "That is the last book."
        if store.last_chapter(translation, nb) < 1:
            return None, "%s is not in %s." % (book_name(nb), translation)
        return (nb, 1, 1, 1), ""
    if segment == "chapter":
        nc = ch + delta
        last_c = store.last_chapter(translation, book)
        if nc < 1:
            return None, "That is chapter 1."
        if nc > last_c:
            return None, "%s has only %d chapters." % (book_name(book), last_c)
        nv = v1 if v1 <= store.last_verse(translation, book, nc) else 1
        return (book, nc, nv, nv), ""
    if segment == "verse":
        nv = v1 + delta
        last = store.last_verse(translation, book, ch)
        if nv < 1:
            return None, "That is verse 1."
        if nv > last:
            return None, "%s %d has only %d verses." % (book_name(book), ch, last)
        return (book, ch, nv, nv), ""
    return None, ""
