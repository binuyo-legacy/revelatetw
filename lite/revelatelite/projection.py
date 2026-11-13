"""The projection window: borderless, goes to the extended display, auto-sizes the verse."""
from PyQt5 import QtCore, QtGui, QtWidgets

from . import background, layout, settings


class SlideView(QtWidgets.QWidget):
    """Draws one slide. Used by BOTH the projector window and the small in-app preview,
    so the preview is exactly what the audience sees (everything scales with the height)."""

    def __init__(self):
        super().__init__()
        self.ref = ""
        self.body = ""
        self.credit = ""
        self.live = False          # False = black screen
        self.theme = "navy"
        self.scale = 100
        self.show_ref = True
        self.font_family = "Georgia"
        self.bold = False
        self.bg_color = ""
        self.text_color = ""
        self.bg_spec = background.spec_from({})
        self._bgp = background.Painter()

    # ---- content ----
    def set_content(self, ref, body, credit=""):
        self.ref, self.body, self.credit = ref, body, credit
        self.live = True
        self.update()

    def blank(self):
        self.live = False
        self.update()

    def set_style(self, theme, scale, show_ref, font_family="Georgia", bold=False, bg_color="", text_color="", bg_spec=None):
        self.theme, self.scale, self.show_ref = theme, scale, show_ref
        self.font_family, self.bold, self.bg_color, self.text_color = font_family, bold, bg_color, text_color
        self.bg_spec = bg_spec or background.spec_from({})
        self.update()

    # ---- drawing ----
    def paintEvent(self, _):
        kind = self.bg_spec[0]
        bg, fg, refc = settings.resolve_colors(self.theme, self.bg_color, self.text_color)
        if kind == "gradient":       # text colour follows the average of the two colours
            bg, fg, refc = settings.resolve_colors(self.theme, background.mix(self.bg_spec[1], self.bg_spec[2]), self.text_color)
        elif kind == "image" and background.load_image(self.bg_spec[4])[0] is not None:
            bg, fg, refc = settings.resolve_colors(self.theme, "#0b0f19", self.text_color)
            bg = self.bg_color if settings.valid_color(self.bg_color) else bg
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.TextAntialiasing)
        if not self.live or not self.body:
            p.fillRect(self.rect(), QtGui.QColor("#000000"))
            return
        self._bgp.paint(p, self.rect(), self.bg_spec, bg)
        w, h = self.width(), self.height()
        mx, my = int(w * 0.07), int(h * 0.06)
        area = QtCore.QRect(mx, my, w - 2 * mx, h - 2 * my)
        ref_h = 0
        if self.show_ref and self.ref:
            f = QtGui.QFont("Segoe UI", 10)
            f.setBold(True)
            f.setPixelSize(max(14, int(h * 0.055 * self.scale / 100)))
            p.setFont(f)
            p.setPen(QtGui.QColor(refc))
            ref_h = QtGui.QFontMetrics(f).height() + int(h * 0.02)
            p.drawText(QtCore.QRect(area.x(), area.y() + area.height() - ref_h + int(h * 0.02),
                                    area.width(), ref_h), QtCore.Qt.AlignCenter, self.ref)
        text_area = QtCore.QRect(area.x(), area.y(), area.width(), area.height() - ref_h)
        flags = QtCore.Qt.AlignCenter | QtCore.Qt.TextWordWrap

        def fits(size):
            f = self._body_font(size)
            r = QtGui.QFontMetrics(f).boundingRect(0, 0, text_area.width(), 100000, flags, self.body)
            return r.height() <= text_area.height()

        top = int(h * 0.12 * self.scale / 100)
        size = layout.fit_font_size(fits, 14, max(16, top))
        p.setFont(self._body_font(size))
        p.setPen(QtGui.QColor(fg))
        p.drawText(text_area, flags, self.body)
        if self.credit:
            f2 = QtGui.QFont("Segoe UI")
            f2.setPixelSize(max(11, int(h * 0.02)))
            p.setFont(f2)
            p.setPen(QtGui.QColor(fg))
            p.setOpacity(0.55)
            p.drawText(QtCore.QRect(0, h - int(h * 0.04) - 4, w, int(h * 0.04)),
                       QtCore.Qt.AlignCenter, self.credit)

    def _body_font(self, size):
        f = QtGui.QFont(self.font_family or "Georgia")
        if hasattr(f, "setFamilies"):      # Qt 5.13+: a missing font falls back to Georgia, then Arial
            f.setFamilies([self.font_family or "Georgia", "Georgia", "Arial"])
        f.setPixelSize(size)
        f.setBold(self.bold)
        return f

    def resizeEvent(self, e):
        self.update()
        super().resizeEvent(e)


class PreviewView(SlideView):
    """Small 16:9 preview inside the operator window. Always shows the selected verse
    (even when the projector is black), with a red frame while it is live."""

    def __init__(self):
        super().__init__()
        self.on_air = False
        self.setMinimumSize(320, 180)
        sp = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        sp.setHeightForWidth(True)
        self.setSizePolicy(sp)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, w):
        return layout.height_for_width(w)

    def sizeHint(self):
        return QtCore.QSize(400, layout.height_for_width(400))

    def show_slide(self, ref, body, credit=""):
        self.ref, self.body, self.credit = ref, body, credit
        self.live = bool(body)
        self.update()

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QtGui.QPainter(self)
        p.setPen(QtGui.QPen(QtGui.QColor("#ef4444" if self.on_air else "#334155"), 3 if self.on_air else 1))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))


class ProjectionWindow(SlideView):
    offRequested = QtCore.pyqtSignal()       # Esc pressed while this window has the keyboard
    projectRequested = QtCore.pyqtSignal()   # F5 pressed while this window has the keyboard
    closedByUser = QtCore.pyqtSignal()       # window closed some other way (Alt+F4, taskbar)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("RevelateTW Lite - Projection")
        self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.FramelessWindowHint)
        self.resize(960, 540)
        self.setCursor(QtCore.Qt.BlankCursor)

    # ---- keys: the full-screen window takes the keyboard, so Esc/F5 must work here too ----
    def keyPressEvent(self, e):
        if e.key() == QtCore.Qt.Key_Escape:
            self.offRequested.emit()
        elif e.key() == QtCore.Qt.Key_F5:
            self.projectRequested.emit()
        else:
            super().keyPressEvent(e)

    def closeEvent(self, e):
        e.accept()
        self.closedByUser.emit()

    # ---- placing on a monitor ----
    def screen_rects(self):
        return [(s.geometry().x(), s.geometry().y(), s.geometry().width(), s.geometry().height())
                for s in QtWidgets.QApplication.screens()]

    def open_on(self, wanted=-1, primary_window=None):
        """Show full screen on the chosen display. Returns (index, extended)."""
        app = QtWidgets.QApplication
        screens = app.screens()
        rects = self.screen_rects()
        primary = screens.index(app.primaryScreen()) if app.primaryScreen() in screens else 0
        if primary_window is not None and primary_window.windowHandle() is not None:
            cur = primary_window.windowHandle().screen()
            if cur in screens:
                primary = screens.index(cur)
        idx, ext = layout.pick_display(rects, primary, wanted)
        g = screens[idx].geometry()
        self.setGeometry(g)
        self.show()
        if self.windowHandle() is not None:
            self.windowHandle().setScreen(screens[idx])
        self.setGeometry(g)
        if ext or len(screens) == 1:
            self.showFullScreen()
        else:
            self.showNormal()   # only one screen: do not cover the operator window
            self.resize(960, 540)
        return idx, ext
