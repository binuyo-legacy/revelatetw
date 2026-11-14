"""Projection transitions: pure helpers (no Qt, so they are unit tested headless).

A transition only ever runs on the FULL-SCREEN display, and only when the operator commits
something: Project (screen comes on), Project while already live (screen switches to the new
preview, this is how Next / Previous reach the audience), and Project Off (screen goes away).
The small in-app preview is never animated, it always shows the final state at once.

Effects (all drawn from two snapshots of the screen, old and new, with plain Qt clipping and
opacity, no shaders, no GPU effects, so they are fine on a Windows 8.1 32-bit / 2 GB PC):

  cut       Instant. No animation at all.
  fade      Fade through black: the old picture fades out, then the new one fades in.
  dissolve  Cross-dissolve: the new picture fades in on top of the old one.
  wipe      A straight edge sweeps across and uncovers the new picture.
  slide     Push: the old picture slides out while the new one slides in behind it.
  blinds    Eight slats open one after another to uncover the new picture.
  open      The new picture opens from the centre outwards (like doors opening).
  checkerboard  Squares in a chequer pattern grow to uncover the new picture (two rounds).
  diagonal  A slanted edge sweeps corner to corner and uncovers the new picture.
  iris      A circle opens from the middle of the screen and uncovers the new picture.
  zoom      The old picture zooms out of view while the new one zooms in (cross-fade).
  mosaic    Small squares of the new picture pop in at scattered places until it is complete.
  clock     A clock hand sweeps round from 12 o'clock and uncovers the new picture.

Direction (Wipe, Slide, Blinds, Open, Diagonal) is the way the motion travels:
  auto = follow Next / Previous (Next travels right to left, Previous left to right),
  or left / right / up / down. Fade and Dissolve have no direction.
"""

EFFECTS = [
    ("cut", "Cut (instant)", "No animation. The screen changes at once."),
    ("fade", "Fade through black", "Old picture fades out, then the new one fades in."),
    ("dissolve", "Dissolve", "New picture fades in on top of the old one."),
    ("wipe", "Wipe", "A straight edge sweeps across and uncovers the new picture."),
    ("slide", "Slide (push)", "Old picture slides out while the new one slides in."),
    ("blinds", "Blinds", "Slats open one after another to uncover the new picture."),
    ("open", "Open from centre", "The new picture opens from the middle outwards."),
    ("checkerboard", "Checkerboard", "Squares in a chequer pattern grow to uncover the new picture."),
    ("diagonal", "Diagonal wipe", "A slanted edge sweeps corner to corner and uncovers the new picture."),
    ("iris", "Iris (circle)", "A circle opens from the middle and uncovers the new picture."),
    ("zoom", "Zoom", "The old picture zooms away while the new one zooms in."),
    ("mosaic", "Mosaic", "Small squares of the new picture pop in at scattered places."),
    ("clock", "Clock sweep", "A clock hand sweeps round and uncovers the new picture."),
]
EFFECT_KEYS = [k for k, _, _ in EFFECTS]
DIRECTED = ("wipe", "slide", "blinds", "open", "diagonal")

DIRECTIONS = [
    ("auto", "Follow Next / Previous"),
    ("left", "Right to left"),
    ("right", "Left to right"),
    ("up", "Bottom to top"),
    ("down", "Top to bottom"),
]
DIRECTION_KEYS = [k for k, _ in DIRECTIONS]

DEFAULT_EFFECT = "dissolve"
DEFAULT_MS = 400
MS_MAX = 3000
MS_STEP = 50
BLIND_COUNT = 8

ON, OFF, SWITCH = "on", "off", "switch"
# Independent full-screen Projection On / Off effect settings (same choices as EFFECTS).
PROJ_KEYS = ("proj_on_effect", "proj_off_effect")
PROJ_KEY_FOR = {ON: "proj_on_effect", OFF: "proj_off_effect"}


def describe(effect):
    for k, _, d in EFFECTS:
        if k == effect:
            return d
    return ""


def clamp_ms(ms):
    try:
        ms = int(ms)
    except (TypeError, ValueError):
        return DEFAULT_MS
    return max(0, min(MS_MAX, ms))


