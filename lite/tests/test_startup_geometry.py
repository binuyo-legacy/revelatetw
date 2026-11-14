"""Startup geometry: the operator window must open wholly inside the primary screen.

Run:  python lite\\tests\\test_startup_geometry.py
Pure geometry math (layout.clamp_startup_geometry) plus one offscreen Qt check
that Main lands inside the (offscreen) primary screen's available geometry.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from revelatelite import layout  # noqa: E402


class Clamp(unittest.TestCase):
    def test_big_screen_keeps_wanted_size_centred(self):
        self.assertEqual(layout.clamp_startup_geometry(1000, 640, 0, 0, 1920, 1080),
                         (460, 220, 1000, 640))

    def test_small_screen_shrinks_to_fit(self):
        # 1000x640 wanted on a 1024x600 screen: shrunk to fit, still centred.
        x, y, w, h = layout.clamp_startup_geometry(1000, 640, 0, 0, 1024, 600)
        self.assertEqual((w, h), (1000, 600))
        self.assertEqual((x, y), (12, 0))
        self.assertLessEqual(x + w, 1024)
        self.assertLessEqual(y + h, 600)

    def test_window_smaller_than_screen_never_overflows(self):
        for aw, ah in ((800, 600), (1024, 600), (1280, 720), (1366, 768)):
            x, y, w, h = layout.clamp_startup_geometry(1000, 640, 0, 0, aw, ah)
            self.assertGreaterEqual(x, 0)
            self.assertGreaterEqual(y, 0)
            self.assertLessEqual(x + w, aw, (aw, ah))
            self.assertLessEqual(y + h, ah, (aw, ah))
            self.assertLessEqual(w, aw)
            self.assertLessEqual(h, ah)

    def test_offset_screen_keeps_window_on_that_screen(self):
        # Secondary screen at x=1920..3840: a 1000x640 window must sit on it.
        x, y, w, h = layout.clamp_startup_geometry(1000, 640, 1920, 0, 1920, 1080)
        self.assertGreaterEqual(x, 1920)
        self.assertLessEqual(x + w, 3840)

    def test_zero_available_falls_back(self):
        self.assertEqual(layout.clamp_startup_geometry(1000, 640, 0, 0, 0, 0),
                         (0, 0, 1000, 640))


class StartupWindow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt5 import QtWidgets
        cls.qa = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        from revelatelite.app import Main
        cls.Main = Main

    def test_window_fits_primary_screen(self):
        from PyQt5 import QtWidgets
        w = self.Main()
        avail = QtWidgets.QApplication.primaryScreen().availableGeometry()
        g = w.geometry()
        self.assertLessEqual(g.width(), avail.width())
        self.assertLessEqual(g.height(), avail.height())
        self.assertGreaterEqual(g.x(), avail.x())
        self.assertGreaterEqual(g.y(), avail.y())
        self.assertLessEqual(g.x() + g.width(), avail.x() + avail.width())
        self.assertLessEqual(g.y() + g.height(), avail.y() + avail.height())
        w.close()


if __name__ == "__main__":
    unittest.main()
