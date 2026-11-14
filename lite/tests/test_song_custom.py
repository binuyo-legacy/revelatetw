"""Tests for song style customising (songs only). Headless Qt; not a Windows 8.1 hardware check.
Run: python -m pytest lite/tests/test_song_custom.py"""
import json
import os
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from PyQt5 import QtCore, QtWidgets
from revelatelite import app as lite_app, paths, settings, songthemes as T
from revelatelite.projection import SlideView
from revelatelite.songs import Song


_APP = []


def qapp():
    if not _APP:
        _APP.append(QtWidgets.QApplication.instance() or QtWidgets.QApplication([]))
        _APP[0].setStyleSheet(lite_app.QSS)
    return _APP[0]


def render(theme, custom=None, meta=T.SAMPLE_META, body=T.SAMPLE_BODY, size=(640, 360)):
    v = SlideView()
    v.set_style("navy", 100, True, "Georgia", False, "", "", None, False, "", 3, theme, custom)
    v.set_content("ref", body, "", meta)
    return v.snapshot(QtCore.QSize(*size)).toImage()


def same(a, b):
    return a.size() == b.size() and a.constBits().asstring(a.byteCount()) == b.constBits().asstring(b.byteCount())


class Model(unittest.TestCase):
    def setUp(self):
        qapp()

    def test_no_overrides_equals_preset(self):
        for k in T.TEMPLATES:
            t = T.resolve(k, {})
            self.assertEqual(t["bg"], T.TEMPLATES[k]["bg"])
            self.assertEqual(t["text"], T.TEMPLATES[k]["text"])
        self.assertIsNone(T.resolve("standard", {"standard": {"text": "#ff0000"}}))

    def test_clean_drops_bad_values(self):
        c = T.clean_custom({"royal": {"text": "red", "scale": 999, "frame": "zig", "shadow": 1, "accent": "#ABCDEF", "font": "Nope"},
                            "standard": {"text": "#ffffff"}, "ghost": {"text": "#ffffff"}, "midnight": "x"})
        self.assertEqual(c, {"royal": {"scale": 150, "accent": "#abcdef"}})

    def test_presets_not_mutated(self):
        before = json.dumps(T.TEMPLATES, sort_keys=True)
        T.resolve("royal", {"royal": {"text": "#ff0000", "frame": "none"}})
        self.assertEqual(json.dumps(T.TEMPLATES, sort_keys=True), before)

    def test_override_changes_only_its_template(self):
        base = render("royal")
        self.assertFalse(same(base, render("royal", {"royal": {"text": "#ff0000"}})))
        self.assertFalse(same(base, render("royal", {"royal": {"align": "left"}})))
        self.assertFalse(same(base, render("royal", {"royal": {"scale": 60}})))
        self.assertTrue(same(render("midnight"), render("midnight", {"royal": {"text": "#ff0000"}})))

    def test_each_option_changes_the_picture(self):
        base = render("royal")
        for ov in ({"show_label": False}, {"show_footer": False}, {"show_count": False}, {"upper": False}, {"frame": "none"},
                   {"bg_kind": "solid"}, {"valign": "top"}, {"two_tone": True}, {"divider": True}, {"shadow": False},
                   {"bold": False}, {"bg1": "#ff0000"}, {"tag": "#00ff00"}, {"dim": "#ff00ff"}):
            self.assertFalse(same(base, render("royal", {"royal": ov})), ov)

    def test_highlight_colour_shows_on_first_line_and_bar(self):
        for ov in ({"two_tone": True}, {"frame": "bar"}):
            a = render("royal", {"royal": ov})
            b = render("royal", {"royal": dict(ov, accent="#ff0000")})
            self.assertFalse(same(a, b), ov)

    def test_verses_ignore_customisation(self):
        custom = {k: {"text": "#ff0000", "frame": "bar", "scale": 60} for k in T.TEMPLATES}
        for k in T.KEYS:
            self.assertTrue(same(render(k, None, meta=None), render(k, custom, meta=None)), k)

    def test_standard_song_ignores_customisation(self):
        self.assertTrue(same(render("standard"), render("standard", {"royal": {"text": "#ff0000"}})))

    def test_option_mixes_do_not_crash(self):
        body = "\n".join("a long lyric line number %d that wraps around the slide" % i for i in range(6))
        for k in T.TEMPLATES:
            for fr in T.CHOICES["frame"]:
                for al in T.CHOICES["align"]:
                    ov = {"frame": fr, "align": al, "valign": "bottom", "scale": 150, "show_label": False, "show_footer": False,
                          "show_count": True, "two_tone": True, "divider": True, "pill": True}
                    render(k, {k: ov}, meta=("T" * 70, "", "Verse 1", 1, 1), body=body, size=(320, 180))
                    render(k, {k: ov}, body="One line", size=(1280, 720))

    def test_blank_stays_black(self):
        v = SlideView()
        v.set_style("navy", 100, True, "Georgia", False, "", "", None, False, "", 3, "royal", {"royal": {"bg1": "#ff0000"}})
        v.set_content("r", T.SAMPLE_BODY, "", T.SAMPLE_META)
        v.blank()
        self.assertEqual(v.snapshot(QtCore.QSize(100, 60)).toImage().pixel(50, 30) & 0xffffff, 0)


