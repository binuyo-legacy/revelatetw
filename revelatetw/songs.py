"""Song lyrics model and library (operator-driven projection).

A Song is a title, an optional artist and an ordered list of Slides. Each Slide is one screen
of text lines with a label such as 'Verse 1' or 'Chorus'. Live detection never touches songs.
Songs are saved as one JSON file per song in a library folder (the store).
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

SECTION_WORDS = ("pre-chorus", "prechorus", "verse", "chorus", "bridge", "intro", "outro", "tag",
                 "refrain", "hook", "interlude", "ending", "coda", "vamp")

# A header is a section word with an optional number or 'x2', written alone, with a colon,
# or in square brackets. 'Tag along with me' is a lyric, not a header.
_HEADER = re.compile(
    r"^[\[(]?\s*(?P<name>(?:%s)(?:\s*\d+|\s*x\s*\d+)?)\s*[\])]?\s*:?$" % "|".join(
        re.escape(w) for w in SECTION_WORDS),
    re.IGNORECASE)
_SAFE_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")


def normalize_label(raw: str) -> str:
    """'verse 1' -> 'Verse 1', 'PRE-CHORUS' -> 'Pre-Chorus'."""
    words = re.sub(r"\s+", " ", raw.strip()).split(" ")
    return " ".join("-".join(p.capitalize() for p in w.split("-")) for w in words)


def split_lyrics(text: str, max_lines: int = 4) -> list["Slide"]:
    """Split pasted lyrics into slides.

    A blank line ends a slide. A header line ([Verse 1], Chorus:, Bridge) ends the previous
    slide and labels the next one. Blocks longer than max_lines are cut into several slides
    (the later ones are labelled '(cont.)'). Unlabelled slides are named 'Slide N'.
    """
    if max_lines < 1:
        raise ValueError("max_lines must be at least 1")
    blocks: list[tuple[Optional[str], list[str]]] = []
    label: Optional[str] = None
    lines: list[str] = []

    def flush() -> None:
        nonlocal label, lines
        if lines:
            blocks.append((label, lines))
            lines = []
            label = None

    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        s = raw.strip()
        if not s:
            flush()
            continue
        m = _HEADER.match(s)
        if m:
            flush()
            label = normalize_label(m.group("name"))
            continue
        lines.append(s)
    flush()

    slides: list[Slide] = []
    for lbl, block in blocks:
        for i in range(0, len(block), max_lines):
            chunk = block[i:i + max_lines]
            if lbl is None:
                name = f"Slide {len(slides) + 1}"
            elif i == 0:
                name = lbl
            else:
                name = f"{lbl} (cont.)"
            slides.append(Slide(label=name, lines=chunk))
    return slides


@dataclass
class Slide:
    label: str
    lines: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"label": self.label, "lines": list(self.lines)}

    @classmethod
    def from_dict(cls, data: dict) -> "Slide":
        return cls(label=str(data.get("label", "")), lines=[str(x) for x in data.get("lines", [])])


@dataclass
class Song:
    title: str
    artist: str = ""
    slides: list[Slide] = field(default_factory=list)
    id: str = ""

    def __post_init__(self) -> None:
        self.title = (self.title or "").strip()
        self.artist = (self.artist or "").strip()
        if not self.title:
            raise ValueError("a song needs a title")
        if not self.id:
            self.id = uuid.uuid4().hex[:12]
        if not _SAFE_ID.fullmatch(self.id):
            raise ValueError(f"song id {self.id!r} must be letters, digits, _ or - (max 64)")

    def search_text(self) -> str:
        lines = [line for s in self.slides for line in s.lines]
        return " ".join([self.title, self.artist, *lines]).lower()

    def to_dict(self) -> dict:
        return {"format": "revelatetw-song", "version": 1, "id": self.id, "title": self.title,
                "artist": self.artist, "slides": [s.to_dict() for s in self.slides]}

    @classmethod
    def from_dict(cls, data: dict) -> "Song":
        return cls(title=str(data.get("title", "")), artist=str(data.get("artist", "")),
                   slides=[Slide.from_dict(s) for s in data.get("slides", [])],
                   id=str(data.get("id", "")))


class SongLibrary:
    """One JSON file per song in a folder. Corrupt files are skipped, never fatal."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, song: Song) -> Path:
        return self.root / f"{song.id}.json"

    def save(self, song: Song) -> Path:
        if not song.slides:
            raise ValueError("split the lyrics into slides before saving")
        path = self.path_for(song)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(song.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
        return path

    def load_all(self) -> list[Song]:
        songs: list[Song] = []
        for path in sorted(self.root.glob("*.json")):
            try:
                songs.append(Song.from_dict(json.loads(path.read_text(encoding="utf-8"))))
            except Exception:  # a bad file must not break the library
                continue
        return sorted(songs, key=lambda s: s.title.lower())

    def search(self, query: str, songs: Optional[Iterable[Song]] = None) -> list[Song]:
        """Every word typed must appear in the title, artist or lyrics (case-insensitive)."""
        pool = list(self.load_all() if songs is None else songs)
        tokens = query.lower().split()
        if not tokens:
            return pool
        return [s for s in pool if all(t in s.search_text() for t in tokens)]
