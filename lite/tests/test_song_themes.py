"""Tests for the song slide templates. Headless (offscreen Qt); not a Windows 8.1 hardware check.
Run: python -m pytest lite/tests/test_song_themes.py"""
import json
import os
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from PyQt5 import QtCore, QtGui, QtWidgets
from revelatelite import app as lite_app, paths, settings, songthemes as T
from revelatelite.projection import SlideView
from revelatelite.songs import Song


_QA = []


def qapp():
    qa = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    _QA[:] = [qa]       # keep a reference so Qt is not torn down between tests
    qa.setStyleSheet(lite_app.QSS)
    return qa


def render(theme, meta=T.SAMPLE_META, body=T.SAMPLE_BODY, size=(640, 360)):
    v = SlideView()
    v.set_style("navy", 100, True, "Georgia", False, "", "", None, False, "", 3, theme)
    v.set_content("ref", body, "", meta)
    return v.snapshot(QtCore.QSize(*size)).toImage()


def same(a, b):
    return a.size() == b.size() and a.constBits().asstring(a.byteCount()) == b.constBits().asstring(b.byteCount())


class Templates(unittest.TestCase):
    def setUp(self):
        qapp()

    def test_five_named_templates_plus_standard(self):
        self.assertEqual(len(T.TEMPLATES), 5)
        self.assertEqual(T.KEYS[0], "standard")
        self.assertEqual(len({t["name"] for t in T.TEMPLATES.values()}), 5)
        self.assertEqual(len({t["blurb"] for t in T.TEMPLATES.values()}), 5)

    def test_all_templates_render_distinct(self):
        imgs = {k: render(k) for k in T.KEYS}
        keys = list(imgs)
        for i in range(len(keys)):
            for j in range(i + 1, len(keys)):
                self.assertFalse(same(imgs[keys[i]], imgs[keys[j]]), (keys[i], keys[j]))

    def test_verses_ignore_song_template(self):
        verse = {k: render(k, meta=None) for k in T.KEYS}
        for k in T.KEYS:
            self.assertTrue(same(verse[k], verse["standard"]), k)

    def test_template_looks_different_from_standard(self):
        for k in T.TEMPLATES:
            self.assertFalse(same(render(k), render("standard")), k)

    def test_unknown_key_cleans_to_standard(self):
        self.assertEqual(T.clean("nope"), "standard")
        self.assertEqual(T.clean(5), "standard")

    def test_meta_and_pill(self):
        s = Song("Way Maker", "Sinach", [{"label": "Verse", "lines": ["a"]}, {"label": "Chorus", "lines": ["b"]}])
        m = T.meta_for(s, 1)
        self.assertEqual(m, ("Way Maker", "Sinach", "Chorus", 2, 2))
        self.assertIn("Chorus", T.pill_text(m))
        self.assertIn("2/2", T.pill_text(m))

    def test_long_text_and_missing_artist_do_not_crash(self):
        body = "\n".join("this is a very long lyric line number %d that wraps around" % i for i in range(6))
        for k in T.TEMPLATES:
            for meta in (("A" * 80, "", "Verse 1", 1, 1), T.SAMPLE_META):
                render(k, meta=meta, body=body, size=(320, 180))
                render(k, meta=meta, body="One line", size=(1280, 720))

    def test_blank_stays_black(self):
        v = SlideView()
        v.set_style("navy", 100, True, "Georgia", False, "", "", None, False, "", 3, "royal")
        v.set_content("r", T.SAMPLE_BODY, "", T.SAMPLE_META)
        v.blank()
        img = v.snapshot(QtCore.QSize(100, 60)).toImage()
        self.assertEqual(img.pixel(50, 30) & 0xffffff, 0)

    def test_outline_still_works_on_song_template(self):
        v = SlideView()
        v.set_style("navy", 100, True, "Georgia", False, "", "", None, True, "#ff0000", 6, "midnight")
        v.set_content("r", T.SAMPLE_BODY, "", T.SAMPLE_META)
        self.assertFalse(same(v.snapshot(QtCore.QSize(640, 360)).toImage(), render("midnight")))


