"""Operator UI (PyQt6): approval queue, live indicator, theme preview, projection window.

Layout:
  Operator window  - audio source picker, level meter, candidate queue, live indicator, keys
  Projection window - borderless, full-screen on a chosen display; shows only the program output
The operator window is never shown on the projector (spec F5 acceptance 1).
"""
from __future__ import annotations

import logging
import time
from datetime import date
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QPoint, QRect, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QGuiApplication, QKeySequence, QShortcut
from PyQt6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFileDialog, QFrame,
                             QInputDialog,
                             QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                             QListWidgetItem, QMainWindow, QPlainTextEdit, QPushButton, QScrollArea,
                             QSpinBox, QStackedWidget, QSizePolicy, QTabWidget, QVBoxLayout, QWidget, QMessageBox)

from .approval import ApprovalQueue
from .media import DEFAULT_MEDIA_FOLDER, MediaItem, MediaLibrary, filter_items, format_duration
from .detection import Candidate
from .displays import (DisplayInfo, default_output_index, list_displays, mode_note, output_mode,
                       should_fullscreen, MODE_DUPLICATED, MODE_EXTENDED)
from .monitor import AudioMonitor, SystemMonitor, band_for
from .output_state import LiveOutputState, pill_state
from .settings_page import SettingsPage
from .preflight import (ACTION_AUDIO_SETUP, ACTION_TOGGLE_OUTPUT, INFO, OK, SUBLINE, headline,
                        heard_sound, preflight)
from .store import APP_VERSION, INPUT_GAIN_RANGE_DB, AppSettings, save_settings
from .paths import bundled
from .sermon import SermonInfo
from .songs import Slide, Song, SongLibrary, lyrics_text, split_lyrics
from .sermon_presets import SermonPreset, SermonPresetLibrary
from .theme import Theme
from .outputs import (PROJECTION_WINDOW_TITLE, paint_background, paint_media_image, paint_media_message,
                      paint_song, paint_sermon,
                      paint_verse)
from .transitions import (FRAME_MS, compose_layout, direction_for, effective_style,
                          interrupt_duration, is_cut, progress)
from .ui_tokens import COLORS, SPACE, build_qss

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


OPERATOR_TICK_MS = 1000              # audit: operator refresh/clock max 1s cadence (visible only)


class ProjectionWindow(QWidget):
    """Borderless live output. Standalone: fullscreen on a chosen display, no OBS needed.

    Hiding it (live output OFF) lets another app take the projector. Any capture tool
    (OBS window capture, virtual camera, other studio software) can read this window.
    Everything is painted by outputs.py (mockups A and B: gold chips, footer, sermon slide).

    Transitions: on a content change the old and new frames are rendered once into pixmaps and
    a QTimer (about 60 fps) composites them (fade, slide, kinetic). The whole composed frame
    moves together, so background images and gradients animate with the text.
    """

    # emitted whenever the projected video starts, stops, pauses or errors, or any content replaces it,
    # so the Media tab playback buttons re-evaluate their enabled state
    video_state_changed = pyqtSignal()
    # right-click on the output: the operator window answers with the monitor menu
    context_menu_requested = pyqtSignal(QPoint)

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setWindowTitle(PROJECTION_WINDOW_TITLE)
        self._theme = Theme()
        self._image_cache: dict = {}
        self._frame = None          # callable(painter, rect) for the settled content; None = background
        self._key = None            # identity of the settled content (same key = no animation)
        self._last_pos = None       # (group, index) of the last content, for direction
        self._last_section = ""     # section label of the last content, for chorus detection
        self._anim = None           # running transition state, or None
        self._live = False          # True only while the window is shown on the output
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.setInterval(FRAME_MS)
        self._timer.timeout.connect(self._on_tick)
        self.setMinimumSize(320, 180)
        self.show_theme(Theme())
        self.show_blank()

    def show_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.update()

    def move_to_display(self, geometry, screen=None) -> None:
        """Cover a whole display (QRect). Borderless and sized to the monitor, so it reads as fullscreen."""
        self._display_rect = geometry
        self._display_screen = screen
        self.setGeometry(geometry)

    def present_fullscreen(self) -> None:
        """Fullscreen on the chosen display (no OBS needed; the window itself is the output)."""
        rect = getattr(self, "_display_rect", None)
        screen = getattr(self, "_display_screen", None)
        if screen is not None and self.windowHandle() is not None:
            self.windowHandle().setScreen(screen)
        if rect is not None:
            self.setGeometry(rect)
        self._live = True
        self.showFullScreen()
        self.raise_()

    def present_minimized(self) -> None:
        """Output is ON but minimized: it never takes over the operator's screen (single or duplicated displays)."""
        rect = getattr(self, "_display_rect", None)
        if rect is not None:
            self.setGeometry(rect)
        self.showMinimized()
        self._live = True                       # set after minimizing: the hide event from minimizing must not clear it

    def present(self) -> None:
        self.present_fullscreen()

    def contextMenuEvent(self, event) -> None:  # noqa: N802 - Qt override
        self.context_menu_requested.emit(event.globalPos())
        event.accept()

    def show_verse(self, c: Candidate | None) -> None:
        if c is None:
            self._set_content(None, ("blank",), "blank", 0, "")
            return
        fn = lambda p, r: paint_verse(p, r, self._theme, c)  # noqa: E731
        key = ("verse", c.reference, c.translation, c.display_text)
        self._set_content(fn, key, ("verse",), 0, "")

    def show_song_slide(self, slide: Slide | None, song=None, index: int = 0, total: int = 0) -> None:
        if slide is None:
            self._set_content(None, ("blank",), "blank", 0, "")
            return
        title = getattr(song, "title", "")
        artist = getattr(song, "artist", "")
        fn = lambda p, r: paint_song(  # noqa: E731
            p, r, self._theme, title=title, artist=artist, section=slide.label,
            index=index, total=total, lines=list(slide.lines), image_cache=self._image_cache)
        key = ("song", title, artist, slide.label, tuple(slide.lines), index, total)
        self._set_content(fn, key, ("song", title, artist), index, slide.label)

    def show_sermon(self, info: SermonInfo | None, church: str = "") -> None:
        if info is None or not info.lines() and not church:
            self._set_content(None, ("blank",), "blank", 0, "")
            return
        line = church or info.church or self._theme.church_line
        fn = lambda p, r: paint_sermon(  # noqa: E731
            p, r, self._theme, church=line, title=info.title,
            speaker=info.speaker, reference=info.reference, image_cache=self._image_cache)
        key = ("sermon", line, info.title, info.speaker, info.reference)
        self._set_content(fn, key, ("sermon",), 0, "")

    def show_media(self, item, loop: bool = False) -> None:
        """Project a media item. Images paint full-frame; videos play in a QVideoWidget.

        Images and the video's first frame go through the transitions pipeline (fade on in and
        out). Video playback itself is not warped.
        """
        if item is None:
            self.show_blank()
            return
        path = item.path
        if item.kind == "image":
            self._stop_video()
            fn = lambda p, r: paint_media_image(p, r, path, self._image_cache)  # noqa: E731
            key = ("media-image", path)
            self._set_content(fn, key, ("media",), 0, "")
            return
        # video: the frame becomes the settled content so the fade-out still has something to show
        key = ("media-video", path, bool(loop))
        self._set_content(None, key, ("media",), 0, "")
        self._play_video(path, loop)

    def _ensure_video(self) -> None:
        if getattr(self, "_video_widget", None) is not None:
            return
        from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
        from PyQt6.QtMultimediaWidgets import QVideoWidget
        self._video_widget = QVideoWidget(self)
        self._video_widget.setGeometry(self.rect())
        self._video_widget.hide()
        self._player = QMediaPlayer(self)
        self._audio = QAudioOutput(self)
        self._audio.setMuted(True)            # projection is video-only; sound goes through the audio mixer
        self._player.setAudioOutput(self._audio)
        self._player.setVideoOutput(self._video_widget)
        self._player.errorOccurred.connect(self._on_video_error)
        self._player.mediaStatusChanged.connect(self._on_video_status)
        self._video_error = ""
        self._video_loop = False

    def _play_video(self, path: str, loop: bool) -> None:
        try:
            self._ensure_video()
        except ImportError:
            self._video_error = "video backend not available"
            self.update()
            return
        from PyQt6.QtCore import QUrl
        self._video_error = ""
        self._video_loop = bool(loop)
        self._video_active = True
        self._video_paused = False
        self._video_widget.setGeometry(self.rect())
        self._video_widget.show()
        self._player.setSource(QUrl.fromLocalFile(path))
        self._player.play()
        self.update()
        self.video_state_changed.emit()

    def _stop_video(self) -> None:
        if getattr(self, "_player", None) is not None:
            self._player.stop()
            self._player.setSource(self._empty_url())
        if getattr(self, "_video_widget", None) is not None:
            self._video_widget.hide()
        self._video_error = ""
        self._video_loop = False
        self._video_active = False
        self._video_paused = False
        self._video_active = False
        self._video_paused = False

    @staticmethod
    def _empty_url():
        from PyQt6.QtCore import QUrl
        return QUrl()

    def _on_video_error(self, *_args) -> None:
        self._video_error = "Cannot play this video format"
        self._video_active = False
        self._video_paused = False
        if getattr(self, "_video_widget", None) is not None:
            self._video_widget.hide()
        self.update()
        self.video_state_changed.emit()

    def _on_video_status(self, status) -> None:
        from PyQt6.QtMultimedia import QMediaPlayer
        if status == QMediaPlayer.MediaStatus.EndOfMedia and self._video_loop and self._player is not None:
            self._rewind_and_play()

    def _rewind_and_play(self) -> None:
        """Back to the first frame and playing. Used by Loop at the end and by Restart."""
        self._player.setPosition(0)
        self._player.play()
        self._video_paused = False

    def set_video_loop(self, loop: bool) -> None:
        self._video_loop = bool(loop)

    # --- playback controls (Media tab buttons) -------------------------------------------
    def has_playing_video(self) -> bool:
        return bool(getattr(self, "_video_active", False)) and getattr(self, "_player", None) is not None

    def is_video_paused(self) -> bool:
        return bool(getattr(self, "_video_paused", False))

    def pause_video(self) -> bool:
        """Pause the projected video. No-op (False) when no video is loaded or it is already paused."""
        if not self.has_playing_video() or self._video_paused:
            return False
        self._player.pause()
        self._video_paused = True
        return True

    def resume_video(self) -> bool:
        """Resume a paused video. No-op (False) when no video is loaded or it is not paused."""
        if not self.has_playing_video() or not self._video_paused:
            return False
        self._player.play()
        self._video_paused = False
        return True

    def toggle_video_pause(self) -> bool:
        return self.resume_video() if self.is_video_paused() else self.pause_video()

    def restart_video(self) -> bool:
        """Restart the projected video from 0 and play it (also clears a paused state)."""
        if not self.has_playing_video():
            return False
        self._rewind_and_play()
        return True

    def show_blank(self) -> None:
        self._set_content(None, ("blank",), "blank", 0, "")

    # --- transitions ----------------------------------------------------------------------
    def _set_content(self, fn, key, group, index: int, section: str) -> None:
        """Make fn the settled content, animating from the previous frame when the theme asks for it."""
        # Any content that is not a video stops the playing video first, so the video widget never
        # sits on top of a verse, song, sermon or blank. The transition then fades from the
        # background (the video's last frame is not captured: simple and correct).
        if not (isinstance(key, tuple) and key and key[0] == "media-video"):
            self._stop_video()
        self.video_state_changed.emit()
        style = effective_style(self._theme.transition, self._last_section, section)
        duration = int(self._theme.transition_ms)
        direction = direction_for(self._last_pos, (group, index))
        same = key == self._key
        old_fn = self._frame
        was_animating = self._anim is not None
        self._key, self._last_pos, self._last_section = key, (group, index), section
        self._frame = fn
        if same or not self._live or is_cut(style, duration):
            self._stop_anim()
            self.update()
            return
        if was_animating:                      # interrupt: start from what is on screen now
            old_pix = self._composite_pixmap()
            dur = interrupt_duration(duration)
        else:
            old_pix = self._render_pixmap(old_fn)
            dur = duration
        self._anim = {"style": style, "old": old_pix, "new": self._render_pixmap(fn),
                      "dir": direction, "dur": max(1, dur), "t0": time.monotonic()}
        self._timer.start()
        self.update()

    def _anim_progress(self) -> float:
        elapsed = (time.monotonic() - self._anim["t0"]) * 1000.0
        return progress(elapsed, self._anim["dur"])

    def _on_tick(self) -> None:
        if self._anim is None:
            self._timer.stop()
            return
        if self._anim_progress() >= 1.0:
            self._stop_anim()
        else:
            self.update()

    def _stop_anim(self) -> None:
        self._timer.stop()
        self._anim = None

    def reset_animation(self) -> None:
        """Drop any running transition and stop video (output toggled off, or the window hidden)."""
        self._stop_anim()
        self._stop_video()
        self._live = False
        self.update()

    def _device_size(self):
        from PyQt6.QtCore import QSize
        return QSize(self.width(), self.height())

    def _new_pixmap(self):
        from PyQt6.QtGui import QColor, QPixmap
        dpr = self.devicePixelRatioF() or 1.0
        size = self._device_size()
        pix = QPixmap(max(1, int(size.width() * dpr)), max(1, int(size.height() * dpr)))
        pix.setDevicePixelRatio(dpr)
        pix.fill(QColor("#000000"))
        return pix

    def _paint_content(self, painter, rect, fn) -> None:
        if fn is None:
            paint_background(painter, rect, self._theme, self._image_cache)
        else:
            fn(painter, rect)

    def _render_pixmap(self, fn):
        from PyQt6.QtGui import QPainter
        from PyQt6.QtCore import QRect
        pix = self._new_pixmap()
        painter = QPainter(pix)
        try:
            self._paint_content(painter, QRect(0, 0, self.width(), self.height()), fn)
        finally:
            painter.end()
        return pix

    def _composite_pixmap(self):
        from PyQt6.QtGui import QPainter
        pix = self._new_pixmap()
        painter = QPainter(pix)
        try:
            self._paint_anim(painter, self.rect(), self._anim_progress())
        finally:
            painter.end()
        return pix

    def _paint_anim(self, painter, rect, t: float) -> None:
        from PyQt6.QtGui import QColor
        a = self._anim
        layout = compose_layout(a["style"], t, a["dir"], float(rect.width()))
        cx, cy = rect.width() / 2, rect.height() / 2
        painter.fillRect(rect, QColor("#000000"))
        self._draw_layer(painter, a["old"], layout["old_dx"], layout["old_scale"],
                         layout["old_alpha"], cx, cy)
        self._draw_layer(painter, a["new"], layout["new_dx"], layout["new_scale"],
                         layout["new_alpha"], cx, cy)

    @staticmethod
    def _draw_layer(painter, pix, dx: float, scale: float, alpha: float, cx: float, cy: float) -> None:
        if alpha <= 0.0:
            return
        painter.save()
        painter.setOpacity(max(0.0, min(1.0, alpha)))
        painter.translate(cx + dx, cy)
        painter.scale(scale, scale)
        painter.translate(-cx, -cy)
        painter.drawPixmap(0, 0, pix)
        painter.restore()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        if getattr(self, "_video_widget", None) is not None:
            self._video_widget.setGeometry(self.rect())
        super().resizeEvent(event)

    def hideEvent(self, event) -> None:  # noqa: N802 - Qt override
        # Minimizing also sends a hide event, but the output is still live then (it is just parked),
        # so only a real hide (live output OFF) stops the transition and the video.
        if not self.isMinimized():
            self.reset_animation()
        super().hideEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        from PyQt6.QtGui import QPainter
        painter = QPainter(self)
        try:
            rect = self.rect()
            if self._anim is not None:
                self._paint_anim(painter, rect, self._anim_progress())
            else:
                self._paint_content(painter, rect, self._frame)
            if getattr(self, "_video_error", ""):
                paint_media_message(painter, rect, self._video_error)
        finally:
            painter.end()


