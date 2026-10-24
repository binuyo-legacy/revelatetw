"""Song import dialog: drives the real dialog offscreen (same pattern as the Bible import tests)."""
import json
import pytest
import time

from PyQt6.QtWidgets import QApplication

from revelatetw.song_import_dialog import ImportSongsDialog
from revelatetw.song_io import build_document, export_songs
from revelatetw.songs import Slide, Song, SongLibrary


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


def _wait(app, cond, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.01)
    return False


def _grace(title="Amazing Grace"):
    return Song(title=title, artist="John Newton", slides=[
        Slide("Verse 1", ["Amazing grace", "how sweet the sound"]),
        Slide("Chorus", ["My chains are gone"]),
    ])


def test_dialog_imports_a_pasted_song_then_saves(tmp_path, qapp):
    lib = SongLibrary(tmp_path / "songs")
    dlg = ImportSongsDialog(None, lib)
    dlg.paste.setPlainText("Blessed Assurance\n\nVerse 1\nthis is my story\n\nChorus\nso I sing")
    assert _wait(qapp, lambda: dlg._batch is not None)
    assert dlg.chip.text().endswith("1 song detected")
    assert dlg.title_edit.text() == "Blessed Assurance"
    assert dlg.btn_save.isEnabled()
    dlg._save()
    assert _wait(qapp, lambda: dlg.saved_count == 1)
    assert [s.title for s in lib.load_all()] == ["Blessed Assurance"]
    assert "1 song imported. Available in Songs & sermon." in dlg.result_message


def test_dialog_rtsong_multi_song_and_duplicate_suffix(tmp_path, qapp):
    lib = SongLibrary(tmp_path / "songs")
    lib.save(_grace())
    path = export_songs([_grace(), _grace("Blessed Assurance")], tmp_path / "set.rtsong")
    dlg = ImportSongsDialog(None, lib)
    dlg._load_file(path)
    assert _wait(qapp, lambda: dlg._batch is not None)
    assert dlg.chip.text().endswith("2 songs")
    assert dlg.replace_box.isChecked() is False
    assert "(2)" in dlg.dup_note.text()
    dlg._save()
    assert _wait(qapp, lambda: dlg.saved_count == 2)
    titles = sorted(s.title for s in lib.load_all())
    assert titles == ["Amazing Grace", "Amazing Grace (2)", "Blessed Assurance"]


def test_dialog_replace_checkbox_overwrites(tmp_path, qapp):
    lib = SongLibrary(tmp_path / "songs")
    lib.save(_grace())
    path = export_songs([_grace()], tmp_path / "one.rtsong")
    dlg = ImportSongsDialog(None, lib)
    dlg._load_file(path)
    assert _wait(qapp, lambda: dlg._batch is not None)
    dlg.replace_box.setChecked(True)
    dlg._save()
    assert _wait(qapp, lambda: dlg.saved_count == 1)
    assert len(lib.load_all()) == 1


def test_dialog_shows_error_card_for_bad_file(tmp_path, qapp):
    bad = tmp_path / "bad.rtsong"
    bad.write_text(json.dumps({"format": "rtsong", "version": 9, "songs": []}), encoding="utf-8")
    dlg = ImportSongsDialog(None, SongLibrary(tmp_path / "songs"))
    dlg._load_file(bad)
    assert _wait(qapp, lambda: dlg.error_card.isVisible() or dlg.error_card.text() != "")
    assert "version" in dlg.error_card.text().lower()
    assert not dlg.btn_save.isEnabled()
