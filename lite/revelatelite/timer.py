"""Timer / clock for Lite. Headless logic plus template dicts (no Qt here).

Original RevelateTW styling: a big centred digital readout with a small
label underneath and a thin accent line. Not copied from any reference app.
The projection code (projection.SlideView) paints the snapshot this module
produces, so preview, projector and the Programs mirror all match.
"""
import datetime
import time


def _valid_color(c):
    return (isinstance(c, str) and len(c) == 7 and c[0] == "#"
            and all(ch in "0123456789abcdefABCDEF" for ch in c[1:]))


# name -> template. bg: ("solid"|"linear", c1, c2). frame: none|line|card
TEMPLATES = {
    "revelate": dict(
        name="Revelate Night",
        blurb="Deep navy with gold digits and a thin gold line under the time. The Lite default.",
        bg=("solid", "#0b0f19", "#0b0f19"), text="#facc15", accent="#facc15", dim="#aab6d6",
        frame="line"),
    "stage": dict(
        name="Stage Glow",
        blurb="Dark plum to amber glow with cream digits, good for evening services.",
        bg=("linear", "#2a0a2e", "#7c2d12"), text="#fff7e6", accent="#ffd58a", dim="#ffe3b0",
        frame="line"),
    "studio": dict(
        name="Studio Light",
        blurb="Light ivory page with dark digits. Clear in a bright room.",
        bg=("solid", "#faf6ec", "#faf6ec"), text="#1f2937", accent="#1d4ed8", dim="#6b7280",
        frame="card"),
    "signal": dict(
        name="Signal Black",
        blurb="Pure black with bright green digits and a green card behind the time.",
        bg=("solid", "#000000", "#000000"), text="#4ade80", accent="#4ade80", dim="#9ca3af",
        frame="card"),
}
KEYS = list(TEMPLATES.keys())
DEFAULT = "revelate"

MODES = ("time", "countdown")
SOURCES = ("live", "manual")
FORMATS = ("24", "12")
STYLES = ("digital", "analog")

# Windows fonts offered in the Timer tab. settings.FONT_GROUPS has the same
# Windows 8.1 faces; duplicated here so this headless module never imports Qt
# settings (avoids a settings <-> timer import cycle through load()).
FONT_FAMILIES = (
    "Segoe UI", "Georgia", "Arial", "Arial Black", "Calibri", "Cambria",
    "Candara", "Comic Sans MS", "Consolas", "Corbel", "Courier New",
    "Franklin Gothic Medium", "Gabriola", "Impact", "Lucida Sans Unicode",
    "Palatino Linotype", "Segoe Script", "Tahoma", "Times New Roman", "Verdana",
)
MAX_MESSAGE = 120

# ---- speaker tag (bottom-left, Timer projection only) ----
# A small tag block pinned to the bottom-left edge of the Timer/Countdown
# projection, independent of the core message. The static "SPEAKER:" label
# sits next to the operator's speaker name. Visibility is one ON/OFF toggle:
# the default is OFF (an empty name must never paint a bare "SPEAKER:").
# Geometry lives in speaker_layout() so the renderer and the bounds tests
# agree. The band is BELOW the digital plate / BELOW the analog digits and
# message (never under the dial), so it cannot collide with the time readout,
# the core message, or the bottom-centre reference area.
SPEAKER_LABEL = "SPEAKER:"
MAX_SPEAKER = 80
SPEAKER_FRAC = (0.02, 0.895, 0.42, 0.06)  # x, y, width, height (fracs of w, h)
SPEAKER_LABEL_FRAC = 0.44  # legacy share; painter now measures the label text
SPEAKER_GAP_FRAC = 0.012  # gap between measured label text and name pill (frac of h)
SPEAKER_PILL_PADX_FRAC = 0.03  # pill horizontal padding inside the name (frac of h)
SPEAKER_PILL_PADY_FRAC = 0.008  # pill vertical padding inside the band (frac of h)


def clean_speaker(s):
    return " ".join(str(s or "").split())[:80]


