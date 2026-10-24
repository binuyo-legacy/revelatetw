"""Import songs dialog (same visual language as the Bible import dialog).

Choose a .rtsong file (one song or a whole library), a .txt lyrics file, or paste lyrics. The
parse and the save both run on a QThread, so a big file never freezes the window. Nothing is
written until Save is clicked. The dialog only calls song_io; it does not parse anything itself.
"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QThread, QTimer, Qt, pyqtSignal
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
                             QLabel, QLineEdit, QPlainTextEdit, QProgressBar, QPushButton, QScrollArea,
                             QStackedWidget, QVBoxLayout, QWidget)

from .import_dialog import (CARD_ERR, CARD_OK, CHIP_OK, DROP_ZONE, FORMAT_CARD, GREEN_STRIP, LABEL,
                            PREVIEW_BOX, STEP, TITLE, _DropZone, _card, _label)
from .song_io import (ImportBatch, SongFileError, import_file, import_text, plan_import, save_plan,
                      slide_counts)
from .songs import Song, SongLibrary

AMBER = "color:#f59e0b;font-size:12px;"
SECTION_CARD = ("background:#111827;border:1px solid #374151;border-radius:8px;")
SECTION_LABEL = "color:#facc15;font-weight:bold;font-size:13px;"
SECTION_LINES = "color:#f3f4f6;font-size:14px;"
SUMMARY = "color:#cbd5e1;font-size:12px;"


class _ParseWorker(QThread):
    """Reads and splits a file or pasted text off the UI thread."""
    done = pyqtSignal(object, object, int)   # (ImportBatch, duplicate titles, seq)
    failed = pyqtSignal(object, int)         # (exception, seq)

    def __init__(self, library_root, path: Path | None, text: str, seq: int):
        super().__init__()
        self._root, self._path, self._text, self._seq = library_root, path, text, seq

    def run(self) -> None:
        try:
            batch = import_file(self._path) if self._path is not None else import_text(self._text)
            existing = {s.title.casefold() for s in SongLibrary(self._root).load_all()}
            dups = [s.title for s in batch.songs if s.title.casefold() in existing]
        except SongFileError as exc:
            self.failed.emit(exc, self._seq)
            return
        except Exception as exc:                  # a damaged file must not crash the app
            self.failed.emit(SongFileError(f"could not read the lyrics: {exc}"), self._seq)
            return
        self.done.emit(batch, dups, self._seq)


class _SaveWorker(QThread):
    done = pyqtSignal(object)                # list[PlannedSong]
    failed = pyqtSignal(object)

    def __init__(self, library: SongLibrary, songs: list[Song], replace: bool):
        super().__init__()
        self._library, self._songs, self._replace = library, songs, replace

    def run(self) -> None:
        try:
            plan = plan_import(self._songs, self._library.load_all(), replace=self._replace)
            save_plan(self._library, plan)
            self.done.emit(plan)
        except Exception as exc:
            self.failed.emit(SongFileError(f"could not save the songs: {exc}"))


def _set_active(button: QPushButton, active: bool) -> None:
    button.setProperty("active", "true" if active else "false")
    button.style().unpolish(button)
    button.style().polish(button)


class ImportSongsDialog(QDialog):
    def __init__(self, parent, library: SongLibrary):
        super().__init__(parent)
        self.setWindowTitle("Import songs")
        self.setModal(True)
        self.setMinimumWidth(680)
        self.setStyleSheet("QDialog{background:#111827;border:1px solid #374151;border-radius:16px;}")
        self._library = library
        self._batch: ImportBatch | None = None
        self._dups: list[str] = []
        self._worker: QThread | None = None
        self._workers: list[QThread] = []        # keep every started thread alive until it finishes
        self._seq = 0
        self._paste_timer = QTimer(self)
        self._paste_timer.setSingleShot(True)
        self._paste_timer.setInterval(350)
        self._paste_timer.timeout.connect(self._parse_pasted)
        self._title_user_edit = False
        self._preview_index = 0
        self.saved_count = 0
        self.touched_ids: set[str] = set()
        self.result_message = ""

        outer = QVBoxLayout(self)
        outer.setContentsMargins(32, 24, 32, 24)
        outer.setSpacing(10)
        title = QLabel("Import songs")
        title.setStyleSheet(TITLE)
        outer.addWidget(title)
        outer.addWidget(_label("Open a .rtsong file (one song or a whole library) or a .txt lyrics file, "
                               "or paste lyrics. Nothing is saved until you click Save.",
                               "color:#9ca3af;font-size:13px;"))

        # 1. source
        outer.addWidget(_label("1. CHOOSE SOURCE", STEP))
        tabs = QHBoxLayout()
        self.btn_tab_file = QPushButton("Open file")
        self.btn_tab_file.setObjectName("seg")
        self.btn_tab_paste = QPushButton("Paste lyrics")
        self.btn_tab_paste.setObjectName("seg")
        self.btn_tab_file.clicked.connect(lambda: self._show_tab(0))
        self.btn_tab_paste.clicked.connect(lambda: self._show_tab(1))
        tabs.addWidget(self.btn_tab_file)
        tabs.addWidget(self.btn_tab_paste)
        tabs.addStretch(1)
        outer.addLayout(tabs)

        self.pages = QStackedWidget()
        self.drop = _DropZone()
        self.drop.setStyleSheet(DROP_ZONE)
        dl = QVBoxLayout(self.drop)
        dl.setContentsMargins(16, 16, 16, 16)
        drop_text = QLabel("Drop a .rtsong or .txt file here, or <a href='#' style='color:#facc15;"
                           "font-weight:bold;'>browse</a> to choose it")
        drop_text.setTextFormat(Qt.TextFormat.RichText)
        drop_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop_text.setStyleSheet("color:#f3f4f6;font-size:14px;")
        drop_text.linkActivated.connect(lambda _: self._browse())
        hint = _label(".rtsong (RevelateTW songs) or plain lyrics text", "color:#9ca3af;font-size:12px;")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dl.addWidget(drop_text)
        dl.addWidget(hint)
        self.drop.clicked.connect(self._browse)
        self.drop.dropped.connect(self._load_file)
        self.pages.addWidget(self.drop)

        self.paste = QPlainTextEdit()
        self.paste.setPlaceholderText("Paste lyrics here. The first line becomes the title. Blank lines "
                                      "start a new slide, and headers like Chorus or V1 label it.")
        self.paste.setMinimumHeight(120)
        self.paste.textChanged.connect(self._on_paste_changed)
        self.pages.addWidget(self.paste)
        self.pages.setFixedHeight(130)
        outer.addWidget(self.pages)

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
        self.error_card = _card("", CARD_ERR)
        self.error_card.hide()
        outer.addWidget(self.error_card)

        # 2. details
        outer.addWidget(_label("2. DETAILS", STEP))
        self.details = QWidget()
        dg = QVBoxLayout(self.details)
        dg.setContentsMargins(0, 0, 0, 0)
        dg.setSpacing(6)
        self.text_fields = QWidget()
        grid = QGridLayout(self.text_fields)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(16)
        grid.addWidget(_label("Song title"), 0, 0)
        grid.addWidget(_label("Author (optional)"), 0, 1)
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Amazing Grace")
        self.title_edit.textEdited.connect(self._on_title_typed)
        self.author_edit = QLineEdit()
        self.author_edit.setPlaceholderText("John Newton")
        grid.addWidget(self.title_edit, 1, 0)
        grid.addWidget(self.author_edit, 1, 1)
        grid.setColumnStretch(0, 3)
        grid.setColumnStretch(1, 2)
        dg.addWidget(self.text_fields)
        self.format_card = _card("Format: nothing chosen yet", FORMAT_CARD)
        dg.addWidget(self.format_card)
        self.replace_box = QCheckBox("Replace songs with the same title")
        self.replace_box.setChecked(False)
        self.replace_box.toggled.connect(lambda _: self._refresh_dup_note())
        dg.addWidget(self.replace_box)
        self.dup_note = _label("", AMBER)
        self.dup_note.hide()
        dg.addWidget(self.dup_note)
        self.details.hide()
        outer.addWidget(self.details)

        # 3. preview
        outer.addWidget(_label("3. PREVIEW", STEP))
        self.preview_summary = _label("", SUMMARY)
        self.preview_summary.hide()
        outer.addWidget(self.preview_summary)
        self.song_pick = QComboBox()
        self.song_pick.currentIndexChanged.connect(self._on_song_picked)
        self.song_pick.hide()
        outer.addWidget(self.song_pick)
        self.preview_box = QFrame()
        self.preview_box.setStyleSheet(PREVIEW_BOX)
        box_layout = QVBoxLayout(self.preview_box)
        box_layout.setContentsMargins(0, 0, 0, 0)
        self.preview_scroll = QScrollArea()
        self.preview_scroll.setWidgetResizable(True)
        self.preview_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.preview_scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        self.preview_scroll.setMaximumHeight(300)
        self.preview_inner = QWidget()
        self.preview_inner.setStyleSheet("background:transparent;")
        self.preview_layout = QVBoxLayout(self.preview_inner)
        self.preview_layout.setContentsMargins(14, 10, 14, 10)
        self.preview_layout.setSpacing(8)
        self.preview_scroll.setWidget(self.preview_inner)
        box_layout.addWidget(self.preview_scroll)
        self.preview_box.setMaximumHeight(320)
        outer.addWidget(self.preview_box)
        self._set_preview_empty("Choose a file or paste lyrics to see how the slides will split here.")
        self.preview_ok = _card("\u2713 Preview looks correct", GREEN_STRIP)
        self.preview_ok.hide()
        outer.addWidget(self.preview_ok)
        self.notes = _label("", AMBER)
        self.notes.hide()
        outer.addWidget(self.notes)

        # footer
        footer = QHBoxLayout()
        footer.addStretch(1)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setObjectName("ghost")
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_save = QPushButton("Save")
        self.btn_save.setObjectName("primary")
        self.btn_save.setEnabled(False)
        self.btn_save.clicked.connect(self._save)
        self.btn_done = QPushButton("Done")
        self.btn_done.setObjectName("primary")
        self.btn_done.clicked.connect(self.accept)
        self.btn_done.hide()
        footer.addWidget(self.btn_cancel)
        footer.addWidget(self.btn_save)
        footer.addWidget(self.btn_done)
        outer.addLayout(footer)

        self.success = _card("", CARD_OK)
        self.success.hide()
        outer.addWidget(self.success)
        self._show_tab(0)

    # --- source ------------------------------------------------------------------------------
    def _show_tab(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        _set_active(self.btn_tab_file, index == 0)
        _set_active(self.btn_tab_paste, index == 1)
        if index == 1:
            self.paste.setFocus()

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose songs file", "",
            "Song files (*.rtsong *.txt *.json);;RevelateTW songs (*.rtsong);;Lyrics text (*.txt);;All files (*)")
        if path:
            self._load_file(Path(path))

    def _load_file(self, path: Path) -> None:
        self._show_tab(0)
        self._start_parse(path, "")

    def _on_paste_changed(self) -> None:
        self._paste_timer.start()

    def _parse_pasted(self) -> None:
        text = self.paste.toPlainText()
        if not text.strip():
            self._reset_result()
            return
        self._start_parse(None, text)

    # --- parse (QThread) ----------------------------------------------------------------------
    def _start_parse(self, path: Path | None, text: str) -> None:
        self._seq += 1
        self._reset_result()
        self._title_user_edit = False
        self.busy.show()
        self.status.setText("Reading lyrics. This can take a moment for large files.")
        worker = _ParseWorker(self._library.root, path, text, self._seq)
        worker.done.connect(self._on_parsed)
        worker.failed.connect(self._on_parse_failed)
        self._track(worker)
        self._worker = worker
        worker.start()
        self._label_source(path)

    def _label_source(self, path: Path | None) -> None:
        self.chip.setText(f"\u2713 {path.name}: reading..." if path else "\u2713 pasted lyrics: reading...")
        self.chip.setStyleSheet(CHIP_OK)
        self.chip.show()

    def _track(self, worker: QThread) -> None:
        self._workers.append(worker)
        worker.finished.connect(lambda w=worker: self._workers.remove(w) if w in self._workers else None)

    def _on_parsed(self, batch: ImportBatch, dups: list, seq: int) -> None:
        if seq != self._seq:
            return                                  # a newer parse replaced this one
        self.busy.hide()
        self.status.setText("")
        self.error_card.hide()
        self._batch = batch
        self._dups = list(dups)
        self.chip.setText(f"\u2713 {batch.format_label}")
        self.chip.setStyleSheet(CHIP_OK)
        self.chip.show()
        raw = batch.kind == "text"
        self.text_fields.setVisible(raw)
        self.details.show()
        if raw:
            song = batch.songs[0]
            if not self._title_user_edit:
                self.title_edit.blockSignals(True)
                self.title_edit.setText(song.title)
                self.title_edit.blockSignals(False)
            self.author_edit.setText(song.artist)
        self.format_card.setText(self._format_text())
        self.song_pick.blockSignals(True)
        self.song_pick.clear()
        if len(batch.songs) > 1:
            for s in batch.songs:
                self.song_pick.addItem(f"{s.title}  \u00b7  {len(s.slides)} slide" + ("" if len(s.slides) == 1 else "s"))
            self.song_pick.show()
        else:
            self.song_pick.hide()
        self.song_pick.blockSignals(False)
        self._preview_index = 0
        self._refresh_dup_note()
        self._render_preview()
        self._update_save_enabled()

    def _on_parse_failed(self, exc: Exception, seq: int) -> None:
        if seq != self._seq:
            return
        self.busy.hide()
        self.status.setText("")
        self._batch = None
        self.chip.hide()
        self.details.hide()
        self.format_card.setText("Format: not supported")
        self._set_preview_empty("Nothing to preview yet.")
        self.preview_summary.hide()
        self.song_pick.hide()
        self.preview_ok.hide()
        self.error_card.setText(f"Could not read these lyrics\n{exc}\n\nUse a .rtsong file exported from "
                                "RevelateTW, or a .txt file with one song's lyrics.")
        self.error_card.show()
        self._update_save_enabled()

    def _reset_result(self) -> None:
        self._batch = None
        self._dups = []
        self.chip.hide()
        self.error_card.hide()
        self.details.hide()
        self.preview_ok.hide()
        self.notes.hide()
        self.song_pick.hide()
        self.preview_summary.hide()
        self._set_preview_empty("Choose a file or paste lyrics to see how the slides will split here.")
        self._update_save_enabled()

    # --- details and preview ----------------------------------------------------------------
    def _format_text(self) -> str:
        b = self._batch
        if b is None:
            return "Format: nothing chosen yet"
        slides = sum(len(s.slides) for s in b.songs)
        kind = "RevelateTW song file (.rtsong)" if b.kind == "rtsong" else "plain lyrics text"
        return f"Format: {kind} \u00b7 {len(b.songs)} song{'s' if len(b.songs) != 1 else ''} \u00b7 {slides} slides"

    def _on_title_typed(self, _text: str) -> None:
        self._title_user_edit = True
        self._update_save_enabled()
        self._refresh_dup_note()

    def _on_song_picked(self, index: int) -> None:
        self._preview_index = max(0, index)
        self._render_preview()

    def _refresh_dup_note(self) -> None:
        if self._batch is None:
            self.dup_note.hide()
            return
        dups = self._dups_now()
        if not dups:
            self.dup_note.hide()
            return
        n = len(dups)
        if self.replace_box.isChecked():
            text = (f"{n} song{'s' if n != 1 else ''} with the same title will replace the saved "
                    f"song{'s' if n != 1 else ''}.")
        else:
            text = (f"{n} song{'s' if n != 1 else ''} already in your library. They will be saved with "
                    f"a \" (2)\" suffix, for example \"{dups[0]} (2)\".")
        self.dup_note.setText(text)
        self.dup_note.show()

    def _dups_now(self) -> list[str]:
        if self._batch is None:
            return []
        if self._batch.kind == "text":
            title = self.title_edit.text().strip()
            if not title:
                return []
            existing = {s.title.casefold() for s in self._library.load_all()}
            return [title] if title.casefold() in existing else []
        return list(self._dups)

    def _current_songs(self) -> list[Song]:
        """The songs to save, with the title/author typed in the form (raw text only)."""
        b = self._batch
        if b is None:
            return []
        if b.kind == "text":
            song = b.songs[0]
            title = self.title_edit.text().strip()
            if not title:
                return []                       # Song() needs a title; Save stays off until one is typed
            return [Song(title=title, artist=self.author_edit.text().strip(), slides=song.slides)]
        return list(b.songs)

    def _render_preview(self) -> None:
        b = self._batch
        self._clear_preview()
        if b is None:
            self._set_preview_empty("Choose a file or paste lyrics to see how the slides will split here.")
            self.preview_ok.hide()
            self.notes.hide()
            return
        songs = self._current_songs()
        if not songs:
            self._set_preview_empty("Type a song title above to see the preview.")
            self.preview_ok.hide()
            return
        idx = min(self._preview_index, len(songs) - 1)
        song = songs[idx]
        total_slides = sum(len(s.slides) for s in songs)
        if len(songs) > 1:
            self.preview_summary.setText(f"{len(songs)} songs \u00b7 {total_slides} slides in total. "
                                         f"Showing: {song.title}")
        else:
            self.preview_summary.setText(f"{song.title}" + (f"  \u00b7  {song.artist}" if song.artist else ""))
        self.preview_summary.show()
        self.preview_layout.addWidget(_label(slide_counts(song.slides), "color:#facc15;font-weight:bold;"))
        for slide in song.slides:
            self.preview_layout.addWidget(self._section_card(slide.label, slide.lines))
        self.preview_layout.addStretch(1)
        self.preview_ok.show()
        notes = []
        if any(s.label.startswith("Slide ") for s in song.slides):
            notes.append("some slides have no section label, so they are numbered. Add a header such as "
                         "Chorus or V1 above them to name them")
        if len(songs) > 1 and any(not s.slides for s in songs):
            notes.append("some songs have no slides")
        if notes:
            self.notes.setText("Check before saving: " + "; ".join(notes) + ".")
            self.notes.show()
        else:
            self.notes.hide()

    def _section_card(self, label: str, lines: list[str]) -> QFrame:
        card = QFrame()
        card.setStyleSheet(SECTION_CARD)
        v = QVBoxLayout(card)
        v.setContentsMargins(12, 8, 12, 8)
        v.setSpacing(3)
        head = _label(label, SECTION_LABEL)
        v.addWidget(head)
        for line in lines:
            row = QLabel(_esc(line))
            row.setTextFormat(Qt.TextFormat.RichText)
            row.setWordWrap(True)
            row.setStyleSheet(SECTION_LINES)
            v.addWidget(row)
        return card

    def _set_preview_empty(self, text: str) -> None:
        self._clear_preview()
        self.preview_layout.addWidget(_label(text, "color:#6b7280;"))
        self.preview_layout.addStretch(1)

    def _clear_preview(self) -> None:
        while self.preview_layout.count():
            item = self.preview_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _update_save_enabled(self) -> None:
        ok = self._batch is not None and bool(self._current_songs()) and self._worker_idle()
        if self._batch is not None and self._batch.kind == "text":
            ok = ok and bool(self.title_edit.text().strip())
        self.btn_save.setEnabled(ok)

    def _worker_idle(self) -> bool:
        return self._worker is None or self._worker.isFinished()

    # --- save (QThread) -----------------------------------------------------------------------
    def _save(self) -> None:
        songs = self._current_songs()
        if not songs:
            return
        self.btn_save.setEnabled(False)
        self.busy.show()
        self.status.setText("Saving songs...")
        self.error_card.hide()
        worker = _SaveWorker(self._library, songs, self.replace_box.isChecked())
        worker.done.connect(self._on_saved)
        worker.failed.connect(self._on_save_failed)
        self._track(worker)
        self._worker = worker
        worker.start()

    def _on_saved(self, plan) -> None:
        self.busy.hide()
        self.status.setText("")
        self.saved_count = len(plan)
        self.touched_ids = {p.song.id for p in plan}
        renamed = sum(1 for p in plan if p.action == "renamed")
        replaced = sum(1 for p in plan if p.action == "replace")
        n = len(plan)
        msg = f"{n} song{'s' if n != 1 else ''} imported. Available in Songs & sermon."
        extras = []
        if renamed:
            extras.append(f"{renamed} saved with a (2) suffix because the title already existed")
        if replaced:
            extras.append(f"{replaced} replaced the song with the same title")
        if extras:
            msg += "\n" + "; ".join(extras) + "."
        self.result_message = msg
        self.success.setText(msg)
        self.success.setStyleSheet(CARD_OK)
        self.success.show()
        self.btn_save.hide()
        self.btn_cancel.hide()
        self.btn_done.show()

    def _on_save_failed(self, exc: Exception) -> None:
        self.busy.hide()
        self.status.setText("")
        self.error_card.setText(f"Could not save\n{exc}")
        self.error_card.show()
        self._update_save_enabled()


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
