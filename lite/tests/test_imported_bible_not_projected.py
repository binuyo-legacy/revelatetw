"""Regression tests for the imported-Bible-name projection issue.

The projection must show only the verse text and, when the Bible-reference
switch is on, the reference itself (bottom centre). The imported translation
name and its licence text stay as operator-side metadata and must never reach
the projected or previewed slide, so the two cannot overprint each other.

Synthetic text only: no copyrighted Bible content is used or copied.
Run: python -m pytest lite/tests/test_imported_bible_not_projected.py
"""
import os
import sqlite3
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from PyQt5 import QtCore, QtWidgets  # noqa: E402
from revelatelite import app as lite_app, songthemes, versethemes as V  # noqa: E402
from revelatelite.bible import BibleStore  # noqa: E402
from revelatelite.projection import SlideView  # noqa: E402

_QA = []
BODY = "Synthetic verse text used only for this projection regression test."
REF = "John 1:1"
# Made-up issuer/licence strings, chosen so they cannot be confused with a
# reference and are easy to find in a failure message.
ISSUER = "Synthetic Test Church Translation"
LICENSE = "Synthetic Test Church holds this test text. Source: local test pack."
CODE = "STC"


def qapp():
    qa = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    _QA[:] = [qa]
    return qa


def _same(a, b):
    return a.size() == b.size() and a.constBits().asstring(a.byteCount()) == b.constBits().asstring(b.byteCount())


def render(ref=REF, body=BODY, credit="", meta=None, theme=V.DEFAULT, size=(640, 360), show_ref=True):
    v = SlideView()
    v.set_style("navy", 100, show_ref, "Georgia", False, "", "", None, False, "", 3,
                songthemes.STANDARD, None, theme)
    v.set_content(ref, body, credit, meta)
    return v.snapshot(QtCore.QSize(*size)).toImage()


class ImportedBibleCreditOnSlide(unittest.TestCase):
    def setUp(self):
        qapp()

    def test_credit_value_alone_changes_no_pixel_in_any_verse_theme(self):
        # Even if a credit is handed to the seed, the painted slide must be
        # identical with and without it, in every verse template (and default).
        for key in V.KEYS:
            blank = render(credit="", theme=key)
            credited = render(credit=ISSUER, theme=key)
            self.assertFalse(blank.isNull(), key)
            self.assertTrue(_same(blank, credited),
                            "%s: the translation name changed the slide" % key)

    def test_reference_still_paints_and_toggles(self):
        with_ref = render(show_ref=True, credit=ISSUER)
        without_ref = render(show_ref=False, credit=ISSUER)
        self.assertFalse(_same(with_ref, without_ref))
        # The reference-on slide must not contain the credit anywhere, and the
        # only difference between the two is the reference band.

    def test_reference_is_the_only_bottom_line(self):
        # A fake long translation name (the widest the operator could enter)
        # must not move or widen anything on the slide.
        plain = render(credit="")
        long_name = render(credit="Q" * 120)
        self.assertTrue(_same(plain, long_name))

    def test_song_slides_are_untouched(self):
        meta = songthemes.SAMPLE_META
        a = render(credit="", meta=meta)
        b = render(credit=ISSUER, meta=meta)
        self.assertTrue(_same(a, b))


class LibraryMetadataStillStored(unittest.TestCase):
    def _pack(self, folder):
        path = os.path.join(folder, CODE + ".sqlite")
        db = sqlite3.connect(path)
        db.execute("CREATE TABLE verses (book_id INTEGER, chapter INTEGER, verse INTEGER, text TEXT)")
        db.execute("CREATE TABLE meta (key TEXT, value TEXT)")
        db.execute("INSERT INTO verses VALUES (43, 1, 1, ?)", (BODY,))
        meta = {"id": CODE, "name": ISSUER, "language": "en", "license": LICENSE,
                "attribution": "", "version": "1", "user_imported": "1",
                "source_format": "zefania", "source_file": "synthetic.zefania.xml"}
        db.executemany("INSERT INTO meta VALUES (?, ?)", sorted(meta.items()))
        db.commit()
        db.close()

    def test_name_and_license_stay_in_the_pack(self):
        folder = tempfile.mkdtemp()
        self._pack(folder)
        store = BibleStore(directory=folder, user_directory=folder)
        self.assertEqual(store.full_name(CODE), ISSUER)
        self.assertEqual(store.credit(CODE), LICENSE)
        self.assertEqual(store.passage(CODE, 43, 1, 1, 1), BODY)
        # The operator still sees the credit; it just never goes on the slide.
        self.assertTrue(store.short_credit(CODE))


class LookupSendsCleanSlide(unittest.TestCase):
    def setUp(self):
        qapp()

    def test_window_slide_has_reference_only(self):
        w = lite_app.Main()
        self.addCleanup(w.close)
        w.lookup(REF)
        slide = w.slide
        self.assertIsNotNone(slide)
        self.assertEqual(slide[0], REF)
        self.assertTrue(slide[1])                     # verse text from the bundled pack
        self.assertEqual(slide[2], "")
        self.assertEqual(w.preview.ref, REF)
        self.assertEqual(w.preview.credit, "")
        self.assertNotIn(CODE, w.preview.ref)
        self.assertNotIn(ISSUER, w.preview.ref)


if __name__ == "__main__":
    unittest.main()