def speaker_layout(w, h):
    """(x, y, width, height) floats for the speaker tag band.

    Bottom-left band at y 89.5%..95.5% of the height, x 2%..44% of the
    width. Digit/message bands all end by ~85% of the height (digital plate
    24%..76%, analog message ends ~85%), so the band overlaps none of them:
    digital time_rect, message_rect, analog digits_rect, message_rect, the
    dial, and the gold rule all stay clear, for both modes and both styles.
    """
    if w <= 0 or h <= 0:
        return (0.0, 0.0, 0.0, 0.0)
    x, y, rw, rh = SPEAKER_FRAC
    return (w * x, h * y, w * rw, h * rh)

# ---- digital timer shape geometry (fractions of w, h, headless + tested) ----
# The "inner curve shape" the operator sees is the dark glass plate the
# projection draws around the digits. It is a rounded rect spanning
# 6%..94% of the width and 24%..76% of the height; the "card" templates
# also draw a lighter rounded rect (8%..92% x 22%..78%) behind it. Every
# projected string (digits, AM/PM marker, message) must stay inside that
# shape. The older MESSAGE_RECT_FRAC sat at 74%..84% of the height, so the
# message straddled the plate's bottom edge and crossed the gold rule at
# 82%: on the "card" templates the message looked like it was below the
# frame entirely, and on the "line" templates the rule cut through it.
# Shifting it down a little is not enough on its own; it has to land inside
# the plate, below the digits and clear of the rule.
#
# digital_layout() below is the single source of truth for both the
# renderer and the bounds tests.
DIGITAL_PLATE_FRAC = (0.06, 0.24, 0.88, 0.52)     # x, y, width, height
DIGITAL_TIME_FRAC = (0.04, 0.30, 0.92, 0.38)      # inside plate (digits)
DIGITAL_MESSAGE_FRAC = (0.08, 0.685, 0.84, 0.07)  # inside plate, below digits
DIGITAL_RULE_Y_FRAC = 0.775                        # gold rule, under message
DIGITAL_MARKER_W_FRAC = 0.14                       # AM/PM column width
# Operator display text size: 100 = autosize to fit the plate (current
# behaviour); >100 pushes toward a full-width look (the fit caps it so the
# message still fits); <100 shrinks. 50..300 in 5% steps.
TEXT_SCALE_MIN, TEXT_SCALE_MAX, TEXT_SCALE_DEFAULT = 50, 300, 100


def clean_text_scale(v):
    try:
        return max(TEXT_SCALE_MIN, min(TEXT_SCALE_MAX, int(round(float(v)))))
    except (TypeError, ValueError):
        return TEXT_SCALE_DEFAULT


MESSAGE_RECT_FRAC = DIGITAL_MESSAGE_FRAC


def analog_layout(w, h, has_subtext=True):
    """Shared geometry for the analog timer render.

    Layout (16:9 and common projector ratios):
      dial ellipse occupies the upper region, digits below it, message
      below digits. Dial marks/hands never sit under the digits or
      message; remaining-time digits and message occupy distinct bands.

    Returns dict with cx, cy, r, digits_rect, message_rect and arc
    radius. Rects are (x, y, width, height) floats.
    """
    if w <= 0 or h <= 0:
        # Callers pass real sizes; keep a safe zero-sized fallback rather
        # than raising during paint.
        return dict(cx=0.0, cy=0.0, r=0.0,
                    digits_rect=(0.0, 0.0, 0.0, 0.0),
                    message_rect=(0.0, 0.0, 0.0, 0.0),
                    arc_r=0.0)
    cy = h * 0.34
    r = min(w, h) * 0.27
    arc_r = r * 1.09
    digits_h = h * 0.16
    digits_rect = (w * 0.10, cy + arc_r + h * 0.015, w * 0.80, digits_h)
    if has_subtext:
        message_rect = (w * 0.10, digits_rect[1] + digits_h + h * 0.012, w * 0.80, h * 0.09)
    else:
        message_rect = (w * 0.10, 0.0, w * 0.80, 0.0)
    return dict(cx=w / 2.0, cy=cy, r=r,
                digits_rect=digits_rect, message_rect=message_rect, arc_r=arc_r)


def rects_overlap(a, b):
    """True when (x, y, w, h) rects share any positive area (edge touch okay)."""
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


def inner_rect(w, h):
    """Inner shape every projected timer string must stay inside.

    Returns (x, y, width, height) as floats. Kept in one place so the
    renderer and the bounds tests agree exactly. This is the message
    band inside the glass plate, so the message sits inside the shape and
    below the digits; see digital_layout() for the full geometry."""
    x, y, rw, rh = DIGITAL_MESSAGE_FRAC
    return (w * x, h * y, w * rw, h * rh)


