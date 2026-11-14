"""The projection window: borderless, goes to the extended display, auto-sizes the verse."""
from PyQt5 import QtCore, QtGui, QtWidgets

from . import background, layout, settings, transitions


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
        self.outline_on, self.outline_color, self.outline_px = False, "", 3
        self._bgp = background.Painter()

    # ---- content ----
    def set_content(self, ref, body, credit=""):
        self.ref, self.body, self.credit = ref, body, credit
        self.live = True
        self.update()

    def blank(self):
        self.live = False
        self.update()

    def set_style(self, theme, scale, show_ref, font_family="Georgia", bold=False, bg_color="", text_color="", bg_spec=None,
                  outline_on=False, outline_color="", outline_px=3):
        self.outline_on, self.outline_color, self.outline_px = bool(outline_on), outline_color, outline_px
        self.theme, self.scale, self.show_ref = theme, scale, show_ref
        self.font_family, self.bold, self.bg_color, self.text_color = font_family, bold, bg_color, text_color
        self.bg_spec = bg_spec or background.spec_from({})
        self.update()

    # ---- drawing ----
    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        self._draw(p, self.rect())

    def snapshot(self, size):
        """The slide as it looks right now, drawn into a plain pixmap (used by transitions)."""
        pm = QtGui.QPixmap(size)
        p = QtGui.QPainter(pm)
        self._draw(p, QtCore.QRect(0, 0, size.width(), size.height()))
        p.end()
        return pm

    def _text(self, p, rect, flags, text, fg, h):
        """Draw text in the current font/pen colour, with an outline when switched on.
        The outline is the same text stamped in a ring around the real one (plain painting, works for
        wrapped text and on any background), then the text itself on top."""
        if self.outline_on:
            oc = QtGui.QColor(settings.resolve_outline(fg, self.outline_color))
            keep = p.pen()
            p.setPen(oc)
            for dx, dy in settings.outline_offsets(settings.outline_pixels(h, self.outline_px)):
                p.drawText(rect.translated(dx, dy), flags, text)
            p.setPen(keep)
        p.drawText(rect, flags, text)

    def _draw(self, p, rect):
        kind = self.bg_spec[0]
        bg, fg, refc = settings.resolve_colors(self.theme, self.bg_color, self.text_color)
        if kind == "gradient":       # text colour follows the average of the two colours
            bg, fg, refc = settings.resolve_colors(self.theme, background.mix(self.bg_spec[1], self.bg_spec[2]), self.text_color)
        elif kind == "image" and background.load_image(self.bg_spec[4])[0] is not None:
            bg, fg, refc = settings.resolve_colors(self.theme, "#0b0f19", self.text_color)
            bg = self.bg_color if settings.valid_color(self.bg_color) else bg
        p.setRenderHint(QtGui.QPainter.TextAntialiasing)
        if not self.live or not self.body:
            p.fillRect(rect, QtGui.QColor("#000000"))
            return
        self._bgp.paint(p, rect, self.bg_spec, bg)
        w, h = rect.width(), rect.height()
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
            self._text(p, QtCore.QRect(area.x(), area.y() + area.height() - ref_h + int(h * 0.02),
                                       area.width(), ref_h), QtCore.Qt.AlignCenter, self.ref, refc, h)
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
        self._text(p, text_area, flags, self.body, fg, h)
        if self.credit:
            f2 = QtGui.QFont("Segoe UI")
            f2.setPixelSize(max(11, int(h * 0.02)))
            p.setFont(f2)
            p.setPen(QtGui.QColor(fg))
            p.setOpacity(0.55)
            self._text(p, QtCore.QRect(0, h - int(h * 0.04) - 4, w, int(h * 0.04)),
                       QtCore.Qt.AlignCenter, self.credit, fg, h)

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
        self._tx = None        # running transition: dict(effect, direction, old, new, p, after)
        self._anim = None
        self._old_was_live = False

    # ---- transitions (only this window; the in-app preview is never animated) ----
    @property
    def transitioning(self):
        return self._tx is not None

    def finish_transition(self):
        """Jump to the end of a running transition (also runs its 'after' step, e.g. hide)."""
        tx, self._tx = self._tx, None
        if self._anim is not None:
            a, self._anim = self._anim, None
            a.stop()
            a.deleteLater()
        if tx is not None:
            self.update()
            if tx.get("after"):
                tx["after"]()

    def transition(self, plan, change, after=None):
        """Run change() (which applies the new content / shows the window) with an animation.
        old picture = what is on screen now (black if the window is hidden); new = after change().
        after() runs when the animation ends (immediately for an instant plan)."""
        self.finish_transition()
        self._old_was_live = bool(self.live and self.isVisible())
        old = self.snapshot(self.size()) if self._old_was_live else None
        if plan.animated:
            self._tx = {"old": old, "new": None, "p": 0.0, "effect": plan.effect,
                        "direction": plan.direction, "after": after}
        change()
        if not plan.animated:
            if after:
                after()
            return
        size = self.size()
        if old is None:
            old = QtGui.QPixmap(size)
            old.fill(QtGui.QColor("#000000"))
        self._tx["old"] = old
        self._tx["new"] = self.snapshot(size)
        a = QtCore.QVariantAnimation(self)
        a.setStartValue(0.0)
        a.setEndValue(1.0)
        a.setDuration(plan.ms)
        a.valueChanged.connect(self._tx_step)
        a.finished.connect(self.finish_transition)
        self._anim = a
        a.start()
        self.update()

    def resizeEvent(self, e):
        tx = self._tx
        if tx is not None and tx.get("new") is not None and self.width() > 0 and self.height() > 0:
            tx["new"] = self.snapshot(self.size())      # went full screen mid-animation: redraw crisp
            if tx["old"] is not None and tx["old"].size() != self.size() and not self._old_was_live:
                tx["old"] = QtGui.QPixmap(self.size())
                tx["old"].fill(QtGui.QColor("#000000"))
        super().resizeEvent(e)

    def _tx_step(self, v):
        if self._tx is not None:
            self._tx["p"] = transitions.ease(float(v))
            self.update()

    def paintEvent(self, e):
        tx = self._tx
        if tx is None:
            return super().paintEvent(e)
        p = QtGui.QPainter(self)
        r = self.rect()
        w, h = r.width(), r.height()
        p.fillRect(r, QtGui.QColor("#000000"))
        old, new, pr, d = tx["old"], tx["new"], tx["p"], tx["direction"]
        if old is None:      # first frame of a show: black, nothing leaks before the animation starts
            return
        eff = tx["effect"]
        if new is None:
            p.drawPixmap(r, old)
        elif eff == "fade":
            a_old, a_new = transitions.fade_alphas(pr)
            p.setOpacity(a_old)
            p.drawPixmap(r, old)
            p.setOpacity(a_new)
            p.drawPixmap(r, new)
        elif eff == "dissolve":
            p.drawPixmap(r, old)
            p.setOpacity(transitions.dissolve_alpha(pr))
            p.drawPixmap(r, new)
        elif eff == "slide":
            (ox, oy), (nx, ny) = transitions.slide_offsets(d, w, h, pr)
            p.drawPixmap(QtCore.QRect(ox, oy, w, h), old)
            p.drawPixmap(QtCore.QRect(nx, ny, w, h), new)
        elif eff == "zoom":
            (os_, oa), (ns, na) = transitions.zoom_states(pr)
            for pm, sc, al in ((old, os_, oa), (new, ns, na)):
                if al > 0:
                    p.setOpacity(al)
                    zw, zh = int(round(w * sc)), int(round(h * sc))
                    p.drawPixmap(QtCore.QRect((w - zw) // 2, (h - zh) // 2, zw, zh), pm)
        elif eff in ("checkerboard", "mosaic"):      # many small squares of the new picture over the old one
            p.drawPixmap(r, old)
            tiles = (transitions.checkerboard_rects(w, h, pr) if eff == "checkerboard"
                     else transitions.mosaic_rects(w, h, pr))
            for x, y, rw, rh in tiles:
                if rw > 0 and rh > 0:
                    p.drawPixmap(x, y, new, x, y, rw, rh)
        else:                # wipe, blinds, open, diagonal, iris, clock: new picture shown through a clip over the old one
            p.drawPixmap(r, old)
            if eff == "wipe":
                rects = [transitions.wipe_rect(d, w, h, pr)]
            elif eff == "blinds":
                rects = transitions.blinds_rects(d, w, h, pr)
            elif eff in ("diagonal", "iris", "clock"):
                path = QtGui.QPainterPath()
                if eff == "diagonal":
                    pts = transitions.diagonal_polygon(d, w, h, pr)
                    if len(pts) >= 3:
                        path.addPolygon(QtGui.QPolygonF([QtCore.QPointF(x, y) for x, y in pts]))
                elif eff == "iris":
                    cx, cy, rad = transitions.iris_circle(w, h, pr)
                    if rad > 0:
                        path.addEllipse(QtCore.QPointF(cx, cy), rad, rad)
                else:
                    deg = transitions.clock_degrees(pr)
                    if deg > 0:
                        rad = transitions.iris_circle(w, h, 1)[2]
                        path.moveTo(w / 2.0, h / 2.0)
                        path.arcTo(QtCore.QRectF(w / 2.0 - rad, h / 2.0 - rad, 2 * rad, 2 * rad), 90, -deg)
                        path.closeSubpath()
                if not path.isEmpty():
                    p.setClipPath(path)
                    p.drawPixmap(r, new)
                return
            else:
                rects = [transitions.open_rect(d, w, h, pr)]
            reg = QtGui.QRegion()
            for x, y, rw, rh in rects:
                if rw > 0 and rh > 0:
                    reg = reg.united(QtGui.QRegion(x, y, rw, rh))
            p.setClipRegion(reg)
            p.drawPixmap(r, new)

    # ---- keys: the full-screen window takes the keyboard, so Esc/F5 must work here too ----
    def keyPressEvent(self, e):
        if e.key() == QtCore.Qt.Key_Escape:
            self.offRequested.emit()
        elif e.key() == QtCore.Qt.Key_F5:
            self.projectRequested.emit()
        else:
            super().keyPressEvent(e)

    def closeEvent(self, e):
        self._tx_after_cancel()
        e.accept()
        self.closedByUser.emit()

    def _tx_after_cancel(self):
        """Window is closing: drop a running transition without running its after-step."""
        if self._tx is not None:
            self._tx["after"] = None
        self.finish_transition()

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
