"""Quick-bar tests: the Service list and Songs quick controls mirror Settings.

They run offscreen and only check sync, persistence and safety. They CANNOT show
the bar looks right on a real Windows 8.1 PC. Run: python -m pytest lite/tests/test_quickbar.py
"""
import json
import os
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from revelatelite import songthemes, transitions as trn
try:
    from PyQt5 import QtWidgets
    from revelatelite import app as lite_app
    from revelatelite import tabanimate
except ImportError:  # pragma: no cover
    QtWidgets = None


@unittest.skipIf(QtWidgets is None, "PyQt5 not installed")
class WithQt(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qa = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        cls.qa.setStyleSheet(lite_app.QSS)

    def make(self, **st):
        from revelatelite import paths
        d = tempfile.mkdtemp()
        self._old = paths.user_dir
        paths.user_dir = lambda: d
        lite_app.paths.user_dir = lambda: d
        w = lite_app.Main()
        w.st.update(st)
        return w

    def tearDown(self):
        self.w.proj.hide()
        self.w.close()
        from revelatelite import paths
        paths.user_dir = self._old
        lite_app.paths.user_dir = self._old

    def saved(self, w):
        with open(w.settings_path) as f:
            return json.load(f)

    def setUp(self):
        self.w = self.make()

    def test_both_bars_exist_with_shared_controls(self):
        w = self.w
        for bar in (w.qsvc, w.qsong):
            self.assertIsNotNone(bar)
        self.assertEqual(w.qsvc_tfx.count(), len(trn.EFFECT_KEYS))
        self.assertEqual(w.qsong_tfx.count(), len(trn.EFFECT_KEYS))
        self.assertEqual(w.qsong_theme.count(), len(songthemes.KEYS))
        self.assertTrue(w.qsvc.isAncestorOf(w.qsvc_tfx))
        self.assertTrue(w.qsong.isAncestorOf(w.qsong_theme))

    def test_service_bar_change_syncs_settings_and_songs_bar_and_saves(self):
        w = self.w
        w.qsvc_tfx.setCurrentIndex(w.qsvc_tfx.findData("slide"))
        w.qsvc_ms.setValue(650)
        w.qsvc_dir.setCurrentIndex(w.qsvc_dir.findData("down"))
        saved = self.saved(w)
        self.assertEqual((saved["transition_effect"], saved["transition_ms"], saved["transition_dir"]),
                         ("slide", 650, "down"))
        self.assertEqual(w.tfx_cb.currentData(), "slide")
        self.assertEqual(w.qsong_tfx.currentData(), "slide")
        self.assertEqual(w.tms_sp.value(), 650)
        self.assertEqual(w.qsong_ms.value(), 650)
        self.assertFalse(w.proj.isVisible())

    def test_song_bar_change_syncs_settings_and_saves(self):
        w = self.w
        w.qsong_tfx.setCurrentIndex(w.qsong_tfx.findData("wipe"))
        w.qsong_ms.setValue(800)
        saved = self.saved(w)
        self.assertEqual((saved["transition_effect"], saved["transition_ms"]), ("wipe", 800))
        self.assertEqual(w.tfx_cb.currentData(), "wipe")
        self.assertEqual(w.qsvc_tfx.currentData(), "wipe")
        self.assertFalse(w.proj.isVisible())

    def test_settings_change_resyncs_both_bars(self):
        w = self.w
        w.tfx_cb.setCurrentIndex(w.tfx_cb.findData("mosaic"))
        self.assertEqual(w.qsvc_tfx.currentData(), "mosaic")
        self.assertEqual(w.qsong_tfx.currentData(), "mosaic")
        w.tms_sp.setValue(250)
        self.assertEqual(w.qsvc_ms.value(), 250)
        self.assertEqual(w.qsong_ms.value(), 250)
        w.tdir_cb.setCurrentIndex(w.tdir_cb.findData("right"))
        self.assertEqual(w.qsvc_dir.currentData(), "right")
        self.assertEqual(w.qsong_dir.currentData(), "right")

    def test_song_theme_only_in_songs_bar_and_syncs_settings(self):
        w = self.w
        w.qsong_theme.setCurrentIndex(w.qsong_theme.findData("sunrise"))
        saved = self.saved(w)
        self.assertEqual(saved["song_theme"], "sunrise")
        self.assertEqual(w.song_theme_lw.currentRow(), songthemes.KEYS.index("sunrise"))
        # Service list quick bar has no song theme control
        self.assertFalse(hasattr(w, "qsvc_theme"))
        # and the other way: Settings gallery row change reaches the Songs bar
        w.song_theme_lw.setCurrentRow(songthemes.KEYS.index("royal"))
        self.assertEqual(w.qsong_theme.currentData(), "royal")

    def test_monitor_selection_syncs_all_three(self):
        w = self.w
        # only one screen in CI: both combos hold Automatic + the primary entry
        self.assertEqual(w.display_cb.count(), w.qsvc_display.count())
        self.assertEqual(w.display_cb.count(), w.qsong_display.count())
        self.assertEqual(w.display_cb.currentData(), w.qsvc_display.currentData())
        if w.display_cb.count() > 1:
            w.qsvc_display.setCurrentIndex(1)
            self.assertEqual(w.display_cb.currentIndex(), 1)
            self.assertEqual(w.qsong_display.currentIndex(), 1)
            saved = self.saved(w)
            self.assertEqual(saved["display"], w.display_cb.currentData())
        self.assertFalse(w.proj.isVisible())

    def test_tab_order_unchanged(self):
        tabs = self.w.findChild(tabanimate.AnimatedTabWidget)
        self.assertEqual([tabs.tabText(i) for i in range(tabs.count())],
                         ["Service list", "Search words", "Songs", "Settings"])

    def test_quick_controls_never_project(self):
        w = self.w
        w.qsvc_tfx.setCurrentIndex(3)
        w.qsong_theme.setCurrentIndex(2)
        w.qsvc_ms.setValue(700)
        self.assertFalse(w.proj.isVisible())


if __name__ == "__main__":
    unittest.main()
