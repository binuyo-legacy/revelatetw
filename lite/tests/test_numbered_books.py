"""Numbered Bible books (1 Samuel, 1 John, ...) as ONE highlightable book component.

The ordinal prefix (1/2/3) is part of the book name, never a chapter number.
Typing "1" must offer the numbered books, the inline fill must complete them,
Left/Right must route to the book part (never verse), and book/chapter/verse
arrow navigation must highlight the whole "1 John" / "2 Thessalonians" name.

Headless (offscreen Qt); not a Windows 8.1 hardware check.
Run: python -m pytest lite/tests/test_numbered_books.py
"""
import os
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from revelatelite.bible import BibleStore, _has_chapter_number, _is_bare_ordinal, parse_reference, reference_spans, format_reference, suggest  # noqa: E402
from revelatetw.books import BOOKS  # noqa: E402

try:
    from PyQt5 import QtCore, QtTest, QtWidgets
    from revelatelite import app as lite_app
except ImportError:  # pragma: no cover
    QtWidgets = None

STORE = BibleStore()
TR = STORE.translations()[0] if STORE.translations() else None
NUMBERED = [b.name for b in BOOKS if b.name and b.name[0] in "123"]


def make_window(test):
    from revelatelite import paths
    d = tempfile.mkdtemp()
    paths.user_dir = lambda: d
    lite_app.paths.user_dir = lambda: d
    w = lite_app.Main()
    test.addCleanup(w.close)
    w.show()
    w.activateWindow()
    test.qa.processEvents()
    return w


@unittest.skipIf(TR is None, "no Bible packs")
class NumberedLogic(unittest.TestCase):
    def test_all_numbered_books_are_in_the_canon(self):
        # 1/2 Samuel, 1/2 Kings, 1/2 Chronicles, 1/2 Corinthians,
        # 1/2 Thessalonians, 1/2 Timothy, 1/2 Peter, 1/2/3 John.
        self.assertEqual(len(NUMBERED), 17)
        self.assertEqual(NUMBERED, ["1 Samuel", "2 Samuel", "1 Kings", "2 Kings",
                                    "1 Chronicles", "2 Chronicles", "1 Corinthians", "2 Corinthians",
                                    "1 Thessalonians", "2 Thessalonians", "1 Timothy", "2 Timothy",
                                    "1 Peter", "2 Peter", "1 John", "2 John", "3 John"])

    def test_bare_ordinal_is_a_book_not_a_chapter(self):
        for t in ("1", "2", "3", "1 ", "3."):
            self.assertTrue(_is_bare_ordinal(t), t)
            self.assertIsNone(parse_reference(t), t)
            self.assertFalse(_has_chapter_number(t), t)
        for t in ("1 John", "1 jo", "joh", "john"):
            self.assertFalse(_is_bare_ordinal(t), t)
            self.assertFalse(_has_chapter_number(t), t)

    def test_bare_ordinal_suggests_its_numbered_books(self):
        s = suggest("1", STORE, TR, 8)
        self.assertEqual(s, [n + " " for n in NUMBERED if n.startswith("1 ")][:8])
        self.assertIn("1 John ", s)
        self.assertIn("1 Samuel ", s)
        self.assertEqual(suggest("2", STORE, TR, 8)[:1], ["2 Samuel "])
        self.assertEqual(suggest("3", STORE, TR, 8), ["3 John "])
        self.assertEqual(suggest("1 ", STORE, TR, 8), suggest("1", STORE, TR, 8))

    def test_numbered_book_span_is_one_book_component(self):
        for name in NUMBERED:
            book = next(b.book_id for b in BOOKS if b.name == name)
            text = format_reference(book, 1, 1, 1)
            sp = reference_spans(book, 1, 1, 1)
            self.assertEqual(text[sp["book"][0]:sp["book"][1]], name, name)
            self.assertEqual(text[sp["chapter"][0]:sp["chapter"][1]], "1", name)

    def test_chapter_number_detection_for_numbered_books(self):
        self.assertTrue(_has_chapter_number("1 john 3"))
        self.assertTrue(_has_chapter_number("2 thessalonians 2"))
        self.assertTrue(_has_chapter_number("1 john 3:16"))
        self.assertTrue(_has_chapter_number("john 3"))
        self.assertFalse(_has_chapter_number("1 john"))

    def test_suggest_completed_numbered_book_gives_chapters(self):
        out = suggest("1 John ", STORE, TR)
        self.assertTrue(out and out[0].startswith("1 John 1:"))
        out = suggest("1 John 3", STORE, TR)
        self.assertEqual(out, ["1 John 3:"])
        out = suggest("1 John 3:1", STORE, TR)
        self.assertTrue(out and all(x.startswith("1 John 3:") for x in out))