def clean(data):
    """Validated copy of the transition keys of a settings dict (bad values -> defaults)."""
    out = {}
    e = data.get("transition_effect")
    out["transition_effect"] = e if e in EFFECT_KEYS else DEFAULT_EFFECT
    for k in PROJ_KEYS:      # Projection On / Off have their own effect; a missing one starts as a copy of the normal one
        v = data.get(k)
        out[k] = v if v in EFFECT_KEYS else (out["transition_effect"] if v is None else DEFAULT_EFFECT)
    out["transition_ms"] = clamp_ms(data.get("transition_ms", DEFAULT_MS))
    d = data.get("transition_dir")
    out["transition_dir"] = d if d in DIRECTION_KEYS else "auto"
    out["transition_onoff"] = bool(data.get("transition_onoff", True))
    out["transition_switch"] = bool(data.get("transition_switch", True))
    return out


def resolve_direction(setting, step_hint=0):
    """The travel direction to use. step_hint: +1 = operator pressed Next, -1 = Previous, 0 = none."""
    if setting in ("left", "right", "up", "down"):
        return setting
    return "right" if step_hint < 0 else "left"


class Plan(object):
    def __init__(self, kind, effect, ms, direction):
        self.kind, self.effect, self.ms, self.direction = kind, effect, ms, direction

    @property
    def animated(self):
        return self.effect != "cut" and self.ms > 0

    def __repr__(self):
        return "Plan(%s, %s, %dms, %s)" % (self.kind, self.effect, self.ms, self.direction)


def plan(kind, st, step_hint=0, same_picture=False):
    """Decide what to play for kind (on / off / switch) using the settings dict st.
    Returns an instant plan when animations are off, the duration is 0, the matching switch is
    unticked, or nothing visible would change (same_picture)."""
    c = clean(st)
    effect, ms = c["transition_effect"], c["transition_ms"]
    if kind in PROJ_KEY_FOR:          # Project / Project Off use their own effect; switching uses the normal one
        effect = c[PROJ_KEY_FOR[kind]]
    enabled = c["transition_onoff"] if kind in (ON, OFF) else c["transition_switch"]
    if not enabled or same_picture or ms <= 0 or effect == "cut":
        return Plan(kind, "cut", 0, resolve_direction(c["transition_dir"], step_hint))
    return Plan(kind, effect, ms, resolve_direction(c["transition_dir"], step_hint))


# ---- geometry. p = progress 0..1 (already eased). Rects are (x, y, w, h) of the NEW picture's visible part. ----

def ease(t):
    """Smooth start and end."""
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def fade_alphas(p):
    """(old opacity, new opacity) for fade through black: out for the first half, in for the second."""
    p = max(0.0, min(1.0, p))
    return (1 - 2 * p, 0.0) if p < 0.5 else (0.0, 2 * p - 1)


def dissolve_alpha(p):
    """Opacity of the new picture drawn over the old one."""
    return max(0.0, min(1.0, p))


def wipe_rect(direction, w, h, p):
    """Part of the screen already showing the new picture (it grows from the side it travels from)."""
    p = max(0.0, min(1.0, p))
    if direction == "left":        # edge travels right to left: new appears from the right edge
        cw = int(round(w * p))
        return (w - cw, 0, cw, h)
    if direction == "right":
        return (0, 0, int(round(w * p)), h)
    if direction == "up":          # edge travels bottom to top: new appears from the bottom
        ch = int(round(h * p))
        return (0, h - ch, w, ch)
    return (0, 0, w, int(round(h * p)))   # down


def slide_offsets(direction, w, h, p):
    """((old dx, old dy), (new dx, new dy)): both pictures move together like a push."""
    p = max(0.0, min(1.0, p))
    if direction == "left":
        d = int(round(w * p))
        return (-d, 0), (w - d, 0)
    if direction == "right":
        d = int(round(w * p))
        return (d, 0), (d - w, 0)
    if direction == "up":
        d = int(round(h * p))
        return (0, -d), (0, h - d)
    d = int(round(h * p))
    return (0, d), (0, d - h)


def blinds_rects(direction, w, h, p, count=BLIND_COUNT):
    """Visible parts of the new picture, one rect per slat. Slats open in a staggered order
    along the direction of travel; every slat is fully open at p = 1."""
    p = max(0.0, min(1.0, p))
    rects = []
    horizontal = direction in ("left", "right")      # vertical slats side by side
    span = (w if horizontal else h)
    for i in range(count):
        a, b = span * i // count, span * (i + 1) // count
        # stagger: slat order follows the travel direction; each slat opens over 60 % of the time
        order = i if direction in ("right", "down") else count - 1 - i
        start = 0.4 * order / max(1, count - 1)
        q = max(0.0, min(1.0, (p - start) / 0.6))
        size = int(round((b - a) * q))
        if horizontal:
            x = a if direction == "right" else b - size
            rects.append((x, 0, size, h))
        else:
            y = a if direction == "down" else b - size
            rects.append((0, y, w, size))
    return rects


