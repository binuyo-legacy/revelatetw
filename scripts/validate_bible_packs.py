"""Check every bundled Bible pack in data/bible against the 66-book canon.

Reports per translation: books present, chapters per book vs the canon, verse rows,
blank verse texts, and verse-number gaps inside a chapter. Exit code 1 if any pack is
missing a book, has a wrong chapter count, or has blank verse text.

Usage: python scripts/validate_bible_packs.py [data/bible]
"""
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHAPTER_COUNTS = [50, 40, 27, 36, 34, 24, 21, 4, 31, 24, 22, 25, 29, 36, 10, 13, 10, 42, 150, 31, 12, 8,
                  66, 52, 5, 48, 12, 14, 3, 9, 1, 4, 7, 3, 3, 3, 2, 14, 4, 28, 16, 24, 21, 28, 16, 16,
                  13, 6, 6, 4, 4, 5, 3, 6, 4, 3, 1, 13, 5, 5, 3, 5, 1, 1, 1, 22]
# Reference totals. ASV and WEB omit 16 verses that KJV has (textual omissions such as Mark 7:16),
# so their counts are lower: ASV 31,086, WEB 31,098 (as shipped by their public-domain sources).
EXPECTED_VERSES = {"KJV": 31102, "ASV": 31086, "WEB": 31098}


def check(path: Path) -> tuple[list[str], dict]:
    problems: list[str] = []
    conn = sqlite3.connect(str(path))
    tid = path.stem
    total = conn.execute("SELECT COUNT(*) FROM verses").fetchone()[0]
    blanks = conn.execute("SELECT COUNT(*) FROM verses WHERE TRIM(text) = ''").fetchone()[0]
    chapters: dict[int, dict[int, int]] = defaultdict(dict)
    for book, ch, n in conn.execute("SELECT book_id, chapter, COUNT(*) FROM verses GROUP BY book_id, chapter"):
        chapters[book][ch] = n
    gaps = 0
    for book, ch, mn, mx, n in conn.execute(
            "SELECT book_id, chapter, MIN(verse), MAX(verse), COUNT(*) FROM verses GROUP BY book_id, chapter"):
        if mn != 1 or mx != n:
            gaps += 1
    books_present = len(chapters)
    for idx in range(1, 67):
        if idx not in chapters:
            problems.append(f"book {idx} missing")
            continue
        got, want = len(chapters[idx]), CHAPTER_COUNTS[idx - 1]
        if got != want:
            problems.append(f"book {idx}: {got} chapters, expected {want}")
    if blanks:
        problems.append(f"{blanks} blank verse text(s)")
    if tid in EXPECTED_VERSES and total != EXPECTED_VERSES[tid]:
        problems.append(f"{total} verses, expected {EXPECTED_VERSES[tid]}")
    info = {"books": books_present, "verses": total, "blank": blanks, "numbering_gaps": gaps}
    conn.close()
    return problems, info


def main(argv: list[str]) -> int:
    folder = Path(argv[1]) if len(argv) > 1 else ROOT / "data" / "bible"
    failed = False
    for path in sorted(folder.glob("*.sqlite")):
        problems, info = check(path)
        status = "OK" if not problems else "PROBLEMS"
        print(f"{path.stem:8} {status:9} books={info['books']}/66 verses={info['verses']} "
              f"blank={info['blank']} gaps={info['numbering_gaps']}")
        for p in problems:
            print(f"           - {p}")
        failed = failed or bool(problems)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
