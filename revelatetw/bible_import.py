"""Import a user's own licensed Bible translation: USFM, OSIS/XML, Zefania XML or plain text.

convert_file() reads a file, detects its format (by extension and by content), parses it and
returns an ImportResult with the canonical verses plus a list of anomalies. Nothing is written.
write_import() stores a parsed result as data/bible/<CODE>.sqlite, using the same pack schema the
bundled packs use (VerseStore.write_pack, the writer scripts/build_bible_bundle.py calls), and marks
the pack user_imported=1 so it is never treated as one of the bundled public-domain translations.

Supported input:
  USFM     (.usfm, .usfm3, .sfm): \\id, \\c and \\v markers. Footnotes, cross-references, headings and
           character markers are dropped; the verse text is kept.
  OSIS     (.osis, or .xml with osisID attributes): <verse osisID="John.3.16"> container verses and
           sID/eID milestone verses. Notes and titles are dropped.
  Zefania  (.xml with root <XMLBIBLE>): <BIBLEBOOK number="1" bname="Genesis"> holding
           <CHAPTER cnumber="1"> holding <VERS vnumber="1">text</VERS>. Tag and
           attribute names are matched case-insensitively, namespaces are ignored, and
           nested markup text is kept via itertext. Headings and metadata are skipped.
           The file header (biblename, copyright) is read as metadata only and is never
           stored as a translation; the user still supplies name, code and licence.
  Text     (.txt, or any other plain file that has "Book C:V text" lines): lenient, one verse per line.
Anything else (PDF, Word, images, XML that is neither OSIS nor Zefania) raises
UnsupportedFormatError.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from .bible import (DEFAULT_BIBLE_DIR, ID_RE, PACK_SUFFIX, RESERVED_IDS, BibleImportError, Translation)
from .books import BOOK_BY_ID, BOOKS, name_forms
from .store import VerseStore

FORMAT_LABELS = {"usfm": "USFM", "osis": "OSIS", "zefania": "Zefania XML", "text": "Plain text"}
SUPPORTED_FORMATS_HELP = (
    "RevelateTW reads four formats:\n"
    "- USFM (.usfm or .usfm3): the standard Bible text format used by Paratext and most publishers.\n"
    "- OSIS (.osis, or .xml that uses osisID verse references).\n"
    "- Zefania XML (.xml with an <XMLBIBLE> root and <BIBLEBOOK>/<CHAPTER>/<VERS> verses).\n"
    "- Plain text (.txt) with one verse per line, like: John 3:16 For God so loved the world ...\n\n"
    "PDF, Word, EPUB and image files are not supported. Export the translation from its publisher's "
    "software as USFM, OSIS or Zefania XML, then choose that file."
)
UNSUPPORTED_EXTS = {".pdf", ".doc", ".docx", ".odt", ".rtf", ".epub", ".mobi", ".zip", ".rar", ".7z",
                    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".mp3", ".mp4", ".wav", ".exe", ".html", ".htm"}


class UnsupportedFormatError(BibleImportError):
    """The file is not in a format the importer reads. The message is safe to show the user."""


# USFM book codes (3 characters, upper case) to canonical book id.
USFM_CODES = {
    "GEN": 1, "EXO": 2, "LEV": 3, "NUM": 4, "DEU": 5, "JOS": 6, "JDG": 7, "RUT": 8, "1SA": 9, "2SA": 10,
    "1KI": 11, "2KI": 12, "1CH": 13, "2CH": 14, "EZR": 15, "NEH": 16, "EST": 17, "JOB": 18, "PSA": 19,
    "PRO": 20, "ECC": 21, "SNG": 22, "ISA": 23, "JER": 24, "LAM": 25, "EZK": 26, "DAN": 27, "HOS": 28,
    "JOL": 29, "AMO": 30, "OBA": 31, "JON": 32, "MIC": 33, "NAM": 34, "HAB": 35, "ZEP": 36, "HAG": 37,
    "ZEC": 38, "MAL": 39, "MAT": 40, "MRK": 41, "LUK": 42, "JHN": 43, "ACT": 44, "ROM": 45, "1CO": 46,
    "2CO": 47, "GAL": 48, "EPH": 49, "PHP": 50, "COL": 51, "1TH": 52, "2TH": 53, "1TI": 54, "2TI": 55,
    "TIT": 56, "PHM": 57, "HEB": 58, "JAS": 59, "1PE": 60, "2PE": 61, "1JN": 62, "2JN": 63, "3JN": 64,
    "JUD": 65, "REV": 66,
}
# OSIS book abbreviations (the part of osisID before the first dot) to canonical book id.
OSIS_CODES = {
    "Gen": 1, "Exod": 2, "Lev": 3, "Num": 4, "Deut": 5, "Josh": 6, "Judg": 7, "Ruth": 8, "1Sam": 9,
    "2Sam": 10, "1Kgs": 11, "2Kgs": 12, "1Chr": 13, "2Chr": 14, "Ezra": 15, "Neh": 16, "Esth": 17,
    "Job": 18, "Ps": 19, "Prov": 20, "Eccl": 21, "Song": 22, "Isa": 23, "Jer": 24, "Lam": 25, "Ezek": 26,
    "Dan": 27, "Hos": 28, "Joel": 29, "Amos": 30, "Obad": 31, "Jonah": 32, "Mic": 33, "Nah": 34,
    "Hab": 35, "Zeph": 36, "Hag": 37, "Zech": 38, "Mal": 39, "Matt": 40, "Mark": 41, "Luke": 42,
    "John": 43, "Acts": 44, "Rom": 45, "1Cor": 46, "2Cor": 47, "Gal": 48, "Eph": 49, "Phil": 50,
    "Col": 51, "1Thess": 52, "2Thess": 53, "1Tim": 54, "2Tim": 55, "Titus": 56, "Phlm": 57, "Heb": 58,
    "Jas": 59, "1Pet": 60, "2Pet": 61, "1John": 62, "2John": 63, "3John": 64, "Jude": 65, "Rev": 66,
}
_OSIS_SKIP = {"note", "title", "head", "figure", "caption"}
# Zefania XML: local tag names (namespace stripped, lower-cased) treated as metadata, dropped with
# their children. Inline highlights (christ, gram) carry verse text and are kept via itertext.
_ZEFANIA_SKIP = {"heading", "footnote", "font", "br", "link"}
_USFM_FOOTNOTE = re.compile(r"\\[fxFX]\s.*?\\[fxFX]\*", re.S)
_USFM_MARK = re.compile(r"\\(id|c|v)(?=\s)")
_USFM_VERSE_NUM = re.compile(r"\s*(\d+)([a-z]?)(\s*-\s*\d+[a-z]?)?")
_USFM_SKIP_LINE = re.compile(
    r"\\(?:mte|imte|imt|mt|ms|mr|sp|sts|cl|cp|rem|toc|ide|ip|io|iot|is|ie|s|r|d|h|id)\d*(?![A-Za-z])")
_USFM_CHAR_MARK = re.compile(r"\\\+?[A-Za-z]+\d?\*?")
_TEXT_LINE = re.compile(r"^\s*((?:[1-3]\s?)?[A-Za-z][A-Za-z.' ]*?)\s+(\d+)\s*:\s*(\d+)\s*(.*)$")
_TEXT_LEAD = re.compile(r"^[-:.)]\s*")
_SAMPLE_REFS = (("John", 3, 16), ("Genesis", 1, 1), ("Psalms", 23, 1))


def _norm_name(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace(".", "").strip().lower())


NAME_INDEX: dict[str, int] = {_norm_name(f): b.book_id for b in BOOKS for f in name_forms(b.book_id)}


class _Collector:
    """Gathers verses and anomalies while a parser runs."""

    def __init__(self) -> None:
        self.verses: dict[tuple[int, int, int], str] = {}
        self.empty_verses = 0
        self.duplicate_verses = 0
        self.range_verses = 0
        self.unknown_books: list[str] = []
        self.unparseable = 0
        self.unparseable_samples: list[str] = []

    def add(self, book_id: int, chapter: int, verse: int, body: str) -> None:
        text = " ".join(body.split())
        if not text:
            self.empty_verses += 1
            return
        key = (book_id, chapter, verse)
        if key in self.verses:
            self.duplicate_verses += 1
            return
        self.verses[key] = text

    def unknown(self, code: str) -> None:
        if code not in self.unknown_books and len(self.unknown_books) < 20:
            self.unknown_books.append(code)

    def bad_line(self, sample: str) -> None:
        self.unparseable += 1
        if len(self.unparseable_samples) < 5:
            self.unparseable_samples.append(sample.strip()[:80])


@dataclass
class ImportResult:
    format: str                       # "usfm" | "osis" | "zefania" | "text"
    source_name: str
    verses: dict = field(default_factory=dict)   # (book_id, chapter, verse) -> text
    empty_verses: int = 0
    duplicate_verses: int = 0
    range_verses: int = 0
    unknown_books: list = field(default_factory=list)
    unparseable: int = 0
    unparseable_samples: list = field(default_factory=list)
    decode_replacements: int = 0
    source_biblename: str = ""        # header metadata only (e.g. XMLBIBLE biblename); never stored

    @property
    def format_label(self) -> str:
        return FORMAT_LABELS.get(self.format, self.format)

    @property
    def book_ids(self) -> set:
        return {b for b, _, _ in self.verses}

    @property
    def book_count(self) -> int:
        return len(self.book_ids)

    @property
    def chapter_count(self) -> int:
        return len({(b, c) for b, c, _ in self.verses})

    @property
    def verse_count(self) -> int:
        return len(self.verses)

    @property
    def missing_books(self) -> list:
        return [BOOK_BY_ID[i].name for i in sorted(BOOK_BY_ID) if i not in self.book_ids]

    @property
    def notes(self) -> list:
        """Plain-language anomalies for the preview. Empty when the file parsed cleanly."""
        out = []
        if self.missing_books:
            n = len(self.missing_books)
            out.append(f"{n} book(s) not in the file: " + (", ".join(self.missing_books) if n <= 5 else
                                                           ", ".join(self.missing_books[:5]) + ", ..."))
        if self.empty_verses:
            out.append(f"{self.empty_verses} verse(s) had no text and were skipped")
        if self.duplicate_verses:
            out.append(f"{self.duplicate_verses} duplicate verse(s) ignored (first copy kept)")
        if self.unparseable:
            out.append(f"{self.unparseable} line(s) could not be read")
        if self.unknown_books:
            out.append("unknown book name(s): " + ", ".join(self.unknown_books))
        if self.range_verses:
            out.append(f"{self.range_verses} verse range(s) kept under the first verse number")
        if self.decode_replacements:
            out.append(f"{self.decode_replacements} byte(s) were not valid UTF-8 and were replaced")
        return out

    def rows(self) -> list:
        return [(b, c, v, t) for (b, c, v), t in sorted(self.verses.items())]

    def samples(self) -> list:
        """Three verses to show in the preview: John 3:16, Genesis 1:1, Psalms 23:1 when present."""
        picked = []
        for name, c, v in _SAMPLE_REFS:
            bid = NAME_INDEX[_norm_name(name)]
            if (bid, c, v) in self.verses:
                picked.append((bid, c, v))
        for key in sorted(self.verses):
            if len(picked) >= 3:
                break
            if key not in picked:
                picked.append(key)
        return [(f"{BOOK_BY_ID[b].name} {c}:{v}", self.verses[(b, c, v)]) for b, c, v in picked[:3]]


def _decode(raw: bytes) -> tuple[str, int]:
    try:
        return raw.decode("utf-8-sig"), 0
    except UnicodeDecodeError:
        text = raw.decode("cp1252", errors="replace")
        return text.lstrip("\ufeff"), text.count("\ufffd")


def _xml_root_local(text: str) -> str | None:
    """Local name of the XML root element, lower-cased, or None when there is no usable tag.

    Skips the XML declaration, processing instructions, comments and DOCTYPE so a
    namespaced or decorated header still yields the root name. Only the head of the
    document is scanned; a full parse is left to the format parser.
    """
    head = text[:8192]
    i = 0
    n = len(head)
    while i < n:
        if head[i] != "<":
            i += 1
            continue
        rest = head[i:]
        if rest.startswith("<?") or rest.startswith("<!--"):
            end = rest.find("?>") if rest.startswith("<?") else rest.find("-->")
            close = "?>" if rest.startswith("<?") else "-->"
            if end == -1:
                return None
            i += end + len(close)
            continue
        if rest.startswith("<!") or rest.startswith("</"):
            end = rest.find(">")
            if end == -1:
                return None
            i += end + 1
            continue
        m = re.match(r"<([A-Za-z_][\w:.-]*)", rest)
        if m:
            return m.group(1).rsplit(":", 1)[-1].rsplit("}", 1)[-1].lower()
        return None
    return None


def _is_zefania_xml(text: str) -> bool:
    """True only for Zefania XML: root element is <XMLBIBLE> (case-insensitive, any namespace)."""
    return _xml_root_local(text) == "xmlbible"


def detect_format(path: Path, text: str) -> str:
    """Return "usfm", "osis", "zefania" or "text". Raises UnsupportedFormatError otherwise."""
    ext = path.suffix.lower()
    if ext in UNSUPPORTED_EXTS:
        raise UnsupportedFormatError(f"{path.name} is a {ext[1:].upper()} file. " + SUPPORTED_FORMATS_HELP)
    head = text.lstrip(" \t\r\n")
    if head.startswith("<"):
        root = _xml_root_local(text)
        if root == "xmlbible":
            return "zefania"
        if "osisID" in text:
            return "osis"
        if root is not None:
            raise UnsupportedFormatError(
                f"{path.name} is XML with root <{root}>, but it is neither OSIS (no osisID) nor "
                f"Zefania (no <XMLBIBLE> root). " + SUPPORTED_FORMATS_HELP)
        raise UnsupportedFormatError(f"{path.name} is XML, but its root element could not be read. "
                                     + SUPPORTED_FORMATS_HELP)
    if _USFM_MARK.search(text[:200000]):
        return "usfm"
    if ext == ".txt" or any(_TEXT_LINE.match(ln) for ln in head[:4000].splitlines()[:50]):
        return "text"
    raise UnsupportedFormatError(f"{path.name} is not a format RevelateTW can read. " + SUPPORTED_FORMATS_HELP)


def _usfm_body(seg: str) -> str:
    lines = [ln for ln in seg.splitlines() if not _USFM_SKIP_LINE.match(ln.lstrip())]
    return _USFM_CHAR_MARK.sub("", " ".join(lines))


def _parse_usfm(text: str, col: _Collector) -> None:
    text = _USFM_FOOTNOTE.sub(" ", text)
    marks = list(_USFM_MARK.finditer(text))
    book = None
    chapter = None
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        seg = text[m.end():end]
        kind = m.group(1)
        if kind == "id":
            code = seg.split()[0].upper() if seg.split() else ""
            book = USFM_CODES.get(code)
            chapter = None
            if book is None and code:
                col.unknown(code)
        elif kind == "c":
            num = re.match(r"\s*(\d+)", seg)
            chapter = int(num.group(1)) if num else None
            if chapter is None:
                col.bad_line("\\c " + seg.strip()[:40])
        else:
            num = _USFM_VERSE_NUM.match(seg)
            if not num:
                col.bad_line("\\v " + seg.strip()[:40])
                continue
            if book is None:
                continue                          # the book code was unknown; already reported
            if chapter is None:
                col.bad_line("\\v " + seg.strip()[:40] + " (no \\c before it)")
                continue
            if num.group(3):
                col.range_verses += 1
            col.add(book, chapter, int(num.group(1)), _usfm_body(seg[num.end():]))


def _osis_ref(oid: str) -> tuple[int, int, int] | None:
    parts = oid.split()[0].split("-")[0].rstrip("!").split(".")
    if len(parts) != 3 or not parts[1].isdigit() or not parts[2].isdigit():
        return None
    book = OSIS_CODES.get(parts[0])
    return None if book is None else (book, int(parts[1]), int(parts[2]))


def _parse_osis(raw: bytes, col: _Collector) -> None:
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise BibleImportError(f"the XML file could not be read: {exc}") from exc
    state = {"ref": None, "oid": "", "parts": []}

    def flush() -> None:
        if state["ref"] is not None:
            book, c, v = state["ref"]
            col.add(book, c, v, "".join(state["parts"]))
        elif state["oid"]:
            col.bad_line("verse osisID " + state["oid"])
        state["ref"] = None
        state["oid"] = ""
        state["parts"] = []

    def start(oid: str) -> None:
        flush()
        ref = _osis_ref(oid)
        if ref is None:
            col.unknown(oid.split(".")[0] or "(blank)")
            state["oid"] = oid
            return
        state["ref"] = ref
        state["oid"] = oid

    def add(s: str | None) -> None:
        if s and state["ref"] is not None:
            state["parts"].append(s)

    def walk(el) -> None:
        local = el.tag.rsplit("}", 1)[-1]
        if local in _OSIS_SKIP:
            return
        if local == "verse" and el.get("osisID"):
            oid = el.get("osisID")
            if el.get("sID") is not None:
                start(oid)
                return
            if el.get("eID") is not None:
                flush()
                return
            start(oid)
            add(el.text)
            for child in el:
                walk(child)
                add(child.tail)
            flush()
            return
        add(el.text)
        for child in el:
            walk(child)
            add(child.tail)

    walk(root)
    flush()



def _local_tag(tag: str) -> str:
    """Element tag with namespace stripped and lower-cased."""
    return tag.rsplit("}", 1)[-1].rsplit(":", 1)[-1].lower()


def _attr_case_insensitive(el, *names: str) -> str | None:
    """First attribute value matching any name, case-insensitively (and namespace-prefix apart)."""
    attrs = {k.rsplit(":", 1)[-1].lower(): v for k, v in el.attrib.items()}
    for n in names:
        v = attrs.get(n.lower())
        if v is not None:
            return v
    return None


def _positive_int(value: str | None) -> int | None:
    """Strict positive integer, or None. Rejects 0, negatives, ranges and non-numeric junk."""
    if value is None:
        return None
    v = value.strip()
    if not re.fullmatch(r"\d+", v):
        return None
    n = int(v)
    return n if n > 0 else None


def _zefania_book_id(el, col: _Collector) -> int | None:
    """Resolve a BIBLEBOOK element to a canonical book id.

    A numeric ``number`` (or ``bnumber``) in 1..66 wins; otherwise the ``bname``
    text is matched against the canonical book names/aliases. Unresolvable books
    are reported once and their verses skipped.
    """
    num = _positive_int(_attr_case_insensitive(el, "number", "bnumber"))
    if num is not None and 1 <= num <= 66:
        return num
    bname = _attr_case_insensitive(el, "bname", "bookname", "name", "bsname")
    if bname and bname.strip():
        book = NAME_INDEX.get(_norm_name(bname))
        if book is not None:
            return book
        col.unknown(bname.strip())
        return None
    if num is not None:
        col.unknown(str(num))
    else:
        col.unknown("(book without number or name)")
    return None


def _zefania_verse_text(el) -> str:
    """Verse text: itertext keeps nested markup (e.g. <christ>/<gram> highlights) inline.

    Metadata-only children are skipped entirely, including their tails' neighbours
    being kept intact.
    """
    parts = []
    if el.text:
        parts.append(el.text)
    for child in el:
        if _local_tag(child.tag) not in _ZEFANIA_SKIP:
            parts.append("".join(child.itertext()))
        if child.tail:
            parts.append(child.tail)
    return "".join(parts)


def _parse_zefania(raw: bytes, col: _Collector) -> str:
    """Parse Zefania XML. Returns the root biblename for metadata only (never stored).

    Strict: the file must be well-formed XML with root <XMLBIBLE>, books must carry
    a number in 1..66 or a recognised name, and every verse needs a positive
    integer cnumber/vnumber. Raises BibleImportError on malformed or incomplete
    files instead of silently returning a partial pack.
    """
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise BibleImportError(f"the XML file could not be read (not well-formed XML): {exc}") from exc
    if _local_tag(root.tag) != "xmlbible":
        raise BibleImportError(
            f"the XML root is <{_local_tag(root.tag)}>, not <XMLBIBLE>. "
            "This file is not a Zefania XML export.")
    biblename = (_attr_case_insensitive(root, "biblename", "name") or "").strip()

    books = [el for el in root.iter() if _local_tag(el.tag) == "biblebook"]
    if not books:
        raise BibleImportError(
            "no <BIBLEBOOK> elements were found. Check that this is a complete "
            "Zefania XML export, not an empty or index file.")
    no_chapter = no_verse = 0
    seen_refs: set[tuple[int, int, int]] = set()
    for book_el in books:
        book_id = _zefania_book_id(book_el, col)
        chapters = [el for el in book_el.iter() if _local_tag(el.tag) == "chapter"]
        if not chapters:
            no_chapter += 1
            continue
        if book_id is None:
            continue                      # already reported as unknown; skip its verses
        for ch_el in chapters:
            chapter = _positive_int(_attr_case_insensitive(ch_el, "cnumber", "number", "c.number"))
            if chapter is None:
                col.bad_line("chapter without a valid cnumber")
                continue
            verses = [el for el in ch_el.iter() if _local_tag(el.tag) == "vers"]
            if not verses:
                no_verse += 1
                continue
            for v_el in verses:
                verse = _positive_int(_attr_case_insensitive(v_el, "vnumber", "number", "v.number"))
                if verse is None:
                    col.bad_line("verse without a valid vnumber")
                    continue
                seen_refs.add((book_id, chapter, verse))
                col.add(book_id, chapter, verse, _zefania_verse_text(v_el))
    if not col.verses:
        detail = (" The file has no verses with text: "
                  + ", ".join(part for part, n in
                              ((f"{no_chapter} book(s) had no chapter", no_chapter),
                               (f"{no_verse} chapter(s) had no verse", no_verse)) if n)
                  + "." if (no_chapter or no_verse) else " It may be an empty or index file.")
        raise BibleImportError(
            "no verses with text were found. Check that it is a complete Zefania XML "
            f"export, not an empty or index file.{detail}")
    if no_chapter:
        col.bad_line(f"{no_chapter} book(s) had no chapter")
    if no_verse:
        col.bad_line(f"{no_verse} chapter(s) had no verse")
    return biblename

def _parse_text(text: str, col: _Collector) -> None:
    for line in text.splitlines():
        if not line.strip():
            continue
        m = _TEXT_LINE.match(line)
        if not m:
            col.bad_line(line)
            continue
        book = NAME_INDEX.get(_norm_name(m.group(1)))
        if book is None:
            col.unknown(m.group(1).strip())
            continue
        body = _TEXT_LEAD.sub("", m.group(4))
        col.add(book, int(m.group(2)), int(m.group(3)), body)


def convert_file(path: Path | str) -> ImportResult:
    """Read, detect and parse a translation file. Raises BibleImportError / UnsupportedFormatError."""
    p = Path(path)
    if not p.is_file():
        raise BibleImportError(f"{p.name} was not found")
    raw = p.read_bytes()
    if raw.startswith(b"%PDF"):
        raise UnsupportedFormatError(f"{p.name} is a PDF file. " + SUPPORTED_FORMATS_HELP)
    text, repl = _decode(raw)
    fmt = detect_format(p, text)
    col = _Collector()
    source_biblename = ""
    if fmt == "usfm":
        _parse_usfm(text, col)
    elif fmt == "osis":
        _parse_osis(raw, col)
    elif fmt == "zefania":
        source_biblename = _parse_zefania(raw, col)
    else:
        _parse_text(text, col)
    if not col.verses:
        raise BibleImportError(
            f"no verses with text were found in {p.name}. Check that it is a complete {FORMAT_LABELS[fmt]} "
            "export, not an empty or index file.")
    return ImportResult(format=fmt, source_name=p.name, verses=col.verses, empty_verses=col.empty_verses,
                        duplicate_verses=col.duplicate_verses, range_verses=col.range_verses,
                        unknown_books=col.unknown_books, unparseable=col.unparseable,
                        unparseable_samples=col.unparseable_samples, decode_replacements=repl,
                        source_biblename=source_biblename)


def installed_ids(folder: Path | str | None = None) -> set:
    d = Path(folder) if folder else DEFAULT_BIBLE_DIR
    return {p.stem.upper() for p in d.glob(f"*{PACK_SUFFIX}")} if d.is_dir() else set()


def write_import(result: ImportResult, *, name: str, code: str, license_text: str,
                 folder: Path | str | None = None, language: str = "en") -> Translation:
    """Store a parsed result as a user-imported pack. Validates the details the dialog collects."""
    code = (code or "").strip()
    name = (name or "").strip()
    license_text = (license_text or "").strip()
    if not ID_RE.match(code):
        raise BibleImportError("short code must be 2-16 letters, digits, '-' or '_' (for example NKJV)")
    if code.upper() in RESERVED_IDS:
        raise BibleImportError(f"{code.upper()} is a bundled translation name; pick another short code")
    if not name:
        raise BibleImportError("translation name cannot be empty")
    if not license_text:
        raise BibleImportError("licence cannot be empty: say who licensed the text and for what use")
    out_dir = Path(folder) if folder else DEFAULT_BIBLE_DIR
    if code.upper() in installed_ids(out_dir):
        raise BibleImportError(f"{code.upper()} is already installed. Remove it in Settings > Bible first.")
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{code}{PACK_SUFFIX}"
    tmp = out_dir / f"{code}.tmp"
    if tmp.exists():
        tmp.unlink()
    meta = {"id": code, "name": name, "language": language or "en", "license": license_text,
            "attribution": "", "version": "1", "user_imported": "1",
            "source_format": result.format, "source_file": result.source_name}
    VerseStore.write_pack(tmp, meta, result.rows())
    tmp.replace(target)
    return Translation(code, name, license_text, str(target), bundled=False, user_imported=True)
