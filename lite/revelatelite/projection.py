"""The projection window: borderless, goes to the extended display, auto-sizes the verse."""
from PyQt5 import QtCore, QtGui, QtWidgets

from revelatetw.ui_tokens import COLORS as C

from . import background, layout, settings, songthemes, transitions, versethemes


def _wrapped_lines(font, text, width):
    """(longest line width, total height, number of lines) word-wrapped into width."""
    if width <= 0:
        return 0.0, 0, 0
    lay = QtGui.QTextLayout(text, font)
    lay.beginLayout()
    longest, total, lines = 0.0, 0.0, 0
    while True:
        line = lay.createLine()
        if not line.isValid():
            break
        line.setLineWidth(width)
        line.setPosition(QtCore.QPointF(0, total))
        longest = max(longest, line.naturalTextWidth())
        total += line.height()
        lines += 1
        if total > 100000:      # plain-text sanity stop; never hit on a slide
            break
    lay.endLayout()
    return longest, int(total), lines


def _paint_height(font, text, width, flags):
    """Height the actual paint draws at this size (boundingRect, same flags)."""
    if width <= 0:
        return 0
    return QtGui.QFontMetrics(font).boundingRect(
        0, 0, width, 100000, flags, text).height()


def _autosize_default_verse(body_font, text, max_w, max_h, current, scale):
    """Largest default-verse size that still fits BOTH max_w and max_h.

    Two regimes, both bounded by the vertical ceiling (the largest
    size whose painted height fits max_h, so nothing ever clips):

    * Short verse (wrapped into at most 2 lines at the hand-off
      size): grow until the longest wrapped line reaches 95% of
      max_w. The one short size that keeps the text on a single line
      full-width can beat a bigger size that wraps to two narrow
      lines, so re-wrapping beats raw pixel size here.
    * Multi-line verse (3+ lines at the hand-off size): keep the
      vertical ceiling, so the block fills the whole available
      height while every wrapped line stays inside max_w. This is
      the EasyWorship look the user asked for: many large lines
      nearly filling the text area.

    Verified fact: the wrapped block height is non-decreasing in the
    size, so the vertical ceiling is found with a binary search.
    Paint parity uses the same boundingRect call _draw's fits()
    uses, so the ceiling can never paint taller than max_h.

    Only called for default (non-template) verse slides; templates
    and songs never reach this helper.
    """
    if max_w <= 0 or max_h <= 0 or not text:
        return current
    flags = QtCore.Qt.AlignCenter | QtCore.Qt.TextWordWrap
    _cache = {}
    def measures(size):
        if size not in _cache:
            _cache[size] = _wrapped_lines(body_font(size), text, max_w)
        return _cache[size]
    def fits(size):
        return _paint_height(body_font(size), text, max_w, flags) <= max_h

    # If even the hand-off size does not fit, rebase the search: a fallback
    # metric (e.g. a missing serif face on Windows) can make the hand-off
    # size fail fits(), and keeping it stranded there would under-fill the
    # whole height. The closest smaller bounding size that still fits is
    # both non-clipping and as full as clipping allows.
    if not fits(current):
        lo, hi, ceiling = 14, current - 1, current
        while lo <= hi:
            mid = (lo + hi) // 2
            if fits(mid):
                ceiling = mid
                lo = mid + 1
            else:
                hi = mid - 1
        return ceiling if ceiling < current else current

    # Vertical ceiling: the largest size that still fits max_h.
    # Height is non-decreasing in size, so binary search is exact.
    lo, hi, ceiling = current, max(current, int(max_h)), current
    while lo <= hi:
        mid = (lo + hi) // 2
        if fits(mid):
            ceiling = mid
            lo = mid + 1
        else:
            hi = mid - 1
    if ceiling <= current:
        return current

    # Multi-line verse: the vertical ceiling already fills the
    # available height with many wrapped lines; growing further
    # is impossible without clipping, so ceiling IS the answer.
    # The line count is also re-checked at the ceiling: a verse that
    # hands off as short may still wrap to 3+ lines up there, and the
    # ceiling is then the right full-height answer.
    if measures(current)[2] >= 3 or measures(ceiling)[2] >= 3:
        return ceiling

    # Primary aim: a short verse fills the width (>= 95%) at the
    # smallest such size that still fits; that is the first size
    # found descending from the ceiling when the full set of 95%
    # sizes is examined from the bottom up. Every candidate examined
    # fits, so width fill decides; longest-line fill is not monotonic
    # (rewrapping changes the lines), so walk UP from current and
    # remember the smallest size reaching 95%.
    target = None
    best_fill, best_size = 0.0, current
    for size in range(current + 1, ceiling + 1):
        fill = measures(size)[0] / max_w
        if fill > best_fill + 1e-9 or (fill == best_fill and size > best_size):
            best_fill, best_size = fill, size
        if fill >= 0.95:
            target = size
            break
    if target is not None:
        return target
    # No size reaches 95% width: take the largest size whose fill is
    # within 0.02 of the best fill seen (prefer bigger text on a near
    # tie), which keeps the width as full as re-wrapping allows.
    best, best_fill = current, measures(current)[0] / max_w
    for size in range(current + 1, ceiling + 1):
        fill = measures(size)[0] / max_w
        if fill >= best_fill - 0.02:
            best, best_fill = size, max(best_fill, fill)
    if best >= ceiling:
        return ceiling
    # A bigger size may still beat this one on fill (rewrap): take the
    # largest size that beats `best` on fill; if none does, grown size
    # can still be short of ceiling without losing fill.
    narrower = 0.0
    for size in range(current + 1, ceiling + 1):
        fill = measures(size)[0] / max_w
        if fill > narrower:
            narrower = fill
    if narrower > best_fill + 1e-9:
        for size in range(ceiling, current, -1):
            if measures(size)[0] / max_w > narrower - 1e-9:
                return size
    return best



