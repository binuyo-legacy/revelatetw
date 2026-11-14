"""Bible verse slide templates for Lite. Verses only: songs never use these.

'default' is the normal verse look (Settings colours, background, font), drawn exactly as before.
The other presets are plain dicts of colours and switches that projection.SlideView paints, so the
small in-app preview and the full-screen projector look the same. Nothing is bundled (no pictures,
no fonts), which keeps it light for Windows 8.1 32-bit / 2 GB PCs. Plain Python 3.8, no Qt here.
"""

DEFAULT = "default"

# frame: none | single | double | bar | card.  ref_pos: top | bottom.  ref_style: plain | pill.
TEMPLATES = {
    "parchment": dict(
        name="Parchment",
        blurb="Warm ivory page, dark brown words, a thin double border and the reference under a small divider. Easy to read in bright rooms.",
        bg=("solid", "#f6efdc", "#f6efdc"), text="#2b1d0e", accent="#8a5a14", dim="#7a6a52",
        frame="double", align="center", ref_pos="bottom", ref_style="plain", divider=True, shadow=False),
    "midnight": dict(
        name="Midnight Psalm",
        blurb="Deep navy glow, white words and the reference in gold at the top with a fine gold line. Calm and clear.",
        bg=("radial", "#1c2d5e", "#050914"), text="#f4f7ff", accent="#facc15", dim="#aab6d6",
        frame="none", align="center", ref_pos="top", ref_style="plain", divider=True, shadow=True),
    "gold": dict(
        name="Gold Frame",
        blurb="Pure black, one thin rounded gold frame, cream words and the gold reference at the bottom.",
        bg=("solid", "#000000", "#000000"), text="#fff6dc", accent="#facc15", dim="#b59a3c",
        frame="single", align="center", ref_pos="bottom", ref_style="plain", divider=False, shadow=False),
    "dawn": dict(
        name="Dawn Banner",
        blurb="Deep plum to warm amber, cream words and the reference in a rounded tag at the top.",
        bg=("linear", "#3a1030", "#b4531a"), text="#fff7e6", accent="#ffe3b0", dim="#ffe3b0",
        frame="none", align="center", ref_pos="top", ref_style="pill", divider=False, shadow=True),
    "scripture": dict(
        name="Gold Bar",
        blurb="Dark slate, a gold bar on the left, left-aligned words and the reference at the bottom left. Modern and tidy.",
        bg=("linear", "#0f172a", "#1e293b"), text="#f8fafc", accent="#facc15", dim="#94a3b8",
        frame="bar", align="left", ref_pos="bottom", ref_style="plain", divider=False, shadow=False),
    "cardroyal": dict(
        name="Royal Card",
        blurb="Purple night with a soft rounded card behind the words and the reference in a rounded tag below.",
        bg=("linear", "#1b1038", "#3b1d6e"), text="#ffffff", accent="#ddd6fe", dim="#ddd6fe",
        frame="card", align="center", ref_pos="bottom", ref_style="pill", divider=False, shadow=True),
}
KEYS = [DEFAULT] + list(TEMPLATES)
DEFAULT_LABEL = "Default (my Settings colours and background)"


def label(key):
    return DEFAULT_LABEL if key == DEFAULT else TEMPLATES[key]["name"]


def blurb(key):
    return ("Verses use the colours, background and font from Settings, as before." if key == DEFAULT
            else TEMPLATES[key]["blurb"])


def clean(key):
    return key if isinstance(key, str) and key in KEYS else DEFAULT


def resolve(key):
    """The template as drawn, or None for 'default' (the old look, untouched)."""
    if key not in TEMPLATES:
        return None
    t = dict(TEMPLATES[key])
    t["bg_kind"], t["bg1"], t["bg2"] = t["bg"]
    return t


SAMPLE_REF = "John 3:16"
SAMPLE_BODY = "For God so loved the world, that he gave his only begotten Son, that whosoever believeth in him should not perish, but have everlasting life."
