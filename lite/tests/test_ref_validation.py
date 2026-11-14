"""Out-of-range chapter/verse handling. Run: python lite\\tests\\test_ref_validation.py"""
import os
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from revelatelite.bible import BibleStore, check_reference, partial_problem, find_book, parse_reference  # noqa: E402

try:
    from PyQt5 import QtWidgets, QtCore, QtTest
    from revelatelite import app as lite_app
except ImportError:  # pragma: no cover
    QtWidgets = None

STORE = BibleStore()
TR = "KJV" if "KJV" in STORE.translations() else (STORE.translations() or [None])[0]


@unittest.skipIf(TR is None, "no Bible packs")
class Limits(unittest.TestCase):
    def chk(self, text):
        return check_reference(STORE, TR, parse_reference(text))

    def test_chapter_limits_by_book(self):
        self.assertIsNone(self.chk("Psalms 150:1"))
        self.assertEqual(self.chk("Psalms 151:1")[0], "chapter")
        self.assertIn("Chapter 151 isn't in Psalms", self.chk("Psalms 151:1")[1])
        self.assertIsNone(self.chk("Jude 1:1"))
        self.assertEqual(self.chk("Jude 2:1")[0], "chapter")
        self.assertEqual(self.chk("3 John 2:1")[0], "chapter")
        self.assertIsNone(self.chk("1 John 5:1"))
        self.assertEqual(self.chk("1 John 6:1")[0], "chapter")
        self.assertEqual(self.chk("Revelation 23:1")[0], "chapter")

    def test_verse_limits_per_chapter(self):
        self.assertIsNone(self.chk("Psalms 23:6"))
        bad = self.chk("Psalms 23:40")
        self.assertEqual(bad[0], "verse")
        self.assertIn("Verse 40 isn't in Psalms 23", bad[1])
        self.assertEqual(bad[2], (19, 23, 6, 6))
        self.assertIsNone(self.chk("Psalms 119:176"))
        self.assertEqual(self.chk("Psalms 117:3")[0], "verse")
        self.assertIsNone(self.chk("John 3:16"))

    def test_partial_vs_committed(self):
        # a chapter that may still grow is fine while typing
        self.assertIsNone(partial_problem(STORE, TR, "Psalms 15"))
        self.assertIsNone(partial_problem(STORE, TR, "Psalms 150"))
        self.assertIsNotNone(partial_problem(STORE, TR, "Psalms 151"))
        self.assertIsNone(partial_problem(STORE, TR, "Psalms 23:"))
        self.assertIsNone(partial_problem(STORE, TR, "Psalms 23:6"))
        self.assertIsNotNone(partial_problem(STORE, TR, "Psalms 23:40"))
        # book still being typed, ordinals and unknown text never count as a problem
        for t in ("1", "2 ", "1 jo", "joh", "", "zzz 9"):
            self.assertIsNone(partial_problem(STORE, TR, t), t)
        self.assertIsNone(partial_problem(STORE, TR, "1 John 5"))
        self.assertIsNotNone(partial_problem(STORE, TR, "1 John 6"))


