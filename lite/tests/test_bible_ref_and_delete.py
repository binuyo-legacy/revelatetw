"""Regression tests for the reference suffix and delete-imported-Bibles fixes.

When an operator typed "New King James Version" / "NKJV" as the name/code of an
imported Bible, that suffix appeared beside the projected reference as
"Deuteronomy 6:5 (NKJV)" and, being drawn in the same bottom band, overprinted
the reference. The reference must stay bottom-centre showing only
book/chapter/verse, in the preview and on the projector, in the default path
and in custom verse templates.

Separately, there was no way to delete an imported Bible. Deletion must:
  - show a confirmation before anything is removed,
  - remove only packs the operator imported (never a bundled pack, even on a
    name clash),
  - fall back to an available translation when the deleted one was selected,
    and refresh the live preview to that fallback state.

Synthetic text only: no copyrighted Bible content is used or copied.
Run: python -m pytest lite/tests/test_bible_ref_and_delete.py
"""
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", ".."))
from revelatelite import app as lite_app
from revelatelite import bibleconvert as BC
from revelatelite.bible import BibleStore
try:
    from PyQt5 import QtWidgets
except ImportError:  # pragma: no cover
    QtWidgets = None

FIX = os.path.join(HERE, "..", "..", "tests", "fixtures", "bible_import")
BUNDLED = os.path.join(HERE, "..", "..", "data", "bible")

CODE = "STC"
NAME = "Synthetic Test Church Translation"
REF = "John 3:16"


def make_store():
    user = tempfile.mkdtemp()
    r = BC.convert(os.path.join(FIX, "sample.usfm"))
    BC.save(r, NAME, CODE, "Licensed", user)
    return BibleStore(BUNDLED, user), user


def make_app(user):
    lite_app.paths.user_dir = lambda: tempfile.mkdtemp()
    w = lite_app.Main()
    w.bible._user_directory = user
    w.bible.close()
    w.refresh_translations()
    return w


def yes(_parent, *_a, **_k):
    return QtWidgets.QMessageBox.Yes


def no(_parent, *_a, **_k):
    return QtWidgets.QMessageBox.No


