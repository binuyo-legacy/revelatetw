"""Operator UI (PyQt6): approval queue, live indicator, theme preview, projection window.

Layout:
  Operator window  - audio source picker, level meter, candidate queue, live indicator, keys
  Projection window - borderless, full-screen on a chosen display; shows only the program output
The operator window is never shown on the projector (spec F5 acceptance 1).
"""
from __future__ import annotations

import time

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QKeySequence, QShortcut
from PyQt6.QtWidgets import (QApplication, QComboBox, QDoubleSpinBox, QHBoxLayout, QLabel,
                             QListWidget, QListWidgetItem, QMainWindow, QPushButton,
                             QVBoxLayout, QWidget, QPlainTextEdit, QLineEdit)

from .approval import ApprovalQueue
from .detection import Candidate
from .theme import Theme

# Brand palette (spec section 1)
INDIGO, PURPLE, GOLD, MIDNIGHT, PARCHMENT, EMBER = (
    "#1E1B4B", "#4C1D95", "#D4A017", "#0F0B2E", "#F5F3FF", "#DC2626")


def render_verse_html(c: Candidate | None, theme: Theme) -> str:
    """HTML used by both the operator preview and the projection window."""
    if c is None:
        return ""
    text = c.display_text.replace("<", "&lt;")
    return (f'<div style="font-family:{theme.font_family};font-weight:{theme.font_weight};'
            f'font-size:{theme.font_size_px}px;line-height:{theme.line_height};color:{theme.text_color};">'
            f'{text}<br><span style="color:{theme.reference_color};font-size:{int(theme.font_size_px*0.6)}px;">'
            f'{c.reference} ({c.translation})</span></div>')


