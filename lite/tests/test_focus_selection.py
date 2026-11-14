"""Focus/selection UX for the verse reference box. Headless (offscreen Qt); not a Windows 8.1 hardware check.
Run: python -m pytest lite/tests/test_focus_selection.py

Covers:
  * picking a translation focuses the reference box with the whole reference selected
  * typing then replaces the old reference (no double-click)
  * repeated translation picks stay stable (still focused + selected, text unchanged)
  * book typing keeps the suggestion popup/cursor (no forced select-all per keystroke)
  * Left/Right traverse book -> chapter -> verse and back while editing
  * completing the chapter does not drop into a state that needs a double-click
  * after committing a suggestion (Enter / pick) the full reference is selected for replacement
"""
import os
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from revelatelite.bible import BibleStore  # noqa: E402

try:
    from PyQt5 import QtCore, QtTest, QtWidgets
    from revelatelite import app as lite_app
except ImportError:  # pragma: no cover
    QtWidgets = None

STORE = BibleStore()
TR = STORE.translations()[0] if STORE.translations() else None


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


@unittest.skipIf(QtWidgets is None or TR is None, "PyQt5 or Bible packs missing")
class FocusSelection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qa = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        cls.qa.setStyleSheet(lite_app.QSS)

    def _window_with_ref(self, ref="Zechariah 1:5"):
        w = make_window(self)
        w.box.setFocus()
        self.qa.processEvents()
        w.lookup(ref)
        return w

    def _other_translation(self, w):
        for i in range(w.trans.count()):
            if w.trans.itemData(i) != w.trans.currentData():
                return i
        return None

    def test_translation_pick_focuses_and_selects_reference(self):
        w = self._window_with_ref()
        other = self._other_translation(w)
        self.assertIsNotNone(other)
        w.trans.setFocus()
        w.trans.setCurrentIndex(other)          # what a mouse pick emits
        self.qa.processEvents()
        self.assertTrue(w.box.hasFocus())
        self.assertEqual(w.box.selectedText(), "Zechariah 1:5")
        self.assertEqual(w.box.selectionStart(), 0)
        self.assertEqual(w.box.selectionEnd(), len("Zechariah 1:5"))
        self.assertIsNone(w.box.segment())      # full selection, not one part

    def test_typing_after_translation_pick_replaces_reference(self):
        w = self._window_with_ref()
        w.trans.setCurrentIndex(self._other_translation(w))
        self.qa.processEvents()
        QtTest.QTest.keyClicks(w.box, "john 3:16")
        self.assertEqual(w.box.text(), "john 3:16")
        self.assertEqual(w.box.typed_text(), "john 3:16")

    def test_repeated_translation_picks_stay_stable(self):
        w = self._window_with_ref()
        first = self._other_translation(w)
        for _ in range(3):
            w.trans.setCurrentIndex(first)
            self.qa.processEvents()
            self.assertTrue(w.box.hasFocus())
            self.assertEqual(w.box.selectedText(), "Zechariah 1:5")
            self.assertEqual(w.box.text(), "Zechariah 1:5")
            other = self._other_translation(w)
            w.trans.setCurrentIndex(other)
            self.qa.processEvents()
            self.assertTrue(w.box.hasFocus())
            self.assertEqual(w.box.selectedText(), "Zechariah 1:5")

    def test_translation_pick_does_not_steal_focus_from_song_slide(self):
        w = self._window_with_ref()
        w.cur = None
        w.song = object()
        w.slide = ("Song", "lyrics", "")
        other = self._other_translation(w)
        before = w.box.text()
        w.trans.setCurrentIndex(other)          # song slide: pick only retargets
        self.qa.processEvents()
        self.assertEqual(w.box.text(), before)  # reference untouched
        self.assertEqual(w.slide, ("Song", "lyrics", ""))

    def _fresh_typing(self):
        w = make_window(self)
        w.box.forget_reference()
        w.box.clear()
        w.box.setFocus()
        self.qa.processEvents()
        return w

    def test_book_typing_keeps_cursor_and_suggestions(self):
        w = self._fresh_typing()
        QtTest.QTest.keyClicks(w.box, "joh")
        self.assertEqual(w.box.text(), "joh" + "n ")     # inline fill, tail selected only
        self.assertEqual(w.box.selectedText(), "n ")
        self.assertEqual(w.box.typed_text(), "joh")
        self.assertTrue(w.sug_model.stringList())        # popup data still there
        self.assertIsNone(w.box.segment())               # not in part-highlight mode

    def test_arrows_traverse_book_chapter_verse_and_back(self):
        w = self._window_with_ref("John 3:16")
        K = QtCore.Qt
        self.assertEqual(w.box.selectedText(), "John")  # book after lookup
        QtTest.QTest.keyClick(w.box, K.Key_Right)
        self.assertEqual(w.box.selectedText(), "3")
        self.assertEqual(w.box.segment(), "chapter")
        QtTest.QTest.keyClick(w.box, K.Key_Right)
        self.assertEqual(w.box.selectedText(), "16")
        self.assertEqual(w.box.segment(), "verse")
        QtTest.QTest.keyClick(w.box, K.Key_Left)
        self.assertEqual(w.box.selectedText(), "3")
        QtTest.QTest.keyClick(w.box, K.Key_Left)
        self.assertEqual(w.box.selectedText(), "John")
        self.assertEqual(w.box.text(), "John 3:16")

    def test_chapter_completion_needs_no_double_click(self):
        # Type a book, step into the chapter, finish it: the reference is shown
        # and the next edit (arrow or typing) works without a double-click.
        w = self._fresh_typing()
        QtTest.QTest.keyClicks(w.box, "joh")
        QtTest.QTest.keyClick(w.box, QtCore.Qt.Key_Right)   # accept John -> chapter
        self.assertEqual(w.box.text(), "John 1:1")
        self.assertEqual(w.box.segment(), "chapter")
        QtTest.QTest.keyClicks(w.box, "3")                  # complete the chapter number
        self.assertEqual(w.box.text(), "John 3:1")
        # Still editable: Left/Right walk the parts again, no double-click needed.
        # (The established arrow contract: Left walks back one part, Right forward.)
        QtTest.QTest.keyClick(w.box, QtCore.Qt.Key_Left)
        self.assertEqual(w.box.segment(), "chapter")
        self.assertEqual(w.box.selectedText(), "3")
        QtTest.QTest.keyClick(w.box, QtCore.Qt.Key_Left)
        self.assertEqual(w.box.segment(), "book")
        self.assertEqual(w.box.selectedText(), "John")
        QtTest.QTest.keyClick(w.box, QtCore.Qt.Key_Right)
        QtTest.QTest.keyClick(w.box, QtCore.Qt.Key_Right)
        self.assertEqual(w.box.segment(), "verse")
        QtTest.QTest.keyClick(w.box, QtCore.Qt.Key_Up)
        self.assertEqual(w.box.text(), "John 3:2")

    def test_enter_commit_selects_full_reference_for_replacement(self):
        w = self._fresh_typing()
        QtTest.QTest.keyClicks(w.box, "john 3:16")
        QtTest.QTest.keyClick(w.box, QtCore.Qt.Key_Return)  # explicit commit
        self.assertEqual(w.box.text(), "John 3:16")
        self.assertTrue(w.box.hasFocus())
        self.assertTrue(w.box.hasSelectedText())
        # Typing now replaces the whole reference instead of appending.
        QtTest.QTest.keyClicks(w.box, "rom 8:28")
        self.assertEqual(w.box.text(), "rom 8:28")
        self.assertEqual(w.box.typed_text(), "rom 8:28")

    def test_suggestion_pick_selects_full_reference(self):
        w = self._fresh_typing()
        w.suggestion_picked("John 3:16")
        self.qa.processEvents()
        self.qa.processEvents()
        self.assertEqual(w.box.text(), "John 3:16")
        self.assertTrue(w.box.hasFocus())
        self.assertTrue(w.box.hasSelectedText())
        QtTest.QTest.keyClicks(w.box, "ps 23:1")
        self.assertEqual(w.box.text(), "ps 23:1")

    def test_mouse_click_in_box_still_places_cursor(self):
        w = self._window_with_ref("John 3:16")
        # A plain click (no translation pick) must not re-select everything.
        QtTest.QTest.mouseClick(w.box, QtCore.Qt.LeftButton, pos=QtCore.QPoint(6, w.box.height() // 2))
        self.qa.processEvents()
        self.assertFalse(w.box.hasSelectedText())


if __name__ == "__main__":
    unittest.main()
