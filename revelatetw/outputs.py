"""Output routing (spec F5).

Routes for feeding OBS / streaming / recording software from the projection output:

  1. Window capture (default, no extra software): the projection window is borderless and
     titled 'RevelateTW output'. In OBS add a 'Window Capture' source and pick it. Works on
     any Windows PC. See SETUP.md.
  2. Virtual camera (optional): VirtualCameraSink sends RGB frames through pyvirtualcam to
     the OBS Virtual Camera driver (free, installed with OBS 26+). Install with
     `pip install pyvirtualcam` and start the virtual camera once in OBS.
  3. NDI: gated. Needs the NDI SDK (licence review, spec section 10). Not shipped.

Spout (GPU texture sharing) is not used; SpoutGL would need a Spout-capable OBS
plugin, and window capture covers the same case without it.

Frames are plain RGB bytes so the Qt widget and any sink share one format.
"""
from __future__ import annotations

import re

from dataclasses import dataclass
from typing import Optional, Protocol

PROJECTION_WINDOW_TITLE = "RevelateTW output"


class OutputSink(Protocol):
    name: str
    def push_frame(self, rgb: bytes, width: int, height: int) -> None: ...
    def close(self) -> None: ...


@dataclass
class ResolutionOption:
    width: int
    height: int
    fps: int = 30


RESOLUTIONS = [ResolutionOption(1920, 1080, 30), ResolutionOption(1280, 720, 30),
               ResolutionOption(1920, 1080, 60)]   # 60 fps on capable hardware only


class NDISink:
    """Gated: spec section 10 requires NDI licence review before this ships."""
    name = "ndi"
    enabled = False  # feature flag

    def push_frame(self, rgb: bytes, width: int, height: int) -> None:
        raise RuntimeError("NDI output is disabled until the licence review is complete. "
                           "Use the OBS window capture route (SETUP.md).")

    def close(self) -> None:
        pass


class VirtualCameraSink:
    """Feeds the OBS Virtual Camera via pyvirtualcam (optional dependency)."""
    name = "virtual_camera"

    def __init__(self, width: int = 1920, height: int = 1080, fps: int = 30):
        import pyvirtualcam  # lazy: raises ImportError if not installed
        self._cam = pyvirtualcam.Camera(width=width, height=height, fps=fps, fmt=pyvirtualcam.PixelFormat.RGB)
        self.width, self.height = width, height

    @property
    def device(self) -> str:
        return self._cam.device

    def push_frame(self, rgb: bytes, width: int, height: int) -> None:
        if (width, height) != (self.width, self.height):
            raise ValueError(f"frame is {width}x{height}, camera is {self.width}x{self.height}")
        self._cam.send(_as_array(rgb, width, height))
        self._cam.sleep_until_next_frame()

    def close(self) -> None:
        self._cam.close()


def _as_array(rgb: bytes, width: int, height: int):
    import numpy as np
    return np.frombuffer(rgb, dtype=np.uint8).reshape(height, width, 3)


def virtual_camera_available() -> bool:
    try:
        import pyvirtualcam  # noqa: F401
        return True
    except ImportError:
        return False


def grab_rgb(widget) -> Optional[tuple[bytes, int, int]]:
    """Render a Qt widget to RGB bytes for a sink. Needs PyQt6 and a running app."""
    from PyQt6.QtGui import QImage
    pix = widget.grab()
    img = pix.toImage().convertToFormat(QImage.Format.Format_RGB888)
    w, h = img.width(), img.height()
    ptr = img.constBits()
    ptr.setsize(img.sizeInBytes())
    # Rows are padded to 4 bytes; strip the padding so the layout is tight width*3.
    stride = img.bytesPerLine()
    raw = bytes(ptr)
    if stride != w * 3:
        raw = b"".join(raw[r * stride:r * stride + w * 3] for r in range(h))
    return raw, w, h


# ---------------------------------------------------------------------------------------
# Projection slide layout (mockups A and B). Pure helpers first: they are tested headless.
# The painter (SlidePainter) only draws what these helpers decide.
# ---------------------------------------------------------------------------------------

from .theme import MIDNIGHT  # noqa: E402  (chip and scrim fill)

SAFE_MARGIN_RATIO = 0.06          # keep text this far from the edges (fraction of width/height)
MIN_FIT_PX = 24                   # never shrink lyrics below this (readability floor)


