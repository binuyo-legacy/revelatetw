"""Operator UI (PyQt6): approval queue, live indicator, theme preview, projection window.

Layout:
  Operator window  - audio source picker, level meter, candidate queue, live indicator, keys
  Projection window - borderless, full-screen on a chosen display; shows only the program output
The operator window is never shown on the projector (spec F5 acceptance 1).
"""
from __future__ import annotations

import time
from typing import Optional

from PyQt6.QtCore import QRect, Qt, QTimer
from PyQt6.QtGui import QColor, QKeySequence, QShortcut
from PyQt6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFileDialog, QFrame,
                             QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                             QListWidgetItem, QMainWindow, QPlainTextEdit, QPushButton, QScrollArea,
                             QSpinBox, QTabWidget, QVBoxLayout, QWidget)

from .approval import ApprovalQueue
from .detection import Candidate
from .displays import DisplayInfo, list_displays
from .output_state import LiveOutputState
from .sermon import SermonInfo
from .songs import Slide, Song, SongLibrary, split_lyrics
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


def render_song_html(slide: Slide | None, theme: Theme) -> str:
    """One lyric slide: its lines, centred, in the theme's text colour. The label is hidden on
    the output (operators see it in the slide list); the reference colour is not used."""
    if slide is None:
        return ""
    size = max(12, int(theme.font_size_px * 0.8))
    body = "<br>".join(line.replace("&", "&amp;").replace("<", "&lt;") for line in slide.lines)
    return (f'<div style="font-family:{theme.font_family};font-weight:{theme.font_weight};'
            f'font-size:{size}px;line-height:{theme.line_height};color:{theme.text_color};">{body}</div>')


def render_sermon_html(info: SermonInfo | None, theme: Theme) -> str:
    """Sermon info slide: title big, speaker and scripture reference smaller in the accent colour."""
    if info is None or not info.lines():
        return ""
    esc = lambda s: s.replace("&", "&amp;").replace("<", "&lt;")  # noqa: E731
    head = (f'<div style="font-family:{theme.font_family};font-weight:{theme.font_weight};'
            f'font-size:{theme.font_size_px}px;line-height:{theme.line_height};color:{theme.text_color};">'
            f'{esc(info.title)}</div>' if info.title else "")
    rest = [esc(x) for x in (info.speaker, info.reference) if x]
    tail = ""
    if rest:
        tail = (f'<div style="font-family:{theme.font_family};font-size:{int(theme.font_size_px*0.6)}px;'
                f'color:{theme.reference_color};margin-top:12px;">' + "<br>".join(rest) + "</div>")
    return head + tail


class ProjectionWindow(QWidget):
    """Borderless live output. Standalone: fullscreen on a chosen display, no OBS needed.

    Hiding it (live output OFF) lets another app take the projector. Any capture tool
    (OBS window capture, virtual camera, other studio software) can read this window.
    """

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

    def move_to_display(self, geometry) -> None:
        """Cover a whole display (QRect). Borderless and sized to the monitor, so it reads as fullscreen."""
        self._display_rect = geometry
        self.setGeometry(geometry)

    def present(self) -> None:
        """Show full-screen on the chosen display (no OBS needed; the window itself is the output)."""
        rect = getattr(self, "_display_rect", None)
        if rect is not None:
            self.setGeometry(rect)
        self.showFullScreen()
        self.raise_()

    def show_verse(self, c: Candidate | None) -> None:
        self.label.setText(render_verse_html(c, self._theme))

    def show_song_slide(self, slide: Slide | None) -> None:
        self.label.setText(render_song_html(slide, self._theme))

    def show_sermon(self, info: SermonInfo | None) -> None:
        self.label.setText(render_sermon_html(info, self._theme))

    def show_blank(self) -> None:
        self.label.setText("")


QSS = """
QMainWindow, QWidget#root { background: #0b0f19; }
QFrame#toolbar { background: #171d2b; border-bottom: 1px solid #232b3b; }
QFrame#panel { background: #131926; border: 1px solid #232b3b; border-radius: 14px; }
QFrame#card { background: #161c2a; border: 1px solid #2a3346; border-radius: 14px; }
QFrame#card[selected="true"] { border: 2px solid #facc15; background: #1b2231; }
QFrame#tile { background: #161c2a; border: 1px solid #2a3346; border-radius: 10px; }
QFrame#slide { background: #0b0f19; border: 3px solid #facc15; border-radius: 6px; }
QLabel { color: #e5e7eb; }
QLabel#brand { color: #0b0f19; background: #facc15; border-radius: 8px; font-weight: 800; font-size: 18px; padding: 4px 9px; }
QLabel#title { color: #f8fafc; font-size: 16px; font-weight: 700; }
QLabel#sub { color: #94a3b8; font-size: 12px; }
QLabel#panelTitle { color: #f8fafc; font-size: 14px; font-weight: 700; }
QLabel#badge { color: #facc15; background: #2a2412; border-radius: 9px; padding: 2px 8px; font-size: 11px; font-weight: 600; }
QLabel#badgeGreen { color: #86efac; background: #1f3a2e; border-radius: 9px; padding: 2px 7px; font-size: 11px; font-weight: 700; }
QLabel#live { color: #f87171; background: #3a1418; border: 1px solid #b42f3d; border-radius: 12px; padding: 3px 10px; font-weight: 800; }
QLabel#timer { color: #facc15; font-family: Consolas, monospace; font-size: 14px; font-weight: 700; }
QLabel#tileLabel { color: #94a3b8; font-size: 11px; }
QLabel#tileValue { color: #f8fafc; font-size: 13px; font-weight: 600; }
QLabel#verse { color: #e5e7eb; font-style: italic; font-size: 13px; }
QLabel#ref { color: #facc15; font-weight: 700; font-size: 13px; }
QLabel#transcript { color: #cbd5e1; font-size: 13px; }
QLabel#time { color: #64748b; font-family: Consolas, monospace; font-size: 12px; }
QLabel#hit { color: #facc15; background: rgba(250,204,21,0.14); border-radius: 4px; padding: 0 3px; font-weight: 700; }
QLabel#footer { color: #94a3b8; font-size: 11px; }
QLabel#footerOk { color: #86efac; font-size: 11px; }
QLabel#slideRef { color: #facc15; font-weight: 700; font-size: 13px; }
QLabel#slideText { color: #f8fafc; font-family: Georgia; font-size: 15px; }
QPushButton { background: #1d2535; color: #e5e7eb; border: 1px solid #2f3a52; border-radius: 8px; padding: 7px 12px; font-weight: 600; }
QPushButton:hover { border-color: #facc15; }
QPushButton#approve { background: #2f9e62; color: #06140c; border: 1px solid #3cc47e; font-weight: 800; }
QPushButton#reject { background: #3a1f2a; color: #f87171; border: 1px solid #7f2a38; font-weight: 700; }
QPushButton#seg { background: #1d2535; color: #94a3b8; border: 1px solid #2f3a52; border-radius: 0px; padding: 5px 12px; }
QPushButton#seg[active="true"] { background: #facc15; color: #0b0f19; border-color: #facc15; font-weight: 800; }
QPushButton#nav { background: #1d2535; color: #facc15; border: 1px solid #facc15; font-weight: 800; padding: 6px 14px; }
QPushButton#nav:disabled { color: #475569; border-color: #2f3a52; }
QPushButton#live { background: #3a1418; color: #f87171; border: 1px solid #b42f3d; border-radius: 12px; padding: 3px 12px; font-weight: 800; }
QPushButton#live[on="false"] { background: #161c2a; color: #64748b; border: 1px dashed #475569; }
QTabWidget::pane { border: none; }
QTabBar::tab { background: #1d2535; color: #94a3b8; padding: 6px 14px; border-top-left-radius: 8px; border-top-right-radius: 8px; }
QTabBar::tab:selected { background: #facc15; color: #0b0f19; font-weight: 800; }
QLabel#liveNote { color: #f59e0b; font-size: 11px; }
QPushButton#ghost { background: transparent; border: 1px solid #2f3a52; color: #cbd5e1; }
QLineEdit, QComboBox { background: #0f1522; color: #e5e7eb; border: 1px solid #2f3a52; border-radius: 8px; padding: 6px 8px; }
QLineEdit:focus, QComboBox:focus { border-color: #facc15; }
QComboBox QAbstractItemView { background: #0f1522; color: #e5e7eb; selection-background-color: #facc15; selection-color: #0b0f19; }
QListWidget { background: #0f1522; color: #e5e7eb; border: 1px solid #2f3a52; border-radius: 8px; }
QListWidget::item:selected { background: #facc15; color: #0b0f19; }
QDoubleSpinBox { background: #0f1522; color: #e5e7eb; border: 1px solid #2f3a52; border-radius: 8px; padding: 4px; }
QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }
QFrame#statusbar { background: #0f1522; border-top: 1px solid #232b3b; }
"""