class Persist(unittest.TestCase):
    def test_roundtrip(self):
        p = os.path.join(tempfile.mkdtemp(), "s.json")
        d = settings.load(p)
        self.assertEqual(d["song_custom"], {})
        val = {"royal": {"text": "#112233", "align": "left", "scale": 80, "show_footer": False}}
        d["song_custom"] = val
        settings.save(p, d)
        self.assertEqual(settings.load(p)["song_custom"], val)

    def test_old_file_and_garbage(self):
        p = os.path.join(tempfile.mkdtemp(), "s.json")
        json.dump({"song_theme": "royal"}, open(p, "w"))
        self.assertEqual(settings.load(p)["song_custom"], {})
        json.dump({"song_custom": [1, 2]}, open(p, "w"))
        self.assertEqual(settings.load(p)["song_custom"], {})
        json.dump({"song_custom": {"royal": {"text": "nope", "scale": "big"}}}, open(p, "w"))
        self.assertEqual(settings.load(p)["song_custom"], {})


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

    def _pick(self, key):
        self.w.song_theme_lw.setCurrentRow(T.KEYS.index(key))

    def test_disabled_on_standard_enabled_on_template(self):
        w = self.w
        self.assertFalse(w.sc_frame_cb.isEnabled())
        self._pick("royal")
        self.assertTrue(w.sc_frame_cb.isEnabled())
        self.assertFalse(w.sc_reset_b.isEnabled())

    def test_controls_edit_preview_not_screen_and_save(self):
        w = self.w
        self._song()
        self._pick("royal")
        before = w.preview.snapshot(QtCore.QSize(320, 180)).toImage()
        w.sc_align_cb.setCurrentIndex(w.sc_align_cb.findData("left"))
        w.sc_check["show_footer"].setChecked(False)
        w.sc_scale_sp.setValue(70)
        self.assertEqual(w.st["song_custom"]["royal"], {"align": "left", "show_footer": False, "scale": 70})
        self.assertFalse(same(before, w.preview.snapshot(QtCore.QSize(320, 180)).toImage()))
        self.assertEqual(w.preview.song_custom["royal"]["align"], "left")
        self.assertFalse(w.proj.isVisible())
        self.assertEqual(settings.load(w.settings_path)["song_custom"]["royal"]["scale"], 70)
        self.assertTrue(w.sc_reset_b.isEnabled())

    def test_live_screen_keeps_look_until_project(self):
        w = self.w
        self._song()
        self._pick("royal")
        w.project()
        self.assertEqual(w.proj.song_custom, {})
        w.sc_frame_cb.setCurrentIndex(w.sc_frame_cb.findData("bar"))
        self.assertEqual(w.proj.song_custom, {})
        self.assertEqual(w.preview.song_custom["royal"]["frame"], "bar")
        w.project()
        self.assertEqual(w.proj.song_custom["royal"]["frame"], "bar")

    def test_project_off_keeps_customisation_and_slide(self):
        w = self.w
        self._song()
        self._pick("classic")
        w.sc_scale_sp.setValue(120)
        w.project()
        w.project_off()
        self.assertEqual(w.st["song_custom"]["classic"]["scale"], 120)
        self.assertEqual(w.slide[1], "three\nfour")

    def test_bible_styling_untouched(self):
        w = self.w
        keys = [k for k in w.st if not k.startswith("song_")]
        snap = {k: w.st[k] for k in keys}
        for k in T.TEMPLATES:
            self._pick(k)
            w.sc_check["show_label"].setChecked(False)
            w.sc_scale_sp.setValue(140)
            w.sc_frame_cb.setCurrentIndex(w.sc_frame_cb.findData("card"))
        self.assertEqual({k: w.st[k] for k in keys}, snap)
        w._set_slide(("John 3:16 (KJV)", "For God so loved", "KJV"))
        self.assertIsNone(w.preview.meta)
        a = w.preview.snapshot(QtCore.QSize(320, 180)).toImage()
        w.st["song_custom"] = {}
        w._apply_style()
        self.assertTrue(same(a, w.preview.snapshot(QtCore.QSize(320, 180)).toImage()))

    def test_templates_customised_separately_and_reset(self):
        w = self.w
        self._pick("royal")
        w.sc_scale_sp.setValue(60)
        self._pick("midnight")
        self.assertEqual(w.sc_scale_sp.value(), 100)
        self.assertNotIn("midnight", w.st["song_custom"])
        self._pick("royal")
        self.assertEqual(w.sc_scale_sp.value(), 60)
        w.sc_reset_b.click()
        self.assertEqual(w.st["song_custom"], {})
        self.assertEqual(w.sc_scale_sp.value(), 100)

    def test_setting_back_to_preset_value_drops_override(self):
        w = self.w
        self._pick("royal")
        w.sc_scale_sp.setValue(60)
        w.sc_scale_sp.setValue(100)
        self.assertEqual(w.st["song_custom"], {})

    def test_gallery_icon_updates(self):
        w = self.w
        self._pick("royal")
        a = w.song_theme_lw.item(T.KEYS.index("royal")).icon().pixmap(160, 90).toImage()
        w.sc_frame_cb.setCurrentIndex(w.sc_frame_cb.findData("none"))
        b = w.song_theme_lw.item(T.KEYS.index("royal")).icon().pixmap(160, 90).toImage()
        self.assertFalse(same(a, b))

    def test_saved_custom_loads_on_start(self):
        w = self.w
        self._pick("light")
        w.sc_align_cb.setCurrentIndex(w.sc_align_cb.findData("right"))
        w2 = lite_app.Main()
        try:
            self.assertEqual(w2.st["song_custom"]["light"]["align"], "right")
            self.assertEqual(w2.preview.song_custom["light"]["align"], "right")
        finally:
            w2.proj.hide()


if __name__ == "__main__":
    unittest.main()
