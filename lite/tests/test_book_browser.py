"""Bible book browser (Service list tab). Headless Qt. Run: python -m pytest lite/tests/test_book_browser.py
Not a Windows 8.1 hardware check."""
import os
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from revelatelite.bible import BibleStore  # noqa: E402
from revelatetw.books import BOOKS  # noqa: E402

try:
    from PyQt5 import QtCore, QtTest, QtWidgets
    from revelatelite import app as lite_app, booklist
except ImportError:  # pragma: no cover
    QtWidgets = None

STORE = BibleStore()
TRS = STORE.translations()
OT = [b.name for b in BOOKS[:39]]
NT = [b.name for b in BOOKS[39:]]


def make_window(test, w=1000, h=640):
    from revelatelite import paths
    d = tempfile.mkdtemp()
    paths.user_dir = lambda: d
    lite_app.paths.user_dir = lambda: d
    win = lite_app.Main()
    test.addCleanup(win.close)
    win.resize(w, h)
    win.show()
    win.activateWindow()
    test.qa.processEvents()
    return win


def pick(win, name):
    for i in range(win.book_browser.count()):
        if win.book_browser.item(i).text() == name:
            win.book_browser._clicked(win.book_browser.item(i))
            QtWidgets.QApplication.processEvents()
            return
    raise AssertionError(name + " not listed")