_GENERIC_LABEL = re.compile(r"slide \d+$", re.IGNORECASE)


def display_section(label: str) -> str:
    """Section name for the output: 'Chorus', 'Verse 2'. Unlabelled 'Slide 3' shows nothing."""
    label = (label or "").strip()
    return "" if not label or _GENERIC_LABEL.fullmatch(label) else label


def chip_text(section: str, index: int, total: int) -> str:
    """'Chorus · 2/8' for the bottom-right chip: section name and slide position in the song.

    index is 0-based (first slide is 1/N). Blank section shows only the position. total < 1 gives ''.
    """
    if total < 1:
        return ""
    pos = f"{min(max(index, 0) + 1, total)}/{total}"
    section = (section or "").strip()
    return f"{section} \u00b7 {pos}" if section else pos


def footer_text(title: str, artist: str = "") -> str:
    """Bottom-left footer: 'Song Title · Artist', or just the title when the artist is blank."""
    title, artist = (title or "").strip(), (artist or "").strip()
    return f"{title} \u00b7 {artist}" if artist and title else title


def fit_font_px(lines: list[str], box_w: int, box_h: int, start_px: int,
                line_height: float = 1.3, measure=None) -> int:
    """Largest font size (<= start_px, >= MIN_FIT_PX) at which the wrapped lines fit the box.

    measure(text, px) -> (width_px, ...) is injected so the logic is testable without Qt;
    the default estimates glyph width from the size (about 0.52em per character).
    Wrapping is done with the same measure, so long lyrics shrink instead of overflowing.
    """
    if box_w <= 0 or box_h <= 0:
        return MIN_FIT_PX
    if measure is None:
        measure = _estimate_measure
    px = max(MIN_FIT_PX, int(start_px))
    while True:
        needed = 0.0
        for line in lines:
            needed += len(wrap_lines(line, box_w, px, measure)) * px * line_height
        if needed <= box_h or px <= MIN_FIT_PX:
            return px
        px = max(MIN_FIT_PX, int(px * 0.92) if px > 40 else px - 2)


def _estimate_measure(text: str, px: int) -> tuple[int, int]:
    return (int(len(text) * px * 0.52), px)