@unittest.skipIf(QtWidgets is None, "PyQt5 not installed")
class ReferenceNeverCarriesTranslationCode(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qa = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_lookup_strips_code_from_preview_and_slide(self):
        st, user = make_store()
        w = make_app(user)
        try:
            w.trans.setCurrentText(CODE)
            w.lookup(REF)
            self.assertEqual(w.ref_lbl.text(), REF)
            self.assertEqual(w.preview.ref, REF)
            self.assertEqual(w.slide[0], REF)
            self.assertEqual(w.slide[2], "")
            self.assertNotIn(CODE, w.preview.ref)
            self.assertNotIn(CODE.split()[0], w.ref_lbl.text())
            self.assertNotIn("(%s)" % CODE, w.preview.ref)
            self.assertNotIn("(%s)" % CODE, w.ref_lbl.text())
            self.assertNotIn("(%s)" % CODE, w.slide[0])
        finally:
            w.close()
            st.close()

    def test_projected_content_never_carries_code(self):
        st, user = make_store()
        w = make_app(user)
        try:
            w.trans.setCurrentText(CODE)
            w.lookup(REF)
            w.proj.set_content(w.slide[0], w.slide[1], w.slide[2], w.slide_meta)
            self.assertEqual(w.proj.ref, REF)
            self.assertNotIn(CODE, w.proj.ref)
        finally:
            w.close()
            st.close()


@unittest.skipIf(QtWidgets is None, "PyQt5 not installed")
class DeleteImportedBibles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qa = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_delete_imported_only_and_confirm_yes(self):
        st, user = make_store()
        w = make_app(user)
        try:
            self.assertIn(CODE, [w.trans.itemText(i) for i in range(w.trans.count())])
            with patch("PyQt5.QtWidgets.QMessageBox.question", yes):
                self.assertTrue(w.delete_imported_bible(CODE))
            self.assertNotIn(CODE, w.bible.translations())
            self.assertNotIn(CODE, [w.trans.itemText(i) for i in range(w.trans.count())])
            # bundled still there
            self.assertIn("KJV", w.bible.translations())
            st.close()
        finally:
            w.close()

    def test_cancel_changes_nothing(self):
        st, user = make_store()
        w = make_app(user)
        try:
            with patch("PyQt5.QtWidgets.QMessageBox.question", no):
                self.assertFalse(w.delete_imported_bible(CODE))
            self.assertIn(CODE, w.bible.translations())
            self.assertIn(CODE, [w.trans.itemText(i) for i in range(w.trans.count())])
            st.close()
        finally:
            w.close()

    def test_bundled_rejected_without_confirmation(self):
        st, user = make_store()
        w = make_app(user)
        try:
            def boom(*_a, **_k):
                raise AssertionError("confirmation must not be asked for a bundled pack")
            with patch("PyQt5.QtWidgets.QMessageBox.question", boom):
                self.assertFalse(w.delete_imported_bible("KJV"))
            self.assertIn("KJV", w.bible.translations())
            self.assertTrue(os.path.isfile(os.path.join(BUNDLED, "KJV.sqlite")))
            st.close()
        finally:
            w.close()

    def test_unknown_rejected(self):
        st, user = make_store()
        w = make_app(user)
        try:
            def boom(*_a, **_k):
                raise AssertionError("confirmation must not be asked for an unknown code")
            with patch("PyQt5.QtWidgets.QMessageBox.question", boom):
                self.assertFalse(w.delete_imported_bible("NOPE"))
            st.close()
        finally:
            w.close()

    def test_selected_falls_back_and_preview_refreshes(self):
        st, user = make_store()
        w = make_app(user)
        try:
            w.trans.setCurrentText(CODE)
            w.lookup(REF)
            self.assertEqual(w.slide[0], REF)
            with patch("PyQt5.QtWidgets.QMessageBox.question", yes):
                self.assertTrue(w.delete_imported_bible(CODE))
            # combo and saved setting no longer point at the deleted pack,
            # and the preview still shows the reference in the fallback pack
            self.assertNotEqual(w.tr_name(), CODE)
            self.assertIn(w.tr_name(), w.bible.translations())
            self.assertEqual(w.st["translation"], w.tr_name())
            self.assertEqual(w.ref_lbl.text(), REF)
            self.assertEqual(w.slide[0], REF)
            self.assertNotIn(CODE, w.slide[0])
            # persistence: settings file agrees after reload
            saved = json.load(open(w.settings_path, encoding="utf-8"))
            self.assertEqual(saved["translation"], w.tr_name())
            st.close()
        finally:
            w.close()

    def test_non_selected_delete_keeps_selection(self):
        st, user = make_store()
        w = make_app(user)
        try:
            w.trans.setCurrentText("KJV")
            w.lookup(REF)
            before = (w.tr_name(), w.slide[0], w.st["translation"])
            with patch("PyQt5.QtWidgets.QMessageBox.question", yes):
                self.assertTrue(w.delete_imported_bible(CODE))
            self.assertEqual((w.tr_name(), w.slide[0], w.st["translation"]), before)
            st.close()
        finally:
            w.close()

    def test_service_rows_for_deleted_pack_dropped(self):
        st, user = make_store()
        w = make_app(user)
        try:
            w.trans.setCurrentText(CODE)
            w.lookup(REF)
            w.add_to_list()
            self.assertEqual(len(w.services.items), 1)
            with patch("PyQt5.QtWidgets.QMessageBox.question", yes):
                self.assertTrue(w.delete_imported_bible(CODE))
            self.assertEqual(w.services.items, [])
            st.close()
        finally:
            w.close()

    def test_store_level_guard(self):
        st, user = make_store()
        try:
            self.assertFalse(st.delete_user_imported("KJV")["deleted"])
            self.assertTrue(os.path.isfile(os.path.join(BUNDLED, "KJV.sqlite")))
            self.assertTrue(st.delete_user_imported(CODE)["deleted"])
            self.assertNotIn(CODE, st.translations())
            self.assertFalse(st.delete_user_imported(CODE)["deleted"])
        finally:
            st.close()

    def test_delete_button_enabled_state(self):
        st, user = make_store()
        w = make_app(user)
        try:
            self.assertTrue(w.delete_bible_b.isEnabled())
            with patch("PyQt5.QtWidgets.QMessageBox.question", yes):
                w.delete_imported_bible(CODE)
            self.assertFalse(w.delete_bible_b.isEnabled())
            st.close()
        finally:
            w.close()


if __name__ == "__main__":
    unittest.main()
