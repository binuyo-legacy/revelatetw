"""Startup splash: the designed card (assets/splash.png), falling back to assets/logo.png, else none.

The pixmap building and the fallback chain are plain functions so they can be tested headless.
The window itself is a frameless, always-on-top QWidget with a thin gold sweep bar and a
'Loading...' line. Call finish_splash() once the operator window is on screen.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Optional

from .paths import bundled

ASSETS_DIR = bundled("revelatetw", "assets")
SPLASH_PATH = ASSETS_DIR / "splash.png"
LOGO_PATH = ASSETS_DIR / "logo.png"

GOLD = (212, 175, 55)
TRACK = (255, 255, 255, 60)
MAX_WIDTH = 560
BAR_HEIGHT = 4
LOADING_TEXT = "Loading\u2026"


def splash_source(splash_path: Path = SPLASH_PATH, logo_path: Path = LOGO_PATH) -> Optional[Path]:
    """First existing image in the chain: splash.png, then logo.png. None means no splash."""
    for p in (splash_path, logo_path):
        if Path(p).is_file():
            return Path(p)
    return None


def wants_splash(argv=None) -> bool:
    """False when --no-splash is on the command line."""
    import sys
    args = sys.argv[1:] if argv is None else list(argv)
    return "--no-splash" not in args


def build_splash_pixmap(source: Path, width: int = MAX_WIDTH, bar_fraction: float = 0.0):
    """Scaled card with the 'Loading...' line and gold progress strip composited onto a copy.

    Returns a QPixmap, or None if the source cannot be read. bar_fraction (0..1) sets where the
    gold sweep sits (used by tests; the live window animates it).
    """
    from PyQt6.QtCore import Qt, QRectF
    from PyQt6.QtGui import QColor, QFont, QPainter, QPixmap
    src = QPixmap(str(source))
    if src.isNull():
        return None
    if src.width() > width:
        src = src.scaledToWidth(width, Qt.TransformationMode.SmoothTransformation)
    out = QPixmap(src.size())
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.drawPixmap(0, 0, src)
    w, h = out.width(), out.height()
    # Loading line sits just above the strip, bottom centre.
    font = QFont()
    font.setPointSize(9)
    p.setFont(font)
    p.setPen(QColor(40, 40, 40))
    p.drawText(QRectF(0, h - 28 - BAR_HEIGHT, w, 20), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
               LOADING_TEXT)
    # Track and sweep at the very bottom.
    p.fillRect(0, h - BAR_HEIGHT, w, BAR_HEIGHT, QColor(*TRACK))
    seg = max(1, int(w * 0.25))
    x = int((w - seg) * max(0.0, min(1.0, bar_fraction)))
    p.fillRect(x, h - BAR_HEIGHT, seg, BAR_HEIGHT, QColor(*GOLD))
    p.end()
    return out


def make_splash_window(source: Path, parent=None):
    """Frameless, always-on-top, centred splash. Returns (widget) or None if the image is unreadable."""
    from PyQt6.QtCore import Qt, QTimer
    from PyQt6.QtGui import QGuiApplication, QPainter
    from PyQt6.QtWidgets import QWidget

    base = build_splash_pixmap(source, bar_fraction=0.0)
    if base is None:
        return None

    class _SplashWindow(QWidget):
        def __init__(self):
            super().__init__(parent, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                             | Qt.WindowType.SplashScreen)
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            self.setFixedSize(base.size())
            self._phase = 0.0
            self._timer = QTimer(self)
            self._timer.timeout.connect(self._tick)
            self._timer.start(25)
            screen = QGuiApplication.primaryScreen()
            if screen is not None:
                g = screen.availableGeometry()
                self.move(g.center().x() - self.width() // 2, g.center().y() - self.height() // 2)

        def _tick(self):
            self._phase = (self._phase + 0.02) % 1.0
            self.update()

        def paintEvent(self, _event):
            p = QPainter(self)
            p.drawPixmap(0, 0, base)
            # Indeterminate sweep: bounce the gold segment back and forth over the track.
            from PyQt6.QtGui import QColor
            w, h = self.width(), self.height()
            seg = max(1, int(w * 0.25))
            pos = 0.5 - 0.5 * math.cos(self._phase * 2 * math.pi)
            x = int((w - seg) * pos)
            p.fillRect(x, h - BAR_HEIGHT, seg, BAR_HEIGHT, QColor(*GOLD))
            p.end()

    return _SplashWindow()


def start_splash(source: Optional[Path] = None, parent=None):
    """Show the splash if an image exists. Returns the window, or None (no splash, no crash)."""
    src = source if source is not None else splash_source()
    if src is None:
        return None
    from PyQt6.QtGui import QGuiApplication
    if QGuiApplication.instance() is None:   # a QPixmap without an app aborts the process; skip the splash
        return None
    try:
        win = make_splash_window(src, parent)
        if win is None:
            return None
        win.show()
        return win
    except Exception:
        return None


def finish_splash(win) -> None:
    """Close the splash once the operator window is up."""
    if win is None:
        return
    try:
        win._timer.stop()
        win.close()
        win.deleteLater()
    except Exception:
        pass


def app_icon_path() -> Optional[Path]:
    return LOGO_PATH if LOGO_PATH.is_file() else None
