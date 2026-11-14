"""Small tab-switch animations for RevelateTW Lite (plain PyQt5, light on old PCs).

1. Tab button slide: the existing selected-tab look (gold top border, text colour, fill from the
   normal stylesheet) glides from the old tab to the new one. It is painted by the tab bar itself
   with the same style, so there is no extra widget and no separate yellow line. When nothing is
   animating, painting is exactly the normal Qt/stylesheet painting.
2. Page content: a short fade-in on the newly shown page.

Lifetime rules (these avoid the old "wrapped C/C++ object has been deleted" crash):
- the tab bar and the tab widget each own exactly ONE QVariantAnimation, created once, parented to
  the owner, reused for every switch, never DeleteWhenStopped and never given a target object;
- the fade's opacity effect is created per switch and only referenced by the owner; it is removed
  (and the Python reference dropped) after the animation is stopped.
Looks only: tab order, signals, quick controls and projection are untouched.
"""
import os

from PyQt5 import QtCore, QtWidgets

SLIDE_MS = 180
FADE_MS = 150
FADE_START = 0.0


def animations_enabled():
    """On by default. Set REVELATELITE_NO_TAB_ANIMATION=1 to opt out."""
    return not os.environ.get("REVELATELITE_NO_TAB_ANIMATION")


class AnimatedTabBar(QtWidgets.QTabBar):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._from = -1          # tab the highlight is leaving
        self._to = -1            # tab the highlight is arriving at
        self._t = 1.0            # 0..1 progress
        self._last = self.currentIndex()
        self._anim = QtCore.QVariantAnimation(self)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setDuration(SLIDE_MS)
        self._anim.setEasingCurve(QtCore.QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._on_value)
        self._anim.finished.connect(self._on_finished)
        self.currentChanged.connect(self._on_current)

    def sliding(self):
        anim = self.__dict__.get("_anim")
        return anim is not None and anim.state() == QtCore.QAbstractAnimation.Running

    def _end(self):
        anim = self.__dict__.get("_anim")      # may be gone while Python/Qt tear the widget down
        if anim is None:
            return
        anim.stop()
        self._from = self._to = -1
        self._t = 1.0
        self.update()

    def _on_value(self, v):
        self._t = float(v)
        self.update()

    def _on_finished(self):
        self._from = self._to = -1
        self._t = 1.0
        self.update()

    def _on_current(self, i):
        old, self._last = self._last, i
        self._anim.stop()
        if not (animations_enabled() and self.isVisible() and self.isEnabled()
                and 0 <= old < self.count() and 0 <= i < self.count() and old != i
                and self.tabRect(old).isValid() and self.tabRect(i).isValid()):
            self._from = self._to = -1
            self._t = 1.0
            self.update()
            return
        # rapid switch: always start from the previous tab's real slot (no stuck / stale state)
        self._from, self._to, self._t = old, i, 0.0
        self._anim.start()

    def tabInserted(self, index):
        self._end()
        self._last = self.currentIndex()
        super().tabInserted(index)

    def tabRemoved(self, index):
        self._end()
        self._last = self.currentIndex()
        super().tabRemoved(index)

    def resizeEvent(self, e):
        if self.sliding():
            self._end()            # geometry changed: finish at the real position
        super().resizeEvent(e)

    def hideEvent(self, e):
        self._end()
        super().hideEvent(e)

    def changeEvent(self, e):
        if e.type() == QtCore.QEvent.EnabledChange and not self.isEnabled():
            self._end()
        super().changeEvent(e)

    def paintEvent(self, e):
        n = self.count()
        if not self.sliding() or not (0 <= self._from < n and 0 <= self._to < n):
            super().paintEvent(e)
            return
        p = QtWidgets.QStylePainter(self)
        t = self._t
        a, b = self.tabRect(self._from), self.tabRect(self._to)
        r = QtCore.QRect(round(a.x() + (b.x() - a.x()) * t), round(a.y() + (b.y() - a.y()) * t),
                         round(a.width() + (b.width() - a.width()) * t),
                         round(a.height() + (b.height() - a.height()) * t))
        sel = self._to if t >= 0.5 else self._from      # which label gets the selected colour
        cur = self.currentIndex()

        def opt(i, selected):
            o = QtWidgets.QStyleOptionTab()
            self.initStyleOption(o, i)
            if selected:
                o.state |= QtWidgets.QStyle.State_Selected
            else:
                o.state &= ~QtWidgets.QStyle.State_Selected
            return o

        for i in range(n):                                  # every button in its normal look
            p.drawControl(QtWidgets.QStyle.CE_TabBarTabShape, opt(i, False))
        o = opt(cur, True)                                  # the real selected look, sliding
        o.rect = r
        p.drawControl(QtWidgets.QStyle.CE_TabBarTabShape, o)
        for i in range(n):
            lo = opt(i, i == sel)       # labels stay in their own tabs; only the highlight shape slides
            p.drawControl(QtWidgets.QStyle.CE_TabBarTabLabel, lo)


class AnimatedTabWidget(QtWidgets.QTabWidget):
    """QTabWidget with the sliding tab highlight and a page fade. Same API and signals."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTabBar(AnimatedTabBar())
        self._fx = None                # opacity effect of the page being faded
        self._fx_page = None
        self._fade = QtCore.QVariantAnimation(self)
        self._fade.setStartValue(FADE_START)
        self._fade.setEndValue(1.0)
        self._fade.setDuration(FADE_MS)
        self._fade.setEasingCurve(QtCore.QEasingCurve.OutCubic)
        self._fade.valueChanged.connect(self._on_fade)
        self._fade.finished.connect(self._clear_fx)
        self.currentChanged.connect(self._on_current)

    def fading(self):
        fade = self.__dict__.get("_fade")
        return fade is not None and fade.state() == QtCore.QAbstractAnimation.Running

    def _on_fade(self, v):
        fx = self._fx
        if fx is not None:
            fx.setOpacity(float(v))

    def _clear_fx(self):
        """Stop first, then remove the effect from its page and drop our reference."""
        fade = self.__dict__.get("_fade")
        if fade is not None:
            fade.stop()
        page, self._fx, self._fx_page = self._fx_page, None, None
        if page is not None:
            page.setGraphicsEffect(None)      # Qt deletes the effect; nothing else references it

    def _on_current(self, i):
        self._clear_fx()                        # rapid switch: finish the previous fade cleanly
        page = self.widget(i)
        if page is None or not (animations_enabled() and self.isVisible() and self.isEnabled()):
            return
        fx = QtWidgets.QGraphicsOpacityEffect(page)
        fx.setOpacity(FADE_START)
        page.setGraphicsEffect(fx)
        self._fx, self._fx_page = fx, page
        self._fade.start()

    def resizeEvent(self, e):
        if self.fading():
            self._clear_fx()
        bar = self.tabBar()
        if bar is not None and bar.sliding():
            bar._end()               # window resized mid-slide: settle on the real tab position
        super().resizeEvent(e)

    def hideEvent(self, e):
        self._clear_fx()
        super().hideEvent(e)