@unittest.skipIf(QtWidgets is None or not TRS, "PyQt5 or Bible packs missing")
class BookBrowser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qa = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        cls.qa.setStyleSheet(lite_app.QSS)

    def test_grouping_helper_and_headings(self):
        old, new = booklist.grouped(range(1, 67))
        self.assertEqual((len(old), len(new)), (39, 27))
        w = make_window(self)
        self.assertEqual(w.book_browser.headings(), ["OLD TESTAMENT", "NEW TESTAMENT"])

    def test_every_translation_lists_all_books_grouped(self):
        w = make_window(self)
        for t in TRS:
            w.trans.setCurrentIndex(w.trans.findData(t))
            self.qa.processEvents()
            have = set(STORE.available_books(t))
            rows = w.book_browser.books()
            self.assertEqual([n for k, _b, n in rows if k == "OT"], [n for i, n in enumerate(OT, 1) if i in have], t)
            self.assertEqual([n for k, _b, n in rows if k == "NT"], [n for i, n in enumerate(NT, 40) if i in have], t)
            if len(have) == 66:
                self.assertEqual(len(rows), 66)
        self.assertIn("1 John", [n for _k, _b, n in w.book_browser.books()])

    def test_missing_books_are_omitted_and_refresh_on_version_change(self):
        w = make_window(self)
        missing = {"s": None}
        orig = BibleStore.available_books
        BibleStore.available_books = lambda self, t: [b for b in orig(self, t) if b not in (31, 64)] if t == TRS[-1] else orig(self, t)
        self.addCleanup(setattr, BibleStore, "available_books", orig)
        w.trans.setCurrentIndex(w.trans.findData(TRS[0]))
        self.qa.processEvents()
        names = [n for _k, _b, n in w.book_browser.books()]
        self.assertIn("Obadiah", names)
        self.assertIn("3 John", names)
        if len(TRS) > 1:
            w.trans.setCurrentIndex(w.trans.findData(TRS[-1]))
            self.qa.processEvents()
            names = [n for _k, _b, n in w.book_browser.books()]
            self.assertNotIn("Obadiah", names)
            self.assertNotIn("3 John", names)
            self.assertEqual(len(names), 64)
            self.assertIn("1 John", names)

    def test_click_inserts_book_focuses_and_ready_for_chapter(self):
        w = make_window(self)
        pick(w, "1 John")
        self.assertEqual(w.box.text(), "1 John ")
        self.assertTrue(w.box.hasFocus())
        self.assertEqual(w.box.cursorPosition(), len(w.box.text()))
        self.assertFalse(w.box.hasSelectedText())
        QtTest.QTest.keyClicks(w.box, "3")
        self.assertEqual(w.box.text(), "1 John 3")
        QtTest.QTest.keyClicks(w.box, ":16")
        QtTest.QTest.keyClick(w.box, QtCore.Qt.Key_Return)
        self.qa.processEvents()
        self.assertEqual(w.cur[:4], (62, 3, 16, 16))
        self.assertEqual(w.box.text(), "1 John 3:16")

    def test_after_book_click_highlight_navigation_continues(self):
        w = make_window(self)
        pick(w, "John")
        QtTest.QTest.keyClicks(w.box, "3")
        QtTest.QTest.keyClick(w.box, QtCore.Qt.Key_Right)       # existing jump into a part
        self.qa.processEvents()
        self.assertEqual(w.cur[:2], (43, 3))
        self.assertEqual(w.box.segment(), "verse")
        QtTest.QTest.keyClicks(w.box, "16")
        self.assertEqual(w.box.text(), "John 3:16")

    def test_click_over_existing_verse_replaces_book_without_changing_preview(self):
        w = make_window(self)
        w.lookup("Romans 8:28")
        before_cur, before_slide = w.cur, w.slide
        pick(w, "Genesis")
        self.assertEqual(w.box.text(), "Genesis ")
        self.assertTrue(w.box.hasFocus())
        self.assertEqual(w.cur, before_cur)
        self.assertEqual(w.slide, before_slide)
        QtTest.QTest.keyClicks(w.box, "1:3")
        QtTest.QTest.keyClick(w.box, QtCore.Qt.Key_Return)
        self.qa.processEvents()
        self.assertEqual(w.cur[:4], (1, 1, 3, 3))

    def test_click_never_projects(self):
        w = make_window(self)
        w.lookup("John 3:16")
        calls = []
        w.project = lambda *a, **k: calls.append(1)
        shown = getattr(w, "proj", None)
        pick(w, "Psalms")
        self.assertEqual(calls, [])
        self.assertEqual(w.cur[:4], (43, 3, 16, 16))
        self.assertEqual(getattr(w, "proj", None), shown)

    def test_headings_fully_visible_at_normal_size(self):
        # NEW TESTAMENT (and OLD TESTAMENT) must not elide at their normal bold size: the
        # browser was widened leftwards for exactly this, so the heading font/metrics are
        # measured as they are, with no shrinking. Qt elides to the viewport width.
        from PyQt5 import QtGui
        w = make_window(self)
        bb = w.book_browser
        viewport_w = bb.viewport().width()
        for text in ("OLD TESTAMENT", "NEW TESTAMENT"):
            item = next(bb.item(i) for i in range(bb.count()) if bb.item(i).text() == text)
            fm = QtGui.QFontMetrics(item.font())
            self.assertTrue(item.font().bold(), text)
            self.assertLessEqual(fm.horizontalAdvance(text), viewport_w, text)
            self.assertEqual(fm.elidedText(text, bb.textElideMode(), viewport_w), text, text)
            # the widest book name must fit too (no elided book rows either)
        for _k, _b, name in bb.books():
            fm = QtGui.QFontMetrics(bb.font())
            self.assertLessEqual(fm.horizontalAdvance(name), viewport_w, name)

    def test_layout_compact_vertical_only_and_neighbours_intact(self):
        w = make_window(self)
        bb = w.book_browser
        self.assertEqual(bb.horizontalScrollBarPolicy(), QtCore.Qt.ScrollBarAlwaysOff)
        self.assertFalse(bb.horizontalScrollBar().isVisible())
        self.assertTrue(bb.verticalScrollBar().isVisible() or bb.verticalScrollBar().maximum() > 0)
        self.assertEqual(bb.width(), booklist.WIDTH)
        self.assertEqual(booklist.WIDTH, 200)  # widened leftwards from 150 so NEW TESTAMENT fits
        r = lambda o: o.mapTo(w, o.rect().topLeft())
        self.assertLess(r(w.service_list).x() + w.service_list.width(), r(bb).x() + 1)
        self.assertLessEqual(r(bb).x() + bb.width(), r(w.up_b).x())
        self.assertGreaterEqual(r(w.up_b).x() - (r(bb).x() + bb.width()), 1)  # right stack untouched, gap kept
        self.assertGreaterEqual(w.service_list.width(), 210)
        self.assertEqual((w.up_b.width(), w.project_b.width()), (w.rm_b.width(), w.down_b.width()))
        self.assertLessEqual(w.preview.mapTo(w, w.preview.rect().bottomRight()).y(), r(bb).y() + bb.height())
        self.assertEqual(w.size().width(), 1000)

    def test_preview_size_unchanged_by_browser(self):
        # (the preview height already shifts by a pixel or more with the credit line of some
        # translations, before this feature; so size is checked across book clicks, and width across versions)
        w = make_window(self)
        s = w.preview.size()
        for name in ("Mark", "1 John", "Genesis"):
            pick(w, name)
            self.assertEqual(w.preview.size(), s)
        for t in TRS:
            w.trans.setCurrentIndex(w.trans.findData(t))
            self.qa.processEvents()
            self.assertEqual(w.preview.width(), s.width())
            self.assertFalse(w.book_browser.horizontalScrollBar().isVisible())


if __name__ == "__main__":
    unittest.main()
