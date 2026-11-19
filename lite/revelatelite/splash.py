"""Startup splash for RevelateTW Lite (PyQt5).

A frameless, translucent, always-on-top widget with NO painted background:
the Qt.WA_TranslucentBackground attribute means no rectangle of colour is
drawn behind the logo. The original logo image (splash.jpg) is shown
as-is with no masking, no flood fill and no pixel modification; the gold
busy QProgressBar sits centred below it. Shown while the main window is
being built and closed once the main window is on screen.

Nothing here touches the main layout, tabs or preview sizes. If the logo
file is missing or unreadable, the splash is skipped silently (no crash).
"""
import os

from PyQt5 import QtCore, QtGui, QtWidgets

from . import paths

LOGO_MAX_WIDTH = 480           # the logo is 1568x940, shown smaller for a light splash
BAR_WIDTH = 220
BAR_TRACK = "#3a3a40"          # dark track so the gold chunk shows on any desktop


def splash_logo_path():
    return paths.splash_logo_path()


def _load_scaled_pixmap():
    """The logo scaled to fit LOGO_MAX_WIDTH, or None if it cannot be read."""
    pm = QtGui.QPixmap(splash_logo_path())
    if pm.isNull():
        return None
    if pm.width() > LOGO_MAX_WIDTH:
        pm = pm.scaledToWidth(LOGO_MAX_WIDTH, QtCore.Qt.SmoothTransformation)
    return pm


class Splash(QtWidgets.QWidget):
    """Frameless, translucent splash: logo centred, busy bar centred below it."""

    def __init__(self, parent=None):
        super().__init__(parent, QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint)
        # No painted background at all: the window itself is translucent.
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self.setStyleSheet("background: transparent; border: none;")
        from revelatetw.ui_tokens import COLORS as C

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(40, 36, 40, 28)
        layout.setSpacing(20)

        self.logo_label = QtWidgets.QLabel()
        self.logo_label.setAlignment(QtCore.Qt.AlignCenter)
        pm = _load_scaled_pixmap()
        if pm is not None:
            self.logo_label.setPixmap(pm)
        layout.addWidget(self.logo_label)

        self.bar = QtWidgets.QProgressBar()
        self.bar.setRange(0, 0)                      # indeterminate / busy mode
        self.bar.setFixedSize(BAR_WIDTH, 10)
        self.bar.setTextVisible(False)
        self.bar.setStyleSheet(
            "QProgressBar {{ background:%s; border:1px solid %s; border-radius:5px; }}"
            "QProgressBar::chunk {{ background:%s; width:60px; border-radius:3px; }}"
            % (BAR_TRACK, BAR_TRACK, C.accent))
        # Centre the bar below the logo (it must not overlap it).
        row = QtWidgets.QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.bar)
        row.addStretch(1)
        layout.addLayout(row)
        self.adjustSize()

    def center_on_screen(self):
        screen = QtGui.QGuiApplication.primaryScreen()
        if screen is not None:
            g = screen.availableGeometry()
            self.move(g.center() - self.rect().center())


def wants_splash(argv):
    """False when --no-splash is on the command line."""
    return "--no-splash" not in list(argv)


def show_splash(parent=None):
    """Show the splash if the logo can be read. Returns the widget, or None."""
    if QtWidgets.QApplication.instance() is None:
        return None
    try:
        splash = Splash(parent)
        splash.center_on_screen()
        splash.show()
        QtWidgets.QApplication.processEvents()
        return splash
    except Exception:
        return None


def finish_splash(splash):
    """Close the splash once the main window is up."""
    if splash is None:
        return
    try:
        splash.close()
        splash.deleteLater()
    except Exception:
        pass
