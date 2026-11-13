"""Song export (.rtsong, same file as the main app), song import round trips, and Bible file import in Lite."""
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", ".."))
from revelatelite import songs as S
from revelatelite import bibleconvert as BC
from revelatelite.bible import BibleStore
try:                                                    # the main app's own reader (needs Python 3.9+; Lite runs on 3.8)
    from revelatetw import song_io as main_io
except TypeError:
    main_io = None
try:
    from PyQt5 import QtWidgets
    from revelatelite import app as lite_app
    from revelatelite.bibleimport import ImportBibleDialog
except ImportError:  # pragma: no cover
    QtWidgets = None

FIX = os.path.join(HERE, "..", "..", "tests", "fixtures", "bible_import")
BUNDLED = os.path.join(HERE, "..", "..", "data", "bible")
LYR = "[Verse 1]\nAmazing grace\nHow sweet the sound\n\nChorus:\nMy chains are gone\nI've been set free\n"


def mk(title="Amazing Grace", artist="Newton"):
    return S.Song(title, artist, S.split_lyrics(LYR))


class SongExport(unittest.TestCase):
    def test_schema_matches_main_app(self):
        d = tempfile.mkdtemp()
        out = S.export_songs([mk(), mk("No Artist", "")], os.path.join(d, "x"))
        self.assertTrue(out.endswith(".rtsong"))             # extension added
        doc = json.load(open(out, encoding="utf-8"))
        self.assertEqual((doc["format"], doc["version"]), ("rtsong", 1))
        self.assertEqual(doc["songs"][0]["author"], "Newton")
        self.assertNotIn("author", doc["songs"][1])           # optional, omitted when empty
        self.assertEqual(doc["songs"][0]["sections"][0], {"label": "Verse 1", "lines": ["Amazing grace", "How sweet the sound"]})
        self.assertFalse(os.path.exists(out + ".tmp"))

    @unittest.skipIf(main_io is None, "main app song_io needs Python 3.9+")
    def test_identical_to_main_app_document(self):
        lite = S.build_document([mk()])
        heavy_song = main_io.parse_rtsong(json.dumps(lite))[0]
        self.assertEqual(main_io.build_document([heavy_song]), lite)   # byte-for-byte same structure

    @unittest.skipIf(main_io is None, "main app song_io needs Python 3.9+")
    def test_main_app_can_read_lite_export_and_back(self):
        d = tempfile.mkdtemp()
        out = S.export_songs([mk()], os.path.join(d, "a.rtsong"))
        heavy = main_io.parse_rtsong(open(out, encoding="utf-8").read())
        self.assertEqual(heavy[0].title, "Amazing Grace")
        self.assertEqual(heavy[0].artist, "Newton")
        # and a file written by the main app opens in Lite
        out2 = str(main_io.export_songs(heavy, os.path.join(d, "b.rtsong")))
        back = S.import_rtsong(open(out2, encoding="utf-8").read())
        self.assertEqual(back[0].slides, mk().slides)

    def test_round_trip_keeps_unicode(self):
        d = tempfile.mkdtemp()
        sg = S.Song("Ọlọ́run mi", "Ayọ̀", [{"label": "Verse 1", "lines": ["Ẹ yìn Olúwa", "ṣé"]}])
        out = S.export_songs([sg], os.path.join(d, "y.rtsong"))
        self.assertIn("Ẹ yìn Olúwa", open(out, encoding="utf-8").read())   # not \\u escaped
        back = S.import_rtsong(open(out, encoding="utf-8").read())[0]
        self.assertEqual((back.title, back.artist, back.slides), (sg.title, sg.artist, sg.slides))

    def test_refuses_empty_and_slideless(self):
        d = tempfile.mkdtemp()
        with self.assertRaises(ValueError):
            S.export_songs([], os.path.join(d, "e.rtsong"))
        with self.assertRaises(ValueError):
            S.export_songs([S.Song("Blank")], os.path.join(d, "e.rtsong"))
        self.assertEqual(os.listdir(d), [])                   # nothing half written

    def test_safe_filename(self):
        self.assertEqual(S.safe_filename('A/B:C*?"<>|'), "A B C")
        self.assertEqual(S.safe_filename("..."), "song")
        self.assertEqual(S.safe_filename(""), "song")

    def test_import_single_song_json_gets_fresh_id(self):
        sg = mk()
        out = S.import_song_json(json.dumps(sg.to_dict()))
        self.assertEqual(out[0].title, "Amazing Grace")
        self.assertNotEqual(out[0].id, sg.id)
        for bad in ("nope", json.dumps({"format": "x"})):
            with self.assertRaises(ValueError):
                S.import_song_json(bad)

    def test_import_rtsong_skips_blank_lines_and_defaults_labels(self):
        doc = {"format": "rtsong", "version": 1, "songs": [
            {"title": "T", "sections": [{"lines": ["a", "  ", "b"]}, {"label": "Empty", "lines": []}]}]}
        sg = S.import_rtsong(json.dumps(doc))[0]
        self.assertEqual(sg.slides, [{"label": "Slide 1", "lines": ["a", "b"]}])
        with self.assertRaises(ValueError):
            S.import_rtsong(json.dumps({"format": "rtsong", "version": 1, "songs": [{"title": "T", "sections": []}]}))
        with self.assertRaises(ValueError):
            S.import_rtsong(json.dumps({"format": "rtsong", "version": 1, "songs": [{"title": " "}]}))

    def test_import_accepts_bom(self):
        text = "\ufeff" + json.dumps(S.build_document([mk()]))
        self.assertEqual(len(S.import_rtsong(text)), 1)


