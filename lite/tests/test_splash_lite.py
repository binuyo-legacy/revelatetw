"""Startup splash checks (offscreen Qt). Run: python lite\\tests\\test_splash_lite.py"""
import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from PyQt5 import QtCore, QtGui, QtWidgets  # noqa: E402
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

    def test_logo_corners_are_clipped_at_display_time(self):
        # The logo file itself stays square; only the paint clip rounds it.
        pm = splash._load_scaled_pixmap()
        self.assertIsNotNone(pm)
        r = splash.corner_radius_for(pm)
        self.assertTrue(30 <= r <= 80, "radius %r is not in the 40-60px ballpark" % r)
        path = splash.rounded_clip_path(
            QtCore.QRectF(0, 0, pm.width(), pm.height()), r)
        self.assertTrue(path.contains(QtCore.QPointF(pm.width() / 2.0, pm.height() / 2.0)),
                        "clip must cover the middle of the logo")
        self.assertFalse(path.contains(QtCore.QPointF(2, 2)),
                         "clip must exclude the square corner")
        self.assertFalse(path.contains(QtCore.QPointF(pm.width() - 2, pm.height() - 2)),
                         "clip must exclude every square corner")

        label = splash.LogoLabel()
        label.setPixmap(pm)
        label.resize(pm.width(), pm.height())
        label.show()
        QtWidgets.QApplication.processEvents()
        out = QtGui.QPixmap(pm.width(), pm.height())
        out.fill(QtGui.QColor(255, 255, 255))
        painter = QtGui.QPainter(out)
        label.render(painter, QtCore.QPoint(0, 0))
        painter.end()
        img = out.toImage()
        corner = img.pixelColor(2, 2)
        centre = img.pixelColor(pm.width() // 2, pm.height() // 2)
        self.assertEqual((corner.red(), corner.green(), corner.blue()), (255, 255, 255),
                         "the corner pixel must not be painted through the clip")
        self.assertNotEqual((centre.red(), centre.green(), centre.blue()), (255, 255, 255),
                            "the middle of the logo must still paint")
        label.hide()


    def test_bar_is_visibly_painted_inside_splash_geometry(self):
        # Regression: the bar's stylesheet used double braces with
        # %-formatting, so Qt rejected it and the bar silently fell back to
        # the native blue busy bar, which reads as gone on Windows. Offscreen
        # this test fails on the old stylesheet (native blue, no gold/dark
        # track) and passes once the stylesheet actually applies.
        sp = splash.show_splash()
        self.assertIsNotNone(sp)
        self.assertTrue(sp.bar.isVisible())
        self.assertTrue(sp.bar.isEnabled())
        self.assertIn("{ background:", sp.bar.styleSheet())
        self.assertNotIn("{{", sp.bar.styleSheet())
        bx = sp.bar.x()
        by = sp.bar.y()
        self.assertGreaterEqual(by - sp.logo_label.y() - sp.logo_label.height(), 0,
                                "bar must sit below the logo, not overlap it")
        self.assertLessEqual(by + sp.bar.height(), sp.height(),
                             "bar bottom must be inside the splash window")
        self.assertGreaterEqual(bx, 0)
        self.assertLessEqual(bx + sp.bar.width(), sp.width())
        # Painted pixels: the bar region must contain both the dark track
        # and the gold accent, not the native blue fallback and not the
        # surrounding desktop (white in this render).
        pm = QtGui.QPixmap(sp.width(), sp.height())
        pm.fill(QtGui.QColor(255, 255, 255))
        painter = QtGui.QPainter(pm)
        sp.render(painter, QtCore.QPoint(0, 0))
        painter.end()
        img = pm.toImage()
        gold = dark = 0
        for y in range(by, by + sp.bar.height()):
            for x in range(bx, bx + sp.bar.width()):
                c = img.pixelColor(x, y)
                if c.red() > 200 and 150 < c.green() < 230 and c.blue() < 80:
                    gold += 1
                if abs(c.red() - 0x3a) < 30 and abs(c.green() - 0x3a) < 30 and abs(c.blue() - 0x40) < 30:
                    dark += 1
        self.assertGreater(gold, 50, "gold chunk must actually paint in the bar region")
        self.assertGreater(dark, 100, "dark track must actually paint in the bar region")
        splash.finish_splash(sp)


if __name__ == "__main__":
    unittest.main()
