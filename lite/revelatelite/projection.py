"""The projection window: borderless, goes to the extended display, auto-sizes the verse."""
from PyQt5 import QtCore, QtGui, QtWidgets

from revelatetw.ui_tokens import COLORS as C

from . import background, layout, settings, songthemes, timer as timermod, transitions, versethemes


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
        self.timer_snap = None                    # timer.py snapshot dict, or None (verses/songs unchanged)
        self.meta = None                         # (title, artist, section, number, total) for song slides, else None
        self._bgp = background.Painter()
        self._fall_prev_text = ""
        self._fall_old_text = ""
        self._fall_frames = None
        self._fall_elapsed = None
        self._fall_timer = QtCore.QTimer(self)
        self._fall_timer.setInterval(16)
        self._fall_timer.timeout.connect(self._step_fall)

    # ---- falling digit animation (timer digital only) ----
    def _step_fall(self):
        if self._fall_elapsed is None:
            return
        try:
            t_ms = self._fall_elapsed.elapsed()
        except Exception:
            t_ms = timermod.FALL_DURATION_MS
        if t_ms >= timermod.FALL_DURATION_MS:
            self._fall_frames = None
            self._fall_timer.stop()
            self._fall_elapsed = None
        else:
            self._fall_frames = timermod.falling_centers(self._fall_old_text, self._fall_prev_text, t_ms)
        self.update()

    def _begin_fall(self, old_text, new_text):
        """Start a falling-digit animation from old_text to new_text."""
        if old_text == new_text:
            self._fall_frames = None
            self._fall_prev_text = str(new_text)
            return
        from PyQt5.QtCore import QElapsedTimer
        self._fall_old_text = str(old_text)
        self._fall_prev_text = str(new_text)
        self._fall_elapsed = QElapsedTimer()
        self._fall_elapsed.start()
        self._fall_frames = timermod.falling_centers(old_text, new_text, 0)
        if not self._fall_timer.isActive():
            self._fall_timer.start()

    # ---- content ----
    def set_content(self, ref, body, credit="", meta=None):
        self.ref, self.body, self.credit, self.meta = ref, body, credit, meta
        if meta is not None or body:
            self.timer_snap = None   # timer state never rides along with a verse/song slide
        self.live = True
        self.update()

    def set_timer(self, snap):
        """Timer tab slide. snap is timer.py's snapshot dict (text/marker/message...)."""
        old_text = ""
        try:
            old_text = str((self.timer_snap or {}).get("text", "")) if self.timer_snap else ""
        except Exception:
            old_text = ""
        new_text = str((snap or {}).get("text", ""))
        self.timer_snap = snap
        self.meta = None
        self.live = True
        if snap and snap.get("style") != "analog" and old_text and new_text and timermod.digit_changed(old_text, new_text):
            self._begin_fall(old_text, new_text)
        elif snap:
            self._fall_frames = None
            self._fall_prev_text = new_text
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
        if self.live and self.timer_snap is not None:
            p.setRenderHint(QtGui.QPainter.TextAntialiasing)
            p.setRenderHint(QtGui.QPainter.Antialiasing)
            return self._draw_timer(p, rect)
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

    def _draw_timer(self, p, rect):
        snap = self.timer_snap or {}
        t = timermod.resolve(snap.get("template", timermod.DEFAULT),
                             snap.get("text_color", ""), snap.get("bg_color", ""),
                             speaker_label_color=snap.get("speaker_label_color", ""),
                             speaker_name_color=snap.get("speaker_name_color", ""))
        w, h = rect.width(), rect.height()
        kind, c1, c2 = t["bg"]
        if kind == "solid":
            p.fillRect(rect, QtGui.QColor(c1))
        else:
            g = QtGui.QLinearGradient(0, 0, w * 0.4, h)
            g.setColorAt(0, QtGui.QColor(c1))
            g.setColorAt(1, QtGui.QColor(c2))
            p.fillRect(rect, QtGui.QBrush(g))
        txt, acc, dim = (QtGui.QColor(t[k]) for k in ("text", "accent", "dim"))
        show_shape = snap.get("show_shape", True)
        if show_shape is None:
            show_shape = True
        show_shape = bool(show_shape)
        if show_shape and t["frame"] == "card":
            p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 60), max(1, h * 0.002)))
            p.setBrush(QtGui.QColor(255, 255, 255, 28))
            p.drawRoundedRect(QtCore.QRectF(w * 0.08, h * 0.22, w * 0.84, h * 0.56), h * 0.04, h * 0.04)
            p.setBrush(QtCore.Qt.NoBrush)
        text = str(snap.get("text", "00:00"))
        marker = str(snap.get("marker", ""))
        # Generic CLOCK/COUNTDOWN captions and RUNNING/PAUSED state are never
        # drawn, even if an older snapshot still carries them; only the
        # operator's own core message joins the time/countdown on screen.
        message = str(timermod.clean_message(snap.get("message", "")))
        family = timermod.clean_font(snap.get("font_family", ""))
        dl = timermod.digital_layout(w, h, marker=marker,
                                     show_shape=show_shape,
                                     text_scale=snap.get("text_scale", 100))
        style = snap.get("style", "digital")
        dial = snap.get("dial") or {}
        if style == "analog" and dial:
            import math
            # Shared, tested geometry: dial has its own upper band; the
            # digits/marker and the message sit below the dial + arc and
            # never overlap numerals, hands, or the ring.
            lay = timermod.analog_layout(w, h, has_subtext=bool(message or marker))
            cx, cy, r, arc_r = lay["cx"], lay["cy"], lay["r"], lay["arc_r"]
            digits_rect = lay["digits_rect"]
            message_rect = lay["message_rect"]
            p.setRenderHint(QtGui.QPainter.Antialiasing)
            p.setPen(QtGui.QPen(acc, max(2, int(r * 0.02))))
            p.setBrush(QtGui.QColor(255, 255, 255, 20))
            p.drawEllipse(QtCore.QRectF(cx - r, cy - r, r * 2, r * 2))
            p.setBrush(QtCore.Qt.NoBrush)
            # Draw the drain arc (countdown only) behind the dial edge so
            # it stays visible; it is outside the digits band.
            if snap.get("mode") == "countdown":
                try:
                    frac_left = float(dial.get("fraction", 0.0))
                except (TypeError, ValueError):
                    frac_left = 0.0
                frac_left = max(0.0, min(1.0, frac_left))
                if frac_left > 0.0:
                    p.setPen(QtGui.QPen(acc, max(3, int(r * 0.035))))
                    p.drawArc(QtCore.QRectF(cx - arc_r, cy - arc_r, arc_r * 2, arc_r * 2),
                              -90 * 16, int(-360 * frac_left * 16))
            tf = QtGui.QFont(family)
            tf.setPixelSize(max(8, int(r * 0.14)))
            p.setFont(tf)
            p.setPen(dim)
            for hr in range(1, 13):
                a = math.radians(hr * 30)
                x = cx + math.sin(a) * r * 0.82
                y = cy - math.cos(a) * r * 0.82
                p.drawText(QtCore.QRectF(x - r * 0.12, y - r * 0.08, r * 0.24, r * 0.16),
                           QtCore.Qt.AlignCenter, str(hr))
            def hand(value, total, length, width, colour):
                ang = (value / float(total)) * 360.0 if total else 0.0
                rad = math.radians(ang)
                p.setPen(QtGui.QPen(colour, max(2, int(r * width))))
                p.drawLine(int(cx), int(cy), int(cx + math.sin(rad) * length), int(cy - math.cos(rad) * length))
            # Standard wall clock, three clearly distinct hands:
            # short thick = hour, medium = minute, thin + accent = second.
            hand(dial.get("hour", 0), 12, r * 0.48, 0.045, txt)
            hand(dial.get("minute", 0), 60, r * 0.72, 0.030, txt)
            hand(dial.get("second", 0), 60, r * 0.82, 0.014, acc)
            p.setPen(acc)
            p.drawEllipse(QtCore.QRectF(cx - r * 0.04, cy - r * 0.04, r * 0.08, r * 0.08))
            # Time mode shows the full digital readout (time plus AM/PM when
            # the 12-hour format is on) in digits_rect, directly below the
            # dial, so viewers can read the analog hands at a glance. The
            # marker alone is never drawn there any more. Countdown digits
            # (time LEFT) and the message keep their own bands below.
            if snap.get("mode") == "countdown":
                df = QtGui.QFont(family)
                df.setBold(True)
                # Largest size that fits the digits rect both ways.
                frac = 0.13
                while frac > 0.04:
                    df.setPixelSize(max(10, int(h * frac)))
                    fm = QtGui.QFontMetrics(df)
                    if fm.horizontalAdvance(text) <= digits_rect[2] * 0.92 and fm.height() <= digits_rect[3]:
                        break
                    frac -= 0.01
                p.setFont(df)
                p.setPen(txt)
                p.drawText(QtCore.QRect(int(digits_rect[0]), int(digits_rect[1]),
                                        int(digits_rect[2]), int(digits_rect[3])),
                           QtCore.Qt.AlignCenter | QtCore.Qt.AlignVCenter, text)
            else:
                readout = timermod.analog_time_readout(text, marker)
                if readout:
                    df = QtGui.QFont(family)
                    df.setBold(True)
                    # Largest size that fits the digits rect both ways.
                    frac = 0.13
                    while frac > 0.04:
                        df.setPixelSize(max(10, int(h * frac)))
                        fm = QtGui.QFontMetrics(df)
                        if fm.horizontalAdvance(readout) <= digits_rect[2] * 0.92 and fm.height() <= digits_rect[3]:
                            break
                        frac -= 0.01
                    p.setFont(df)
                    p.setPen(txt)
                    p.drawText(QtCore.QRect(int(digits_rect[0]), int(digits_rect[1]),
                                            int(digits_rect[2]), int(digits_rect[3])),
                               QtCore.Qt.AlignCenter | QtCore.Qt.AlignVCenter, readout)
            if message:
                sf = QtGui.QFont(family)
                # Largest size whose wrapped height and longest line fit
                # the message rect (inside card frame, above screen edge).
                mfrac = 0.055
                chosen = sf
                while mfrac > 0.02:
                    sf.setPixelSize(max(10, int(h * mfrac)))
                    rh = QtGui.QFontMetrics(sf).boundingRect(
                        0, 0, int(message_rect[2]), 100000,
                        QtCore.Qt.AlignCenter | QtCore.Qt.TextWordWrap,
                        message).height()
                    if rh <= message_rect[3]:
                        chosen = sf
                        break
                    mfrac -= 0.005
                else:
                    chosen = sf
                    chosen.setPixelSize(max(10, int(h * 0.02)))
                p.setFont(chosen)
                p.setPen(txt)
                p.drawText(QtCore.QRect(int(message_rect[0]), int(message_rect[1]),
                                        int(message_rect[2]), int(message_rect[3])),
                           QtCore.Qt.AlignCenter | QtCore.Qt.AlignVCenter | QtCore.Qt.TextWordWrap,
                           message)
            self._draw_speaker_tag(p, snap, t, w, h)
            return
        # digital: bold Segoe UI readout with a subtle dark glass plate behind it
        # (original RevelateTW look; not copied from any reference app)
        plate = QtCore.QRectF(*dl["plate"])
        if show_shape:
            p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 40), max(1, int(h * 0.003))))
            p.setBrush(QtGui.QColor(0, 0, 0, 90))
            p.drawRoundedRect(plate, h * 0.05, h * 0.05)
            p.setBrush(QtCore.Qt.NoBrush)
        # fit the time into the plate width (binary search, like the verse autosize);
        # the marker column is reserved inside plate_inner so the digits and
        # AM/PM share the plate and the marker cannot cross the curve.
        tr = dl["time_rect"]
        plate_inner_w = tr[2]
        scale = dl["text_scale"] / 100.0
        # autosize target: the digit height may use the time band fully
        auto_max = tr[3]
        frac = min(0.30, auto_max / float(h)) * (1.0 if scale >= 1.0 else max(scale, 0.2))
        # above 100 the operator grows the readout toward full width; the
        # fit loop below caps it so the digits still fit the band.
        start_frac = frac
        target_frac = frac * scale if scale > 1.0 else frac
        f = QtGui.QFont(family)
        f.setBold(True)
        # first find the autosize height for this text in the band
        frac = start_frac
        while frac > 0.05:
            f.setPixelSize(max(10, int(h * frac)))
            if QtGui.QFontMetrics(f).horizontalAdvance(text) <= plate_inner_w:
                break
            frac -= 0.02
        if scale > 1.0 and text:
            # grow toward the operator's scale (full-width vibe) while the
            # measured digits still fit the band horizontally
            grown = frac
            while grown < target_frac:
                nxt = min(grown + 0.02, target_frac)
                f.setPixelSize(max(10, int(h * nxt)))
                if QtGui.QFontMetrics(f).horizontalAdvance(text) <= plate_inner_w:
                    grown = nxt
                else:
                    break
            f.setPixelSize(max(10, int(h * grown)))
            frac = grown
        p.setFont(f)
        p.setPen(txt)
        time_rect = QtCore.QRect(int(tr[0]), int(tr[1]), int(tr[2]), int(tr[3]))
        # Falling digit animation: when new digits land, the changed columns
        # fall into place (old digit dropping out below). The view tracks the
        # previous snapshot text and a small work timer repaints at ~60fps
        # until the fall settles; outside that window the plain draw below is
        # used, so the slide is identical when nothing is animating.
        frames = getattr(self, "_fall_frames", None)
        if frames is not None:
            try:
                digit_h = max(10, int(h * frac))
                fm = QtGui.QFontMetrics(f)
                advances = []
                for ch in text:
                    try:
                        advances.append(fm.horizontalAdvance(ch))
                    except AttributeError:
                        advances.append(fm.width(ch))
                total_w = sum(advances) or plate_inner_w
                cx0 = tr[0] + max(0.0, (tr[2] - total_w) / 2.0)
                y_mid = tr[1] + tr[3] / 2.0
                slot_top = y_mid - digit_h / 2.0
                slot_bottom = y_mid + digit_h / 2.0
                x = cx0
                for i, frame in enumerate(frames):
                    if i >= len(text):
                        break
                    nw, old = frame[0], frame[1]
                    new_off = frame[2] if len(frame) > 2 else 0.0
                    old_off = frame[3] if len(frame) > 3 else 0.0
                    aw = advances[i] if i < len(advances) else 0
                    # per-digit slot: horizontal span is this column only, and
                    # the clip band runs the full slide height so a glyph can
                    # fall in/out vertically but never bleed into a neighbour
                    # column or past the top/bottom of the frame
                    slot = QtCore.QRectF(x, 0.0, max(aw, 1), h)
                    if old == nw:
                        glyphs = ((nw, new_off, slot),)
                    else:
                        # new glyph falls onto its slot (centre offset <= 0,
                        # so it can never paint below the slot bottom); the
                        # old glyph drops out and is clipped at the slot
                        # bottom, so it never overlaps the row below
                        exit_clip = QtCore.QRectF(x, 0.0, max(aw, 1),
                                                  min(slot_bottom, h))
                        glyphs = ((old, old_off, exit_clip), (nw, new_off, slot))
                    for glyph, off, clip in glyphs:
                        cell = QtCore.QRectF(x, slot_top + off * digit_h,
                                             max(aw, 1), digit_h)
                        p.save()
                        p.setClipRect(clip)
                        p.drawText(cell, QtCore.Qt.AlignCenter | QtCore.Qt.AlignVCenter, str(glyph))
                        p.restore()
                    x += aw
            except Exception:
                p.drawText(time_rect, QtCore.Qt.AlignCenter | QtCore.Qt.AlignVCenter, text)
        else:
            p.drawText(time_rect, QtCore.Qt.AlignCenter | QtCore.Qt.AlignVCenter, text)
        if marker:
            mf = QtGui.QFont(family)
            mf.setBold(True)
            mf.setPixelSize(max(10, int(h * 0.07)))
            p.setFont(mf)
            p.setPen(acc)
            # marker column is reserved inside the plate (marker_rect), so
            # AM/PM stays inside the inner line during digit animation
            mk = dl["marker_rect"]
            p.save()
            p.setClipRect(QtCore.QRectF(*mk))
            p.drawText(QtCore.QRectF(*mk),
                       QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter, marker)
            p.restore()
        # the operator's own message, inside the plate, below the digits and
        # above the rule (never a generic label)
        if message:
            mm = dl["message_rect"]
            sf = QtGui.QFont(family)
            sfrac = 0.055
            while sfrac > 0.02:
                sf.setPixelSize(max(10, int(h * sfrac)))
                if QtGui.QFontMetrics(sf).horizontalAdvance(message) <= mm[2]:
                    break
                sfrac -= 0.005
            p.setFont(sf)
            p.setPen(txt)
            p.drawText(QtCore.QRect(int(mm[0]), int(mm[1]), int(mm[2]), int(mm[3])),
                       QtCore.Qt.AlignCenter | QtCore.Qt.AlignVCenter | QtCore.Qt.TextWordWrap, message)
        if show_shape and t["frame"] == "line":
            p.setPen(QtGui.QPen(acc, max(2, int(h * 0.008))))
            p.drawLine(int(w * 0.30), int(dl["rule_y"]), int(w * 0.70), int(dl["rule_y"]))
        self._draw_speaker_tag(p, snap, t, w, h)

    def _draw_speaker_tag(self, p, snap, t, w, h):
        """Bottom-left SPEAKER tag, drawn only when the toggle is ON and a
        name is set. Both parts share one bottom-left band; each gets its own
        font and colour (label accent-coloured by default, name template
        text by default), separate from the core-message settings. Nothing
        is drawn for a legacy/unknown snapshot: a missing name or OFF toggle
        keeps the band empty, never a bare "SPEAKER:"."""
        if not snap.get("show_speaker", False):
            return
        name = timermod.clean_speaker(snap.get("speaker", ""))
        if not name:
            return
        label = timermod.SPEAKER_LABEL
        x, y, bw, bh = timermod.speaker_layout(w, h)
        if bw <= 0 or bh <= 0:
            return
        label_w = bw * timermod.SPEAKER_LABEL_FRAC
        name_x = x + label_w
        label_rect = QtCore.QRectF(x, y, label_w, bh)
        name_rect = QtCore.QRectF(name_x, y, bw - label_w, bh)
        # Fit each part independently to its own column, like the digits.
        lfam = timermod.clean_font(snap.get("speaker_label_font", ""))
        nfam = timermod.clean_font(snap.get("speaker_name_font", ""))
        lcol = snap.get("speaker_label_color") or t.get("speaker_label_color") or t.get("accent", "")
        ncol = snap.get("speaker_name_color") or t.get("speaker_name_color") or t.get("text", "")
        if not timermod._valid_color(lcol):
            lcol = "#ffffff"
        if not timermod._valid_color(ncol):
            ncol = "#ffffff"
        ncol_q = QtGui.QColor(ncol)

        def fit(family, txt, rect):
            frac = 0.045
            f = QtGui.QFont(family)
            f.setBold(True)
            while frac > 0.012:
                f.setPixelSize(max(8, int(h * frac)))
                fm = QtGui.QFontMetrics(f)
                if fm.horizontalAdvance(txt) <= rect.width() and fm.height() <= rect.height():
                    return f
                frac -= 0.0025
            f.setPixelSize(max(8, int(h * 0.012)))
            return f

        # Auto-adapting glass pill for the name: light text gets a dark glass
        # fill, dark text gets a light glass fill, so contrast never flips.
        # Fill alpha stays translucent (glassmorphism); border is the name
        # colour itself at a soft alpha so it can never clash with the text.
        # The pill hugs the measured name text plus symmetric padding, so
        # the name text sits fully inside the pill with left/right breathing
        # room. The sheen is a subtle low-alpha vertical gradient painted as
        # the pill FILL itself, behind the letters: light at the top fading
        # to transparent at the bottom. It is never a solid bar above the
        # text, so it can never overlap or obscure the name.
        lum = (ncol_q.red() * 299 + ncol_q.green() * 587 + ncol_q.blue() * 114) / 1000.0
        text_is_light = lum >= 140
        base_fill = QtGui.QColor(8, 12, 24, 62) if text_is_light else QtGui.QColor(255, 255, 255, 56)
        sheen_top = QtGui.QColor(255, 255, 255, 30) if text_is_light else QtGui.QColor(0, 0, 0, 16)
        border_color = QtGui.QColor(ncol_q)
        border_color.setAlpha(99)

        label_font = fit(lfam, label, label_rect)
        label_w = QtGui.QFontMetrics(label_font).horizontalAdvance(label)
        gap = h * timermod.SPEAKER_GAP_FRAC
        padx = h * timermod.SPEAKER_PILL_PADX_FRAC
        pady = h * timermod.SPEAKER_PILL_PADY_FRAC
        # The pill starts after the measured label plus the gap, and its
        # width is the measured name text plus padding on both sides, so it
        # never extends past the name into empty space. Fit the name to the
        # band that remains after the label, minus the pill padding, so a
        # long name shrinks to fit inside its own pill instead of overhanging.
        name_x = x + label_w + gap
        max_name_text_w = max(1.0, (x + bw - name_x) - padx * 2)
        name_font = fit(nfam, name, QtCore.QRectF(0.0, 0.0, max_name_text_w, bh))
        text_w = QtGui.QFontMetrics(name_font).horizontalAdvance(name)
        pill_rect = QtCore.QRectF(name_x, y + pady, text_w + padx * 2, bh - pady * 2)
        text_rect = QtCore.QRectF(name_x + padx, y + pady, text_w, bh - pady * 2)
        radius = max(4.0, pill_rect.height() * 0.5)
        # Glass fill: solid translucent base + subtle top-to-bottom sheen
        # gradient in the same rounded shape, behind the text.
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(QtGui.QBrush(base_fill))
        p.drawRoundedRect(pill_rect, radius, radius)
        sheen = QtGui.QLinearGradient(pill_rect.topLeft(), pill_rect.bottomLeft())
        sheen.setColorAt(0.0, sheen_top)
        sheen.setColorAt(1.0, QtGui.QColor(sheen_top.red(), sheen_top.green(), sheen_top.blue(), 0))
        p.setBrush(QtGui.QBrush(sheen))
        p.drawRoundedRect(pill_rect, radius, radius)
        p.setBrush(QtCore.Qt.NoBrush)
        p.setPen(QtGui.QPen(border_color, max(1.0, h * 0.0025)))
        p.drawRoundedRect(pill_rect, radius, radius)
        p.setPen(QtCore.Qt.NoPen)

        p.setFont(label_font)
        p.setPen(QtGui.QColor(lcol))
        p.drawText(QtCore.QRectF(x, y, label_w, bh), QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter, label)
        p.setFont(name_font)
        p.setPen(ncol_q)
        p.drawText(text_rect, QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter, name)

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
        if meta is not None or body:
            self.timer_snap = None
        self.live = bool(body) or self.timer_snap is not None
        self.update()

    def show_timer(self, snap):
        self.set_timer(snap)

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QtGui.QPainter(self)
        p.setPen(QtGui.QPen(QtGui.QColor(C.accent if self.on_air else "#334155"), 3 if self.on_air else 1))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))


class ProjectionWindow(SlideView):
    offRequested = QtCore.pyqtSignal()       # Esc pressed while this window has the keyboard
    projectRequested = QtCore.pyqtSignal()   # F1 (or F5 / Ctrl+Enter) pressed while this window has the keyboard
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

    # ---- keys: the full-screen window takes the keyboard, so Esc/F1 must work here too ----
    def keyPressEvent(self, e):
        mods = e.modifiers() & ~QtCore.Qt.KeypadModifier
        if e.key() == QtCore.Qt.Key_Escape:
            self.offRequested.emit()
        elif e.key() in (QtCore.Qt.Key_F1, QtCore.Qt.Key_F5):
            self.projectRequested.emit()
        elif mods & QtCore.Qt.ControlModifier and e.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            # Alternate Project shortcut for laptops whose bare F1/F5 is a media key
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
