"""Quick controls in the tab-bar row (offscreen Qt). Run: python lite\\tests\\test_quick_controls.py"""
import json
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
class QuickControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qa = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        cls.qa.setStyleSheet(lite_app.QSS)

    def make(self, st=None):
        from revelatelite import paths
        d = tempfile.mkdtemp()
        paths.user_dir = lambda: d
        lite_app.paths.user_dir = lambda: d
        if st:
            with open(os.path.join(d, "settings.json"), "w") as f:
                json.dump(st, f)
        w = lite_app.Main()
        w.dir = d
        w.show()
        self.qa.processEvents()
        return w

    def saved(self, w):
        with open(os.path.join(w.dir, "settings.json")) as f:
            return json.load(f)

    def go(self, w, i):
        w.tabs.setCurrentIndex(i)
        self.qa.processEvents()

    def test_tab_order_and_default_size_untouched(self):
        w = self.make()
        names = [w.tabs.tabText(i) for i in range(w.tabs.count())]
        self.assertEqual(names, ["Service list", "Search words", "Songs", "Settings"])
        self.assertEqual((w.width(), w.height()), (1000, 640))     # no forced maximize / resize

    def test_toolbar_is_in_tab_row_right_of_tabs(self):
        w = self.make()
        tb = w.tabs.tabBar()
        for i in (0, 2):
            self.go(w, i)
            host = w.quick_host
            self.assertTrue(host.isVisible())
            top = host.mapTo(w.tabs, QtCore.QPoint(0, 0))
            tabs_right = tb.mapTo(w.tabs, QtCore.QPoint(tb.tabRect(w.tabs.count() - 1).right(), 0)).x()
            self.assertGreaterEqual(top.x(), tabs_right)                              # right of the tab buttons
            self.assertLessEqual(top.y() + host.height(), tb.height())                # inside the tab-bar row height
            self.assertLessEqual(top.x() + host.width(), w.tabs.width())              # inside the tab widget
            pane_top = w.tabs.currentWidget().mapTo(w.tabs, QtCore.QPoint(0, 0)).y()
            self.assertLessEqual(top.y() + host.height(), pane_top)                   # nothing under the row

    def test_exactly_three_controls_per_context(self):
        w = self.make()
        for i in (0, 2):
            self.go(w, i)
            vis = [c for c in w.quick_host.findChildren(QtWidgets.QWidget) if c.isVisible() and
                   isinstance(c, (QtWidgets.QComboBox, QtWidgets.QAbstractButton, QtWidgets.QAbstractSpinBox))]
            self.assertEqual(len(vis), 3, i)
            self.assertEqual(len(w.quick_controls[i]), 3)
        self.go(w, 1)
        self.assertEqual(w.quick_host.width(), 0 if not w.quick_host.isVisible() else w.quick_host.width())
        self.assertFalse([c for c in w.quick_host.findChildren(QtWidgets.QComboBox) if c.isVisible()])

    def test_narrow_widths_and_no_layout_growth(self):
        w = self.make()
        for i in (0, 2):
            self.go(w, i)
            for c in w.quick_controls[i]:
                self.assertLessEqual(c.width(), 70)
            self.assertLessEqual(w.quick_host.width(), 200)
        # even with the longest item text, controls keep their width (they never grow to the longest item)
        self.go(w, 0)
        before = [c.width() for c in w.quick_controls[0]]
        w.q_sl_screen.addItem("Screen 9: 3840x2160 and a very long name", 9)
        self.qa.processEvents()
        self.assertEqual(before, [c.width() for c in w.quick_controls[0]])
        # the toolbar leaves the tab bar at its natural width
        self.assertEqual(w.tabs.tabBar().width(), w.tabs.tabBar().sizeHint().width())

    def test_preview_and_pane_sizes_unchanged_by_toolbar(self):
        w = self.make()
        self.go(w, 0)
        pane = w.tabs.currentWidget().height()
        pv = (w.preview.width(), w.preview.height())
        w.quick_host.hide()
        self.qa.processEvents()
        self.assertEqual(pane, w.tabs.currentWidget().height())
        self.assertEqual(pv, (w.preview.width(), w.preview.height()))
        self.assertEqual(w.preview.height() * 16 // 9, w.preview.height() * 16 // 9)

    def test_hidden_when_window_too_narrow_tabs_unaffected(self):
        w = self.make()
        w.resize(700, 640)
        self.qa.processEvents()
        self.go(w, 0)
        if w.tabs.width() < w.tabs.tabBar().sizeHint().width() + w.quick_host.width() + 6:
            self.assertFalse(w.quick_host.isVisible())
        self.assertEqual(w.tabs.tabBar().width(), w.tabs.tabBar().sizeHint().width())

    def test_service_quick_sets_settings_and_persists(self):
        w = self.make()
        k = w.q_sl_effect.findData("wipe")
        w.q_sl_effect.setCurrentIndex(k)
        w.q_sl_effect.activated.emit(k)
        self.assertEqual(w.tfx_cb.currentData(), "wipe")
        self.assertEqual(w.st["transition_effect"], "wipe")
        self.assertEqual(self.saved(w)["transition_effect"], "wipe")
        self.assertEqual(w.q_sg_effect.currentData(), "wipe")          # Songs copy follows
        k = w.q_sl_speed.findData(800)
        w.q_sl_speed.activated.emit(k)
        self.assertEqual((w.tms_sp.value(), self.saved(w)["transition_ms"]), (800, 800))
        w.q_sl_screen.addItem("Scr 7", 7)       # a screen that does not exist is simply not offered by the Settings list
        w.q_sl_screen.activated.emit(w.q_sl_screen.count() - 1)
        self.assertEqual(w.st["display"], w.display_cb.currentData())
        w.q_sl_effect.setCurrentIndex(w.q_sl_effect.findData("cut"))
        w.q_sl_effect.activated.emit(w.q_sl_effect.findData("cut"))
        self.assertFalse(w.q_sl_speed.isEnabled())                     # instant: speed has no meaning

    def test_settings_changes_update_quick_controls(self):
        w = self.make()
        w.tfx_cb.setCurrentIndex(w.tfx_cb.findData("iris"))
        self.assertEqual(w.q_sl_effect.currentData(), "iris")
        w.tms_sp.setValue(1500)
        self.assertEqual(w.q_sl_speed.currentData(), 1500)
        w.tms_sp.setValue(650)                                          # odd value is shown, not lost
        self.assertEqual(w.q_sl_speed.currentData(), 650)
        w.song_theme_lw.setCurrentRow(2)
        self.assertEqual(w.q_sg_style.currentData(), "classic")

    def test_songs_style_and_size(self):
        w = self.make()
        self.assertFalse(w.q_sg_size.isEnabled())                       # Standard has nothing to size
        k = w.q_sg_style.findData("royal")
        w.q_sg_style.activated.emit(k)
        self.assertEqual(w.st["song_theme"], "royal")
        self.assertEqual(self.saved(w)["song_theme"], "royal")
        self.assertEqual(w.song_theme_lw.currentRow(), songthemes_index("royal"))
        self.assertTrue(w.q_sg_size.isEnabled())
        w.q_sg_size.activated.emit(w.q_sg_size.findData(120))
        self.assertEqual(w.sc_scale_sp.value(), 120)
        self.assertEqual(self.saved(w)["song_custom"]["royal"]["scale"], 120)
        self.assertEqual(w.q_sg_size.currentData(), 120)
        w._sc_reset()
        self.assertNotIn("royal", self.saved(w)["song_custom"])
        self.assertEqual(w.q_sg_size.currentData(), w.sc_scale_sp.value())

    def test_startup_reads_saved_settings(self):
        w = self.make({"transition_effect": "zoom", "transition_ms": 800, "song_theme": "sunrise"})
        self.assertEqual(w.q_sl_effect.currentData(), "zoom")
        self.assertEqual(w.q_sl_speed.currentData(), 800)
        self.assertEqual(w.q_sg_style.currentData(), "sunrise")

    def test_selected_tab_gold_top_style_kept(self):
        self.assertIn("QTabBar::tab:selected", lite_app.QSS)
        self.assertIn("border-top:2px solid", lite_app.QSS.split("QTabBar::tab:selected")[1].split("}")[0])
        for bad in ("QPropertyAnimation", "QVariantAnimation"):
            self.assertNotIn(bad, open(lite_app.__file__, encoding="utf-8").read())


def songthemes_index(k):
    from revelatelite import songthemes
    return songthemes.KEYS.index(k)


if __name__ == "__main__":
    unittest.main()
