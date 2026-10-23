"""Build data/bible/<ID>.sqlite packs from a public-domain source JSON.

Input: scrollmapper-style JSON {"books": [{"name", "chapters": [{"chapter", "verses": [{"verse", "text"}]}]}]}
(books in canonical order). Output: the VerseStore pack format read by revelatetw.bible.
Refuses to write unless there are 66 books with the canonical chapter counts.
Usage: python scripts/build_bible_bundle.py <source.json> <ID> "<Name>" "<license>" "<attribution>"
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from revelatetw.books import BOOKS  # noqa: E402
from revelatetw.store import VerseStore  # noqa: E402

CHAPTER_COUNTS = [50, 40, 27, 36, 34, 24, 21, 4, 31, 24, 22, 25, 29, 36, 10, 13, 10, 42, 150, 31, 12, 8,
                  66, 52, 5, 48, 12, 14, 3, 9, 1, 4, 7, 3, 3, 3, 2, 14, 4, 28, 16, 24, 21, 28, 16, 16,
                  13, 6, 6, 4, 4, 5, 3, 6, 4, 3, 1, 13, 5, 5, 3, 5, 1, 1, 1, 22]


def _group_chapters(details):
    out = {}
    for v in details:
        out.setdefault(int(v["chapter"]), []).append(v)
    return sorted(out.items())


def main(argv):
    src, tid, name, license_text, attribution = argv[1:6]
    normalize_punct = len(argv) > 6 and argv[6] == "--fix-punct"
    data = json.loads(Path(src).read_text(encoding="utf-8-sig"))
    if isinstance(data, list) and data and "details" in data[0]:
        # tayoraph/yoruba-Bible-in-json layout: flat verse rows per book, SWORD-style book_number
        # (10, 20, ... 730). Sort by book_number and use the canonical order from there.
        data = {"books": [{"name": b["bookName"], "chapters": [
            {"chapter": c, "verses": [{"verse": v["verse"], "text": v["text"]}
                                      for v in sorted(vs, key=lambda x: x["verse"])]}
            for c, vs in _group_chapters(b["details"])]}
            for b in sorted(data, key=lambda b: b["details"][0]["book_number"])]}
    books = data["books"] if isinstance(data, dict) else data
    # thiagobodruk layout: chapters are lists of verse strings; normalise to the scrollmapper shape
    books = [{"name": b["name"], "chapters": [
                {"chapter": ci, "verses": [{"verse": vi, "text": t} for vi, t in enumerate(ch, 1)]}
                if isinstance(ch, list) else ch
                for ci, ch in enumerate(b["chapters"], 1)]} for b in books]
    if len(books) != 66 or len(BOOKS) != 66:
        raise SystemExit(f"expected 66 books, got {len(books)}")
    rows, chapters = [], []
    for idx, b in enumerate(books, start=1):
        if len(b["chapters"]) != CHAPTER_COUNTS[idx - 1]:
            raise SystemExit(f"{BOOKS[idx-1].name}: {len(b['chapters'])} chapters, expected {CHAPTER_COUNTS[idx-1]}")
        for ch in b["chapters"]:
            c = int(ch["chapter"])
            chapters.append(c)
            for v in ch["verses"]:
                text = v["text"].strip()
                if normalize_punct:
                    text = re.sub(r" +([,.;:?!])", r"\1", text)   # source puts a space before punctuation
                rows.append((idx, c, int(v["verse"]), text))
    meta = {"id": tid, "name": name, "language": "en", "license": license_text,
            "attribution": attribution, "version": "1"}
    target = ROOT / "data" / "bible" / f"{tid}.sqlite"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()
    VerseStore.write_pack(target, meta, rows)
    print(f"{tid}: 66 books, {len(chapters)} chapters, {len(rows)} verses -> {target} ({target.stat().st_size} bytes)")


if __name__ == "__main__":
    main(sys.argv)
