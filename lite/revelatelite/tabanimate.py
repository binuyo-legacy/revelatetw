"""Tiny tab switch animations for RevelateTW Lite.

One small effect, plain PyQt5 (no heavy deps) so it stays friendly for the
Windows 8.1 32-bit / 2 GB target:

- A short fade on the incoming tab content.

Rapid switching is safe: any running animation is stopped and the final state is
restored before a new one starts, so the selection can never get stuck off-screen.

Looks only. This code never changes the tab order, the widgets, the signals or
projection. The projector and the live preview are not touched (see
Main._animate_tab_switch in app.py).

Selected-tab styling note (operator request, Nov 2026): the selected tab keeps
its original treatment from theme.py, a gold top border and gold text via
QTabBar::tab:selected. A previous version also painted a separate gold strip
under the label (TabIndicator). That extra bottom line was removed by request;
do not re-add it without asking. To tune the fade, change CONTENT_MS below.
"""
from PyQt5 import QtCore, QtGui, QtWidgets

# Quick and gentle: long enough to feel alive, short enough to never slow work.
CONTENT_MS = 140
CONTENT_DIRECTION_RIGHT = 1   # moving to a tab on the right
CONTENT_DIRECTION_LEFT = -1   # moving to a tab on the left

# Backwards-compatible names kept for callers/tests that read them, but the
# bottom indicator they described no longer exists.
INDICATOR_MS = 0
INDICATOR_HEIGHT = 0


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


def indicator_rect(bar, tab_r):
    """Deprecated: empty rect. The bottom gold strip was removed; the selected
    tab's gold stays as the top border/text from theme.py QTabBar::tab:selected."""
    return QtCore.QRect()


class TabIndicator(QtWidgets.QWidget):
    """Retained as a hidden no-op so older callers stop erroring.

    It never paints, never shows, and holds no animation. The crash fix from
    3c311bb is preserved by keeping _stop_anim/_forget_anim safe on a missing
    animation. New code should not use this class.
    """

    def __init__(self, bar):
        super().__init__(bar)
        self._bar = bar
        self._rect = QtCore.QRect()
        self._anim = None
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self.hide()

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

    def animate_to(self, index):
        self._stop_anim()
        self._rect = QtCore.QRect()
        self.hide()
        self.update()

    def place_immediately(self, index):
        self._stop_anim()
        self._rect = QtCore.QRect()
        self.hide()
        self.update()

    def _get_pillRect(self):
        return self._rect

    def _set_pillRect(self, rect):
        self._rect = QtCore.QRect()

    pillRect = QtCore.pyqtProperty(QtCore.QRect, _get_pillRect, _set_pillRect)

    def paintEvent(self, e):
        return


class ContentFade:
    """One-shot fade on the incoming tab content.

    The page widget itself is never moved and never reparented (QTabWidget owns
    the page); the effect is an opacity shortcut, restored always. finish()
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
        self._effect = QtWidgets.QGraphicsOpacityEffect(page)
        self._effect.setOpacity(0.0)
        page.setGraphicsEffect(self._effect)
        self._anim = QtCore.QPropertyAnimation(self._effect, b"opacity", self._effect,
                                                startValue=0.0, endValue=1.0,
                                                duration=CONTENT_MS,
                                                easingCurve=QtCore.QEasingCurve.OutCubic)
        self._running = True
        self._anim.finished.connect(self.finish)
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
            if self.page is not None:
                try:
                    self.page.setGraphicsEffect(None)
                except RuntimeError:
                    pass
            self._effect = None


class AnimatedTabBar(QtWidgets.QTabBar):
    """QTabBar kept so tab order/widgets/signals are unchanged.

    No gold pill is painted any more; selection styling comes from theme.py.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._indicator = TabIndicator(self)

    def indicator(self):
        return self._indicator

    def move_to(self, index, animate=True):
        self._indicator.hide()
        self._indicator.place_immediately(index)

    def resizeEvent(self, e):
        super().resizeEvent(e)


class AnimatedTabWidget(QtWidgets.QTabWidget):
    """QTabWidget with a gentle content fade on every switch.

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
        self._fade.attach(self.widget(index))
        self._fade.play(direction)

    def _sync(self):
        idx = self.currentIndex()
        self._prev_index = idx if idx >= 0 else -1

    def resizeEvent(self, e):
        super().resizeEvent(e)
