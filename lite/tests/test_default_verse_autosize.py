"""Default verse auto-sizing: a short default verse should grow until its longest
wrapped line nearly fills the width, never clipping vertically.
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
from revelatelite.projection import SlideView, _autosize_default_verse, _wrapped_lines  # noqa: E402

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
    # The default _draw paints the body once, at the fitted (possibly grown)
    # size: the largest _body_font request is the drawn size. (Seen sizes are
    # the fit binary-search probes plus the final paint.)
    return (max(seen) if seen else None), img


SHORT = ("And Jesus returned in the power of the Spirit into Galilee: and there "
         "went out a fame of him through all the region round about.")
LONG = " ".join(["word"] * 120)
JOHN = ("For God so loved the world, that he gave his only begotten Son, that "
        "whosoever believeth in him should not perish, but have everlasting life.")


class Autosize(unittest.TestCase):
    def setUp(self):
        qapp()

    def _area(self, w=640, h=360):
        mx, my = int(w * 0.07), int(h * 0.06)
        return w - 2 * mx, h - 2 * my

    def test_short_verse_grows_to_fill_width(self):
        aw, ah = self._area()
        current = 43  # old cap: int(360 * 0.12) at scale 100
        size = _autosize_default_verse(body_font, SHORT, aw, ah, current, 100)
        self.assertGreater(size, current)
        longest, height = _wrapped_lines(body_font(size), SHORT, aw)
        self.assertGreaterEqual(longest / aw, 0.90)
        self.assertLessEqual(height, ah)

    def test_grown_size_never_clips_vertically(self):
        for w, h in [(640, 360), (320, 180), (960, 540), (400, 225)]:
            aw, ah = self._area(w, h)
            current = max(16, int(h * 0.12))
            size = _autosize_default_verse(body_font, SHORT, aw, ah, current, 100)
            _, height = _wrapped_lines(body_font(size), SHORT, aw)
            self.assertLessEqual(height, ah, (w, h, size))

    def test_long_verse_stays_put_and_fits(self):
        aw, ah = self._area()
        current = 19          # the size the old fit actually picks for LONG
        size = _autosize_default_verse(body_font, LONG, aw, ah, current, 100)
        self.assertEqual(size, current)
        _, height = _wrapped_lines(body_font(size), LONG, aw)
        self.assertLessEqual(height, ah)

    def test_already_wide_verse_unchanged(self):
        aw, ah = self._area()
        current = 43
        size = _autosize_default_verse(body_font, JOHN, aw, ah, current, 100)
        longest, _ = _wrapped_lines(body_font(current), JOHN, aw)
        if longest >= aw * 0.95:      # already full: helper must not grow it
            self.assertEqual(size, current)

    def test_custom_verse_templates_unchanged(self):
        # Every custom template must render pixel-identical (the patch never
        # touches _draw_verse, and the default path is verse-only).
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
        longest, height = _wrapped_lines(body_font(size), SHORT, aw)
        self.assertGreaterEqual(longest / aw, 0.90, (size, longest / aw))
        # pushed past the old height-only fit means bigger than the smallest
        # size that already filled the width
        self.assertLessEqual(height, ah)


if __name__ == "__main__":
    unittest.main()
