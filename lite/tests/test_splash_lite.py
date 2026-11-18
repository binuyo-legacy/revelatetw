"""Startup splash checks (offscreen Qt). Run: python lite\\tests\\test_splash_lite.py"""
import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from PyQt5 import QtGui, QtWidgets  # noqa: E402
from revelatelite import splash  # noqa: E402


class Splash(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qa = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_logo_file_is_readable(self):
        self.assertTrue(os.path.isfile(splash.splash_logo_path()))
        pm = QtGui.QPixmap(splash.splash_logo_path())
        self.assertFalse(pm.isNull(), "splash image must load")
        self.assertEqual((pm.width(), pm.height()), (1568, 940))

    def test_splash_shows_busy_bar_below_logo(self):
        sp = splash.show_splash()
        self.assertIsNotNone(sp, "splash must show when the logo loads")
        self.assertEqual((sp.bar.minimum(), sp.bar.maximum()), (0, 0), "busy/indeterminate")
        self.assertTrue(sp.bar.y() > sp.logo_label.y(), "bar below the logo")
        self.assertTrue(sp.bar.x() + sp.bar.width() // 2 == sp.width() // 2
                        or abs((sp.bar.x() + sp.bar.width() // 2) - sp.width() // 2) <= 2)
        self.assertTrue(sp.isVisible())
        splash.finish_splash(sp)
        self.assertFalse(sp.isVisible(), "finish_splash must close it")

    def test_no_splash_flag(self):
        self.assertTrue(splash.wants_splash([]))
        self.assertFalse(splash.wants_splash(["--no-splash"]))


if __name__ == "__main__":
    unittest.main()
