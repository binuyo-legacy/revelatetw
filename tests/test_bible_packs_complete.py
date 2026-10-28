"""The bundled Bible packs are complete, and the app loads them instead of the 9-verse sample."""
import os
import sqlite3
import subprocess
import sys

from revelatetw.__main__ import build, load_store

ROOT = os.path.join(os.path.dirname(__file__), "..")
PACKS = os.path.join(ROOT, "data", "bible")


def test_verses_tab_source_is_full_kjv_pack_not_sample():
    store = load_store("data/sample_kjv.json")
    assert store.translation_id == "KJV"
    total = sum(1 for _ in store.items())
    assert total == 31102


def test_build_uses_full_pack_for_detection_too():
    store, _, pipeline = build("data/sample_kjv.json", log_path=None)
    assert sum(1 for _ in store.items()) == 31102


def test_bundled_packs_validate():
    out = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "validate_bible_packs.py")],
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stdout + out.stderr


def test_asv_has_no_blank_verse_rows():
    conn = sqlite3.connect(os.path.join(PACKS, "ASV.sqlite"))
    assert conn.execute("SELECT COUNT(*) FROM verses WHERE TRIM(text) = ''").fetchone()[0] == 0
    conn.close()


def test_menu_store_follows_selected_translation(tmp_path, monkeypatch):
    """Chapter/verse menus must read the chosen translation's pack, not always KJV."""
    from revelatetw.bible import BibleLibrary
    from revelatetw.store import VerseStore
    from revelatetw.ui import OperatorWindow as MainWindow

    # A tiny Yoruba-only pack: John 1 has 2 verses, no KJV-only chapters.
    folder = tmp_path / "bible"
    folder.mkdir()
    VerseStore.write_pack(folder / "Yoruba.sqlite", {"id": "Yoruba", "name": "Yoruba", "language": "yo",
                                                    "license": "x"},
                          [(43, 1, 1, "Ninu ibere..."), (43, 1, 2, "Ohun gbogbo...")])
    fake = MainWindow.__new__(MainWindow)
    fake._bible = BibleLibrary(folder=folder, sample_json=tmp_path / "none.json")
    fake._store = None

    class S:
        bible_translation = "Yoruba"
    fake.settings = S()
    store = MainWindow._menu_store(fake)
    assert store is not None and store.translation_id == "Yoruba"
    assert store.verse_numbers(43, 1) == [1, 2]
