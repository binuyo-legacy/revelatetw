"""Look-only guarantees for the theme pass: tab order, layout, wiring and projection are unchanged."""
import os
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
try:
    from PyQt5 import QtWidgets
    from revelatelite import app as lite_app, theme, layout
except ImportError:  # pragma: no cover
    QtWidgets = None


@unittest.skipIf(QtWidgets is None, "PyQt5 not installed")
class ThemeLook(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qa = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        cls.qa.setStyleSheet(lite_app.QSS)

    def make(self):
        d = tempfile.mkdtemp()
        lite_app.paths.user_dir = lambda: d
        w = lite_app.Main()
        w.st["transition_ms"] = 0
        w.resize(1100, 720)
        w.show()
        return w

    def test_tab_order_unchanged(self):
        w = self.make()
        tabs = w.findChild(QtWidgets.QTabWidget)
        self.assertEqual([tabs.tabText(i) for i in range(tabs.count())],
                         ["Service list", "Search words", "Songs", "Timer", "Settings"])

    def test_stylesheet_builds_and_covers_controls(self):
        q = theme.build_qss()
        for sel in ("QPushButton#primary", "QTabBar::tab:selected", "QScrollBar:vertical", "QLineEdit:focus",
                    "QListWidget::item:selected", "QFrame#card", "QCheckBox::indicator:checked"):
            self.assertIn(sel, q)
        self.assertEqual(q.count("{"), q.count("}"))

    def test_tv_frame_is_cosmetic_around_preview(self):
        w = self.make()
        self.qa.processEvents()
        self.assertIs(w.preview.parentWidget(), w.tv_frame)
        # preview keeps its exact 16:9 shape and height-for-width rule inside the bezel
        self.assertEqual(w.preview.heightForWidth(640), layout.height_for_width(640))
        pw, ph = w.preview.width(), w.preview.height()
        self.assertLessEqual(abs(ph - layout.height_for_width(pw)), 2)
        m = theme.TvFrame.BEZEL
        self.assertEqual(w.tv_frame.layout().contentsMargins().left(), m)
        # projection window is not wrapped or styled by the frame
        self.assertNotIsInstance(w.proj.parentWidget(), theme.TvFrame)

    def test_frame_follows_live_state_only(self):
        w = self.make()
        w.lookup("John 3:16")
        self.assertFalse(w.proj.isVisible())
        self.assertFalse(w.tv_frame.on_air)
        w.project()
        self.assertTrue(w.tv_frame.on_air)
        shown = w.slide
        w.blank()
        self.assertFalse(w.tv_frame.on_air)
        self.assertEqual(w.slide, shown)          # Project Off leaves operator state alone

    def test_preview_only_until_project(self):
        w = self.make()
        w.lookup("John 3:16")
        self.assertFalse(w.proj.isVisible())
        self.assertTrue(w.preview.body)
        self.assertTrue(w.project_b.isEnabled())

    def test_key_buttons_keep_order_in_layout(self):
        w = self.make()
        right = w.prev_b.parentWidget()
        names = [b.text() for b in right.findChildren(QtWidgets.QPushButton)
                 if b in (w.prev_b, w.next_b, w.add_b, w.blank_b, w.project_b)]
        self.assertEqual(set(names), {"< Previous", "Next >", "Add to service list", "Project Off (Esc)", "Project (F1)"})
        ys = [w.prev_b.mapTo(w, w.prev_b.rect().topLeft()).y(), w.add_b.mapTo(w, w.add_b.rect().topLeft()).y()]
        self.assertEqual(ys, sorted(ys))
        # Project / Project Off now live in the middle stack, not under the preview
        self.assertIs(w.project_b.parentWidget(), w.up_b.parentWidget())
        self.assertLess(w.project_b.y(), w.blank_b.y())

    def test_signals_still_wired(self):
        w = self.make()
        w.lookup("John 3:16")
        n = len(w.services.items) if hasattr(w.services, "items") else None
        w.add_b.click()
        if n is not None:
            self.assertEqual(len(w.services.items), n + 1)
        before = w.cur
        w.next_b.click()
        self.assertNotEqual(w.cur, before)
        w.prev_b.click()
        self.assertEqual(w.cur, before)


if __name__ == "__main__":
    unittest.main()
