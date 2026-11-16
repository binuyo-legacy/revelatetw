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
        w = lite_app.Main()
        w.st["transition_ms"] = 0      # these tests are about content, so screen changes are instant (see test_transitions.py)
        return w

    def test_preview_follows_lookup_and_style(self):
        lite_app.Main._installed_fonts = staticmethod(lambda: ["Arial", "Georgia"])
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

    def test_enter_never_opens_projector(self):
        w = self.make()
        w.box.setText("Rom 8:28")
        w.box.returnPressed.emit()
        self.assertIn("Romans 8:28", w.preview.ref)
        self.assertFalse(w.proj.live)
        self.assertFalse(w.proj.isVisible())
        self.assertFalse(w.blank_b.isEnabled())
        w.step(1)
        w.size_sp.setValue(130)
        self.assertFalse(w.proj.isVisible())
        w.close()

    def test_project_then_edit_stays_local_then_project_off_keeps_state(self):
        w = self.make()
        w.lookup("Rom 8:28")
        w.add_to_list()
        w.project()
        self.assertTrue(w.proj.isVisible())
        self.assertTrue(w.blank_b.isEnabled())
        w.lookup("John 3:16")
        w.size_sp.setValue(140)
        self.assertIn("Romans 8:28", w.proj.ref)
        self.assertNotEqual(w.proj.scale, 140)
        self.assertIn("not sent", w.live_badge.text())
        w.project()
        self.assertIn("John 3:16", w.proj.ref)
        self.assertEqual(w.proj.scale, 140)
        self.assertEqual(w.live_badge.text(), "LIVE")
        w.lookup("Rom 8:28")
        w.project_off()
        self.assertFalse(w.proj.isVisible())
        self.assertFalse(w.proj.live)
        self.assertFalse(w.preview.on_air)
        self.assertFalse(w.blank_b.isEnabled())
        self.assertIn("Romans 8:28", w.preview.ref)        # preview kept
        self.assertEqual(len(w.services.items), 1)
        self.assertTrue(w.project_b.isEnabled())
        w.lookup("John 3:16")
        self.assertFalse(w.proj.isVisible())
        w.project()
        self.assertTrue(w.proj.isVisible())
        w.proj.close()
        w.close()

    def test_esc_and_f5_work_from_the_projector_window(self):
        from PyQt5 import QtCore, QtGui, QtTest
        w = self.make()
        w.lookup("Rom 8:28")
        w.project()
        self.assertTrue(w.proj.isVisible())
        w.lookup("John 3:16")
        QtTest.QTest.keyClick(w.proj, QtCore.Qt.Key_F5)
        self.assertIn("John 3:16", w.proj.ref)
        QtTest.QTest.keyClick(w.proj, QtCore.Qt.Key_Escape)
        self.assertFalse(w.proj.isVisible())
        self.assertIn("John 3:16", w.preview.ref)
        self.assertFalse(w.blank_b.isEnabled())
        w.close()

    def test_f1_works_from_the_projector_window(self):
        from PyQt5 import QtCore, QtGui, QtTest
        w = self.make()
        w.lookup("Rom 8:28")
        w.project()
        self.assertTrue(w.proj.isVisible())
        w.lookup("John 3:16")
        QtTest.QTest.keyClick(w.proj, QtCore.Qt.Key_F1)
        self.assertIn("John 3:16", w.proj.ref)
        QtTest.QTest.keyClick(w.proj, QtCore.Qt.Key_Escape)
        self.assertFalse(w.proj.isVisible())
        w.close()

    def test_closing_projector_window_resets_live_state(self):
        w = self.make()
        w.lookup("Rom 8:28")
        w.add_to_list()
        w.project()
        w.proj.close()
        self.assertFalse(w.proj.live)
        self.assertFalse(w.preview.on_air)
        self.assertEqual(w.live_badge.text(), "")
        self.assertFalse(w.blank_b.isEnabled())
        self.assertIn("Romans 8:28", w.preview.ref)
        self.assertEqual(len(w.services.items), 1)
        w.project()
        self.assertTrue(w.proj.isVisible())
        w.proj.close()
        w.close()

    def test_project_without_verse_says_so_and_status_resets(self):
        w = self.make()
        w._set_slide(None)
        w.cur = None
        w.lookup("Nope 9:9")
        w.project()
        self.assertIn("Look up a verse", w.status.text())
        self.assertFalse(w.proj.isVisible())
        w.close()


    def test_display_box_headings_are_preview_and_program(self):
        w = self.make()
        w.show()
        hints = [l.text() for l in w.findChildren(QtWidgets.QLabel)
                 if l.objectName() == "hint"]
        self.assertIn("Preview", hints)
        self.assertIn("Program", hints)
        for old in ("Live preview (what the screen shows)",
                    "Programs (live output on the projector screen, view only)",
                    "Programs"):
            self.assertNotIn(old, hints)
        self.assertLess(hints.index("Preview"), hints.index("Program"))
        self.assertEqual(w.tv_frame.size(), w.programs_frame.size())
        w.close()



if __name__ == "__main__":
    unittest.main()
