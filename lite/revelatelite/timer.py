"""Timer / clock for Lite. Headless logic plus template dicts (no Qt here).

Original RevelateTW styling: a big centred digital readout with a small
label underneath and a thin accent line. Not copied from any reference app.
The projection code (projection.SlideView) paints the snapshot this module
produces, so preview, projector and the Programs mirror all match.
"""
import datetime


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
MESSAGE_RECT_FRAC = (0.10, 0.74, 0.80, 0.10)


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
    renderer and the bounds tests agree exactly."""
    x, y, rw, rh = MESSAGE_RECT_FRAC
    return (w * x, h * y, w * rw, h * rh)


def clean_message(m):
    return " ".join(str(m or "").split())[:MAX_MESSAGE]


def clean_source(s):
    return s if s in SOURCES else "live"


def clean_font(f):
    return f if f in FONT_FAMILIES else "Segoe UI"


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


def resolve(key, text_color="", bg_color=""):
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


def falling_centers(old_text, new_text, t_ms):
    """Frames to draw at t_ms into a digit change, one entry per column.

    Each entry is (new_char, old_char, y_offset_frac): y_offset is in digit
    heights, negative = above the slot (falling in), positive = below it
    (the old digit exiting). At t >= FALL_DURATION_MS all offsets are 0 and
    the caller draws the plain text. Deterministic: same inputs, same frames.
    """
    n = max(len(str(old_text)), len(str(new_text)))
    old_s = str(old_text).rjust(n)
    new_s = str(new_text).rjust(n)
    if t_ms is None or t_ms >= FALL_DURATION_MS:
        return [(nw, o, 0.0) for nw, o in zip(new_s, old_s)]
    frac = max(0.0, min(1.0, float(t_ms) / float(FALL_DURATION_MS)))
    # new digit eases in from above (ease-out), old digit drops out below
    # with an accelerating (gravity) ease.
    land = 1.0 - (1.0 - frac) ** 3
    drop = frac * frac
    out = []
    for o, nw in zip(old_s, new_s):
        if o == nw:
            out.append((nw, o, 0.0))
        else:
            out.append((nw, o, -FALL_TRAVEL_FRAC * (1.0 - land) + FALL_TRAVEL_FRAC * drop))
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
    """Operator-controlled clock/countdown state. One tick per second from Qt."""

    def __init__(self, mode="time", fmt="24", show_ampm=True, duration=300, template=DEFAULT,
                 text_color="", bg_color="", style="digital", show_seconds=False,
                 message="", source="live", manual_hour=9, manual_minute=0, manual_second=0,
                 font_family="Segoe UI"):
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

    def configure(self, mode=None, fmt=None, show_ampm=None, duration=None,
                  template=None, text_color=None, bg_color=None, style=None, show_seconds=None,
                  message=None, source=None, manual_hour=None, manual_minute=None, manual_second=None,
                  font_family=None):
        if mode is not None:
            self.mode = clean_mode(mode)
        if fmt is not None:
            self.fmt = clean_format(fmt)
        if show_ampm is not None:
            self.show_ampm = bool(show_ampm)
        if duration is not None:
            self.duration = clamp_duration(duration)
            if not self.running:
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

    def manual_dt(self):
        return manual_datetime(self.manual_hour, self.manual_minute, self.manual_second)

    def start(self):
        if self.mode == "countdown":
            if self.finished or self.remaining <= 0:
                self.remaining = float(self.duration)
                self.finished = False
            self.running = True

    def pause(self):
        self.running = False

    def reset(self):
        self.running = False
        self.finished = False
        self.remaining = float(self.duration)

    def tick(self, now=None):
        """Advance one beat. Returns the display snapshot dict."""
        if self.mode == "countdown" and self.running:
            self.remaining = max(0.0, self.remaining - 1.0)
            if self.remaining <= 0:
                self.running = False
                self.finished = True
        return self.snapshot(now)

    def snapshot(self, now=None):
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
                    template=self.template, font_family=self.font_family,
                    text_color=self.text_color, bg_color=self.bg_color,
                    remaining=int(round(self.remaining)) if self.mode == "countdown" else None)