class BibleConvert(unittest.TestCase):
    def test_convert_each_format_and_save(self):
        for name, fmt in (("sample.usfm", "usfm"), ("sample.osis.xml", "osis"), ("sample.txt", "text")):
            r = BC.convert(os.path.join(FIX, name))
            self.assertEqual(r.format, fmt, name)
            self.assertGreater(r.verse_count, 0)
        r = BC.convert(os.path.join(FIX, "sample.usfm"))
        folder = os.path.join(tempfile.mkdtemp(), "bibles")   # not created yet: save makes it
        code = BC.save(r, "Test Bible", "TST", "Licensed for church use", folder)
        self.assertEqual(code, "TST")
        db = sqlite3.connect(os.path.join(folder, "TST.sqlite"))
        self.assertEqual(db.execute("SELECT count(*) FROM verses").fetchone()[0], r.verse_count)
        meta = dict(db.execute("SELECT key,value FROM meta"))
        self.assertEqual((meta["user_imported"], meta["license"]), ("1", "Licensed for church use"))
        db.close()

    def test_bad_inputs_have_plain_errors_and_save_nothing(self):
        d = tempfile.mkdtemp()
        with self.assertRaises(BC.BibleImportError):
            BC.convert(os.path.join(d, "missing.usfm"))
        pdf = os.path.join(d, "b.pdf")
        open(pdf, "wb").write(b"%PDF-1.4 junk")
        with self.assertRaises(BC.BibleImportError):
            BC.convert(pdf)
        empty = os.path.join(d, "e.txt")
        open(empty, "w").write("hello world, no verses here\n")
        with self.assertRaises(BC.BibleImportError):
            BC.convert(empty)
        r = BC.convert(os.path.join(FIX, "sample.usfm"))
        folder = os.path.join(d, "bibles")
        for code, lic, name in (("KJV", "x", "n"), ("kjv", "x", "n"), ("a", "x", "n"), ("T 1", "x", "n"),
                                ("OKK", "", "n"), ("OKK", "x", "")):
            with self.assertRaises(BC.BibleImportError):
                BC.save(r, name, code, lic, folder)
        with self.assertRaises(BC.BibleImportError):
            BC.save(r, "n", "TAKEN", "x", folder, taken=["taken"])   # case-insensitive clash
        self.assertFalse(os.path.exists(folder) and os.listdir(folder))

    def test_size_guard(self):
        old = BC.MAX_FILE_MB
        BC.MAX_FILE_MB = 0
        try:
            with self.assertRaises(BC.BibleImportError):
                BC.convert(os.path.join(FIX, "sample.usfm"))
        finally:
            BC.MAX_FILE_MB = old

    def test_duplicate_code_refused_on_second_save(self):
        r = BC.convert(os.path.join(FIX, "sample.txt"))
        folder = tempfile.mkdtemp()
        BC.save(r, "One", "ONE", "lic", folder)
        with self.assertRaises(BC.BibleImportError):
            BC.save(r, "One", "ONE", "lic", folder)


class StoreSeesImports(unittest.TestCase):
    def make_store(self):
        user = tempfile.mkdtemp()
        r = BC.convert(os.path.join(FIX, "sample.usfm"))
        BC.save(r, "Test Bible", "TST", "Licensed", user)
        return BibleStore(BUNDLED, user), user

    def test_imported_pack_is_listed_and_readable(self):
        st, _ = self.make_store()
        self.assertIn("TST", st.translations())
        self.assertIn("KJV", st.translations())
        self.assertIn("For God so loved the world", st.passage("TST", 43, 3, 16, 16))
        self.assertTrue(st.search("TST", "loved world"))
        st.close()

    def test_missing_user_folder_is_fine(self):
        st = BibleStore(BUNDLED, os.path.join(tempfile.mkdtemp(), "nope"))
        self.assertIn("KJV", st.translations())
        st.close()

    def test_remove_only_imported(self):
        st, user = self.make_store()
        self.assertTrue(st.is_user_imported("TST"))
        self.assertFalse(st.is_user_imported("KJV"))
        self.assertFalse(BC.remove("KJV", st))
        self.assertTrue(os.path.isfile(os.path.join(BUNDLED, "KJV.sqlite")))
        self.assertTrue(BC.remove("TST", st))
        self.assertNotIn("TST", st.translations())
        self.assertFalse(BC.remove("TST", st))
        st.close()

    def test_bundled_wins_name_clash(self):
        user = tempfile.mkdtemp()
        shutil.copy(os.path.join(BUNDLED, "WEB.sqlite"), os.path.join(user, "KJV.sqlite"))
        st = BibleStore(BUNDLED, user)
        self.assertEqual(st.translations().count("KJV"), 1)
        self.assertFalse(st.is_user_imported("KJV"))
        st.close()


