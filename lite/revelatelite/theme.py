"""Visual theme for RevelateTW Lite: one stylesheet plus the cosmetic TV frame.

Looks only. Nothing here changes layout order, signals or behaviour. Colours, sizes and spacing come
from the shared design tokens (revelatetw.ui_tokens). Plain Qt style sheets only (PyQt5 5.15, no
effects or shaders), so it stays light on a 2 GB Windows 8.1 32-bit machine.
"""
import os

from PyQt5 import QtCore, QtGui, QtWidgets

from revelatetw.ui_tokens import COLORS as C, TYPE as T

RADIUS = 8        # cards and the larger shapes
RADIUS_CTL = 6    # buttons, inputs, tabs
FRAME_RADIUS = 16  # outer corner of the TV frame

_QSS = """
QWidget {{ background:{bg}; color:{text}; font-size:{body}px; }}
QToolTip {{ background:{raised}; color:{strong}; border:1px solid {bh}; padding:4px 6px; }}
QLabel {{ background:transparent; }}
QLabel#ref {{ color:{accent}; font-size:{emph}px; font-weight:bold; }}
QLabel#verse {{ font-size:{trans}px; }}
QLabel#status, QLabel#hint {{ color:{muted}; font-size:{cap}px; }}
QLabel#live {{ color:{lt}; background:{lbg}; border:1px solid {lb}; border-radius:{rc}px; padding:3px 8px; font-weight:bold; }}

QFrame#card {{ background:{alt}; border:1px solid {bcard}; border-radius:{rad}px; }}
QFrame#card QLabel, QFrame#card QCheckBox {{ background:transparent; }}
QGroupBox {{ background:{alt}; border:1px solid {bcard}; border-radius:{rad}px; margin-top:14px; padding:10px 8px 8px 8px; }}
QGroupBox::title {{ subcontrol-origin:margin; subcontrol-position:top left; left:12px; padding:0 6px; color:{muted}; background:{bg}; }}

QLineEdit, QComboBox, QSpinBox, QPlainTextEdit {{ background:{inp}; border:1px solid {bc}; padding:6px 8px; border-radius:{rc}px;
    selection-background-color:{accent}; selection-color:{on}; }}
QLineEdit:hover, QComboBox:hover, QSpinBox:hover, QPlainTextEdit:hover {{ border-color:{bh}; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QPlainTextEdit:focus {{ border:1px solid {accent}; }}
QLineEdit[invalid="true"], QLineEdit[invalid="true"]:focus {{ border:1px solid {dbd}; }}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {{ color:{dis}; border-color:{border}; }}
QComboBox {{ padding-right:24px; }}
QComboBox::drop-down {{ subcontrol-origin:padding; subcontrol-position:center right; width:22px; border:none;
    border-left:1px solid {border}; border-top-right-radius:{rc}px; border-bottom-right-radius:{rc}px; background:transparent; }}
QComboBox::down-arrow {{ width:0; height:0; border-left:4px solid transparent; border-right:4px solid transparent; border-top:5px solid {muted}; }}
QComboBox QAbstractItemView {{ background:{inp}; border:1px solid {bh}; selection-background-color:{sel}; selection-color:{accent}; outline:0; padding:2px; }}
QSpinBox::up-button, QSpinBox::down-button {{ width:16px; border:none; background:transparent; }}

QListWidget, QListView {{ background:{inp}; border:1px solid {bc}; border-radius:{rad}px; padding:4px; outline:0; }}
QListWidget::item {{ padding:7px 8px; border-radius:{rc}px; margin:1px 0; }}
QListWidget::item:hover {{ background:{raised}; }}
QListWidget::item:selected {{ background:{sel}; color:{accent}; border:1px solid {accsoft}; }}

QPushButton {{ background:{raised}; border:1px solid {bc}; padding:7px 14px; border-radius:{rc}px; min-height:16px; }}
QPushButton:hover {{ border-color:{bh}; background:{rh}; }}
QPushButton:pressed {{ background:{inp}; border-color:{bh}; }}
QPushButton:focus {{ border:1px solid {accent}; }}
QPushButton:disabled {{ color:{dis}; background:{alt}; border-color:{border}; }}
QPushButton#primary {{ background:{accent}; color:{on}; border:1px solid {accent}; font-weight:bold; }}
QPushButton#primary:hover {{ background:{acch}; border-color:{acch}; }}
QPushButton#primary:pressed {{ background:{accent}; }}
QPushButton#primary:disabled {{ background:{raised}; color:{dis}; border-color:{bc}; }}

QCheckBox {{ spacing:8px; background:transparent; }}
QCheckBox::indicator {{ width:16px; height:16px; border:1px solid {bc}; border-radius:4px; background:{inp}; }}
QCheckBox::indicator:hover {{ border-color:{bh}; }}
QCheckBox::indicator:checked {{ background:{accent}; border-color:{accent}; }}
QCheckBox::indicator:disabled {{ background:{alt}; border-color:{border}; }}

QTabWidget::pane {{ border:1px solid {bcard}; border-radius:{rad}px; background:{bg}; top:-1px; }}
QTabBar {{ background:transparent; }}
QTabBar::tab {{ background:{raised}; color:{muted}; padding:8px 12px; border:1px solid {bc}; border-bottom:none;
    border-top-left-radius:{rc}px; border-top-right-radius:{rc}px; margin-right:2px; }}
QTabBar::scroller {{ width:0; }}
QTabBar::tab:hover {{ color:{text}; border-color:{bh}; }}
QTabBar::tab:selected {{ background:{alt}; color:{accent}; border-color:{bcard}; border-top:2px solid {accent}; }}

QScrollArea {{ background:transparent; border:none; }}
QScrollBar:vertical {{ background:transparent; width:12px; margin:2px; }}
QScrollBar:horizontal {{ background:transparent; height:12px; margin:2px; }}
QScrollBar::handle:vertical {{ background:{bc}; border-radius:4px; min-height:28px; }}
QScrollBar::handle:horizontal {{ background:{bc}; border-radius:4px; min-width:28px; }}
QScrollBar::handle:hover {{ background:{bh}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width:0; height:0; background:none; border:none; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background:transparent; }}

QMessageBox, QDialog {{ background:{bg}; }}
QDialog#ImportBibleDialog {{ background:{bg}; }}
QDialog#ImportBibleDialog QFrame#ImportBibleHeader {{ background:{alt}; border:1px solid {bcard}; border-radius:{rad}px; }}
QDialog#ImportBibleDialog QFrame#ImportBibleHeader QLabel#ImportBibleTitle {{ color:{strong}; font-weight:bold; font-size:{emph}px; }}
QDialog#ImportBibleDialog QFrame#ImportBibleHeader QLabel#ImportBibleSub {{ color:{muted}; }}
QDialog#ImportBibleDialog QFrame#ImportBibleSection {{ background:{alt}; border:1px solid {bcard}; border-radius:{rad}px; }}
QDialog#ImportBibleDialog QFrame#ImportBibleSection QLabel#ImportBibleSectionTitle {{ color:{accent}; font-weight:bold; }}
QDialog#ImportBibleDialog QLabel#ImportBibleHelp {{ color:{muted}; }}
QDialog#ImportBibleDialog QLabel#ImportBibleHint {{ color:{muted}; font-size:{cap}px; }}
QDialog#ImportBibleDialog QLabel#ImportBibleStatus {{ color:{accent}; font-size:{cap}px; font-weight:bold; }}
QDialog#ImportBibleDialog QPushButton#ImportBibleBrowse {{ background:{accent}; color:{on}; border:1px solid {accent}; font-weight:bold; }}
QDialog#ImportBibleDialog QPushButton#ImportBibleBrowse:hover {{ background:{acch}; border-color:{acch}; }}
QDialog#ImportBibleDialog QPlainTextEdit#ImportBibleReport {{ background:{inp}; color:{text}; border:1px solid {bc}; border-radius:{rc}px; padding:6px 8px; selection-background-color:{accent}; selection-color:{on}; }}
QDialog#ImportBibleDialog QPlainTextEdit#ImportBibleReport:focus {{ border:1px solid {accent}; }}
QDialog#ImportBibleDialog QLabel#ImportBiblePreview {{ color:{muted}; font-weight:bold; }}
QDialog#ImportBibleDialog QLineEdit:focus {{ border:1px solid {accent}; }}
QDialog#ImportBibleDialog QPushButton#ImportBibleCancel {{ background:{raised}; border:1px solid {bc}; }}
QDialog#ImportBibleDialog QPushButton#ImportBibleCancel:hover {{ border-color:{bh}; background:{rh}; }}
QMenu {{ background:{alt}; border:1px solid {bc}; padding:4px; }}
QMenu::item {{ padding:6px 18px; border-radius:4px; }}
QMenu::item:selected {{ background:{sel}; color:{accent}; }}
"""