def digital_layout(w, h, marker="", show_shape=True, text_scale=TEXT_SCALE_DEFAULT):
    """Shared, tested geometry for the digital timer render.

    Returns a dict of (x, y, width, height) float rects plus rule_y:
      plate         the curved inner shape (only drawn when show_shape)
      plate_inner   plate shrunk by the plate margin; when a marker is
                    present the right-hand marker column is reserved, so
                    the AM/PM marker can never cross the inner curve
      time_rect     digit band, inside plate_inner, clear of the message
      marker_rect   right-hand column inside the plate, same vertical band
                    as the digits; empty when there is no marker
      message_rect  message band, inside the plate, below the digits and
                    above the decorative rule (rule_y)
      rule_y        vertical position of the gold rule (message-free band)
    When show_shape is False the plate/card/line are not drawn and the
    text may use the full width, but the message, marker and digit bands
    keep the same relative positions so the message stays fitted and the
    marker stays next to the digits.
    """
    pw = w * DIGITAL_PLATE_FRAC[2]
    ph = h * DIGITAL_PLATE_FRAC[3]
    plate = (w * DIGITAL_PLATE_FRAC[0], h * DIGITAL_PLATE_FRAC[1], pw, ph)
    scale = clean_text_scale(text_scale)
    if show_shape:
        inner_x = plate[0] + pw * 0.04
        inner_w = pw * 0.92
        time_y = h * 0.30
    else:
        # full-width ("non-template") look: use the screen itself
        inner_x = w * 0.03
        inner_w = w * 0.94
        time_y = h * 0.30
    marker_w = w * DIGITAL_MARKER_W_FRAC if marker else 0.0
    text_w = max(inner_w - marker_w - w * 0.02, inner_w * 0.40)
    time_rect = (inner_x, time_y, text_w, h * 0.38)
    marker_rect = ((inner_x + text_w + w * 0.01, time_y, marker_w, h * 0.38)
                   if marker else (0.0, 0.0, 0.0, 0.0))
    mx, my, mrw, mrh = DIGITAL_MESSAGE_FRAC
    # with the shape off the message may run the full inner width
    # (3% margin each side), keeping its fitted font size
    if show_shape:
        message_rect = (w * mx, h * my, w * mrw, h * mrh)
    else:
        message_rect = (w * 0.03, h * my, w * 0.94, h * mrh)
    return dict(plate=plate, plate_inner=(inner_x, time_y, inner_w, h * 0.45),
                time_rect=time_rect, marker_rect=marker_rect,
                message_rect=message_rect, rule_y=h * DIGITAL_RULE_Y_FRAC,
                show_shape=bool(show_shape), text_scale=scale)


def digit_rects_overlap(a, b):
    return rects_overlap(a, b)


def clean_message(m):
    return " ".join(str(m or "").split())[:MAX_MESSAGE]


def clean_source(s):
    return s if s in SOURCES else "live"


def clean_font(f):
    return f if f in FONT_FAMILIES else "Segoe UI"


def analog_time_readout(text, marker=""):
    """Combined digital readout shown under an analog Time dial.

    Returns the clock text plus the AM/PM marker when present (for example
    ``5:04 PM``), or just the clock text in 24-hour mode (``17:04``).
    Headless so callers and tests share the exact string the renderer draws.
    """
    text = " ".join(str(text or "").split())
    marker = " ".join(str(marker or "").split()).upper()
    return "%s %s" % (text, marker) if text and marker else (text or marker)


def clamp_time(hour, minute, second=0, ampm=None):
    """Normalise a manually entered clock time to a plain (h, m, s) 24h tuple."""
    try:
        h, m, s = int(hour), int(minute), int(second)
    except (TypeError, ValueError):
        return (0, 0, 0)
    if ampm in ("AM", "am", "a"):
        h = h % 12
    elif ampm in ("PM", "pm", "p"):
        h = (h % 12) + 12
    return (max(0, min(23, h)), max(0, min(59, m)), max(0, min(59, s)))


def clean(key):
    return key if key in TEMPLATES else DEFAULT


def clean_mode(m):
    if m == "clock":  # settings saved before the Time rename
        return "time"
    return m if m in MODES else "time"


