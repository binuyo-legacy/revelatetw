"""Headless tests for v0.2.0: Bible bundle, translation switch, update check, history, theme sharing."""
import json
import sqlite3
import urllib.error
from pathlib import Path

import pytest

from revelatetw.bible import BibleLibrary, BibleImportError, import_translation
from revelatetw.history import ServiceHistory
from revelatetw.theme import Theme
from revelatetw.theme_io import export_theme, import_theme
from revelatetw.updates import check_for_update, parse_version
from revelatetw.store import APP_VERSION

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "data" / "bible"


def _fixture_books():
    counts = [50, 40, 27, 36, 34, 24, 21, 4, 31, 24, 22, 25, 29, 36, 10, 13, 10, 42, 150, 31, 12, 8,
              66, 52, 5, 48, 12, 14, 3, 9, 1, 4, 7, 3, 3, 3, 2, 14, 4, 28, 16, 24, 21, 28, 16, 16,
              13, 6, 6, 4, 4, 5, 3, 6, 4, 3, 1, 13, 5, 5, 3, 5, 1, 1, 1, 22]
    return counts


def test_bundled_kjv_has_31102_verses_and_john_316():
    db = BUNDLE / "KJV.sqlite"
    if not db.exists():
        pytest.skip("bundle not present in this checkout")
    c = sqlite3.connect(db)
    assert c.execute("select count(*) from verses").fetchone()[0] == 31102
    assert c.execute("select count(distinct book_id) from verses").fetchone()[0] == 66
    text = c.execute("select text from verses where book_id=43 and chapter=3 and verse=16").fetchone()[0]
    assert "God so loved the world" in text


def test_library_lookup_against_bundle():
    lib = BibleLibrary(folder=BUNDLE, sample_json=ROOT / "data" / "sample_kjv.json")
    if not lib.has("KJV"):
        pytest.skip("bundle not present")
    assert "God so loved the world" in lib.get("KJV", 43, 3, 16)
    assert lib.get("KJV", 43, 3, 999) is None
    assert lib.get("NOPE", 43, 3, 16) is None
    assert {t.id for t in lib.installed()} >= {"KJV"}
    lib.close()


def test_fixture_66_books_counts_and_translation_switch(tmp_path):
    """Synthetic 66-book source: one verse per chapter, two translations, switch and fallback."""
    counts = _fixture_books()
    from revelatetw.books import BOOKS
    assert len(counts) == 66 and len(BOOKS) == 66
    src = {"id": "FIX", "name": "Fixture", "language": "en", "license": "Test fixture (synthetic)",
           "verses": []}
    for idx, n in enumerate(counts, start=1):
        for ch in range(1, n + 1):
            src["verses"].append({"book": idx, "chapter": ch, "verse": 1, "text": f"fx {idx}:{ch}:1"})
    jf = tmp_path / "fix.json"
    jf.write_text(json.dumps(src), encoding="utf-8")
    folder = tmp_path / "bible"
    tr = import_translation(jf, folder=folder)
    assert tr.id == "FIX"
    lib = BibleLibrary(folder=folder, sample_json=tmp_path / "none.json")
    assert lib.get("FIX", 66, 22, 1) == "fx 66:22:1"
    # translation switch: missing translation falls back to an installed one
    text, used = lib.get_or_default("MISSING", 1, 1, 1)
    assert used == "FIX" and text == "fx 1:1:1"
    lib.close()


def test_user_import_rejects_bad_files(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("[]", encoding="utf-8")
    with pytest.raises(BibleImportError):
        import_translation(bad, folder=tmp_path / "b")
    with pytest.raises(BibleImportError):
        import_translation(tmp_path / "missing.json", folder=tmp_path / "b")


def test_parse_version():
    assert parse_version("v0.2.0") == (0, 2, 0)
    assert parse_version("0.10.1") > parse_version("0.9.9")


def test_update_available_mocked():
    res = check_for_update(current="0.2.0", fetch=lambda: {"tag_name": "v0.3.0", "html_url": "https://github.com/binuyo-legacy/revelatetw/releases/tag/v0.3.0"})
    assert res.kind == "update" and res.latest == "0.3.0" and "releases" in res.url


def test_up_to_date_mocked():
    res = check_for_update(current="0.2.0", fetch=lambda: {"tag_name": "v0.2.0"})
    assert res.kind == "current"


def test_offline_is_friendly_not_a_crash():
    def boom():
        raise urllib.error.URLError("no network")
    res = check_for_update(current="0.2.0", fetch=boom)
    assert res.kind == "offline" and "internet" in res.message


def test_bad_payload_is_error_not_crash():
    res = check_for_update(current="0.2.0", fetch=lambda: {"tag_name": "nonsense"})
    assert res.kind == "error"


def test_history_round_trip(tmp_path):
    clock = iter([1_700_000_000.0, 1_700_000_060.0])
    h = ServiceHistory(folder=tmp_path, clock=lambda: next(clock))
    h.record("verse", ref="John 3:16 (KJV)", text="For God so loved the world")
    h.record("song", title="Amazing Grace", ref="Verse 2")
    days = h.days()
    assert len(days) == 1
    txt = h.to_text(days[0])
    assert "John 3:16 (KJV)" in txt and "Amazing Grace" in txt
    out = h.export_text(tmp_path / "out.txt", days[0])
    assert out.read_text(encoding="utf-8").startswith("Service history")


def test_history_rejects_unknown_type(tmp_path):
    h = ServiceHistory(folder=tmp_path)
    with pytest.raises(ValueError):
        h.record("bogus", ref="x")


def test_history_skips_corrupt_day(tmp_path):
    (tmp_path / "2026-01-01.json").write_text("{not json", encoding="utf-8")
    h = ServiceHistory(folder=tmp_path)
    assert "nothing projected" in h.to_text("2026-01-01")


def test_theme_export_import_roundtrip(tmp_path):
    t = Theme()
    path = export_theme(t, tmp_path / "design.json")
    back = import_theme(path)
    assert back.to_dict() == t.to_dict()


def test_theme_import_rejects_garbage(tmp_path):
    p = tmp_path / "x.json"
    p.write_text("[1,2]", encoding="utf-8")
    with pytest.raises(ValueError):
        import_theme(p)
