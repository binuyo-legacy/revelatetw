"""Background tests: pure maths (always run) and Qt checks (skip without PyQt5)."""
import os
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from revelatelite import background as bg, settings
try:
    from PyQt5 import QtCore, QtGui, QtWidgets
    from revelatelite import app as lite_app
except ImportError:  # pragma: no cover
    QtWidgets = None


class Maths(unittest.TestCase):
    def test_clean_defaults_and_bad_values(self):
        c = bg.clean({"bg_kind": "x", "grad_color1": "red", "grad_direction": "up", "image_mode": 5,
                      "image_dim": 999, "bg_image": 7})
        self.assertEqual((c["bg_kind"], c["grad_direction"], c["image_mode"], c["bg_image"]), ("color", "vertical", "fill", ""))
        self.assertEqual(c["grad_color1"], bg.DEFAULT_C1)
        self.assertEqual(c["image_dim"], bg.DIM_MAX)
        self.assertEqual(bg.clean({"image_dim": True})["image_dim"], 30)

    def test_settings_roundtrip_and_old_file(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "s.json")
        settings.save(p, dict(settings.DEFAULTS, bg_kind="gradient", grad_color2="#ff0000", image_mode="tile", bg_image="C:\\a.png"))
        s = settings.load(p)
        self.assertEqual((s["bg_kind"], s["grad_color2"], s["image_mode"], s["bg_image"]), ("gradient", "#ff0000", "tile", "C:\\a.png"))
        with open(p, "w") as f:
            f.write('{"theme": "gold"}')      # a file from before this feature
        s = settings.load(p)
        self.assertEqual((s["bg_kind"], s["theme"]), ("color", "gold"))
        with open(p, "w") as f:
            f.write('{"bg_kind": "image", "image_mode": "zoom", "grad_direction": 3')   # damaged
        self.assertEqual(settings.load(p)["image_mode"], "fill")

    def test_gradient_points(self):
        self.assertEqual(bg.gradient_points("vertical", 100, 50), (0, 0, 0, 50))
        self.assertEqual(bg.gradient_points("horizontal", 100, 50), (0, 0, 100, 0))
        self.assertEqual(bg.gradient_points("diagonal_down", 100, 50), (0, 0, 100, 50))
        self.assertEqual(bg.gradient_points("diagonal_up", 100, 50), (0, 50, 100, 0))

    def test_mix(self):
        self.assertEqual(bg.mix("#000000", "#ffffff"), "#7f7f7f")

    def test_fit_and_fill_rects(self):
        self.assertEqual(bg.fit_size(1000, 1000, 1600, 900), (900, 900))
        self.assertEqual(bg.fit_size(1000, 1000, 1600, 900, cover=True), (1600, 1600))
        self.assertEqual(bg.image_rects("stretch", 100, 100, 160, 90), ((0, 0, 100, 100), (0, 0, 160, 90)))
        src, dst = bg.image_rects("fit", 100, 100, 160, 90)
        self.assertEqual((src, dst), ((0, 0, 100, 100), (35, 0, 90, 90)))
        src, dst = bg.image_rects("fill", 100, 100, 160, 90)
        self.assertEqual(dst, (0, 0, 160, 90))
        self.assertEqual(src[2], 100)
        self.assertTrue(55 <= src[3] <= 57)               # 100 * 90/160 = 56.25
        self.assertEqual(src[1], (100 - src[3]) // 2)     # centred crop

    def test_check_image_file(self):
        self.assertEqual(bg.check_image_file(""), (False, ""))
        self.assertIn("not found", bg.check_image_file(os.path.join(tempfile.gettempdir(), "nope_zz.png"))[1])
        d = tempfile.mkdtemp()
        t = os.path.join(d, "a.txt")
        open(t, "w").write("x")
        self.assertIn("not supported", bg.check_image_file(t)[1])
        ok = os.path.join(d, "a.PNG")
        open(ok, "wb").write(b"x")
        self.assertTrue(bg.check_image_file(ok)[0])

    def test_spec_changes(self):
        a = bg.spec_from({})
        self.assertEqual(a, bg.spec_from({}))
        self.assertNotEqual(a, bg.spec_from({"bg_kind": "gradient"}))


def make_png(path, w=200, h=100, color=0xFFFF0000, fmt="PNG"):
    im = QtGui.QImage(w, h, QtGui.QImage.Format_RGB32)
    im.fill(QtGui.QColor.fromRgba(color))
    assert im.save(path, fmt)


@unittest.skipIf(QtWidgets is None, "PyQt5 not installed")
class QtSide(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qa = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        cls.qa.setStyleSheet(lite_app.QSS)

    def make(self):
        d = tempfile.mkdtemp()
        lite_app.paths.user_dir = lambda: d
        self.dir = d
        w = lite_app.Main()
        w.st["transition_ms"] = 0      # these tests are about content, so screen changes are instant (see test_transitions.py)
        return w

    def grab(self, view, w=320, h=180):
        view.resize(w, h)
        return view.grab().toImage()

    def test_tab_renamed(self):
        w = self.make()
        names = []
        tabs = w.findChild(QtWidgets.QTabWidget)
        names = [tabs.tabText(i) for i in range(tabs.count())]
        self.assertIn("Settings", names)
        self.assertNotIn("Look and screen", names)

    def test_gradient_renders_both_colours_and_matches_projector(self):
        w = self.make()
        w.st.update(grad_color1="#ff0000", grad_color2="#0000ff")
        w.gdir_cb.setCurrentIndex(w.gdir_cb.findData("horizontal"))
        w.bgkind_cb.setCurrentIndex(w.bgkind_cb.findData("gradient"))
        self.assertEqual(w.st["bg_kind"], "gradient")
        w.project()
        a = self.grab(w.preview.__class__.__mro__[1] and w.preview)
        b = self.grab(w.proj)
        # compare background pixels in a text-free spot: left edge and right edge
        ia, ib = a.pixelColor(3, 90), b.pixelColor(3, 90)
        self.assertGreater(ia.red(), 200)
        self.assertGreater(a.pixelColor(316, 90).blue(), 200)
        self.assertGreater(ib.red(), 200)
        self.assertGreater(b.pixelColor(316, 90).blue(), 200)
        w.project_off()
        w.close()

    def test_gradient_vertical_direction(self):
        w = self.make()
        w.st.update(grad_color1="#ff0000", grad_color2="#0000ff")
        w.gdir_cb.setCurrentIndex(w.gdir_cb.findData("vertical"))
        w.bgkind_cb.setCurrentIndex(w.bgkind_cb.findData("gradient"))
        im = self.grab(w.preview)
        self.assertGreater(im.pixelColor(3, 3).red(), im.pixelColor(3, 176).red())
        self.assertGreater(im.pixelColor(3, 176).blue(), im.pixelColor(3, 3).blue())
        w.close()

    def test_image_modes(self):
        w = self.make()
        png = os.path.join(self.dir, "pic.png")
        make_png(png, 100, 100, 0xFF00FF00)           # square green picture
        w.choose_image(png)
        self.assertEqual(w.st["bg_kind"], "image")
        self.assertEqual(w.st["bg_image"], png)
        w.imgdim_sp.setValue(0)
        w.imgmode_cb.setCurrentIndex(w.imgmode_cb.findData("fit"))
        im = self.grab(w.preview)
        self.assertGreater(im.pixelColor(160, 90).green(), 200)       # centre is picture
        self.assertLess(im.pixelColor(2, 90).green(), 80)             # side bar is the plain colour
        w.imgmode_cb.setCurrentIndex(w.imgmode_cb.findData("fill"))
        im = self.grab(w.preview)
        self.assertGreater(im.pixelColor(2, 2).green(), 200)          # covers the corner
        w.imgmode_cb.setCurrentIndex(w.imgmode_cb.findData("stretch"))
        im = self.grab(w.preview)
        self.assertGreater(im.pixelColor(317, 3).green(), 200)
        w.imgmode_cb.setCurrentIndex(w.imgmode_cb.findData("tile"))
        im = self.grab(w.preview)
        self.assertGreater(im.pixelColor(310, 170).green(), 200)
        w.close()

    def test_bad_files_rejected_and_old_background_kept(self):
        w = self.make()
        bad = os.path.join(self.dir, "fake.png")
        open(bad, "wb").write(b"not an image at all")
        w.choose_image(bad)
        self.assertEqual(w.st["bg_image"], "")
        self.assertEqual(w.st["bg_kind"], "color")
        self.assertTrue(w.img_lbl.text())
        txt = os.path.join(self.dir, "x.txt")
        open(txt, "w").write("hi")
        w.choose_image(txt)
        self.assertIn("not supported", w.img_lbl.text())
        w.choose_image(os.path.join(self.dir, "gone.png"))
        self.assertIn("not found", w.img_lbl.text())
        self.assertEqual(w.st["bg_image"], "")
        w.close()

    def test_missing_saved_image_falls_back_and_does_not_crash(self):
        d = tempfile.mkdtemp()
        lite_app.paths.user_dir = lambda: d
        settings.save(os.path.join(d, "settings.json"),
                      dict(settings.DEFAULTS, bg_kind="image", bg_image=os.path.join(d, "deleted.jpg")))
        w = lite_app.Main()
        im = self.grab(w.preview)
        self.assertIsNotNone(im)
        self.assertIn("not found", w.img_lbl.text())
        self.assertEqual(w.st["bg_kind"], "image")       # setting kept, so restoring the file brings it back
        w.close()

    def test_bright_picture_hint_and_tile_repaint(self):
        self.assertEqual(bg.too_bright_hint(10, 30), "")
        self.assertIn("bright", bg.too_bright_hint(250, 30))
        self.assertEqual(bg.too_bright_hint(250, 80), "")
        w = self.make()
        png = os.path.join(self.dir, "white.png")
        make_png(png, 100, 100, 0xFFFFFFFF)
        w.choose_image(png)
        w.imgdim_sp.setValue(0)
        self.assertIn("bright", w.img_lbl.text())
        w.imgdim_sp.setValue(80)
        self.assertNotIn("bright", w.img_lbl.text())
        # a different picture with the same size must not reuse the old scaled copy
        png2 = os.path.join(self.dir, "red.png")
        make_png(png2, 100, 100, 0xFFFF0000)
        w.imgdim_sp.setValue(0)
        w.imgmode_cb.setCurrentIndex(w.imgmode_cb.findData("tile"))
        self.grab(w.preview)
        w.choose_image(png2)
        im = self.grab(w.preview)
        self.assertGreater(im.pixelColor(310, 170).red(), 200)
        self.assertLess(im.pixelColor(310, 170).green(), 80)
        self.assertEqual(w.st["bg_kind"], "image")
        w.close()

    def test_font_groups_and_persistence(self):
        self.assertEqual(len(settings.FONTS), len(set(settings.FONTS)))
        self.assertGreaterEqual(len(settings.FONTS), 20)
        self.assertIn("Georgia", settings.FONTS)
        d = tempfile.mkdtemp()
        p = os.path.join(d, "s.json")
        settings.save(p, dict(settings.DEFAULTS, font_family="Impact"))
        self.assertEqual(settings.load(p)["font_family"], "Impact")
        settings.save(p, dict(settings.DEFAULTS, font_family="Not A Font"))
        self.assertEqual(settings.load(p)["font_family"], "Georgia")
        lite_app.Main._installed_fonts = staticmethod(lambda: ["Arial", "Impact", "Consolas", "Georgia"])
        w = self.make()
        items = [w.font_cb.itemText(i) for i in range(w.font_cb.count())]
        self.assertNotIn("Cambria", items)       # not installed here, so not offered
        heads = [t for t in items if t.startswith("-- ")]
        self.assertTrue(heads)
        self.assertIn("Georgia", items)
        i = w.font_cb.findText(heads[0])
        self.assertFalse(w.font_cb.model().item(i).flags() & QtCore.Qt.ItemIsEnabled)
        pick = next(t for t in items if not t.startswith("-- ") and t != "Georgia")
        w.font_cb.setCurrentIndex(w.font_cb.findText(pick))
        self.assertEqual(w.st["font_family"], pick)
        self.assertEqual((w.preview.font_family, w.proj.font_family), (pick, pick))
        d = self.dir
        w.close()
        lite_app.paths.user_dir = lambda: d      # restart in the same settings folder
        w = lite_app.Main()
        self.assertEqual(w.font_cb.currentText(), pick)
        w.close()

    def test_big_image_is_capped_and_cached(self):
        d = tempfile.mkdtemp()
        big = os.path.join(d, "big.png")
        make_png(big, 4000, 3000, 0xFF123456)
        img, msg = bg.load_image(big)
        self.assertEqual(msg, "")
        self.assertLessEqual(img.width(), bg.MAX_W)
        self.assertLessEqual(img.height(), bg.MAX_H)
        self.assertIs(img, bg.load_image(big)[0])        # cached, not decoded twice

    def test_edits_stay_preview_only_until_project(self):
        w = self.make()
        w.lookup("John 3:16")
        w.project()
        sent = w.proj.bg_spec
        w.bgkind_cb.setCurrentIndex(w.bgkind_cb.findData("gradient"))
        w.gdir_cb.setCurrentIndex(w.gdir_cb.findData("diagonal_down"))
        self.assertEqual(w.proj.bg_spec, sent)                        # projector untouched
        self.assertEqual(w.preview.bg_spec[0], "gradient")
        self.assertIn("preview not sent", w.live_badge.text())
        w.project()
        self.assertEqual(w.proj.bg_spec, w.preview.bg_spec)
        self.assertEqual(w.live_badge.text(), "LIVE")
        w.project_off()
        w.close()

    def test_persisted_across_restart(self):
        w = self.make()
        w.st.update(grad_color1="#112233")
        w.swap_grad()
        w.bgkind_cb.setCurrentIndex(w.bgkind_cb.findData("gradient"))
        d = self.dir
        w.close()
        lite_app.paths.user_dir = lambda: d
        w2 = lite_app.Main()
        self.assertEqual(w2.bgkind_cb.currentData(), "gradient")
        self.assertEqual(w2.st["grad_color2"], "#112233")
        w2.close()

    def test_remove_picture(self):
        w = self.make()
        png = os.path.join(self.dir, "p.png")
        make_png(png)
        w.choose_image(png)
        w.remove_image()
        self.assertEqual((w.st["bg_image"], w.st["bg_kind"]), ("", "color"))
        w.close()


if __name__ == "__main__":
    unittest.main()
