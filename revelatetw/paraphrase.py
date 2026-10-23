"""Paraphrase matching (spec F1): finds the verse a speaker is quoting without naming it.

Two scorers behind one interface:
  TokenSimilarityMatcher  (default, pure Python, works fully offline)
      IDF-weighted token overlap with light stemming and fuzzy spelling repair
      ('shepard' -> 'shepherd'). Score is the geometric mean of how much of the spoken
      words appear in the verse and how much of the verse the speaker said.
  EmbeddingMatcher  (optional)
      sentence-transformers cosine similarity. Used only when the package AND a cached
      model are present. Any failure falls back to the token matcher, so a church with no
      internet or no model keeps working.

The threshold is tunable (VerseDetector(paraphrase_threshold=...)); 0-100 scale.
"""
from __future__ import annotations

import difflib
import math
import re
from collections import Counter
from typing import Optional

from .store import VerseStore

STOP = set("""a an and are as at be but by for from had has have he her his i if in into is it
its me my no not of on or our she so that the their them then there they this to was we were
what when who will with you your thy thee thou shall unto upon also""".split())

_SUFFIXES = ("eth", "est", "ing", "ed", "es", "s", "ly")


def stem(word: str) -> str:
    """Light stemmer, enough for KJV-style forms: suffereth->suffer, loveth->love."""
    for suf in _SUFFIXES:
        if len(word) > len(suf) + 3 and word.endswith(suf):
            return word[: -len(suf)]
    return word


def content_tokens(text: str) -> list[str]:
    return [stem(w) for w in re.findall(r"[a-z']+", text.lower())
            if len(w) > 2 and w not in STOP]


class TokenSimilarityMatcher:
    """Pure-Python lexical-semantic scorer. Works offline and needs no model download."""

    backend = "token"

    def __init__(self, store: VerseStore, min_shared: int = 2, fuzzy_cutoff: float = 0.8):
        self._min_shared = min_shared
        self._fuzzy_cutoff = fuzzy_cutoff
        self._verses = []   # (key, Counter of stems, verse text)
        df: Counter = Counter()
        for key, text in store.items():
            toks = Counter(content_tokens(text))
            self._verses.append((key, toks, text))
            df.update(toks.keys())
        n = max(1, len(self._verses))
        self._idf = {t: math.log(1 + n / (1 + d)) + 1.0 for t, d in df.items()}
        self._vocab = sorted(self._idf)
        self._fuzzy_cache: dict[str, Optional[str]] = {}
        self._postings: dict[str, list[int]] = {}
        for i, (_, toks, _) in enumerate(self._verses):
            for t in toks:
                self._postings.setdefault(t, []).append(i)
        self._verse_mass = [sum(self._idf[t] * c for t, c in toks.items())
                            for _, toks, _ in self._verses]

    def _repair(self, token: str) -> Optional[str]:
        """Map an unknown token to a close vocabulary word (mishearing / misspelling)."""
        if token in self._idf:
            return token
        if len(token) < 5:
            return None
        if token not in self._fuzzy_cache:
            close = difflib.get_close_matches(token, self._vocab, n=1, cutoff=self._fuzzy_cutoff)
            self._fuzzy_cache[token] = close[0] if close else None
        return self._fuzzy_cache[token]

    def match(self, text: str) -> list[tuple[int, int, int, int, str]]:
        """Return (score 0-100, book, chapter, verse, verse_text), best first."""
        q_tokens = [t for t in (self._repair(t) for t in content_tokens(text)) if t]
        if not q_tokens:
            return []
        q_set = set(q_tokens)
        q_mass = sum(self._idf[t] for t in q_set)
        candidates: Counter = Counter()
        for t in q_set:
            for i in self._postings.get(t, ()):
                candidates[i] += 1
        hits = []
        for i, shared_n in candidates.items():
            if shared_n < self._min_shared:
                continue
            (b, c, v), toks, verse_text = self._verses[i]
            shared_mass = sum(self._idf[t] for t in q_set if t in toks)
            cov_q = shared_mass / q_mass                       # how much of the speech is in the verse
            cov_v = shared_mass / max(self._verse_mass[i], 1e-9)  # how much of the verse was said
            score = round(100 * math.sqrt(cov_q * cov_v))
            hits.append((score, b, c, v, verse_text))
        return sorted(hits, reverse=True)


class EmbeddingMatcher:
    """Sentence-embedding scorer (optional). Needs `pip install sentence-transformers`
    and a model that is already cached locally, so it never downloads at church time."""

    backend = "embedding"

    def __init__(self, store: VerseStore, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        from sentence_transformers import SentenceTransformer, util  # raises if missing
        self._util = util
        self._model = SentenceTransformer(model_name, local_files_only=True)  # raises if not cached
        self._keys, self._texts = [], []
        for key, text in store.items():
            self._keys.append(key)
            self._texts.append(text)
        self._emb = self._model.encode(self._texts, convert_to_tensor=True, batch_size=256,
                                       show_progress_bar=False)

    def match(self, text: str) -> list[tuple[int, int, int, int, str]]:
        q = self._model.encode(text, convert_to_tensor=True)
        sims = self._util.cos_sim(q, self._emb)[0]
        order = sims.argsort(descending=True)[:5].tolist()
        out = []
        for i in order:
            (b, c, v) = self._keys[i]
            out.append((max(0, round(100 * float(sims[i]))), b, c, v, self._texts[i]))
        return out


def best_paraphrase_matcher(store: VerseStore, prefer_embeddings: bool = True):
    """Embeddings when available and cached; otherwise the offline token matcher."""
    if prefer_embeddings:
        try:
            return EmbeddingMatcher(store)
        except Exception:
            pass
    return TokenSimilarityMatcher(store)