QSS = build_qss()     # all colours, sizes and spacing live in ui_tokens.py


def _set_prop(w, name, value) -> None:
    """Re-polish a widget after changing a QSS dynamic property."""
    w.setProperty(name, value)
    w.style().unpolish(w)
    w.style().polish(w)


def _set_name(w, name: str) -> None:
    """Switch a widget to another QSS object name and re-polish it. No-op if it already has that name,
    so calling it every refresh costs nothing."""
    if w.objectName() == name:
        return
    w.setObjectName(name)
    w.style().unpolish(w)
    w.style().polish(w)


_LOGO_PATH = bundled("revelatetw", "assets", "logo.png")


def _logo_pixmap(height: int = 30):
    """Brand logo scaled to `height` px (aspect kept), or None if the asset is missing or unreadable."""
    from PyQt6.QtGui import QPixmap
    if not _LOGO_PATH.is_file():
        return None
    pix = QPixmap(str(_LOGO_PATH))
    if pix.isNull():
        return None
    return pix.scaledToHeight(height, Qt.TransformationMode.SmoothTransformation)


def _brand_mark(height: int = 30) -> QLabel:
    """Logo image for the toolbar; falls back to the gold 'R' badge if the asset is missing."""
    pix = _logo_pixmap(height)
    if pix is None:
        return _label("R", "brand")
    lab = QLabel()
    lab.setObjectName("brandLogo")
    lab.setPixmap(pix)
    lab.setFixedSize(pix.size())
    return lab


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


_log = logging.getLogger(__name__)

# --- header monitoring widgets (top bar only; fixed width so the header never jiggles) -----
WAVE_BARS = 24
WAVE_W, WAVE_H = 210, 30
SYS_W, SYS_H = 176, 30
HEADER_TICK_MS = 200           # 5 fps wave + chip repaint, runs only while the window is visible

_GOLD_HEX, _AMBER_HEX, _RED_HEX, _GREEN_HEX = "#facc15", "#f59e0b", "#ef4444", "#22c55e"
_GREY_HEX, _PANEL_HEX, _TRACK_HEX = "#64748b", "#131926", "#2a3346"
_BAND_HEX = {"green": _GREEN_HEX, "amber": _AMBER_HEX, "red": _RED_HEX, "none": _GREY_HEX}


class MicWaveWidget(QWidget):
    """AUDIO SOURCE: 24 gold bars driven by level history with peak-hold decay.

    States: live (gold bars, green dot when signal present), detection off (flat dimmed strip,
    grey dot), no mic device (flat strip, 'NO MIC' label instead of a dot). Turns red/amber when
    the PC is under load (set_load_band). Never hidden, so the header layout never jumps.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(WAVE_W, WAVE_H)
        self.setObjectName("waveWidget")
        self.setToolTip("AUDIO SOURCE level. Needs the live microphone selected in Settings > Audio.")
        self._history = [0.0] * WAVE_BARS     # newest last
        self._peak = 0.0                      # peak-hold value shown as the top marker
        self._present = False
        self._state = "off"                   # off | live | nomic
        self._load = "none"                   # green | amber | red | none (from SysChipWidget)

    # state setters (main thread only)
    def set_detection_off(self) -> None:
        self._state = "off"
        self._present = False
        self._history = [0.0] * WAVE_BARS
        self._peak = 0.0
        self.update()

    def set_no_mic(self) -> None:
        self._state = "nomic"
        self._present = False
        self._history = [0.0] * WAVE_BARS
        self._peak = 0.0
        self.update()

    def push(self, level: float, peak: float, present: bool) -> None:
        """One UI tick of audio data. peak decays by 12%/tick so the top marker falls back."""
        self._state = "live"
        self._present = bool(present)
        self._history = self._history[1:] + [max(0.0, min(1.0, float(level)))]
        self._peak = max(float(peak), self._peak * 0.88)
        self.update()

    def set_load_band(self, band: str) -> None:
        if band != self._load:
            self._load = band
            self.update()

    def bar_color(self) -> QColor:
        if self._state != "live":
            return QColor(_GOLD_HEX)
        if self._load == "red":
            return QColor(_RED_HEX)
        if self._load == "amber":
            return QColor(_AMBER_HEX)
        return QColor(_GOLD_HEX)

    def label_text(self) -> str:
        return "NO MIC" if self._state == "nomic" else "AUDIO SOURCE"

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        from PyQt6.QtCore import QRectF
        from PyQt6.QtGui import QBrush, QFont, QPainter, QPen
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            w, h = self.width(), self.height()
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(_PANEL_HEX))
            p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 8, 8)
            dim = self._state != "live"
            # mic glyph: capsule + stand
            ink = QColor(_GREY_HEX if dim else _GOLD_HEX)
            p.setBrush(ink)
            p.drawRoundedRect(QRectF(9, 7, 6, 10), 3, 3)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(ink, 1.4))
            p.drawArc(QRectF(6, 9, 12, 9), 180 * 16, -180 * 16)
            p.drawLine(12, 18, 12, 21)
            p.setPen(Qt.PenStyle.NoPen)
            # label
            font = QFont("Segoe UI", 8)
            font.setBold(True)
            p.setFont(font)
            p.setPen(QColor("#94a3b8" if dim else "#e5e7eb"))
            p.drawText(QRectF(20, 0, 84, h), Qt.AlignmentFlag.AlignVCenter, self.label_text())
            # status dot / label handled above; dot sits at the right edge
            if self._state == "live":
                p.setBrush(QColor(_GREEN_HEX if self._present else _GREY_HEX))
                p.drawEllipse(QRectF(w - 13, h / 2 - 3.5, 7, 7))
            elif self._state == "off":
                p.setBrush(QColor(_GREY_HEX))
                p.drawEllipse(QRectF(w - 13, h / 2 - 3.5, 7, 7))
            # bars area
            x0, x1, top, bottom = 6, w - 18, 5, h - 5
            bars_w = x1 - x0
            slot = bars_w / WAVE_BARS
            bw = max(2.0, slot * 0.55)
            color = self.bar_color()
            track = QColor(_TRACK_HEX)
            for i, lv in enumerate(self._history):
                cx = x0 + i * slot + (slot - bw) / 2
                if dim:
                    p.setBrush(track)
                    p.drawRoundedRect(QRectF(cx, bottom - 2, bw, 2), 1, 1)
                    continue
                bh = max(2.0, lv * (bottom - top))
                c = QColor(color)
                if not dim:
                    c.setAlphaF(0.35 + 0.65 * min(1.0, lv * 1.5))
                p.setBrush(QBrush(c))
                p.drawRoundedRect(QRectF(cx, bottom - bh, bw, bh), 1, 1)
            if self._state == "live" and self._peak > 0.02:
                py = bottom - self._peak * (bottom - top)
                p.setBrush(color)
                p.drawRect(QRectF(x0, py, bars_w, 1.2))
        finally:
            p.end()


class SysChipWidget(QWidget):
    """'CPU 23%  RAM 41%' with two mini bars. Colour band: green <60, amber 60-85, red >85."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(SYS_W, SYS_H)
        self.setObjectName("sysChip")
        self.setToolTip("PC load: CPU and RAM, sampled every 2 seconds.")
        self._cpu: Optional[float] = None
        self._ram: Optional[float] = None

    def set_values(self, cpu: Optional[float], ram: Optional[float]) -> None:
        self._cpu, self._ram = cpu, ram
        self.update()

    def cpu_band(self) -> str:
        return band_for(self._cpu)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        from PyQt6.QtCore import QRectF
        from PyQt6.QtGui import QFont, QPainter
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            w, h = self.width(), self.height()
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(_PANEL_HEX))
            p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 8, 8)
            font = QFont("Consolas", 8)
            font.setBold(True)
            p.setFont(font)
            fm = p.fontMetrics()
            cpu_txt = "CPU --" if self._cpu is None else f"CPU {round(self._cpu):d}%"
            ram_txt = "RAM --" if self._ram is None else f"RAM {round(self._ram):d}%"
            # fixed columns keep the chip the same width whatever the numbers
            p.setPen(QColor(_BAND_HEX[band_for(self._cpu)]))
            p.drawText(QRectF(8, 0, 58, 16), Qt.AlignmentFlag.AlignVCenter, cpu_txt)
            p.setPen(QColor(_BAND_HEX[band_for(self._ram)]))
            p.drawText(QRectF(90, 0, 80, 16), Qt.AlignmentFlag.AlignVCenter, ram_txt)
            # mini bars under the text (fixed 4px height)
            for x, val, lab in ((8, self._cpu, "cpu"), (90, self._ram, "ram")):
                bar_w = 76 if lab == "ram" else 70
                p.setBrush(QColor(_TRACK_HEX))
                p.drawRoundedRect(QRectF(x, h - 9, bar_w, 4), 2, 2)
                if val is not None:
                    fill = max(0.0, min(100.0, float(val))) / 100.0 * bar_w
                    p.setBrush(QColor(_BAND_HEX[band_for(val)]))
                    p.drawRoundedRect(QRectF(x, h - 9, fill, 4), 2, 2)
        finally:
            p.end()