class SlideView(QtWidgets.QWidget):
    """Draws one slide. Used by BOTH the projector window and the small in-app preview,
    so the preview is exactly what the audience sees (everything scales with the height)."""

    def __init__(self):
        super().__init__()
        self.ref = ""
        self.body = ""
        self.credit = ""
        self.live = False          # False = black screen
        self.theme = "navy"
        self.scale = 100
        self.show_ref = True
        self.font_family = "Georgia"
        self.bold = False
        self.bg_color = ""
        self.text_color = ""
        self.bg_spec = background.spec_from({})
        self.outline_on, self.outline_color, self.outline_px = False, "", 3
        self.song_custom = {}                    # per-template overrides (songs only)
        self.song_theme = songthemes.STANDARD   # used only when the slide is a song slide (meta is not None)
        self.verse_theme = versethemes.DEFAULT   # used only for verse slides (meta is None); 'default' = the old look
        self.meta = None                         # (title, artist, section, number, total) for song slides, else None
        self._bgp = background.Painter()

    # ---- content ----
    def set_content(self, ref, body, credit="", meta=None):
        self.ref, self.body, self.credit, self.meta = ref, body, credit, meta
        self.live = True
        self.update()

    def blank(self):
        self.live = False
        self.update()

    def set_style(self, theme, scale, show_ref, font_family="Georgia", bold=False, bg_color="", text_color="", bg_spec=None,
                  outline_on=False, outline_color="", outline_px=3, song_theme=songthemes.STANDARD, song_custom=None,
                  verse_theme=versethemes.DEFAULT):
        self.verse_theme = versethemes.clean(verse_theme)
        self.song_theme = songthemes.clean(song_theme)
        self.song_custom = songthemes.copy_custom(song_custom)
        self.outline_on, self.outline_color, self.outline_px = bool(outline_on), outline_color, outline_px
        self.theme, self.scale, self.show_ref = theme, scale, show_ref
        self.font_family, self.bold, self.bg_color, self.text_color = font_family, bold, bg_color, text_color
        self.bg_spec = bg_spec or background.spec_from({})
        self.update()

    # ---- drawing ----
    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        self._draw(p, self.rect())

    def snapshot(self, size):
        """The slide as it looks right now, drawn into a plain pixmap (used by transitions)."""
        pm = QtGui.QPixmap(size)
        p = QtGui.QPainter(pm)
        self._draw(p, QtCore.QRect(0, 0, size.width(), size.height()))
        p.end()
        return pm

    def _text(self, p, rect, flags, text, fg, h):
        """Draw text in the current font/pen colour, with an outline when switched on.
        The outline is the same text stamped in a ring around the real one (plain painting, works for
        wrapped text and on any background), then the text itself on top."""
        if self.outline_on:
            oc = QtGui.QColor(settings.resolve_outline(fg, self.outline_color))
            keep = p.pen()
            p.setPen(oc)
            for dx, dy in settings.outline_offsets(settings.outline_pixels(h, self.outline_px)):
                p.drawText(rect.translated(dx, dy), flags, text)
            p.setPen(keep)
        p.drawText(rect, flags, text)

    def _draw(self, p, rect):
        if self.live and self.body and self.meta is not None and self.song_theme in songthemes.TEMPLATES:
            p.setRenderHint(QtGui.QPainter.TextAntialiasing)
            p.setRenderHint(QtGui.QPainter.Antialiasing)
            return self._draw_song(p, rect, songthemes.resolve(self.song_theme, self.song_custom))
        if self.live and self.body and self.meta is None and self.verse_theme in versethemes.TEMPLATES:
            p.setRenderHint(QtGui.QPainter.TextAntialiasing)
            p.setRenderHint(QtGui.QPainter.Antialiasing)
            return self._draw_verse(p, rect, versethemes.resolve(self.verse_theme))
        kind = self.bg_spec[0]
        bg, fg, refc = settings.resolve_colors(self.theme, self.bg_color, self.text_color)
        if kind == "gradient":       # text colour follows the average of the two colours
            bg, fg, refc = settings.resolve_colors(self.theme, background.mix(self.bg_spec[1], self.bg_spec[2]), self.text_color)
        elif kind == "image" and background.load_image(self.bg_spec[4])[0] is not None:
            bg, fg, refc = settings.resolve_colors(self.theme, "#0b0f19", self.text_color)
            bg = self.bg_color if settings.valid_color(self.bg_color) else bg
        p.setRenderHint(QtGui.QPainter.TextAntialiasing)
        if not self.live or not self.body:
            p.fillRect(rect, QtGui.QColor("#000000"))
            return
        self._bgp.paint(p, rect, self.bg_spec, bg)
        w, h = rect.width(), rect.height()
        # Default (non-template) verses run nearly full-bleed like the
        # EasyWorship comparison: a 1.5% side margin and ~0.8% top/bottom
        # instead of the old 7%/6%, so text wins bigger lines and more of
        # the screen. Songs and other paths keep the old margins.
        is_default_verse = self.meta is None and self.verse_theme == versethemes.DEFAULT
        if is_default_verse:
            mx, my = int(w * 0.015), int(h * 0.008)
        else:
            mx, my = int(w * 0.07), int(h * 0.06)
        area = QtCore.QRect(mx, my, w - 2 * mx, h - 2 * my)
        ref_h = 0
        if self.show_ref and self.ref:
            f = QtGui.QFont("Segoe UI", 10)
            f.setBold(True)
            f.setPixelSize(max(14, int(h * 0.055 * self.scale / 100)))
            p.setFont(f)
            p.setPen(QtGui.QColor(refc))
            ref_h = QtGui.QFontMetrics(f).height() + int(h * 0.02)
            self._text(p, QtCore.QRect(area.x(), area.y() + area.height() - ref_h + int(h * 0.02),
                                       area.width(), ref_h), QtCore.Qt.AlignCenter, self.ref, refc, h)
        text_area = QtCore.QRect(area.x(), area.y(), area.width(), area.height() - ref_h)
        flags = QtCore.Qt.AlignCenter | QtCore.Qt.TextWordWrap

        def fits(size):
            f = self._body_font(size)
            r = QtGui.QFontMetrics(f).boundingRect(0, 0, text_area.width(), 100000, flags, self.body)
            return r.height() <= text_area.height()

        top = int(h * 0.12 * self.scale / 100)
        size = layout.fit_font_size(fits, 14, max(16, top))
        # Default verse look only (custom verse templates and song slides never reach
        # here): grow past the old 12%-of-height cap when a short verse fits
        # vertically anyway, so its longest wrapped line nearly fills the width.
        # The hard limit stays the vertical fit; a size that would clip vertically
        # is never picked. Songs keep the exact old sizing.
        if is_default_verse:
            size = _autosize_default_verse(self._body_font, self.body, text_area.width(),
                                           text_area.height(), size, self.scale)
        p.setFont(self._body_font(size))
        p.setPen(QtGui.QColor(fg))
        # Default verses paint vertically centred in their area so a grown
        # long verse sits in the middle of the full height (the EasyWorship
        # look) instead of hugging the top; other paths are unchanged.
        if is_default_verse:
            self._text(p, text_area, flags | QtCore.Qt.AlignVCenter, self.body, fg, h)
        else:
            self._text(p, text_area, flags, self.body, fg, h)
        if self.credit:
            # Never painted: the translation name and licence are operator-side
            # metadata (they stay in the pack and the operator's credit line),
            # not slide content. The credit text and the bottom-centre reference
            # both used to default to this same bottom band, so they overprinted
            # each other on every licensed translation.
            pass

    # ---- song templates (songs only; verses never come here) ----
    def _sfont(self, h, frac, bold=False, spacing=0.0, family="Segoe UI"):
        f = QtGui.QFont(family)
        f.setPixelSize(max(10, int(h * frac)))
        f.setBold(bold)
        if spacing:
            f.setLetterSpacing(QtGui.QFont.AbsoluteSpacing, spacing)
        return f

    def _paint_song_bg(self, p, rect, t):
        kind, c1, c2 = t["bg"]
        w, h = rect.width(), rect.height()
        if kind == "solid":
            p.fillRect(rect, QtGui.QColor(c1))
        elif kind == "radial":
            p.fillRect(rect, QtGui.QColor(c2))
            g = QtGui.QRadialGradient(w / 2.0, h * 0.5, max(w, h) * 0.65)
            g.setColorAt(0, QtGui.QColor(c1))
            g.setColorAt(1, QtGui.QColor(c2))
            p.fillRect(rect, QtGui.QBrush(g))
        else:
            g = QtGui.QLinearGradient(0, 0, w * 0.4, h)
            g.setColorAt(0, QtGui.QColor(c1))
            g.setColorAt(1, QtGui.QColor(c2))
            p.fillRect(rect, QtGui.QBrush(g))

    def _draw_song(self, p, rect, t):
        title, artist, section, num, total = self.meta
        w, h = rect.width(), rect.height()
        self._paint_song_bg(p, rect, t)
        txt, acc, lab, dim = (QtGui.QColor(t[k]) for k in ("text", "accent", "tag", "dim"))
        frame = t["frame"]
        A = QtCore.Qt
        h_al = {"left": A.AlignLeft, "center": A.AlignHCenter, "right": A.AlignRight}[t["align"]]
        sect = section.upper() if t["upper"] else section
        pad = int(h * 0.075)
        # frame / decoration
        if frame == "single":
            p.setBrush(A.NoBrush)
            c = QtGui.QColor(t["tag"])
            c.setAlphaF(0.8)
            p.setPen(QtGui.QPen(c, max(1, h * 0.004)))
            m = h * 0.04
            p.drawRoundedRect(QtCore.QRectF(m, m, w - 2 * m, h - 2 * m), h * 0.03, h * 0.03)
            pad = int(h * 0.11)
        elif frame == "bar":
            p.fillRect(QtCore.QRect(int(w * 0.06), int(h * 0.12), max(3, int(h * 0.012)), int(h * 0.76)), acc)
        elif frame == "card":
            p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 60), max(1, h * 0.002)))
            p.setBrush(QtGui.QColor(255, 255, 255, 28))
            p.drawRoundedRect(QtCore.QRectF(w * 0.06, h * 0.17, w * 0.88, h * 0.60), h * 0.04, h * 0.04)
            p.setBrush(A.NoBrush)
        left = int(w * (0.12 if frame == "bar" else 0.0)) + pad
        inner = QtCore.QRect(left, pad, w - left - pad, h - 2 * pad)
        # top section label
        label_h = int(h * 0.07) if t["show_label"] else int(h * 0.01)
        if t["show_label"]:
            p.setFont(self._sfont(h, 0.032, False, h * 0.008))
            p.setPen(lab)
            top_rect = QtCore.QRect(inner.x(), inner.y(), inner.width(), label_h)
            if t["pill"] and frame == "none":      # rounded tag on top
                fm = QtGui.QFontMetrics(p.font())
                tw = fm.horizontalAdvance(sect) if hasattr(fm, "horizontalAdvance") else fm.width(sect)
                tag_w = tw + h * 0.05
                x = {"left": inner.x(), "center": (w - tag_w) / 2.0, "right": inner.right() - tag_w}[t["align"]]
                tag = QtCore.QRectF(x, inner.y(), tag_w, label_h * 0.85)
                p.setPen(QtGui.QPen(lab, max(1, h * 0.002)))
                p.setBrush(QtGui.QColor(0, 0, 0, 50))
                p.drawRoundedRect(tag, tag.height() / 2, tag.height() / 2)
                p.setBrush(A.NoBrush)
                p.drawText(tag, A.AlignCenter, sect)
            else:
                p.drawText(top_rect, h_al | A.AlignVCenter, sect)
        # footer: rounded count chip and/or title line
        chip = bool(t["pill"] and frame in ("none", "card") and t["show_count"])
        show_title = bool(t["show_footer"])
        count_inline = bool(t["show_count"] and not chip and not (t["pill"] and frame in ("none", "card")))
        foot_h = int(h * 0.07) if (self.show_ref and (chip or show_title or count_inline)) else int(h * 0.01)
        foot = QtCore.QRect(inner.x(), inner.bottom() - foot_h, inner.width(), foot_h)
        if self.show_ref and foot_h > int(h * 0.02):
            f = self._sfont(h, 0.03)
            p.setFont(f)
            fm = QtGui.QFontMetrics(f)
            if chip:
                pill_s = songthemes.pill_text(self.meta) if t["show_label"] or True else ""
                pw = (fm.horizontalAdvance(pill_s) if hasattr(fm, "horizontalAdvance") else fm.width(pill_s)) + int(h * 0.05)
                px = foot.x() if t["align"] == "right" else foot.right() - pw
                pr = QtCore.QRectF(px, foot.y() + (foot_h - h * 0.05) / 2.0, pw, h * 0.05)
                p.setPen(QtGui.QPen(lab, max(1, h * 0.002)))
                p.setBrush(QtGui.QColor(0, 0, 0, 70))
                p.drawRoundedRect(pr, pr.height() / 2, pr.height() / 2)
                p.setBrush(A.NoBrush)
                p.setPen(txt)
                p.drawText(pr, A.AlignCenter, pill_s)
            if show_title or count_inline:
                parts = []
                if show_title:
                    parts.append(title + (" \u00b7 " + artist if artist else ""))
                if count_inline:
                    parts.append("%d/%d" % (num, total))
                line = " \u00b7 ".join(parts)
                if chip:       # chip takes one side, the title keeps the other
                    fl = A.AlignRight if t["align"] == "right" else A.AlignLeft
                    half = foot.adjusted(int(foot.width() * 0.3) if t["align"] == "right" else 0, 0,
                                         0 if t["align"] == "right" else -int(foot.width() * 0.3), 0)
                else:
                    fl, half = h_al, foot
                p.setPen(dim)
                p.drawText(half, fl | A.AlignVCenter, fm.elidedText(line, A.ElideRight, half.width()))
        # lyrics
        gap = int(h * 0.05) if t["divider"] else 0
        area = QtCore.QRect(inner.x() + (int(w * 0.03) if frame == "card" else 0), inner.y() + label_h + int(h * 0.02),
                            inner.width() - (int(w * 0.06) if frame == "card" else 0),
                            inner.height() - label_h - foot_h - int(h * 0.04))
        lines = self.body.split("\n")
        blocks = [self.body]
        if t["two_tone"] and len(lines) > 1:
            blocks = [lines[0], "\n".join(lines[1:])]
        flags = h_al | A.AlignVCenter | A.TextWordWrap
        fam = t["font"] or self.font_family
        bold = bool(t["bold"])

        def sbody(size):
            f = self._body_font(size, bold, fam)
            return f

        def heights(size):
            fm = QtGui.QFontMetrics(sbody(size))
            return [fm.boundingRect(0, 0, area.width(), 100000, flags, b).height() for b in blocks]

        def fits(size):
            hs = heights(size)
            return sum(hs) + (gap if len(hs) > 1 else 0) <= area.height()

        size = layout.fit_font_size(fits, 14, max(16, int(h * 0.1 * self.scale / 100 * t["scale"] / 100)))
        hs = heights(size)
        total_h = sum(hs) + (gap if len(hs) > 1 else 0)
        free = area.height() - total_h
        y = area.y() + {"top": 0, "middle": free // 2, "bottom": max(0, free)}[t["valign"]]
        p.setFont(sbody(size))

        def divider_at(cy):
            g = QtGui.QLinearGradient(w / 2.0 - w * 0.09, 0, w / 2.0 + w * 0.09, 0)
            c0 = QtGui.QColor(t["tag"])
            c0.setAlpha(0)
            g.setColorAt(0, c0)
            g.setColorAt(0.5, QtGui.QColor(t["tag"]))
            g.setColorAt(1, c0)
            p.fillRect(QtCore.QRectF(w / 2.0 - w * 0.09, cy, w * 0.18, max(1, h * 0.003)), QtGui.QBrush(g))

        for i, b in enumerate(blocks):
            r = QtCore.QRect(area.x(), y, area.width(), hs[i])
            col = txt if i == 0 else acc
            if t["shadow"]:
                p.setPen(QtGui.QColor(0, 0, 0, 140))
                p.drawText(r.translated(0, max(1, int(h * 0.004))), flags, b)
            p.setPen(col)
            self._text(p, r, flags, b, col.name(), h)
            y += hs[i]
            if i == 0 and len(blocks) > 1:
                if t["divider"]:
                    divider_at(y + gap // 2)
                y += gap
        if len(blocks) == 1 and t["divider"]:     # one block: divider under the words, inside the free space
            cy = y + int(h * 0.015)
            if cy < area.bottom():
                divider_at(cy)

    # ---- verse templates (verses only; songs never come here) ----
    def _draw_verse(self, p, rect, t):
        w, h = rect.width(), rect.height()
        A = QtCore.Qt
        self._paint_song_bg(p, rect, t)       # same painted backgrounds as the song templates
        acc, dim = QtGui.QColor(t["accent"]), QtGui.QColor(t["dim"])
        frame = t["frame"]
        pad = int(h * 0.09)
        left = pad
        if frame == "single":
            p.setBrush(A.NoBrush)
            c = QtGui.QColor(t["accent"])
            c.setAlphaF(0.85)
            p.setPen(QtGui.QPen(c, max(1, h * 0.004)))
            m = h * 0.04
            p.drawRoundedRect(QtCore.QRectF(m, m, w - 2 * m, h - 2 * m), h * 0.03, h * 0.03)
            pad = int(h * 0.12)
            left = pad
        elif frame == "double":
            p.setBrush(A.NoBrush)
            c = QtGui.QColor(t["accent"])
            p.setPen(QtGui.QPen(c, max(2, h * 0.006)))
            m = h * 0.035
            p.drawRect(QtCore.QRectF(m, m, w - 2 * m, h - 2 * m))
            p.setPen(QtGui.QPen(c, max(1, h * 0.002)))
            m2 = h * 0.05
            p.drawRect(QtCore.QRectF(m2, m2, w - 2 * m2, h - 2 * m2))
            pad = int(h * 0.13)
            left = pad
        elif frame == "bar":
            p.fillRect(QtCore.QRect(int(w * 0.06), int(h * 0.12), max(3, int(h * 0.012)), int(h * 0.76)), acc)
            left = int(w * 0.12)
        elif frame == "card":
            p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 60), max(1, h * 0.002)))
            p.setBrush(QtGui.QColor(255, 255, 255, 28))
            p.drawRoundedRect(QtCore.QRectF(w * 0.06, h * 0.10, w * 0.88, h * 0.70), h * 0.04, h * 0.04)
            p.setBrush(A.NoBrush)
            pad = int(h * 0.15)
            left = int(w * 0.10)
        inner = QtCore.QRect(left, pad if frame != "card" else int(h * 0.13), w - left - (pad if frame != "bar" else int(w * 0.07)),
                             h - 2 * pad if frame != "card" else int(h * 0.64))
        h_al = {"left": A.AlignLeft, "center": A.AlignHCenter, "right": A.AlignRight}[t["align"]]
        # reference block (top or bottom); the Settings switch 'show verse reference' still applies
        ref_h = 0
        show_ref = bool(self.show_ref and self.ref)
        pill = t["ref_style"] == "pill"
        rf = QtGui.QFont("Segoe UI")
        rf.setBold(True)
        rf.setPixelSize(max(14, int(h * 0.05 * self.scale / 100)))
        fm = QtGui.QFontMetrics(rf)
        if show_ref:
            ref_h = fm.height() + int(h * (0.05 if t["divider"] or pill else 0.03))
        top = t["ref_pos"] == "top"
        ref_rect = QtCore.QRect(inner.x(), inner.y() if top else inner.bottom() - ref_h, inner.width(), ref_h)
        body_area = QtCore.QRect(inner.x(), inner.y() + (ref_h if top else 0), inner.width(), inner.height() - ref_h)
        flags = h_al | A.AlignVCenter | A.TextWordWrap

        def fits(size):
            r = QtGui.QFontMetrics(self._body_font(size)).boundingRect(0, 0, body_area.width(), 100000, flags, self.body)
            return r.height() <= body_area.height()

        size = layout.fit_font_size(fits, 14, max(16, int(h * 0.11 * self.scale / 100)))
        p.setFont(self._body_font(size))
        if t["shadow"]:
            p.setPen(QtGui.QColor(0, 0, 0, 140))
            p.drawText(body_area.translated(0, max(1, int(h * 0.004))), flags, self.body)
        p.setPen(QtGui.QColor(t["text"]))
        self._text(p, body_area, flags, self.body, t["text"], h)
        if show_ref:
            p.setFont(rf)
            if pill:
                tw = fm.horizontalAdvance(self.ref) if hasattr(fm, "horizontalAdvance") else fm.width(self.ref)
                pw, ph = tw + h * 0.07, fm.height() + h * 0.02
                x = {"left": inner.x(), "center": inner.x() + (inner.width() - pw) / 2.0, "right": inner.right() - pw}[t["align"]]
                y = ref_rect.y() + (h * 0.005 if top else ref_rect.height() - ph)
                pr = QtCore.QRectF(x, y, pw, ph)
                p.setPen(QtGui.QPen(acc, max(1, h * 0.002)))
                p.setBrush(QtGui.QColor(0, 0, 0, 60))
                p.drawRoundedRect(pr, ph / 2, ph / 2)
                p.setBrush(A.NoBrush)
                p.setPen(acc)
                p.drawText(pr, A.AlignCenter, self.ref)
            else:
                if t["divider"]:
                    g = QtGui.QLinearGradient(w / 2.0 - w * 0.09, 0, w / 2.0 + w * 0.09, 0)
                    c0 = QtGui.QColor(t["accent"])
                    c0.setAlpha(0)
                    g.setColorAt(0, c0)
                    g.setColorAt(0.5, acc)
                    g.setColorAt(1, c0)
                    cy = ref_rect.bottom() - ref_h + int(h * 0.01) if not top else ref_rect.bottom() - int(h * 0.01)
                    if not top:
                        cy = ref_rect.y() + int(h * 0.005)
                    p.fillRect(QtCore.QRectF(w / 2.0 - w * 0.09, cy, w * 0.18, max(1, h * 0.003)), QtGui.QBrush(g))
                    ref_rect = ref_rect.adjusted(0, int(h * 0.02) if not top else 0, 0, 0 if not top else -int(h * 0.02))
                p.setPen(acc)
                self._text(p, ref_rect, h_al | A.AlignVCenter, self.ref, t["accent"], h)
        if self.credit:
            # Never painted: same rule as the default verse path above.
            pass

    def _body_font(self, size, bold=None, family=None):
        fam = family or self.font_family or "Georgia"
        f = QtGui.QFont(fam)
        if hasattr(f, "setFamilies"):      # Qt 5.13+: a missing font falls back to Georgia, then Arial
            f.setFamilies([fam, "Georgia", "Arial"])
        f.setPixelSize(size)
        f.setBold(self.bold if bold is None else bold)
        return f

    def resizeEvent(self, e):
        self.update()
        super().resizeEvent(e)


