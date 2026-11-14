"""Settings page scrolls up/down only (offscreen Qt). Run: python lite\\tests\\test_settings_no_hscroll.py"""
import os
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
try:
    from PyQt5 import QtWidgets, QtCore
    from revelatelite import app as lite_app
except ImportError:  # pragma: no cover
    QtWidgets = None


@unittest.skipIf(QtWidgets is None, "PyQt5 not installed")
class SettingsNoHScroll(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qa = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        cls.qa.setStyleSheet(lite_app.QSS)

    def make(self, width=1000, height=640):
        from revelatelite import paths
        d = tempfile.mkdtemp()
        paths.user_dir = lambda: d
        lite_app.paths.user_dir = lambda: d
        w = lite_app.Main()
        w.resize(width, height)
        w.show()
        w.tabs.setCurrentIndex(3)
        self.qa.processEvents()
        return w

    def test_no_horizontal_scroll_at_startup_width(self):
        w = self.make()
        sc = w.settings_scroll
        self.assertEqual(sc.horizontalScrollBarPolicy(), QtCore.Qt.ScrollBarAlwaysOff)
        self.assertFalse(sc.horizontalScrollBar().isVisible())
        self.assertEqual(sc.horizontalScrollBar().maximum(), 0)
        self.assertLessEqual(sc.widget().minimumSizeHint().width(), sc.viewport().width())
        w.close()

    def test_no_horizontal_scroll_a_bit_narrower(self):
        w = self.make(900, 600)
        sc = w.settings_scroll
        self.assertEqual(sc.horizontalScrollBar().maximum(), 0)
        self.assertLessEqual(sc.widget().minimumSizeHint().width(), sc.viewport().width())
        w.close()

    def test_every_control_inside_width_and_reachable_by_vertical_scroll(self):
        w = self.make()
        sc = w.settings_scroll
        page = sc.widget()
        self.assertGreater(sc.verticalScrollBar().maximum(), 0)
        vw = sc.viewport().width()
        checked = 0
        for c in page.findChildren(QtWidgets.QWidget):
            if not isinstance(c, (QtWidgets.QComboBox, QtWidgets.QAbstractButton, QtWidgets.QAbstractSpinBox,
                                  QtWidgets.QListWidget)):
                continue
            if c.parent() is not None and isinstance(c.parent(), QtWidgets.QAbstractSpinBox):
                continue
            if not c.isVisibleTo(page):
                continue
            tl = c.mapTo(page, QtCore.QPoint(0, 0))
            self.assertGreaterEqual(tl.x(), 0, c)
            self.assertLessEqual(tl.x() + c.width(), vw, c)
            sc.ensureWidgetVisible(c)
            self.qa.processEvents()
            top = c.mapTo(sc.viewport(), QtCore.QPoint(0, 0)).y()
            self.assertTrue(-1 <= top <= sc.viewport().height(), c)
            checked += 1
        self.assertGreater(checked, 30)
        for name in ("pon_cb", "poff_cb", "verse_theme_lw", "song_theme_lw", "tfx_cb", "font_cb"):
            wid = getattr(w, name)
            self.assertLessEqual(wid.mapTo(page, QtCore.QPoint(wid.width(), 0)).x(), vw, name)
        w.close()

    def test_all_controls_still_exist_and_full_choices_kept(self):
        w = self.make()
        self.assertEqual(w.pon_cb.count(), w.tfx_cb.count())
        self.assertEqual(w.poff_cb.count(), w.tfx_cb.count())
        self.assertGreaterEqual(w.verse_theme_lw.count(), 7)
        self.assertTrue(w.tsw_cb.toolTip())
        w.close()

    def test_preview_tv_unchanged_size(self):
        w = self.make()
        before = (w.tv_frame.width(), w.tv_frame.height())
        w.tabs.setCurrentIndex(0)
        self.qa.processEvents()
        w.tabs.setCurrentIndex(3)
        self.qa.processEvents()
        self.assertEqual(before, (w.tv_frame.width(), w.tv_frame.height()))
        w.close()


if __name__ == "__main__":
    unittest.main()