def clean_format(f):
    return f if f in FORMATS else "24"


def clean_style(s):
    return s if s in STYLES else "digital"


def label(key):
    return TEMPLATES[clean(key)]["name"]


def blurb(key):
    return TEMPLATES[clean(key)]["blurb"]


def resolve(key, text_color="", bg_color="", **kwargs):
    """Template dict with text/bg colours overridden ('' = template default).

    `kwargs` stays generic so the engine can pass the operator's speaker tag
    colours straight through (see resolve() usage): speaker_label_color and
    speaker_name_color.
    """
    t = dict(TEMPLATES[clean(key)])
    t["bg_kind"], t["bg1"], t["bg2"] = t["bg"]
    if _valid_color(text_color):
        t["text"] = text_color.lower()
    if _valid_color(bg_color):
        bg = bg_color.lower()
        # Every historical key must agree: some renders read the legacy "bg"
        # tuple (kind, c1, c2) while others read bg_kind/bg1/bg2. Updating only
        # the new keys left the tuple at the template navy, so a custom
        # background picked in the Timer tab never painted. Keep all four in sync.
        t["bg_kind"], t["bg1"], t["bg2"] = "solid", bg, bg
        t["bg"] = ("solid", bg, bg)
    # Speaker tag colours. They are independent of the core message: each of
    # the "SPEAKER:" label and the name takes its own override when the
    # operator set one (kwargs speaker_label_color / speaker_name_color, kept
    # as strict extras so callers passing text_color/bg_color positionally can
    # never leak into them), else it inherits the template accent/text colour
    # (so the tag still pops on its own without adding a new palette rule).
    label_c = kwargs.get("speaker_label_color", "")
    name_c = kwargs.get("speaker_name_color", "")
    t["speaker_label_color"] = label_c.lower() if _valid_color(label_c) else t.get("accent", "")
    t["speaker_name_color"] = name_c.lower() if _valid_color(name_c) else t.get("text", "")
    return t


def manual_datetime(hour, minute, second=0, ampm=None):
    """A datetime carrying only the manually entered time (today's date)."""
    h, m, s = clamp_time(hour, minute, second, ampm)
    return datetime.datetime.now().replace(hour=h, minute=m, second=s, microsecond=0)


def format_clock(dt, fmt="24", show_ampm=True, show_seconds=False):
    """(text, marker) for a datetime. 12h has no leading zero; marker only in 12h+show."""
    fmt = clean_format(fmt)
    if fmt == "24":
        text = "%02d:%02d" % (dt.hour, dt.minute)
        marker = ""
    else:
        h = dt.hour % 12 or 12
        marker = ("AM" if dt.hour < 12 else "PM") if show_ampm else ""
        text = "%d:%02d" % (h, dt.minute)
    if show_seconds:
        text += ":%02d" % dt.second
    return text, marker


