"""Reference box with EasyWorship-style segment editing (book / chapter / verse).

While a part is highlighted:
  Left / Right   move the highlight Book <-> Chapter <-> Verse (nothing else changes)
  Up / Down      previous / next value of the highlighted part (the app applies it)
  type / Delete  replaces the highlighted part and goes back to normal typing + suggestions
(Esc is left alone: it is the app's black-screen key.) Plain PyQt5 only.
"""
from PyQt5 import QtCore, QtWidgets

from .bible import SEGMENTS

_K = QtCore.Qt


class RefEdit(QtWidgets.QLineEdit):
    adjustRequested = QtCore.pyqtSignal(str, int)     # (segment, +1 / -1)

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._spans = None       # spans of the reference currently shown
        self._canonical = None   # its text
        self._seg = None         # highlighted part, or None (normal typing)
        self._erasing = False    # last key was Backspace/Delete: do not re-fill the suggestion
        self.jumpHandler = None  # app callback: (direction) -> True when it jumped into a part

    def erasing(self):
        return self._erasing

    def typed_text(self):
        """What the user actually typed: the text minus a selected, auto-filled tail."""
        t = self.text()
        if self.hasSelectedText() and self.selectionEnd() == len(t) and self._seg is None:
            return t[:self.selectionStart()]
        return t

    def fill_suggestion(self, full):
        """Show the suggestion after what was typed, with the filled-in tail selected
        (typing carries on over it, Backspace removes it, Left/Right accept it)."""
        typed = self.text()
        self.setText(full)
        self.setSelection(len(full), -(len(full) - len(typed)))
        self._seg = None

    def segment(self):
        return self._seg

    def set_reference(self, text, spans, highlight, segment=None):
        self._spans, self._canonical = spans, text
        self.setText(text)
        if highlight:
            self._select(segment or self._seg or "book")
        else:
            self._seg = None

    def forget_reference(self):
        self._spans = self._canonical = self._seg = None

    def _select(self, seg):
        if not self._spans or seg not in self._spans or self.text() != self._canonical:
            self._seg = None
            return
        self._seg = seg
        s, e = self._spans[seg]
        self.setSelection(s, e - s)
        comp = self.completer()
        if comp is not None:
            comp.popup().hide()

    def focusInEvent(self, e):
        super().focusInEvent(e)
        if e.reason() in (_K.TabFocusReason, _K.BacktabFocusReason, _K.ShortcutFocusReason):
            self._select(self._seg or "book")

    def mousePressEvent(self, e):
        self._seg = None
        super().mousePressEvent(e)

    def keyPressEvent(self, e):
        key = e.key()
        mods = e.modifiers() & ~_K.KeypadModifier
        plain = mods == _K.NoModifier
        self._erasing = key in (_K.Key_Backspace, _K.Key_Delete)
        if plain and key in (_K.Key_Left, _K.Key_Right) and self._seg is None and self.jumpHandler \
                and self.text() and (self.cursorPosition() == len(self.text()) or self.hasSelectedText()) \
                and self.text() != self._canonical:
            # typing mode (suggestions showing): accept what is typed/suggested and jump into a part
            if self.jumpHandler(1 if key == _K.Key_Right else -1):
                return
        if plain and key in (_K.Key_Left, _K.Key_Right) and self._seg is None \
                and self._canonical and self.text() == self._canonical:
            self._select("book" if key == _K.Key_Right else "verse")   # enter highlight mode
            return
        if self._seg and plain:
            i = SEGMENTS.index(self._seg)
            if key == _K.Key_Left:
                self._select(SEGMENTS[max(0, i - 1)])
                return
            if key == _K.Key_Right:
                self._select(SEGMENTS[min(len(SEGMENTS) - 1, i + 1)])
                return
            if key in (_K.Key_Up, _K.Key_Down):
                self.adjustRequested.emit(self._seg, 1 if key == _K.Key_Up else -1)
                return
            if key in (_K.Key_Return, _K.Key_Enter):
                pass
            elif key in (_K.Key_Home, _K.Key_End):
                self._seg = None
            elif key in (_K.Key_Backspace, _K.Key_Delete) or (e.text() and e.text().isprintable()):
                if self._seg == "book":
                    self.clear()      # a new book search starts from scratch
                self._seg = None
        elif self._seg and not (mods & _K.ControlModifier):
            self._seg = None
        super().keyPressEvent(e)
