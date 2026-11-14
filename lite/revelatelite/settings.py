"""Small JSON settings file. Missing or damaged file just gives the defaults."""
import json
import os

DEFAULTS = {
    "translation": "KJV",
    "font_scale": 100,       # percent, projection text size multiplier
    "theme": "navy",         # navy | black | gold
    "show_reference": True,
    "display": -1,           # -1 = automatic (first screen that is not the main one)
    "last_reference": "John 3:16",
    "font_family": "Georgia",  # verse font
    "bold": False,
    "bg_color": "",          # "" = use the theme colour, else "#rrggbb"
    "text_color": "",        # "" = use the theme colour
    "bg_kind": "color",      # color | gradient | image (see background.py)
    "grad_color1": "#1e3a8a",
    "grad_color2": "#0b0f19",
    "grad_direction": "vertical",   # vertical | horizontal | diagonal_down | diagonal_up
    "bg_image": "",          # full path of the chosen picture ("" = none)
    "image_mode": "fill",    # fill | fit | stretch | tile
    "image_dim": 30,         # percent darkening over a picture, keeps text readable
    "transition_effect": "dissolve",   # cut | fade | dissolve | wipe | slide | blinds | open (see transitions.py)
    "transition_ms": 400,    # 0 = instant
    "transition_dir": "auto",          # auto | left | right | up | down
    "transition_onoff": True,          # animate Project / Project Off
    "transition_switch": True,         # animate a change while already live (Next / Previous, then Project)
}

# Fonts that ship with Windows 8.1 (nothing to download), grouped for the Settings picker.
# Georgia stays first: it is the default and the safe fallback.
FONT_GROUPS = [
    ("Easy to read (serif)", ["Georgia", "Times New Roman", "Cambria", "Palatino Linotype", "Book Antiqua",
                              "Bookman Old Style", "Century Schoolbook", "Constantia", "Garamond"]),
    ("Clean (sans-serif)", ["Segoe UI", "Segoe UI Semibold", "Segoe UI Light", "Arial", "Verdana", "Tahoma",
                           "Trebuchet MS", "Calibri", "Candara", "Corbel", "Lucida Sans Unicode",
                           "Franklin Gothic Medium"]),
    ("Big and bold", ["Arial Black", "Impact"]),
    ("Decorative", ["Segoe Script", "Gabriola", "Comic Sans MS"]),
    ("Fixed width", ["Consolas", "Courier New"]),
]
FONTS = [f for _, names in FONT_GROUPS for f in names]


def valid_color(c):
    """True for '#rrggbb' only (no Qt needed)."""
    return (isinstance(c, str) and len(c) == 7 and c[0] == "#"
            and all(ch in "0123456789abcdefABCDEF" for ch in c[1:]))


def resolve_colors(theme, bg_color="", text_color=""):
    """(background, text, reference colour). Custom colours override the theme.
    The reference colour stays readable: theme colour, or the text colour when the background was changed."""
    bg, fg, refc = THEMES.get(theme, THEMES["navy"])
    if valid_color(bg_color):
        bg = bg_color
        if not valid_color(text_color) and bg_color.lower() != THEMES.get(theme, THEMES["navy"])[0]:
            fg = best_text_on(bg)
            refc = fg
    if valid_color(text_color):
        fg = text_color
        refc = text_color if valid_color(bg_color) else refc
    return bg, fg, refc


def best_text_on(bg):
    """White or near-black, whichever reads better on bg ('#rrggbb')."""
    r, g, b = (int(bg[i:i + 2], 16) for i in (1, 3, 5))
    return "#0b0f19" if (0.299 * r + 0.587 * g + 0.114 * b) > 150 else "#f8fafc"

THEMES = {  # name -> (background, text, reference colour); same palette as the main app
    "navy": ("#0b0f19", "#f8fafc", "#facc15"),
    "black": ("#000000", "#ffffff", "#facc15"),
    "gold": ("#facc15", "#0b0f19", "#0b0f19"),
}


def load(path):
    data = dict(DEFAULTS)
    try:
        with open(path, "r", encoding="utf-8") as f:
            saved = json.load(f)
        if isinstance(saved, dict):
            for k in DEFAULTS:
                if k in saved and isinstance(saved[k], type(DEFAULTS[k])):
                    data[k] = saved[k]
    except (OSError, ValueError):
        pass
    data["font_scale"] = max(50, min(200, data["font_scale"]))
    if data["font_family"] not in FONTS:
        data["font_family"] = "Georgia"
    for k in ("bg_color", "text_color"):
        if data[k] and not valid_color(data[k]):
            data[k] = ""
    if data["theme"] not in THEMES:
        data["theme"] = "navy"
    from . import background, transitions
    data.update(background.clean(data))
    data.update(transitions.clean(data))
    return data


def save(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)
