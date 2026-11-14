"""Tiny fade-in for the inline reference hint (one opacity effect, one 220 ms animation, no idle cost)."""
from PyQt5 import QtCore, QtWidgets


class HintFade(QtCore.QObject):
    def __init__(self, label):
        super().__init__(label)
        self.label = label
        self._fx = None
        self._anim = None

    def play(self):
        self.stop()
        self._fx = QtWidgets.QGraphicsOpacityEffect(self.label)
        self._fx.setOpacity(0.0)
        self.label.setGraphicsEffect(self._fx)
        self._anim = QtCore.QPropertyAnimation(self._fx, b"opacity", self)
        self._anim.setDuration(220)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()

    def stop(self):
        if self._anim is not None:
            self._anim.stop()
            self._anim = None
        if self._fx is not None:
            self.label.setGraphicsEffect(None)
            self._fx = None