@unittest.skipIf(QtWidgets is None or TR is None, "PyQt5 or Bible packs missing")
class Typing(unittest.TestCase):
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
        w.box.setFocus()
        self.qa.processEvents()
        if not w.box.hasFocus():
            w.box.hasFocus = lambda: True
        i = w.trans.findData(TR)
        if i >= 0:
            w.trans.setCurrentIndex(i)
        w.lookup("Psalms 23:1")
        return w

    def type(self, w, s):
        for ch in s:
            QtTest.QTest.keyClicks(w.box, ch)

    def fresh(self, w, s):
        w.box.selectAll()
        QtTest.QTest.keyClick(w.box, QtCore.Qt.Key_Delete)
        self.type(w, s)

    def enter(self, w):
        QtTest.QTest.keyClick(w.box, QtCore.Qt.Key_Return)

    def test_multi_digit_chapter_still_types(self):
        w = self.make()
        self.fresh(w, "Psalms 119:176")
        self.assertEqual(w.box.text(), "Psalms 119:176")
        self.assertFalse(w.box.property("invalid"))
        self.enter(w)
        self.assertEqual(w.cur[:4], (19, 119, 176, 176))

    def test_invalid_chapter_digit_refused_and_preview_kept(self):
        w = self.make()
        before_slide = w.slide
        before_ref = w.preview.ref
        self.fresh(w, "Psalms 15")
        self.type(w, "1")                      # 151 can never be valid
        self.assertEqual(w.box.text(), "Psalms 15")
        self.assertIn("Chapter 151 isn't in Psalms", w.verse_lbl.text())
        self.assertEqual(w.slide, before_slide)
        self.assertEqual(w.preview.ref, before_ref)
        self.assertTrue(w.preview.live)
        self.assertIsNotNone(w.cur)
        self.type(w, "0")                      # recovery: 150 is fine
        self.assertEqual(w.box.text(), "Psalms 150")
        self.enter(w)
        self.assertEqual(w.cur[:4], (19, 150, 1, 1))
        self.assertEqual(w.verse_lbl.text(), "")

    def test_invalid_verse_digit_refused_with_hint(self):
        w = self.make()
        self.fresh(w, "Psalms 23:4")
        self.type(w, "0")
        self.assertEqual(w.box.text(), "Psalms 23:4")
        self.assertIn("Verse 40 isn't in Psalms 23", w.verse_lbl.text())
        self.assertTrue(w.preview.live)
        self.assertIn("Psalms 23:1", w.preview.ref)
        self.enter(w)
        self.assertEqual(w.cur[:4], (19, 23, 4, 4))

    def test_committed_out_of_range_never_blanks_preview(self):
        w = self.make()
        for bad, word in (("Psalms 151:1", "Chapter 151"), ("Psalms 23:40", "Verse 40"), ("Jude 5:1", "Chapter 5")):
            w.lookup(bad)                          # Enter / Look up path
            self.assertIn(word, w.verse_lbl.text())
            self.assertEqual(w.cur[:4], (19, 23, 1, 1), bad)
            self.assertTrue(w.preview.live, bad)
            self.assertIn("Psalms 23:1", w.preview.ref)
            self.assertTrue(w.project_b.isEnabled())
        w.lookup("Psalms 23:2")                    # valid recovery
        self.assertEqual(w.cur[:4], (19, 23, 2, 2))
        self.assertEqual(w.verse_lbl.text(), "")

    def test_unreadable_text_keeps_preview(self):
        w = self.make()
        w.lookup("blah blah")
        self.assertTrue(w.preview.live)
        self.assertEqual(w.cur[:4], (19, 23, 1, 1))
        self.assertIn("could not read", w.verse_lbl.text())

    def test_pasted_invalid_is_marked_not_blanked(self):
        w = self.make()
        w.box.setText("Psalms 151:1")
        w.box.textEdited.emit("Psalms 151:1")
        self.assertTrue(w.box.property("invalid"))
        self.assertIn("Chapter 151", w.verse_lbl.text())
        self.assertTrue(w.preview.live)
        w.box.setText("Psalms 15")
        w.box.textEdited.emit("Psalms 15")
        self.assertFalse(w.box.property("invalid"))
        self.assertEqual(w.verse_lbl.text(), "")

    def test_numbered_books_and_ordinals_unaffected(self):
        w = self.make()
        self.fresh(w, "1 jo")
        self.assertEqual(w.box.text().lower()[:4], "1 jo")
        self.assertEqual(w.verse_lbl.text(), "")
        self.fresh(w, "1 John 5")
        self.type(w, "1")                      # 1 John has 5 chapters: 51 refused
        self.assertEqual(w.box.text(), "1 John 5")
        self.assertIn("Chapter 51 isn't in 1 John", w.verse_lbl.text())

    def test_editing_never_projects(self):
        w = self.make()
        self.assertFalse(w.proj.live)
        self.fresh(w, "Psalms 15")
        self.type(w, "1")
        w.lookup("Psalms 151:1")
        w.lookup("Psalms 23:40")
        self.assertFalse(w.proj.live)

    def test_arrow_navigation_unchanged(self):
        w = self.make()
        K = QtCore.Qt
        QtTest.QTest.keyClick(w.box, K.Key_Right)
        QtTest.QTest.keyClick(w.box, K.Key_Right)
        QtTest.QTest.keyClick(w.box, K.Key_Up)
        self.assertEqual(w.box.text(), "Psalms 23:2")
        self.assertEqual(w.cur[:4], (19, 23, 2, 2))

    def test_hint_clears_itself(self):
        w = self.make()
        w.lookup("Psalms 151:1")
        self.assertTrue(w._hint_timer.isActive())
        w.clear_ref_hint()
        self.assertEqual(w.verse_lbl.text(), "")
        self.assertFalse(w._hint_timer.isActive())


if __name__ == "__main__":
    unittest.main()