class ProjectionWindow(QWidget):
    """Borderless output. The scaffold shows the live verse on a solid background."""

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setWindowTitle("RevelateTW output")
        self.label = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self.label.setWordWrap(True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(80, 80, 80, 80)
        lay.addWidget(self.label)
        self.show_theme(Theme())
        self.show_blank()

    def show_theme(self, theme: Theme) -> None:
        self._theme = theme
        bg = theme.background.colors[0]
        self.setStyleSheet(f"background:{bg};")

    def show_verse(self, c: Candidate | None) -> None:
        self.label.setText(render_verse_html(c, self._theme))

    def show_blank(self) -> None:
        self.label.setText("")


class OperatorWindow(QMainWindow):
    def __init__(self, queue: ApprovalQueue, theme: Theme, projection: ProjectionWindow,
                 audio_meter=None, pipeline=None, live=None):
        super().__init__()
        self.setWindowTitle("RevelateTW (operator)")
        self.queue = queue
        self.pipeline = pipeline
        self.live = live                  # LiveTranscriptionLoop (mic or dev text)
        self.theme = theme
        self.projection = projection
        self._audio_meter = audio_meter  # callable returning {'peak_db', 'rms_db'} or None
        self._devices = []

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)

        # --- left: queue -------------------------------------------------------------
        left = QVBoxLayout()
        self.list = QListWidget()
        self.list.setStyleSheet(f"background:{INDIGO};color:{PARCHMENT};font-size:14px;")
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setStyleSheet(f"background:{INDIGO};color:{PARCHMENT};font-size:16px;")
        left.addWidget(QLabel("Candidates (approve to project)"))
        left.addWidget(self.list, 3)
        left.addWidget(QLabel("Selected verse"))
        left.addWidget(self.preview, 2)
        row = QHBoxLayout()
        self.btn_approve = self._btn("Approve (Enter)", GOLD, MIDNIGHT)
        self.btn_reject = self._btn("Reject (Esc)", EMBER, PARCHMENT)
        self.btn_hold = self._btn("Hold (H)", PURPLE, PARCHMENT)
        self.btn_blank = self._btn("Blank (B)", EMBER, PARCHMENT)
        for b in (self.btn_approve, self.btn_reject, self.btn_hold, self.btn_blank):
            row.addWidget(b)
        left.addLayout(row)
        root.addLayout(left, 3)

        # --- right: live indicator, audio, output ------------------------------------------
        right = QVBoxLayout()
        self.indicator = QLabel("IDLE")
        self.indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.indicator.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
        right.addWidget(self.indicator)
        self.meter = QLabel("Level: --")
        right.addWidget(self.meter)
        self.source_box = QComboBox()
        self.source_box.addItems(["Dev text feed", "Live microphone"])
        self.source_box.setToolTip("Dev text feed: typed sentences. Live microphone: audio from the device below.")
        right.addWidget(QLabel("Source"))
        right.addWidget(self.source_box)
        self.device_box = QComboBox()
        self.device_box.setToolTip("Audio input (WASAPI loopback lists mixing-desk output)")
        right.addWidget(QLabel("Audio input"))
        right.addWidget(self.device_box)
        self.btn_theme = QPushButton("Theme editor...")
        self.btn_theme.clicked.connect(self.open_theme_editor)
        right.addWidget(self.btn_theme)
        self.source_status = QLabel("")
        self.source_status.setWordWrap(True)
        right.addWidget(self.source_status)
        self.gain = QDoubleSpinBox()
        self.gain.setRange(-60, 20)
        self.gain.setSuffix(" dB")
        self.gain.setValue(0)
        right.addWidget(QLabel("Gain"))
        right.addWidget(self.gain)
        right.addStretch(1)
        self.feed = QLineEdit()
        self.feed.setPlaceholderText("Simulated speech: type a sentence and press Enter")
        self.feed.returnPressed.connect(self._on_feed)
        right.addWidget(QLabel("Dev feed (typed speech, used in text mode)"))
        right.addWidget(self.feed)
        root.addLayout(right, 2)

        # --- keys (spec F2: Enter approve, Esc reject, E edit, arrows move, B blank) ---
        for key, fn in [("Return", self.approve_selected), ("Escape", self.reject_selected),
                        ("E", self.edit_selected), ("H", self.hold_selected),
                        ("Down", lambda: self._move(1)), ("Up", lambda: self._move(-1)),
                        ("B", self.toggle_blank)]:
            QShortcut(QKeySequence(key), self, activated=fn)

        self.source_box.currentIndexChanged.connect(self._apply_source)
        self.device_box.currentIndexChanged.connect(self._apply_source)
        self._populate_devices()
        self.btn_approve.clicked.connect(self.approve_selected)
        self.btn_reject.clicked.connect(self.reject_selected)
        self.btn_hold.clicked.connect(self.hold_selected)
        self.btn_blank.clicked.connect(self.toggle_blank)
        self.list.currentRowChanged.connect(self._on_row)

        self._timer = QTimer(self, interval=150, timeout=self.refresh)
        self._timer.start()
        self.refresh()

    # --- live source -----------------------------------------------------------------------
    def _populate_devices(self) -> None:
        if self.live is None:
            self.source_box.setEnabled(False)
            self.device_box.setEnabled(False)
            self.source_status.setText("Live audio not available in this session (dev text feed only).")
            return
        try:
            from .audio import list_input_devices
            self._devices = list_input_devices()
        except Exception as exc:  # sounddevice missing or no audio host
            self._devices = []
            self.source_status.setText(f"Audio devices unavailable: {exc}")
        self.device_box.blockSignals(True)
        self.device_box.clear()
        for d in self._devices:
            self.device_box.addItem(f"{d.name}  ({d.channels} ch, {d.default_rate} Hz)")
        self.device_box.blockSignals(False)

    def _apply_source(self) -> None:
        if self.live is None:
            return
        if self.source_box.currentIndex() == 0 or not self._devices:
            self.live.use_text_feed()
            self.source_status.setText("Dev text feed (typed sentences)")
            return
        dev = self._devices[max(0, self.device_box.currentIndex())]
        try:
            self.live.start_mic(dev)
            self.source_status.setText(f"Listening: {dev.name}")
        except Exception as exc:  # device busy or unsupported; never leave the loop half-open
            self.live.use_text_feed()
            self.source_box.blockSignals(True)
            self.source_box.setCurrentIndex(0)
            self.source_box.blockSignals(False)
            self.source_status.setText(f"Mic failed, back to text feed: {exc}")

    def open_theme_editor(self) -> None:
        from .theme_editor import ThemeEditor
        dlg = ThemeEditor(self.theme, self)
        if dlg.exec():
            self.theme = dlg.theme
            self.projection.show_theme(self.theme)
            if self.queue.live:
                self.projection.show_verse(self.queue.live)

    def _btn(self, text, bg, fg) -> QPushButton:
        b = QPushButton(text)
        b.setStyleSheet(f"background:{bg};color:{fg};padding:10px;font-weight:bold;border-radius:6px;")
        return b

    # --- actions -----------------------------------------------------------------------
    def _move(self, d: int) -> None:
        self.queue.move(d)
        self.refresh()

    def _on_feed(self) -> None:
        text = self.feed.text()
        self.feed.clear()
        if text.strip():
            if self.live is not None:
                self.live.feed_text(text)
            elif self.pipeline:
                self.pipeline.on_transcript(text)
        self.refresh()

    def _on_row(self, row: int) -> None:
        if row >= 0:
            self.queue.selected = row
            self._show_selected()

    def approve_selected(self) -> None:
        c = self.queue.selected_item()
        if c:
            self.queue.approve(c.id)
            self.projection.show_theme(self.theme)
            self.projection.show_verse(c)
        self.refresh()

    def reject_selected(self) -> None:
        c = self.queue.selected_item()
        if c:
            self.queue.reject(c.id)
        self.refresh()

    def hold_selected(self) -> None:
        c = self.queue.selected_item()
        if c:
            self.queue.hold(c.id)
        self.refresh()

    def edit_selected(self) -> None:
        c = self.queue.selected_item()
        if c:
            # scaffold: edit happens in the preview box; press Ctrl+Enter to store it
            self.preview.setReadOnly(False)
            self.preview.setFocus()

    def toggle_blank(self) -> None:
        self.queue.set_blank(not self.queue.blank)
        if self.queue.blank:
            self.projection.show_blank()
        elif self.queue.live:
            self.projection.show_verse(self.queue.live)
        self.refresh()

    # --- rendering ------------------------------------------------------------------------
    def _show_selected(self) -> None:
        c = self.queue.selected_item()
        self.preview.setPlainText(
            f"{c.reference}  [{c.match_type}, {c.confidence}%]\n\n{c.display_text}\n\n"
            f"Heard: \u201c{c.snippet}\u201d" if c else "")

    def refresh(self) -> None:
        pending = self.queue.pending()
        current = self.list.currentRow()
        self.list.blockSignals(True)
        self.list.clear()
        for c in pending:
            item = QListWidgetItem(f"{c.reference}  {c.confidence}%  {c.match_type}  [{c.status}]")
            self.list.addItem(item)
        if pending:
            self.list.setCurrentRow(min(max(self.queue.selected, 0), len(pending) - 1))
        self.list.blockSignals(False)
        self._show_selected()
        st = self.queue.state
        self.indicator.setText({"live": "LIVE", "blank": "BLANK", "idle": "IDLE"}[st])
        color = {"live": GOLD, "blank": EMBER, "idle": PURPLE}[st]
        self.indicator.setStyleSheet(f"color:{color};")
        if self.live is not None:
            m = self.live.meter()
            self.meter.setText(f"Peak {m['peak_db']:.0f} dB   RMS {m['rms_db']:.0f} dB")
        elif self._audio_meter:
            m = self._audio_meter()
            self.meter.setText(f"Peak {m['peak_db']:.0f} dB   RMS {m['rms_db']:.0f} dB")


def run_app(queue: ApprovalQueue, theme: Theme, pipeline=None, projection_screen: int = 0,
            live=None):
    """Start the Qt event loop. pipeline receives dev-feed text; live (optional) runs the mic loop."""
    app = QApplication.instance() or QApplication([])
    projection = ProjectionWindow()
    screens = app.screens()
    if screens and len(screens) > projection_screen:
        projection.setGeometry(screens[projection_screen].geometry())
    projection.show_theme(theme)
    op = OperatorWindow(queue, theme, projection, pipeline=pipeline, live=live)
    op.resize(1200, 720)
    op.show()
    projection.show()
    return app.exec()
