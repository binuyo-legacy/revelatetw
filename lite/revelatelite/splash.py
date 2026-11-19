"""Startup splash for RevelateTW Lite (PyQt5).

A frameless, translucent, always-on-top widget with NO painted background:
the Qt.WA_TranslucentBackground attribute means no rectangle of colour is
drawn behind the logo. The original logo image (splash.jpg) is shown
as-is with no masking, no flood fill and no pixel modification; only the
corners are clipped at display time (a rounded-rect QPainterPath clip, like
Canva's preview) so the square jpg corners are simply not drawn. The gold
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

# Display-time-only corner rounding, like Canva's preview. This is a painter
# clip, never a file edit: the jpg stays byte-identical and is drawn whole,
# only its square corners fall outside the clip and are not drawn. The
# radius is a share of the displayed logo height so it scales with the
# logo; at the 480px display width the logo is ~480x288 and the radius is
# ~48px (roughly 1/6 of the height, in the Canva ballpark).
CORNER_RADIUS_FRACTION = 1.0 / 6.0


def corner_radius_for(pixmap):
    """Corner radius (px) for a pixmap of this size, as a float."""
    return pixmap.height() * CORNER_RADIUS_FRACTION


def rounded_clip_path(rect, radius):
    """A QPainterPath of rect rounded by radius on every corner."""
    path = QtGui.QPainterPath()
    path.addRoundedRect(QtCore.QRectF(rect), radius, radius)
    return path


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


class LogoLabel(QtWidgets.QLabel):
    """Label that paints its pixmap through a rounded-rect clip.

    Same size and position as the plain QLabel it replaces; the pixmap is
    drawn whole and unchanged, only the corner pixels outside the rounded
    clip are skipped. Nothing is painted behind it.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        # Transparent background: only the clipped pixmap may paint. The
        # default label chrome would otherwise fill the corners the clip
        # leaves open, showing as a solid card edge on the desktop.
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self.setStyleSheet("background: transparent; border: none;")

    def paintEvent(self, event):
        pm = self.pixmap()
        if pm is None or pm.isNull():
            super().paintEvent(event)
            return
        rect = QtCore.QRectF(
            (self.width() - pm.width()) / 2.0,
            (self.height() - pm.height()) / 2.0,
            pm.width(), pm.height())
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        painter.setClipPath(
            rounded_clip_path(rect, corner_radius_for(pm)))
        painter.drawPixmap(QtCore.QPointF(rect.x(), rect.y()), pm)
        painter.end()
        # deliberately not calling super().paintEvent() here: the base
        # class would draw the same pixmap again, square corners and all


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

        self.logo_label = LogoLabel()
        self.logo_label.setAlignment(QtCore.Qt.AlignCenter)
        pm = _load_scaled_pixmap()
        if pm is not None:
            self.logo_label.setPixmap(pm)
        layout.addWidget(self.logo_label)

        self.bar = QtWidgets.QProgressBar()
        self.bar.setRange(0, 0)                      # indeterminate / busy mode
        self.bar.setFixedSize(BAR_WIDTH, 10)
        self.bar.setTextVisible(False)
        # Single braces (this is %-formatting, not str.format): the old
        # double-brace stylesheet was rejected by Qt's style engine, so the
        # bar fell back to the native blue on Windows (where the native busy
        # chunk barely reads on a translucent window) and looked gone.
        self.bar.setAttribute(QtCore.Qt.WA_OpaquePaintEvent, True)
        self.bar.setStyleSheet(
            "QProgressBar { background:%s; border:1px solid %s; border-radius:5px; }"
            "QProgressBar::chunk { background:%s; width:60px; border-radius:3px; }"
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