def _set_prop(w, name, value) -> None:
    """Re-polish a widget after changing a QSS dynamic property."""
    w.setProperty(name, value)
    w.style().unpolish(w)
    w.style().polish(w)


def _label(text: str, obj: str = "", wrap: bool = False) -> QLabel:
    lab = QLabel(text)
    if obj:
        lab.setObjectName(obj)
    lab.setWordWrap(wrap)
    return lab


def _seg(text: str) -> QPushButton:
    b = QPushButton(text)
    b.setObjectName("seg")
    b.setCheckable(True)
    return b


class OperatorWindow(QMainWindow):
    def __init__(self, queue: ApprovalQueue, theme: Theme, projection: ProjectionWindow,
                 audio_meter=None, pipeline=None, live=None, songs_dir: str = "data/songs"):
        super().__init__()
        self.setWindowTitle("RevelateTW \u2014 Operator")
        self.queue = queue
        self.pipeline = pipeline
        self.live = live                  # LiveTranscriptionLoop (mic or dev text)
        self.theme = theme
        self.projection = projection
        self._audio_meter = audio_meter  # callable returning {'peak_db', 'rms_db'} or None
        self._devices = []
        self._started = time.time()
        self._cursor: Optional[tuple[int, int, int]] = None  # (book, chapter, verse) last projected
        self._store = getattr(pipeline, "detector", None) and pipeline.detector.store
        self.output = LiveOutputState(on=True)     # LIVE pill: projection window shown or hidden
        self._kind: Optional[str] = None           # what the output shows: verse | song | sermon
        self._song_live: Optional[tuple[Song, int]] = None
        self._song_pending: Optional[tuple[Song, int]] = None
        self._sermon_live: Optional[SermonInfo] = None
        self._song_sel: Optional[Song] = None
        self._editing_id: str = ""
        self.library = SongLibrary(songs_dir)
        self._songs: list[Song] = []

        self.setStyleSheet(QSS)
        central = QWidget()
        central.setObjectName("root")
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._build_toolbar())

        body = QHBoxLayout()
        body.setContentsMargins(14, 12, 14, 10)
        body.setSpacing(12)
        body.addWidget(self._build_transcript_panel(), 3)
        body.addWidget(self._build_queue_panel(), 3)
        body.addWidget(self._build_preview_panel(), 3)
        live_page = QWidget()
        live_page.setLayout(body)
        self._tabs = QTabWidget()
        self._tabs.addTab(live_page, "Live (verses)")
        self._tabs.addTab(self._build_songs_tab(), "Songs & sermon")
        outer.addWidget(self._tabs, 1)
        outer.addWidget(self._build_statusbar())

        self._build_shortcuts()
        self.source_box.currentIndexChanged.connect(self._apply_source)
        self.device_box.currentIndexChanged.connect(self._apply_source)
        self._populate_devices()
        self.btn_source_mic.toggled.connect(self._on_source_toggle)
        self.btn_source_dev.toggled.connect(self._on_source_toggle)
        self.btn_approve.clicked.connect(self.approve_selected)
        self.btn_reject.clicked.connect(self.reject_selected)
        self.btn_hold.clicked.connect(self.hold_selected)
        self.btn_blank.clicked.connect(self.toggle_blank)
        self.btn_prev.clicked.connect(lambda: self.step(-1))
        self.btn_next.clicked.connect(lambda: self.step(+1))
        self.list.currentRowChanged.connect(self._on_row)
        self.search.textChanged.connect(self._on_search_text)
        self.search.installEventFilter(self)
        self.search_list.itemActivated.connect(self._on_suggestion_activated)
        self.btn_manual.toggled.connect(self._on_manual_toggle)
        self.man_testament.currentIndexChanged.connect(self._fill_books)
        self.man_book.currentIndexChanged.connect(self._fill_chapters)
        self.man_chapter.currentIndexChanged.connect(self._fill_verses)
        self.btn_project_manual.clicked.connect(self._project_manual)
        self.feed.returnPressed.connect(self._on_feed)
        self.display_box.currentIndexChanged.connect(self._on_display_chosen)
        self.btn_rescan.clicked.connect(lambda: self._populate_displays(self.display_box.currentIndex()))
        self.song_search.textChanged.connect(self._fill_song_list)
        self.song_list.currentRowChanged.connect(self._on_song_row)
        self.btn_new_song.clicked.connect(self._new_song)
        self.btn_import_song.clicked.connect(self._import_song)
        self.btn_split.clicked.connect(self._split_editor)
        self.btn_save_song.clicked.connect(self._save_song)
        self.slide_pick.currentRowChanged.connect(self._on_slide_pick)
        self.btn_song_send.clicked.connect(self._send_slide)
        self.btn_song_approve.clicked.connect(self.approve_pending_song)
        self.btn_song_reject.clicked.connect(self.reject_pending_song)
        self.btn_song_prev.clicked.connect(lambda: self.step_song(-1))
        self.btn_song_next.clicked.connect(lambda: self.step_song(+1))
        self.btn_sermon_show.clicked.connect(self.show_sermon_slide)
        self.btn_sermon_clear.clicked.connect(self.clear_sermon_slide)

        self._timer = QTimer(self, interval=150, timeout=self.refresh)
        self._timer.start()
        self._fill_testaments()
        self._populate_displays()
        self._fill_song_list()
        self._apply_output_state()
        self.refresh()

    # --- layout builders -----------------------------------------------------------------
    def _build_toolbar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("toolbar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 10, 16, 10)
        lay.setSpacing(10)
        lay.addWidget(_label("R", "brand"))
        t = QVBoxLayout()
        t.setSpacing(0)
        t.addWidget(_label("RevelateTW \u2014 Operator", "title"))
        lay.addLayout(t)
        lay.addStretch(1)
        lay.addWidget(_label("Source", "sub"))
        seg = QHBoxLayout()
        seg.setSpacing(0)
        self.btn_source_mic = _seg("Mic")
        self.btn_source_dev = _seg("Dev feed")
        self.btn_source_mic.setToolTip("Live microphone (audio input picker on the right)")
        self.btn_source_dev.setToolTip("Dev text feed: type sermon text in the feed box")
        seg.addWidget(self.btn_source_mic)
        seg.addWidget(self.btn_source_dev)
        seg_frame = QWidget()
        seg_frame.setLayout(seg)
        lay.addWidget(seg_frame)
        self.session_label = _label("Sunday Service", "sub")
        lay.addWidget(self.session_label)
        self.timer_label = _label("00:00:00", "timer")
        lay.addWidget(self.timer_label)
        self.live_pill = QPushButton("\u25cf LIVE")
        self.live_pill.setObjectName("live")
        self.live_pill.setProperty("on", "true")
        self.live_pill.setCursor(Qt.CursorShape.PointingHandCursor)
        self.live_pill.setToolTip("Click to switch the live output OFF (hides the projection window) or ON")
        self.live_pill.clicked.connect(self.toggle_output)
        lay.addWidget(self.live_pill)
        return bar

    def _build_transcript_panel(self) -> QFrame:
        frame, lay = self._panel("Sermon Transcription", "")
        self.transcript_badge = _label("0 detected", "badge")
        frame.layout().itemAt(0).layout().insertWidget(2, self.transcript_badge)
        self.transcript_box = QVBoxLayout()
        self.transcript_box.setSpacing(8)
        holder = QWidget()
        holder.setLayout(self.transcript_box)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(holder)
        self._transcript_scroll = scroll
        lay.addWidget(scroll, 1)
        self.feed = QLineEdit()
        self.feed.setPlaceholderText("Dev feed: type a sentence and press Enter")
        lay.addWidget(self.feed)
        foot = QHBoxLayout()
        self.transcriber_label = _label("Transcriber: text feed", "footer")
        foot.addWidget(self.transcriber_label)
        foot.addStretch(1)
        self.latency_label = _label("Latency 0.0s", "footer")
        foot.addWidget(self.latency_label)
        lay.addLayout(foot)
        return frame

    def _build_queue_panel(self) -> QFrame:
        frame, lay = self._panel("Approval Queue", "")
        self.queue_badge = _label("0 pending", "badge")
        frame.layout().itemAt(0).layout().insertWidget(2, self.queue_badge)

        # search with autosuggest + manual verse mode (collapsible)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search: 'first john', '1 jn 3:16', 'jo 3 16'... (\u2191\u2193, Enter projects)")
        lay.addWidget(self.search)
        self.search_list = QListWidget()
        self.search_list.setMaximumHeight(120)
        self.search_list.hide()
        lay.addWidget(self.search_list)

        self.btn_manual = QPushButton("Manual verse mode \u25b8")
        self.btn_manual.setCheckable(True)
        self.btn_manual.setObjectName("ghost")
        lay.addWidget(self.btn_manual)
        self.manual_box = QWidget()
        mg = QGridLayout(self.manual_box)
        mg.setContentsMargins(0, 0, 0, 0)
        self.man_testament = QComboBox()
        self.man_book = QComboBox()
        self.man_chapter = QComboBox()
        self.man_verse = QComboBox()
        for i, (w, lbl) in enumerate([(self.man_testament, "Testament"), (self.man_book, "Book"),
                                      (self.man_chapter, "Chapter"), (self.man_verse, "Verse")]):
            mg.addWidget(_label(lbl, "sub"), 0, i)
            mg.addWidget(w, 1, i)
        self.btn_project_manual = QPushButton("Project this verse")
        self.btn_project_manual.setObjectName("approve")
        mg.addWidget(self.btn_project_manual, 2, 0, 1, 4)
        self.manual_box.hide()
        lay.addWidget(self.manual_box)
        self._manual_on = False

        self.list = QListWidget()
        lay.addWidget(self.list, 3)
        self.cards_hint = _label("Select a card. First card is next to project.", "sub")
        lay.addWidget(self.cards_hint)
        self.preview = QLabel()
        self.preview.setObjectName("verse")
        self.preview.setWordWrap(True)
        self.preview.setTextFormat(Qt.TextFormat.PlainText)
        lay.addWidget(self.preview, 1)

        row = QHBoxLayout()
        self.btn_approve = QPushButton("Approve (Enter)")
        self.btn_approve.setObjectName("approve")
        self.btn_reject = QPushButton("Reject (Esc)")
        self.btn_reject.setObjectName("reject")
        self.btn_hold = QPushButton("Hold (H)")
        self.btn_blank = QPushButton("Blank (B)")
        for b in (self.btn_approve, self.btn_reject, self.btn_hold, self.btn_blank):
            row.addWidget(b)
        lay.addLayout(row)
        foot = QHBoxLayout()
        self.auto_label = _label("Auto-approve: off", "footer")
        foot.addWidget(self.auto_label)
        foot.addStretch(1)
        self.cleared_label = _label("Queue cleared 0 this session", "footerOk")
        foot.addWidget(self.cleared_label)
        lay.addLayout(foot)
        return frame

    def _build_preview_panel(self) -> QFrame:
        frame, lay = self._panel("Live Projection Preview", "")
        self.output_badge = _label("Output 1 \u00b7 1920\u00d71080", "badge")
        frame.layout().itemAt(0).layout().insertWidget(2, self.output_badge)
        self.slide = QFrame()
        self.slide.setObjectName("slide")
        sl = QVBoxLayout(self.slide)
        sl.setContentsMargins(18, 14, 18, 14)
        self.slide_text = _label("", "slideText", wrap=True)
        self.slide_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.slide_ref = _label("", "slideRef")
        self.slide_ref.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sl.addWidget(self.slide_text, 1)
        sl.addWidget(self.slide_ref)
        lay.addWidget(self.slide, 1)

        nav = QHBoxLayout()
        self.btn_prev = QPushButton("\u25c0 Prev verse (\u2190)")
        self.btn_prev.setObjectName("nav")
        self.btn_next = QPushButton("Next verse (\u2192) \u25b6")
        self.btn_next.setObjectName("nav")
        nav.addWidget(self.btn_prev)
        nav.addWidget(self.btn_next)
        lay.addLayout(nav)
        self.next_label = _label("", "sub", wrap=True)
        lay.addWidget(self.next_label)

        grid = QGridLayout()
        grid.setSpacing(8)
        self.tile_theme = self._tile("Theme", self.theme.name)
        self.tile_transition = self._tile("Transition", f"{self.theme.transition.title()} \u00b7 {self.theme.transition_ms}ms")
        self.tile_feed = self._tile("Live output", "On")
        self.tile_audio = self._tile("Audio route", "Dev feed")
        for i, t in enumerate([self.tile_theme, self.tile_transition, self.tile_feed, self.tile_audio]):
            grid.addWidget(t, i // 2, i % 2)
        lay.addLayout(grid)

        disp = QHBoxLayout()
        self.display_box = QComboBox()
        self.display_box.setToolTip("Monitor for the live output. Fullscreen borderless on that display.")
        self.btn_rescan = QPushButton("Rescan")
        self.btn_rescan.setObjectName("ghost")
        disp.addWidget(self.display_box, 1)
        disp.addWidget(self.btn_rescan)
        lay.addWidget(_label("Output display (fullscreen, any capture software can read it)", "sub"))
        lay.addLayout(disp)
        self.btn_theme = QPushButton("Theme editor...")
        self.btn_theme.clicked.connect(self.open_theme_editor)
        lay.addWidget(self.btn_theme)
        self.meter = _label("Level: --", "footer")
        lay.addWidget(self.meter)
        self.source_status = _label("", "footer", wrap=True)
        lay.addWidget(self.source_status)
        self.gain = QDoubleSpinBox()
        self.gain.setRange(-60, 20)
        self.gain.setSuffix(" dB")
        self.gain.setValue(0)
        self.gain.setToolTip("Input gain")
        lay.addWidget(self.gain)
        self.source_box = QComboBox()
        self.source_box.addItems(["Dev text feed", "Live microphone"])
        self.source_box.hide()   # the Mic / Dev feed pills in the toolbar drive this
        self.device_box = QComboBox()
        self.device_box.setToolTip("Audio input (WASAPI loopback lists mixing-desk output)")
        self.device_box.setPlaceholderText("Audio input")
        lay.addWidget(self.device_box)
        self.indicator = _label("IDLE", "footer")
        self.indicator.hide()
        lay.addWidget(self.indicator)

        status = QHBoxLayout()
        self.footer_proj = _label("Projecting", "footerOk")
        status.addWidget(self.footer_proj)
        status.addStretch(1)
        self.footer_sync = _label("Preview synced", "footer")
        status.addWidget(self.footer_sync)
        lay.addLayout(status)
        return frame

    def _build_songs_tab(self) -> QWidget:
        page = QWidget()
        root = QHBoxLayout(page)
        root.setContentsMargins(14, 12, 14, 10)
        root.setSpacing(12)

        # library
        left, ll = self._panel("Song Library", "")
        self.song_search = QLineEdit()
        self.song_search.setPlaceholderText("Search title, artist or a lyric word")
        ll.addWidget(self.song_search)
        self.song_list = QListWidget()
        ll.addWidget(self.song_list, 1)
        row = QHBoxLayout()
        self.btn_new_song = QPushButton("New song")
        self.btn_import_song = QPushButton("Import file")
        row.addWidget(self.btn_new_song)
        row.addWidget(self.btn_import_song)
        ll.addLayout(row)
        self.song_count = _label("", "footer")
        ll.addWidget(self.song_count)
        root.addWidget(left, 3)

        # editor
        mid, ml = self._panel("Song Editor", "")
        self.song_title = QLineEdit()
        self.song_title.setPlaceholderText("Song title")
        self.song_artist = QLineEdit()
        self.song_artist.setPlaceholderText("Artist (optional)")
        ml.addWidget(self.song_title)
        ml.addWidget(self.song_artist)
        self.song_lyrics = QPlainTextEdit()
        self.song_lyrics.setPlaceholderText(
            "Paste lyrics. A blank line starts a new slide.\n"
            "Headers such as [Verse 1], Chorus: or Bridge start a labelled slide.")
        ml.addWidget(self.song_lyrics, 1)
        split_row = QHBoxLayout()
        split_row.addWidget(_label("Lines per slide", "sub"))
        self.max_lines = QSpinBox()
        self.max_lines.setRange(1, 12)
        self.max_lines.setValue(4)
        split_row.addWidget(self.max_lines)
        self.btn_split = QPushButton("Split into slides")
        split_row.addWidget(self.btn_split, 1)
        ml.addLayout(split_row)
        self.slide_pick = QListWidget()
        self.slide_pick.setMaximumHeight(150)
        ml.addWidget(self.slide_pick)
        self.btn_save_song = QPushButton("Save song")
        self.btn_save_song.setObjectName("approve")
        ml.addWidget(self.btn_save_song)
        self.editor_status = _label("", "footer", wrap=True)
        ml.addWidget(self.editor_status)
        self._editor_slides: list[Slide] = []
        root.addWidget(mid, 3)

        # live: slide navigation, approval, sermon info
        right, rl = self._panel("Song Projection", "")
        self.song_now = _label("Pick a song in the library, then choose a slide.", "verse", wrap=True)
        rl.addWidget(self.song_now)
        self.slide_now_list = QListWidget()
        self.slide_now_list.setMaximumHeight(160)
        rl.addWidget(self.slide_now_list)
        self.song_direct = QCheckBox("Direct (project now, no approval)")
        self.song_direct.setChecked(False)
        rl.addWidget(self.song_direct)
        self.btn_song_send = QPushButton("Send selected slide (Enter)")
        self.btn_song_send.setObjectName("approve")
        rl.addWidget(self.btn_song_send)
        self.song_pending_label = _label("", "footerOk", wrap=True)
        rl.addWidget(self.song_pending_label)
        pend = QHBoxLayout()
        self.btn_song_approve = QPushButton("Approve (Enter)")
        self.btn_song_approve.setObjectName("approve")
        self.btn_song_reject = QPushButton("Reject (Esc)")
        self.btn_song_reject.setObjectName("reject")
        pend.addWidget(self.btn_song_approve)
        pend.addWidget(self.btn_song_reject)
        rl.addLayout(pend)
        nav = QHBoxLayout()
        self.btn_song_prev = QPushButton("\u25c0 Prev slide (\u2190)")
        self.btn_song_prev.setObjectName("nav")
        self.btn_song_next = QPushButton("Next slide (\u2192) \u25b6")
        self.btn_song_next.setObjectName("nav")
        nav.addWidget(self.btn_song_prev)
        nav.addWidget(self.btn_song_next)
        rl.addLayout(nav)
        rl.addWidget(_label("Sermon info slide", "panelTitle"))
        self.sermon_title = QLineEdit()
        self.sermon_title.setPlaceholderText("Sermon title")
        self.sermon_speaker = QLineEdit()
        self.sermon_speaker.setPlaceholderText("Speaker (optional)")
        rl.addWidget(self.sermon_title)
        rl.addWidget(self.sermon_speaker)
        srow = QHBoxLayout()
        self.btn_sermon_show = QPushButton("Show sermon info")
        self.btn_sermon_show.setObjectName("approve")
        self.btn_sermon_clear = QPushButton("Clear")
        self.btn_sermon_clear.setObjectName("ghost")
        srow.addWidget(self.btn_sermon_show, 1)
        srow.addWidget(self.btn_sermon_clear)
        rl.addLayout(srow)
        self.sermon_note = _label("Shows the title, speaker and the last projected verse reference.", "sub", wrap=True)
        rl.addWidget(self.sermon_note)
        rl.addStretch(1)
        root.addWidget(right, 3)
        return page

    def _build_statusbar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("statusbar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 6, 16, 6)
        self.status_transcriber = _label("Transcriber: text feed", "footer")
        self.status_latency = _label("Latency 0.0s", "footer")
        self.status_auto = _label("Auto-approve: off", "footer")
        self.status_cleared = _label("Queue cleared 0", "footerOk")
        for w in (self.status_transcriber, self.status_latency, self.status_auto):
            lay.addWidget(w)
            lay.addWidget(_label("\u00b7", "footer"))
        lay.addWidget(self.status_cleared)
        lay.addStretch(1)
        self.status_key = _label("\u2190\u2192 verse   Space next   Enter approve   Esc reject   / search", "footer")
        lay.addWidget(self.status_key)
        return bar

    def _panel(self, title: str, badge: str):
        frame = QFrame()
        frame.setObjectName("panel")
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)
        head = QHBoxLayout()
        head.addWidget(_label(title, "panelTitle"))
        head.addStretch(1)
        lay.addLayout(head)
        if badge:
            head.addWidget(_label(badge, "badge"))
        return frame, lay

    def _tile(self, label: str, value: str) -> QFrame:
        f = QFrame()
        f.setObjectName("tile")
        v = QVBoxLayout(f)
        v.setContentsMargins(10, 8, 10, 8)
        v.setSpacing(2)
        v.addWidget(_label(label.upper(), "tileLabel"))
        val = _label(value, "tileValue")
        val.setWordWrap(True)
        v.addWidget(val)
        f.value = val  # type: ignore[attr-defined]
        return f

    def _build_shortcuts(self) -> None:
        # Typing in a text box keeps its keys; the window-level shortcuts are only for the
        # queue and projection, so 'space' or 'b' never fires while the operator is typing.
        def guard(fn):
            def run():
                if self._typing():
                    return
                fn()
            return run
        # Shortcut keys (B, H, E, arrows, Space) are ignored while any text box has focus,
        # so typing 'bible' in the search never blanks the screen.

        for key, fn in [("Return", self.approve_selected), ("Escape", self.reject_selected),
                        ("E", self.edit_selected), ("H", self.hold_selected),
                        ("Down", lambda: self._move(1)), ("Up", lambda: self._move(-1)),
                        ("Left", lambda: self.step(-1)), ("Right", lambda: self.step(+1)),
                        ("Space", lambda: self.step(+1)), ("B", self.toggle_blank),
                        ("O", self.toggle_output),
                        ("/", self.focus_search)]:
            QShortcut(QKeySequence(key), self, activated=guard(fn))

    def _typing(self) -> bool:
        fw = QApplication.focusWidget()
        return isinstance(fw, (QLineEdit, QPlainTextEdit))

    # --- live source -----------------------------------------------------------------------
    def _populate_devices(self) -> None:
        if self.live is None:
            self.btn_source_mic.setEnabled(False)
            self.device_box.setEnabled(False)
            self.btn_source_dev.setChecked(True)
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

    def _on_source_toggle(self, checked: bool) -> None:
        if not checked:
            return
        mic = self.sender() is self.btn_source_mic
        self.btn_source_mic.setChecked(mic)
        self.btn_source_dev.setChecked(not mic)
        self.source_box.blockSignals(True)
        self.source_box.setCurrentIndex(1 if mic else 0)
        self.source_box.blockSignals(False)
        self._apply_source()

    def _apply_source(self) -> None:
        if self.live is None:
            return
        if self.source_box.currentIndex() == 0 or not self._devices:
            self.live.use_text_feed()
            self.source_status.setText("Dev text feed (typed sentences)")
            self.transcriber_label.setText("Transcriber: text feed")
            self.status_transcriber.setText("Transcriber: text feed")
            self.tile_audio.value.setText("Dev feed")
            return
        dev = self._devices[max(0, self.device_box.currentIndex())]
        try:
            self.live.start_mic(dev)
            self.source_status.setText(f"Listening: {dev.name}")
            self.tile_audio.value.setText(dev.name)
            self.transcriber_label.setText("Transcriber: Whisper")
            self.status_transcriber.setText("Transcriber: Whisper")
        except Exception as exc:  # device busy or unsupported; never leave the loop half-open
            self.live.use_text_feed()
            self.source_box.blockSignals(True)
            self.source_box.setCurrentIndex(0)
            self.source_box.blockSignals(False)
            self.btn_source_dev.setChecked(True)
            self.source_status.setText(f"Mic failed, back to text feed: {exc}")

    def open_theme_editor(self) -> None:
        from .theme_editor import ThemeEditor
        dlg = ThemeEditor(self.theme, self)
        if dlg.exec():
            self.theme = dlg.theme
            self.projection.show_theme(self.theme)
            self.tile_theme.value.setText(self.theme.name)
            self.tile_transition.value.setText(f"{self.theme.transition.title()} \u00b7 {self.theme.transition_ms}ms")
            self._render_output()

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

    def _project(self, c: Candidate) -> None:
        self.queue.approve(c.id)
        self._show_on_output(c)

    def _show_on_output(self, c: Candidate) -> None:
        self._cursor = (c.book_id, c.chapter, c.verse)
        self._kind = "verse"
        self._song_pending = None
        self.projection.show_theme(self.theme)
        self.projection.show_verse(c)

    def _render_output(self) -> None:
        """Re-draw whatever the output is showing (after theme change or blank toggle)."""
        self.projection.show_theme(self.theme)
        if self.queue.blank:
            self.projection.show_blank()
        elif self._kind == "song" and self._song_live:
            song, i = self._song_live
            self.projection.show_song_slide(song.slides[i])
        elif self._kind == "sermon" and self._sermon_live:
            self.projection.show_sermon(self._sermon_live)
        elif self.queue.live:
            self.projection.show_verse(self.queue.live)

    def approve_selected(self) -> None:
        if self._tabs.currentIndex() == 1:
            self.approve_pending_song()
            return
        c = self.queue.selected_item()
        if c:
            self._project(c)
        self.refresh()

    def reject_selected(self) -> None:
        if self._tabs.currentIndex() == 1:
            self.reject_pending_song()
            return
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
            self.preview.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
            self.preview.setFocus()

    def toggle_blank(self) -> None:
        self.queue.set_blank(not self.queue.blank)
        self._render_output()
        self.refresh()

    # --- live output ON/OFF (LIVE pill, key O) --------------------------------------------
    def toggle_output(self) -> None:
        self.output.toggle()
        self._apply_output_state()
        self.refresh()

    def _apply_output_state(self) -> None:
        on = self.output.on
        self.live_pill.setText(self.output.pill_text())
        self.live_pill.setChecked(on)
        self.live_pill.setProperty("on", "true" if on else "false")
        self.live_pill.style().unpolish(self.live_pill)
        self.live_pill.style().polish(self.live_pill)
        self.live_pill.setToolTip("Live output ON: click to hide the projection window (O)" if on
                                  else "Live output OFF: projection window hidden. Click to show (O)")
        if on:
            self._render_output()
            self.projection.present()
        else:
            self.projection.hide()
        self.tile_feed.value.setText("On" if on else "Off (hidden)")

    # --- display picker -----------------------------------------------------------------------
    def _populate_displays(self, keep: int = 0) -> None:
        self._displays: list[DisplayInfo] = list_displays()
        self.display_box.blockSignals(True)
        self.display_box.clear()
        for d in self._displays:
            self.display_box.addItem(d.label)
        if not self._displays:
            self.display_box.addItem("No display found")
        self.display_box.setCurrentIndex(min(max(keep, 0), max(len(self._displays) - 1, 0)))
        self.display_box.blockSignals(False)
        self._on_display_chosen(self.display_box.currentIndex())

    def _on_display_chosen(self, idx: int) -> None:
        if not getattr(self, "_displays", None) or idx < 0 or idx >= len(self._displays):
            return
        d = self._displays[idx]
        self.projection.move_to_display(QRect(d.x, d.y, d.width, d.height))
        if self.output.on:
            self.projection.present()

    # --- songs library ------------------------------------------------------------------------
    def _fill_song_list(self) -> None:
        self._songs = self.library.search(self.song_search.text())
        self.song_list.blockSignals(True)
        self.song_list.clear()
        for s in self._songs:
            label = s.title + (f"  \u2014 {s.artist}" if s.artist else "")
            self.song_list.addItem(f"{label}  ({len(s.slides)} slides)")
        self.song_list.blockSignals(False)
        total = len(self.library.load_all())
        self.song_count.setText(f"{len(self._songs)} shown  \u00b7  {total} in library")

    def _on_song_row(self, row: int) -> None:
        if row < 0 or row >= len(self._songs):
            return
        self._song_sel = self._songs[row]
        self._editing_id = self._song_sel.id
        self.song_title.setText(self._song_sel.title)
        self.song_artist.setText(self._song_sel.artist)
        self._editor_slides = list(self._song_sel.slides)
        self.song_lyrics.setPlainText("\n\n".join("\n".join(s.lines) for s in self._editor_slides))
        self._show_slide_list(self._editor_slides, self.slide_pick)
        self._show_slide_list(self._editor_slides, self.slide_now_list)
        self.song_now.setText(f"{self._song_sel.title}" + (f"  \u00b7  {self._song_sel.artist}" if self._song_sel.artist else ""))

    def _show_slide_list(self, slides: list[Slide], widget: QListWidget) -> None:
        widget.blockSignals(True)
        widget.clear()
        for i, s in enumerate(slides):
            widget.addItem(f"{s.label}: {s.lines[0] if s.lines else ''}")
        if slides:
            widget.setCurrentRow(0)
        widget.blockSignals(False)

    def _new_song(self) -> None:
        self._song_sel = None
        self._editing_id = ""
        self.song_title.clear()
        self.song_artist.clear()
        self.song_lyrics.clear()
        self._editor_slides = []
        self.slide_pick.clear()
        self.song_list.clearSelection()
        self.editor_status.setText("New song. Paste lyrics, then Split into slides.")

    def _import_song(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import lyrics", "", "Text or song JSON (*.txt *.json)")
        if not path:
            return
        try:
            from pathlib import Path as _P
            raw = _P(path).read_text(encoding="utf-8")
            if path.lower().endswith(".json"):
                import json as _json
                song = Song.from_dict(_json.loads(raw))
                self.song_title.setText(song.title)
                self.song_artist.setText(song.artist)
                self._editor_slides = song.slides
                self._editing_id = song.id
                self.song_lyrics.setPlainText("\n\n".join("\n".join(s.lines) for s in song.slides))
                self._show_slide_list(self._editor_slides, self.slide_pick)
                self.editor_status.setText(f"Imported {song.title}: {len(song.slides)} slides. Save to keep it.")
            else:
                self.song_lyrics.setPlainText(raw)
                self.song_title.setText(self.song_title.text() or _P(path).stem)
                self._split_editor()
        except Exception as exc:
            self.editor_status.setText(f"Import failed: {exc}")

    def _split_editor(self) -> None:
        text = self.song_lyrics.toPlainText()
        self._editor_slides = split_lyrics(text, max_lines=self.max_lines.value())
        self._show_slide_list(self._editor_slides, self.slide_pick)
        self.editor_status.setText(f"{len(self._editor_slides)} slides. Check them, then Save song.")

    def _save_song(self) -> None:
        if not self._editor_slides:
            self._split_editor()
        title = self.song_title.text().strip()
        if not title:
            self.editor_status.setText("Give the song a title first.")
            return
        try:
            song = Song(title=title, artist=self.song_artist.text().strip(),
                        slides=list(self._editor_slides), id=self._editing_id)
            if not song.slides:
                self.editor_status.setText("No lyrics to save. Paste lyrics and split them.")
                return
            path = self.library.save(song)
        except Exception as exc:
            self.editor_status.setText(f"Save failed: {exc}")
            return
        self._editing_id = song.id
        self.editor_status.setText(f"Saved {song.title} to {path.name}")
        self.song_search.clear()
        self._fill_song_list()

    def _on_slide_pick(self, row: int) -> None:
        if row >= 0:
            self.slide_now_list.setCurrentRow(row)

    def _current_song_and_slide(self) -> tuple[Optional[Song], int]:
        song = self._song_sel
        row = self.slide_now_list.currentRow()
        return song, row

    def _send_slide(self) -> None:
        """Send selected slide: direct projects now, otherwise it waits for approval (Enter)."""
        song, row = self._current_song_and_slide()
        if song is None or not song.slides or row < 0:
            self.song_pending_label.setText("Pick a song and a slide first.")
            return
        if self.song_direct.isChecked():
            self._project_song(song, row)
            return
        self._song_pending = (song, row)
        self.song_pending_label.setText(f"Waiting: {song.title}, {song.slides[row].label}. Approve to project.")

    def _project_song(self, song: Song, row: int) -> None:
        self._song_live = (song, row)
        self._kind = "song"
        self._song_pending = None
        self._sermon_live = None
        self.song_pending_label.setText("")
        self.song_now.setText(f"Projected: {song.title}  \u00b7  {song.slides[row].label}")
        if self.output.on and not self.queue.blank:
            self.projection.show_song_slide(song.slides[row])
        self.slide_now_list.setCurrentRow(row)
        self.refresh()

    def approve_pending_song(self) -> None:
        if self._song_pending is None:
            return
        song, row = self._song_pending
        self._project_song(song, row)

    def reject_pending_song(self) -> None:
        self._song_pending = None
        self.song_pending_label.setText("Slide rejected.")

    def step_song(self, delta: int) -> None:
        """Next/previous slide of the projected song (same song only). Keyboard: arrows, Space."""
        if self._song_live is None:
            return
        song, i = self._song_live
        j = i + delta
        if 0 <= j < len(song.slides):
            self._project_song(song, j)

    # --- sermon info -----------------------------------------------------------------------
    def _current_reference(self) -> str:
        live = self.queue.live
        if live is None or self.queue.blank:
            return ""
        return f"{live.reference} ({live.translation})"

    def show_sermon_slide(self) -> None:
        info = SermonInfo(title=self.sermon_title.text().strip(),
                          speaker=self.sermon_speaker.text().strip(),
                          reference=self._current_reference())
        if not info.lines():
            self.sermon_note.setText("Type a sermon title first.")
            return
        self._sermon_live = info
        self._kind = "sermon"
        self._song_pending = None
        if self.output.on and not self.queue.blank:
            self.projection.show_sermon(info)
        self.sermon_note.setText("Sermon info on screen." if not info.reference else
                                 f"Sermon info on screen. Reference: {info.reference}")

    def clear_sermon_slide(self) -> None:
        self._sermon_live = None
        if self._kind == "sermon":
            self._kind = "verse" if self.queue.live else None
            self._render_output()
        self.sermon_note.setText("Sermon slide cleared.")

    # --- verse navigation (next/prev in the same chapter) ----------------------------------
    def _live_verse(self):
        return self.queue.live

    def step(self, delta: int) -> None:
        """Songs tab: previous/next slide. Live tab: previous/next verse in the same chapter."""
        if self._tabs.currentIndex() == 1:
            self.step_song(delta)
            return
        live = self.queue.live
        if live is None or self.queue.blank or self._store is None:
            return
        from .navigation import candidate_from_suggestion, step_verse
        s = step_verse(self._store, live.book_id, live.chapter, live.verse, delta)
        if s is None:
            return
        c = candidate_from_suggestion(self._store, s, "navigation", 100, "projected from navigation")
        self._add_and_project(c)

    def _add_and_project(self, c: Candidate) -> None:
        """Queue (so the log records it) and immediately project a navigated/manual/search verse."""
        added = self.queue.add([c], force=True)
        target = added[0] if added else c
        self.queue.approve(target.id)
        self._show_on_output(target)
        self.refresh()

    # --- search with autosuggest -------------------------------------------------------------
    def focus_search(self) -> None:
        self.search.setFocus()
        self.search.selectAll()

    def _on_search_text(self, text: str) -> None:
        if self._store is None:
            return
        from .navigation import suggest
        items = suggest(text, self._store)
        self.search_list.clear()
        if not items or not text.strip():
            self.search_list.hide()
            return
        for s in items:
            it = QListWidgetItem(s.label)
            it.setData(Qt.ItemDataRole.UserRole, s)
            self.search_list.addItem(it)
        self.search_list.setCurrentRow(0)
        self.search_list.show()

    def _on_search_enter(self) -> None:
        if self._store is None:
            return
        from .navigation import candidate_from_suggestion, resolve, suggest
        row = self.search_list.currentRow()
        if self.search_list.isVisible() and row >= 0:
            s = self.search_list.item(row).data(Qt.ItemDataRole.UserRole)
            if s.kind == "verse":
                self._project_suggestion(s)
                return
            self.search.setText(s.completion)
            return
        s = resolve(self.search.text(), self._store)
        if s is not None:
            self._project_suggestion(s)

    def _on_suggestion_activated(self, item: QListWidgetItem) -> None:
        s = item.data(Qt.ItemDataRole.UserRole)
        if s.kind == "verse":
            self._project_suggestion(s)
        else:
            self.search.setText(s.completion)

    def _project_suggestion(self, s) -> None:
        from .navigation import candidate_from_suggestion
        c = candidate_from_suggestion(self._store, s, "manual", 100, "search")
        self.search.clear()
        self.search_list.hide()
        self._add_and_project(c)

    _SEARCH_KEYS = (Qt.Key.Key_Down, Qt.Key.Key_Up, Qt.Key.Key_Escape, Qt.Key.Key_Space,
                    Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Return, Qt.Key.Key_Enter,
                    Qt.Key.Key_B, Qt.Key.Key_H, Qt.Key.Key_E)

    def eventFilter(self, obj, event):
        """While the search box has focus it owns the keys it uses. Window shortcuts (B, H, arrows,
        Space) would otherwise fire and swallow them. Keys are claimed via ShortcutOverride."""
        from PyQt6.QtCore import QEvent
        if obj is self.search and event.type() in (QEvent.Type.ShortcutOverride, QEvent.Type.KeyPress):
            key = event.key()
            if key in self._SEARCH_KEYS:
                if event.type() == QEvent.Type.ShortcutOverride:
                    event.accept()
                    return True
                return self._search_key(key)
        return super().eventFilter(obj, event)

    def _search_key(self, key) -> bool:
        if key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
            if self.search_list.isVisible():
                step = 1 if key == Qt.Key.Key_Down else -1
                row = max(0, min(self.search_list.count() - 1, self.search_list.currentRow() + step))
                self.search_list.setCurrentRow(row)
            return True
        if key == Qt.Key.Key_Escape:
            self.search.clear()
            self.search_list.hide()
            return True
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._on_search_enter()
            return True
        return False  # letters/space/arrows keep editing the text

    # --- manual verse mode -----------------------------------------------------------------
    def _on_manual_toggle(self, on: bool) -> None:
        self._manual_on = on
        self.manual_box.setVisible(on)
        self.btn_manual.setText("Manual verse mode \u25be" if on else "Manual verse mode \u25b8")
        if on:
            self._fill_books()

    def _fill_testaments(self) -> None:
        from .navigation import manual_testaments
        self.man_testament.blockSignals(True)
        self.man_testament.clear()
        self.man_testament.addItems(manual_testaments())
        self.man_testament.blockSignals(False)
        self._fill_books()

    def _fill_books(self) -> None:
        from .navigation import manual_books
        self.man_book.blockSignals(True)
        self.man_book.clear()
        self._man_books = manual_books(self.man_testament.currentText() or "Old Testament")
        for bid, name in self._man_books:
            self.man_book.addItem(name, bid)
        self.man_book.blockSignals(False)
        self._fill_chapters()

    def _fill_chapters(self) -> None:
        if self._store is None:
            return
        from .navigation import manual_chapters
        self.man_chapter.blockSignals(True)
        self.man_chapter.clear()
        bid = self.man_book.currentData()
        if bid is not None:
            for ch in manual_chapters(self._store, bid):
                self.man_chapter.addItem(str(ch), ch)
        self.man_chapter.blockSignals(False)
        self._fill_verses()

    def _fill_verses(self) -> None:
        if self._store is None:
            return
        from .navigation import manual_verses
        self.man_verse.blockSignals(True)
        self.man_verse.clear()
        bid, ch = self.man_book.currentData(), self.man_chapter.currentData()
        if bid is not None and ch is not None:
            for v in manual_verses(self._store, bid, ch):
                self.man_verse.addItem(str(v), v)
        self.man_verse.blockSignals(False)

    def _project_manual(self) -> None:
        if self._store is None:
            return
        from .navigation import _verse_sugg, candidate_from_suggestion
        bid, ch, v = self.man_book.currentData(), self.man_chapter.currentData(), self.man_verse.currentData()
        if None in (bid, ch, v):
            return
        c = candidate_from_suggestion(self._store, _verse_sugg(self._store, bid, ch, v), "manual", 100, "manual pick")
        self._add_and_project(c)

    # --- rendering ------------------------------------------------------------------------
    def _show_selected(self) -> None:
        c = self.queue.selected_item()
        if c is None:
            self.preview.setText("")
            self.cards_hint.setText("No verse waiting. Detections appear here; search or manual mode projects directly.")
            return
        self.preview.setText(f"\u201c{c.display_text}\u201d")
        self.cards_hint.setText(f"{c.reference}  \u00b7  {c.confidence}% {c.match_type}  \u00b7  Heard: \u201c{c.snippet}\u201d")

    def _refresh_transcript(self) -> None:
        if self.pipeline is None:
            return
        while self.transcript_box.count():
            w = self.transcript_box.takeAt(0).widget()
            if w is not None:
                w.deleteLater()
        hits = 0
        for ts, text, refs in list(self.pipeline.history)[-40:]:
            row = QFrame()
            row.setStyleSheet("background:transparent;")
            hl = QVBoxLayout(row)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.setSpacing(2)
            hl.addWidget(_label(time.strftime("%H:%M:%S", time.localtime(ts)), "time"))
            line = _label(text, "transcript", wrap=True)
            hl.addWidget(line)
            for ref, conf in refs:
                hits += 1
                hl.addWidget(_label(f"{ref}  {conf}%", "badgeGreen"))
            self.transcript_box.addWidget(row)
        self.transcript_box.addStretch(1)
        self.transcript_badge.setText(f"{hits} detected")
        self._transcript_scroll.verticalScrollBar().setValue(
            self._transcript_scroll.verticalScrollBar().maximum())

    def refresh(self) -> None:
        pending = self.queue.pending()
        self.list.blockSignals(True)
        self.list.clear()
        for c in pending:
            item = QListWidgetItem(f"{c.reference}   {c.confidence}%  {c.match_type}")
            self.list.addItem(item)
        if pending:
            self.list.setCurrentRow(min(max(self.queue.selected, 0), len(pending) - 1))
        self.list.blockSignals(False)
        # gold outline on the first card = next to project
        for i in range(self.list.count()):   # first card = next to project: gold text, tinted row
            it = self.list.item(i)
            if i == 0:
                it.setForeground(QColor("#facc15"))
                it.setBackground(QColor("#1b2231"))
            else:
                it.setForeground(QColor("#e5e7eb"))
                it.setBackground(QColor("#0f1522"))
        self.queue_badge.setText(f"{len(pending)} pending")
        self._show_selected()
        self._refresh_transcript()

        live = self.queue.live
        st = self.queue.state
        # The pill shows the output switch (ON/OFF), not the queue state; blank/idle shows in the status bar.
        self.live_pill.setVisible(True)
        if live is not None:
            self.slide_text.setText(live.display_text if not self.queue.blank else "")
            self.slide_ref.setText(live.reference)
        else:
            self.slide_text.setText("")
            self.slide_ref.setText("")
        self.footer_proj.setText({"live": "Projecting", "blank": "Blanked", "idle": "Idle"}[st])
        self.footer_proj.setObjectName("footerOk" if st == "live" else "footer")
        self.footer_proj.style().unpolish(self.footer_proj)
        self.footer_proj.style().polish(self.footer_proj)
        self.btn_prev.setEnabled(live is not None and self._has_neighbour(-1))
        self.btn_next.setEnabled(live is not None and self._has_neighbour(+1))
        if live is not None and self._store is not None:
            nxt = self._neighbour_text(+1)
            self.next_label.setText(f"Next in chapter: {nxt}" if nxt else "Last verse of this chapter")
        else:
            self.next_label.setText("")

        cleared = self.queue.cleared_count()
        self.cleared_label.setText(f"Queue cleared {cleared} this session")
        self.status_cleared.setText(f"Queue cleared {cleared}")
        if self.pipeline is not None:
            ms = self.pipeline.last_latency_ms
            self.latency_label.setText(f"Latency {ms / 1000:.1f}s")
            self.status_latency.setText(f"Latency {ms / 1000:.1f}s")
        self.timer_label.setText(time.strftime("%H:%M:%S", time.gmtime(time.time() - self._started)))
        if self.live is not None:
            m = self.live.meter()
            self.meter.setText(f"Peak {m['peak_db']:.0f} dB   RMS {m['rms_db']:.0f} dB")
        elif self._audio_meter:
            m = self._audio_meter()
            self.meter.setText(f"Peak {m['peak_db']:.0f} dB   RMS {m['rms_db']:.0f} dB")

    def _has_neighbour(self, delta: int) -> bool:
        live = self.queue.live
        if live is None or self._store is None:
            return False
        return self._store.neighbour(live.book_id, live.chapter, live.verse, delta) is not None

    def _neighbour_text(self, delta: int) -> str:
        live = self.queue.live
        n = self._store.neighbour(live.book_id, live.chapter, live.verse, delta)
        return f"{live.book_name} {live.chapter}:{n}" if n is not None else ""


def run_app(queue: ApprovalQueue, theme: Theme, pipeline=None, projection_screen: int = 0,
            live=None, songs_dir: str = "data/songs"):
    """Start the Qt event loop. pipeline receives dev-feed text; live (optional) runs the mic loop.

    projection_screen picks the starting monitor for the live output (the display box can change it).
    """
    app = QApplication.instance() or QApplication([])
    projection = ProjectionWindow()
    projection.show_theme(theme)
    op = OperatorWindow(queue, theme, projection, pipeline=pipeline, live=live, songs_dir=songs_dir)
    op.display_box.setCurrentIndex(projection_screen)
    op.resize(1280, 800)
    op.show()
    if op.output.on:
        projection.present()
    return app.exec()
