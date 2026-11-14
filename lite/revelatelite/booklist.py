"""Compact Bible book browser for the Service list tab (plain PyQt5, one light QListWidget).

Two distinct sections, Old Testament then New Testament, in canonical order, listing only the
books the selected Bible pack actually contains. Scrolls up/down only. A click asks the app to
put that book into the reference box (see Main.pick_book); this widget never touches the preview
or the projector.
"""
from PyQt5 import QtCore, QtGui, QtWidgets

from revelatetw.books import BOOKS

OT_LAST = 39           # book_id 1..39 Old Testament, 40..66 New Testament
BOOK_ROLE = QtCore.Qt.UserRole + 1
WIDTH = 150


def testament_of(book_id):
    return "OT" if book_id <= OT_LAST else "NT"


def grouped(book_ids):
    """Split available book ids into (old, new) lists, canonical order, no duplicates."""
    ids = sorted({b for b in book_ids if 1 <= b <= len(BOOKS)})
    return [b for b in ids if b <= OT_LAST], [b for b in ids if b > OT_LAST]


class BookBrowser(QtWidgets.QListWidget):
    bookChosen = QtCore.pyqtSignal(int)      # book_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("bookBrowser")
        self.setFixedWidth(WIDTH)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        self.setTextElideMode(QtCore.Qt.ElideRight)
        self.setUniformItemSizes(False)
        self.setToolTip("Click a book to start a search with it")
        self.itemClicked.connect(self._clicked)

    def set_books(self, book_ids):
        """Rebuild both sections from the books a translation has."""
        self.setUpdatesEnabled(False)
        self.clear()
        old, new = grouped(book_ids)
        for title, ids in (("Old Testament", old), ("New Testament", new)):
            if not ids:
                continue
            head = QtWidgets.QListWidgetItem(title.upper())
            head.setFlags(QtCore.Qt.NoItemFlags)           # a heading, never clickable
            head.setData(BOOK_ROLE, None)
            f = head.font()
            f.setBold(True)
            head.setFont(f)
            head.setForeground(QtGui.QBrush(QtGui.QColor("#c9a54a")))
            self.addItem(head)
            for b in ids:
                it = QtWidgets.QListWidgetItem(BOOKS[b - 1].name)
                it.setData(BOOK_ROLE, b)
                self.addItem(it)
        self.setUpdatesEnabled(True)

    def books(self):
        """[(testament, book_id, name)] as listed, top to bottom."""
        out = []
        for i in range(self.count()):
            b = self.item(i).data(BOOK_ROLE)
            if b is not None:
                out.append((testament_of(b), b, self.item(i).text()))
        return out

    def headings(self):
        return [self.item(i).text() for i in range(self.count()) if self.item(i).data(BOOK_ROLE) is None]

    def _clicked(self, item):
        b = item.data(BOOK_ROLE)
        if b is not None:
            self.bookChosen.emit(int(b))
