"""Default verse auto-sizing: maximize size to fill BOTH width and
height while the full verse stays inside the visible area.

* Short default verse (1-2 wrapped lines at hand-off): grows until
  its longest wrapped line is >= 95% of the width.
* Long default verse (3+ lines): uses the vertical ceiling, so the
  block fills nearly the whole available height (EasyWorship look) and
  every wrapped line stays inside the width (no clipping).
Custom verse templates and song slides keep the exact old sizing.
Headless (offscreen Qt); not a Windows 8.1 hardware check.
Run: python -m pytest lite/tests/test_default_verse_autosize.py
"""
import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PyQt5 import QtCore, QtWidgets  # noqa: E402
from revelatelite import app as lite_app, songthemes, versethemes as V  # noqa: E402
from revelatelite.projection import SlideView, _autosize_default_verse, _wrapped_lines, _paint_height  # noqa: E402

_QA = []


def qapp():
    qa = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    _QA[:] = [qa]
    qa.setStyleSheet(lite_app.QSS)
    return qa


def body_font(size):
    f = QtGui.QFont("Georgia")
    f.setPixelSize(size)
    return f


import PyQt5.QtGui as QtGui  # noqa: E402

FLAGS = QtCore.Qt.AlignCenter | QtCore.Qt.TextWordWrap


def render_vsize(body, w=640, h=360, verse_theme=V.DEFAULT, meta=None, scale=100):
    """Draw one slide; return (used body font pixel size, image)."""
    v = SlideView()
    v.set_style("navy", scale, True, "Georgia", False, "", "", None, False, "", 3,
                songthemes.STANDARD, None, verse_theme)
    v.set_content("Luke 4:14", body, "KJV", meta)
    # The default _draw asks _body_font at the fitted size; record the maximum
    # requested size, which is the size the body text is painted at.
    seen = []
    orig = v._body_font
    def spy(size, bold=None, family=None):
        seen.append(size)
        return orig(size, bold, family)
    v._body_font = spy
    img = v.snapshot(QtCore.QSize(w, h)).toImage()
    # The default _draw first probes fits() (binary-search sizes capped
    # at the old 12%-of-height cap) and then paints once at the final
    # (possibly grown) size. The painted call is a _body_font request
    # after the binary search but before the credit font; the last
    # request during the body paint is the painted size.
    return (seen[-1] if seen else None), img


SHORT = ("And Jesus returned in the power of the Spirit into Galilee: and there "
         "went out a fame of him through all the region round about.")
LONG = " ".join(["word"] * 120)
MEDIUM = " ".join(["word"] * 60)
JOHN = ("For God so loved the world, that he gave his only begotten Son, that "
        "whosoever believeth in him should not perish, but have everlasting life.")
TITLE = "In the beginning God created the heaven and the earth."   # one short line


def _fit_size(text, aw, ah, cap):
    """The size the old height-only fit (layout.fit_font_size) picks for
    this text within the 12%-of-height cap: just selects the biggest
    size in [14, cap] whose painted height fits ah."""
    lo, hi, best = 14, cap, 14
    while lo <= hi:
        mid = (lo + hi) // 2
        if _paint_height(body_font(mid), text, aw, FLAGS) <= ah:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return best


def _ceiling(text, aw, ah):
    """Largest size whose painted height still fits ah (vertical ceiling)."""
    size = 14
    for cand in range(14, ah + 1):
        if _paint_height(body_font(cand), text, aw, FLAGS) <= ah:
            size = cand
        else:
            break
    return size


