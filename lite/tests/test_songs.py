"""Songs and lyrics in Lite: model, library, import, and the single shared preview."""
import json
import os
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from revelatelite import songs as S
try:
    from PyQt5 import QtWidgets
    from revelatelite import app as lite_app
except ImportError:  # pragma: no cover
    QtWidgets = None

LYR = "[Verse 1]\nAmazing grace\nHow sweet the sound\n\nChorus:\nMy chains are gone\nI've been set free\n"


class Model(unittest.TestCase):
    def test_split_labels_and_blank_lines(self):
        sl = S.split_lyrics(LYR)
        self.assertEqual([x["label"] for x in sl], ["Verse 1", "Chorus"])
        self.assertEqual(sl[0]["lines"], ["Amazing grace", "How sweet the sound"])

    def test_long_block_is_cut_and_marked_cont(self):
        sl = S.split_lyrics("[Verse]\n" + "\n".join("l%d" % i for i in range(6)), 4)
        self.assertEqual([x["label"] for x in sl], ["Verse", "Verse (cont.)"])
        self.assertEqual(len(sl[1]["lines"]), 2)

    def test_lone_lowercase_c_is_lyric_but_capital_is_header(self):
        self.assertEqual(S.split_lyrics("c\nhello")[0]["lines"], ["c", "hello"])
        self.assertEqual(S.split_lyrics("C\nhello")[0]["label"], "Chorus")

    def test_round_trip_keeps_labels(self):
        sl = S.split_lyrics(LYR)
        self.assertEqual(S.split_lyrics(S.lyrics_text(sl)), sl)

    def test_song_needs_title_and_library_roundtrip(self):
        with self.assertRaises(ValueError):
            S.Song("  ")
        d = tempfile.mkdtemp()
        lib = S.SongLibrary(d)
        sg = S.Song("Amazing Grace", "Newton", S.split_lyrics(LYR))
        lib.save(sg)
        open(os.path.join(d, "bad.json"), "w").write("{not json")
        got = lib.load_all()
        self.assertEqual([x.title for x in got], ["Amazing Grace"])
        self.assertEqual(got[0].slides, sg.slides)
        self.assertEqual(len(S.SongLibrary.search(got, "chains FREE")), 1)
        self.assertEqual(S.SongLibrary.search(got, "zebra"), [])
        self.assertTrue(lib.delete(sg.id))
        self.assertFalse(lib.delete("../x"))
        with self.assertRaises(ValueError):
            lib.save(S.Song("Empty"))

    def test_import_rtsong(self):
        doc = {"format": "rtsong", "version": 1, "songs": [
            {"title": "A", "author": "B", "sections": [{"label": "Verse 1", "lines": ["x", "y"]}]}]}
        out = S.import_rtsong(json.dumps(doc))
        self.assertEqual((out[0].title, out[0].artist, out[0].slides[0]["lines"]), ("A", "B", ["x", "y"]))
        for bad in ("nope", json.dumps({"format": "other"}), json.dumps(dict(doc, version=2)),
                    json.dumps(dict(doc, songs=[]))):
            with self.assertRaises(ValueError):
                S.import_rtsong(bad)


@unittest.skipIf(QtWidgets is None, "PyQt5 not installed")
class Shared(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qa = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        cls.qa.setStyleSheet(lite_app.QSS)

    def make(self):
        d = tempfile.mkdtemp()
        lite_app.paths.user_dir = lambda: d
        lib = S.SongLibrary(os.path.join(d, "songs"))
        lib.save(S.Song("Amazing Grace", "Newton", S.split_lyrics(LYR)))
        w = lite_app.Main()
        w.st["transition_ms"] = 0      # these tests are about content, so screen changes are instant (see test_transitions.py)
        return w

    def test_songs_listed_and_slide_goes_to_the_same_preview(self):
        w = self.make()
        self.assertEqual(w.song_list.count(), 1)
        w.lookup("Rom 8:28")
        verse_preview = w.preview
        w.song_list.setCurrentRow(0)
        w.pick_song(0)
        self.assertIs(w.preview, verse_preview)           # one preview widget for everything
        self.assertIn("Amazing Grace - Verse 1", w.preview.ref)
        self.assertIn("How sweet the sound", w.preview.body)
        self.assertTrue(w.project_b.isEnabled())
        self.assertFalse(w.proj.isVisible())               # choosing a slide never projects
        w.slide_list.setCurrentRow(1)
        self.assertIn("Chorus", w.preview.ref)
        w.lookup("John 3:16")                              # back to a verse: same preview
        self.assertIn("John 3:16", w.preview.ref)
        w.close()

    def test_project_sends_song_slide_and_edits_stay_local(self):
        w = self.make()
        w.pick_song(0)
        w.project()
        self.assertTrue(w.proj.isVisible())
        self.assertIn("Verse 1", w.proj.ref)
        w.step(1)                                          # next slide: preview only
        self.assertIn("Chorus", w.preview.ref)
        self.assertIn("Verse 1", w.proj.ref)
        self.assertIn("not sent", w.live_badge.text())
        w.project()
        self.assertIn("Chorus", w.proj.ref)
        self.assertEqual(w.live_badge.text(), "LIVE")
        w.project_off()
        self.assertFalse(w.proj.isVisible())
        self.assertIn("Chorus", w.preview.ref)             # state kept
        self.assertEqual(w.song_list.count(), 1)
        w.close()

    def test_step_at_ends_and_translation_change_keep_song_slide(self):
        w = self.make()
        w.pick_song(0)
        w.step(-1)
        self.assertIn("first slide", w.status.text())
        w.step(1)
        w.step(1)
        self.assertIn("last slide", w.status.text())
        before = w.preview.ref
        if w.trans.count() > 1:
            w.trans.setCurrentIndex(1)
        self.assertEqual(w.preview.ref, before)
        w.close()

    def test_import_text_file_and_duplicate_titles(self):
        w = self.make()
        p = os.path.join(tempfile.mkdtemp(), "Amazing Grace.txt")
        open(p, "w", encoding="utf-8").write("[Verse 1]\nline a\nline b\n")
        self.assertEqual(w.import_song_file(p), 1)
        self.assertEqual(sorted(x.title for x in w.song_all), ["Amazing Grace", "Amazing Grace (2)"])
        bad = os.path.join(tempfile.mkdtemp(), "x.rtsong")
        open(bad, "w").write("junk")
        self.assertEqual(w.import_song_file(bad), 0)
        self.assertIn("Could not import", w.status.text())
        w.close()

    def test_search_filters_and_delete_keeps_preview(self):
        w = self.make()
        w.pick_song(0)
        ref = w.preview.ref
        w.song_search.setText("zebra")
        self.assertEqual(w.song_list.count(), 0)
        w.song_search.setText("chains")
        self.assertEqual(w.song_list.count(), 1)
        self.assertEqual(w.preview.ref, ref)               # searching never changes the preview
        w.close()

    def test_project_still_disabled_with_nothing_shown(self):
        w = self.make()
        w.lookup("Nope 9:9")
        self.assertFalse(w.project_b.isEnabled())
        w.close()


if __name__ == "__main__":
    unittest.main()