def wrap_lines(text: str, box_w: int, px: int, measure=None) -> list[str]:
    """Greedy word wrap of one line to box_w at font size px. Long single words are split."""
    if measure is None:
        measure = _estimate_measure
    words = (text or "").split()
    if not words:
        return [""]
    out, cur = [], ""
    for w in words:
        trial = w if not cur else f"{cur} {w}"
        if measure(trial, px)[0] <= box_w:
            cur = trial
            continue
        if cur:
            out.append(cur)
        cur = w
        while measure(cur, px)[0] > box_w and len(cur) > 1:   # split a word wider than the box
            cut = max(1, len(cur) * box_w // max(1, measure(cur, px)[0]))
            out.append(cur[:cut])
            cur = cur[cut:]
    out.append(cur)
    return out


def sermon_lines(church: str, title: str, speaker: str, reference: str) -> dict[str, str]:
    """Which text goes in which slot of the sermon info slide (blank slots are skipped by painter)."""
    return {"church": (church or "").strip(), "title": (title or "").strip(),
            "speaker": (speaker or "").strip(), "reference": (reference or "").strip()}


# --- painting (Qt imported lazily so headless tests import this module) -----------------

def _qcolor(hex_value: str):
    from PyQt6.QtGui import QColor
    return QColor(hex_value)


def paint_background(painter, rect, theme, image_cache: dict | None = None) -> None:
    """Fill rect from the theme background: solid, vertical gradient, radial, or image (cover + scrim).

    An image that is missing or unreadable falls back to the first colour, so a shared theme
    never leaves the projector black with no warning in the operator log.
    """
    from PyQt6.QtCore import QPointF, QRectF
    from PyQt6.QtGui import QLinearGradient, QPixmap, QRadialGradient
    bg = theme.background
    colors = bg.colors or [MIDNIGHT]
    kind = bg.kind
    if kind == "image":
        path = resolve_background_image(bg.image_path)
        pix = None
        if path is not None:
            cache = image_cache if image_cache is not None else {}
            pix = lru_get_or_load(cache, str(path), lambda p: QPixmap(p))
        if pix is not None and not pix.isNull():
            scaled = pix.scaled(int(rect.width()), int(rect.height()), 
                                _keep_aspect_crop(), _smooth())
            x = rect.x() + (rect.width() - scaled.width()) / 2
            y = rect.y() + (rect.height() - scaled.height()) / 2
            painter.drawPixmap(QRectF(x, y, scaled.width(), scaled.height()).toRect(), scaled)
            scrim = _qcolor(MIDNIGHT)
            scrim.setAlphaF(max(0.0, min(0.9, float(theme.image_scrim))))
            painter.fillRect(rect, scrim)
            return
        kind = "solid"                       # missing image: first colour
    if kind == "linear" and len(colors) > 1:
        g = QLinearGradient(QPointF(rect.x(), rect.y()), QPointF(rect.x(), rect.y() + rect.height()))
        g.setColorAt(0.0, _qcolor(colors[0]))
        g.setColorAt(1.0, _qcolor(colors[1]))
        painter.fillRect(rect, g)
    elif kind == "radial" and len(colors) > 1:
        cx, cy = rect.x() + rect.width() / 2, rect.y() + rect.height() / 2
        r = max(rect.width(), rect.height()) / 2
        g = QRadialGradient(QPointF(cx, cy), r)
        g.setColorAt(0.0, _qcolor(colors[0]))
        g.setColorAt(1.0, _qcolor(colors[1]))
        painter.fillRect(rect, g)
    else:
        painter.fillRect(rect, _qcolor(colors[0]))


def _keep_aspect_crop():
    from PyQt6.QtCore import Qt
    return Qt.AspectRatioMode.KeepAspectRatioByExpanding


def _smooth():
    from PyQt6.QtCore import Qt
    return Qt.TransformationMode.SmoothTransformation


def _font(theme, px: int):
    from PyQt6.QtGui import QFont
    f = QFont(theme.font_family)
    f.setPixelSize(max(1, int(px)))
    f.setWeight(_qt_weight(theme.font_weight))
    return f


def _qt_weight(css_weight: int):
    from PyQt6.QtGui import QFont
    # CSS 100..900 maps onto Qt's 0..99 scale (400 normal, 700 bold).
    return QFont.Weight(max(0, min(99, int(css_weight / 9))))


def _draw_frame(painter, rect, theme) -> None:
    from PyQt6.QtCore import QRectF, Qt
    from PyQt6.QtGui import QPen
    if theme.frame == "none":
        return
    inset = max(0, int(theme.frame_inset_px) // 8)   # frame sits inside the safe margin
    box = QRectF(rect).adjusted(inset, inset, -inset, -inset)
    gold = _qcolor(theme.accent_color)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    if theme.frame == "thin":
        painter.setPen(QPen(gold, 2))
        painter.drawRoundedRect(box, 14, 14)
    elif theme.frame == "double":
        painter.setPen(QPen(gold, 2))
        painter.drawRoundedRect(box, 14, 14)
        painter.drawRoundedRect(box.adjusted(10, 10, -10, -10), 10, 10)
    else:                                              # gold_rule: one heavier rule
        painter.setPen(QPen(gold, 4))
        painter.drawRoundedRect(box, 18, 18)


def _draw_chip(painter, text: str, x: float, y: float, theme, size_px: int) -> float:
    """Gold-outlined rounded chip. Returns its width so callers can stack or align chips."""
    from PyQt6.QtCore import QRectF, Qt
    from PyQt6.QtGui import QFontMetrics, QPen
    if not text:
        return 0.0
    font = _font(theme, size_px)
    painter.setFont(font)
    fm = QFontMetrics(font)
    w = fm.horizontalAdvance(text) + size_px * 1.2
    h = fm.height() + size_px * 0.6
    rect = QRectF(x, y, w, h)
    painter.setBrush(_qcolor(MIDNIGHT))
    painter.setPen(QPen(_qcolor(theme.accent_color), 2))
    painter.drawRoundedRect(rect, h / 2, h / 2)
    painter.setPen(_qcolor(theme.accent_color))
    painter.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), text)
    return w


def _text_color(theme):
    from PyQt6.QtGui import QColor
    return QColor(theme.text_color)