class Persist(unittest.TestCase):
    def test_default_and_persist(self):
        self.assertEqual(settings.DEFAULTS["song_theme"], "standard")
        p = os.path.join(tempfile.mkdtemp(), "s.json")
        data = settings.load(p)
        data["song_theme"] = "royal"
        settings.save(p, data)
        self.assertEqual(settings.load(p)["song_theme"], "royal")

    def test_bad_value_falls_back(self):
        p = os.path.join(tempfile.mkdtemp(), "s.json")
        json.dump({"song_theme": "bogus"}, open(p, "w"))
        self.assertEqual(settings.load(p)["song_theme"], "standard")
        json.dump({"song_theme": 7}, open(p, "w"))
        self.assertEqual(settings.load(p)["song_theme"], "standard")


class AppFlow(unittest.TestCase):
    def setUp(self):
        qapp()
        d = tempfile.mkdtemp()
        self._old = paths.user_dir
        paths.user_dir = lambda: d
        lite_app.paths.user_dir = lambda: d
        self.w = lite_app.Main()
        self.w.st["transition_onoff"] = self.w.st["transition_switch"] = False

    def tearDown(self):
        self.w.proj.hide()
        paths.user_dir = self._old
        lite_app.paths.user_dir = self._old

    def _song(self):
        w = self.w
        s = Song("Way Maker", "Sinach", [{"label": "Verse", "lines": ["one", "two"]}, {"label": "Chorus", "lines": ["three", "four"]}])
        w.songs.save(s)
        w.song_all = w.songs.load_all()
        w.refresh_songs()
        w.song_list.setCurrentRow(0)
        w.pick_slide(1)

    def test_gallery_has_six_rows_with_icons(self):
        lw = self.w.song_theme_lw
        self.assertEqual(lw.count(), 6)
        self.assertFalse(lw.item(1).icon().isNull())

    def test_choosing_template_changes_preview_not_screen(self):
        w = self.w
        self._song()
        self.assertFalse(w.proj.isVisible())
        self.assertEqual(w.preview.meta[2], "Chorus")
        before = w.preview.snapshot(QtCore.QSize(320, 180)).toImage()
        w.song_theme_lw.setCurrentRow(T.KEYS.index("royal"))
        self.assertEqual(w.st["song_theme"], "royal")
        self.assertEqual(w.preview.song_theme, "royal")
        self.assertFalse(same(before, w.preview.snapshot(QtCore.QSize(320, 180)).toImage()))
        self.assertFalse(w.proj.isVisible())

    def test_live_screen_keeps_look_until_project(self):
        w = self.w
        self._song()
        w.project()
        self.assertEqual(w.proj.song_theme, "standard")
        w.song_theme_lw.setCurrentRow(T.KEYS.index("sunrise"))
        self.assertEqual(w.proj.song_theme, "standard")
        self.assertEqual(w.preview.song_theme, "sunrise")
        w.project()
        self.assertEqual(w.proj.song_theme, "sunrise")
        self.assertEqual(w.proj.meta[2], "Chorus")

    def test_verse_has_no_song_look(self):
        w = self.w
        self._song()
        w.song_theme_lw.setCurrentRow(T.KEYS.index("light"))
        w._set_slide(("John 3:16 (KJV)", "For God so loved", "KJV"))
        self.assertIsNone(w.preview.meta)

    def test_project_off_keeps_state(self):
        w = self.w
        self._song()
        w.song_theme_lw.setCurrentRow(T.KEYS.index("classic"))
        w.project()
        w.project_off()
        self.assertEqual(w.st["song_theme"], "classic")
        self.assertEqual(w.slide[1], "three\nfour")

    def test_choice_saved_to_disk(self):
        w = self.w
        w.song_theme_lw.setCurrentRow(T.KEYS.index("midnight"))
        self.assertEqual(settings.load(w.settings_path)["song_theme"], "midnight")


if __name__ == "__main__":
    unittest.main()