@unittest.skipIf(QtWidgets is None or TR is None, "PyQt5 or Bible packs missing")
class NumberedKeys(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qa = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        cls.qa.setStyleSheet(lite_app.QSS)

    def _fresh(self):
        w = make_window(self)
        w.box.forget_reference()
        w.box.clear()
        w.box.setFocus()
        self.qa.processEvents()
        return w

    def _window_with_ref(self, ref):
        w = make_window(self)
        w.box.setFocus()
        self.qa.processEvents()
        w.lookup(ref)
        self.qa.processEvents()
        return w

    def _type(self, w, s):
        QtTest.QTest.keyClicks(w.box, s)
        self.qa.processEvents()

    def test_typing_1_offers_numbered_books_and_fills_first(self):
        w = self._fresh()
        self._type(w, "1")
        self.assertEqual(w.box.text(), "1 Samuel ")
        self.assertEqual(w.box.typed_text(), "1")
        self.assertEqual(w.box.selectedText(), " Samuel ")
        self.assertIn("1 Samuel ", w.sug_model.stringList())
        self.assertIn("1 John ", w.sug_model.stringList())
        self.assertIsNone(w.box.segment())

    def test_typing_1_then_book_name_narrows_to_that_book(self):
        w = self._fresh()
        self._type(w, "1 jo")
        self.assertEqual(w.box.text(), "1 john ")
        self.assertEqual(w.box.typed_text(), "1 jo")
        self.assertEqual(w.sug_model.stringList(), ["1 John "])
        self._type(w, "hn")
        self.assertEqual(w.box.text(), "1 john")
        self.assertTrue(w.sug_model.stringList()[0].startswith("1 John 1:"))

    def test_3_john_from_ordinal_prefix(self):
        w = self._fresh()
        self._type(w, "3")
        self.assertEqual(w.box.text(), "3 John ")
        self.assertEqual(w.box.typed_text(), "3")
        self.assertEqual(w.sug_model.stringList(), ["3 John "])

    def test_right_from_numbered_book_highlight_goes_to_chapter(self):
        w = self._fresh()
        self._type(w, "1 john")
        QtTest.QTest.keyClick(w.box, QtCore.Qt.Key_Right)
        self.qa.processEvents()
        self.assertEqual(w.box.text(), "1 John 1:1")
        self.assertEqual(w.box.segment(), "chapter")   # not verse
        self.assertEqual(w.box.selectedText(), "1")
        self.assertEqual(w.cur[:4], (62, 1, 1, 1))

    def test_left_from_numbered_book_highlight_stays_on_book(self):
        w = self._fresh()
        self._type(w, "1 thessalonians")
        QtTest.QTest.keyClick(w.box, QtCore.Qt.Key_Left)
        self.qa.processEvents()
        self.assertEqual(w.box.text(), "1 Thessalonians 1:1")
        self.assertEqual(w.box.segment(), "book")
        self.assertEqual(w.box.selectedText(), "1 Thessalonians")

    def test_numbered_book_complete_flow_and_reedit(self):
        w = self._fresh()
        self._type(w, "1 john")
        QtTest.QTest.keyClick(w.box, QtCore.Qt.Key_Right)   # -> chapter
        QtTest.QTest.keyClick(w.box, QtCore.Qt.Key_Right)   # -> verse
        self.assertEqual(w.box.segment(), "verse")
        self._type(w, "3")
        self.assertEqual(w.box.text(), "1 John 1:3")
        QtTest.QTest.keyClick(w.box, QtCore.Qt.Key_Right)   # accept, re-highlight verse
        self.qa.processEvents()
        self.assertEqual(w.box.text(), "1 John 1:3")
        self.assertEqual(w.box.segment(), "verse")
        self.assertEqual(w.box.selectedText(), "3")
        QtTest.QTest.keyClick(w.box, QtCore.Qt.Key_Up)
        self.qa.processEvents()
        self.assertEqual(w.box.text(), "1 John 1:4")
        self.assertEqual(w.box.selectedText(), "4")
        # walk back through chapter to the whole numbered book
        QtTest.QTest.keyClick(w.box, QtCore.Qt.Key_Left)
        QtTest.QTest.keyClick(w.box, QtCore.Qt.Key_Left)
        self.assertEqual(w.box.segment(), "book")
        self.assertEqual(w.box.selectedText(), "1 John")
        self.assertEqual(w.box.text(), "1 John 1:4")

    def test_committed_numbered_ref_arrows_highlight_whole_book(self):
        for ref, book_txt in (("1 Chronicles 1:1", "1 Chronicles"),
                              ("2 Thessalonians 1:1", "2 Thessalonians"),
                              ("1 Corinthians 13:4", "1 Corinthians"),
                              ("1 Timothy 1:1", "1 Timothy"),
                              ("2 Peter 3:9", "2 Peter"),
                              ("3 John 1:4", "3 John")):
            w = self._window_with_ref(ref)
            self.assertEqual(w.box.selectedText(), book_txt, ref)
            K = QtCore.Qt
            QtTest.QTest.keyClick(w.box, K.Key_Right)
            self.assertEqual(w.box.segment(), "chapter", ref)
            QtTest.QTest.keyClick(w.box, K.Key_Right)
            self.assertEqual(w.box.segment(), "verse", ref)
            QtTest.QTest.keyClick(w.box, K.Key_Up)
            self.qa.processEvents()
            self.assertEqual(w.box.segment(), "verse", ref)
            QtTest.QTest.keyClick(w.box, K.Key_Left)
            QtTest.QTest.keyClick(w.box, K.Key_Left)
            self.assertEqual(w.box.selectedText(), book_txt, ref)
            self.assertEqual(w.box.segment(), "book", ref)

    def test_numeric_ref_still_works_after_numbered_book(self):
        w = self._window_with_ref("1 John 3:16")
        self.assertEqual(w.box.selectedText(), "1 John")
        K = QtCore.Qt
        QtTest.QTest.keyClick(w.box, K.Key_Right)
        self.assertEqual(w.box.selectedText(), "3")
        QtTest.QTest.keyClick(w.box, K.Key_Right)
        self.assertEqual(w.box.selectedText(), "16")
        # re-editing a part replaces the whole reference first (fresh search)
        w._ = None
        w.box.select_all_for_replacement()
        self.qa.processEvents()
        self._type(w, "rom 8:28")
        self.assertEqual(w.box.text(), "rom 8:28")

    def test_regular_books_unaffected(self):
        w = self._fresh()
        self._type(w, "joh")
        self.assertEqual(w.box.text(), "joh" + "n ")
        self.assertEqual(w.box.selectedText(), "n ")
        QtTest.QTest.keyClick(w.box, QtCore.Qt.Key_Right)
        self.qa.processEvents()
        self.assertEqual(w.box.text(), "John 1:1")
        self.assertEqual(w.box.segment(), "chapter")


if __name__ == "__main__":
    unittest.main()