def paint_song(painter, rect, theme, *, title: str, artist: str, section: str, index: int,
               total: int, lines: list[str], image_cache: dict | None = None) -> None:
    """Mockup A: lyrics large and centred, section label above, footer bottom-left, chip bottom-right."""
    from PyQt6.QtCore import QRectF, Qt
    section = display_section(section)
    paint_background(painter, rect, theme, image_cache)
    _draw_frame(painter, rect, theme)
    W, H = rect.width(), rect.height()
    margin_x, margin_y = W * SAFE_MARGIN_RATIO, H * SAFE_MARGIN_RATIO
    footer_h = H * 0.12
    label_h = H * 0.07 if section else 0.0
    box_w = W - 2 * margin_x - (W * 0.10 if theme.frame != "none" else 0)
    box_h = H - 2 * margin_y - footer_h - label_h
    px = fit_font_px(lines or [""], int(box_w), int(box_h), theme.font_size_px,
                     theme.line_height, measure=_qt_measure(theme))
    font = _font(theme, px)
    painter.setFont(font)
    painter.setPen(_text_color(theme))
    body = []
    for line in lines:
        body.extend(wrap_lines(line, int(box_w), px, _qt_measure(theme)))
    block_h = len(body) * px * theme.line_height
    top = margin_y + label_h + (box_h - block_h) / 2
    if section:
        painter.setFont(_font(theme, max(MIN_FIT_PX, int(H * 0.035))))
        painter.setPen(_qcolor(theme.accent_color))
        painter.drawText(QRectF(rect.x(), rect.y() + margin_y, W, label_h),
                         int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter), section)
        painter.setFont(font)
        painter.setPen(_text_color(theme))
    painter.drawText(QRectF(rect.x() + margin_x + (W * 0.05 if theme.frame != "none" else 0),
                            rect.y() + top, box_w, block_h),
                     int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap),
                     "\n".join(body))
    # footer and chip
    small = max(MIN_FIT_PX, int(H * 0.032))
    painter.setFont(_font(theme, small))
    painter.setPen(_qcolor(theme.dim_color))
    foot = footer_text(title, artist)
    fy = H - margin_y - small * 1.6
    if foot:
        painter.drawText(QRectF(rect.x() + margin_x, rect.y() + fy, W * 0.6, small * 1.6),
                         int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), foot)
    chip = chip_text(section, index, total)
    if chip:
        probe = _font(theme, small)
        from PyQt6.QtGui import QFontMetrics
        cw = QFontMetrics(probe).horizontalAdvance(chip) + small * 1.2
        _draw_chip(painter, chip, rect.x() + W - margin_x - cw, rect.y() + fy - small * 0.2,
                   theme, small)


def paint_sermon(painter, rect, theme, *, church: str, title: str, speaker: str,
                 reference: str, image_cache: dict | None = None) -> None:
    """Mockup B: church line at top, large serif title, speaker below, reference in a gold chip."""
    from PyQt6.QtCore import QRectF, Qt
    paint_background(painter, rect, theme, image_cache)
    _draw_frame(painter, rect, theme)
    W, H = rect.width(), rect.height()
    mx, my = W * SAFE_MARGIN_RATIO, H * SAFE_MARGIN_RATIO
    box_w = W - 2 * mx
    centre = int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
    y = rect.y() + my
    if church:
        painter.setFont(_font(theme, max(MIN_FIT_PX, int(H * 0.035))))
        painter.setPen(_qcolor(theme.accent_color))
        painter.drawText(QRectF(rect.x() + mx, y, box_w, H * 0.07), centre, church.upper())
        y += H * 0.09
    if title:
        tpx = fit_font_px([title], int(box_w), int(H * 0.45), int(theme.font_size_px * 1.2),
                          theme.line_height, measure=_qt_measure(theme, serif=True))
        font = _font(theme, tpx)
        font.setFamily(theme.font_family)
        painter.setFont(font)
        painter.setPen(_text_color(theme))
        wrapped = []
        for line in title.split("\n"):
            wrapped.extend(wrap_lines(line, int(box_w), tpx, _qt_measure(theme, serif=True)))
        th = len(wrapped) * tpx * theme.line_height
        painter.drawText(QRectF(rect.x() + mx, y, box_w, th),
                         int(centre | Qt.TextFlag.TextWordWrap), "\n".join(wrapped))
        y += th + H * 0.03
    if speaker:
        painter.setFont(_font(theme, max(MIN_FIT_PX, int(H * 0.045))))
        painter.setPen(_qcolor(theme.dim_color))
        painter.drawText(QRectF(rect.x() + mx, y, box_w, H * 0.07), centre, speaker)
        y += H * 0.09
    if reference:
        small = max(MIN_FIT_PX, int(H * 0.04))
        from PyQt6.QtGui import QFontMetrics
        cw = QFontMetrics(_font(theme, small)).horizontalAdvance(reference) + small * 1.2
        _draw_chip(painter, reference, rect.x() + (W - cw) / 2, y, theme, small)