@unittest.skipIf(QtWidgets is None, "PyQt5 not installed")
class InApp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qa = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        cls.qa.setStyleSheet(lite_app.QSS)

    def make(self, with_song=True):
        d = tempfile.mkdtemp()
        lite_app.paths.user_dir = lambda: d
        if with_song:
            S.SongLibrary(os.path.join(d, "songs")).save(mk())
        return lite_app.Main(), d

    def test_export_button_flow_and_projection_untouched(self):
        w, d = self.make()
        self.assertFalse(w.song_exp_b.isEnabled())            # nothing selected yet
        self.assertTrue(w.song_expall_b.isEnabled())
        w.song_list.setCurrentRow(0)
        w.pick_song(0)
        self.assertTrue(w.song_exp_b.isEnabled())
        ref = w.preview.ref
        out = os.path.join(d, "out.rtsong")
        self.assertEqual(w.export_song_file(out, [w.song]), 1)
        self.assertIn("Exported 1 song", w.status.text())
        self.assertEqual(w.preview.ref, ref)                   # export never changes the preview
        self.assertFalse(w.proj.isVisible())                   # and never projects
        self.assertEqual(S.import_rtsong(open(out, encoding="utf-8").read())[0].title, "Amazing Grace")
        w.close()

    def test_export_failure_is_reported(self):
        w, d = self.make()
        self.assertEqual(w.export_song_file(os.path.join(d, "x.rtsong"), []), 0)
        self.assertIn("Could not export", w.status.text())
        w.close()

    def test_full_import_flow_export_then_import_in_app(self):
        w, d = self.make()
        out = os.path.join(d, "all.rtsong")
        self.assertEqual(w.export_song_file(out, w.song_all), 1)
        self.assertEqual(w.import_song_file(out), 1)           # same title -> kept as "(2)", original untouched
        self.assertEqual(sorted(x.title for x in w.song_all), ["Amazing Grace", "Amazing Grace (2)"])
        self.assertFalse(w.proj.isVisible())
        w.close()

    def test_import_single_song_json_in_app(self):
        w, d = self.make(with_song=False)
        p = os.path.join(d, "one.json")
        open(p, "w", encoding="utf-8").write(json.dumps(mk().to_dict()))
        self.assertEqual(w.import_song_file(p), 1)
        self.assertEqual(w.song_list.count(), 1)
        w.close()

    def test_bible_dialog_and_new_translation_in_list(self):
        w, d = self.make(with_song=False)
        user = os.path.join(d, "bibles")
        w.bible._user_directory = user
        dlg = ImportBibleDialog(w, user, w.bible.translations())
        self.assertFalse(dlg.save_b.isEnabled())
        self.assertFalse(dlg.load(os.path.join(d, "missing.usfm")))
        self.assertIn("Could not read", dlg.msg.text())
        self.assertTrue(dlg.load(os.path.join(FIX, "sample.usfm")))
        self.assertIn("John 3:16", dlg.report.toPlainText())
        self.assertTrue(dlg.save_b.isEnabled())
        dlg.name_e.setText("Test Bible")
        dlg.code_e.setText("KJV")                              # clash with bundled
        dlg.lic_e.setText("Licensed")
        self.assertFalse(dlg.save())
        self.assertIn("already installed", dlg.msg.text())
        dlg.code_e.setText("TST")
        self.assertTrue(dlg.save())
        self.assertEqual(dlg.imported_code, "TST")
        before = w.preview.ref
        w.refresh_translations("TST")
        self.assertIn("TST", [w.trans.itemText(i) for i in range(w.trans.count())])
        self.assertEqual(w.preview.ref, before)                # list refresh never changes the preview
        self.assertFalse(w.proj.isVisible())
        w.trans.setCurrentText("TST")
        w.lookup("John 3:16")
        self.assertIn("John 3:16", w.preview.ref)
        self.assertIn("For God so loved", w.preview.body)
        w.close()


if __name__ == "__main__":
    unittest.main()
