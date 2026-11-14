"""Add Bible dialog: pick a file, see exactly what was found, give name/code/licence, save.
Saving only adds a translation to the list. It never changes the preview or the projected screen."""
from PyQt5 import QtWidgets

from revelatetw.ui_tokens import COLORS as _C

from . import bibleconvert as bc

def _flat(w):
    w.setFrameShape(QtWidgets.QFrame.NoFrame)
    return w

def _frame(name, title_text, title_id="ImportBibleSectionTitle"):
    f = QtWidgets.QFrame()
    f.setObjectName(name)
    f.setFrameShape(QtWidgets.QFrame.StyledPanel)
    lay = QtWidgets.QVBoxLayout(f)
    lay.setContentsMargins(12, 10, 12, 10)
    lay.setSpacing(6)
    t = QtWidgets.QLabel(title_text)
    t.setObjectName(title_id)
    lay.addWidget(t)
    return f, lay

def style_dialog(dlg):
    dlg.setObjectName("ImportBibleDialog")
    dlg.setWindowTitle("Add a Bible")
    try:
        from .theme import build_qss
        dlg.setStyleSheet(build_qss())
    except Exception:
        pass

class ImportBibleDialog(QtWidgets.QDialog):
    def __init__(self, parent, user_folder, taken):
        super().__init__(parent)
        style_dialog(self)
        self.resize(600, 500)
        self._folder = user_folder
        self._taken = list(taken)
        self._result = None
        self.imported_code = ""
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(10)
        # header
        hdr, hl = _frame("ImportBibleHeader", "Add a Bible", "ImportBibleTitle")
        sub = QtWidgets.QLabel("Add a Bible your church is licensed to use.")
        sub.setObjectName("ImportBibleSub")
        sub.setWordWrap(True)
        hl.addWidget(sub)
        lay.addWidget(hdr)
        # choose file section
        sec1, s1 = _frame("ImportBibleSection", "1. Choose a Bible file")
        intro = QtWidgets.QLabel("Choose a USFM, OSIS (XML) or plain text file. Nothing is uploaded; it is converted on this PC.")
        intro.setObjectName("ImportBibleHelp")
        intro.setWordWrap(True)
        s1.addWidget(intro)
        row = QtWidgets.QHBoxLayout()
        self.file_e = QtWidgets.QLineEdit()
        self.file_e.setReadOnly(True)
        self.file_e.setPlaceholderText("No file chosen")
        self.file_e.setObjectName("ImportBibleFilePath")
        self.browse_b = QtWidgets.QPushButton("Choose file...")
        self.browse_b.setObjectName("ImportBibleBrowse")
        row.addWidget(self.file_e, 1)
        row.addWidget(self.browse_b)
        s1.addLayout(row)
        lay.addWidget(sec1)
        # preview section
        sec2, s2 = _frame("ImportBibleSection", "2. Preview what was found")
        self.preview_lbl = QtWidgets.QLabel("What was found in the file shows here before anything is saved.")
        self.preview_lbl.setObjectName("ImportBiblePreview")
        s2.addWidget(self.preview_lbl)
        self.report = QtWidgets.QPlainTextEdit()
        self.report.setReadOnly(True)
        self.report.setObjectName("ImportBibleReport")
        self.report.setPlaceholderText("What was found in the file shows here before anything is saved.")
        self.report.setMinimumHeight(96)
        s2.addWidget(self.report, 1)
        lay.addWidget(sec2, 1)
        # details section
        sec3, s3 = _frame("ImportBibleSection", "3. Name and licence")
        self.name_e = QtWidgets.QLineEdit()
        self.name_e.setPlaceholderText("Name, e.g. New King James Version")
        self.code_e = QtWidgets.QLineEdit()
        self.code_e.setPlaceholderText("Short code, e.g. NKJV")
        self.lic_e = QtWidgets.QLineEdit()
        self.lic_e.setPlaceholderText("Licence: who allowed it and for what use")
        self.name_e.setObjectName("ImportBibleName")
        self.code_e.setObjectName("ImportBibleCode")
        self.lic_e.setObjectName("ImportBibleLicence")
        for w in (self.name_e, self.code_e, self.lic_e):
            s3.addWidget(w)
        lic_hint = QtWidgets.QLabel("Only add a Bible your church is licensed to use. The licence note is kept with the saved Bible.")
        lic_hint.setObjectName("ImportBibleHint")
        lic_hint.setWordWrap(True)
        s3.addWidget(lic_hint)
        lay.addWidget(sec3)
        fmt_hint = QtWidgets.QLabel("RevelateTW reads three formats: USFM, OSIS, and plain text (.txt). PDF, Word, EPUB and image files are not supported.")
        fmt_hint.setObjectName("ImportBibleHint")
        fmt_hint.setWordWrap(True)
        lay.addWidget(fmt_hint)
        self.msg = QtWidgets.QLabel("")
        self.msg.setObjectName("ImportBibleStatus")
        self.msg.setWordWrap(True)
        lay.addWidget(self.msg)
        btns = QtWidgets.QHBoxLayout()
        btns.addStretch(1)
        self.save_b = QtWidgets.QPushButton("Add this Bible")
        self.save_b.setObjectName("primary")
        self.save_b.setEnabled(False)
        cancel = QtWidgets.QPushButton("Cancel")
        cancel.setObjectName("ImportBibleCancel")
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
