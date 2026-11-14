"""Tab animation tests. Offscreen Qt, quick and headless. They check the tab order,
the sliding pill and the content fade, plus rapid switching. They CANNOT show that
the motion looks smooth on a real Windows 8.1 PC. Run: python -m pytest lite/tests/test_tabanimate.py"""
import os
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

try:
    from PyQt5 import QtCore, QtWidgets
    from revelatelite import app as lite_app, tabanimate
except ImportError:  # pragma: no cover
    QtWidgets = None


@unittest.skipIf(QtWidgets is None, "PyQt5 not installed")
class TabAnimation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qa = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        cls.qa.setStyleSheet(lite_app.QSS)

    def make(self):
        d = tempfile.mkdtemp()
        lite_app.paths.user_dir = lambda: d
        w = lite_app.Main()
        w.resize(1100, 720)
        w.show()
        self.qa.processEvents()
        return w

    def _tabs(self, w):
        # Locate the tab strip the same way older tests do, independent of class.
        return w.findChild(QtWidgets.QTabWidget)

    def bars(self, w):
        tabs = self._tabs(w)
        return tabs, tabs.tabBar()

    def test_tab_order_and_widgets_unchanged(self):
        w = self.make()
        tabs = self._tabs(w)
        self.assertEqual([tabs.tabText(i) for i in range(tabs.count())],
                         ["Service list", "Search words", "Songs", "Settings"])
        self.assertEqual(tabs.count(), 4)
        self.assertEqual(tabs.currentIndex(), 0)
        # the animated strip is still a QTabWidget at heart
        self.assertTrue(isinstance(tabs, QtWidgets.QTabWidget))
        w.close()

    def test_no_bottom_indicator_and_no_layout_change(self):
        """Operator request: no extra gold strip under the selected label."""
        w = self.make()
        tabs, bar = self.bars(w)
        ind = bar.indicator()
        self.assertIsNotNone(ind)
        before = (tabs.geometry(), [tabs.widget(i).geometry() for i in range(tabs.count())])
        tabs.setCurrentIndex(1)
        self.qa.processEvents()
        after = (tabs.geometry(), [tabs.widget(i).geometry() for i in range(tabs.count())])
        self.assertEqual(before[0], after[0])
        # nothing gold paints at the bottom: rect empty, widget hidden
        self.assertEqual(ind._rect, QtCore.QRect())
        self.assertFalse(ind.isVisible())
        self.assertIsNone(ind._anim)
        w.close()

    def test_indicator_rect_is_empty_for_every_tab(self):
        w = self.make()
        tabs, bar = self.bars(w)
        for i in range(bar.count()):
            self.assertEqual(tabanimate.indicator_rect(bar, bar.tabRect(i)),
                             QtCore.QRect())
        self.assertEqual(tabanimate.indicator_rect(None, None), QtCore.QRect())
        w.close()

    def test_rapid_switching_never_gets_stuck(self):
        w = self.make()
        tabs = self._tabs(w)
        # fire many switches fast, like a hurried user
        for i in [1, 2, 3, 2, 1, 0, 3, 3, 0, 2, 1, 0]:
            tabs.setCurrentIndex(i)
            self.qa.processEvents()
        self.assertEqual(tabs.currentIndex(), 0)
        tabs.setCurrentIndex(2)
        self.qa.processEvents()
        self.assertEqual(tabs.currentIndex(), 2)
        # finish() restores the active page; only a leftover effect on a page that
        # is not the active one is a real problem (it would keep a stale opacity).
        current = tabs.widget(tabs.currentIndex())
        for i in range(tabs.count()):
            page = tabs.widget(i)
            if page is current:
                continue
            self.assertIsNone(page.graphicsEffect())
        # no bottom strip is painted after rapid switches
        bar = tabs.tabBar()
        bar.indicator().place_immediately(2)
        self.assertEqual(bar.indicator()._rect, QtCore.QRect())
        self.assertFalse(bar.indicator().isVisible())
        w.close()

    def test_current_changed_still_fires(self):
        w = self.make()
        tabs = self._tabs(w)
        seen = []
        tabs.currentChanged.connect(seen.append)
        tabs.setCurrentIndex(3)
        tabs.setCurrentIndex(1)
        self.qa.processEvents()
        self.assertEqual(seen, [3, 1])
        w.close()

    def test_rebuild_keeps_tab_order_after_signal_wiring(self):
        w = self.make()
        tabs, bar = self.bars(w)
        # selection by clicking the tab button itself (not just setCurrentIndex)
        bar.setCurrentIndex(2)
        self.qa.processEvents()
        self.assertEqual(tabs.currentIndex(), 2)
        bar.setCurrentIndex(0)
        self.qa.processEvents()
        self.assertEqual(tabs.currentIndex(), 0)
        w.close()

    def test_deleted_animation_wrapper_never_raises(self):
        """Regression: DeleteWhenStopped left self._anim pointing at a deleted C++
        wrapper; the next stop() in resizeEvent/place_immediately raised RuntimeError.
        The bottom pill is gone now, so _stop_anim must stay safe with no animation."""
        w = self.make()
        tabs, bar = self.bars(w)
        ind = bar.indicator()
        tabs.setCurrentIndex(1)
        self.qa.processEvents()
        self.assertIsNone(ind._anim)
        try:
            ind._stop_anim()
            ind.place_immediately(1)
            w.resize(1200, 800)
            self.qa.processEvents()
        except RuntimeError as e:
            self.fail("stop/place_immediately/resize raised: %r" % e)
        self.assertEqual(ind._rect, QtCore.QRect())
        w.close()

    def test_resize_during_animation_never_raises(self):
        """The exact crash path: resizeEvent -> move_to -> place_immediately -> _anim.stop()."""
        w = self.make()
        tabs, bar = self.bars(w)
        ind = bar.indicator()
        tabs.setCurrentIndex(2)
        self.qa.processEvents()
        # an animation is (or just was) running; force several resizes right after switches
        for i in [3, 1, 0, 2]:
            tabs.setCurrentIndex(i)
            w.resize(1300, 850)
            w.resize(1100, 720)
            self.qa.processEvents()
        # still no bottom strip
        ind.place_immediately(tabs.currentIndex())
        self.assertEqual(ind._rect, QtCore.QRect())
        self.assertFalse(ind.isVisible())
        w.close()

    def test_finished_animation_clears_its_reference(self):
        """Content fade finishes and restores the page; no stale wrapper."""
        w = self.make()
        tabs, bar = self.bars(w)
        ind = bar.indicator()
        tabs.setCurrentIndex(3)
        self.qa.processEvents()
        QtCore.QThread.msleep(tabanimate.CONTENT_MS + 100)
        self.qa.processEvents()
        self.assertIsNone(ind._anim)
        self.assertIsNone(tabs._fade._anim)
        self.assertEqual(ind._rect, QtCore.QRect())
        w.close()

    def test_top_gold_selected_tab_style_preserved(self):
        """Selected tab keeps gold top border + gold text from theme.py."""
        from revelatelite import theme
        qss = theme.build_qss()
        self.assertIn("QTabBar::tab:selected", qss)
        sel = [ln for ln in qss.splitlines() if "QTabBar::tab:selected" in ln][0]
        self.assertIn("border-top:2px solid", sel)
        # and nothing in theme.py paints a bottom strip on selected tabs
        self.assertNotIn("border-bottom:2px", sel)
        # no bottom-strip rule in the tab styling at all
        tab_lines = [ln for ln in qss.splitlines() if "QTabBar::tab" in ln]
        for ln in tab_lines:
            self.assertNotIn("border-bottom:2px solid", ln)
            self.assertNotIn("border-bottom:3px solid", ln)


if __name__ == "__main__":
    unittest.main()
