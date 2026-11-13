"""The projection window: borderless, goes to the extended display, auto-sizes the verse."""
from PyQt5 import QtCore, QtGui, QtWidgets

from . import layout, settings


class ProjectionWindow(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RevelateTW Lite - Projection")
        self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.FramelessWindowHint)
        self.ref = ""
        self.body = ""
        self.credit = ""
        self.live = False          # False = black screen
        self.theme = "navy"
        self.scale = 100
        self.show_ref = True
        self.resize(960, 540)
        self.setCursor(QtCore.Qt.BlankCursor)

    # ---- content ----
    def set_content(self, ref, body, credit=""):
        self.ref, self.body, self.credit = ref, body, credit
        self.live = True
        self.update()

    def blank(self):
        self.live = False
        self.update()

    def set_style(self, theme, scale, show_ref):
        self.theme, self.scale, self.show_ref = theme, scale, show_ref
        self.update()

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

    # ---- drawing ----
    def paintEvent(self, _):
        bg, fg, refc = settings.THEMES.get(self.theme, settings.THEMES["navy"])
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.TextAntialiasing)
        if not self.live or not self.body:
            p.fillRect(self.rect(), QtGui.QColor("#000000"))
            return
        p.fillRect(self.rect(), QtGui.QColor(bg))
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
            f = QtGui.QFont("Georgia")
            f.setPixelSize(size)
            r = QtGui.QFontMetrics(f).boundingRect(0, 0, text_area.width(), 100000, flags, self.body)
            return r.height() <= text_area.height()

        top = int(h * 0.12 * self.scale / 100)
        size = layout.fit_font_size(fits, 14, max(16, top))
        f = QtGui.QFont("Georgia")
        f.setPixelSize(size)
        p.setFont(f)
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

    def resizeEvent(self, e):
        self.update()
        super().resizeEvent(e)
