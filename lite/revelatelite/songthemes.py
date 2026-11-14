"""Song slide templates for Lite. Songs only: Bible verses never use these.

Each template is a plain dict of colours and switches; projection.SlideView draws it, so the small
in-app preview and the full-screen projector look the same. No pictures or fonts are bundled
(everything is painted), which keeps it light for Windows 8.1 32-bit / 2 GB PCs.
Plain Python 3.8, no Qt in this file.
"""

STANDARD = "standard"

# key -> template. frame: single | none | bar | card. two_tone: first line in the text colour, the rest in the accent colour.
TEMPLATES = {
    "midnight": dict(
        name="Midnight Glow",
        blurb="Deep navy with a soft glow, one thin rounded silver-blue frame, bold white words and the song title centred below.",
        bg=("radial", "#1c2d5e", "#060a16"), text="#f4f7ff", accent="#9bb8ff", tag="#9bb8ff", dim="#aab6d6",
        frame="single", two_tone=False, divider=False, pill=False, shadow=True),
    "classic": dict(
        name="Classic Black",
        blurb="Pure black, big white words, small section name above and song title below. Clear and plain, easy on every projector.",
        bg=("solid", "#000000", "#000000"), text="#ffffff", accent="#ffffff", tag="#9ca3af", dim="#9ca3af",
        frame="none", two_tone=False, divider=False, pill=False, shadow=False),
    "sunrise": dict(
        name="Warm Sunrise",
        blurb="Deep red to amber glow with cream words, a rounded section tag on top and a soft footer.",
        bg=("linear", "#4a0f1f", "#b4531a"), text="#fff7e6", accent="#ffd58a", tag="#ffe3b0", dim="#ffe3b0",
        frame="none", two_tone=False, divider=True, pill=True, shadow=True),
    "light": dict(
        name="Soft Ivory",
        blurb="Light ivory page, dark text, a thin blue bar on the left and the song title below. Good for bright rooms.",
        bg=("solid", "#faf6ec", "#faf6ec"), text="#1f2937", accent="#1d4ed8", tag="#1d4ed8", dim="#6b7280",
        frame="bar", two_tone=False, divider=False, pill=False, shadow=False),
    "royal": dict(
        name="Royal Card",
        blurb="Purple night sky with a soft rounded card behind the words, section name above, title and slide count below.",
        bg=("linear", "#1b1038", "#3b1d6e"), text="#ffffff", accent="#c4b5fd", tag="#c4b5fd", dim="#ddd6fe",
        frame="card", two_tone=False, divider=False, pill=True, shadow=True),
}
KEYS = [STANDARD] + list(TEMPLATES)      # 'standard' = the normal Settings look (colours, gradient, picture)
STANDARD_LABEL = "Standard (my Settings colours and background)"


def label(key):
    return STANDARD_LABEL if key == STANDARD else TEMPLATES[key]["name"]


def blurb(key):
    return ("Songs use the colours, background and font from Settings, like verses." if key == STANDARD
            else TEMPLATES[key]["blurb"])


def clean(key):
    return key if key in KEYS else STANDARD


def meta_for(song, i):
    """(title, artist, section, slide number, slide total) for slide i of a song."""
    return (song.title, song.artist, song.slides[i]["label"], i + 1, len(song.slides))


def pill_text(meta):
    return "%s \u00b7 %d/%d" % (meta[2], meta[3], meta[4])


def footer_text(meta):
    return (meta[0], meta[1])


SAMPLE_META = ("Way Maker", "Sinach", "Chorus", 2, 8)
SAMPLE_BODY = "Way maker, miracle worker\nPromise keeper, light in the darkness"


# ---------------------------------------------------------------------------------------------
# Customising a template. The five presets above never change. Each template keeps its own small
# dict of overrides (settings key "song_custom"); resolve() lays them over the preset. Songs only.
# ---------------------------------------------------------------------------------------------
COLOR_FIELDS = ("text", "accent", "tag", "dim", "bg1", "bg2")
CHOICES = {
    "bg_kind": ("solid", "linear", "radial"),
    "frame": ("none", "single", "bar", "card"),
    "align": ("left", "center", "right"),
    "valign": ("top", "middle", "bottom"),
}
BOOL_FIELDS = ("show_label", "show_footer", "show_count", "upper", "shadow", "two_tone", "divider", "pill", "bold")
SCALE_MIN, SCALE_MAX = 50, 150
FIELD_NAMES = COLOR_FIELDS + tuple(CHOICES) + BOOL_FIELDS + ("scale", "font")


def _is_color(c):
    return (isinstance(c, str) and len(c) == 7 and c[0] == "#"
            and all(ch in "0123456789abcdefABCDEF" for ch in c[1:]))


def clean_overrides(raw):
    """Keep only valid override fields (bad values are dropped, so the preset value shows)."""
    out = {}
    if not isinstance(raw, dict):
        return out
    from . import settings
    for k, v in raw.items():
        if k in COLOR_FIELDS and _is_color(v):
            out[k] = v.lower()
        elif k in CHOICES and v in CHOICES[k]:
            out[k] = v
        elif k in BOOL_FIELDS and isinstance(v, bool):
            out[k] = v
        elif k == "scale" and isinstance(v, int) and not isinstance(v, bool):
            out[k] = max(SCALE_MIN, min(SCALE_MAX, v))
        elif k == "font" and isinstance(v, str) and (v == "" or v in settings.FONTS):
            out[k] = v
    return out


def clean_custom(raw):
    """{template key: overrides}. Unknown templates ('standard' too) and empty entries are dropped."""
    out = {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            if k in TEMPLATES:
                o = clean_overrides(v)
                if o:
                    out[k] = o
    return out


def copy_custom(custom):
    return {k: dict(v) for k, v in (custom or {}).items()}


def resolve(key, custom=None):
    """The template as drawn: preset + this template's overrides. None for 'standard'."""
    if key not in TEMPLATES:
        return None
    base = TEMPLATES[key]
    t = dict(base)
    kind, c1, c2 = base["bg"]
    t.update(bg_kind=kind, bg1=c1, bg2=c2, align="left" if base["frame"] == "bar" else "center", valign="middle",
             scale=100, font="", bold=True, show_label=True, show_footer=True, show_count=bool(base["pill"]), upper=True)
    t.update(clean_overrides((custom or {}).get(key)))
    t["bg"] = (t["bg_kind"], t["bg1"], t["bg2"])
    return t


def changed_fields(key, custom=None):
    """Names of the fields that differ from the preset (used for 'Customised' and Reset)."""
    if key not in TEMPLATES:
        return []
    ov = clean_overrides((custom or {}).get(key))
    base = resolve(key, None)
    return [f for f, v in ov.items() if base.get(f) != v]
