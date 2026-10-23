"""Operator navigation: autosuggest search, manual cascade, next/prev verse, 'verse two' continuation.

Everything here is pure logic (no Qt) so it runs headless in tests.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from .books import BOOKS, BOOK_BY_ID, name_forms, testament
from .detection import normalise
from .store import VerseStore


@dataclass(frozen=True)
class Suggestion:
    kind: str                 # "book" | "chapter" | "verse"
    label: str
    book_id: int
    chapter: Optional[int] = None
    verse: Optional[int] = None
    text: Optional[str] = None  # verse text for kind == "verse"

    @property
    def reference(self) -> str:
        name = BOOK_BY_ID[self.book_id].name
        if self.chapter is None:
            return name
        if self.verse is None:
            return f"{name} {self.chapter}"
        return f"{name} {self.chapter}:{self.verse}"

    @property
    def completion(self) -> str:
        """Text the search box shows when the operator presses Tab or picks a non-verse row."""
        name = BOOK_BY_ID[self.book_id].name
        if self.chapter is None:
            return name + " "
        if self.verse is None:
            return f"{name} {self.chapter}:"
        return self.reference


_PARSE_RE = re.compile(
    r"^(?P<book>[0-9a-z ]*[a-z])\.?\s*(?:ch(?:apter)?\.?\s*)?(?P<ch>\d{1,3})?"
    r"(?:\s*[:\s]\s*(?P<v>\d{1,3}))?\s*:?\s*$")


def parse_query(query: str) -> Optional[tuple[str, Optional[int], Optional[int]]]:
    """'first john 3:16' -> ('1 john', 3, 16); 'jn' -> ('jn', None, None); '' -> None."""
    q = normalise(query.strip().lower())
    q = re.sub(r"(?<=\d)\s*\.\s*(?=\d)", ":", q)     # 'john 3.16' -> 'john 3:16'
    q = re.sub(r"\s+", " ", q).strip()
    m = _PARSE_RE.match(q)
    if not m or not m.group("book").strip():
        return None
    ch = int(m.group("ch")) if m.group("ch") else None
    v = int(m.group("v")) if m.group("v") else None
    return m.group("book").strip(), ch, v


def _book_matches(book_part: str) -> list[int]:
    compact = book_part.replace(" ", "")
    exact, prefix = [], []
    for b in BOOKS:
        forms = name_forms(b.book_id)
        if any(f == book_part for f in forms):
            exact.append(b.book_id)
        elif any(f.replace(" ", "").startswith(compact) for f in forms):
            prefix.append(b.book_id)
    return exact + [i for i in prefix if i not in exact]


def suggest(query: str, store: VerseStore, limit: int = 8) -> list[Suggestion]:
    parsed = parse_query(query)
    if parsed is None:
        return []
    book_part, ch, v = parsed
    out: list[Suggestion] = []
    for book_id in _book_matches(book_part):
        name = BOOK_BY_ID[book_id].name
        if ch is None:
            out.append(Suggestion("book", name, book_id))
            continue
        if ch not in store.chapters(book_id):
            continue
        if v is None:
            out.append(Suggestion("chapter", f"{name} {ch}", book_id, ch))
            for n in store.verse_numbers(book_id, ch)[:limit]:
                out.append(_verse_sugg(store, book_id, ch, n))
            continue
        nums = [n for n in store.verse_numbers(book_id, ch) if str(n).startswith(str(v))]
        for n in nums:
            out.append(_verse_sugg(store, book_id, ch, n))
    return out[:limit * 3]


def _verse_sugg(store: VerseStore, book_id: int, ch: int, n: int) -> Suggestion:
    text = store.get(book_id, ch, n) or ""
    name = BOOK_BY_ID[book_id].name
    preview = text if len(text) <= 60 else text[:57] + "..."
    return Suggestion("verse", f"{name} {ch}:{n}  {preview}", book_id, ch, n, text)


def resolve(query: str, store: VerseStore) -> Optional[Suggestion]:
    """What Enter should project: the top verse suggestion, or None if the query is incomplete."""
    for s in suggest(query, store):
        if s.kind == "verse":
            parsed = parse_query(query)
            if parsed and parsed[2] is not None and s.verse == parsed[2]:
                return s
            if parsed and parsed[2] is None:
                return None
    return None


# ------------------------------------------------------------------ manual cascade
def manual_testaments() -> list[str]:
    return ["Old Testament", "New Testament"]


def manual_books(testament_name: str) -> list[tuple[int, str]]:
    code = "OT" if testament_name.lower().startswith("old") else "NT"
    return [(b.book_id, b.name) for b in BOOKS if testament(b.book_id) == code]


def manual_chapters(store: VerseStore, book_id: int) -> list[int]:
    return store.chapters(book_id)


def manual_verses(store: VerseStore, book_id: int, chapter: int) -> list[int]:
    return store.verse_numbers(book_id, chapter)


# ------------------------------------------------------------------ next / prev
def step_verse(store: VerseStore, book_id: int, chapter: int, verse: int, delta: int) -> Optional[Suggestion]:
    """Neighbouring verse in the same chapter, or None at the chapter edge (never crosses chapters)."""
    n = store.neighbour(book_id, chapter, verse, delta)
    if n is None:
        return None
    return _verse_sugg(store, book_id, chapter, n)


# ------------------------------------------------------------------ 'verse two' continuation
_VERSE_MENTION_RE = re.compile(r"\b(next verse|verse (\d{1,3})\b)")


def verse_mentions(text: str) -> list[Optional[int]]:
    """Verse mentions without a book: 'verse two' -> [2]; 'next verse' -> [None] (means previous+1)."""
    out: list[Optional[int]] = []
    for m in _VERSE_MENTION_RE.finditer(normalise(text.lower())):
        out.append(int(m.group(2)) if m.group(2) else None)
    return out


def candidate_from_suggestion(store: VerseStore, s: Suggestion, match_type: str = "manual",
                              confidence: int = 100, snippet: str = ""):
    """Build a queue Candidate for a verse suggestion (manual pick, search, next/prev, continuation)."""
    from .detection import Candidate  # local import keeps this module light
    if s.kind != "verse":
        raise ValueError("only verse suggestions can be projected")
    return Candidate(s.reference, s.book_id, BOOK_BY_ID[s.book_id].name, s.chapter, s.verse,
                     store.translation_id, s.text or store.get(s.book_id, s.chapter, s.verse) or "",
                     confidence, match_type, snippet)


def continuation_suggestions(store: VerseStore, live_book: int, live_chapter: int,
                             live_verse: int, text: str) -> list[Suggestion]:
    """'verse two' / 'verse 2' -> same chapter as the live verse; 'next verse' -> live + 1."""
    out: list[Suggestion] = []
    for mention in verse_mentions(text):
        if mention is None:
            s = step_verse(store, live_book, live_chapter, live_verse, +1)
        else:
            s = _verse_sugg(store, live_book, live_chapter, mention) \
                if mention in store.verse_numbers(live_book, live_chapter) else None
        if s and s not in out:
            out.append(s)
    return out


verse_suggestion = _verse_sugg  # public alias used by the operator UI
