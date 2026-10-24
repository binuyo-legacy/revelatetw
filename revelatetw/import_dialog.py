"""Import Bible translation dialog (mockup 1): choose file, detected format, details, preview, import.

The conversion runs on a QThread so a large file never freezes the window. The dialog only
calls the library (bible_import.convert_file / write_import); it does not parse anything itself.
"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QThread, Qt, pyqtSignal
from PyQt6.QtWidgets import (QDialog, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                             QProgressBar, QPushButton, QVBoxLayout, QWidget)

from .bible import BibleImportError, DEFAULT_BIBLE_DIR
from .bible_import import (SUPPORTED_FORMATS_HELP, ImportResult, UnsupportedFormatError, convert_file,
                           write_import)

SUPPORTED_EXTS = (".usfm", ".usfm3", ".sfm", ".osis", ".xml", ".txt")
CARD_OK = ("background:#14302a;border:1px solid #166534;border-radius:8px;color:#86efac;padding:10px;")
CARD_ERR = ("background:#2a1414;border:1px solid #7f1d1d;border-radius:8px;color:#fca5a5;padding:10px;")
CHIP_OK = ("background:#14302a;border:1px solid #166534;border-radius:14px;color:#86efac;padding:6px 12px;")
FORMAT_CARD = ("background:#0b0f19;border:1px solid #374151;border-radius:8px;color:#f3f4f6;padding:14px;")
DROP_ZONE = ("border:1px dashed #4b5563;border-radius:10px;background:#0b0f19;")
PREVIEW_BOX = "border:1px solid #374151;border-radius:8px;background:#0b0f19;"
LABEL = "color:#9ca3af;font-size:12px;"
TITLE = "color:#facc15;font-weight:bold;font-size:20px;"
STEP = "color:#facc15;font-weight:bold;font-size:12px;letter-spacing:1px;"
GREEN_STRIP = ("background:#14302a;border:1px solid #166534;border-radius:8px;color:#86efac;"
               "font-weight:bold;padding:10px;")


class _ConvertWorker(QThread):
    done = pyqtSignal(object)      # ImportResult
    failed = pyqtSignal(object)    # BibleImportError / other error
    progress = pyqtSignal(str)

    def __init__(self, path: Path):
        super().__init__()
        self._path = path

    def run(self) -> None:
        self.progress.emit("Reading file...")
        try:
            result = convert_file(self._path)
        except BibleImportError as exc:
            self.failed.emit(exc)
            return
        except Exception as exc:                      # a damaged file must not crash the app
            self.failed.emit(BibleImportError(f"could not read {self._path.name}: {exc}"))
            return
        self.done.emit(result)


class _SaveWorker(QThread):
    done = pyqtSignal(object)
    failed = pyqtSignal(object)

    def __init__(self, result: ImportResult, name: str, code: str, license_text: str, folder):
        super().__init__()
        self._args = (result, name, code, license_text, folder)

    def run(self) -> None:
        try:
            result, name, code, license_text, folder = self._args
            self.done.emit(write_import(result, name=name, code=code, license_text=license_text, folder=folder))
        except BibleImportError as exc:
            self.failed.emit(exc)
        except Exception as exc:
            self.failed.emit(BibleImportError(f"could not save the translation: {exc}"))


def _label(text: str, style: str = LABEL) -> QLabel:
    lab = QLabel(text)
    lab.setStyleSheet(style)
    lab.setWordWrap(True)
    return lab


def _card(text: str, style: str) -> QLabel:
    lab = QLabel(text)
    lab.setWordWrap(True)
    lab.setStyleSheet(style)
    lab.setTextFormat(Qt.TextFormat.PlainText)
    return lab


class _DropZone(QFrame):
    """Drop zone: click to browse, or drop a local file."""
    clicked = pyqtSignal()
    dropped = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event) -> None:
        self.clicked.emit()
        super().mousePressEvent(event)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        urls = event.mimeData().urls()
        if urls and urls[0].isLocalFile():
            self.dropped.emit(Path(urls[0].toLocalFile()))


class ImportTranslationDialog(QDialog):
    def __init__(self, parent=None, folder=None):
        super().__init__(parent)
        self.setWindowTitle("Import Bible translation")
        self.setModal(True)
        self.setMinimumWidth(640)
        self.setStyleSheet("QDialog{background:#111827;border:1px solid #374151;border-radius:16px;}")
        self._folder = Path(folder) if folder else DEFAULT_BIBLE_DIR
        self._path: Path | None = None
        self._result: ImportResult | None = None
        self._worker: QThread | None = None
        self.result_message = ""

        outer = QVBoxLayout(self)
        outer.setContentsMargins(32, 24, 32, 24)
        outer.setSpacing(10)
        title = QLabel("Import Bible translation")
        title.setStyleSheet(TITLE)
        outer.addWidget(title)
        outer.addWidget(_label("Bring your own licensed translation. Nothing is bundled without your licence.",
                               "color:#9ca3af;font-size:13px;"))

        # 1. choose file
        outer.addWidget(_label("1. CHOOSE FILE", STEP))
        self.drop = _DropZone()
        self.drop.setStyleSheet(DROP_ZONE)
        dl = QVBoxLayout(self.drop)
        dl.setContentsMargins(16, 16, 16, 16)
        drop_text = QLabel("Drop a file here, or <a href='#' style='color:#facc15;font-weight:bold;'>browse</a> "
                           "to choose it")
        drop_text.setTextFormat(Qt.TextFormat.RichText)
        drop_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop_text.setStyleSheet("color:#f3f4f6;font-size:14px;")
        drop_text.linkActivated.connect(lambda _: self._browse())
        hint = _label("USFM, OSIS or XML", "color:#9ca3af;font-size:12px;")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dl.addWidget(drop_text)
        dl.addWidget(hint)
        self.drop.clicked.connect(self._browse)
        self.drop.dropped.connect(self._load)
        outer.addWidget(self.drop)

        self.chip = QLabel("")
        self.chip.setStyleSheet(CHIP_OK)
        self.chip.hide()
        outer.addWidget(self.chip, 0, Qt.AlignmentFlag.AlignLeft)

        self.busy = QProgressBar()
        self.busy.setRange(0, 0)
        self.busy.setTextVisible(False)
        self.busy.setFixedHeight(6)
        self.busy.hide()
        outer.addWidget(self.busy)
        self.status = _label("")
        outer.addWidget(self.status)

        # 2. format
        outer.addWidget(_label("2. FORMAT", STEP))
        self.format_card = _card("Format: not checked yet", FORMAT_CARD)
        outer.addWidget(self.format_card)
        self.error_card = _card("", CARD_ERR)
        self.error_card.hide()
        outer.addWidget(self.error_card)
        self.help_row = QHBoxLayout()
        self.btn_formats = QPushButton("Show supported formats")
        self.btn_formats.setObjectName("ghost")
        self.btn_formats.clicked.connect(self._show_formats)
        self.btn_contact = QPushButton("Contact support")
        self.btn_contact.setObjectName("ghost")
        self.btn_contact.clicked.connect(self._contact)
        self.help_row.addWidget(self.btn_formats)
        self.help_row.addWidget(self.btn_contact)
        self.help_row.addStretch(1)
        self.help_widget = QWidget()
        self.help_widget.setLayout(self.help_row)
        self.help_widget.hide()
        outer.addWidget(self.help_widget)

        # 3. details
        outer.addWidget(_label("3. DETAILS", STEP))
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.addWidget(_label("Translation name"), 0, 0)
        grid.addWidget(_label("Short code"), 0, 1)
        self.name = QLineEdit()
        self.name.setPlaceholderText("New King James Version")
        self.code = QLineEdit()
        self.code.setPlaceholderText("NKJV")
        self.code.setMaxLength(16)
        grid.addWidget(self.name, 1, 0)
        grid.addWidget(self.code, 1, 1)
        grid.setColumnStretch(0, 3)
        grid.setColumnStretch(1, 1)
        outer.addLayout(grid)
        self.licence = QLineEdit()
        self.licence.setPlaceholderText("Licence: who licensed this text and for what use")
        outer.addWidget(self.licence)
        outer.addWidget(_label("You are responsible for having the right to use this text. "
                               "Your licence (for example Thomas Nelson or Biblica) applies, not RevelateTW's."))

        # 4. preview
        outer.addWidget(_label("4. PREVIEW", STEP))
        self.preview_box = QFrame()
        self.preview_box.setStyleSheet(PREVIEW_BOX)
        self.preview_layout = QVBoxLayout(self.preview_box)
        self.preview_layout.setContentsMargins(14, 10, 14, 10)
        self.preview_layout.setSpacing(6)
        self.preview_empty = _label("Choose a file to see three sample verses here.", "color:#6b7280;")
        self.preview_layout.addWidget(self.preview_empty)
        outer.addWidget(self.preview_box)
        self.preview_ok = _card("\u2713 Preview looks correct", GREEN_STRIP)
        self.preview_ok.hide()
        outer.addWidget(self.preview_ok)
        self.notes = _label("", "color:#f59e0b;font-size:12px;")
        self.notes.hide()
        outer.addWidget(self.notes)

        # footer
        footer = QHBoxLayout()
        footer.addStretch(1)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setObjectName("ghost")
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_import = QPushButton("Import")
        self.btn_import.setObjectName("primary")
        self.btn_import.setEnabled(False)
        self.btn_import.clicked.connect(self._import)
        footer.addWidget(self.btn_cancel)
        footer.addWidget(self.btn_import)
        outer.addLayout(footer)

        self.success = _card("", CARD_OK)
        self.success.hide()
        outer.addWidget(self.success)
        self.btn_done = QPushButton("Done")
        self.btn_done.setObjectName("primary")
        self.btn_done.clicked.connect(self.accept)
        self.btn_done.hide()
        footer.addWidget(self.btn_done)
        self.name.textChanged.connect(self._update_import_enabled)
        self.code.textChanged.connect(self._update_import_enabled)
        self.licence.textChanged.connect(self._update_import_enabled)

    # --- file selection --------------------------------------------------------------------
    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose Bible file", "",
            "Bible files (*.usfm *.usfm3 *.sfm *.osis *.xml *.txt);;All files (*)")
        if path:
            self._load(Path(path))

    def _load(self, path: Path) -> None:
        self._path = path
        self._result = None
        self._set_chip(f"\u2713 {path.name}: detecting format...")
        self.chip.setStyleSheet(CHIP_OK)
        self.format_card.setText("Format: reading the file...")
        self.error_card.hide()
        self.help_widget.hide()
        self.preview_ok.hide()
        self.btn_import.setEnabled(False)
        self._clear_preview()
        self.busy.show()
        self.status.setText("Converting. This can take a moment for large files.")
        self._worker = _ConvertWorker(path)
        self._worker.done.connect(self._on_converted)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _set_chip(self, text: str) -> None:
        self.chip.setText(text)
        self.chip.show()

    def _on_converted(self, result: ImportResult) -> None:
        self.busy.hide()
        self.status.setText("")
        self._result = result
        self.error_card.hide()
        self.help_widget.hide()
        self._set_chip(f"\u2713 {self._path.name}: {result.format_label} detected")
        self.format_card.setText(
            f"Format: {result.format_label} \u00b7 {result.book_count} books \u00b7 {result.verse_count:,} verses detected")
        self._clear_preview()
        for ref, text in result.samples():
            row = QLabel(f"<span style='color:#facc15;font-weight:bold;'>{ref}</span>  "
                         f"<span style='color:#f3f4f6;'>{_esc(text)}</span>")
            row.setTextFormat(Qt.TextFormat.RichText)
            row.setWordWrap(True)
            self.preview_layout.addWidget(row)
        self.preview_ok.show()
        if result.notes:
            self.notes.setText("Check before importing: " + "; ".join(result.notes) + ".")
            self.notes.show()
        else:
            self.notes.hide()
        if not self.code.text().strip():
            stem = self._path.stem.upper().replace(" ", "")[:16]
            self.code.setText(stem if stem else "")
        if not self.name.text().strip():
            self.name.setText(self._path.stem.replace("_", " ").replace("-", " ").strip())
        self._update_import_enabled()

    def _on_failed(self, exc: Exception) -> None:
        self.busy.hide()
        self.status.setText("")
        self._result = None
        self.chip.hide()
        self.format_card.setText("Format: not supported")
        self.preview_ok.hide()
        self._clear_preview()
        self.btn_import.setEnabled(False)
        if isinstance(exc, UnsupportedFormatError):
            title = "Unsupported format"
            body = str(exc).split("\n", 1)[0]
        else:
            title = "Could not import"
            body = str(exc)
        self.error_card.setText(f"{title}\n{body}\n\nRevelateTW reads USFM and OSIS exports. "
                                f"Export the translation as USFM or OSIS from its publisher's software.")
        self.error_card.show()
        self.help_widget.show()

    def _clear_preview(self) -> None:
        while self.preview_layout.count():
            item = self.preview_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.preview_layout.addWidget(_label("Choose a file to see three sample verses here.", "color:#6b7280;"))

    def _update_import_enabled(self) -> None:
        ok = (self._result is not None and bool(self.name.text().strip()) and bool(self.code.text().strip())
              and bool(self.licence.text().strip()) and self._worker_idle())
        self.btn_import.setEnabled(ok)

    def _worker_idle(self) -> bool:
        return self._worker is None or self._worker.isFinished()

    # --- import ----------------------------------------------------------------------------
    def _import(self) -> None:
        if self._result is None:
            return
        self.btn_import.setEnabled(False)
        self.busy.show()
        self.status.setText("Saving the translation...")
        self._worker = _SaveWorker(self._result, self.name.text(), self.code.text(), self.licence.text(),
                                   self._folder)
        self._worker.done.connect(self._on_saved)
        self._worker.failed.connect(self._on_save_failed)
        self._worker.start()

    def _on_saved(self, t) -> None:
        self.busy.hide()
        self.status.setText("")
        r = self._result
        self.result_message = (f"{t.id} imported: {r.book_count} books, {r.verse_count:,} verses. "
                               "Available in the translation dropdown.")
        self.success.setText(self.result_message)
        self.success.setStyleSheet(CARD_OK)
        self.success.show()
        self.btn_import.hide()
        self.btn_cancel.hide()
        self.btn_done.show()

    def _on_save_failed(self, exc: Exception) -> None:
        self.busy.hide()
        self.status.setText("")
        self.error_card.setText(f"Could not save\n{exc}")
        self.error_card.show()
        self.btn_import.setEnabled(True)

    def _show_formats(self) -> None:
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.information(self, "Supported formats", SUPPORTED_FORMATS_HELP)

    def _contact(self) -> None:
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.information(self, "Contact support",
                                "Send the file name and the message above to RevelateTW support. "
                                "Do not send the Bible text itself.")


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
