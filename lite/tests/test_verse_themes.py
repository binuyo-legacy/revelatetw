"""Tests for the Bible verse slide templates. Headless (offscreen Qt); not a Windows 8.1 hardware check.
Run: python -m pytest lite/tests/test_verse_themes.py"""
import json
import os
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from PyQt5 import QtCore, QtWidgets
from revelatelite import app as lite_app, paths, settings, songthemes, versethemes as V
from revelatelite.projection import SlideView
from revelatelite.songs import Song


_QA = []


def qapp():
    qa = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    _QA[:] = [qa]       # keep a reference so Qt is not torn down between tests
    qa.setStyleSheet(lite_app.QSS)
    return qa


def render(theme=None, meta=None, size=(640, 360), show_ref=True, credit=""):
    v = SlideView()
    if theme is None:       # old call shape: no verse template argument at all
        v.set_style("navy", 100, show_ref, "Georgia", False, "", "", None, False, "", 3)
    else:
        v.set_style("navy", 100, show_ref, "Georgia", False, "", "", None, False, "", 3, songthemes.STANDARD, None, theme)
    v.set_content(V.SAMPLE_REF, V.SAMPLE_BODY, credit, meta)
    return v.snapshot(QtCore.QSize(*size)).toImage()


def same(a, b):
    return a.size() == b.size() and a.constBits().asstring(a.byteCount()) == b.constBits().asstring(b.byteCount())


class Presets(unittest.TestCase):
    def setUp(self):
        qapp()

    def test_default_plus_six_named_templates(self):
        self.assertEqual(V.KEYS[0], "default")
        self.assertEqual(len(V.TEMPLATES), 6)
        self.assertEqual(len({t["name"] for t in V.TEMPLATES.values()}), 6)
        self.assertEqual(len({t["blurb"] for t in V.TEMPLATES.values()}), 6)

    def test_default_is_identical_to_old_rendering(self):
        self.assertTrue(same(render(None), render("default")))
        self.assertTrue(same(render(None, show_ref=False), render("default", show_ref=False)))

    def test_every_template_renders_and_all_are_distinct(self):
        imgs = {k: render(k) for k in V.KEYS}
        keys = list(imgs)
        for i in range(len(keys)):
            self.assertFalse(imgs[keys[i]].isNull())
            for j in range(i + 1, len(keys)):
                self.assertFalse(same(imgs[keys[i]], imgs[keys[j]]), (keys[i], keys[j]))

    def test_each_template_handles_no_reference_credit_and_long_text(self):
        long_body = " ".join(["word"] * 120)
        for k in V.TEMPLATES:
            self.assertFalse(same(render(k, show_ref=False), render(k)), k)
            self.assertFalse(render(k, credit="KJV").isNull())
            v = SlideView()
            v.set_style("navy", 150, True, "Georgia", True, "", "", None, True, "", 3, songthemes.STANDARD, None, k)
            v.set_content("Psalm 119:1", long_body, "KJV")
            self.assertFalse(v.snapshot(QtCore.QSize(320, 180)).isNull())
            v.blank()
            self.assertFalse(v.snapshot(QtCore.QSize(320, 180)).isNull())

    def test_blank_screen_stays_black(self):
        v = SlideView()
        v.set_style("navy", 100, True, "Georgia", False, "", "", None, False, "", 3, songthemes.STANDARD, None, "gold")
        v.blank()
        img = v.snapshot(QtCore.QSize(64, 36)).toImage()
        self.assertEqual(img.pixelColor(10, 10).name(), "#000000")

    def test_song_slides_ignore_verse_template(self):
        meta = songthemes.SAMPLE_META
        base = render("default", meta=meta)
        for k in V.TEMPLATES:
            self.assertTrue(same(render(k, meta=meta), base), k)

    def test_unknown_key_cleans_to_default(self):
        self.assertEqual(V.clean("nope"), "default")
        self.assertEqual(V.clean(5), "default")
        self.assertIsNone(V.resolve("default"))


class Persistence(unittest.TestCase):
    def setUp(self):
        qapp()

    def test_default_value_and_roundtrip(self):
        p = os.path.join(tempfile.mkdtemp(), "s.json")
        self.assertEqual(settings.load(p)["verse_theme"], "default")
        d = settings.load(p)
        d["verse_theme"] = "gold"
        settings.save(p, d)
        self.assertEqual(settings.load(p)["verse_theme"], "gold")

    def test_old_settings_file_without_key_loads_default(self):
        p = os.path.join(tempfile.mkdtemp(), "s.json")
        json.dump({"theme": "black", "song_theme": "royal"}, open(p, "w"))
        d = settings.load(p)
        self.assertEqual((d["verse_theme"], d["song_theme"]), ("default", "royal"))

    def test_bad_value_falls_back(self):
        p = os.path.join(tempfile.mkdtemp(), "s.json")
        for bad in ("bogus", 7, None):
            json.dump({"verse_theme": bad}, open(p, "w"))
            self.assertEqual(settings.load(p)["verse_theme"], "default")


