"""Visual theme for RevelateTW Lite: one stylesheet plus the cosmetic TV frame.

Looks only. Nothing here changes layout order, signals or behaviour. Colours, sizes and spacing come
from the shared design tokens (revelatetw.ui_tokens). Plain Qt style sheets only (PyQt5 5.15, no
effects or shaders), so it stays light on a 2 GB Windows 8.1 32-bit machine.
"""
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
        rad=RADIUS, rc=RADIUS_CTL)


class TvFrame(QtWidgets.QWidget):
    """Cosmetic TV bezel drawn AROUND a widget. It only adds margins and paints; the wrapped preview
    keeps its own 16:9 shape, content and size rules, and projection never sees this frame."""

    BEZEL = 10   # px of bezel on each side

    def __init__(self, inner, parent=None):
        super().__init__(parent)
        self.on_air = False
        lay = QtWidgets.QVBoxLayout(self)
        m = self.BEZEL
        lay.setContentsMargins(m, m, m, m + 6)   # slightly thicker chin, like a TV
        lay.setSpacing(0)
        lay.addWidget(inner)
        sp = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        sp.setHeightForWidth(True)
        self.setSizePolicy(sp)

    def set_on_air(self, on):
        on = bool(on)
        if on != self.on_air:
            self.on_air = on
            self.update()

    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)
        r = QtCore.QRectF(self.rect()).adjusted(1, 1, -1, -1)
        grad = QtGui.QLinearGradient(r.topLeft(), r.bottomLeft())
        grad.setColorAt(0.0, QtGui.QColor("#2a3346"))
        grad.setColorAt(1.0, QtGui.QColor("#141a27"))
        p.setBrush(QtGui.QBrush(grad))
        p.setPen(QtGui.QPen(QtGui.QColor("#ef4444" if self.on_air else C.border_hover), 2 if self.on_air else 1))
        p.drawRoundedRect(r, FRAME_RADIUS, FRAME_RADIUS)
        # thin inner rim around the screen
        m = self.BEZEL - 2
        inner = QtCore.QRectF(self.rect()).adjusted(m, m, -m, -(m + 6))
        p.setBrush(QtCore.Qt.NoBrush)
        p.setPen(QtGui.QPen(QtGui.QColor("#05080f"), 2))
        p.drawRoundedRect(inner, 4, 4)
        # power LED on the chin
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(QtGui.QColor("#ef4444" if self.on_air else "#475569"))
        p.drawEllipse(QtCore.QPointF(r.center().x(), r.bottom() - 5), 2, 2)
