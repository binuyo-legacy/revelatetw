"""Projection background: solid colour, two-colour gradient, or a picture from disk.

The maths here is plain Python (no Qt) so it is easy to test. Qt drawing helpers sit at the bottom and
import PyQt5 lazily. The preview and the full-screen window both call the same paint function, so they
always show the same background.

Kept light for a 2 GB / 32-bit PC: a picture is read once, shrunk to at most 1920x1080 while it is
decoded (never the full camera-size bitmap), and cached; the scaled copy is cached per window size.
"""
import os

KINDS = [("color", "Solid colour"), ("gradient", "Gradient (two colours)"), ("image", "Picture")]
KIND_KEYS = [k for k, _ in KINDS]

DIRECTIONS = [
    ("vertical", "Top to bottom"),
    ("horizontal", "Left to right"),
    ("diagonal_down", "Diagonal (top-left to bottom-right)"),
    ("diagonal_up", "Diagonal (bottom-left to top-right)"),
]
DIRECTION_KEYS = [k for k, _ in DIRECTIONS]

IMAGE_MODES = [
    ("fill", "Fill (crop edges, no gaps)"),
    ("fit", "Fit (whole picture, bars if needed)"),
    ("stretch", "Stretch (may distort)"),
    ("tile", "Tile (repeat)"),
]
IMAGE_MODE_KEYS = [k for k, _ in IMAGE_MODES]

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".gif")
MAX_IMAGE_BYTES = 30 * 1024 * 1024   # refuse huge files outright
MAX_W, MAX_H = 1920, 1080             # decoded size cap
TILE_MAX = 512                        # tiles larger than this are shrunk before repeating
DIM_MAX = 80

DEFAULT_C1, DEFAULT_C2 = "#1e3a8a", "#0b0f19"


def _hex_ok(c):
    return (isinstance(c, str) and len(c) == 7 and c[0] == "#"
            and all(ch in "0123456789abcdefABCDEF" for ch in c[1:]))


def clean(st):
    """Return validated background fields from a settings dict (bad values fall back to defaults)."""
    kind = st.get("bg_kind")
    mode = st.get("image_mode")
    dirn = st.get("grad_direction")
    c1, c2 = st.get("grad_color1"), st.get("grad_color2")
    dim = st.get("image_dim", 30)
    return {
        "bg_kind": kind if kind in KIND_KEYS else "color",
        "grad_color1": c1 if _hex_ok(c1) else DEFAULT_C1,
        "grad_color2": c2 if _hex_ok(c2) else DEFAULT_C2,
        "grad_direction": dirn if dirn in DIRECTION_KEYS else "vertical",
        "bg_image": st.get("bg_image") if isinstance(st.get("bg_image"), str) else "",
        "image_mode": mode if mode in IMAGE_MODE_KEYS else "fill",
        "image_dim": max(0, min(DIM_MAX, dim)) if isinstance(dim, int) and not isinstance(dim, bool) else 30,
    }


def spec_from(st):
    """Hashable tuple describing the background. Used to tell the preview and the projector apart:
    if this changes, the preview is ahead of what is on the big screen until Project is clicked."""
    c = clean(st)
    return (c["bg_kind"], c["grad_color1"], c["grad_color2"], c["grad_direction"],
            c["bg_image"], c["image_mode"], c["image_dim"])


