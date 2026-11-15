"""TV frame glow fade (offscreen Qt). Run: python -m pytest lite/tests/test_tv_glow.py"""
import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
try:
    from PyQt5 import QtWidgets, QtCore
    from revelatelite import theme
except ImportError:  # pragma: no cover
    QtWidgets = None


@unittest.skipIf(QtWidgets is None, "PyQt5 not installed")
class TvGlow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qa = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def make(self):
        inner = QtWidgets.QWidget()
        inner.setMinimumSize(320, 180)
        f = theme.TvFrame(inner)
        f.resize(360, 230)
        f.show()
        self.qa.processEvents()
        return f

    def wait(self, ms):
        end = QtCore.QTime.currentTime().addMSecs(ms)
        while QtCore.QTime.currentTime() < end:
            self.qa.processEvents()
            QtCore.QThread.msleep(5)

    def test_fade_in_out_and_no_size_change(self):
        f = self.make()
        size = f.size()
        inner_geo = f.layout().itemAt(0).widget().geometry()
        self.assertEqual(f.glow, 0.0)
        f.set_on_air(True)
        self.wait(120)
        self.assertTrue(0.0 < f.glow < 1.0)      # mid-fade, not a snap
        self.wait(600)
        self.assertEqual(f.glow, 1.0)
        f.set_on_air(False)
        self.wait(120)
        self.assertTrue(0.0 < f.glow < 1.0)
        self.wait(900)
        self.assertEqual(f.glow, 0.0)
        self.assertEqual(f.size(), size)
        self.assertEqual(f.layout().itemAt(0).widget().geometry(), inner_geo)
        f.grab()  # paints at every glow level without error
        f.close()

    def test_same_state_does_not_restart(self):
        f = self.make()
        f.set_on_air(True)
        self.wait(700)
        f.set_on_air(True)
        self.assertIsNot(f._anim.state(), QtCore.QAbstractAnimation.Running)
        self.assertEqual(f.glow, 1.0)
        f.close()

    def test_rapid_toggles_settle_on_final_state(self):
        f = self.make()
        for i in range(25):
            f.set_on_air(i % 2 == 0)
            self.wait(10)
        f.set_on_air(True)
        self.wait(700)
        self.assertEqual(f.glow, 1.0)
        f.set_on_air(False)
        f.set_on_air(True)
        f.set_on_air(False)
        self.wait(900)
        self.assertEqual(f.glow, 0.0)
        self.assertFalse(f.on_air)
        f.close()

    def test_hidden_and_cleanup(self):
        f = self.make()
        f.set_on_air(True)
        self.wait(50)
        f.hide()
        self.assertEqual(f.glow, 1.0)
        self.assertIsNot(f._anim.state(), QtCore.QAbstractAnimation.Running)
        f.set_on_air(False)                       # while hidden: instant, no animation
        self.assertEqual(f.glow, 0.0)
        f.show()
        f.set_on_air(True)
        f.close()
        f.deleteLater()
        self.wait(50)

    def test_hide_before_init_complete_is_safe(self):
        # hideEvent can fire while Qt tears a widget down, before __init__ finished
        # assigning _anim. _stop_glow must not raise AttributeError (regression: "TvFrame object has no attribute '_anim'").
        f = theme.TvFrame.__new__(theme.TvFrame)
        f._stop_glow()  # no _anim in __dict__ yet; must be a no-op, not a crash
        f._glow = 0.0
        f.on_air = False
        f.update = lambda *a, **k: None   # hideEvent calls _set_glow -> update(); skip the C++ call on an unbuilt widget
        # exercise hide-path guards without the C++ super call on an un-built widget
        f._stop_glow(); f._set_glow(0.0)

    def test_no_animation_env(self):
        os.environ["REVELATELITE_NO_GLOW_ANIMATION"] = "1"
        try:
            f = self.make()
            f.set_on_air(True)
            self.assertEqual(f.glow, 1.0)
            f.close()
        finally:
            del os.environ["REVELATELITE_NO_GLOW_ANIMATION"]


if __name__ == "__main__":
    unittest.main()
