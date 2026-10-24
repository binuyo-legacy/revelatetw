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

# Short section headers used by many lyric sheets: V1, V2, C, CH, B, PC (case-insensitive).
_ABBR_HEADER = re.compile(r"^[\[(]?\s*(?P<abbr>vs|v|ch|c|pc|b)\s*(?P<num>\d{1,2})?\s*[\])]?\s*:?$",
                          re.IGNORECASE)
_ABBR_NAMES = {"v": "Verse", "vs": "Verse", "c": "Chorus", "ch": "Chorus", "pc": "Pre-Chorus",
               "b": "Bridge"}


def normalize_label(raw: str) -> str:
    """'verse 1' -> 'Verse 1', 'PRE-CHORUS' -> 'Pre-Chorus'."""
    words = re.sub(r"\s+", " ", raw.strip()).split(" ")
    return " ".join("-".join(p.capitalize() for p in w.split("-")) for w in words)


def header_label(line: str) -> Optional[str]:
    """The section label if this line is a header ('Chorus 2:', '[Verse 1]', 'V1', 'C'), else None."""
    s = line.strip()
    m = _HEADER.match(s)
    if m:
        return normalize_label(m.group("name"))
    m = _ABBR_HEADER.match(s)
    if m:
        abbr = m.group("abbr")
        num = m.group("num")
        # A bare single letter is only a header when it is written in capitals ('C', 'V1').
        # A lowercase 'b' or 'c' on its own line is far more likely to be a lyric.
        bare = not num and len(abbr) == 1 and not (s.endswith(":") or s[0] in "[(")
        if bare and not abbr.isupper():
            return None
        name = _ABBR_NAMES[abbr.lower()]
        return f"{name} {num}" if num else name
    return None


Block = tuple[Optional[str], list[str]]


def split_blocks(text: str) -> list[Block]:
    """Group lines into (label, lines) blocks. A blank line or a header line ends a block."""
    blocks: list[Block] = []
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
        hdr = header_label(s)
        if hdr is not None:
            flush()
            label = hdr
            continue
        lines.append(s)
    flush()
    return blocks


def blocks_to_slides(blocks: list[Block], max_lines: int = 4) -> list["Slide"]:
    """Cut each block into slides of at most max_lines lines (continuations marked '(cont.)')."""
    if max_lines < 1:
        raise ValueError("max_lines must be at least 1")
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


def split_lyrics(text: str, max_lines: int = 4) -> list["Slide"]:
    """Split pasted lyrics into slides.

    A blank line ends a slide. A header line ([Verse 1], Chorus:, Bridge, V1, C) ends the previous
    slide and labels the next one. Blocks longer than max_lines are cut into several slides
    (the later ones are labelled '(cont.)'). Unlabelled slides are named 'Slide N'.
    """
    if max_lines < 1:
        raise ValueError("max_lines must be at least 1")
    return blocks_to_slides(split_blocks(text), max_lines)


_GENERIC_LABEL = re.compile(r"Slide \d+$")


def lyrics_text(slides: Iterable["Slide"]) -> str:
    """Render slides back to editor text so split_lyrics(lyrics_text(x)) keeps the labels.

    Generic 'Slide N' names are written without a header; continuation slides repeat the
    base section header.
    """
    blocks: list[str] = []
    for s in slides:
        label = s.label or ""
        if label and not _GENERIC_LABEL.fullmatch(label):
            base = label.split(" (cont.)")[0]
            blocks.append(f"[{base}]\n" + "\n".join(s.lines))
        else:
            blocks.append("\n".join(s.lines))
    return "\n\n".join(blocks)


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

    def copy(self, title: str | None = None) -> "Song":
        """A duplicate with a new id (Save As New)."""
        return Song(title=self.title if title is None else title, artist=self.artist,
                    slides=[Slide(s.label, list(s.lines)) for s in self.slides])

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

    def delete(self, song_id: str) -> bool:
        """Remove the song's file. Returns False when there was no such song."""
        if not _SAFE_ID.fullmatch(song_id or ""):
            return False
        path = self.root / f"{song_id}.json"
        if not path.exists():
            return False
        path.unlink()
        return True

    def get(self, song_id: str) -> Optional[Song]:
        if not _SAFE_ID.fullmatch(song_id or ""):
            return None
        path = self.root / f"{song_id}.json"
        if not path.exists():
            return None
        try:
            return Song.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            return None

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
