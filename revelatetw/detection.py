"""Verse detection: exact citations (regex) plus a lexical paraphrase stub.

Paraphrase matching lives in paraphrase.py: IDF-weighted token similarity offline by
default, sentence embeddings when an optional model is cached (spec F1).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from .books import BOOKS, BOOK_BY_ID
from .paraphrase import TokenSimilarityMatcher, best_paraphrase_matcher
from .store import VerseStore

# ------------------------------------------------------------------ spoken numbers
_ORDINAL_RE = [(re.compile(r"\b(first|1st)\s+(?=[a-z])"), "1 "),
               (re.compile(r"\b(second|2nd)\s+(?=[a-z])"), "2 "),
               (re.compile(r"\b(third|3rd)\s+(?=[a-z])"), "3 ")]
_UNITS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen "
    "fourteen fifteen sixteen seventeen eighteen nineteen".split())}
_TENS = {w: (i + 2) * 10 for i, w in enumerate(
    "twenty thirty forty fifty sixty seventy eighty ninety".split())}
_NUM_WORDS = sorted(set(_UNITS) | set(_TENS) | {"hundred"}, key=len, reverse=True)
_NUMBER_RE = re.compile(r"\b(?:" + "|".join(_NUM_WORDS) + r")(?:[\s-]+(?:" + "|".join(_NUM_WORDS) + r"))*\b")


def words_to_digits(phrase: str) -> str:
    """'three sixteen' -> '3 16'; 'twenty three' -> '23'; 'one hundred twenty three' -> '123'."""
    parts: list[int] = []
    cur: Optional[int] = None
    for w in re.split(r"[\s-]+", phrase.strip()):
        if w == "hundred":
            cur = 100 if cur is None else (cur * 100 if cur < 100 else cur)
            continue
        val = _UNITS.get(w, _TENS.get(w))
        if val is None:
            continue
        if cur is None:
            cur = val
        elif cur >= 100 and cur % 100 == 0:               # one hundred + twenty
            cur += val
        elif cur % 100 >= 20 and cur % 10 == 0 and val < 10:  # twenty + three
            cur += val
        else:                                            # 'three sixteen' -> two numbers
            parts.append(cur)
            cur = val
    if cur is not None:
        parts.append(cur)
    return " ".join(str(p) for p in parts)


def normalise(text: str) -> str:
    t = text.lower()
    for pat, repl in _ORDINAL_RE:
        t = pat.sub(repl, t)
    return _NUMBER_RE.sub(lambda m: words_to_digits(m.group(0)), t)


# ------------------------------------------------------------------ exact citations
@dataclass
class ExactReference:
    book_id: int
    chapter: int
    verse: int
    verse_end: Optional[int]
    matched_text: str


class BookIndex:
    """Matches 'John 3:16', 'Jn 3 16', 'first corinthians 13 verse 4', 'john chapter three verse sixteen'."""

    def __init__(self):
        self._phrases: dict[str, int] = {}
        for b in BOOKS:
            for p in (b.name, *b.aliases):
                self._phrases[p.lower()] = b.book_id
        self._pattern: Optional[re.Pattern] = None

    def add_aliases(self, book_id: int, phrases) -> None:
        """Add pack-supplied aliases (Yoruba, Hausa, Igbo, Swahili book names)."""
        for p in phrases:
            self._phrases[p.lower().strip()] = book_id
        self._pattern = None

    def _compile(self) -> re.Pattern:
        names = sorted(self._phrases, key=len, reverse=True)
        alt = "|".join(r"\s+".join(re.escape(w) for w in p.split()) for p in names)
        return re.compile(
            r"\b(?P<book>" + alt + r")\.?\s*(?:chapter\s+|ch\.?\s*)?"
            r"(?P<ch>\d{1,3})\s*(?:[:.]\s*|\s+verse\s+|\s+)(?P<v>\d{1,3})"
            r"(?:\s*(?:-|to|through)\s*(?P<v2>\d{1,3}))?(?!\d)",
            re.IGNORECASE)

    def find(self, text: str) -> list[ExactReference]:
        if self._pattern is None:
            self._pattern = self._compile()
        refs = []
        for m in self._pattern.finditer(normalise(text)):
            book_key = re.sub(r"\s+", " ", m.group("book").lower())
            refs.append(ExactReference(
                book_id=self._phrases[book_key],
                chapter=int(m.group("ch")),
                verse=int(m.group("v")),
                verse_end=int(m.group("v2")) if m.group("v2") else None,
                matched_text=m.group(0)))
        return refs


# ------------------------------------------------------------------ candidates
@dataclass
class Candidate:
    reference: str
    book_id: int
    book_name: str
    chapter: int
    verse: int
    translation: str
    text: str
    confidence: int
    match_type: str           # "exact" or "paraphrase"
    snippet: str
    id: str = ""
    detected_at: float = 0.0
    status: str = "pending"   # pending | held | approved | rejected
    edited_text: Optional[str] = None

    @property
    def display_text(self) -> str:
        return self.edited_text if self.edited_text is not None else self.text


class VerseDetector:
    def __init__(self, store: VerseStore, books: Optional[BookIndex] = None,
                 paraphrase_threshold: int = 60, paraphrase_matcher=None,
                 prefer_embeddings: bool = False):
        """paraphrase_threshold: 0-100, lower finds more (and more false hits). Tunable per church.
        prefer_embeddings: use a cached sentence-embedding model if one is installed."""
        self.store = store
        self.books = books or BookIndex()
        self.paraphrase = paraphrase_matcher or (
            best_paraphrase_matcher(store, True) if prefer_embeddings else TokenSimilarityMatcher(store))
        self.paraphrase_threshold = paraphrase_threshold

    def detect(self, text: str) -> list[Candidate]:
        out: list[Candidate] = []
        seen: set[tuple[int, int, int]] = set()
        for ref in self.books.find(text):
            verse_text = self.store.get(ref.book_id, ref.chapter, ref.verse)
            if verse_text is None:  # citation not in the active translation
                continue
            key = (ref.book_id, ref.chapter, ref.verse)
            if key in seen:
                continue
            seen.add(key)
            name = BOOK_BY_ID[ref.book_id].name
            ref_str = f"{name} {ref.chapter}:{ref.verse}" + (f"-{ref.verse_end}" if ref.verse_end else "")
            out.append(Candidate(ref_str, ref.book_id, name, ref.chapter, ref.verse,
                                 self.store.translation_id, verse_text, 100, "exact",
                                 text.strip()[-200:]))
        if not out:  # paraphrase only when no explicit citation was spoken
            for score, b, c, v, verse_text in self.paraphrase.match(text):
                if score < self.paraphrase_threshold:
                    break
                name = BOOK_BY_ID[b].name
                out.append(Candidate(f"{name} {c}:{v}", b, name, c, v, self.store.translation_id,
                                     verse_text, score, "paraphrase", text.strip()[-200:]))
                break  # scaffold: top paraphrase only
        return out