def _cell_name(name: str, limit: int = 22) -> str:
    """File name shortened for a grid cell (the full file name is in the tooltip)."""
    return name if len(name) <= limit else name[: limit - 1] + "\u2026"


class AspectBox(QWidget):
    """Holds one child at a fixed aspect ratio: full width, height derived, letterboxed (no distortion)."""

    def __init__(self, child: QWidget, ratio: float = 16 / 9, parent=None):
        super().__init__(parent)
        self._child = child
        self._ratio = ratio
        child.setParent(self)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, w: int) -> int:
        return int(round(w / self._ratio))

    def sizeHint(self):
        return QSize(320, int(round(320 / self._ratio)))

    def minimumSizeHint(self):
        return QSize(160, int(round(160 / self._ratio)))

    def resizeEvent(self, _event) -> None:
        w = self.width()
        h = min(self.height(), int(round(w / self._ratio)))
        y = (self.height() - h) // 2
        self._child.setGeometry(0, y, w, h)


class MediaPreviewWidget(QWidget):
    """The selected media drawn the way the projection output draws it: 16:9, letterboxed on black."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._item = None
        self._image_cache: dict = {}
        self._thumb_cache: dict = {}
        self.setMinimumSize(320, 180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_item(self, item) -> None:
        self._item = item
        self.update()

    def paintEvent(self, _event) -> None:
        from PyQt6.QtGui import QPainter, QPixmap
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#0b0f19"))
        w, h = self.width(), self.height()
        fw = min(w, h * 16 / 9)
        fh = fw * 9 / 16
        rect = QRect(int((w - fw) / 2), int((h - fh) / 2), int(fw), int(fh))
        it = self._item
        if it is None:
            painter.setPen(QColor("#64748b"))
            painter.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), "No media selected")
        elif not it.is_video:
            paint_media_image(painter, rect, it.path, self._image_cache)
        else:
            painter.fillRect(rect, QColor("#000000"))
            pix = self._thumb_cache.get(it.path)
            if pix is None:
                pix = QPixmap(it.thumb) if it.thumb else QPixmap()
                self._thumb_cache[it.path] = pix
            if not pix.isNull():
                scaled = pix.scaled(rect.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                    Qt.TransformationMode.SmoothTransformation)
                painter.drawPixmap(rect.x() + (rect.width() - scaled.width()) // 2,
                                   rect.y() + (rect.height() - scaled.height()) // 2, scaled)
            strip = QRect(rect.x(), rect.bottom() - 28, rect.width(), 28)
            painter.fillRect(strip, QColor(0, 0, 0, 170))
            painter.setPen(QColor("#facc15"))
            label = "\u25B6  VIDEO" + (f"  \u00b7  {it.duration_label()}" if it.duration_label() else "")
            painter.drawText(strip, int(Qt.AlignmentFlag.AlignCenter), label)
        painter.end()


class OperatorWindow(QMainWindow):
    def __init__(self, queue: ApprovalQueue, theme: Theme, projection: ProjectionWindow,
                 audio_meter=None, pipeline=None, live=None, songs_dir: str = "data/songs",
                 settings: Optional[AppSettings] = None, settings_path: Optional[str] = None,
                 dev: bool = False, sermons_dir: str = "data/sermons"):
        super().__init__()
        self.settings = settings or AppSettings()
        self._settings_path = settings_path
        self._dev = bool(dev)
        self.setWindowTitle("RevelateTW")
        self.queue = queue
        self.pipeline = pipeline
        self.live = live                  # LiveTranscriptionLoop (mic or dev text)
        self.theme = theme
        self.projection = projection
        self.projection.video_state_changed.connect(self._update_media_controls)
        self._audio_meter = audio_meter  # callable returning {'peak_db', 'rms_db'} or None
        self._devices = []
        self._started = time.time()
        self._cursor: Optional[tuple[int, int, int]] = None  # (book, chapter, verse) last projected
        self._store = getattr(pipeline, "detector", None) and pipeline.detector.store
        # Always starts OFF: the projection window is never shown until the operator projects.
        self.output = LiveOutputState(on=False)  # LIVE pill: shown or hidden
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
        self.media = MediaLibrary(self.settings.media_folder or DEFAULT_MEDIA_FOLDER)
        self._media_live: Optional[object] = None   # MediaItem on the output, or None
        self._media_items: list = []
        self.sermon_presets = SermonPresetLibrary(sermons_dir)
        self._songs: list[Song] = []
        self._setup_autoexpanded = False     # Audio & display section opened itself once for a problem
        self._heard_sound = False            # the mic has picked up sound since it was (re)opened
        self._check_sig = None               # last checklist shown; the card is rebuilt only when it changes
        # Gain can change on every arrow-key step; the file is written once the operator stops.
        self._gain_save_timer = QTimer(self, singleShot=True, interval=600, timeout=self._save_settings)

        self.setStyleSheet(QSS)
        central = QWidget()
        central.setObjectName("root")
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._build_toolbar())

        body = QHBoxLayout()
        body.setContentsMargins(SPACE.gap, SPACE.md, SPACE.gap, SPACE.md)
        body.setSpacing(SPACE.gap)
        body.addWidget(self._build_transcript_panel(), 3)
        body.addWidget(self._build_queue_panel(), 3)
        live_page = QWidget()
        live_page.setLayout(body)
        # ONE live preview panel, docked on the right of the main window. It sits outside the tabs,
        # so switching tabs only swaps the left-to-middle content and the preview never moves.
        self.shared_preview = self._build_preview_panel()
        self.shared_preview.setMinimumWidth(300)
        preview_scroll = QScrollArea()
        preview_scroll.setWidgetResizable(True)
        preview_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        preview_scroll.setFrameShape(QFrame.Shape.NoFrame)
        preview_scroll.setWidget(self.shared_preview)
        preview_dock = QWidget()
        pd = QVBoxLayout(preview_dock)
        pd.setContentsMargins(0, SPACE.md, SPACE.gap, SPACE.md)
        pd.setSpacing(0)
        pd.addWidget(preview_scroll)
        self._tabs = QTabWidget()
        self._tabs.addTab(live_page, "Verses")
        self._tabs.addTab(self._build_songs_tab(), "Songs & sermon")
        self._tabs.addTab(self._build_media_tab(), "Media")
        from . import fftools
        fftools.set_configured_dir(self.settings.ffmpeg_dir)
        self.settings_page = SettingsPage(self.settings, check_updates_cb=self._check_updates)
        self.settings_page.changed.connect(self._on_setting_changed)
        self._tabs.addTab(self.settings_page, "Settings")
        self._settings_index = self._tabs.count() - 1
        for i in range(self._tabs.count()):       # Ctrl+1 to Ctrl+4 switch tabs (see _build_shortcuts)
            self._tabs.setTabToolTip(i, f"{self._tabs.tabText(i)} (Ctrl+{i + 1})")
        middle = QHBoxLayout()
        middle.setContentsMargins(0, 0, 0, 0)
        middle.setSpacing(0)
        middle.addWidget(self._tabs, 5)
        middle.addWidget(preview_dock, 3)
        outer.addLayout(middle, 1)
        outer.addWidget(self._build_statusbar())
        if self.settings.check_updates_on_startup:
            QTimer.singleShot(3000, lambda: self._check_updates(self._on_startup_update))

        self._build_shortcuts()
        self.source_box.currentIndexChanged.connect(self._apply_source)
        self.device_box.currentIndexChanged.connect(self._apply_source)
        self._populate_devices()
        self.btn_source_mic.toggled.connect(self._on_source_toggle)
        self.btn_source_dev.toggled.connect(self._on_source_toggle)
        self.btn_setup.toggled.connect(self._on_setup_toggle)
        self.gain.valueChanged.connect(self._on_gain_changed)
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
        self.song_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.song_list.customContextMenuRequested.connect(self._song_context_menu)
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

        # Audit: operator refresh/clock cadence is 1s (was 150ms) and runs only while the window
        # is visible (showEvent/hideEvent below). The status clock needs whole seconds only.
        self._timer = QTimer(self, interval=OPERATOR_TICK_MS, timeout=self.refresh)
        self._timer.setTimerType(Qt.TimerType.CoarseTimer)   # 1s, whole-second clock is enough
        # Header monitoring: one 5 fps main-thread timer, alive only while visible AND live mic
        # detection is on. The PC sampler is a QThread that runs only while visible.
        self.audio_mon = AudioMonitor()
        self.sys_mon = SystemMonitor(parent=self)
        self.sys_mon.sampled.connect(self._on_sys_sampled)   # queued: emitted from worker thread
        self._mic_on = False                                 # True once start_mic succeeded
        self._mic_dev = None                                 # InputDevice currently capturing
        self._failed_devices: set[str] = set()               # inputs that failed to open this session
        self._capture_error = ""
        self._header_timer = QTimer(self, interval=HEADER_TICK_MS, timeout=self._tick_header)
        self._header_timer.setTimerType(Qt.TimerType.CoarseTimer)
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
        lay.setContentsMargins(SPACE.panel_x, SPACE.md, SPACE.panel_x, SPACE.md)
        lay.setSpacing(SPACE.md)
        lay.addWidget(_brand_mark(30))
        lay.addWidget(_label("RevelateTW", "title"))
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
        self.wave = MicWaveWidget()
        self.sys_chip = SysChipWidget()
        lay.addWidget(self.wave)
        lay.addWidget(self.sys_chip)
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
        # "Getting ready" card: shown until the first words are transcribed (see _update_checklist).
        self.checklist = QFrame()
        self.checklist.setObjectName("checklist")
        cl = QVBoxLayout(self.checklist)
        cl.setContentsMargins(SPACE.xl, SPACE.lg, SPACE.xl, SPACE.lg)
        cl.setSpacing(SPACE.md)
        self.check_title = _label("Getting ready", "checkTitle")
        cl.addWidget(self.check_title)
        self.check_rows = QVBoxLayout()
        self.check_rows.setSpacing(SPACE.sm)
        cl.addLayout(self.check_rows)
        cl.addWidget(_label(SUBLINE, "sub", wrap=True))
        lay.addWidget(self.checklist)
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
        # Transcriber and latency are shown once, in the status bar at the bottom of the window.
        return frame

    def _build_queue_panel(self) -> QFrame:
        frame, lay = self._panel("Approval Queue", "")
        self.queue_badge = _label("0 pending", "badge")
        frame.layout().itemAt(0).layout().insertWidget(2, self.queue_badge)

        # translation picker: applies to detected + manual verses, remembered in settings
        self.translation_box = QComboBox()
        self.translation_box.setToolTip("Translation for detected and manual verses. Remembered in settings.")
        self._fill_translation_box()
        self.translation_box.currentIndexChanged.connect(self._on_translation_pick)
        tr_row = QHBoxLayout()
        tr_row.addWidget(_label("Translation", "badge"))
        tr_row.addWidget(self.translation_box, 1)
        lay.addLayout(tr_row)

        # one-time, dismissible Yoruba live-detection advisory (informs only, never blocks)
        self.yoruba_note = QFrame()
        self.yoruba_note.setObjectName("liveNote")
        yn = QHBoxLayout(self.yoruba_note)
        yn.setContentsMargins(6, 4, 6, 4)
        self.yoruba_note_text = QLabel("")
        self.yoruba_note_text.setWordWrap(True)
        yn.addWidget(self.yoruba_note_text, 1)
        dismiss = QPushButton("Dismiss")
        dismiss.clicked.connect(self._dismiss_yoruba_advisory)
        yn.addWidget(dismiss)
        self.yoruba_note.hide()
        lay.addWidget(self.yoruba_note)

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
        self.list.setObjectName("queueList")     # larger rows and text (see ui_tokens)
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
        self.btn_hold.setObjectName("subtle")
        self.btn_blank = QPushButton("Blank (B)")
        self.btn_blank.setObjectName("subtle")
        # Approve is the main action: it gets twice the width of the others.
        row.addWidget(self.btn_approve, 2)
        for b in (self.btn_reject, self.btn_hold, self.btn_blank):
            row.addWidget(b, 1)
        lay.addLayout(row)
        # Auto-approve and "queue cleared" are shown once, in the status bar at the bottom of the window.
        return frame

    def _build_preview_panel(self) -> QFrame:
        frame, lay = self._panel("Live Projection Preview", "")
        self.output_badge = _label("Output 1 \u00b7 1920\u00d71080", "badge")
        frame.layout().itemAt(0).layout().insertWidget(2, self.output_badge)
        self.slide = QFrame()
        self.slide.setObjectName("slide")
        sl = QVBoxLayout(self.slide)
        sl.setContentsMargins(12, 10, 12, 10)
        self.slide_text = _label("", "slideText", wrap=True)
        self.slide_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.slide_ref = _label("", "slideRef")
        self.slide_ref.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.shared_media = MediaPreviewWidget()    # the projected image or video, shown in the same frame
        self.shared_media.hide()
        sl.addWidget(self.shared_media, 1)
        sl.addWidget(self.slide_text, 1)
        sl.addWidget(self.slide_ref)
        lay.addWidget(AspectBox(self.slide), 0)   # 16:9 like the output, letterboxed at the panel's width

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

        # Output state, shown once here. The LIVE pill in the toolbar is the control; this line also
        # says "Blanked", which the pill cannot.
        self.footer_proj = _label("Projecting", "footerOk")
        lay.addWidget(self.footer_proj)

        grid = QGridLayout()
        grid.setSpacing(SPACE.sm)
        self.tile_theme = self._tile("Theme", self.theme.name)
        self.tile_transition = self._tile("Transition", f"{self.theme.transition.title()} \u00b7 {self.theme.transition_ms}ms")
        grid.addWidget(self.tile_theme, 0, 0)
        grid.addWidget(self.tile_transition, 0, 1)
        lay.addLayout(grid)
        self.btn_theme = QPushButton("Theme editor...")
        self.btn_theme.clicked.connect(self.open_theme_editor)
        lay.addWidget(self.btn_theme)

        # Setup (projector display and audio input) is needed once per service, so it is collapsed
        # by default. The summary line under the button says what is currently chosen, and the section
        # opens by itself if audio reports a problem (see _update_setup_summary).
        self.btn_setup = QPushButton("Audio & display \u25b8")
        self.btn_setup.setObjectName("disclosure")
        self.btn_setup.setCheckable(True)
        self.btn_setup.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_setup.setToolTip("Choose the projector display and the audio input")
        lay.addWidget(self.btn_setup)
        self.setup_summary = _label("", "sub", wrap=True)
        lay.addWidget(self.setup_summary)
        self.setup_box = QFrame()
        self.setup_box.setObjectName("setupBody")
        sb = QVBoxLayout(self.setup_box)
        sb.setContentsMargins(SPACE.lg, SPACE.md, SPACE.lg, SPACE.lg)
        sb.setSpacing(SPACE.sm)
        sb.addWidget(_label("Output display", "fieldLabel"))
        disp = QHBoxLayout()
        self.display_box = QComboBox()
        self.display_box.setToolTip("Monitor for the live output. Fullscreen borderless on that display.")
        self.btn_rescan = QPushButton("Rescan")
        self.btn_rescan.setObjectName("ghost")
        disp.addWidget(self.display_box, 1)
        disp.addWidget(self.btn_rescan)
        sb.addLayout(disp)
        sb.addWidget(_label("Fullscreen on that monitor. Any capture software can read it.", "sub", wrap=True))
        sb.addWidget(_label("Audio input", "fieldLabel"))
        self.source_box = QComboBox()
        self.source_box.addItems(["Dev text feed", "Live microphone"])
        self.source_box.setCurrentIndex(1)           # default source: live microphone
        self.source_box.hide()   # the Mic / Dev feed pills in the toolbar drive this
        self.device_box = QComboBox()
        self.device_box.setToolTip("Audio input (WASAPI loopback lists mixing-desk output)")
        self.device_box.setPlaceholderText("Audio input")
        sb.addWidget(self.device_box)
        gain_row = QHBoxLayout()
        gain_row.addWidget(_label("Input gain", "fieldLabel"))
        self.gain = QDoubleSpinBox()
        self.gain.setRange(*INPUT_GAIN_RANGE_DB)
        self.gain.setDecimals(1)
        self.gain.setSingleStep(1.0)
        self.gain.setSuffix(" dB")
        self.gain.setKeyboardTracking(False)          # typing a number applies on Enter, not per digit
        self.gain.setValue(self.settings.input_gain_db)
        self.gain.setToolTip("Input gain. Raise it if the level meter stays low while the preacher "
                             "speaks. Applies immediately and is remembered.")
        gain_row.addWidget(self.gain, 1)
        sb.addLayout(gain_row)
        self.meter = _label("Level: --", "footer")
        sb.addWidget(self.meter)
        self.source_status = _label("", "footer", wrap=True)
        sb.addWidget(self.source_status)
        self.setup_box.hide()
        lay.addWidget(self.setup_box)
        lay.addStretch(1)
        return frame

    def _build_songs_tab(self) -> QWidget:
        page = QWidget()
        self._songs_page = page
        root = QHBoxLayout(page)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(8)

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
        self.btn_import_song = QPushButton("Import")
        self.btn_import_song.setToolTip("Import a .rtsong file, a .txt lyrics file, or pasted lyrics")
        self.btn_export_all = QPushButton("Export all")
        self.btn_export_all.setToolTip("Save every song to one .rtsong file")
        self.btn_export_all.clicked.connect(lambda: self._export_song(None))
        row.addWidget(self.btn_new_song)
        row.addWidget(self.btn_import_song)
        row.addWidget(self.btn_export_all)
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


    def _update_shared_preview(self) -> None:
        """The one live preview: mirrors what the output shows (verse, song slide, sermon info or media)."""
        if not hasattr(self, "slide_text"):
            return
        text, ref, media = "", "", None
        if self.queue.blank:
            pass
        elif self._kind == "song" and self._song_live:
            song, i = self._song_live
            slide = song.slides[i]
            text = "\n".join(slide.lines)
            ref = f"{song.title}  \u00b7  {slide.label}"
        elif self._kind == "sermon" and self._sermon_live:
            text = "\n".join(self._sermon_live.lines())
        elif self._kind == "media" and self._media_live is not None:
            media = self._media_live
            ref = f"{media.name}  \u00b7  {media.type_label}"
            if media.is_video and media.duration_label():
                ref += f"  \u00b7  {media.duration_label()}"
        elif self.queue.live is not None:
            text = self.queue.live.display_text
            ref = self.queue.live.reference
        self.shared_media.set_item(media)
        self.shared_media.setVisible(media is not None)
        self.slide_text.setVisible(media is None)
        self.slide_text.setText(text)
        self.slide_ref.setText(ref)

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
        lay.setContentsMargins(SPACE.panel_x, SPACE.panel_y, SPACE.panel_x, SPACE.panel_y)
        lay.setSpacing(SPACE.md)
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
        v.setContentsMargins(8, 6, 8, 6)
        v.setSpacing(1)
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

        for i in range(4):
            QShortcut(QKeySequence(f"Ctrl+{i + 1}"), self, activated=lambda i=i: self._goto_tab(i))

        for key, fn in [("Return", self.approve_selected), ("Escape", self.reject_selected),
                        ("E", self.edit_selected), ("H", self.hold_selected),
                        ("Down", lambda: self._move(1)), ("Up", lambda: self._move(-1)),
                        ("Left", lambda: self.step(-1)), ("Right", lambda: self.step(+1)),
                        ("Space", lambda: self.step(+1)), ("B", self.toggle_blank),
                        ("O", self.toggle_output),
                        ("/", self.focus_search)]:
            QShortcut(QKeySequence(key), self, activated=guard(fn))

    def _goto_tab(self, index: int) -> None:
        if 0 <= index < self._tabs.count() and self._tabs.isTabEnabled(index):
            self._tabs.setCurrentIndex(index)

    def _typing(self) -> bool:
        fw = QApplication.focusWidget()
        return isinstance(fw, (QLineEdit, QPlainTextEdit))

    # --- live source -----------------------------------------------------------------------
    def _populate_devices(self) -> None:
        if self.live is None:
            self.btn_source_mic.setEnabled(False)
            self.device_box.setEnabled(False)
            self.source_status.setText("Live audio not available in this session.")
            if self._dev:
                self.btn_source_dev.setChecked(True)
                self.source_status.setText("Live audio not available in this session (dev text feed only).")
            return
        try:
            from .audio import list_input_devices
            found = list_input_devices()
            self._devices = [d for d in found if not d.loopback] + [d for d in found if d.loopback]
        except Exception as exc:  # sounddevice missing or no audio host
            _log.warning("audio device enumeration failed: %s", exc)
            self._devices = []
            self.source_status.setText(f"Audio devices unavailable: {exc}")
        self.device_box.blockSignals(True)
        self.device_box.clear()
        for d in self._devices:
            self.device_box.addItem(f"{d.name}  ({d.channels} ch, {d.default_rate} Hz)")
        # Start on the SYSTEM DEFAULT input (never a hardcoded index); a remembered name still wins.
        self.device_box.setCurrentIndex(self._default_device_row())
        self.device_box.blockSignals(False)
        if hasattr(self, "settings_page") and self.settings_page is not None:
            self.settings_page.set_input_devices([d.name for d in self._devices if not d.loopback]
                                                 + [d.name for d in self._devices if d.loopback])

    def _default_device_row(self) -> int:
        """Row for the remembered device name if it still exists, else the system default input."""
        remembered = self.settings.input_device_name
        for i, d in enumerate(self._devices):
            if remembered and d.name == remembered:
                return i
        from .audio import pick_default_device
        try:
            chosen = pick_default_device(self._devices)
        except Exception as exc:  # noqa: BLE001
            _log.warning("default input lookup failed: %s", exc)
            chosen = None
        for i, d in enumerate(self._devices):
            if chosen is not None and d is chosen:
                return i
        return 0

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
            self._mic_on = False
            self._mic_dev = None
            self._refresh_header_state()
            self.source_status.setText("Dev text feed (typed sentences)")
            self.status_transcriber.setText("Transcriber: text feed")
            return
        # A user action (picking a device, pressing Mic) gives every input a fresh chance.
        self._failed_devices.clear()
        self._open_mic_chain()

    def _start_default_mic(self) -> None:
        """Startup: go live on the system default input without waiting for a click."""
        from .audio import InputDevice
        if self.live is None or self._dev or not self._devices:
            return
        if not all(isinstance(d, InputDevice) for d in self._devices):
            return                          # not real devices (test doubles): leave the mic off
        self.source_box.blockSignals(True)
        self.source_box.setCurrentIndex(1)
        self.source_box.blockSignals(False)
        self.btn_source_mic.setChecked(True)     # toggled -> _on_source_toggle -> _apply_source
        self._refresh_header_state()

    def _open_mic_chain(self) -> None:
        """Open the picked input, then the system default, then fall back to the text feed.

        Every failure is logged and shown in the status line and on the AUDIO SOURCE wave.
        """
        from .audio import pick_default_device
        row = max(0, self.device_box.currentIndex())
        chosen = self._devices[row] if row < len(self._devices) else self._devices[0]
        default = pick_default_device(self._devices)
        candidates: list = []
        for dev in (chosen, default):
            if dev is None or dev.name in self._failed_devices:
                continue
            if any(dev is c for c in candidates):
                continue
            candidates.append(dev)
        if not candidates:
            # every configured input already failed this session: try the rest, in list order
            candidates = [d for d in self._devices if d.name not in self._failed_devices]
        opened = None
        last_exc = None
        for dev in candidates:
            try:
                self.live.start_mic(dev, gain_db=self.settings.input_gain_db,
                                    gate_db=self.settings.noise_gate_db, tap=self.audio_mon.feed)
                opened = dev
                break
            except Exception as exc:  # device busy, unplugged, or unsupported
                last_exc = exc
                self._failed_devices.add(dev.name)
                _log.warning("could not open audio input %r: %s", dev.name, exc)
        if opened is None:
            self._mic_on = False
            self._mic_dev = None
            self._capture_error = f"Mic failed, back to text feed: {last_exc or 'no usable input'}"
            self.live.use_text_feed()
            self.source_box.blockSignals(True)
            self.source_box.setCurrentIndex(0)
            self.source_box.blockSignals(False)
            self.btn_source_dev.setChecked(True)
            self.source_status.setText(self._capture_error)
            self.wave.set_no_mic()
            self._refresh_header_state()
            return
        self._mic_on = True
        self._mic_dev = opened
        self._capture_error = ""
        self._heard_sound = False                 # a new input has to prove it hears sound
        if opened is not chosen:
            _log.warning("configured input %r unavailable, using %r", chosen.name, opened.name)
            self.source_status.setText(f"{chosen.name} unavailable, using default input: {opened.name}")
            for i, d in enumerate(self._devices):   # keep the picker honest: show the device in use
                if d is opened:
                    self.device_box.blockSignals(True)
                    self.device_box.setCurrentIndex(i)
                    self.device_box.blockSignals(False)
                    break
        else:
            self.source_status.setText(f"Listening: {opened.name}")
        self.status_transcriber.setText("Transcriber: Whisper")
        self._refresh_header_state()

    def _check_capture(self) -> bool:
        """Watchdog (main thread, while the wave runs). True when the capture had to be replaced.

        A stream that errors inside the audio callback, or that never delivers a block, is
        reported and moved to the next input instead of leaving a dead grey wave.
        """
        cap = getattr(self.live, "capture", None) if self.live is not None else None
        if cap is None or self._mic_dev is None:
            return False
        err = cap.error
        if not err and not cap.stalled():
            return False
        name = self._mic_dev.name
        reason = err or "no audio arrived from this input"
        _log.warning("capture on %r failed: %s", name, reason)
        self._failed_devices.add(name)
        self.source_status.setText(f"{name} failed ({reason}). Switching input.")
        self._populate_devices()                 # hot-plug: pick up devices added or removed
        self._open_mic_chain()
        return True

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

    # --- Bible translations ------------------------------------------------------------
    def _bible_library(self):
        if getattr(self, "_bible", None) is None:
            from .bible import BibleLibrary
            self._bible = BibleLibrary()
        return self._bible

    def _fill_translation_box(self) -> None:
        lib = self._bible_library()
        wanted = self.settings.bible_translation
        self.translation_box.blockSignals(True)
        self.translation_box.clear()
        for t in lib.installed():
            self.translation_box.addItem(t.label, t.id)
        idx = self.translation_box.findData(lib.resolve(wanted))
        self.translation_box.setCurrentIndex(max(idx, 0))
        self.translation_box.blockSignals(False)

    def _on_translation_pick(self, idx: int) -> None:
        tid = self.translation_box.itemData(idx)
        if not tid or tid == self.settings.bible_translation:
            return
        self.settings.bible_translation = tid
        self.settings.clean()
        self.refresh()
        self._fill_chapters()          # chapter/verse menus follow the chosen translation
        self._refresh_yoruba_advisory()

    def _live_detection_on(self) -> bool:
        live = self.live
        return bool(live is not None and getattr(live, "capture", None) is not None)

    def _refresh_yoruba_advisory(self) -> None:
        from .model_advice import YORUBA_ADVISORY, should_show_yoruba_advisory
        if not hasattr(self, "yoruba_note"):
            return
        show = should_show_yoruba_advisory(self.settings.bible_translation, self._live_detection_on(),
                                           self.settings.yoruba_advisory_dismissed)
        self.yoruba_note_text.setText(YORUBA_ADVISORY)
        self.yoruba_note.setVisible(show)

    def _dismiss_yoruba_advisory(self) -> None:
        self.settings.yoruba_advisory_dismissed = True
        self.settings.clean()
        self.yoruba_note.hide()
        self._save_settings()

    def _in_selected_translation(self, c: Candidate) -> Candidate:
        """Same verse, text in the operator's chosen translation (falls back to the candidate's own text)."""
        tid = self.settings.bible_translation
        if not tid or c.translation == tid:
            return c
        text, used = self._bible_library().get_or_default(tid, c.book_id, c.chapter, c.verse)
        if used and text:
            c.translation = used
            c.text = text
            c.edited_text = None
        return c

    def _record_media_history(self, item) -> None:
        """Media projection: name + kind (image, video, audio, ...)."""
        kind = str(getattr(item, "kind", "") or getattr(item, "media_type", "") or "media")
        self._record_history("media", ref=kind, title=str(getattr(item, "name", "") or getattr(item, "title", "") or ""))

    def _record_sermon_history(self, info, church: str = "") -> None:
        """Sermon projection: title + speaker."""
        if info is None:
            return
        self._record_history("sermon", title=str(getattr(info, "title", "") or ""),
                             ref=str(getattr(info, "speaker", "") or church or ""))

    def _record_song_history(self, title: str, section: str = "") -> None:
        """Song slide projection: title + slide section (e.g. Verse 2, Chorus)."""
        self._record_history("song", title=str(title or ""), ref=str(section or ""))

    def _record_history(self, kind: str, ref: str = "", title: str = "", text: str = "") -> None:
        try:
            if getattr(self, "_history", None) is None:
                from .history import ServiceHistory
                self._history = ServiceHistory()
            self._history.record(kind, ref=ref, title=title, text=text)
        except OSError:
            pass   # history is best-effort; never block a projection

    # --- update check (background thread, offline-safe) ------------------------------------
    def _check_updates(self, done) -> None:
        from .updates import start_background_check
        start_background_check(done)

    def _on_startup_update(self, result) -> None:
        # only surface it when there is something to say; offline at startup stays silent
        if result.kind == "update" and getattr(self, "settings_page", None) is not None:
            self.settings_page._update_result.emit(result)

    def _open_output_for_project(self) -> None:
        """An explicit Project click opens the output (the one shared window) if it is hidden.

        Skipped while blanked: a blank click must not pop the projection window up.
        """
        if not self.output.on and not self.queue.blank:
            self.output.set(True)
            self._apply_output_state()

    def _show_on_output(self, c: Candidate) -> None:
        self._cursor = (c.book_id, c.chapter, c.verse)
        self._kind = "verse"
        c = self._in_selected_translation(c)
        self._record_history("verse", ref=f"{c.reference} ({c.translation})", text=c.display_text)
        self._media_live = None
        self._song_pending = None
        self._open_output_for_project()
        self.projection.show_theme(self.theme)
        self.projection.show_verse(c)
        self._update_media_controls()
        self._update_shared_preview()

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
        elif self._kind == "media" and self._media_live is not None:
            self.projection.show_media(self._media_live, loop=self.media_loop.isChecked())
        elif self.queue.live:
            self.projection.show_verse(self.queue.live)
        self._update_shared_preview()

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

    # --- Media tab ---
    def _build_media_tab(self) -> QWidget:
        page = QWidget()
        self._media_page = page
        root = QHBoxLayout(page)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(8)
        # the library only: the live preview is the one shared panel on the right
        root.addWidget(self._build_media_library_panel(), 1)
        return page

    def _build_media_library_panel(self) -> QFrame:
        frame, lay = self._panel("Media Library", "")
        self.media_badge = _label("0 items", "badge")
        frame.layout().itemAt(0).layout().insertWidget(1, self.media_badge)
        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.media_search = QLineEdit()
        self.media_search.setPlaceholderText("Search media by name")
        self.media_search.textChanged.connect(self._refresh_media_grid)
        self.media_filter = QComboBox()
        self.media_filter.addItem("All", "all")
        self.media_filter.addItem("Images", "images")
        self.media_filter.addItem("Videos", "videos")
        self.media_filter.currentIndexChanged.connect(self._refresh_media_grid)
        add_btn = QPushButton("Add media")
        add_btn.setObjectName("primary")
        add_btn.setToolTip("Copy images or videos into the media folder")
        add_btn.clicked.connect(self.import_media)
        self.media_remove_btn = QPushButton("Remove")
        self.media_remove_btn.setObjectName("danger")
        self.media_remove_btn.setToolTip("Delete the selected file from the media folder")
        self.media_remove_btn.setEnabled(False)
        self.media_remove_btn.clicked.connect(self._on_media_remove)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setToolTip("Rescan the media folder")
        refresh_btn.clicked.connect(self.rescan_media)
        bar.addWidget(self.media_search, 1)
        for w in (self.media_filter, add_btn, self.media_remove_btn, refresh_btn):
            bar.addWidget(w)
        lay.addLayout(bar)
        self.media_empty = self._build_media_empty_state()
        self.media_list = QListWidget()
        self.media_list.setObjectName("mediaGrid")
        self.media_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.media_list.setIconSize(QSize(160, 90))        # matches the 160px cached thumbnails (no upscale)
        self.media_list.setGridSize(QSize(184, 150))       # fixed cells: thumb + name + type label
        self.media_list.setSpacing(8)
        self.media_list.setUniformItemSizes(True)
        self.media_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.media_list.setMovement(QListWidget.Movement.Static)
        self.media_list.setWordWrap(True)
        self.media_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.media_list.currentRowChanged.connect(lambda _r: self._update_media_preview())
        self.media_list.itemDoubleClicked.connect(lambda _it: self.project_selected_media())
        self.media_stack = QStackedWidget()
        self.media_stack.addWidget(self.media_empty)
        self.media_stack.addWidget(self.media_list)
        lay.addWidget(self.media_stack, 1)
        self.media_status = QLabel("")
        self.media_status.setObjectName("sub")
        lay.addWidget(self.media_status)
        ctrl = QHBoxLayout()
        ctrl.setSpacing(8)
        self.media_project_btn = QPushButton("Project")
        self.media_project_btn.setObjectName("primary")
        self.media_project_btn.setToolTip("Project the selected media (double-click in the grid also works)")
        self.media_project_btn.clicked.connect(self.project_selected_media)
        self.media_pause = QPushButton("Pause video")
        self.media_pause.clicked.connect(self._on_media_pause)
        self.media_restart = QPushButton("Restart video")
        self.media_restart.clicked.connect(self._on_media_restart)
        self.media_loop = QCheckBox("Loop video")
        self.media_loop.setToolTip("Replay a projected video from the start when it ends")
        self.media_loop.toggled.connect(self._on_media_loop)
        for w in (self.media_project_btn, self.media_pause, self.media_restart, self.media_loop):
            ctrl.addWidget(w)
        ctrl.addStretch(1)
        lay.addLayout(ctrl)
        return frame

    def _build_media_empty_state(self) -> QFrame:
        f = QFrame()
        v = QVBoxLayout(f)
        v.setContentsMargins(8, 18, 8, 18)
        v.setSpacing(6)
        icon = _label("\U0001F5BC", "mediaEmptyIcon")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint = _label("No media yet \u2014 Add media to get started", "emptyHint", wrap=True)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        add_btn = QPushButton("Add media")
        add_btn.setObjectName("primary")
        add_btn.clicked.connect(self.import_media)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(add_btn)
        row.addStretch(1)
        v.addStretch(1)
        v.addWidget(icon)
        v.addWidget(hint)
        v.addLayout(row)
        v.addStretch(1)
        f.icon = icon
        f.hint = hint
        return f

    def _set_media_folder(self, folder: str) -> None:
        self.media = MediaLibrary(folder)
        self.media.load_cached()
        self.rescan_media()

    def _media_folder_str(self) -> str:
        return str(self.media.folder)

    def load_media_cache(self) -> None:
        """Show the last scan at startup without rescanning (fast)."""
        self.media.load_cached()
        self._refresh_media_grid()

    def rescan_media(self) -> None:
        self.media.rescan()
        self._refresh_media_grid()
        self.media_status.setText(f"Scanned {self._media_folder_str()}: {len(self.media.items)} item(s).")

    def import_media(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Import images or videos", "",
            "Media (*.png *.jpg *.jpeg *.webp *.gif *.mp4 *.mkv *.webm *.mov);;All files (*)")
        if not paths:
            return
        copied, skipped = self.media.import_files(paths)
        self.media.rescan()
        self._refresh_media_grid()
        msg = f"Imported {len(copied)} file(s)."
        if skipped:
            msg += f" Skipped (not images or videos): {', '.join(skipped)}."
        self.media_status.setText(msg)

    def _refresh_media_grid(self) -> None:
        if not hasattr(self, "media_stack"):
            return
        kind = self.media_filter.currentData()
        text = self.media_search.text()
        shown = filter_items(self.media.items, text, kind)
        self._media_items = shown
        keep = self._current_media_path()
        self.media_list.blockSignals(True)
        self.media_list.clear()
        from PyQt6.QtGui import QIcon, QPixmap
        for it in shown:
            label = f"{_cell_name(it.name)}\n{it.type_label}"
            if it.is_video:
                label += f" \u00b7 {it.duration_label()}"
            row = QListWidgetItem(label)
            row.setToolTip(Path(it.path).name)
            row.setData(Qt.ItemDataRole.UserRole, it.path)
            pix = QPixmap(it.thumb) if it.thumb else QPixmap()
            if not pix.isNull():
                row.setIcon(QIcon(pix))
            self.media_list.addItem(row)
            if it.path == keep:
                self.media_list.setCurrentRow(self.media_list.count() - 1)
        self.media_list.blockSignals(False)
        total = len(self.media.items)
        if len(shown) != total:
            self.media_badge.setText(f"{len(shown)} of {total} items")
        else:
            self.media_badge.setText(f"{total} item" + ("" if total == 1 else "s"))
        if not self.media.items:
            self.media_empty.hint.setText("No media yet \u2014 Add media to get started")
            self.media_stack.setCurrentWidget(self.media_empty)
        elif not shown:
            self.media_empty.hint.setText("No media matches this search or filter")
            self.media_stack.setCurrentWidget(self.media_empty)
        else:
            self.media_stack.setCurrentWidget(self.media_list)
        self._update_media_preview()

    def _current_media_path(self):
        row = self.media_list.currentItem() if hasattr(self, "media_list") else None
        return row.data(Qt.ItemDataRole.UserRole) if row is not None else None

    def _update_media_preview(self) -> None:
        """Keep Remove and the media controls in step with the grid selection (the preview is the shared panel)."""
        if not hasattr(self, "media_remove_btn"):
            return
        it = self._selected_media_item()
        self.media_remove_btn.setEnabled(it is not None)
        self._update_media_controls()

    def _on_media_remove(self) -> None:
        it = self._selected_media_item()
        if it is None:
            self.media_status.setText("Select a media item to remove.")
            return
        answer = QMessageBox.question(
            self, "Remove media",
            f"Delete \"{Path(it.path).name}\" from the media folder? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        on_output = self._kind == "media" and self._media_live is not None and self._media_live.path == it.path
        if not self.media.remove_item(it):
            self.media_status.setText(f"Could not remove {Path(it.path).name}. Is it open in another app?")
            return
        if on_output:
            # the shared output stops showing the deleted file (same as a blank)
            self._media_live = None
            self._kind = "verse" if self.queue.live else None
            self._render_output()
            if self._kind is None:
                self.projection.show_blank()
        self.rescan_media()
        self.media_status.setText(f"Removed {Path(it.path).name}.")
        self._update_media_controls()
        self._update_shared_preview()

    def _selected_media_item(self):
        row = self.media_list.currentItem()
        if row is None:
            return None
        path = row.data(Qt.ItemDataRole.UserRole)
        for it in self._media_items:
            if it.path == path:
                return it
        return None

    def project_selected_media(self) -> None:
        """Project straight away (no approval for media). Respects LIVE: while the output is off,
        it is remembered and shown when the output turns on."""
        it = self._selected_media_item()
        if it is None:
            self.media_status.setText("Select a media item first.")
            return
        self._project_media(it)

    def _project_media(self, it) -> None:
        self._media_live = it
        self._kind = "media"
        self._song_pending = None
        self._song_live = None
        self._sermon_live = None
        self.media_status.setText(f"Projected: {it.name} ({it.type_label.lower()})")
        self._open_output_for_project()
        if self.output.on and not self.queue.blank:
            self.projection.show_media(it, loop=self.media_loop.isChecked())
            self._record_media_history(it)
        self._update_media_controls()
        self.refresh()

    def _on_media_loop(self, on: bool) -> None:
        self.projection.set_video_loop(on)

    def _media_controls_state(self) -> dict:
        from .output_state import media_controls_state
        kind = self._media_live.kind if (self._kind == "media" and self._media_live is not None) else None
        projected = kind == "video" and self.projection.has_playing_video()
        return media_controls_state(kind, self.output.on, self.queue.blank, projected,
                                    self.projection.is_video_paused())

    def _update_media_controls(self) -> None:
        if not hasattr(self, "media_pause"):
            return
        st = self._media_controls_state()
        self.media_pause.setText(st["pause_text"])
        self.media_pause.setToolTip(st["pause_tip"])
        self.media_pause.setEnabled(st["enabled"])
        self.media_restart.setToolTip(st["restart_tip"])
        self.media_restart.setEnabled(st["enabled"])

    def _on_media_pause(self) -> None:
        self.projection.toggle_video_pause()
        self._update_media_controls()

    def _on_media_restart(self) -> None:
        self.projection.restart_video()
        self._update_media_controls()

    def toggle_blank(self) -> None:
        self.queue.set_blank(not self.queue.blank)
        self._render_output()
        self._update_media_controls()
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
        # Auto-approve skips the operator, so when it is on the status bar says so in amber.
        _set_name(self.status_auto, "footerWarn" if on else "footer")

    def _on_setting_changed(self, key: str) -> None:
        """Apply one changed setting to the running app, then save the file."""
        s = self.settings
        if key == "bible_translation":
            # a translation was imported or removed in Settings > Bible: rebuild the library and dropdown
            self._bible = None
            self._fill_translation_box()
            self._refresh_yoruba_advisory()
        elif key == "paraphrase_threshold" and self.pipeline is not None and hasattr(self.pipeline, "detector"):
            self.pipeline.detector.paraphrase_threshold = s.paraphrase_threshold
        elif key == "dedupe_minutes":
            self.queue.set_dedupe_seconds(s.dedupe_minutes * 60.0)
        elif key == "auto_approve":
            self.queue.set_auto_approve(s.auto_approve)
            self._apply_auto_label()
        elif key == "output_display" and hasattr(self, "display_box") and self.display_box.count() > s.output_display:
            self.display_box.setCurrentIndex(s.output_display)
        elif key in ("model_size", "compute_type", "cpu_threads") and self.live is not None:
            cfg = getattr(self.live.transcriber, "configure", None)
            if callable(cfg):   # a changed model/compute/threads takes effect on the next mic start
                cfg(model_size=s.model_size, compute_type=s.compute_type, cpu_threads=s.cpu_threads)
        elif key == "noise_gate_db" and self.live is not None and getattr(self.live, "capture", None) is not None:
            self.live.capture.set_gate_threshold(s.noise_gate_db)
        elif key == "input_gain_db":
            self._apply_gain(s.input_gain_db)
        elif key == "input_device_name":
            self._select_device_by_name(s.input_device_name)
        elif key == "media_folder":
            self._set_media_folder(s.media_folder or DEFAULT_MEDIA_FOLDER)
        elif key == "ffmpeg_dir":
            from . import fftools
            fftools.set_configured_dir(s.ffmpeg_dir)
            if hasattr(self, "settings_page") and self.settings_page is not None:
                self.settings_page.refresh_ffmpeg_status()
        self._save_settings()

    def _on_gain_changed(self, value: float) -> None:
        """The gain box was changed by the operator: apply it to the running capture now, remember it."""
        self.settings.input_gain_db = float(value)
        self._apply_gain(value)
        self._gain_save_timer.start()            # restarts the 600 ms wait while the value keeps changing

    def _apply_gain(self, value: float) -> None:
        """Set the gain on the open capture (no restart needed) and make the box show it."""
        cap = getattr(self.live, "capture", None) if self.live is not None else None
        if cap is not None:
            cap.set_gain(float(value))
        if abs(self.gain.value() - float(value)) > 1e-9:
            self.gain.blockSignals(True)
            self.gain.setValue(float(value))
            self.gain.blockSignals(False)

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
        h.addAction("Service history...", self._show_history)
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
                                 lambda _checked=False, idx=i: self.display_box.setCurrentIndex(idx))
            act.setCheckable(True)
            act.setChecked(i == self.display_box.currentIndex())

    def _open_settings_output(self) -> None:
        self._tabs.setCurrentIndex(self._settings_index)
        self.settings_page.select_section("Output")

    def _show_history(self) -> None:
        """Today's service and past days, with copy/export to text. Read-only."""
        from .history import ServiceHistory
        hist = getattr(self, "_history", None) or ServiceHistory()
        self._history = hist
        box = QDialog(self)
        box.setWindowTitle("Service history")
        box.resize(640, 460)
        lay = QVBoxLayout(box)
        day_box = QComboBox()
        days = hist.days()
        today = date.today().isoformat()
        if today not in days:
            days.insert(0, today)
        day_box.addItems(days)
        lay.addWidget(day_box)
        view = QPlainTextEdit()
        view.setReadOnly(True)
        lay.addWidget(view, 1)
        row = QHBoxLayout()
        btn_copy = QPushButton("Copy to clipboard")
        btn_export = QPushButton("Export to text file...")
        btn_close = QPushButton("Close")
        for b in (btn_copy, btn_export, btn_close):
            row.addWidget(b)
        lay.addLayout(row)

        def refresh(_idx=None):
            view.setPlainText(hist.to_text(day_box.currentText()))
        def copy():
            QApplication.clipboard().setText(view.toPlainText())
        def export():
            path, _ = QFileDialog.getSaveFileName(box, "Export service history", f"service-{day_box.currentText()}.txt", "Text (*.txt)")
            if path:
                try:
                    hist.export_text(path, day_box.currentText())
                except OSError as exc:
                    QMessageBox.warning(box, "Not exported", str(exc))
        day_box.currentIndexChanged.connect(refresh)
        btn_copy.clicked.connect(copy)
        btn_export.clicked.connect(export)
        btn_close.clicked.connect(box.accept)
        refresh()
        box.exec()

    def _show_setup_docs(self) -> None:
        QMessageBox.information(self, "Setup docs",
                                "The setup guide is the README.md in the RevelateTW project folder.")

    def _show_about(self) -> None:
        box = QMessageBox(self)
        box.setWindowTitle("About RevelateTW")
        box.setText(f"RevelateTW version {APP_VERSION}.")
        logo = _logo_pixmap(96)
        if logo is not None:
            box.setIconPixmap(logo)
        box.exec()

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
            self._present_output()
        else:
            self.projection.hide()                     # media stays selected in _media_live; re-shown on ON
        self._update_media_controls()

    # --- display picker -----------------------------------------------------------------------
    def _populate_displays(self, keep: int | None = None) -> None:
        """keep=None (startup): the second monitor in extended mode, else the first. A rescan keeps the choice."""
        self._displays: list[DisplayInfo] = list_displays()
        pick = default_output_index(self._displays) if keep is None else keep
        self.display_box.blockSignals(True)
        self.display_box.clear()
        for d in self._displays:
            self.display_box.addItem(d.label)
        if not self._displays:
            self.display_box.addItem("No display found")
        self.display_box.setCurrentIndex(min(max(pick, 0), max(len(self._displays) - 1, 0)))
        self.display_box.blockSignals(False)
        self._on_display_chosen(self.display_box.currentIndex())

    def _on_display_chosen(self, idx: int) -> None:
        if not getattr(self, "_displays", None) or idx < 0 or idx >= len(self._displays):
            return
        d = self._displays[idx]
        screens = QGuiApplication.screens()
        screen = screens[idx] if idx < len(screens) else None
        self.projection.move_to_display(QRect(d.x, d.y, d.width, d.height), screen)
        self.display_box.setToolTip(f"Monitor for the live output ({mode_note(self._displays)}).")
        if self.output.on:
            self._present_output()

    def _present_output(self, explicit: bool = False) -> None:
        """Where the output window goes when the output is ON.
        Automatic (explicit=False): fullscreen only on a second monitor in extended mode, otherwise minimized
        so it never covers the operator's screen. explicit=True (menu pick): fullscreen on the chosen monitor."""
        displays = getattr(self, "_displays", None) or []
        idx = self.display_box.currentIndex()
        if explicit or should_fullscreen(displays, idx):
            self.projection.present_fullscreen()
        else:
            self.projection.present_minimized()

    def _output_menu(self) -> "QMenu":
        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self)
        displays = list(getattr(self, "_displays", None) or [])
        head = menu.addAction(f"Mode: {mode_note(displays)}")
        head.setEnabled(False)
        cur = self.display_box.currentIndex()
        for i, d in enumerate(displays):
            tag = " (active)" if i == cur else ""
            prim = ", primary" if d.primary else ""
            act = menu.addAction(f"Show on Monitor {i + 1}{tag}  [{d.width}x{d.height}{prim}]",
                                 lambda _checked=False, idx=i: self._output_on_monitor(idx))
            act.setCheckable(True)
            act.setChecked(i == cur)
        if not displays:
            none = menu.addAction("No monitor found")
            none.setEnabled(False)
        menu.addSeparator()
        mini = menu.addAction("Minimize output window", self._minimize_output)
        mini.setEnabled(self.output.on)
        return menu

    def _show_output_menu(self, pos) -> None:
        self._output_menu().exec(pos)   # monitor list as last scanned (Rescan refreshes it)

    def _output_on_monitor(self, idx: int) -> None:
        """Menu pick: that monitor carries the output, fullscreen there, and the output switches ON."""
        self.display_box.setCurrentIndex(idx)            # moves the output window to that monitor
        if not self.output.on:
            self.output.set(True)
            self._apply_output_state()
        self._present_output(explicit=True)              # a deliberate pick goes fullscreen
        self.refresh()

    def _minimize_output(self) -> None:
        if self.output.on:
            self.projection.present_minimized()

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

    def _song_context_menu(self, pos) -> None:
        from PyQt6.QtWidgets import QMenu
        row = self.song_list.indexAt(pos).row()
        if row < 0 or row >= len(self._songs):
            return
        menu = QMenu(self)
        act = menu.addAction("Export this song")
        if menu.exec(self.song_list.viewport().mapToGlobal(pos)) == act:
            self._export_song(self._songs[row])

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
        from .song_import_dialog import ImportSongsDialog
        dlg = ImportSongsDialog(self, self.library)
        dlg.exec()
        if dlg.saved_count:
            self._fill_song_list()
            self.editor_status.setText(dlg.result_message.split("\n")[0])

    def _export_song(self, song: Optional[Song] = None) -> None:
        """Export one song (row button / context menu) or the whole library when song is None."""
        from . import song_io
        if song is None:
            songs = self.library.load_all()
            if not songs:
                self.editor_status.setText("No songs to export yet.")
                return
            default = f"revelate_songs_{len(songs)}.rtsong"
            path, _ = QFileDialog.getSaveFileName(self, "Export all songs", default, "RevelateTW songs (*.rtsong)")
            if not path:
                return
            try:
                song_io.export_songs(songs, path)
                self.editor_status.setText(f"Exported {len(songs)} songs to {Path(path).name}")
            except Exception as exc:
                self.editor_status.setText(f"Export failed: {exc}")
            return
        default = song_io.safe_filename(song.title) + song_io.EXTENSION
        path, _ = QFileDialog.getSaveFileName(self, "Export song", default, "RevelateTW song (*.rtsong)")
        if not path:
            return
        try:
            song_io.export_song(song, path)
            self.editor_status.setText(f"Exported {song.title} to {Path(path).name}")
        except Exception as exc:
            self.editor_status.setText(f"Export failed: {exc}")

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
                self._record_song_history(song.title, song.slides[i].label)
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
        self._media_live = None
        self.song_pending_label.setText("")
        self.song_now.setText(f"Projected: {song.title}  \u00b7  {song.slides[row].label}")
        self._open_output_for_project()
        if self.output.on and not self.queue.blank:
            self.projection.show_song_slide(song.slides[row], song, row, len(song.slides))
            self._record_song_history(song.title, song.slides[row].label)
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
        self._media_live = None
        self._song_pending = None
        self._open_output_for_project()
        if self.output.on and not self.queue.blank:
            self.projection.show_sermon(info)
            self._record_sermon_history(info)
        self._update_shared_preview()
        self.sermon_note.setText("Sermon info on screen." if not info.reference else
                                 f"Sermon info on screen. Reference: {info.reference}")

    def clear_sermon_slide(self) -> None:
        self._sermon_live = None
        if self._kind == "sermon":
            self._kind = "verse" if self.queue.live else None
            self._render_output()
        self._update_shared_preview()
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

    def _on_setup_toggle(self, on: bool) -> None:
        """Show or hide the Audio & display section. While it is collapsed, a one-line summary stands in."""
        self.setup_box.setVisible(on)
        self.setup_summary.setVisible(not on)
        self.btn_setup.setText("Audio & display \u25be" if on else "Audio & display \u25b8")

    def _update_setup_summary(self) -> None:
        """One line saying which input and display are in use. A problem is marked with a warning sign,
        and the section opens by itself the first time one appears so the operator sees the message."""
        status = self.source_status.text().strip()
        normal = (not status or status.startswith(("Listening", "Dev text feed"))
                  or (self._dev and self.live is None))      # --dev without audio is by design, not a fault
        parts = [status or "Audio input not started"]
        display = self.display_box.currentText().strip()
        if display:
            parts.append(display)
        text = ("\u26a0 " if not normal else "") + "  \u00b7  ".join(parts)
        if self.setup_summary.text() != text:
            self.setup_summary.setText(text)
        if not normal and not self._setup_autoexpanded:
            self._setup_autoexpanded = True
            self.btn_setup.setChecked(True)

    def _update_checklist(self) -> None:
        """Show the "Getting ready" card until the first words are transcribed, and keep it current."""
        history = getattr(self.pipeline, "history", None)
        waiting = not history
        self.checklist.setVisible(waiting)
        if not waiting:
            return
        peak = None
        if self.live is not None:
            peak = self.live.meter().get("peak_db")
        elif self._audio_meter:
            peak = self._audio_meter().get("peak_db")
        if self._mic_on and heard_sound(peak):
            self._heard_sound = True             # latched, so a pause in speech never un-ticks it
        dev_feed = self._dev and self.btn_source_dev.isChecked()
        checks = preflight(
            live_available=self.live is not None and not dev_feed, dev=self._dev, mic_on=self._mic_on,
            mic_name=self._mic_dev.name if self._mic_dev is not None else "", devices_found=bool(self._devices),
            capture_error=self._capture_error, sound_heard=self._heard_sound,
            displays=getattr(self, "_displays", []), target_display=self.display_box.currentIndex(),
            output_on=self.output.on)
        sig = tuple(checks)
        if sig == self._check_sig:
            return
        self._check_sig = sig
        self.check_title.setText(headline(checks))
        while self.check_rows.count():
            w = self.check_rows.takeAt(0).widget()
            if w is not None:
                w.hide()
                w.setParent(None)             # detach now: deleteLater alone keeps it on the card for one more event-loop turn
                w.deleteLater()
        icons = {OK: ("\u2713", "checkOk"), INFO: ("\u2022", "checkInfo")}
        for c in checks:
            glyph, name = icons.get(c.state, ("!", "checkWarn"))
            row = QWidget()
            hl = QHBoxLayout(row)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.setSpacing(SPACE.md)
            icon = _label(glyph, name)
            icon.setFixedWidth(18)
            icon.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
            hl.addWidget(icon)
            hl.addWidget(_label(c.text, "checkText", wrap=True), 1)
            if c.action:
                btn = QPushButton(c.action_label)
                btn.setObjectName("subtle")
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.clicked.connect(lambda _checked=False, a=c.action: self._on_check_action(a))
                hl.addWidget(btn)
            self.check_rows.addWidget(row)

    def _on_check_action(self, action: str) -> None:
        if action == ACTION_AUDIO_SETUP:
            self.btn_setup.setChecked(True)
        elif action == ACTION_TOGGLE_OUTPUT:
            self.toggle_output()

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

    def _menu_store(self):
        """Verse store for the operator's chosen translation (drives the chapter/verse menus).

        Falls back to the detector's store when the chosen translation has no pack.
        """
        tid = self.settings.bible_translation
        try:
            store = self._bible_library().store(tid) if tid else None
        except Exception:
            store = None
        return store if store is not None else self._store

    def _fill_chapters(self) -> None:
        store = self._menu_store()
        if store is None:
            return
        from .navigation import manual_chapters
        self.man_chapter.blockSignals(True)
        self.man_chapter.clear()
        bid = self.man_book.currentData()
        if bid is not None:
            for ch in manual_chapters(store, bid):
                self.man_chapter.addItem(str(ch), ch)
        self.man_chapter.blockSignals(False)
        self._fill_verses()

    def _fill_verses(self) -> None:
        store = self._menu_store()
        if store is None:
            return
        from .navigation import manual_verses
        self.man_verse.blockSignals(True)
        self.man_verse.clear()
        bid, ch = self.man_book.currentData(), self.man_chapter.currentData()
        if bid is not None and ch is not None:
            for v in manual_verses(store, bid, ch):
                self.man_verse.addItem(str(v), v)
        self.man_verse.blockSignals(False)

    def _project_manual(self) -> None:
        store = self._menu_store()
        if store is None:
            return
        from .navigation import _verse_sugg, candidate_from_suggestion
        bid, ch, v = self.man_book.currentData(), self.man_chapter.currentData(), self.man_verse.currentData()
        if None in (bid, ch, v):
            return
        c = candidate_from_suggestion(store, _verse_sugg(store, bid, ch, v), "manual", 100, "manual pick")
        c = self._in_selected_translation(c)
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

    def showEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._timer.start()              # idle timer runs only while visible
        self.sys_mon.start_sampling()    # PC sampler: visible only
        super().showEvent(event)
        if not getattr(self, "_startup_mic_done", False):
            self._startup_mic_done = True
            try:
                self._start_default_mic()     # first show: go live on the default input, no click needed
            except Exception as exc:          # never let a mic problem break the window
                _log.error("startup mic failed: %s", exc)
                self.source_status.setText(f"Mic failed at startup: {exc}")
        self._refresh_header_state()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self._gain_save_timer.isActive():     # a gain change is still waiting to be written
            self._gain_save_timer.stop()
            self._save_settings()
        super().closeEvent(event)

    def hideEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._timer.stop()               # hidden operator window: no refresh, no clock work
        self._header_timer.stop()
        self.audio_mon.set_active(False)
        self.sys_mon.stop_sampling()
        super().hideEvent(event)

    # --- header monitoring (main thread only) ---------------------------------------------
    def _detection_on(self) -> bool:
        return bool(self._mic_on and self.isVisible())

    def _refresh_header_state(self) -> None:
        """Start or stop the header timer and the audio tap to match visibility + detection."""
        on = self._detection_on()
        self.audio_mon.set_active(on)
        if on:
            if not self._header_timer.isActive():
                self._header_timer.start()
            self.wave.set_load_band(self.sys_chip.cpu_band())
        else:
            self._header_timer.stop()
            if not self._devices:            # no audio input device at all
                self.wave.set_no_mic()
            else:                            # device exists, detection off: flat dimmed strip
                self.wave.set_detection_off()

    def _tick_header(self) -> None:
        if not self._detection_on():     # defensive: stop if state changed without a refresh
            self._refresh_header_state()
            return
        if self._check_capture():        # stalled or failed capture was moved to the next input
            return
        self.wave.push(self.audio_mon.level, self.audio_mon.drain_peak(), self.audio_mon.signal_present)

    def _on_sys_sampled(self, cpu: float, ram: float) -> None:
        self.sys_chip.set_values(cpu, ram)
        self.wave.set_load_band(band_for(cpu))

    def refresh(self) -> None:
        self._refresh_yoruba_advisory()
        pending = self.queue.pending()
        self.list.blockSignals(True)
        self.list.clear()
        for c in pending:
            item = QListWidgetItem(f"{c.reference}   {c.confidence}%  {c.match_type}")
            item.setSizeHint(QSize(0, SPACE.row_height))
            self.list.addItem(item)
        if pending:
            self.list.setCurrentRow(min(max(self.queue.selected, 0), len(pending) - 1))
        self.list.blockSignals(False)
        # gold outline on the first card = next to project
        for i in range(self.list.count()):   # first card = next to project: gold text, tinted row
            it = self.list.item(i)
            if i == 0:
                it.setForeground(QColor(COLORS.accent))
                it.setBackground(QColor(COLORS.selected_bg))
            else:
                it.setForeground(QColor(COLORS.text))
                it.setBackground(QColor(COLORS.surface_input))
        self.queue_badge.setText(f"{len(pending)} pending")
        self._show_selected()
        self._refresh_transcript()

        live = self.queue.live
        st = self.queue.state
        # The pill shows the output switch (ON/OFF), not the queue state; blank/idle shows in the status bar.
        self.live_pill.setVisible(True)
        self._update_shared_preview()
        if self.output.on:
            self.footer_proj.setText({"live": "Projecting", "blank": "Blanked", "idle": "Idle"}[st])
            _set_name(self.footer_proj, "footerOk" if st == "live" else "footer")
        else:
            # the output switch is off, so nothing reaches the projector whatever the queue says
            self.footer_proj.setText("Output off (projector window hidden)")
            _set_name(self.footer_proj, "footerWarn")
        self.btn_prev.setEnabled(live is not None and self._has_neighbour(-1))
        self.btn_next.setEnabled(live is not None and self._has_neighbour(+1))
        if live is not None and self._store is not None:
            nxt = self._neighbour_text(+1)
            self.next_label.setText(f"Next in chapter: {nxt}" if nxt else "Last verse of this chapter")
        else:
            self.next_label.setText("")

        cleared = self.queue.cleared_count()
        self.status_cleared.setText(f"Queue cleared {cleared}")
        if self.pipeline is not None:
            ms = self.pipeline.last_latency_ms
            self.status_latency.setText(f"Latency {ms / 1000:.1f}s")
        self.timer_label.setText(time.strftime("%H:%M:%S", time.gmtime(time.time() - self._started)))
        if self.live is not None:
            m = self.live.meter()
            self.meter.setText(f"Peak {m['peak_db']:.0f} dB   RMS {m['rms_db']:.0f} dB")
        elif self._audio_meter:
            m = self._audio_meter()
            self.meter.setText(f"Peak {m['peak_db']:.0f} dB   RMS {m['rms_db']:.0f} dB")
        self._update_setup_summary()
        self._update_checklist()

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
            settings_path: Optional[str] = None, dev: bool = False, splash=None):
    """Start the Qt event loop. pipeline receives dev-feed text; live (optional) runs the mic loop.

    projection_screen picks the starting monitor for the live output (the display box can change it).
    splash (optional) is closed as soon as the operator window is shown.
    """
    app = QApplication.instance() or QApplication([])
    icon_path = _LOGO_PATH if _LOGO_PATH.is_file() else None
    if icon_path is not None:
        from PyQt6.QtGui import QIcon
        app.setWindowIcon(QIcon(str(icon_path)))
    projection = ProjectionWindow()
    projection.show_theme(theme)
    op = OperatorWindow(queue, theme, projection, pipeline=pipeline, live=live, songs_dir=songs_dir,
                        settings=settings, settings_path=settings_path, dev=dev)
    if icon_path is not None:
        op.setWindowIcon(app.windowIcon())
    if projection_screen is not None:               # None = automatic (second monitor in extended mode)
        op.display_box.setCurrentIndex(projection_screen)
    projection.context_menu_requested.connect(op._show_output_menu)
    op.live_pill.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    op.live_pill.customContextMenuRequested.connect(op._show_output_menu)
    op.display_box.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    op.display_box.customContextMenuRequested.connect(op._show_output_menu)
    op.shared_preview.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    op.shared_preview.customContextMenuRequested.connect(op._show_output_menu)
    op.resize(1280, 800)
    projection.hide()                               # startup: output is OFF, so the output window never appears
    op.show()
    if splash is not None:
        from .splash import finish_splash
        finish_splash(splash)
    # The projection window stays hidden at launch (output starts OFF); it opens on the first project.
    return app.exec()