def format_countdown(remaining):
    """Seconds -> MM:SS, or H:MM:SS once an hour or more. Never negative."""
    s = max(0, int(round(remaining)))
    if s >= 3600:
        return "%d:%02d:%02d" % (s // 3600, (s % 3600) // 60, s % 60)
    return "%02d:%02d" % (s // 60, s % 60)


def dial_string(dt, fmt="24"):
    """Dial label for analog display: clock uses the actual hour; countdown uses remaining MM:SS as a value."""
    text, _ = format_clock(dt, fmt, show_ampm=False, show_seconds=False)
    return text


def clamp_duration(seconds):
    return max(1, min(12 * 3600, int(seconds)))


# ---- digit fall (flip) animation ----
# When a time/countdown digit changes, the NEW digit falls in from above
# and settles into its slot while the old digit drops out below. The model is
# headless and deterministic so it is testable without a frame loop; the
# projection renderer draws the per-change offsets it returns.
FALL_DURATION_MS = 350
FALL_TRAVEL_FRAC = 1.1  # new digit starts this many digit heights above its slot
# Geometry bounds, in digit-height fractions of the slot centre. The new glyph
# must land on 0 and never pass it: a separate gravity term used to carry the
# *drawn* glyph past 0 to nearly +1.1 heights, so its lower leg sat a full
# digit height under the row (over the message/line) and snapped back at
# settle. The exiting glyph is the only one allowed to travel below the slot,
# and only down to this floor, where the renderer clips it away.
FALL_NEW_MIN = -FALL_TRAVEL_FRAC
FALL_OLD_MAX = +FALL_TRAVEL_FRAC


def falling_centers(old_text, new_text, t_ms):
    """Frames to draw at t_ms into a digit change, one 4-tuple per column.

    Each entry is (new_char, old_char, new_off_frac, old_off_frac):
    offsets are in digit heights relative to the slot centre, negative =
    above, positive = below. The *new* glyph falls monotonically from
    FALL_NEW_MIN to 0 and never goes below its slot (new_off_frac <= 0 for
    every t), so its bottom leg can never dip under the row. The *old* glyph
    drops monotonically from 0 to FALL_OLD_MAX as it exits. At
    t >= FALL_DURATION_MS all offsets are 0 and the caller draws the plain
    text. Deterministic: same inputs, same frames. Unchanged columns and
    non-digit columns (colons) stay at 0. The 4-tuple keeps the historic
    (new, old, offset) shape as a prefix: entry[2] is the new glyph's
    offset, i.e. what the old code drew (wrongly, with the drop term added).
    """
    n = max(len(str(old_text)), len(str(new_text)))
    old_s = str(old_text).rjust(n)
    new_s = str(new_text).rjust(n)
    if t_ms is None or t_ms >= FALL_DURATION_MS:
        return [(nw, o, 0.0, 0.0) for nw, o in zip(new_s, old_s)]
    frac = max(0.0, min(1.0, float(t_ms) / float(FALL_DURATION_MS)))
    # new glyph: ease-out landing onto the slot, clamped to never overshoot
    # below it; old glyph: accelerating gravity drop out of the slot.
    land = 1.0 - (1.0 - frac) ** 3
    drop = frac * frac
    new_off = FALL_NEW_MIN * (1.0 - land)
    old_off = FALL_OLD_MAX * drop
    out = []
    for o, nw in zip(old_s, new_s):
        if o == nw or not (o.isalnum() or nw.isalnum()):
            out.append((nw, o, 0.0, 0.0))
        else:
            out.append((nw, o, new_off, old_off))
    return out


def digit_changed(old_text, new_text):
    """True when any aligned digit position differs (colon/other chars ignored)."""
    if old_text == new_text:
        return False
    o = str(old_text).rjust(len(str(new_text)))
    n = str(new_text)
    if len(o) != len(n):
        return True
    for a, b in zip(o, n):
        if a != b and (a.isalnum() or b.isalnum()):
            return True
    return False


class TimerEngine:
    """Operator-controlled clock/countdown state.

    The countdown timebase is a monotonic deadline set at start() and
    reconciled whenever a value is read. It does not depend on how often
    tick() is called, which tab is selected, or what the shared projector
    currently shows, so time keeps elapsing while Bible or Songs content is
    projected. tick(now) is kept for the one-second UI beat and pushes a
    fresh snapshot; callers may pass an explicit monotonic "now" in tests.
    """

    def __init__(self, mode="time", fmt="24", show_ampm=True, duration=300, template=DEFAULT,
                 text_color="", bg_color="", style="digital", show_seconds=False,
                 message="", source="live", manual_hour=9, manual_minute=0, manual_second=0,
                 font_family="Segoe UI", clock=None, show_shape=True,
                 text_scale=TEXT_SCALE_DEFAULT, speaker="", show_speaker=False,
                 speaker_label_font=None, speaker_name_font=None,
                 speaker_label_color="", speaker_name_color=""):
        self.mode = clean_mode(mode)
        self.fmt = clean_format(fmt)
        self.show_ampm = bool(show_ampm)
        self.duration = clamp_duration(duration)
        self.remaining = float(self.duration)
        self.running = False
        self.finished = False
        self.template = clean(template)
        self.text_color = text_color if _valid_color(text_color) else ""
        self.bg_color = bg_color if _valid_color(bg_color) else ""
        self.style = clean_style(style)
        self.show_seconds = bool(show_seconds)
        self.message = clean_message(message)
        self.source = clean_source(source)
        self.manual_hour, self.manual_minute, self.manual_second = clamp_time(manual_hour, manual_minute, manual_second)
        self.font_family = clean_font(font_family)
        self.show_shape = bool(show_shape)
        self.text_scale = clean_text_scale(text_scale)
        self.speaker = clean_speaker(speaker)
        self.show_speaker = bool(show_speaker)
        self.speaker_label_font = clean_font(speaker_label_font) if speaker_label_font else ""
        self.speaker_name_font = clean_font(speaker_name_font) if speaker_name_font else ""
        self.speaker_label_color = speaker_label_color.lower() if _valid_color(speaker_label_color) else ""
        self.speaker_name_color = speaker_name_color.lower() if _valid_color(speaker_name_color) else ""
        self._clock = clock or time.monotonic
        self._deadline = None

    def configure(self, mode=None, fmt=None, show_ampm=None, duration=None,
                  template=None, text_color=None, bg_color=None, style=None, show_seconds=None,
                  message=None, source=None, manual_hour=None, manual_minute=None, manual_second=None,
                  font_family=None, show_shape=None, text_scale=None, speaker=None,
                  show_speaker=None, speaker_label_font=None, speaker_name_font=None,
                  speaker_label_color=None, speaker_name_color=None):
        # Reconcile the running countdown deadline before touching anything
        # else, so a Timer Type switch (countdown -> time -> countdown), a
        # style/format change, or a duration edit never works from a stale
        # remaining value. The deadline is mode-independent: the display
        # mode only picks what is drawn, never whether time has passed.
        self._sync()
        if mode is not None:
            self.mode = clean_mode(mode)
        if fmt is not None:
            self.fmt = clean_format(fmt)
        if show_ampm is not None:
            self.show_ampm = bool(show_ampm)
        if duration is not None:
            old_duration = self.duration
            self.duration = clamp_duration(duration)
            if self.running and self._deadline is not None:
                self._deadline += float(self.duration - old_duration)
                if self._deadline <= self._clock():
                    self._deadline = self._clock()
                    self.running = False
                    self.finished = True
                    self.remaining = 0.0
            elif not self.running:
                self.remaining = float(self.duration)
                self.finished = False
        if template is not None:
            self.template = clean(template)
        if text_color is not None:
            self.text_color = text_color if _valid_color(text_color) else ""
        if bg_color is not None:
            self.bg_color = bg_color if _valid_color(bg_color) else ""
        if style is not None:
            self.style = clean_style(style)
        if show_seconds is not None:
            self.show_seconds = bool(show_seconds)
        if message is not None:
            self.message = clean_message(message)
        if source is not None:
            self.source = clean_source(source)
        if manual_hour is not None or manual_minute is not None or manual_second is not None:
            self.manual_hour, self.manual_minute, self.manual_second = clamp_time(
                self.manual_hour if manual_hour is None else manual_hour,
                self.manual_minute if manual_minute is None else manual_minute,
                self.manual_second if manual_second is None else manual_second)
        if font_family is not None:
            self.font_family = clean_font(font_family)
        if show_shape is not None:
            self.show_shape = bool(show_shape)
        if text_scale is not None:
            self.text_scale = clean_text_scale(text_scale)
        if speaker is not None:
            self.speaker = clean_speaker(speaker)
        if show_speaker is not None:
            self.show_speaker = bool(show_speaker)
        if speaker_label_font is not None:
            self.speaker_label_font = clean_font(speaker_label_font) if speaker_label_font else ""
        if speaker_name_font is not None:
            self.speaker_name_font = clean_font(speaker_name_font) if speaker_name_font else ""
        if speaker_label_color is not None:
            self.speaker_label_color = speaker_label_color.lower() if _valid_color(speaker_label_color) else ""
        if speaker_name_color is not None:
            self.speaker_name_color = speaker_name_color.lower() if _valid_color(speaker_name_color) else ""

    def manual_dt(self):
        return manual_datetime(self.manual_hour, self.manual_minute, self.manual_second)

    def _sync(self, now=None):
        """Reconcile remaining from the monotonic deadline. Safe to call any time.

        Deliberately independent of the display mode: a running countdown
        keeps time while the Timer Type selector shows Clock, so the next
        read after any mode switch is already correct and nothing is lost.
        """
        if self.running and self._deadline is not None:
            now_t = self._clock() if now is None else now
            self.remaining = max(0.0, float(self._deadline) - float(now_t))
            if self.remaining <= 0:
                self.running = False
                self.finished = True
                self._deadline = None
        return self.remaining

    def elapsed(self, now=None):
        """Seconds consumed by the current countdown, derived from the deadline."""
        self._sync(now)
        return max(0.0, float(self.duration) - float(self.remaining))

    def start(self, now=None):
        if self.mode == "countdown":
            self._sync(now)
            if self.finished or self.remaining <= 0:
                self.remaining = float(self.duration)
                self.finished = False
            if not self.running:
                now_t = self._clock() if now is None else now
                self._deadline = float(now_t) + float(self.remaining)
                self.running = True

    def pause(self, now=None):
        if self.running:
            self._sync(now)
        self.running = False
        self._deadline = None

    def reset(self):
        self.running = False
        self.finished = False
        self._deadline = None
        self.remaining = float(self.duration)

    def tick(self, now=None):
        """Advance one beat. Reconciles from the deadline; returns a snapshot.

        "now" here is the monotonic instant (seconds), not a datetime. It is
        only used for the countdown; time mode reads live/manual time itself.
        Elapsed time is never inferred from the number of ticks, so a beat
        that arrives late (or while another tab is projected) still counts
        every second that passed.
        """
        self._sync(now)
        return self.snapshot(monotonic_now=now)

    def snapshot(self, now=None, monotonic_now=None):
        # "now" is a datetime for the live clock. monotonic_now is the
        # monotonic instant used to reconcile the countdown; when omitted,
        # the engine clock is read, so a snapshot taken after time away from
        # the Timer tab is already correct with no tick at all.
        # Reconcile even while the Timer Type selector shows Clock: the
        # deadline belongs to the running countdown, not to the display mode.
        if monotonic_now is not None:
            self._sync(monotonic_now)
        else:
            self._sync()
        # No generic CLOCK / COUNTDOWN caption and no RUNNING/PAUSED/FINISHED state
        # is projected: people already know what it is, and those words used to
        # overflow the custom template shapes. The only words on screen are the
        # operator's own message (if any) plus the time/countdown itself.
        if self.mode == "time":
            if self.source == "manual":
                dt = self.manual_dt()
            else:
                dt = now or datetime.datetime.now()
            text, marker = format_clock(dt, self.fmt, self.show_ampm, self.show_seconds)
            dial = None
            if self.style == "analog":
                # Standard clockwise wall-clock mapping. Fractional parts are
                # included so the hands sweep smoothly between ticks:
                #   second = seconds (with microsecond fraction when live)
                #   minute = minutes + seconds/60
                #   hour   = hours(12h) + minutes/60
                sec = dt.second + dt.microsecond / 1e6
                dial = dict(hour=(dt.hour % 12) + dt.minute / 60.0 + sec / 3600.0,
                            minute=dt.minute + sec / 60.0,
                            second=sec)
        else:
            text = format_countdown(self.remaining)
            marker = ""
            dial = None
            if self.style == "analog":
                # Countdown hands show ELAPSED time sweeping clockwise like a
                # normal clock (never backwards); the remaining time is shown
                # in digits under/inside the dial, and the draining arc shows
                # how much is left. So the hands equal "time since it started",
                # the digits equal "time remaining".
                elapsed = max(0.0, float(self.duration) - float(self.remaining))
                sec = elapsed % 60.0
                minutes = (elapsed / 60.0) % 60.0
                hours = (elapsed / 3600.0) % 12.0
                dial = dict(hour=hours + minutes / 60.0,
                            minute=minutes,
                            second=sec,
                            elapsed=elapsed,
                            remaining=float(self.remaining),
                            fraction=(self.remaining / float(self.duration)) if self.duration else 0.0)
        return dict(text=text, marker=marker, label="", state="",
                    message=self.message,
                    mode=self.mode, style=self.style, dial=dial, seconds=self.show_seconds,
                    show_shape=self.show_shape, text_scale=self.text_scale,
                    speaker=self.speaker, show_speaker=self.show_speaker,
                    speaker_label=SPEAKER_LABEL,
                    speaker_label_font=self.speaker_label_font or self.font_family,
                    speaker_name_font=self.speaker_name_font or self.font_family,
                    speaker_label_color=self.speaker_label_color,
                    speaker_name_color=self.speaker_name_color,
                    template=self.template, font_family=self.font_family,
                    text_color=self.text_color, bg_color=self.bg_color,
                    remaining=int(round(self.remaining)) if self.mode == "countdown" else None)