class PreviewView(SlideView):
    """Small 16:9 preview inside the operator window. Always shows the selected verse
    (even when the projector is black), with a red frame while it is live."""

    def __init__(self):
        super().__init__()
        self.on_air = False
        self.setMinimumSize(320, 180)
        sp = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        sp.setHeightForWidth(True)
        self.setSizePolicy(sp)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, w):
        return layout.height_for_width(w)

    def sizeHint(self):
        return QtCore.QSize(400, layout.height_for_width(400))

    def show_slide(self, ref, body, credit="", meta=None):
        self.ref, self.body, self.credit, self.meta = ref, body, credit, meta
        self.live = bool(body)
        self.update()

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QtGui.QPainter(self)
        p.setPen(QtGui.QPen(QtGui.QColor(C.accent if self.on_air else "#334155"), 3 if self.on_air else 1))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))


class ProjectionWindow(SlideView):
    offRequested = QtCore.pyqtSignal()       # Esc pressed while this window has the keyboard
    projectRequested = QtCore.pyqtSignal()   # F5 pressed while this window has the keyboard
    closedByUser = QtCore.pyqtSignal()       # window closed some other way (Alt+F4, taskbar)
    frameChanged = QtCore.pyqtSignal()       # anything the window would repaint (content, style, transition frame, show/hide)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("RevelateTW Lite - Projection")
        self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.FramelessWindowHint)
        self.resize(960, 540)
        self.setCursor(QtCore.Qt.BlankCursor)
        self._tx = None        # running transition: dict(effect, direction, old, new, p, after)
        self._anim = None
        self._old_was_live = False
        self.mirror_size = QtCore.QSize()   # size of the Programs box (set by ProgramsView); never used for the real output

    # ---- 'Programs' mirror: signal only, no polling, no screenshots ----
    def update(self, *a):
        super().update(*a)
        self.frameChanged.emit()

    def showEvent(self, e):
        super().showEvent(e)
        self.frameChanged.emit()

    def hideEvent(self, e):
        super().hideEvent(e)
        self.frameChanged.emit()

    def on_air(self):
        """True only while the full-screen window is really showing something."""
        return bool(self.live and self.isVisible())

    # ---- transitions (only this window; the in-app preview is never animated) ----
    @property
    def transitioning(self):
        return self._tx is not None

    def finish_transition(self):
        """Jump to the end of a running transition (also runs its 'after' step, e.g. hide)."""
        tx, self._tx = self._tx, None
        if self._anim is not None:
            a, self._anim = self._anim, None
            a.stop()
            a.deleteLater()
        if tx is not None:
            self.update()
            if tx.get("after"):
                tx["after"]()

    def transition(self, plan, change, after=None):
        """Run change() (which applies the new content / shows the window) with an animation.
        old picture = what is on screen now (black if the window is hidden); new = after change().
        after() runs when the animation ends (immediately for an instant plan)."""
        self.finish_transition()
        self._old_was_live = bool(self.live and self.isVisible())
        old = self.snapshot(self.size()) if self._old_was_live else None
        view = getattr(self, "mirror_view", None)
        if view is not None:                       # read the live box size, never a stale one
            self.mirror_size = QtCore.QSize(view.width(), view.height())
        msize = QtCore.QSize(self.mirror_size)
        m_old = None
        if plan.animated:
            # the Programs box gets its OWN pictures, drawn with the same slide layout as the TV preview
            # at the box's own size, so no transition frame is ever the projector's shape
            if self._old_was_live and msize.isValid() and msize.width() > 0 and msize.height() > 0:
                m_old = self.snapshot(msize)
            self._tx = {"old": old, "new": None, "p": 0.0, "effect": plan.effect,
                        "direction": plan.direction, "after": after,
                        "m_size": msize, "m_old": m_old, "m_new": None}
        change()
        if not plan.animated:
            if after:
                after()
            return
        size = self.size()
        if old is None:
            old = QtGui.QPixmap(size)
            old.fill(QtGui.QColor("#000000"))
        self._tx["old"] = old
        self._tx["new"] = self.snapshot(size)
        if msize.isValid() and msize.width() > 0 and msize.height() > 0:
            if m_old is None:
                m_old = QtGui.QPixmap(msize)
                m_old.fill(QtGui.QColor("#000000"))
            self._tx["m_old"] = m_old
            self._tx["m_new"] = self.snapshot(msize)
        a = QtCore.QVariantAnimation(self)
        a.setStartValue(0.0)
        a.setEndValue(1.0)
        a.setDuration(plan.ms)
        a.valueChanged.connect(self._tx_step)
        a.finished.connect(self.finish_transition)
        self._anim = a
        a.start()
        self.update()

    def resizeEvent(self, e):
        tx = self._tx
        if tx is not None and tx.get("new") is not None and self.width() > 0 and self.height() > 0:
            tx["new"] = self.snapshot(self.size())      # went full screen mid-animation: redraw crisp
            if tx["old"] is not None and tx["old"].size() != self.size() and not self._old_was_live:
                tx["old"] = QtGui.QPixmap(self.size())
                tx["old"].fill(QtGui.QColor("#000000"))
        super().resizeEvent(e)

    def refit_mirror_pictures(self):
        """Programs box changed size while a transition is running: redraw its pictures at the new size."""
        tx = self._tx
        ms = self.mirror_size
        if tx is None or tx.get("m_new") is None or not ms.isValid() or ms.width() <= 0 or ms.height() <= 0:
            return
        if tx["m_new"].size() == ms:
            return
        tx["m_new"] = self.snapshot(ms)
        if tx.get("m_old") is not None and tx["m_old"].size() != ms:
            if self._old_was_live:
                tx["m_old"] = tx["m_old"].scaled(ms, QtCore.Qt.IgnoreAspectRatio, QtCore.Qt.SmoothTransformation)
            else:
                tx["m_old"] = QtGui.QPixmap(ms)
                tx["m_old"].fill(QtGui.QColor("#000000"))
        tx["m_size"] = ms

    def _tx_step(self, v):
        if self._tx is not None:
            self._tx["p"] = transitions.ease(float(v))
            self.update()

    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        self.render_frame(p, self.rect())

    def render_frame(self, p, r):
        """Paint exactly what this window shows (slide, black, or the running transition frame) into
        rect r. The window itself and the 'Programs' mirror both use this, so they cannot disagree."""
        p.save()
        p.translate(r.x(), r.y())
        p.setClipRect(QtCore.QRect(0, 0, r.width(), r.height()))
        try:
            self._render_local(p, QtCore.QRect(0, 0, r.width(), r.height()))
        finally:
            p.restore()

    def render_frame_adaptive(self, p, r):
        """Paint what this window shows into rect r, ADAPTING to r's own shape (used by Programs).

        A still slide is drawn straight into r, exactly the way the in-app TV preview draws it:
        the slide engine scales to the height of the rectangle it is given, so the slide fills
        its box without stretching the text. A running transition is drawn from pictures that were
        rendered at the Programs box's own size with that same slide layout (never the projector's
        shape), so every frame, first to last, fills the box with no black side bars. The real
        projector keeps its own native-size frames (render_frame).
        """
        tx = self._tx
        p.save()
        p.translate(r.x(), r.y())
        p.setClipRect(QtCore.QRect(0, 0, r.width(), r.height()))
        try:
            local = QtCore.QRect(0, 0, r.width(), r.height())
            if tx is None:
                self._draw(p, local)
            else:
                old, new = tx.get("m_old"), tx.get("m_new")
                if old is None and new is None and tx.get("old") is not None:
                    old = self._mirror_pic(tx, "old", local)     # no box pictures yet: never show the projector shape
                if new is None and tx.get("new") is not None:
                    new = self._mirror_pic(tx, "new", local)
                if old is not None and old.size() != local.size():
                    old = old.scaled(local.size(), QtCore.Qt.IgnoreAspectRatio, QtCore.Qt.SmoothTransformation)
                if new is not None and new.size() != local.size():
                    new = self.snapshot(local.size()) if tx.get("m_new") is not None else \
                        new.scaled(local.size(), QtCore.Qt.IgnoreAspectRatio, QtCore.Qt.SmoothTransformation)
                self._render_local(p, local, old, new)
        finally:
            p.restore()

    def _mirror_pic(self, tx, key, local):
        """Fallback only (Programs size unknown when the transition began): stretch the projector picture to the box."""
        pm = tx.get(key)
        if pm is None:
            return None
        return pm.scaled(local.size(), QtCore.Qt.IgnoreAspectRatio, QtCore.Qt.SmoothTransformation)

    def fit_rect(self, r):
        """The projector's own shape, fitted inside rect r (letterboxed if the shapes differ)."""
        pw, ph = max(1, self.width()), max(1, self.height())
        if r.width() * ph >= r.height() * pw:
            h = max(1, r.height())
            w = max(1, h * pw // ph)
            return QtCore.QRect(r.x() + (r.width() - w) // 2, r.y(), w, h)
        w = max(1, r.width())
        h = max(1, w * ph // pw)
        return QtCore.QRect(r.x(), r.y() + (r.height() - h) // 2, w, h)

    def _render_local(self, p, r, old=None, new=None):
        tx = self._tx
        if tx is None:
            return self._draw(p, r)
        w, h = r.width(), r.height()
        p.fillRect(r, QtGui.QColor("#000000"))
        pr, d = tx["p"], tx["direction"]
        if old is None and new is None:
            old, new = tx["old"], tx["new"]
        if old is None:      # first frame of a show: black, nothing leaks before the animation starts
            return
        eff = tx["effect"]
        if new is None:
            p.drawPixmap(r, old)
        elif eff == "fade":
            a_old, a_new = transitions.fade_alphas(pr)
            p.setOpacity(a_old)
            p.drawPixmap(r, old)
            p.setOpacity(a_new)
            p.drawPixmap(r, new)
        elif eff == "dissolve":
            p.drawPixmap(r, old)
            p.setOpacity(transitions.dissolve_alpha(pr))
            p.drawPixmap(r, new)
        elif eff == "slide":
            (ox, oy), (nx, ny) = transitions.slide_offsets(d, w, h, pr)
            p.drawPixmap(QtCore.QRect(ox, oy, w, h), old)
            p.drawPixmap(QtCore.QRect(nx, ny, w, h), new)
        elif eff == "zoom":
            (os_, oa), (ns, na) = transitions.zoom_states(pr)
            for pm, sc, al in ((old, os_, oa), (new, ns, na)):
                if al > 0:
                    p.setOpacity(al)
                    zw, zh = int(round(w * sc)), int(round(h * sc))
                    p.drawPixmap(QtCore.QRect((w - zw) // 2, (h - zh) // 2, zw, zh), pm)
        elif eff in ("checkerboard", "mosaic"):      # many small squares of the new picture over the old one
            p.drawPixmap(r, old)
            tiles = (transitions.checkerboard_rects(w, h, pr) if eff == "checkerboard"
                     else transitions.mosaic_rects(w, h, pr))
            for x, y, rw, rh in tiles:
                if rw > 0 and rh > 0:
                    p.drawPixmap(x, y, new, x, y, rw, rh)
        else:                # wipe, blinds, open, diagonal, iris, clock: new picture shown through a clip over the old one
            p.drawPixmap(r, old)
            if eff == "wipe":
                rects = [transitions.wipe_rect(d, w, h, pr)]
            elif eff == "blinds":
                rects = transitions.blinds_rects(d, w, h, pr)
            elif eff in ("diagonal", "iris", "clock"):
                path = QtGui.QPainterPath()
                if eff == "diagonal":
                    pts = transitions.diagonal_polygon(d, w, h, pr)
                    if len(pts) >= 3:
                        path.addPolygon(QtGui.QPolygonF([QtCore.QPointF(x, y) for x, y in pts]))
                elif eff == "iris":
                    cx, cy, rad = transitions.iris_circle(w, h, pr)
                    if rad > 0:
                        path.addEllipse(QtCore.QPointF(cx, cy), rad, rad)
                else:
                    deg = transitions.clock_degrees(pr)
                    if deg > 0:
                        rad = transitions.iris_circle(w, h, 1)[2]
                        path.moveTo(w / 2.0, h / 2.0)
                        path.arcTo(QtCore.QRectF(w / 2.0 - rad, h / 2.0 - rad, 2 * rad, 2 * rad), 90, -deg)
                        path.closeSubpath()
                if not path.isEmpty():
                    p.setClipPath(path)
                    p.drawPixmap(r, new)
                return
            else:
                rects = [transitions.open_rect(d, w, h, pr)]
            reg = QtGui.QRegion()
            for x, y, rw, rh in rects:
                if rw > 0 and rh > 0:
                    reg = reg.united(QtGui.QRegion(x, y, rw, rh))
            p.setClipRegion(reg)
            p.drawPixmap(r, new)

    # ---- keys: the full-screen window takes the keyboard, so Esc/F5 must work here too ----
    def keyPressEvent(self, e):
        mods = e.modifiers() & ~QtCore.Qt.KeypadModifier
        if e.key() == QtCore.Qt.Key_Escape:
            self.offRequested.emit()
        elif e.key() == QtCore.Qt.Key_F5:
            self.projectRequested.emit()
        elif mods & QtCore.Qt.ControlModifier and e.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            # Alternate Project shortcut for laptops whose bare F5 is a media key
            # (volume/speaker) intercepted before the app ever sees it.
            self.projectRequested.emit()
        else:
            super().keyPressEvent(e)

    def closeEvent(self, e):
        self._tx_after_cancel()
        e.accept()
        self.closedByUser.emit()

    def _tx_after_cancel(self):
        """Window is closing: drop a running transition without running its after-step."""
        if self._tx is not None:
            self._tx["after"] = None
        self.finish_transition()

    # ---- placing on a monitor ----
    def screen_rects(self):
        return [(s.geometry().x(), s.geometry().y(), s.geometry().width(), s.geometry().height())
                for s in QtWidgets.QApplication.screens()]

    def open_on(self, wanted=-1, primary_window=None):
        """Show full screen on the chosen display. Returns (index, extended)."""
        app = QtWidgets.QApplication
        screens = app.screens()
        rects = self.screen_rects()
        primary = screens.index(app.primaryScreen()) if app.primaryScreen() in screens else 0
        if primary_window is not None and primary_window.windowHandle() is not None:
            cur = primary_window.windowHandle().screen()
            if cur in screens:
                primary = screens.index(cur)
        idx, ext = layout.pick_display(rects, primary, wanted)
        g = screens[idx].geometry()
        self.setGeometry(g)
        self.show()
        if self.windowHandle() is not None:
            self.windowHandle().setScreen(screens[idx])
        self.setGeometry(g)
        if ext or len(screens) == 1:
            self.showFullScreen()
        else:
            self.showNormal()   # only one screen: do not cover the operator window
            self.resize(960, 540)
        return idx, ext


class ProgramsView(QtWidgets.QWidget):
    """Read-only mirror of the REAL projector window ('Programs'). It never holds slide content of its
    own: every repaint asks the projector to draw its current frame (including a running transition)
    into this widget, scaled to the projector's own shape. Repaints are driven by the projector's
    frameChanged signal only (no timer, no screen capture). Hidden projector = black 'Projection off'."""

    def __init__(self, proj):
        super().__init__()
        self.proj = proj
        self.setMinimumSize(320, 180)
        self.setFocusPolicy(QtCore.Qt.NoFocus)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)   # not interactive
        sp = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        sp.setHeightForWidth(True)
        self.setSizePolicy(sp)
        proj.frameChanged.connect(self._on_frame)
        self._sync_size()

    def _sync_size(self):
        """Tell the projector how big this box is, so transitions are drawn for THIS box (Programs only)."""
        self.proj.mirror_view = self
        self.proj.mirror_size = QtCore.QSize(self.width(), self.height())
        self.proj.refit_mirror_pictures()

    def _on_frame(self):
        self.update()

    def resizeEvent(self, e):
        self._sync_size()
        super().resizeEvent(e)

    def showEvent(self, e):
        self._sync_size()
        super().showEvent(e)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, w):
        return layout.height_for_width(w)

    def sizeHint(self):
        return QtCore.QSize(400, layout.height_for_width(400))

    def screen_rect(self):
        """The whole inner display area: a still slide adapts to this widget's own shape, the same
        way the in-app TV preview does (the slide engine scales to the height of the rect it is
        given, so the slide fills the box without distorting the text). A running transition is
        drawn from pictures rendered at this box's own size (same layout as a still slide)."""
        return self.rect()

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.fillRect(self.rect(), QtGui.QColor("#000000"))
        if not self.proj.isVisible():
            p.setPen(QtGui.QColor("#64748b"))
            p.drawText(self.rect(), QtCore.Qt.AlignCenter, "Projection off")
            return
        self.proj.render_frame_adaptive(p, self.screen_rect())