def build_qss():
    return _QSS.format(
        bg=C.bg, text=C.text, strong=C.text_strong, body=T.body, inp=C.surface_input, bc=C.border_control,
        sel=C.selected_bg, accent=C.accent, raised=C.surface_raised, rh="#232d42", bh=C.border_hover,
        dis=C.text_disabled, on=C.accent_on, acch=C.accent_hover, alt=C.surface_alt, bcard=C.border_card,
        border=C.border, emph=T.emphasis, trans=T.transcript, muted=C.text_muted, cap=T.caption,
        lt=C.live_on_text, lbg=C.live_on_bg, lb=C.live_on_border, accsoft=C.accent_soft,
        rad=RADIUS, rc=RADIUS_CTL, dbd=C.danger_border)


def _mix(a, b, t):
    """Blend colour a toward b by t (0..1)."""
    return QtGui.QColor(int(a.red() + (b.red() - a.red()) * t), int(a.green() + (b.green() - a.green()) * t),
                        int(a.blue() + (b.blue() - a.blue()) * t))


class TvFrame(QtWidgets.QWidget):
    """Cosmetic TV bezel drawn AROUND a widget. It only adds margins and paints; the wrapped preview
    keeps its own 16:9 shape, content and size rules, and projection never sees this frame."""

    BEZEL = 10   # px of bezel on each side

    def __init__(self, inner, parent=None):
        super().__init__(parent)
        self.on_air = False
        self._glow = 0.0
        self._anim = None
        lay = QtWidgets.QVBoxLayout(self)
        m = self.BEZEL
        lay.setContentsMargins(m, m, m, m + 6)   # slightly thicker chin, like a TV
        lay.setSpacing(0)
        lay.addWidget(inner)
        sp = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        sp.setHeightForWidth(True)
        self.setSizePolicy(sp)

    GLOW_IN_MS = 450    # light switching on: quick warm rise
    GLOW_OUT_MS = 750   # light switching off: slower fade, like a cooling bulb

    def _get_glow(self):
        return self._glow

    def _set_glow(self, v):
        v = max(0.0, min(1.0, float(v)))
        if abs(v - self._glow) > 0.001 or v in (0.0, 1.0):
            self._glow = v
            self.update()

    glow = QtCore.pyqtProperty(float, _get_glow, _set_glow)   # 0 = off, 1 = fully lit (paint only)

    def set_on_air(self, on):
        """Only a real on/off change starts the glow fade; repeating the same state does nothing."""
        on = bool(on)
        if on == self.on_air:
            return
        self.on_air = on
        target = 1.0 if on else 0.0
        if os.environ.get("REVELATELITE_NO_GLOW_ANIMATION") or not self.isVisible():
            self._stop_glow()
            self._set_glow(target)
            return
        if self._anim is None:   # one reused animation, created on first use
            self._anim = QtCore.QPropertyAnimation(self, b"glow", self)
            self._anim.setEasingCurve(QtCore.QEasingCurve.InOutSine)
        self._anim.stop()
        self._anim.setDuration(int((self.GLOW_IN_MS if on else self.GLOW_OUT_MS) * abs(target - self._glow)) + 40)
        self._anim.setStartValue(self._glow)   # rapid toggles continue from the current brightness
        self._anim.setEndValue(target)
        self._anim.start()

    def _stop_glow(self):
        if self._anim is not None:
            self._anim.stop()

    def hideEvent(self, e):
        self._stop_glow()
        self._set_glow(1.0 if self.on_air else 0.0)   # never leave a half-lit frame while hidden
        super().hideEvent(e)

    def closeEvent(self, e):
        self._stop_glow()
        super().closeEvent(e)

    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)
        r = QtCore.QRectF(self.rect()).adjusted(1, 1, -1, -1)
        grad = QtGui.QLinearGradient(r.topLeft(), r.bottomLeft())
        grad.setColorAt(0.0, QtGui.QColor("#2a3346"))
        grad.setColorAt(1.0, QtGui.QColor("#141a27"))
        p.setBrush(QtGui.QBrush(grad))
        g = self._glow
        ring = _mix(QtGui.QColor(C.border_hover), QtGui.QColor(C.accent), g)
        p.setPen(QtGui.QPen(ring, 1 + g))
        p.drawRoundedRect(r, FRAME_RADIUS, FRAME_RADIUS)
        if g > 0.01:   # warm halo: a few soft translucent strokes just inside the ring (no blur, no layout change)
            p.setBrush(QtCore.Qt.NoBrush)
            for i, (w, a) in enumerate(((7.0, 0.07), (4.5, 0.11), (2.5, 0.16))):
                c = QtGui.QColor(C.accent)
                c.setAlphaF(a * g)
                p.setPen(QtGui.QPen(c, w))
                p.drawRoundedRect(r.adjusted(1 + w / 2, 1 + w / 2, -1 - w / 2, -1 - w / 2), FRAME_RADIUS - w / 2, FRAME_RADIUS - w / 2)
            # warm light wash across the bezel: brighter at the top, fading down (gives the metal some depth)
            wash = QtGui.QLinearGradient(r.topLeft(), r.bottomLeft())
            top = QtGui.QColor(C.accent)
            top.setAlphaF(0.20 * g)
            bot = QtGui.QColor(C.accent)
            bot.setAlphaF(0.05 * g)
            wash.setColorAt(0.0, top)
            wash.setColorAt(1.0, bot)
            p.setPen(QtCore.Qt.NoPen)
            p.setBrush(QtGui.QBrush(wash))
            p.drawRoundedRect(r, FRAME_RADIUS, FRAME_RADIUS)
            # controlled bright edge: a thin pale-gold highlight just inside the ring
            hi = QtGui.QColor("#fff1c2")
            hi.setAlphaF(0.55 * g)
            p.setBrush(QtCore.Qt.NoBrush)
            p.setPen(QtGui.QPen(hi, 1))
            p.drawRoundedRect(r.adjusted(2.2, 2.2, -2.2, -2.2), FRAME_RADIUS - 2, FRAME_RADIUS - 2)
            p.setBrush(QtGui.QBrush(grad))
        # thin inner rim around the screen
        m = self.BEZEL - 2
        inner = QtCore.QRectF(self.rect()).adjusted(m, m, -m, -(m + 6))
        p.setBrush(QtCore.Qt.NoBrush)
        p.setPen(QtGui.QPen(QtGui.QColor("#05080f"), 2))
        p.drawRoundedRect(inner, 4, 4)
        if g > 0.01:   # the screen rim picks up a faint gold light, keeping the double-line look
            rim = QtGui.QColor(C.accent)
            rim.setAlphaF(0.45 * g)
            p.setPen(QtGui.QPen(rim, 1))
            p.drawRoundedRect(inner.adjusted(-1.5, -1.5, 1.5, 1.5), 5, 5)
        # power LED on the chin
        p.setPen(QtCore.Qt.NoPen)
        led = QtCore.QPointF(r.center().x(), r.bottom() - 5)
        if g > 0.01:
            halo = QtGui.QColor(C.accent)
            halo.setAlphaF(0.28 * g)
            p.setBrush(halo)
            p.drawEllipse(led, 4.5, 4.5)
        p.setBrush(_mix(QtGui.QColor("#475569"), QtGui.QColor(C.accent), g))
        p.drawEllipse(led, 2, 2)
