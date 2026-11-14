"""Tab slide + page fade animations (offscreen Qt). Run: python -m pytest lite/tests/test_tab_animation.py"""
import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.dirname(__file__))
try:
    from PyQt5 import QtWidgets, QtCore, QtGui
    from revelatelite import app as lite_app, tabanimate
    import test_quick_controls as _tqc
except ImportError:  # pragma: no cover
    QtWidgets = None


@unittest.skipIf(QtWidgets is None, "PyQt5 not installed")
class TabAnimation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qa = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        cls.qa.setStyleSheet(lite_app.QSS)

    def make(self):
        b = _tqc.QuickControls("test_tab_order_and_default_size_untouched")
        b.qa = self.qa
        return b.make()

    def wait(self, ms=400):
        end = QtCore.QTime.currentTime().addMSecs(ms)
        while QtCore.QTime.currentTime() < end:
            self.qa.processEvents()
            QtCore.QThread.msleep(5)

    def geom(self, w):
        tb = w.tabs.tabBar()
        return ([tb.tabRect(i) for i in range(tb.count())], w.quick_host.geometry(), w.tabs.geometry(),
                w.preview.geometry() if hasattr(w, "preview") else None)

    def test_animation_starts_and_finishes(self):
        w = self.make()
        tb = w.tabs.tabBar()
        w.tabs.setCurrentIndex(2)
        self.assertTrue(tb.sliding())
        self.assertTrue(w.tabs.fading())
        self.assertIsNotNone(w.tabs.currentWidget().graphicsEffect())
        self.wait()
        self.assertFalse(tb.sliding())
        self.assertFalse(w.tabs.fading())
        self.assertIsNone(w.tabs.widget(2).graphicsEffect())      # effect removed, page fully opaque
        w.close()

    def test_slide_paints_without_error_and_final_matches_plain(self):
        w = self.make()
        tb = w.tabs.tabBar()
        w.tabs.setCurrentIndex(3)
        for _ in range(5):
            self.qa.processEvents()
            tb.grab()
            QtCore.QThread.msleep(30)
        self.wait()
        self.assertEqual(tb.grab().toImage(), QtWidgets.QTabBar.grab(tb).toImage())
        self.assertEqual(w.tabs.currentIndex(), 3)
        w.close()

    def test_rapid_switching_is_stable(self):
        w = self.make()
        for n in range(60):
            w.tabs.setCurrentIndex(n % 4)
            if n % 3 == 0:
                self.qa.processEvents()
        w.tabs.setCurrentIndex(1)
        self.wait()
        self.assertEqual(w.tabs.currentIndex(), 1)
        self.assertFalse(w.tabs.tabBar().sliding())
        for i in range(4):
            self.assertIsNone(w.tabs.widget(i).graphicsEffect())
        self.assertEqual([w.tabs.tabText(i) for i in range(4)], ["Service list", "Search words", "Songs", "Settings"])
        w.close()

    def test_resize_mid_animation(self):
        w = self.make()
        w.tabs.setCurrentIndex(2)
        self.assertTrue(w.tabs.tabBar().sliding())
        w.resize(1100, 700)
        self.qa.processEvents()
        self.assertFalse(w.tabs.tabBar().sliding())
        self.assertFalse(w.tabs.fading())
        w.tabs.setCurrentIndex(0)
        w.resize(900, 600)
        w.resize(1000, 640)
        self.wait()
        self.assertIsNone(w.tabs.widget(0).graphicsEffect())
        self.assertEqual(w.tabs.currentIndex(), 0)
        w.close()

    def test_wrapper_lifetime_after_finish(self):
        w = self.make()
        tb = w.tabs.tabBar()
        for i in (1, 2, 3, 0, 2):
            w.tabs.setCurrentIndex(i)
            self.wait(260)
        # the same animation objects are reused and still alive (no "wrapped C/C++ object deleted")
        self.assertEqual(tb._anim.state(), QtCore.QAbstractAnimation.Stopped)
        self.assertEqual(w.tabs._fade.state(), QtCore.QAbstractAnimation.Stopped)
        self.assertEqual(tb._anim.duration(), tabanimate.SLIDE_MS)
        w.tabs.setCurrentIndex(1)
        self.assertTrue(tb.sliding())
        self.wait()
        import gc
        gc.collect()
        self.qa.processEvents()
        w.tabs.setCurrentIndex(3)
        self.wait()
        self.assertEqual(w.tabs.currentIndex(), 3)
        w.close()

    def test_close_during_animation_and_hidden(self):
        w = self.make()
        w.tabs.setCurrentIndex(2)
        w.close()
        self.qa.processEvents()
        self.wait(250)
        w2 = self.make()
        w2.tabs.setCurrentIndex(1)
        w2.hide()
        self.assertFalse(w2.tabs.tabBar().sliding())
        self.assertFalse(w2.tabs.fading())
        w2.tabs.setCurrentIndex(3)       # hidden: switches instantly, no animation started
        self.assertFalse(w2.tabs.tabBar().sliding())
        self.assertIsNone(w2.tabs.widget(3).graphicsEffect())
        w2.close()

    def test_disabled_tabs_do_not_animate(self):
        w = self.make()
        w.tabs.setEnabled(False)
        w.tabs.setCurrentIndex(2)
        self.assertFalse(w.tabs.tabBar().sliding())
        self.assertFalse(w.tabs.fading())
        w.tabs.setEnabled(True)
        w.close()

    def test_opt_out_env_is_explicit(self):
        os.environ["REVELATELITE_NO_TAB_ANIMATION"] = "1"
        try:
            w = self.make()
            w.tabs.setCurrentIndex(2)
            self.assertFalse(w.tabs.tabBar().sliding())
            w.close()
        finally:
            del os.environ["REVELATELITE_NO_TAB_ANIMATION"]

    def test_layout_unchanged_by_animation_and_no_bottom_indicator(self):
        w = self.make()
        self.assertEqual((w.width(), w.height()), (1000, 640))
        base = {}
        for i in (0, 1, 2, 3):                      # settled layout per tab, animations finished
            w.tabs.setCurrentIndex(i)
            self.wait(260)
            base[i] = self.geom(w)
        for i in (2, 1, 0, 3, 0):
            w.tabs.setCurrentIndex(i)
            self.qa.processEvents()
            self.assertEqual(self.geom(w), base[i])  # mid-animation: tabs, quick bar, tab widget, preview identical
            self.wait(260)
            self.assertEqual(self.geom(w), base[i])
        tb = w.tabs.tabBar()
        self.assertEqual([c for c in tb.findChildren(QtWidgets.QWidget) if not isinstance(c, QtWidgets.QToolButton)], [])  # no overlay widget (only Qt's own scroll arrows)
        # tab row only: quick controls right of tabs, nothing under the row
        w.tabs.setCurrentIndex(2)
        self.wait()
        host = w.quick_host
        self.assertTrue(host.isVisible())
        self.assertGreaterEqual(host.x(), tb.x() + tb.tabRect(3).right())
        pane_top = w.tabs.currentWidget().mapTo(w.tabs, QtCore.QPoint(0, 0)).y()
        self.assertLessEqual(host.y() + host.height(), pane_top)
        self.assertEqual(len(w.quick_controls[2]), 3)
        w.close()

    def test_selected_tab_keeps_gold_top_border_and_stylesheet(self):
        w = self.make()
        self.assertIn("QTabBar::tab:selected{background:#161c2a;color:#facc15;border-color:#2a3346;border-top:2pxsolid#facc15;}",
                      lite_app.QSS.replace(" ", "").replace("\n", ""))
        tb = w.tabs.tabBar()
        w.tabs.setCurrentIndex(1)
        self.wait()
        img = tb.grab().toImage()
        r = tb.tabRect(1)
        gold = QtGui.QColor(img.pixel(r.center().x(), r.top() + 1))
        other = QtGui.QColor(img.pixel(tb.tabRect(0).center().x(), tb.tabRect(0).top() + 1))
        self.assertNotEqual(gold.name(), other.name())          # selected tab top border differs (gold)
        w.close()

    def test_tab_switch_keeps_settings_sync(self):
        w = self.make()
        w.tabs.setCurrentIndex(0)
        w.q_sl_effect.setCurrentIndex(2)
        w.q_sl_effect.activated.emit(2)
        self.wait(60)
        w.tabs.setCurrentIndex(2)
        self.wait(250)
        self.assertEqual(w.q_sg_effect.currentData(), w.q_sl_effect.currentData())
        w.close()


if __name__ == "__main__":
    unittest.main()
