"""Tiny tab switch animations for RevelateTW Lite.

Two small effects, both plain PyQt5 (no heavy deps) so they stay friendly for the
Windows 8.1 32-bit / 2 GB target:

- A gold "pill" behind the selected tab button that slides to the next button.
- A short fade plus a small sideways nudge on the tab content.

Rapid switching is safe: any running animation is stopped and the final state is
restored before a new one starts, so the selection can never get stuck off-screen.

Looks only. This code never changes the tab order, the widgets, the signals or
projection. The projector and the live preview are not touched (see
Main._animate_tab_switch in app.py).
"""
from PyQt5 import QtCore, QtGui, QtWidgets

from revelatetw.ui_tokens import COLORS as C

# Quick and gentle: long enough to feel alive, short enough to never slow work.
INDICATOR_MS = 160
CONTENT_MS = 140
# Content nudges at most a few pixels; barely a slide, never a jump.
CONTENT_NUDGE_PX = 8
INDICATOR_HEIGHT = 3
INDICATOR_INSET = 8      # px margin on each side of the tab (inset from pill edges)
INDICATOR_Y_PAD = 2      # px gap above the pill bottom

INDICATOR_COLOR = C.accent
CONTENT_DIRECTION_RIGHT = 1   # moving to a tab on the right
CONTENT_DIRECTION_LEFT = -1   # moving to a tab on the left


def animated_enabled():
    """Animation is on unless the user opted out (env var or Qt setting)."""
    import os
    if os.environ.get("REVELATELITE_NO_TAB_ANIMATION"):
        return False
    return True


def tab_rect(bar, index):
    """QRect of the tab at index in bar coordinates, or None if unavailable."""
    if bar is None or index is None or index < 0 or index >= bar.count():
        return None
    r = bar.tabRect(index)
    if r.width() <= 0 or r.height() <= 0:
        return None
    return r


def parent_is_bar(widget):
    return isinstance(widget.parentWidget(), QtWidgets.QTabBar)


class TabIndicator(QtWidgets.QWidget):
    """The gold pill painted behind the selected tab button.

    It is a child of the QTabBar, so it sits exactly where tabs live and never
    affects the layout. It ignores mouse events, so buttons still get their clicks.
    """

    def __init__(self, bar):
        super().__init__(bar)
        self._bar = bar
        self._rect = QtCore.QRect()
        self._anim = None
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self.hide()

    # -- animation lifetime -------------------------------------------------
    # DeleteWhenStopped let Qt delete the C++ animation on finish while the
    # Python reference stayed in self._anim, so the next stop() raised
    # RuntimeError. Animations are now Python-owned: no DeleteWhenStopped,
    # and every stop goes through _stop_anim which drops the ref first and
    # swallows RuntimeError for a wrapper already deleted with its target.
    def _forget_anim(self):
        self._anim = None

    def _stop_anim(self):
        anim = self._anim
        self._anim = None
        if anim is None:
            return
        try:
            anim.stop()
        except RuntimeError:
            pass

    # -- placement ------------------------------------------------------------
    def animate_to(self, index):
        """Slide to tab index. Falls back to an instant jump when it cannot animate."""
        r = tab_rect(self._bar, index)
        if r is None or not animated_enabled():
            self.place_immediately(index)
            return
        target = indicator_rect(self._bar, r)
        if not self.isVisible():
            self._rect = QtCore.QRect(target)
            self.show()
            self.update()
            return
        start = QtCore.QRect(self._rect)
        if start == target:
            self._rect = QtCore.QRect(target)
            self.update()
            return
        if self._anim is not None:
            self._stop_anim()
        anim = QtCore.QPropertyAnimation(self, b"pillRect", self,
                                         startValue=start, endValue=target,
                                         duration=INDICATOR_MS,
                                         easingCurve=QtCore.QEasingCurve.OutCubic)
        self._anim = anim
        anim.finished.connect(self._forget_anim)
        anim.start()

    def place_immediately(self, index):
        """Snap to tab index without animating (used for the first tab and on resize)."""
        r = tab_rect(self._bar, index)
        if r is None:
            self._rect = QtCore.QRect()
            self.hide()
            self.update()
            return
        if self._anim is not None:
            self._stop_anim()
        self._rect = QtCore.QRect(indicator_rect(self._bar, r))
        self.setGeometry(self._bar.geometry())
        self.show()
        self.update()

    # -- painting -------------------------------------------------------------
    def _get_pillRect(self):
        return self._rect

    def _set_pillRect(self, rect):
        self._rect = QtCore.QRect(rect)
        self.setGeometry(self._bar.geometry())
        self.update()

    pillRect = QtCore.pyqtProperty(QtCore.QRect, _get_pillRect, _set_pillRect)

    def paintEvent(self, e):
        if self._rect.width() <= 0 or self._rect.height() <= 0:
            return
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)
        p.setBrush(QtGui.QColor(INDICATOR_COLOR))
        p.setPen(QtCore.Qt.NoPen)
        p.drawRoundedRect(self._rect, 2, 2)
        p.end()