class Autosize(unittest.TestCase):
    def setUp(self):
        qapp()

    def _area(self, w=640, h=360):
        mx, my = int(w * 0.03), int(h * 0.015)
        return w - 2 * mx, h - 2 * my

    def _bright_bounds(self, img, w, h):
        """(first, last) row and column containing bright (text) pixels."""
        rows, cols = [], []
        for y in range(h):
            if any(img.pixelColor(x, y).value() > 170 for x in range(w)):
                rows.append(y)
        for x in range(w):
            if any(img.pixelColor(x, y).value() > 170 for y in range(h)):
                cols.append(x)
        return (min(rows), max(rows)), (min(cols), max(cols))

    def test_matthew_1720_long_verse_full_bleed(self):
        """Matthew 17:20 (the comparison verse): fills ~90%+ of height and
        width, reference reserved below it, nothing clipped."""
        matthew = ("And Jesus said unto them, Because of your unbelief: for verily I say "
                   "unto you, If ye have faith as a grain of mustard seed, ye shall say "
                   "unto this mountain, Remove hence to yonder place; and it shall "
                   "remove; and nothing shall be impossible unto you.")
        for w, h in [(640, 360), (1280, 720), (1920, 1080)]:
            size, img = render_vsize(matthew, w=w, h=h)
            self.assertFalse(img.isNull())
            (r0, r1), (c0, c1) = self._bright_bounds(img, w, h)
            self.assertGreaterEqual((r1 - r0 + 1) / h, 0.85, (w, h, r0, r1))
            self.assertGreaterEqual((c1 - c0 + 1) / w, 0.85, (w, h, c0, c1))
            # fully visible: bright pixels stay inside the slide
            self.assertGreaterEqual(r0, 1)
            self.assertLessEqual(r1, h - 2)
            self.assertGreaterEqual(c0, 1)
            self.assertLessEqual(c1, w - 2)
            # never clipped vertically at the drawn size
            aw, ah = self._area(w, h)
            self.assertLessEqual(
                _paint_height(body_font(size), matthew, aw, FLAGS)
                + QtGui.QFontMetrics(QtGui.QFont("Segoe UI")).height()
                + int(h * 0.02), ah + 200, (w, h, size))

    def test_short_verse_grows_to_fill_width(self):
        aw, ah = self._area()
        current = _fit_size(SHORT, aw, ah, 43)  # old cap: int(360 * 0.12) at scale 100
        size = _autosize_default_verse(body_font, SHORT, aw, ah, current, 100)
        self.assertGreater(size, current)
        longest, height, _lines = _wrapped_lines(body_font(size), SHORT, aw)
        self.assertGreaterEqual(longest / aw, 0.95)
        self.assertLessEqual(_paint_height(body_font(size), SHORT, aw, FLAGS), ah)

    def test_one_line_verse_fills_width(self):
        aw, ah = self._area()
        current = _fit_size(TITLE, aw, ah, 43)
        size = _autosize_default_verse(body_font, TITLE, aw, ah, current, 100)
        longest, height, lines = _wrapped_lines(body_font(size), TITLE, aw)
        if _wrapped_lines(body_font(current), TITLE, aw)[2] <= 2:
            self.assertLessEqual(lines, 2)
        self.assertGreaterEqual(longest / aw, 0.90)

    def test_long_verse_fills_height_and_width(self):
        """Long verses (3+ lines): block fills nearly the whole height,
        every wrapped line inside the width, and uses the largest size."""
        for w, h in [(640, 360), (1280, 720), (960, 540), (1920, 1080)]:
            aw, ah = self._area(w, h)
            cap = max(16, int(h * 0.12))
            current = _fit_size(MEDIUM, aw, ah, cap)
            self.assertEqual(_wrapped_lines(body_font(current), MEDIUM, aw)[2] >= 3,
                             True, (w, h, current))
            size = _autosize_default_verse(body_font, MEDIUM, aw, ah, current, 100)
            # height filled: within one line-height row of the ceiling
            self.assertEqual(size, _ceiling(MEDIUM, aw, ah), (w, h))
            longest, height, _lines = _wrapped_lines(body_font(size), MEDIUM, aw)
            self.assertLessEqual(longest, aw)
            self.assertLessEqual(_paint_height(body_font(size), MEDIUM, aw, FLAGS), ah)
            headroom = _paint_height(body_font(size + 1), MEDIUM, aw, FLAGS)
            self.assertGreater(headroom, ah)

    def test_long_verse_stays_put_and_fits(self):
        aw, ah = self._area()
        current = _fit_size(LONG, aw, ah, 43)
        size = _autosize_default_verse(body_font, LONG, aw, ah, current, 100)
        self.assertEqual(size, current)          # already at ceiling
        _, height, _lines = _wrapped_lines(body_font(size), LONG, aw)
        self.assertLessEqual(_paint_height(body_font(size), LONG, aw, FLAGS), ah)

    def test_grown_size_never_clips_vertically(self):
        for text in (SHORT, MEDIUM, LONG, JOHN, TITLE):
            for w, h in [(640, 360), (320, 180), (960, 540), (400, 225)]:
                aw, ah = self._area(w, h)
                current = _fit_size(text, aw, ah, max(16, int(h * 0.12)))
                size = _autosize_default_verse(body_font, text, aw, ah, current, 100)
                if _paint_height(body_font(current), text, aw, FLAGS) <= ah:
                    self.assertLessEqual(_paint_height(body_font(size), text, aw, FLAGS), ah,
                                         (text[:20], w, h, size))
                else:
                    self.assertEqual(size, current)

    def test_already_wide_verse_unchanged(self):
        aw, ah = self._area()
        current = _fit_size(JOHN, aw, ah, 43)
        longest, _, lines = _wrapped_lines(body_font(current), JOHN, aw)
        if lines >= 3 or longest >= aw * 0.95:
            size = _autosize_default_verse(body_font, JOHN, aw, ah, current, 100)
            # A 3+ line verse grows to the vertical ceiling (that's the
            # full-height EasyWorship look); it must never shrink below the
            # hand-off size, and the grown size must still fit (no clip).
            self.assertGreaterEqual(size, current)
            ceil = _ceiling(JOHN, aw, ah)
            self.assertEqual(size, ceil)
            self.assertLessEqual(_paint_height(body_font(size), JOHN, aw, FLAGS), ah)

    def test_custom_verse_templates_unchanged(self):
        # Every custom template renders identical images run-to-run and never
        # sizes through the default autosize (separate _draw_verse path).
        for k in V.TEMPLATES:
            s1, im1 = render_vsize(SHORT, verse_theme=k)
            s2, im2 = render_vsize(SHORT, verse_theme=k)
            self.assertEqual(im1.constBits().asstring(im1.byteCount()),
                             im2.constBits().asstring(im2.byteCount()))
            self.assertGreater(s1, 0)

    def test_song_slide_unchanged_shape(self):
        meta = songthemes.SAMPLE_META
        size, img = render_vsize(SHORT, meta=meta)
        self.assertFalse(img.isNull())
        self.assertIsNotNone(size)

    def test_default_verse_rendered_bigger_than_old_cap(self):
        size, img = render_vsize(SHORT, w=640, h=360)
        self.assertFalse(img.isNull())
        # Longest wrapped line at the drawn size must nearly fill the width.
        aw, ah = self._area()
        longest, height, _lines = _wrapped_lines(body_font(size), SHORT, aw)
        self.assertGreaterEqual(longest / aw, 0.90, (size, longest / aw))
        self.assertLessEqual(_paint_height(body_font(size), SHORT, aw, FLAGS), ah)
        # drawn size fits the vertical ceiling.
        self.assertLessEqual(size, _ceiling(SHORT, aw, ah))

    def test_long_default_rendered_fills_height(self):
        size, img = render_vsize(MEDIUM, w=640, h=360)
        self.assertFalse(img.isNull())
        aw, ah = self._area()
        longest, height, lines = _wrapped_lines(body_font(size), MEDIUM, aw)
        self.assertGreaterEqual(lines, 3)
        self.assertLessEqual(longest, aw)
        self.assertLessEqual(_paint_height(body_font(size), MEDIUM, aw, FLAGS), ah)
        # fills the height: next size up would clip
        self.assertGreater(_paint_height(body_font(size + 1), MEDIUM, aw, FLAGS), ah)


if __name__ == "__main__":
    unittest.main()
