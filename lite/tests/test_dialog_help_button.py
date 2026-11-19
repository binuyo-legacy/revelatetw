"""The Add a Bible and New song dialogs must not show the "?" context-help button.

Headless (offscreen Qt); not a Windows 8.1 hardware check.
"""
import os
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from PyQt5 import QtCore, QtWidgets

from revelatelite import app as lite_app
from revelatelite import bibleimport


class NoContextHelpButton(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_add_bible_dialog_help_hint_off(self):
        d = tempfile.mkdtemp()
        dlg = bibleimport.ImportBibleDialog(None, d, [])
        self.assertFalse(bool(dlg.windowFlags() & QtCore.Qt.WindowContextHelpButtonHint))
        dlg.close()

    def test_new_song_dialog_help_hint_off(self):
        dlg = lite_app.SongDialog(None)
        self.assertFalse(bool(dlg.windowFlags() & QtCore.Qt.WindowContextHelpButtonHint))
        dlg.close()


if __name__ == "__main__":
    unittest.main()
