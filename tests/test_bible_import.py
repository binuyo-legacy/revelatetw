"""Bible import: USFM / OSIS / plain text conversion, registry, persistence, removal, and the dialog."""
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from revelatetw.bible import BibleLibrary, installed_ids, remove_user_translation, verse_count
from revelatetw.bible_import import UnsupportedFormatError, convert_file, write_import

FIX = Path(__file__).resolve().parent / "fixtures" / "bible_import"


@pytest.fixture
def folder():
    return Path(tempfile.mkdtemp())


def _lib(folder):
    return BibleLibrary(folder=folder, sample_json=Path("/nonexistent/sample.json"))


def test_usfm_round_trip_counts_and_lookup():
    r = convert_file(FIX / "sample.usfm")
    assert r.format == "usfm"
    assert r.book_count == 3                      # GEN, JHN, PSA in the fixture
    assert r.chapter_count == 4                   # Gen 1, Gen 2, John 3, Psalm 23
    assert r.verse_count == 7
    assert any("63 book(s) not in the file" in n for n in r.notes)
    assert any("XXX" in n for n in r.notes)      # unknown book code is reported, not silently dropped
    assert any("no text" in n for n in r.notes)  # John 3:18 was empty
    rows = {(b, c, v): t for b, c, v, t in r.rows()}
    assert rows[(1, 1, 1)] == "In the beginning God created the heavens and the earth."
    assert rows[(1, 1, 2)] == "And the earth was without form, and void; and darkness was upon the face of the deep."
    assert rows[(43, 3, 16)].startswith("For God so loved the world")  # \wj markup removed, text kept
    assert "\\" not in " ".join(rows.values())   # no leftover USFM markers
    assert (43, 3, 18) not in rows


def test_osis_xml_round_trip_handles_milestones_and_empty_verses():
    r = convert_file(FIX / "sample.osis.xml")
    assert r.format == "osis"
    assert r.book_count == 2 and r.chapter_count == 2
    assert r.verse_count == 4
    rows = {(b, c, v): t for b, c, v, t in r.rows()}
    assert rows[(1, 1, 1)] == "In the beginning God created the heavens and the earth."  # <note> dropped
    assert rows[(43, 3, 16)] == "For God so loved the world, that he gave his only begotten Son."  # milestone verse
    assert (43, 3, 18) not in rows
    assert any("no text" in n for n in r.notes)


def test_plain_text_lenient_headers_and_unparseable_line_reported():
    r = convert_file(FIX / "sample.txt")
    assert r.format == "text"
    rows = {(b, c, v): t for b, c, v, t in r.rows()}
    assert rows[(62, 1, 9)] == "If we confess our sins, he is faithful."  # "1 John" numbered book
    assert rows[(19, 23, 1)] == "The Lord is my shepherd; I shall not want."  # "Psalm" alias
    assert any("could not be read" in n for n in r.notes)


def test_unsupported_format_raises_plain_error(tmp_path):
    pdf = tmp_path / "book.pdf"
    pdf.write_bytes(b"%PDF-1.4 nothing")
    with pytest.raises(UnsupportedFormatError) as exc:
        convert_file(pdf)
    assert "USFM" in str(exc.value) and "OSIS" in str(exc.value)
    unknown = tmp_path / "data.bin"
    unknown.write_bytes(b"\x00\x01\x02random")
    with pytest.raises(UnsupportedFormatError):
        convert_file(unknown)


def test_import_registry_dropdown_persistence_flag_and_remove(folder):
    r = convert_file(FIX / "sample.usfm")
    t = write_import(r, name="Fixture Text", code="FXT", license_text="Test fixture, for tests only",
                     folder=folder)
    assert t.user_imported is True and t.bundled is False
    assert installed_ids(folder) == {"FXT"}
    assert verse_count(t.path) == 7

    lib = _lib(folder)                             # the registry sees it, marked as user imported
    listed = {x.id: x for x in lib.installed()}
    assert listed["FXT"].user_imported and not listed["FXT"].bundled
    assert lib.get("FXT", 43, 3, 16).startswith("For God so loved")
    assert lib.resolve("FXT") == "FXT"
    lib.close()

    lib2 = _lib(folder)                            # persists: a fresh registry still lists it
    assert "FXT" in {x.id for x in lib2.installed()}
    lib2.close()

    assert remove_user_translation("FXT", folder=folder) is True
    assert "FXT" not in {x.id for x in _lib(folder).installed()}


def test_bundled_ids_are_never_imported_over_or_removed(folder):
    r = convert_file(FIX / "sample.usfm")
    with pytest.raises(Exception):
        write_import(r, name="x", code="KJV", license_text="x", folder=folder)
    assert remove_user_translation("KJV", folder=folder) is False


def test_pack_without_user_imported_marker_cannot_be_removed(folder):
    from revelatetw.store import VerseStore
    VerseStore.write_pack(folder / "HAND.sqlite", {"id": "HAND", "name": "Hand", "license": "x"},
                          [(1, 1, 1, "In the beginning")])
    assert remove_user_translation("HAND", folder=folder) is False
    assert (folder / "HAND.sqlite").is_file()


def test_bundled_packs_still_load_unchanged():
    lib = BibleLibrary()
    ids = {t.id: t for t in lib.installed()}
    assert ids["KJV"].bundled and not ids["KJV"].user_imported
    lib.close()


def _wait(app, cond, seconds=8.0):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.02)
    return False


def test_dialog_import_flow_and_unsupported_card(folder, tmp_path):
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from revelatetw.import_dialog import ImportTranslationDialog

    dlg = ImportTranslationDialog(None, folder=folder)
    dlg._load(FIX / "sample.usfm")
    assert _wait(app, lambda: dlg._result is not None)
    assert dlg.format_card.text() == "Format: USFM \u00b7 3 books \u00b7 7 verses detected"
    assert dlg.btn_import.isEnabled() is False      # no name/code/licence yet
    dlg.name.setText("Fixture Text")
    dlg.code.setText("FXT")
    dlg.licence.setText("Test fixture licence")
    assert dlg.btn_import.isEnabled() is True
    dlg._import()
    assert _wait(app, lambda: dlg.btn_done.isHidden() is False)
    assert dlg.result_message == "FXT imported: 3 books, 7 verses. Available in the translation dropdown."
    assert installed_ids(folder) == {"FXT"}

    bad = ImportTranslationDialog(None, folder=folder)
    pdf = tmp_path / "book.pdf"
    pdf.write_bytes(b"%PDF-1.4 x")
    bad._load(pdf)
    assert _wait(app, lambda: bad.error_card.isHidden() is False)
    assert bad.error_card.text().startswith("Unsupported format")
    assert bad.help_widget.isHidden() is False
    assert bad.btn_import.isEnabled() is False
