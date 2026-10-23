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
                             QInputDialog,
                             QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                             QListWidgetItem, QMainWindow, QPlainTextEdit, QPushButton, QScrollArea,
                             QSpinBox, QTabWidget, QVBoxLayout, QWidget, QMessageBox)

from .approval import ApprovalQueue
from .detection import Candidate
from .displays import DisplayInfo, list_displays
from .output_state import LiveOutputState, pill_state
from .settings_page import SettingsPage
from .store import APP_VERSION, AppSettings, save_settings
from .sermon import SermonInfo
from .songs import Slide, Song, SongLibrary, lyrics_text, split_lyrics
from .sermon_presets import SermonPreset, SermonPresetLibrary
from .theme import Theme
from .outputs import (PROJECTION_WINDOW_TITLE, paint_background, paint_song, paint_sermon,
                      paint_verse)

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
    """Borderless live output. Standalone: fullscreen on a chosen display, no OBS needed.

    Hiding it (live output OFF) lets another app take the projector. Any capture tool
    (OBS window capture, virtual camera, other studio software) can read this window.
    Everything is painted by outputs.py (mockups A and B: gold chips, footer, sermon slide).
    """

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setWindowTitle(PROJECTION_WINDOW_TITLE)
        self._theme = Theme()
        self._image_cache: dict = {}
        self._frame = None          # callable(painter, rect) set by show_* methods
        self.setMinimumSize(320, 180)
        self.show_theme(Theme())
        self.show_blank()

    def show_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.update()

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
        if c is None:
            self._frame = None
        else:
            self._frame = lambda p, r: paint_verse(p, r, self._theme, c)
        self.update()

    def show_song_slide(self, slide: Slide | None, song=None, index: int = 0, total: int = 0) -> None:
        if slide is None:
            self._frame = None
        else:
            title = getattr(song, "title", "")
            artist = getattr(song, "artist", "")
            self._frame = lambda p, r: paint_song(
                p, r, self._theme, title=title, artist=artist, section=slide.label,
                index=index, total=total, lines=list(slide.lines), image_cache=self._image_cache)
        self.update()

    def show_sermon(self, info: SermonInfo | None, church: str = "") -> None:
        if info is None or not info.lines() and not church:
            self._frame = None
        else:
            line = church or info.church or self._theme.church_line
            self._frame = lambda p, r: paint_sermon(
                p, r, self._theme, church=line, title=info.title,
                speaker=info.speaker, reference=info.reference, image_cache=self._image_cache)
        self.update()

    def show_blank(self) -> None:
        self._frame = None
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        from PyQt6.QtGui import QPainter
        painter = QPainter(self)
        try:
            rect = self.rect()
            if self._frame is None:
                paint_background(painter, rect, self._theme, self._image_cache)
            else:
                self._frame(painter, rect)
        finally:
            painter.end()


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
QPushButton#live { background: #14532d; color: #4ade80; border: 1px solid #22c55e; border-radius: 12px; padding: 3px 12px; font-weight: 800; }
QPushButton#live[on="false"] { background: #3a1418; color: #f87171; border: 1px solid #b42f3d; }
QTabWidget::pane { border: none; }
QTabBar::tab { background: #1d2535; color: #94a3b8; padding: 6px 14px; border-top-left-radius: 8px; border-top-right-radius: 8px; }
QTabBar::tab:selected { background: #facc15; color: #0b0f19; font-weight: 800; }
QLabel#liveNote { color: #f59e0b; font-size: 11px; }
QPushButton#ghost { background: transparent; border: 1px solid #2f3a52; color: #cbd5e1; }
QPushButton#primary { background: #facc15; color: #0b0f19; border: 1px solid #facc15; font-weight: 800; padding: 8px 14px; }
QPushButton#primary:hover { background: #fde047; }
QPushButton#subtle { background: #161d2c; color: #cbd5e1; border: 1px solid #2f3a52; }
QPushButton#subtle:disabled { color: #475569; border-color: #232d40; }
QPushButton#danger { background: transparent; color: #8a4a55; border: 1px solid #3a2228; font-weight: 600; }
QPushButton#danger:disabled { color: #3f2a31; border-color: #251a1e; }
QPushButton#small { padding: 3px 10px; font-size: 12px; }
QLabel#emptyIcon { color: #8a7224; font-size: 46px; }
QLabel#emptyHint { color: #94a3b8; font-size: 13px; }
QLabel#emptyIconBook { color: #5b6478; font-size: 40px; }
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
                 audio_meter=None, pipeline=None, live=None, songs_dir: str = "data/songs",
                 settings: Optional[AppSettings] = None, settings_path: Optional[str] = None,
                 dev: bool = False, sermons_dir: str = "data/sermons"):
        super().__init__()
        self.settings = settings or AppSettings()
        self._settings_path = settings_path
        self._dev = bool(dev)
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
        self.output = LiveOutputState(on=self.settings.startup_live_on)  # LIVE pill: shown or hidden
        self._kind: Optional[str] = None           # what the output shows: verse | song | sermon
        self._song_live: Optional[tuple[Song, int]] = None
        self._song_pending: Optional[tuple[Song, int]] = None
        self._sermon_live: Optional[SermonInfo] = None
        self._song_sel: Optional[Song] = None
        self._editing_id: str = ""
        self._saved_snapshot = None          # editor contents as last loaded/saved (None before build)
        self._loading_editor = False         # True while the editor is filled programmatically
        self._songs_page: Optional[QWidget] = None
        self.library = SongLibrary(songs_dir)
        self.sermon_presets = SermonPresetLibrary(sermons_dir)
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
        media_placeholder = QLabel("Media is coming soon.")
        media_placeholder.setObjectName("sub")
        self._tabs.addTab(media_placeholder, "Media")
        self._tabs.setTabEnabled(self._tabs.count() - 1, False)
        self._tabs.setTabToolTip(self._tabs.count() - 1, "soon")
        self.settings_page = SettingsPage(self.settings, check_updates_cb=self._check_updates)
        self.settings_page.changed.connect(self._on_setting_changed)
        self._tabs.addTab(self.settings_page, "Settings")
        self._settings_index = self._tabs.count() - 1
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
        self.btn_save_as_new.clicked.connect(self._save_as_new)
        self.btn_delete_song.clicked.connect(self._delete_song)
        self.btn_preset_save.clicked.connect(self.save_sermon_preset)
        self.btn_preset_delete.clicked.connect(self.delete_sermon_preset)
        self.sermon_preset_pick.currentIndexChanged.connect(self._on_preset_pick)

        self._timer = QTimer(self, interval=150, timeout=self.refresh)
        self._timer.start()
        self._fill_testaments()
        self._populate_displays()
        self._fill_song_list()
        self._new_song()
        self._fill_presets()
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
        self.btn_source_dev.setVisible(self._dev)     # Dev feed only with --dev
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
        self.feed.setVisible(self._dev)               # dev text box only with --dev
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
        self.source_box.setCurrentIndex(1)           # default source: live microphone
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
        self._songs_page = page
        root = QHBoxLayout(page)
        root.setContentsMargins(14, 12, 14, 10)
        root.setSpacing(12)

        # library
        left, ll = self._panel("Song Library", "")
        self.song_badge = _label("0 songs", "badge")
        ll.itemAt(0).layout().insertWidget(1, self.song_badge)
        self.song_hint = _label("", "sub", wrap=True)
        ll.addWidget(self.song_hint)
        self.song_empty = self._empty_state("\u266a", "No songs yet \u2014 click New song to add your first", "emptyIcon")
        ll.addWidget(self.song_empty, 1)
        self.song_search = QLineEdit()
        self.song_search.setPlaceholderText("Search songs...")
        ll.addWidget(self.song_search)
        self.song_list = QListWidget()
        ll.addWidget(self.song_list, 1)
        row = QHBoxLayout()
        self.btn_new_song = QPushButton("New song")
        self.btn_new_song.setObjectName("primary")
        self.btn_import_song = QPushButton("Import file")
        row.addWidget(self.btn_new_song)
        row.addWidget(self.btn_import_song)
        ll.addLayout(row)
        self.song_count = _label("", "footer")
        ll.addWidget(self.song_count)
        root.addWidget(left, 3)

        # editor
        mid, ml = self._panel("Edit Song", "")
        self.btn_new_small = QPushButton("New")
        self.btn_new_small.setObjectName("small")
        self.btn_new_small.clicked.connect(self._new_song)
        ml.itemAt(0).layout().addWidget(self.btn_new_small)
        self.song_title = QLineEdit()
        self.song_title.setPlaceholderText("Title")
        self.song_artist = QLineEdit()
        self.song_artist.setPlaceholderText("Artist")
        ml.addWidget(self.song_title)
        ml.addWidget(self.song_artist)
        self.song_lyrics = QPlainTextEdit()
        self.song_lyrics.setPlaceholderText("Paste lyrics here...")
        ml.addWidget(self.song_lyrics, 1)
        ml.addWidget(_label("A blank line starts a new slide. Headers such as [Verse 1] or Chorus: start a labelled slide.",
                            "sub", wrap=True))
        self.song_title.textChanged.connect(self._update_dirty)
        self.song_artist.textChanged.connect(self._update_dirty)
        self.song_lyrics.textChanged.connect(self._update_dirty)
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
        save_row = QHBoxLayout()
        self.btn_save_song = QPushButton("Save song")
        self.btn_save_song.setObjectName("subtle")
        self.btn_save_as_new = QPushButton("Save as new")
        self.btn_save_as_new.setObjectName("subtle")
        self.btn_delete_song = QPushButton("Delete song")
        self.btn_delete_song.setObjectName("danger")
        save_row.addWidget(self.btn_save_song, 2)
        save_row.addWidget(self.btn_save_as_new, 1)
        save_row.addWidget(self.btn_delete_song, 1)
        ml.addLayout(save_row)
        self.song_dirty = _label("", "footerOk")
        ml.addWidget(self.song_dirty)
        self.editor_status = _label("", "footer", wrap=True)
        ml.addWidget(self.editor_status)
        self.editor_footer = _label("Nothing selected", "footer")
        ml.addWidget(self.editor_footer)
        self._editor_slides: list[Slide] = []
        root.addWidget(mid, 3)

        # live: slide navigation, approval, sermon info
        right, rl = self._panel("Song Projection", "")
        self.song_now = _label("Pick a song in the library, then choose a slide.", "verse", wrap=True)
        rl.addWidget(self.song_now)
        slides_head = QHBoxLayout()
        slides_head.addWidget(_label("Slides", "panelTitle"))
        slides_head.addStretch(1)
        self.slide_badge = _label("0 slides", "badge")
        slides_head.addWidget(self.slide_badge)
        rl.addLayout(slides_head)
        self.slides_empty = self._empty_state("\U0001F4D6", "Split a song into slides to see them here", "emptyIconBook")
        rl.addWidget(self.slides_empty)
        self.slide_now_list = QListWidget()
        self.slide_now_list.setMaximumHeight(160)
        rl.addWidget(self.slide_now_list)
        self.slides_footer = _label("No slides", "footer")
        rl.addWidget(self.slides_footer)
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
        self.sermon_church = QLineEdit()
        self.sermon_church.setPlaceholderText("Church line (optional, blank uses the theme's)")
        rl.addWidget(self.sermon_title)
        rl.addWidget(self.sermon_speaker)
        rl.addWidget(self.sermon_church)
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

        # sermon presets (data/sermons, one JSON per preset)
        rl.addWidget(_label("Sermon presets", "panelTitle"))
        self.sermon_preset_pick = QComboBox()
        rl.addWidget(self.sermon_preset_pick)
        prow = QHBoxLayout()
        self.btn_preset_save = QPushButton("Save as preset")
        self.btn_preset_save.setObjectName("approve")
        self.btn_preset_delete = QPushButton("Delete preset")
        self.btn_preset_delete.setObjectName("reject")
        prow.addWidget(self.btn_preset_save, 1)
        prow.addWidget(self.btn_preset_delete)
        rl.addLayout(prow)
        self.preset_note = _label("Pick a saved sermon to fill the fields, edit them, then Save as preset "
                                  "(same name overwrites).", "sub", wrap=True)
        rl.addWidget(self.preset_note)
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
            self.btn_source_mic.setEnabled(False)
            self.source_status.setText("Live audio not available in this session.")
            if self._dev:
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
            self.live.start_mic(dev, gate_db=self.settings.noise_gate_db)
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
            self.projection.show_song_slide(song.slides[i], song, i, len(song.slides))
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

    # --- settings, menus, and persistence ----------------------------------------------------
    def _apply_settings_to_widgets(self) -> None:
        """Push the loaded settings into the live app once, at startup."""
        self.queue.set_dedupe_seconds(self.settings.dedupe_minutes * 60.0)
        self.queue.set_auto_approve(self.settings.auto_approve)
        if self.pipeline is not None and hasattr(self.pipeline, "detector"):
            self.pipeline.detector.paraphrase_threshold = self.settings.paraphrase_threshold
        self._apply_auto_label()
        self._apply_output_state()

    def _apply_auto_label(self) -> None:
        on = self.settings.auto_approve
        text = "Auto-approve: ON (no operator approval)" if on else "Auto-approve: off"
        self.status_auto.setText(text)
        self.auto_label.setText(text)

    def _on_setting_changed(self, key: str) -> None:
        """Apply one changed setting to the running app, then save the file."""
        s = self.settings
        if key == "paraphrase_threshold" and self.pipeline is not None and hasattr(self.pipeline, "detector"):
            self.pipeline.detector.paraphrase_threshold = s.paraphrase_threshold
        elif key == "dedupe_minutes":
            self.queue.set_dedupe_seconds(s.dedupe_minutes * 60.0)
        elif key == "auto_approve":
            self.queue.set_auto_approve(s.auto_approve)
            self._apply_auto_label()
        elif key == "output_display" and hasattr(self, "display_box") and self.display_box.count() > s.output_display:
            self.display_box.setCurrentIndex(s.output_display)
        elif key == "noise_gate_db" and self.live is not None and getattr(self.live, "capture", None) is not None:
            self.live.capture.set_gate_threshold(s.noise_gate_db)
        elif key == "input_device_name":
            self._select_device_by_name(s.input_device_name)
        self._save_settings()

    def _select_device_by_name(self, name: str) -> None:
        for i, d in enumerate(self._devices):
            if d.name == name:
                self.device_box.setCurrentIndex(i)
                return

    def _save_settings(self) -> None:
        if self._settings_path:
            try:
                save_settings(self._settings_path, self.settings)
            except OSError as exc:
                self.source_status.setText(f"Could not save settings: {exc}")

    def _check_updates(self) -> str:
        return ("Couldn't reach the update server. Check your internet connection and try again. "
                f"You are on {APP_VERSION}.")

    def _build_menus(self) -> None:
        bar = self.menuBar()
        f = bar.addMenu("File")
        f.addAction("Open song library folder", self._open_song_folder)
        f.addSeparator()
        f.addAction("Exit", self.close)
        o = bar.addMenu("Output")
        o.addAction("Toggle live output (O)", self.toggle_output)
        o.addMenu("Choose display").aboutToShow.connect(self._fill_display_menu)
        o.addAction("Display settings...", self._open_settings_output)
        h = bar.addMenu("Help")
        h.addAction("Setup docs (see README.md in the project folder)", self._show_setup_docs)
        h.addAction("About RevelateTW", self._show_about)

    def _open_song_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Song library folder", str(self.library.root))
        if path:
            self.library.root = type(self.library.root)(path)
            self._fill_song_list()

    def _fill_display_menu(self) -> None:
        menu = self.sender()
        if menu is None:
            return
        menu.clear()
        for i, d in enumerate(getattr(self, "_displays", None) or []):
            act = menu.addAction(f"{i}: {d.name} ({d.width}x{d.height})",
                                 lambda idx=i: self.display_box.setCurrentIndex(idx))
            act.setCheckable(True)
            act.setChecked(i == self.display_box.currentIndex())

    def _open_settings_output(self) -> None:
        self._tabs.setCurrentIndex(self._settings_index)
        self.settings_page.select_section("Output")

    def _show_setup_docs(self) -> None:
        QMessageBox.information(self, "Setup docs",
                                "The setup guide is the README.md in the RevelateTW project folder.")

    def _show_about(self) -> None:
        QMessageBox.about(self, "About RevelateTW", f"RevelateTW version {APP_VERSION}.")

    # --- live output ON/OFF (LIVE pill, key O) --------------------------------------------
    def toggle_output(self) -> None:
        self.output.toggle()
        self._apply_output_state()
        self.refresh()

    def _apply_output_state(self) -> None:
        on = self.output.on
        st = pill_state(on)
        self.live_pill.setText(st["text"])
        self.live_pill.setProperty("on", st["on"])
        self.live_pill.style().unpolish(self.live_pill)
        self.live_pill.style().polish(self.live_pill)
        self.live_pill.setToolTip(st["tooltip"])
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
    def _empty_state(self, icon: str, hint: str, icon_obj: str) -> QFrame:
        f = QFrame()
        v = QVBoxLayout(f)
        v.setContentsMargins(8, 18, 8, 18)
        v.setSpacing(6)
        ic = _label(icon, icon_obj)
        ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h = _label(hint, "emptyHint", wrap=True)
        h.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addStretch(1)
        v.addWidget(ic)
        v.addWidget(h)
        v.addStretch(1)
        f.icon = ic
        f.hint = h
        return f

    def _refresh_song_chrome(self) -> None:
        """Badges, empty states, button enablement and footers for the songs tab."""
        if not hasattr(self, "slides_empty") or not hasattr(self, "btn_save_song"):
            return
        total = getattr(self, "_library_total", 0)
        has_song = getattr(self, "_song_sel", None) is not None
        has_text = bool(self.song_title.text().strip() or self.song_lyrics.toPlainText().strip())
        active = has_song or has_text
        self.btn_save_song.setEnabled(active)
        self.btn_save_as_new.setEnabled(active)
        self.btn_delete_song.setEnabled(has_song)
        dirty = self._editor_dirty()
        if dirty:
            self.editor_footer.setText("Unsaved changes")
        elif has_song:
            self.editor_footer.setText("Saved as JSON")
        elif has_text:
            self.editor_footer.setText("New song, not saved yet")
        else:
            self.editor_footer.setText("Nothing selected")
        n = self.slide_now_list.count()
        self.slide_badge.setText(f"{n} slide" + ("" if n == 1 else "s"))
        self.slides_empty.setVisible(n == 0)
        self.slide_now_list.setVisible(n > 0)
        self.slides_footer.setText("No slides" if n == 0 else f"{n} slide" + ("" if n == 1 else "s") + " ready")

    def _fill_song_list(self) -> None:
        self._songs = self.library.search(self.song_search.text())
        self.song_list.blockSignals(True)
        self.song_list.clear()
        for s in self._songs:
            label = s.title + (f"  \u00b7  {s.artist}" if s.artist else "")
            self.song_list.addItem(f"{label}  ({len(s.slides)} slides)")
        self.song_list.blockSignals(False)
        self._select_loaded_row()
        total = len(self.library.load_all())
        self._library_total = total
        self.song_badge.setText(f"{total} song" + ("" if total == 1 else "s"))
        self.song_empty.setVisible(total == 0)
        self.song_list.setVisible(total > 0)
        self.song_hint.setVisible(total > 0)
        if total == 0:
            self.song_count.setText("Library empty")
            self.song_hint.setText("")
        else:
            self.song_count.setText(f"Saved as JSON  \u00b7  {len(self._songs)} shown  \u00b7  {total} in library")
            if self._song_sel is None:
                self.song_hint.setText("Pick a song to edit it, or click New song to add one.")
            else:
                self.song_hint.setText("Edit below, then Save song. Save as new keeps the original.")
        self._refresh_song_chrome()

    def _editor_snapshot(self) -> tuple:
        return (self.song_title.text().strip(), self.song_artist.text().strip(),
                self.song_lyrics.toPlainText(),
                tuple((s.label, tuple(s.lines)) for s in self._editor_slides))

    def _editor_dirty(self) -> bool:
        return self._saved_snapshot is not None and self._editor_snapshot() != self._saved_snapshot

    def _update_dirty(self, *_args) -> None:
        self._refresh_song_chrome()
        if self._loading_editor or self._saved_snapshot is None:
            return
        dirty = self._editor_dirty()
        self.song_dirty.setText("\u25cf Unsaved changes" if dirty else "")
        self.btn_save_song.setText("Save song *" if dirty else "Save song")
        if self._songs_page is not None:
            idx = self._tabs.indexOf(self._songs_page)
            if idx >= 0:
                self._tabs.setTabText(idx, "Songs & sermon \u25cf" if dirty else "Songs & sermon")

    # Confirmation prompts are isolated here so tests can stub them.
    def _ask_discard(self) -> bool:
        box = QMessageBox(self)
        box.setWindowTitle("Discard changes?")
        box.setIcon(QMessageBox.Icon.Question)
        box.setText("This song has unsaved changes. Discard them?")
        box.setInformativeText("Click Save song first if you want to keep them.")
        keep = box.addButton("Keep editing", QMessageBox.ButtonRole.RejectRole)
        drop = box.addButton("Discard changes", QMessageBox.ButtonRole.DestructiveRole)
        box.setDefaultButton(keep)
        box.exec()
        return box.clickedButton() is drop

    def _ask_yes_no(self, title: str, text: str) -> bool:
        answer = QMessageBox.question(self, title, text,
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                      QMessageBox.StandardButton.No)
        return answer == QMessageBox.StandardButton.Yes

    def _ask_text(self, title: str, label: str, default: str = "") -> str:
        text, ok = QInputDialog.getText(self, title, label, text=default)
        return text if ok else ""

    def _confirm_discard(self) -> bool:
        """True when it is safe to leave the editor (no unsaved edits, or the operator says discard)."""
        return (not self._editor_dirty()) or self._ask_discard()

    def _select_loaded_row(self) -> None:
        """Keep the library highlight on the song that is loaded in the editor."""
        self.song_list.blockSignals(True)
        row = next((i for i, s in enumerate(self._songs)
                    if self._song_sel is not None and s.id == self._song_sel.id), -1)
        if row >= 0:
            self.song_list.setCurrentRow(row)
        else:
            self.song_list.clearSelection()
        self.song_list.blockSignals(False)

    def _on_song_row(self, row: int) -> None:
        if row < 0 or row >= len(self._songs):
            return
        target = self._songs[row]
        if self._song_sel is not None and target.id == self._song_sel.id:
            return
        if not self._confirm_discard():
            self._select_loaded_row()
            return
        self._load_into_editor(target)
        self.editor_status.setText(f"Editing {target.title}. Change it, then Save song.")

    def _load_into_editor(self, song: Optional[Song]) -> None:
        """Fill the editor from a saved song (or clear it for None) and mark it clean."""
        self._loading_editor = True
        try:
            self._song_sel = song
            self._editing_id = song.id if song else ""
            self.song_title.setText(song.title if song else "")
            self.song_artist.setText(song.artist if song else "")
            self._editor_slides = [Slide(s.label, list(s.lines)) for s in song.slides] if song else []
            self.song_lyrics.setPlainText(lyrics_text(self._editor_slides) if song else "")
            self._show_slide_list(self._editor_slides, self.slide_pick)
            if song is not None:
                self._show_slide_list(self._editor_slides, self.slide_now_list)
            else:
                self.slide_pick.clear()
                self.slide_now_list.clear()
        finally:
            self._loading_editor = False
        self._saved_snapshot = self._editor_snapshot()
        self._update_dirty()

    def _show_slide_list(self, slides: list[Slide], widget: QListWidget) -> None:
        widget.blockSignals(True)
        widget.clear()
        for i, s in enumerate(slides):
            widget.addItem(f"{s.label}: {s.lines[0] if s.lines else ''}")
        if slides:
            widget.setCurrentRow(0)
        widget.blockSignals(False)
        if hasattr(self, "slides_empty"):
            self._refresh_song_chrome()

    def _new_song(self) -> None:
        if not self._confirm_discard():
            return
        self._load_into_editor(None)
        self._select_loaded_row()
        self.editor_status.setText("New song. Paste lyrics, then Split into slides and Save song.")
        self.song_title.setFocus()

    def _import_song(self) -> None:
        if not self._confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Import lyrics", "", "Text or song JSON (*.txt *.json)")
        if not path:
            return
        try:
            from pathlib import Path as _P
            raw = _P(path).read_text(encoding="utf-8")
            if path.lower().endswith(".json"):
                import json as _json
                song = Song.from_dict(_json.loads(raw))
                # an import is a new song until saved: it keeps its id so Save overwrites the same file
                self._load_into_editor(song)
                self._song_sel = None
                self._select_loaded_row()
                self._update_dirty()
                self.editor_status.setText(f"Imported {song.title}: {len(song.slides)} slides. Save song to keep it.")
            else:
                self._load_into_editor(None)
                self.song_lyrics.setPlainText(raw)
                self.song_title.setText(self.song_title.text() or _P(path).stem)
                self._split_editor()
        except Exception as exc:
            self.editor_status.setText(f"Import failed: {exc}")

    def _split_editor(self) -> None:
        text = self.song_lyrics.toPlainText()
        self._editor_slides = split_lyrics(text, max_lines=self.max_lines.value())
        self._show_slide_list(self._editor_slides, self.slide_pick)
        self._update_dirty()
        self.editor_status.setText(f"{len(self._editor_slides)} slides. Check them, then Save song.")

    def _sync_slides_with_text(self) -> None:
        """Lyrics edited since the last split are re-split before a save, so the saved slides match the text."""
        text = self.song_lyrics.toPlainText()
        if text.strip() and text != lyrics_text(self._editor_slides):
            self._split_editor()

    def _editor_song(self, song_id: str) -> Song:
        """A Song built from the editor fields (raises ValueError when it cannot be saved)."""
        title = self.song_title.text().strip()
        if not title:
            raise ValueError("Give the song a title first.")
        if not self._editor_slides:
            raise ValueError("No lyrics to save. Paste lyrics and split them.")
        return Song(title=title, artist=self.song_artist.text().strip(),
                    slides=[Slide(s.label, list(s.lines)) for s in self._editor_slides], id=song_id)

    def _write_song(self, song: Song) -> bool:
        try:
            path = self.library.save(song)
        except Exception as exc:
            self.editor_status.setText(f"Save failed: {exc}")
            return False
        self._refresh_projected_song(song)
        self._song_sel = song
        self._editing_id = song.id
        self._saved_snapshot = self._editor_snapshot()
        self._update_dirty()
        self.song_search.clear()              # triggers the list refresh
        self._fill_song_list()
        self.editor_status.setText(f"Saved {song.title} to {path.name}")
        return True

    def _save_song(self) -> None:
        """Save the editor. An existing song keeps its file (same id, same filename)."""
        self._sync_slides_with_text()
        try:
            song = self._editor_song(self._editing_id)
        except ValueError as exc:
            self.editor_status.setText(str(exc))
            return
        self._write_song(song)

    def _save_as_new(self) -> None:
        """Save the editor contents as a new song file. The original is not touched."""
        self._sync_slides_with_text()
        title = self.song_title.text().strip()
        if not title:
            self.editor_status.setText("Give the song a title first.")
            return
        new_title = self._ask_text("Save as new song", "Title for the new song:", f"{title} (copy)").strip()
        if not new_title:
            return
        try:
            song = self._editor_song("")
        except ValueError as exc:
            self.editor_status.setText(str(exc))
            return
        song.title = new_title
        if self._write_song(song):
            self._load_into_editor(song)
            self._select_loaded_row()
            self.editor_status.setText(f"Saved as new song {song.title}. The original is unchanged.")

    def _delete_song(self) -> None:
        song = self._song_sel
        if song is None or self.library.get(song.id) is None:
            self.editor_status.setText("Nothing saved to delete. Pick a song in the library first.")
            return
        text = f'Delete "{song.title}" from the library? Its file is removed and this cannot be undone.'
        if self._editor_dirty():
            text += " Your unsaved edits will be lost too."
        if not self._ask_yes_no("Delete song", text):
            return
        if not self.library.delete(song.id):
            self.editor_status.setText("Delete failed: the song file was not found.")
            return
        self._forget_song(song.id)
        self._load_into_editor(None)
        self.song_search.clear()
        self._fill_song_list()
        self.editor_status.setText(f"Deleted {song.title}.")

    def _refresh_projected_song(self, song: Song) -> None:
        """A saved edit or rename reaches the queue/preview: the projected or pending slide is
        re-pointed at the saved copy. The projector is only repainted if the song is on screen."""
        if self._song_live is not None and self._song_live[0].id == song.id:
            i = min(self._song_live[1], max(0, len(song.slides) - 1))
            self._song_live = (song, i)
            if self._kind == "song" and self.output.on and not self.queue.blank:
                self.projection.show_song_slide(song.slides[i], song, i, len(song.slides))
            self.song_now.setText(f"Projected: {song.title}  \u00b7  {song.slides[i].label}")
            self._show_slide_list(song.slides, self.slide_now_list)
            self.slide_now_list.setCurrentRow(i)
        if self._song_pending is not None and self._song_pending[0].id == song.id:
            i = min(self._song_pending[1], max(0, len(song.slides) - 1))
            self._song_pending = (song, i)
            self.song_pending_label.setText(f"Waiting: {song.title}, {song.slides[i].label}. Approve to project.")

    def _forget_song(self, song_id: str) -> None:
        """A song file was deleted. A pending slide from it is cancelled. The slide already on the
        projector stays until the operator changes it, but nothing more is sent from the deleted song."""
        if self._song_pending is not None and self._song_pending[0].id == song_id:
            self._song_pending = None
            self.song_pending_label.setText("Waiting slide cancelled: its song was deleted.")
        if self._song_sel is not None and self._song_sel.id == song_id:
            self._song_sel = None
        if self._song_live is not None and self._song_live[0].id == song_id:
            self.song_now.setText("The projected song was deleted from the library.")
            self._song_live = None
            self.slide_now_list.clear()

    # --- sermon presets (data/sermons) -------------------------------------------------------
    def _fill_presets(self, select: str = "") -> None:
        self._presets = self.sermon_presets.load_all()
        self.sermon_preset_pick.blockSignals(True)
        self.sermon_preset_pick.clear()
        self.sermon_preset_pick.addItem("(none, type a sermon below)", "")
        for p in self._presets:
            self.sermon_preset_pick.addItem(f"{p.name}: {p.title}", p.id)
        idx = self.sermon_preset_pick.findData(select) if select else 0
        self.sermon_preset_pick.setCurrentIndex(max(idx, 0))
        self.sermon_preset_pick.blockSignals(False)
        self.btn_preset_delete.setEnabled(bool(self._presets))
        if not self._presets:
            self.preset_note.setText("No sermon presets yet. Type a title and speaker, then Save as preset.")

    def _on_preset_pick(self, _index: int) -> None:
        pid = self.sermon_preset_pick.currentData()
        if not pid:
            return
        preset = self.sermon_presets.get(pid)
        if preset is None:
            self._fill_presets()
            return
        self.sermon_title.setText(preset.title)
        self.sermon_speaker.setText(preset.speaker)
        self.sermon_church.setText(preset.church)
        self.preset_note.setText(f"Loaded preset {preset.name}. Show sermon info puts it on the slide.")

    def save_sermon_preset(self) -> None:
        title = self.sermon_title.text().strip()
        if not title:
            self.preset_note.setText("Type a sermon title first, then save it as a preset.")
            return
        default = self.sermon_preset_pick.currentText().split(":")[0] if self.sermon_preset_pick.currentData() else title
        name = self._ask_text("Save sermon preset", "Preset name (saving under an existing name overwrites it):",
                              default).strip()
        if not name:
            return
        try:
            preset = SermonPreset(name=name, title=title, speaker=self.sermon_speaker.text(),
                                  church=self.sermon_church.text())
            saved = self.sermon_presets.save(preset)
        except (ValueError, OSError) as exc:
            self.preset_note.setText(f"Could not save preset: {exc}")
            return
        self._fill_presets(select=saved.id)
        self.preset_note.setText(f"Saved preset {saved.name}.")

    def delete_sermon_preset(self) -> None:
        pid = self.sermon_preset_pick.currentData()
        preset = self.sermon_presets.get(pid) if pid else None
        if preset is None:
            self.preset_note.setText("Pick a saved preset to delete it.")
            return
        if not self._ask_yes_no("Delete sermon preset",
                                f'Delete the preset "{preset.name}"? This cannot be undone.'):
            return
        if not self.sermon_presets.delete(preset.id):
            self.preset_note.setText("Delete failed: the preset file was not found.")
            return
        self._fill_presets()
        self.preset_note.setText(f"Deleted preset {preset.name}.")

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
            self.projection.show_song_slide(song.slides[row], song, row, len(song.slides))
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
            live=None, songs_dir: str = "data/songs", settings: Optional[AppSettings] = None,
            settings_path: Optional[str] = None, dev: bool = False):
    """Start the Qt event loop. pipeline receives dev-feed text; live (optional) runs the mic loop.

    projection_screen picks the starting monitor for the live output (the display box can change it).
    """
    app = QApplication.instance() or QApplication([])
    projection = ProjectionWindow()
    projection.show_theme(theme)
    op = OperatorWindow(queue, theme, projection, pipeline=pipeline, live=live, songs_dir=songs_dir,
                        settings=settings, settings_path=settings_path, dev=dev)
    op.display_box.setCurrentIndex(projection_screen)
    op.resize(1280, 800)
    op.show()
    if op.output.on:
        projection.present()
    return app.exec()