class AppFlow(unittest.TestCase):
    def setUp(self):
        qapp()
        d = tempfile.mkdtemp()
        self._old = paths.user_dir
        paths.user_dir = lambda: d
        lite_app.paths.user_dir = lambda: d
        self.w = lite_app.Main()
        self.w.st["transition_onoff"] = self.w.st["transition_switch"] = False
        self.w._set_slide(("John 3:16 (KJV)", "For God so loved the world", "KJV"))

    def tearDown(self):
        self.w.proj.hide()
        paths.user_dir = self._old
        lite_app.paths.user_dir = self._old

    def test_gallery_rows_icons_and_default_selected(self):
        lw = self.w.verse_theme_lw
        self.assertEqual(lw.count(), 7)
        self.assertEqual(lw.currentRow(), 0)
        self.assertFalse(lw.item(1).icon().isNull())
        self.assertEqual(self.w.st["verse_theme"], "default")

    def test_choose_changes_preview_only_not_screen(self):
        w = self.w
        before = w.preview.snapshot(QtCore.QSize(320, 180)).toImage()
        w.verse_theme_lw.setCurrentRow(V.KEYS.index("parchment"))
        self.assertEqual(w.preview.verse_theme, "parchment")
        self.assertFalse(same(before, w.preview.snapshot(QtCore.QSize(320, 180)).toImage()))
        self.assertFalse(w.proj.isVisible())
        self.assertFalse(w.proj.live)

    def test_live_screen_keeps_look_until_project(self):
        w = self.w
        w.project()
        self.assertEqual(w.proj.verse_theme, "default")
        w.verse_theme_lw.setCurrentRow(V.KEYS.index("dawn"))
        self.assertEqual(w.proj.verse_theme, "default")
        self.assertEqual(w.preview.verse_theme, "dawn")
        w.project()
        self.assertEqual(w.proj.verse_theme, "dawn")

    def test_project_off_keeps_choice_and_slide(self):
        w = self.w
        w.verse_theme_lw.setCurrentRow(V.KEYS.index("cardroyal"))
        w.project()
        w.project_off()
        self.assertEqual(w.st["verse_theme"], "cardroyal")
        self.assertEqual(w.slide[1], "For God so loved the world")

    def test_choice_saved_to_disk(self):
        w = self.w
        w.verse_theme_lw.setCurrentRow(V.KEYS.index("scripture"))
        self.assertEqual(settings.load(w.settings_path)["verse_theme"], "scripture")

    def test_switching_does_not_touch_song_or_background_settings(self):
        w = self.w
        w.song_theme_lw.setCurrentRow(songthemes.KEYS.index("royal"))
        keep = {k: (json.dumps(w.st[k], sort_keys=True)) for k in
                ("song_theme", "song_custom", "bg_kind", "bg_color", "text_color", "grad_color1", "grad_color2",
                 "bg_image", "image_mode", "image_dim", "font_family", "theme", "transition_effect",
                 "proj_on_effect", "proj_off_effect")}
        for k in V.KEYS:
            w.verse_theme_lw.setCurrentRow(V.KEYS.index(k))
        saved = settings.load(w.settings_path)
        for k, v in keep.items():
            self.assertEqual(json.dumps(w.st[k], sort_keys=True), v, k)
            self.assertEqual(json.dumps(saved[k], sort_keys=True), v, k)
        self.assertEqual(w.preview.song_theme, "royal")

    def test_song_slide_in_app_ignores_verse_template(self):
        w = self.w
        s = Song("Way Maker", "Sinach", [{"label": "Verse", "lines": ["one", "two"]}])
        w.songs.save(s)
        w.song_all = w.songs.load_all()
        w.refresh_songs()
        w.song_list.setCurrentRow(0)
        w.pick_slide(0)
        self.assertIsNotNone(w.preview.meta)
        a = w.preview.snapshot(QtCore.QSize(320, 180)).toImage()
        w.verse_theme_lw.setCurrentRow(V.KEYS.index("gold"))
        self.assertTrue(same(a, w.preview.snapshot(QtCore.QSize(320, 180)).toImage()))


if __name__ == "__main__":
    unittest.main()
