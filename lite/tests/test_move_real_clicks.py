"""Service list Move Up/Down through real mouse/keyboard events on the full main window.

Linux offscreen only, not a Windows 8.1 check.
"""
import os
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

try:
    from PyQt5 import QtCore, QtWidgets
    from PyQt5.QtTest import QTest
    from revelatelite import app as lite_app
except ImportError:  # pragma: no cover
    QtWidgets = None

REFS = [("Zechariah 1:2", "WEB"), ("3 John 1:13", "KJV"), ("Exodus 4:13", "KJV"),
        ("Matthew 4:6", "ASV"), ("Zechariah 1:4", "WEB"), ("John 3:16", "KJV")]


@unittest.skipIf(QtWidgets is None, "PyQt5 not installed")
class MoveWithRealEvents(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qa = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["x"])
        lite_app.theme.install_button_focus_style(cls.qa)
        cls.qa.setStyleSheet(lite_app.QSS)

    def make(self):
        from revelatelite import paths
        d = tempfile.mkdtemp()
        paths.user_dir = lambda: d
        lite_app.paths.user_dir = lambda: d
        w = lite_app.Main()
        for r, t in REFS:
            w.services.add(r, t)
        w.refresh_service_list()
        w.show()
        QTest.qWait(100)
        self.addCleanup(w.close)
        return w

    def click_row(self, w, i):
        sl = w.service_list
        QTest.mouseClick(sl.viewport(), QtCore.Qt.LeftButton, pos=sl.visualItemRect(sl.item(i)).center())

    def check(self, w):
        r = w.service_list.currentRow()
        it = w.services.items[r]
        self.assertEqual(w.service_list.item(r).text(), "%s  (%s)" % (it["ref"], it["translation"]))
        self.assertEqual(w.box.text(), it["ref"])
        self.assertEqual(w.preview.ref, "%s  (%s)" % (it["ref"], it["translation"]))
        self.assertEqual(w.trans.currentData(), it["translation"])

    def test_click_row_then_repeated_move_buttons(self):
        w = self.make()
        self.click_row(w, 4)
        self.check(w)
        for _ in range(6):
            QTest.mouseClick(w.up_b, QtCore.Qt.LeftButton)
            self.check(w)
        self.assertEqual(w.service_list.currentRow(), 0)
        self.assertEqual(w.services.items[0]["ref"], "Zechariah 1:4")
        for _ in range(7):
            QTest.mouseClick(w.down_b, QtCore.Qt.LeftButton)
            self.check(w)
        self.assertEqual(w.service_list.currentRow(), len(REFS) - 1)
        self.assertFalse(w.proj.isVisible())

    def test_move_never_projects_or_changes_program(self):
        w = self.make()
        self.click_row(w, 1)
        QTest.mouseClick(w.project_b, QtCore.Qt.LeftButton)
        live = w.proj.ref
        QTest.mouseClick(w.up_b, QtCore.Qt.LeftButton)
        self.check(w)
        self.assertEqual(w.proj.ref, live)

    def test_arrow_keys_in_list_load_item_preview_only(self):
        w = self.make()
        self.click_row(w, 0)
        self.check(w)
        QTest.keyClick(w.service_list, QtCore.Qt.Key_Down)
        self.assertEqual(w.service_list.currentRow(), 1)
        self.check(w)
        self.assertEqual(w.box.text(), "3 John 1:13")
        self.assertFalse(w.proj.isVisible())


if __name__ == "__main__":
    unittest.main()
