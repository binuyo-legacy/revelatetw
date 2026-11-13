"""Add Bible dialog: pick a file, see exactly what was found, give name/code/licence, save.
Saving only adds a translation to the list. It never changes the preview or the projected screen."""
from PyQt5 import QtWidgets

from . import bibleconvert as bc


class ImportBibleDialog(QtWidgets.QDialog):
    def __init__(self, parent, user_folder, taken):
        super().__init__(parent)
        self.setWindowTitle("Add a Bible")
        self.resize(560, 460)
        self._folder = user_folder
        self._taken = list(taken)
        self._result = None
        self.imported_code = ""
        lay = QtWidgets.QVBoxLayout(self)
        intro = QtWidgets.QLabel("Add a Bible your church is licensed to use. Choose a USFM, OSIS (XML) or "
                                 "plain text file. Nothing is uploaded; it is converted on this PC.")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        row = QtWidgets.QHBoxLayout()
        self.file_e = QtWidgets.QLineEdit()
        self.file_e.setReadOnly(True)
        self.file_e.setPlaceholderText("No file chosen")
        self.browse_b = QtWidgets.QPushButton("Choose file...")
        row.addWidget(self.file_e, 1)
        row.addWidget(self.browse_b)
        lay.addLayout(row)
        self.report = QtWidgets.QPlainTextEdit()
        self.report.setReadOnly(True)
        self.report.setPlaceholderText("What was found in the file shows here before anything is saved.")
        lay.addWidget(self.report, 1)
        self.name_e = QtWidgets.QLineEdit()
        self.name_e.setPlaceholderText("Name, e.g. New King James Version")
        self.code_e = QtWidgets.QLineEdit()
        self.code_e.setPlaceholderText("Short code, e.g. NKJV")
        self.lic_e = QtWidgets.QLineEdit()
        self.lic_e.setPlaceholderText("Licence: who allowed it and for what use")
        for w in (self.name_e, self.code_e, self.lic_e):
            lay.addWidget(w)
        self.msg = QtWidgets.QLabel("")
        self.msg.setObjectName("hint")
        self.msg.setWordWrap(True)
        lay.addWidget(self.msg)
        btns = QtWidgets.QHBoxLayout()
        btns.addStretch(1)
        self.save_b = QtWidgets.QPushButton("Add this Bible")
        self.save_b.setObjectName("primary")
        self.save_b.setEnabled(False)
        cancel = QtWidgets.QPushButton("Cancel")
        btns.addWidget(cancel)
        btns.addWidget(self.save_b)
        lay.addLayout(btns)
        self.browse_b.clicked.connect(self.choose)
        self.save_b.clicked.connect(self.save)
        cancel.clicked.connect(self.reject)

    def choose(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Choose a Bible file", "", bc.FILE_FILTER + ";;All files (*)")
        if path:
            self.load(path)

    def load(self, path):
        """Convert a file and show the report. Returns True when it can be saved."""
        self._result = None
        self.save_b.setEnabled(False)
        self.file_e.setText(path)
        try:
            r = bc.convert(path)
        except bc.BibleImportError as ex:
            self.report.setPlainText("")
            self.msg.setText("Could not read this file: %s" % ex)
            return False
        self._result = r
        lines = ["Format: %s" % r.format_label,
                 "%d books, %d chapters, %d verses" % (r.book_count, r.chapter_count, r.verse_count)]
        lines += ["Note: " + n for n in r.notes]
        lines += ["Sample, %s: %s" % (ref, text[:90]) for ref, text in r.samples()]
        self.report.setPlainText("\n".join(str(x) for x in lines))
        self.msg.setText("Fill in the name, short code and licence, then add it.")
        self.save_b.setEnabled(True)
        return True

    def save(self):
        if self._result is None:
            return False
        try:
            code = bc.save(self._result, self.name_e.text(), self.code_e.text(), self.lic_e.text(),
                           self._folder, self._taken)
        except (bc.BibleImportError, OSError) as ex:
            self.msg.setText(str(ex))
            return False
        self.imported_code = code
        self.accept()
        return True
