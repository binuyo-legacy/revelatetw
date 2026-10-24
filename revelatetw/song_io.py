"""Song import and export: the .rtsong file format and plain lyrics text (headless, no Qt).

.rtsong is a JSON file so other tools and churches can produce it:

    {
      "format": "rtsong",
      "version": 1,
      "songs": [
        {
          "title": "Amazing Grace",
          "author": "John Newton",            (optional)
          "sections": [
            {"label": "Verse 1", "lines": ["Amazing grace how sweet the sound", "..."]},
            {"label": "Chorus",  "lines": ["..."]}
          ]
        }
      ]
    }

One file can hold one song or a whole library. Each section becomes one slide, in order.
Unknown keys are ignored. A file with a version newer than this build is refused with a
clear message, never guessed at.
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

from .songs import Slide, Song, blocks_to_slides, header_label, split_blocks

FORMAT = "rtsong"
VERSION = 1
EXTENSION = ".rtsong"
LEGACY_APP_FORMAT = "revelatetw-song"   # the single-song .json the app wrote before .rtsong


class SongFileError(ValueError):
    """A file or pasted text that cannot be imported. The message is shown to the operator as-is."""


@dataclass
class PlannedSong:
    song: Song                 # the song that will be written (title/id already decided)
    original_title: str        # the title as it appeared in the file or text
    action: str                # "new" | "renamed" | "replace"

    @property
    def title(self) -> str:
        return self.song.title


@dataclass
class ImportBatch:
    """What a file or paste contains, before anything is saved."""
    source: str                # display name, e.g. 'worship_set.rtsong' or 'pasted lyrics'
    kind: str                  # "rtsong" | "text"
    songs: list[Song] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def format_label(self) -> str:
        n = len(self.songs)
        if self.kind == "rtsong":
            return f"{self.source} \u00b7 {n} song{'s' if n != 1 else ''}"
        return f"{self.source} \u00b7 {n} song{'s' if n != 1 else ''} detected"


# ---------------------------------------------------------------- export

def song_to_entry(song: Song) -> dict:
    entry: dict = {"title": song.title}
    if song.artist:
        entry["author"] = song.artist
    entry["sections"] = [{"label": s.label, "lines": list(s.lines)} for s in song.slides]
    return entry


def build_document(songs: Iterable[Song]) -> dict:
    return {"format": FORMAT, "version": VERSION, "songs": [song_to_entry(s) for s in songs]}


def export_songs(songs: Iterable[Song], path: str | Path) -> Path:
    """Write one or many songs to a .rtsong file (atomic replace)."""
    songs = list(songs)
    if not songs:
        raise SongFileError("there are no songs to export")
    for song in songs:
        if not song.slides:
            raise SongFileError(f"'{song.title}' has no slides, so it cannot be exported")
    out = Path(path)
    if out.suffix.lower() != EXTENSION:
        out = out.with_suffix(EXTENSION)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text(json.dumps(build_document(songs), ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(out)
    return out


def export_song(song: Song, path: str | Path) -> Path:
    return export_songs([song], path)


def safe_filename(title: str, fallback: str = "song") -> str:
    """A file-name stem that is safe on Windows (no \\ / : * ? \" < > |)."""
    stem = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', " ", title or "").strip().rstrip(".")
    stem = re.sub(r"\s+", " ", stem)[:80].strip()
    return stem or fallback


# ---------------------------------------------------------------- .rtsong import

def parse_rtsong(text: str) -> list[Song]:
    """Validate and load an .rtsong document. Raises SongFileError with a plain message."""
    try:
        data = json.loads(text.lstrip("\ufeff"))
    except ValueError as exc:
        raise SongFileError(f"this is not a valid .rtsong file (JSON error on line {getattr(exc, 'lineno', '?')})")
    if not isinstance(data, dict):
        raise SongFileError("this is not a RevelateTW song file (the top level must be an object)")
    if data.get("format") != FORMAT:
        raise SongFileError('this is not a RevelateTW song file (expected "format": "rtsong")')
    version = data.get("version")
    if not isinstance(version, int) or isinstance(version, bool):
        raise SongFileError('"version" must be a whole number')
    if version > VERSION:
        raise SongFileError(f"this file uses song format version {version}, which is newer than this "
                            f"RevelateTW reads (version {VERSION}). Update RevelateTW to import it.")
    if version != VERSION:
        raise SongFileError(f"unsupported song format version {version} (this RevelateTW reads version {VERSION})")
    entries = data.get("songs")
    if not isinstance(entries, list) or not entries:
        raise SongFileError('"songs" must be a list with at least one song')
    return [_parse_entry(entry, n) for n, entry in enumerate(entries, 1)]


def _parse_entry(entry, n: int) -> Song:
    if not isinstance(entry, dict):
        raise SongFileError(f"song {n} must be an object")
    title = entry.get("title")
    if not isinstance(title, str) or not title.strip():
        raise SongFileError(f"song {n} needs a title")
    where = f"'{title.strip()}'"
    author = entry.get("author", "")
    if author is None:
        author = ""
    if not isinstance(author, str):
        raise SongFileError(f"{where}: author must be text")
    sections = entry.get("sections")
    if not isinstance(sections, list) or not sections:
        raise SongFileError(f"{where} needs at least one section")
    slides: list[Slide] = []
    for j, sec in enumerate(sections, 1):
        if not isinstance(sec, dict):
            raise SongFileError(f"{where}: section {j} must be an object")
        label = sec.get("label")
        if not isinstance(label, str) or not label.strip():
            raise SongFileError(f"{where}: section {j} needs a label such as Verse 1 or Chorus")
        lines = sec.get("lines")
        if not isinstance(lines, list) or not lines:
            raise SongFileError(f"{where}: section '{label}' needs at least one line")
        for k, line in enumerate(lines, 1):
            if not isinstance(line, str) or not line.strip():
                raise SongFileError(f"{where}: line {k} of section '{label}' must be non-empty text")
        slides.append(Slide(label=label, lines=list(lines)))
    return Song(title=title, artist=author, slides=slides)


# ---------------------------------------------------------------- raw lyrics import

def read_text_file(path: str | Path) -> str:
    raw = Path(path).read_bytes()
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")


def parse_lyrics(text: str, title: str = "", author: str = "", fallback_title: str = "Untitled song",
                 max_lines: int = 4) -> Song:
    """Turn plain lyrics into one song.

    Title: when `title` is empty, the first non-empty line becomes the title and is removed from
    the lyrics. A first line that is a section header ([Verse 1], Chorus) is not a title; the
    fallback title is used and the header stays in the lyrics.

    Sections: blank lines end a slide, header lines label the next slide. When the text has no
    explicit header at all, blocks that repeat exactly are tagged Chorus.
    """
    if max_lines < 1:
        raise ValueError("max_lines must be at least 1")
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    body = text
    if not title.strip():
        first = next((i for i, ln in enumerate(lines) if ln.strip()), None)
        if first is not None and header_label(lines[first]) is None:
            title = lines[first].strip()
            body = "\n".join(lines[first + 1:])
        else:
            title = fallback_title
    blocks = split_blocks(body)
    if not blocks:
        raise SongFileError("no lyrics found after the title")
    has_explicit = any(lbl is not None for lbl, _ in blocks)
    if not has_explicit:
        seen: dict[tuple, int] = {}
        for _, block in blocks:
            key = tuple(ln.casefold() for ln in block)
            seen[key] = seen.get(key, 0) + 1
        blocks = [("Chorus" if seen[tuple(ln.casefold() for ln in block)] >= 2 else None, block)
                  for _, block in blocks]
    slides = blocks_to_slides(blocks, max_lines)
    if not slides:
        raise SongFileError("no lyrics found after the title")
    return Song(title=title, artist=author.strip(), slides=slides)


def import_text(text: str, source: str = "pasted lyrics") -> ImportBatch:
    """Import pasted text. Text that starts with '{' is read as an .rtsong document."""
    stripped = text.lstrip("\ufeff \t\r\n")
    if not stripped:
        raise SongFileError("paste some lyrics first")
    if stripped.startswith("{"):
        return ImportBatch(source=source, kind="rtsong", songs=parse_rtsong(stripped))
    return ImportBatch(source=source, kind="text", songs=[parse_lyrics(text)])


def import_file(path: str | Path) -> ImportBatch:
    """Read a .rtsong, .json (single song from the app or an .rtsong), or .txt lyrics file."""
    p = Path(path)
    ext = p.suffix.lower()
    if not p.exists():
        raise SongFileError(f"{p.name} was not found")
    text = read_text_file(p)
    if ext == EXTENSION:
        return ImportBatch(source=p.name, kind="rtsong", songs=parse_rtsong(text))
    if ext == ".json":
        return _import_json(p.name, text)
    if ext in (".txt", ".text", ".lyrics", ""):
        if not text.strip():
            raise SongFileError(f"{p.name} is empty")
        return ImportBatch(source=p.name, kind="text",
                           songs=[parse_lyrics(text, fallback_title=p.stem.replace("_", " ").strip() or "Untitled song")])
    raise SongFileError(f"{p.name}: unsupported file type. Choose a .rtsong or a .txt lyrics file.")


def _import_json(name: str, text: str) -> ImportBatch:
    try:
        data = json.loads(text.lstrip("\ufeff"))
    except ValueError:
        raise SongFileError(f"{name} is not valid JSON. Choose a .rtsong or a .txt lyrics file.")
    if isinstance(data, dict) and data.get("format") == LEGACY_APP_FORMAT:
        song = Song.from_dict(data)
        if not song.slides:
            raise SongFileError(f"{name} has no slides")
        return ImportBatch(source=name, kind="rtsong", songs=[song])
    return ImportBatch(source=name, kind="rtsong", songs=parse_rtsong(text))


# ---------------------------------------------------------------- duplicates

def unique_title(title: str, taken: set[str]) -> str:
    """'Amazing Grace' -> 'Amazing Grace (2)' when the title (any case) is already taken."""
    base = title.strip()
    if base.casefold() not in taken:
        return base
    n = 2
    while f"{base} ({n})".casefold() in taken:
        n += 1
    return f"{base} ({n})"


def plan_import(songs: Iterable[Song], existing: Iterable[Song], replace: bool = False) -> list[PlannedSong]:
    """Decide the final title and file id for each imported song.

    replace=False (default): a title already in the library, or already used earlier in this
    batch, gets a ' (2)' suffix. replace=True: a song whose title matches an existing one takes
    that song's id, so saving overwrites the old file (only the first match per batch).
    """
    existing = list(existing)
    taken = {s.title.casefold() for s in existing}
    by_title: dict[str, Song] = {}
    for s in existing:
        by_title.setdefault(s.title.casefold(), s)
    claimed: set[str] = set()
    plan: list[PlannedSong] = []
    for song in songs:
        original = song.title
        match = by_title.get(original.casefold())
        if replace and match is not None and match.id not in claimed:
            claimed.add(match.id)
            new = Song(title=original, artist=song.artist, slides=song.slides, id=match.id)
            plan.append(PlannedSong(new, original, "replace"))
            continue
        title = unique_title(original, taken)
        taken.add(title.casefold())
        new = Song(title=title, artist=song.artist, slides=song.slides, id="")
        plan.append(PlannedSong(new, original, "renamed" if title != original else "new"))
    return plan


def save_plan(library, plan: Iterable[PlannedSong]) -> list[Song]:
    """Write every planned song through the SongLibrary. Returns the saved songs."""
    saved = []
    for item in plan:
        library.save(item.song)
        saved.append(item.song)
    return saved


def slide_counts(slides: Iterable[Slide]) -> str:
    """'4 slides: 2 verses, 1 chorus' for the preview summary."""
    slides = list(slides)
    kinds: dict[str, int] = {}
    for s in slides:
        base = re.sub(r"\s*\(cont\.\)$", "", s.label or "").strip()
        base = re.sub(r"\s*\d+$", "", base).strip()
        kind = (base or "unlabelled").lower()
        kinds[kind] = kinds.get(kind, 0) + 1
    plural = {"verse": "verses", "chorus": "choruses", "bridge": "bridges", "pre-chorus": "pre-choruses"}
    parts = [f"{n} {plural.get(k, k) if n != 1 else k}" for k, n in kinds.items()]
    n = len(slides)
    head = f"{n} slide" + ("" if n == 1 else "s")
    return head + (": " + ", ".join(parts) if parts else "")
