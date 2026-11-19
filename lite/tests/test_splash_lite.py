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


if __name__ == "__main__":
    unittest.main()
