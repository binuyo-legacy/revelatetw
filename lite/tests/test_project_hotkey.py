"""Project hotkey: F1 primary, F5 and Ctrl+Enter aliases, Esc Project Off.

Regression tests for the F5 -> F1 change. F1 sits next to Esc on the top
row, so both projector keys are beside each other and need no Fn layer on
Windows 10+ laptops. Qt has no F1 help conflict in Lite: Main is a QWidget
(no QMainWindow help action), no WhatsThis/help shortcut is registered, and
Qt's What's This shortcut is Shift+F1, not bare F1. Bare F1/F5 can still be
swallowed by laptop media layers, so F5 and Ctrl+Enter stay as aliases.
"""
import os
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
try:
    from PyQt5 import QtCore, QtGui, QtWidgets, QtTest
    from revelatelite import app as lite_app
except ImportError:  # pragma: no cover
    QtWidgets = None


@unittest.skipIf(QtWidgets is None, "PyQt5 not installed")
class ProjectHotkey(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qa = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def make(self):
        d = tempfile.mkdtemp()
        lite_app.paths.user_dir = lambda: d
        w = lite_app.Main()
        w.st["transition_ms"] = 0
        w.show()
        w.activateWindow()
        return w

    def _shortcuts(self, w):
        # map key-string -> receiver name via the shortcut's activated signal
        mapping = {}
        for sc in w.findChildren(QtWidgets.QShortcut):
            key = sc.key().toString()
            # identify receiver by its bound method name
            recv = sc.receivers(QtCore.SIGNAL("activated()")) if hasattr(sc, "receivers") else None
            mapping[key] = sc
        return mapping

    def test_primary_label_and_tooltip_show_f1(self):
        w = self.make()
        self.assertEqual(w.project_b.text(), "Project (F1)")
        self.assertIn("F1", w.project_b.toolTip())
        self.assertIn("Esc", w.project_b.toolTip())
        self.assertEqual(w.blank_b.text(), "Project Off (Esc)")
        w.close()

    def test_main_window_has_f1_f5_ctrl_enter_and_esc_shortcuts(self):
        w = self.make()
        keys = {}
        for sc in w.findChildren(QtWidgets.QShortcut):
            keys.setdefault(sc.key().toString(), []).append(sc)
        for want in ("F1", "F5", "Ctrl+Return", "Ctrl+Enter", "Esc"):
            self.assertIn(want, keys, f"missing shortcut {want}, have {sorted(keys)}")
        # F1 and F5 must both be bare (no modifier) so they work without Fn,
        # and their context must cover the whole main window (WindowShortcut
        # is the QShortcut default), not a single focused widget.
        for want in ("F1", "F5"):
            sc = keys[want][0]
            self.assertEqual(sc.context(), QtCore.Qt.WindowShortcut)
        w.close()

    def test_f1_from_main_window_projects(self):
        w = self.make()
        w.lookup("Rom 8:28")
        self.assertFalse(w.proj.isVisible())
        self.qa.processEvents()
        QtTest.QTest.keyClick(w, QtCore.Qt.Key_F1)
        self.qa.processEvents()
        self.assertTrue(w.proj.isVisible(), "F1 from main window did not project")
        self.assertIn("Romans 8:28", w.proj.ref)
        self.qa.processEvents()
        QtTest.QTest.keyClick(w.proj, QtCore.Qt.Key_Escape)
        self.qa.processEvents()
        self.assertFalse(w.proj.isVisible(), "Esc did not project off")
        w.close()

    def test_f5_still_projects_from_main_window(self):
        w = self.make()
        w.lookup("Rom 8:28")
        self.qa.processEvents()
        QtTest.QTest.keyClick(w, QtCore.Qt.Key_F5)
        self.qa.processEvents()
        self.assertTrue(w.proj.isVisible(), "F5 alias from main window did not project")
        self.qa.processEvents()
        QtTest.QTest.keyClick(w.proj, QtCore.Qt.Key_Escape)
        self.qa.processEvents()
        self.assertFalse(w.proj.isVisible())
        w.close()

    def test_ctrl_enter_still_projects_from_main_window(self):
        w = self.make()
        w.lookup("Rom 8:28")
        self.qa.processEvents()
        QtTest.QTest.keyClick(w, QtCore.Qt.Key_Return, QtCore.Qt.ControlModifier)
        self.qa.processEvents()
        self.assertTrue(w.proj.isVisible(), "Ctrl+Enter alias from main window did not project")
        self.qa.processEvents()
        QtTest.QTest.keyClick(w.proj, QtCore.Qt.Key_Escape)
        self.qa.processEvents()
        self.assertFalse(w.proj.isVisible())
        w.close()

    def test_f1_from_projector_window_reprojects_and_esc_turns_off(self):
        w = self.make()
        w.lookup("Rom 8:28")
        w.project()
        self.assertTrue(w.proj.isVisible())
        w.lookup("John 3:16")
        self.assertIn("Romans 8:28", w.proj.ref)
        self.qa.processEvents()
        QtTest.QTest.keyClick(w.proj, QtCore.Qt.Key_F1)
        self.assertIn("John 3:16", w.proj.ref, "F1 from projector window did not re-project")
        self.qa.processEvents()
        QtTest.QTest.keyClick(w.proj, QtCore.Qt.Key_Escape)
        self.assertFalse(w.proj.isVisible(), "Esc from projector window did not turn off")
        self.assertIn("John 3:16", w.preview.ref)
        self.assertFalse(w.blank_b.isEnabled())
        w.close()

    def test_f5_and_ctrl_enter_from_projector_window_still_project(self):
        w = self.make()
        w.lookup("Rom 8:28")
        w.project()
        for key, mods, ref in ((QtCore.Qt.Key_F5, QtCore.Qt.NoModifier, "John 3:16"),
                               (QtCore.Qt.Key_Return, QtCore.Qt.ControlModifier, "Rom 8:28")):
            w.lookup(ref)
            self.qa.processEvents()
            QtTest.QTest.keyClick(w.proj, key, mods)
            self.qa.processEvents()
            self.assertIn(ref.replace("Rom 8:28", "Romans 8:28"), w.proj.ref)
            self.assertTrue(w.proj.isVisible())
        self.qa.processEvents()
        QtTest.QTest.keyClick(w.proj, QtCore.Qt.Key_Escape)
        self.qa.processEvents()
        self.assertFalse(w.proj.isVisible())
        w.close()

    def test_no_help_or_whatsthis_shortcut_steals_f1(self):
        w = self.make()
        for sc in w.findChildren(QtWidgets.QShortcut):
            self.assertNotEqual(sc.key().toString(), "Shift+F1")
        # exactly one bare F1 shortcut on the main window, bound to project
        f1 = [s for s in w.findChildren(QtWidgets.QShortcut) if s.key().toString() == "F1"]
        self.assertEqual(len(f1), 1)
        w.close()


if __name__ == "__main__":
    unittest.main()
