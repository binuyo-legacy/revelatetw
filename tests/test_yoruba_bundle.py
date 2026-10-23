"""Yoruba bundle: registry, 66 books, counts, spot checks, attribution. Headless-safe."""
from pathlib import Path

from revelatetw.bible import BibleLibrary, RESERVED_IDS
from revelatetw.books import BOOKS
from revelatetw.store import VerseStore

BIBLE = Path(__file__).resolve().parents[1] / "data" / "bible"


def test_yoruba_pack_registered_and_bundled():
    lib = BibleLibrary(BIBLE)
    ids = lib.ids()
    assert "Yoruba" in ids
    t = next(t for t in lib.installed() if t.id == "Yoruba")
    assert t.bundled and "CC BY-SA" in t.license
    assert "YORUBA" in RESERVED_IDS


def test_yoruba_counts_and_books():
    store = VerseStore.open(BIBLE / "Yoruba.sqlite")
    assert len(BOOKS) == 66
    assert store.meta.get("id") == "Yoruba"
    assert "Biblica" in store.meta.get("attribution", "")


def test_yoruba_lookup_spot_checks():
    lib = BibleLibrary(BIBLE)
    assert lib.get("Yoruba", 43, 3, 16)            # John 3:16
    assert lib.get("Yoruba", 1, 1, 1)              # Genesis 1:1
    assert lib.get("Yoruba", 19, 23, 1)           # Psalm 23:1
    assert lib.get("Yoruba", 66, 1, 1)             # Revelation 1:1


def test_yoruba_yo_advisory_uses_translation_id_lowercase():
    from revelatetw.model_advice import is_yoruba
    assert is_yoruba("Yoruba") and is_yoruba("yo")