def open_rect(direction, w, h, p):
    """Centre band showing the new picture: opens sideways for left/right, up/down for up/down."""
    p = max(0.0, min(1.0, p))
    if direction in ("left", "right"):
        cw = int(round(w * p))
        return ((w - cw) // 2, 0, cw, h)
    ch = int(round(h * p))
    return (0, (h - ch) // 2, w, ch)


def checkerboard_rects(w, h, p, cols=8):
    """Squares of the new picture. Cells of one chequer colour grow from their centres during the
    first half, the other colour during the second half; everything is covered at p = 1."""
    p = max(0.0, min(1.0, p))
    cell = max(1, int(-(-w // cols)))
    rows = int(-(-h // cell))
    rects = []
    for r in range(rows):
        for c in range(cols):
            x0, y0 = c * cell, r * cell
            x1, y1 = min(w, x0 + cell), min(h, y0 + cell)
            q = min(1.0, p * 2) if (r + c) % 2 == 0 else max(0.0, p * 2 - 1)
            if q <= 0:
                continue
            cw, ch = int(round((x1 - x0) * q)), int(round((y1 - y0) * q))
            if q >= 1.0:
                cw, ch = x1 - x0, y1 - y0
            rects.append((x0 + ((x1 - x0) - cw) // 2, y0 + ((y1 - y0) - ch) // 2, cw, ch))
    return rects


def _clip_halfplane(poly, t):
    """Keep the part of polygon poly (list of (u, v)) where u + v <= t."""
    out = []
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        fa, fb = a[0] + a[1] - t, b[0] + b[1] - t
        if fa <= 0:
            out.append(a)
        if (fa < 0 < fb) or (fb < 0 < fa):
            k = fa / (fa - fb)
            out.append((a[0] + k * (b[0] - a[0]), a[1] + k * (b[1] - a[1])))
    return out


def diagonal_polygon(direction, w, h, p):
    """Corner of the screen the new picture comes from, as a polygon (list of (x, y)).
    left = from the bottom right, right = from the top left, up = from the bottom left, down = from the top right."""
    p = max(0.0, min(1.0, p))
    sx, sy = {"left": (-1, -1), "right": (1, 1), "up": (1, -1), "down": (-1, 1)}.get(direction, (-1, -1))
    cx, cy = (0 if sx > 0 else w), (0 if sy > 0 else h)
    t = p * (w + h)
    if p >= 1.0:
        return [(0, 0), (w, 0), (w, h), (0, h)]
    poly = _clip_halfplane([(0, 0), (w, 0), (w, h), (0, h)], t)
    return [(cx + sx * u, cy + sy * v) for u, v in poly]


def iris_circle(w, h, p):
    """(centre x, centre y, radius) of the circle showing the new picture; covers the screen at p = 1."""
    p = max(0.0, min(1.0, p))
    return (w / 2.0, h / 2.0, p * ((w * w + h * h) ** 0.5) / 2.0 + (1 if p >= 1.0 else 0))


def zoom_states(p):
    """((old scale, old opacity), (new scale, new opacity)). Small scale moves only (old 1 -> 1.15,
    new 0.85 -> 1), cheap to draw on a slow PC."""
    p = max(0.0, min(1.0, p))
    return (1.0 + 0.15 * p, 1.0 - p), (0.85 + 0.15 * p, p)


def mosaic_rects(w, h, p, cols=16):
    """Scattered squares of the new picture, in a fixed pseudo-random order (same every time)."""
    p = max(0.0, min(1.0, p))
    cell = max(1, int(-(-w // cols)))
    rows = int(-(-h // cell))
    n = cols * rows
    order = sorted(range(n), key=lambda i: (i * 2654435761) % 4294967296)
    shown = n if p >= 1.0 else int(n * p)
    rects = []
    for i in order[:shown]:
        r, c = divmod(i, cols)
        x0, y0 = c * cell, r * cell
        rects.append((x0, y0, min(w, x0 + cell) - x0, min(h, y0 + cell) - y0))
    return rects


def clock_degrees(p):
    """How far (0..360, clockwise from 12 o'clock) the sweep has gone."""
    return 360.0 * max(0.0, min(1.0, p))