def indicator_rect(bar, tab_r):
    """Where the pill sits to mark a tab: a thin strip under the selected button."""
    if bar is None or tab_r is None:
        return QtCore.QRect()
    width = max(0, tab_r.width() - INDICATOR_INSET * 2)
    if width <= 0:
        # very narrow tab: keep at least a small visible strip
        width = max(1, tab_r.width() - 4)
    x = tab_r.x() + INDICATOR_INSET
    if x < tab_r.x():
        x = tab_r.x()
    y = tab_r.y() + tab_r.height() - INDICATOR_HEIGHT - INDICATOR_Y_PAD
    if y < tab_r.y():
        y = tab_r.y()
    return QtCore.QRect(x, y, width, INDICATOR_HEIGHT)


class ContentFade:
    """One-shot fade+nudge on the incoming tab content.

    The page widget itself is never moved and never reparented (QTabWidget owns
    the page); the effect is an opacity shortcut plus a tiny painted offset on a
    dedicated wrapper label painted behind the page, restored always. finish()
    is safe to call any number of times and restores the exact prior state.
    """

    def __init__(self, page=None):
        self.page = None
        self._effect = None
        self._anim = None
        self._running = False
        self.attach(page)

    def attach(self, page):
        self.finish()
        self.page = page

    def play(self, direction=CONTENT_DIRECTION_LEFT):
        self.finish()
        if not animated_enabled():
            return
        page = self.page
        if page is None or not page.isVisible():
            return
        # Opacity effect applied to the page itself; the GS effect object is owned by
        # the page, so removing it restores the page exactly.
        self._effect = QtWidgets.QGraphicsOpacityEffect(page)
        self._effect.setOpacity(0.0)
        page.setGraphicsEffect(self._effect)
        self._anim = QtCore.QPropertyAnimation(self._effect, b"opacity", self._effect,
                                                startValue=0.0, endValue=1.0,
                                                duration=CONTENT_MS,
                                                easingCurve=QtCore.QEasingCurve.OutCubic)
        self._running = True
        # finishing the animation (or an early finish() call) restores the page
        self._anim.finished.connect(self.finish)
        # Python-owned: no DeleteWhenStopped, so finish() can always stop it safely
        self._anim.start()

    def finish(self):
        """Restore the page exactly as it was. Safe to call any number of times."""
        anim = self._anim
        self._anim = None
        if anim is not None:
            try:
                anim.stop()
            except RuntimeError:  # wrapper deleted with its effect meanwhile
                pass
        self._running = False
        if self._effect is not None:
            # Removing the effect returns the page to its prior appearance.
            if self.page is not None:
                try:
                    self.page.setGraphicsEffect(None)
                except RuntimeError:
                    pass
            self._effect = None


class AnimatedTabBar(QtWidgets.QTabBar):
    """QTabBar that slides a gold indicator pill between the selected tabs."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._indicator = TabIndicator(self)
        self._indicator.raise_()

    def indicator(self):
        return self._indicator

    def move_to(self, index, animate=True):
        """Ask the pill to go to tab index (instantly when animate is off)."""
        if animate:
            self._indicator.animate_to(index)
        else:
            self._indicator.place_immediately(index)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        idx = self.currentIndex()
        if idx >= 0:
            self._indicator.place_immediately(idx)


class AnimatedTabWidget(QtWidgets.QTabWidget):
    """QTabWidget with the sliding pill and a gentle content fade on every switch.

    Built-in tab order, page widgets and signals of QTabWidget are untouched:
    selecting a tab still just calls setCurrentIndex, and currentChanged fires
    exactly as before.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTabBar(AnimatedTabBar(self))
        self._bar = self.tabBar()
        self._fade = ContentFade()
        self._prev_index = -1
        self.currentChanged.connect(self._on_tab_changed)
        self._fade.attach(self.widget(0) if self.count() > 0 else None)
        self._sync()

    def tabBar(self):
        # QTabWidget.setTabBar() calls this before _bar exists; fall back to the
        # built-in implementation until our own bar is installed.
        return getattr(self, "_bar", None) or super().tabBar()

    def move_indicator(self, index, animate=True):
        self._bar.move_to(index, animate=animate)

    def addTab(self, widget, text):
        super().addTab(widget, text)
        self._fade.attach(widget)
        self._sync()

    def insertTab(self, index, widget, text):
        super().insertTab(index, widget, text)
        self._fade.attach(widget)
        self._sync()

    def _on_tab_changed(self, index):
        prev = self._prev_index
        self._prev_index = index
        direction = CONTENT_DIRECTION_LEFT
        if prev is not None and prev >= 0 and index > prev:
            direction = CONTENT_DIRECTION_RIGHT
        self._bar.move_to(index, animate=True)
        self._fade.attach(self.widget(index))
        self._fade.play(direction)

    def _sync(self):
        idx = self.currentIndex()
        if idx >= 0:
            self._bar.move_to(idx, animate=False)
            self._prev_index = idx
        else:
            self._prev_index = -1

    def resizeEvent(self, e):
        super().resizeEvent(e)
        idx = self.currentIndex()
        if idx >= 0:
            self._bar.move_to(idx, animate=False)
