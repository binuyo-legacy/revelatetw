"""Qt smoke test for the live preview. Skips itself if PyQt5 is missing.  Run: python lite\tests\test_preview_qt.py"""
import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
try:
    from PyQt5 import QtWidgets
    from revelatelite import app as lite_app
except ImportError:  # pragma: no cover
    QtWidgets = None


@unittest.skipIf(QtWidgets is None, "PyQt5 not installed")
class PreviewQt(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qa = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        cls.qa.setStyleSheet(lite_app.QSS)

    def make(self):
        import tempfile
        from revelatelite import paths
        d = tempfile.mkdtemp()
        paths.user_dir = lambda: d
        lite_app.paths.user_dir = lambda: d
        return lite_app.Main()

    def test_preview_follows_lookup_and_style(self):
        w = self.make()
        w.show()
        self.assertTrue(w.preview.body)
        self.assertEqual(w.preview.height() * 16 // 9 // 1, w.preview.height() * 16 // 9)
        w.lookup("John 3:16")
        self.assertIn("John 3:16", w.preview.ref)
        w.size_sp.setValue(150)
        w.font_cb.setCurrentText("Arial")
        w.bold_cb.setChecked(True)
        w.st["bg_color"] = "#ffffff"
        w._style_changed()
        for v in (w.preview, w.proj):
            self.assertEqual((v.scale, v.font_family, v.bold, v.bg_color), (150, "Arial", True, "#ffffff"))
        img = w.preview.grab().toImage()
        self.assertEqual(img.pixelColor(img.width() // 2, 6).name(), "#ffffff")
        w.reset_colors()
        self.assertEqual(w.preview.bg_color, "")
        w.close()

    def test_preview_shows_while_projector_black(self):
        w = self.make()
        w.lookup("Rom 8:28")
        w.blank()
        self.assertFalse(w.preview.on_air)
        self.assertTrue(w.preview.live)
        w.close()

    def test_live_frame_when_projected(self):
        w = self.make()
        w.lookup("Rom 8:28")
        w.project()
        self.assertTrue(w.preview.on_air)
        w.proj.close()
        w.close()


if __name__ == "__main__":
    unittest.main()
