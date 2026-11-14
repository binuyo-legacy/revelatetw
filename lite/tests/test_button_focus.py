"""Buttons show no native dotted focus rectangle; gold focus border and keyboard use stay intact."""
import os
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
try:
    from PyQt5 import QtCore, QtGui, QtWidgets, QtTest
    from revelatelite import app as lite_app, theme
except ImportError:  # pragma: no cover
    QtWidgets = None


@unittest.skipIf(QtWidgets is None, "PyQt5 not installed")
class ButtonFocus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qa = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        theme.install_button_focus_style(cls.qa)
        cls.qa.setStyleSheet(lite_app.QSS)

    def test_qss_has_gold_focus_and_no_dotted_outline(self):
        q = lite_app.QSS
        self.assertIn("QPushButton:focus { border:1px solid", q)
        self.assertNotIn("dotted", q)

    def test_install_is_idempotent(self):
        first = theme.install_button_focus_style(self.qa)
        self.assertIs(theme.install_button_focus_style(self.qa), first)
        self.assertIsInstance(first, theme.NoButtonFocusRectStyle)
        self.assertNotIsInstance(first.baseStyle(), theme.NoButtonFocusRectStyle)

    def test_focus_rect_skipped_for_buttons_only(self):
        st = theme.install_button_focus_style(self.qa)
        opt = QtWidgets.QStyleOptionFocusRect()
        opt.rect = QtCore.QRect(0, 0, 40, 20)
        opt.backgroundColor = QtGui.QColor("black")

        def paint(widget):
            img = QtGui.QImage(40, 20, QtGui.QImage.Format_ARGB32)
            img.fill(QtGui.QColor("black"))
            p = QtGui.QPainter(img)
            st.drawPrimitive(QtWidgets.QStyle.PE_FrameFocusRect, opt, p, widget)
            p.end()
            return img

        blank = QtGui.QImage(40, 20, QtGui.QImage.Format_ARGB32)
        blank.fill(QtGui.QColor("black"))
        self.assertEqual(paint(QtWidgets.QPushButton("x")), blank)
        # a non-button still gets the base style's behaviour (no exception, proxy delegates)
        paint(QtWidgets.QLineEdit())

    def test_all_lite_buttons_stay_focusable_and_keyboard_operable(self):
        d = tempfile.mkdtemp()
        lite_app.paths.user_dir = lambda: d
        w = lite_app.Main()
        w.show()
        btns = w.findChildren(QtWidgets.QPushButton)
        self.assertGreater(len(btns), 15)
        for b in btns:
            self.assertNotEqual(b.focusPolicy(), QtCore.Qt.NoFocus, b.text())
        w.close()

    def test_space_activates_focused_button_and_focus_is_reported(self):
        win = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(win)
        a, b = QtWidgets.QPushButton("A"), QtWidgets.QPushButton("B")
        lay.addWidget(a)
        lay.addWidget(b)
        hits = []
        b.clicked.connect(lambda: hits.append("b"))
        win.show()
        win.activateWindow()
        b.setFocus()
        QtTest.QTest.keyClick(b, QtCore.Qt.Key_Space)
        self.assertEqual(hits, ["b"])
        win.close()


if __name__ == "__main__":
    unittest.main()