def mix(c1, c2):
    """Average of two '#rrggbb' colours."""
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple((x + y) // 2 for x, y in zip(a, b))


def gradient_points(direction, w, h):
    """(x1, y1, x2, y2) start and end of the gradient line for a w x h area."""
    if direction == "horizontal":
        return (0, 0, w, 0)
    if direction == "diagonal_down":
        return (0, 0, w, h)
    if direction == "diagonal_up":
        return (0, h, w, 0)
    return (0, 0, 0, h)


def check_image_file(path):
    """(ok, message). Cheap checks only: exists, a file, allowed type, not enormous."""
    if not path:
        return False, ""
    if not os.path.isfile(path):
        return False, "Picture not found (moved or deleted). Using the plain colour instead."
    if os.path.splitext(path)[1].lower() not in IMAGE_EXTS:
        return False, "That picture type is not supported. Use PNG, JPG, BMP or GIF."
    try:
        if os.path.getsize(path) > MAX_IMAGE_BYTES:
            return False, "That picture is too big (over 30 MB). Pick a smaller one."
    except OSError:
        return False, "Could not read that picture. Using the plain colour instead."
    return True, ""


def fit_size(iw, ih, w, h, cover=False):
    """Size of an iw x ih picture scaled to fit inside (or, with cover, to cover) w x h, same shape."""
    if iw <= 0 or ih <= 0 or w <= 0 or h <= 0:
        return (max(w, 0), max(h, 0))
    s = max(w / iw, h / ih) if cover else min(w / iw, h / ih)
    return (max(1, round(iw * s)), max(1, round(ih * s)))


def image_rects(mode, iw, ih, w, h):
    """(source_rect, target_rect) as (x, y, w, h) tuples, for stretch / fit / fill."""
    if mode == "stretch":
        return (0, 0, iw, ih), (0, 0, w, h)
    if mode == "fit":
        tw, th = fit_size(iw, ih, w, h)
        return (0, 0, iw, ih), ((w - tw) // 2, (h - th) // 2, tw, th)
    # fill: crop the picture (centred) to the window's shape
    tw, th = fit_size(iw, ih, w, h, cover=True)
    sw = min(iw, max(1, round(iw * w / tw)))
    sh = min(ih, max(1, round(ih * h / th)))
    return ((iw - sw) // 2, (ih - sh) // 2, sw, sh), (0, 0, w, h)


# ---------------- Qt side ----------------
_cache = {"key": None, "image": None, "msg": "", "gen": 0, "lum": 0}


def load_image(path):
    """(QImage or None, message). One shared, size-capped copy for every window."""
    ok, msg = check_image_file(path)
    if not ok:
        return None, msg
    try:
        key = (path, os.path.getmtime(path))
    except OSError:
        return None, "Could not read that picture. Using the plain colour instead."
    if _cache["key"] == key:
        return _cache["image"], _cache["msg"]
    from PyQt5 import QtCore, QtGui
    img, msg = None, ""
    try:
        r = QtGui.QImageReader(path)
        r.setAutoTransform(True)
        sz = r.size()
        if sz.isValid() and (sz.width() > MAX_W or sz.height() > MAX_H):
            tw, th = fit_size(sz.width(), sz.height(), MAX_W, MAX_H)
            r.setScaledSize(QtCore.QSize(tw, th))   # shrunk while decoding, big bitmap never built
        img = r.read()
        if img.isNull():
            img, msg = None, "That picture could not be opened (damaged or not a real image). Using the plain colour instead."
        else:
            img = img.convertToFormat(QtGui.QImage.Format_RGB32)
    except Exception:  # never let a bad file take the app down
        img, msg = None, "That picture could not be opened. Using the plain colour instead."
    lum = 0
    if img is not None:
        try:   # average brightness from a tiny copy (cheap), used for the readability hint
            t = img.scaled(16, 9, QtCore.Qt.IgnoreAspectRatio, QtCore.Qt.FastTransformation)
            vals = [QtGui.QColor(t.pixel(x, y)) for x in range(16) for y in range(9)]
            lum = sum(0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue() for c in vals) / len(vals)
        except Exception:
            lum = 0
    _cache.update(key=key, image=img, msg=msg, gen=_cache["gen"] + 1, lum=lum)
    return img, msg


def too_bright_hint(lum, dim):
    """Plain-language warning when a bright picture (after darkening) would make white text hard to read."""
    if lum * (1 - dim / 100.0) > 150:
        return "This picture is bright, so white text may be hard to read. Raise Darken picture."
    return ""


def image_hint(path, dim):
    """Brightness hint for the picture at path ('' if none or unreadable)."""
    img, _ = load_image(path)
    return too_bright_hint(_cache["lum"], dim) if img is not None else ""


def image_problem(path):
    """'' if the picture is usable, else the message to show the operator."""
    if not path:
        return ""
    return load_image(path)[1]


class Painter:
    """Paints the chosen background. One per window; remembers its scaled copy."""

    def __init__(self):
        self._scaled = None
        self._scaled_key = None
        self._tile = None
        self._tile_key = None

    def paint(self, p, rect, spec, base_color):
        """Draw the background of `spec` into rect. base_color ('#rrggbb') is the solid colour and
        the fallback / bar colour."""
        from PyQt5 import QtCore, QtGui
        kind, c1, c2, dirn, path, mode, dim = spec
        w, h = rect.width(), rect.height()
        if kind == "gradient":
            x1, y1, x2, y2 = gradient_points(dirn, w, h)
            g = QtGui.QLinearGradient(x1, y1, x2, y2)
            g.setColorAt(0, QtGui.QColor(c1))
            g.setColorAt(1, QtGui.QColor(c2))
            p.fillRect(rect, QtGui.QBrush(g))
            return
        p.fillRect(rect, QtGui.QColor(base_color))
        if kind != "image":
            return
        img, _ = load_image(path)
        if img is None:
            return
        if mode == "tile":
            tile = img
            if max(img.width(), img.height()) > TILE_MAX:
                tw, th = fit_size(img.width(), img.height(), TILE_MAX, TILE_MAX)
                tile = self._get_scaled(img, (tw, th), "tile", lambda: img.scaled(
                    tw, th, QtCore.Qt.IgnoreAspectRatio, QtCore.Qt.FastTransformation))
            tkey = (_cache["gen"], tile.width(), tile.height())
            if self._tile_key != tkey:      # convert once, not on every repaint
                self._tile, self._tile_key = QtGui.QPixmap.fromImage(tile), tkey
            p.drawTiledPixmap(rect, self._tile)
        else:
            src, dst = image_rects(mode, img.width(), img.height(), w, h)
            crop = QtCore.QRect(*src)
            scaled = self._get_scaled(img, (w, h), (mode, src), lambda: img.copy(crop).scaled(
                dst[2], dst[3], QtCore.Qt.IgnoreAspectRatio, QtCore.Qt.SmoothTransformation))
            p.drawImage(QtCore.QPoint(dst[0], dst[1]), scaled)
        if dim:
            p.fillRect(rect, QtGui.QColor(0, 0, 0, int(255 * dim / 100)))

    def _get_scaled(self, img, size, tag, make):
        key = (_cache["gen"], size, tag)   # gen changes with every new picture (id() can be reused)
        if self._scaled_key != key:
            self._scaled = make()
            self._scaled_key = key
        return self._scaled
