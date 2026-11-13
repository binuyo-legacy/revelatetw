"""Keyboard segment editing (Left/Right/Up/Down on book, chapter, verse). Run: python lite\\tests\\test_refedit.py"""
import os
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from revelatelite.bible import BibleStore, adjust_reference, reference_spans, format_reference  # noqa: E402

try:
    from PyQt5 import QtWidgets, QtCore, QtTest
    from revelatelite import app as lite_app
except ImportError:  # pragma: no cover
    QtWidgets = None

STORE = BibleStore()
TR = STORE.translations()[0] if STORE.translations() else None


@unittest.skipIf(TR is None, "no Bible packs")
class Logic(unittest.TestCase):
    def test_spans(self):
        sp = reference_spans(43, 3, 16, 16)
        t = format_reference(43, 3, 16, 16)
        self.assertEqual([t[a:b] for a, b in (sp["book"], sp["chapter"], sp["verse"])], ["John", "3", "16"])
        sp = reference_spans(45, 8, 28, 30)
        t = format_reference(45, 8, 28, 30)
        self.assertEqual(t[sp["verse"][0]:sp["verse"][1]], "28-30")
        sp = reference_spans(46, 13, 1, 1)
        self.assertEqual(format_reference(46, 13, 1, 1)[sp["book"][0]:sp["book"][1]], "1 Corinthians")

    def test_verse_chapter_book(self):
        self.assertEqual(adjust_reference(STORE, TR, (43, 3, 16, 16), "verse", 1)[0], (43, 3, 17, 17))
        self.assertEqual(adjust_reference(STORE, TR, (43, 3, 16, 16), "verse", -1)[0], (43, 3, 15, 15))
        self.assertEqual(adjust_reference(STORE, TR, (45, 8, 28, 30), "verse", 1)[0], (45, 8, 29, 29))
        self.assertEqual(adjust_reference(STORE, TR, (43, 3, 16, 16), "chapter", 1)[0], (43, 4, 16, 16))
        self.assertEqual(adjust_reference(STORE, TR, (43, 3, 16, 16), "book", 1)[0], (44, 1, 1, 1))

    def test_edges_never_wrap(self):
        self.assertIsNone(adjust_reference(STORE, TR, (43, 3, 1, 1), "verse", -1)[0])
        self.assertIsNone(adjust_reference(STORE, TR, (43, 1, 1, 1), "chapter", -1)[0])
        self.assertIsNone(adjust_reference(STORE, TR, (1, 1, 1, 1), "book", -1)[0])
        self.assertIsNone(adjust_reference(STORE, TR, (66, 1, 1, 1), "book", 1)[0])
        last_v = STORE.last_verse(TR, 43, 3)
        self.assertIsNone(adjust_reference(STORE, TR, (43, 3, last_v, last_v), "verse", 1)[0])
        last_c = STORE.last_chapter(TR, 43)
        self.assertIsNone(adjust_reference(STORE, TR, (43, last_c, 1, 1), "chapter", 1)[0])

    def test_chapter_change_clamps_verse(self):
        # Psalm 119:100 -> Psalm 118 has only 29 verses, so verse falls back to 1
        new = adjust_reference(STORE, TR, (19, 119, 100, 100), "chapter", -1)[0]
        self.assertEqual(new, (19, 118, 1, 1))


@unittest.skipIf(QtWidgets is None or TR is None, "PyQt5 or Bible packs missing")
class Keys(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qa = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        cls.qa.setStyleSheet(lite_app.QSS)

    def make(self):
        from revelatelite import paths
        d = tempfile.mkdtemp()
        paths.user_dir = lambda: d
        lite_app.paths.user_dir = lambda: d
        w = lite_app.Main()
        w.show()
        w.activateWindow()
        w.box.setFocus()
        self.qa.processEvents()
        if not w.box.hasFocus():       # some headless Qt builds never give focus; keep tests meaningful
            w.box.hasFocus = lambda: True
        w.lookup("John 3:16")
        return w

    def key(self, w, k):
        QtTest.QTest.keyClick(w.box, k)

    def sel(self, w):
        return w.box.selectedText()

    def test_left_right_moves_highlight_without_changing_verse(self):
        w = self.make()
        self.assertEqual(self.sel(w), "John")                # book highlighted after lookup
        K = QtCore.Qt
        self.key(w, K.Key_Right); self.assertEqual(self.sel(w), "3")
        self.key(w, K.Key_Right); self.assertEqual(self.sel(w), "16")
        self.key(w, K.Key_Right); self.assertEqual(self.sel(w), "16")   # stops at the end
        self.key(w, K.Key_Left); self.assertEqual(self.sel(w), "3")
        self.key(w, K.Key_Left); self.assertEqual(self.sel(w), "John")
        self.key(w, K.Key_Left); self.assertEqual(self.sel(w), "John")
        self.assertEqual(w.cur[:4], (43, 3, 16, 16))
        self.assertEqual(w.box.text(), "John 3:16")

    def test_up_down_edits_verse_and_keeps_highlight(self):
        w = self.make()
        K = QtCore.Qt
        self.key(w, K.Key_Right); self.key(w, K.Key_Right)
        self.key(w, K.Key_Up)
        self.assertEqual(w.box.text(), "John 3:17")
        self.assertEqual(self.sel(w), "17")
        self.assertIn("John 3:17", w.preview.ref)
        self.key(w, K.Key_Down); self.key(w, K.Key_Down)
        self.assertEqual(w.box.text(), "John 3:15")
        self.key(w, K.Key_Left); self.key(w, K.Key_Up)
        self.assertEqual(w.box.text(), "John 4:15")
        self.assertEqual(self.sel(w), "4")

    def test_live_projection_follows_edit(self):
        w = self.make()
        K = QtCore.Qt
        w.project()
        self.assertTrue(w.proj.live)
        self.key(w, K.Key_Right); self.key(w, K.Key_Right); self.key(w, K.Key_Up)
        self.assertIn("John 3:17", w.proj.ref)
        w.proj.close()

    def test_not_live_does_not_project(self):
        w = self.make()
        K = QtCore.Qt
        self.key(w, K.Key_Right); self.key(w, K.Key_Right); self.key(w, K.Key_Up)
        self.assertFalse(w.proj.live)

    def test_typing_replaces_highlight_and_returns_to_normal(self):
        w = self.make()
        QtTest.QTest.keyClicks(w.box, "rom")
        self.assertEqual(w.box.text(), "rom")
        self.assertIsNone(w.box.segment())
        self.assertTrue(w.sug_model.stringList())            # autocomplete still works

    def test_typing_over_chapter_keeps_book(self):
        w = self.make()
        K = QtCore.Qt
        self.key(w, K.Key_Right)
        QtTest.QTest.keyClicks(w.box, "5")
        self.assertEqual(w.box.text(), "John 5:16")
        self.assertIsNone(w.box.segment())

    def test_range_up_becomes_single_verse(self):
        w = self.make()
        w.lookup("Rom 8:28-30")
        K = QtCore.Qt
        self.key(w, K.Key_Right); self.key(w, K.Key_Right)
        self.assertEqual(self.sel(w), "28-30")
        self.key(w, K.Key_Up)
        self.assertEqual(w.box.text(), "Romans 8:29")


if __name__ == "__main__":
    unittest.main()
