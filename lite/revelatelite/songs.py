"""Songs and lyrics for Lite. Plain Python 3.8 (no dataclasses tricks, no new typing syntax).

Same file layout as the main app: one JSON file per song ({"format": "revelatetw-song", ...}),
so songs can be copied between the two editions. Pasted lyrics are cut into slides: a blank line
ends a slide, a header line ([Verse 1], Chorus:, V1, C) labels the next one, and long blocks are
cut into slides of at most max_lines lines.
"""
import json
import os
import re
import uuid

SECTION_WORDS = ("pre-chorus", "prechorus", "verse", "chorus", "bridge", "intro", "outro", "tag",
                 "refrain", "hook", "interlude", "ending", "coda", "vamp")
_HEADER = re.compile(
    r"^[\[(]?\s*(?P<name>(?:%s)(?:\s*\d+|\s*x\s*\d+)?)\s*[\])]?\s*:?$" % "|".join(re.escape(w) for w in SECTION_WORDS),
    re.IGNORECASE)
_ABBR = re.compile(r"^[\[(]?\s*(?P<abbr>vs|v|ch|c|pc|b)\s*(?P<num>\d{1,2})?\s*[\])]?\s*:?$", re.IGNORECASE)
_ABBR_NAMES = {"v": "Verse", "vs": "Verse", "c": "Chorus", "ch": "Chorus", "pc": "Pre-Chorus", "b": "Bridge"}
_SAFE_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")
_GENERIC = re.compile(r"Slide \d+$")


def normalize_label(raw):
    words = re.sub(r"\s+", " ", raw.strip()).split(" ")
    return " ".join("-".join(p.capitalize() for p in w.split("-")) for w in words)


def header_label(line):
    s = line.strip()
    m = _HEADER.match(s)
    if m:
        return normalize_label(m.group("name"))
    m = _ABBR.match(s)
    if m:
        abbr, num = m.group("abbr"), m.group("num")
        bare = not num and len(abbr) == 1 and not (s.endswith(":") or s[0] in "[(")
        if bare and not abbr.isupper():      # a lone lowercase 'c' is a lyric, not a header
            return None
        name = _ABBR_NAMES[abbr.lower()]
        return "%s %s" % (name, num) if num else name
    return None


def split_lyrics(text, max_lines=4):
    """Pasted lyrics -> list of {"label", "lines"} slides."""
    if max_lines < 1:
        raise ValueError("max_lines must be at least 1")
    blocks, label, lines = [], None, []

    def flush():
        nonlocal label, lines
        if lines:
            blocks.append((label, lines))
        label, lines = None, []

    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        s = raw.strip()
        if not s:
            flush()
            continue
        h = header_label(s)
        if h is not None:
            flush()
            label = h
            continue
        lines.append(s)
    flush()
    slides = []
    for lbl, block in blocks:
        for i in range(0, len(block), max_lines):
            if lbl is None:
                name = "Slide %d" % (len(slides) + 1)
            else:
                name = lbl if i == 0 else "%s (cont.)" % lbl
            slides.append({"label": name, "lines": block[i:i + max_lines]})
    return slides


def lyrics_text(slides):
    """Slides back to editor text; split_lyrics(lyrics_text(x)) keeps the labels."""
    out = []
    for s in slides:
        label = s.get("label", "")
        if label and not _GENERIC.fullmatch(label):
            out.append("[%s]\n%s" % (label.split(" (cont.)")[0], "\n".join(s["lines"])))
        else:
            out.append("\n".join(s["lines"]))
    return "\n\n".join(out)


class Song(object):
    def __init__(self, title, artist="", slides=None, id=""):
        self.title = (title or "").strip()
        self.artist = (artist or "").strip()
        if not self.title:
            raise ValueError("a song needs a title")
        self.slides = slides or []
        self.id = id or uuid.uuid4().hex[:12]
        if not _SAFE_ID.fullmatch(self.id):
            raise ValueError("bad song id")

    def search_text(self):
        return " ".join([self.title, self.artist] + [l for s in self.slides for l in s["lines"]]).lower()

    def to_dict(self):
        return {"format": "revelatetw-song", "version": 1, "id": self.id, "title": self.title,
                "artist": self.artist, "slides": [{"label": s["label"], "lines": list(s["lines"])} for s in self.slides]}

    @classmethod
    def from_dict(cls, d):
        slides = []
        for s in d.get("slides", []):
            lines = [str(x) for x in s.get("lines", []) if str(x).strip()]
            if lines:
                slides.append({"label": str(s.get("label", "")) or "Slide %d" % (len(slides) + 1), "lines": lines})
        return cls(str(d.get("title", "")), str(d.get("artist", "")), slides, str(d.get("id", "")))

    def slide_ref(self, i):
        """Heading shown with a slide (like a verse reference): 'Title - Chorus'."""
        return "%s - %s" % (self.title, self.slides[i]["label"])

    def slide_body(self, i):
        return "\n".join(self.slides[i]["lines"])


class SongLibrary(object):
    """One JSON file per song. A damaged file is skipped, never fatal."""

    def __init__(self, root):
        self.root = root
        try:
            os.makedirs(root, exist_ok=True)
        except OSError:
            pass

    def _path(self, song_id):
        return os.path.join(self.root, song_id + ".json")

    def save(self, song):
        if not song.slides:
            raise ValueError("add some lyrics first")
        path = self._path(song.id)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(song.to_dict(), f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)

    def delete(self, song_id):
        if not _SAFE_ID.fullmatch(song_id or "") or not os.path.isfile(self._path(song_id)):
            return False
        os.remove(self._path(song_id))
        return True

    def load_all(self):
        songs = []
        try:
            names = sorted(os.listdir(self.root))
        except OSError:
            return songs
        for n in names:
            if not n.endswith(".json"):
                continue
            try:
                with open(os.path.join(self.root, n), "r", encoding="utf-8") as f:
                    songs.append(Song.from_dict(json.load(f)))
            except (OSError, ValueError, AttributeError, TypeError):
                continue
        return sorted(songs, key=lambda s: s.title.lower())

    @staticmethod
    def search(songs, query):
        tokens = query.lower().split()
        return [s for s in songs if all(t in s.search_text() for t in tokens)]


def import_rtsong(text):
    """Songs from a .rtsong document ({"format": "rtsong", "version": 1, "songs": [...]}).
    Raises ValueError with a plain message when the file is not usable."""
    try:
        data = json.loads(text.lstrip("\ufeff"))
    except ValueError:
        raise ValueError("this is not a valid song file")
    if not isinstance(data, dict) or data.get("format") != "rtsong":
        raise ValueError("this is not a RevelateTW song file")
    if data.get("version") != 1:
        raise ValueError("this song file version is not supported by this RevelateTW Lite")
    songs = []
    for n, e in enumerate(data.get("songs") or [], 1):
        if not isinstance(e, dict) or not isinstance(e.get("title"), str) or not e["title"].strip():
            raise ValueError("song %d needs a title" % n)
        slides = []
        for sec in e.get("sections") or []:
            lines = [l for l in (sec.get("lines") or []) if isinstance(l, str) and l.strip()]
            if lines:
                slides.append({"label": str(sec.get("label") or "Slide %d" % (len(slides) + 1)), "lines": lines})
        if not slides:
            raise ValueError("'%s' has no lyrics" % e["title"])
        songs.append(Song(e["title"], e.get("author") or "", slides))
    if not songs:
        raise ValueError("no songs found in this file")
    return songs
