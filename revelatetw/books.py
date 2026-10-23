"""Canonical Bible books (Protestant canon, 66 books) with English aliases.

Translation packs add aliases for Yoruba, Hausa, Igbo and Swahili through
BookIndex.add_aliases(), sourced from pack metadata (spec F1 / F6).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Book:
    book_id: int  # canonical order, 1 (Genesis) to 66 (Revelation)
    name: str
    aliases: tuple[str, ...] = ()


_RAW: list[tuple[str, str]] = [
    ("Genesis", "gen, gn"), ("Exodus", "exod, exo"), ("Leviticus", "lev, lv"),
    ("Numbers", "num, nm"), ("Deuteronomy", "deut, dt"), ("Joshua", "josh, jos"),
    ("Judges", "judg, jdg"), ("Ruth", ""), ("1 Samuel", "1 sam, 1sam"),
    ("2 Samuel", "2 sam, 2sam"), ("1 Kings", "1 kgs, 1 ki"), ("2 Kings", "2 kgs, 2 ki"),
    ("1 Chronicles", "1 chron, 1 chr"), ("2 Chronicles", "2 chron, 2 chr"),
    ("Ezra", ""), ("Nehemiah", "neh"), ("Esther", "esth, est"), ("Job", ""),
    ("Psalms", "psalm, psa, ps, pslm"), ("Proverbs", "prov, prv, pr"),
    ("Ecclesiastes", "eccl, ecc"), ("Song of Solomon", "song of songs, song, sos"),
    ("Isaiah", "isa"), ("Jeremiah", "jer"), ("Lamentations", "lam"), ("Ezekiel", "ezek, eze"),
    ("Daniel", "dan, dn"), ("Hosea", "hos"), ("Joel", ""), ("Amos", ""),
    ("Obadiah", "obad, oba"), ("Jonah", "jon"), ("Micah", "mic"), ("Nahum", "nah"),
    ("Habakkuk", "hab"), ("Zephaniah", "zeph, zep"), ("Haggai", "hag"),
    ("Zechariah", "zech, zec"), ("Malachi", "mal"), ("Matthew", "matt, mt"),
    ("Mark", "mk, mrk"), ("Luke", "lk"), ("John", "jn, jhn"), ("Acts", "act"),
    ("Romans", "rom, rm"), ("1 Corinthians", "1 cor, 1cor"), ("2 Corinthians", "2 cor, 2cor"),
    ("Galatians", "gal"), ("Ephesians", "eph"), ("Philippians", "phil, php"),
    ("Colossians", "col"), ("1 Thessalonians", "1 thess, 1 thes"),
    ("2 Thessalonians", "2 thess, 2 thes"), ("1 Timothy", "1 tim, 1tim"),
    ("2 Timothy", "2 tim, 2tim"), ("Titus", "tit"), ("Philemon", "philem, phm"),
    ("Hebrews", "heb"), ("James", "jas, jm"), ("1 Peter", "1 pet, 1pet"),
    ("2 Peter", "2 pet, 2pet"), ("1 John", "1 jn, 1jn, 1 jhn"), ("2 John", "2 jn, 2jn"),
    ("3 John", "3 jn, 3jn"), ("Jude", "jud"),
    ("Revelation", "rev, revelations"),
]

BOOKS: tuple[Book, ...] = tuple(
    Book(i + 1, name, tuple(a.strip() for a in aliases.split(",") if a.strip()))
    for i, (name, aliases) in enumerate(_RAW)
)
assert len(BOOKS) == 66, "canon must have 66 books"
BOOK_BY_ID: dict[int, Book] = {b.book_id: b for b in BOOKS}
BOOK_BY_NAME: dict[str, int] = {b.name.lower(): b.book_id for b in BOOKS}