def _qt_measure(theme, serif: bool = False):
    from PyQt6.QtGui import QFontMetrics

    def measure(text: str, px: int) -> tuple[int, int]:
        fm = QFontMetrics(_font(theme, px))
        return (fm.horizontalAdvance(text), fm.height())
    return measure


def paint_verse(painter, rect, theme, candidate) -> None:
    """Scripture slide: text large and centred, reference and translation in the accent colour below."""
    from PyQt6.QtCore import QRectF, Qt
    paint_background(painter, rect, theme)
    _draw_frame(painter, rect, theme)
    W, H = rect.width(), rect.height()
    mx, my = W * SAFE_MARGIN_RATIO, H * SAFE_MARGIN_RATIO
    ref = f"{candidate.reference} ({candidate.translation})"
    ref_px = max(MIN_FIT_PX, int(theme.font_size_px * 0.6))
    box_w = W - 2 * mx
    box_h = H - 2 * my - ref_px * 2.2
    text = candidate.display_text or ""
    px = fit_font_px([text], int(box_w), int(box_h), theme.font_size_px, theme.line_height,
                     measure=_qt_measure(theme))
    body = wrap_lines(text, int(box_w), px, _qt_measure(theme))
    painter.setFont(_font(theme, px))
    painter.setPen(_text_color(theme))
    centre = int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
    painter.drawText(QRectF(rect.x() + mx, rect.y() + my, box_w, box_h - px * 0.5),
                     centre | int(Qt.TextFlag.TextWordWrap), "\n".join(body))
    painter.setFont(_font(theme, ref_px))
    painter.setPen(_qcolor(theme.reference_color))
    painter.drawText(QRectF(rect.x() + mx, rect.y() + H - my - ref_px * 2.2, box_w, ref_px * 2.2),
                     centre, ref)


IMAGE_CACHE_MAX = 8   # audit: bounded LRU of decoded projection images (full-res, so keep it small)


def lru_get_or_load(cache: dict, key, loader, max_entries: int = IMAGE_CACHE_MAX):
    """Return cache[key], loading it with loader(key) on a miss. Least recently used entries are
    dropped once the cache holds more than max_entries, so long media sessions cannot grow memory
    without limit. dict preserves insertion order: a hit is moved to the end."""
    if key in cache:
        value = cache.pop(key)
        cache[key] = value
        return value
    value = loader(key)
    cache[key] = value
    while len(cache) > max_entries:
        cache.pop(next(iter(cache)))
    return value


def paint_media_image(painter, rect, path: str, image_cache: dict | None = None) -> None:
    """Full-frame media image: scaled to fill the frame, aspect kept (cropped to fit), on black.

    A missing or unreadable file paints black with the on-slide message handled by the window.
    """
    from PyQt6.QtCore import QRectF
    from PyQt6.QtGui import QPixmap
    painter.fillRect(rect, _qcolor(MIDNIGHT))
    cache = image_cache if image_cache is not None else {}
    pix = lru_get_or_load(cache, path, lambda p: QPixmap(p))
    if pix.isNull():
        return
    scaled = pix.scaled(int(rect.width()), int(rect.height()), _keep_aspect_crop(), _smooth())
    x = rect.x() + (rect.width() - scaled.width()) / 2
    y = rect.y() + (rect.height() - scaled.height()) / 2
    painter.drawPixmap(QRectF(x, y, scaled.width(), scaled.height()).toRect(), scaled)


def paint_media_message(painter, rect, text: str) -> None:
    """Friendly on-slide message for media that cannot play (black letterbox, gold text)."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QFont
    font = QFont()
    font.setPixelSize(max(20, int(rect.height() / 22)))
    painter.setFont(font)
    painter.setPen(_qcolor("#D4A017"))
    painter.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), text)
