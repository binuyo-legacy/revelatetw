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

MODES = ("clock", "countdown")
FORMATS = ("24", "12")
STYLES = ("digital", "analog")


def clean(key):
    return key if key in TEMPLATES else DEFAULT


def clean_mode(m):
    return m if m in MODES else "clock"


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
        t["bg_kind"], t["bg1"], t["bg2"] = "solid", bg_color.lower(), bg_color.lower()
    return t


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


class TimerEngine:
    """Operator-controlled clock/countdown state. One tick per second from Qt."""

    def __init__(self, mode="clock", fmt="24", show_ampm=True, duration=300, template=DEFAULT,
                 text_color="", bg_color="", style="digital", show_seconds=False):
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

    def configure(self, mode=None, fmt=None, show_ampm=None, duration=None,
                  template=None, text_color=None, bg_color=None, style=None, show_seconds=None):
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
        if self.mode == "clock":
            dt = now or datetime.datetime.now()
            text, marker = format_clock(dt, self.fmt, self.show_ampm, self.show_seconds)
            label_text = "CLOCK"
            state = ""
            dial = None
            if self.style == "analog":
                dial = dict(hour=dt.hour % 12 + dt.minute / 60.0, minute=dt.minute + dt.second / 60.0, second=dt.second)
        else:
            text = format_countdown(self.remaining)
            marker = ""
            label_text = "COUNTDOWN"
            state = "FINISHED" if self.finished else ("RUNNING" if self.running else "PAUSED")
            dial = None
            if self.style == "analog":
                # countdown dial sweeps from full to empty over the configured duration
                frac = (self.remaining / float(self.duration)) if self.duration else 0.0
                dial = dict(hour=frac * 12.0, minute=frac * 60.0, second=(self.remaining % 60))
        return dict(text=text, marker=marker, label=label_text, state=state,
                    mode=self.mode, style=self.style, dial=dial, seconds=self.show_seconds,
                    template=self.template,
                    text_color=self.text_color, bg_color=self.bg_color,
                    remaining=int(round(self.remaining)) if self.mode == "countdown" else None)
