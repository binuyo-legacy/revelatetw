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
    "outline_on": False,     # draw an outline around the verse text (preview and screen alike)
    "outline_color": "",     # "" = automatic (dark outline on light text, light on dark text), else "#rrggbb"
    "outline_px": 3,         # thickness 1..10 (scales with screen height, so preview matches the projector)
    "song_theme": "standard",  # song slide template (songthemes.py); Bible verses never use it
    "song_custom": {},       # per-template song look overrides {template: {field: value}} (songthemes.py)
    "verse_theme": "default",  # Bible verse slide template (versethemes.py); songs never use it
    "timer_template": "revelate",  # Timer tab look (timer.py); verses/songs never use it
    "timer_text_color": "",   # "" = template text colour, else "#rrggbb"
    "timer_bg_color": "",     # "" = template background, else "#rrggbb"
    "timer_mode": "time",     # time | countdown (timer.py); "clock" from older saves is mapped to "time"
    "timer_source": "live",   # live (system clock) | manual (operator-set time) for Time mode
    "timer_manual_hour": 9,   # manual Time value, 0..23
    "timer_manual_minute": 0, # manual Time value, 0..59
    "timer_manual_second": 0, # manual Time value, 0..59
    "timer_message": "",      # operator's own core message/title shown with the time/countdown
    "timer_font_family": "Segoe UI",  # projected timer font (timer.py FONT_FAMILIES)
    "timer_format": "24",     # 24 | 12
    "timer_ampm": False,      # show AM/PM marker (12h only)
    "timer_duration": 300,    # countdown length in seconds
    "timer_style": "digital", # digital | analog
    "timer_show_seconds": False,  # clock seconds in digital readout
    "timer_show_shape": True,  # inner curved plate on digital templates
    "timer_text_scale": 100,   # digital display text size, 50..300 (% of autosize)
    "timer_speaker": "",       # speaker name shown in the bottom-left tag (Timer projection only)
    "timer_show_speaker": False,  # ON/OFF hide toggle: False hides the tag entirely
    "timer_speaker_label_font": "",  # "" = core timer font, else a FONT_FAMILIES face
    "timer_speaker_name_font": "",   # independent of the label + core font
    "timer_speaker_label_color": "", # "" = template accent, else "#rrggbb"
    "timer_speaker_name_color": "",  # "" = template text colour, else "#rrggbb"
    "bg_kind": "color",      # color | gradient | image (see background.py)
    "grad_color1": "#1e3a8a",
    "grad_color2": "#0b0f19",
    "grad_direction": "vertical",   # vertical | horizontal | diagonal_down | diagonal_up
    "bg_image": "",          # full path of the chosen picture ("" = none)
    "image_mode": "fill",    # fill | fit | stretch | tile
    "image_dim": 30,         # percent darkening over a picture, keeps text readable
    "transition_effect": "dissolve",   # cut | fade | dissolve | wipe | slide | blinds | open | checkerboard | diagonal | iris | zoom | mosaic | clock (see transitions.py)
    "proj_on_effect": "dissolve",      # effect when Project turns the full-screen display on (same choices as transition_effect)
    "proj_off_effect": "dissolve",     # effect when Project Off turns it off (independent of transition_effect)
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


OUTLINE_MIN, OUTLINE_MAX = 1, 10


def resolve_outline(fg, outline_color=""):
    """Outline colour to draw: the chosen one, or automatic (opposite of the text colour)."""
    return outline_color if valid_color(outline_color) else best_text_on(fg if valid_color(fg) else "#ffffff")


def outline_pixels(height, thickness):
    """Outline radius in pixels for a surface of this height (same look in preview and projector)."""
    t = max(OUTLINE_MIN, min(OUTLINE_MAX, int(thickness)))
    return max(1, int(round(height * t / 900.0)))


def _lum(c):
    r, g, b = (int(c[i:i + 2], 16) for i in (1, 3, 5))
    return 0.299 * r + 0.587 * g + 0.114 * b


def outline_hint(fg, outline_color):
    """Plain-words warning when a chosen outline colour is too close to the text colour, else ''."""
    if valid_color(outline_color) and valid_color(fg) and abs(_lum(outline_color) - _lum(fg)) < 70:
        return "The outline is almost the same colour as the text, so it will not help. Pick a darker or lighter outline."
    return ""


def outline_offsets(r):
    """Points on a ring (plus the inner ring for thick outlines) used to stamp the outline."""
    import math
    pts = set()
    for rad in ([r] if r <= 2 else [r, max(1, r // 2)]):
        steps = 8 if rad <= 1 else 16
        for i in range(steps):
            a = 2 * math.pi * i / steps
            pts.add((int(round(rad * math.cos(a))), int(round(rad * math.sin(a)))))
    pts.discard((0, 0))
    return sorted(pts)


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
            for k in ("proj_on_effect", "proj_off_effect"):   # older files: start as the effect they already had
                if k not in saved and isinstance(saved.get("transition_effect"), str):
                    data[k] = saved["transition_effect"]
    except (OSError, ValueError):
        pass
    data["font_scale"] = max(50, min(200, data["font_scale"]))
    if data["font_family"] not in FONTS:
        data["font_family"] = "Georgia"
    for k in ("bg_color", "text_color"):
        if data[k] and not valid_color(data[k]):
            data[k] = ""
    if data["outline_color"] and not valid_color(data["outline_color"]):
        data["outline_color"] = ""
    data["outline_px"] = max(OUTLINE_MIN, min(OUTLINE_MAX, data["outline_px"]))
    if data["theme"] not in THEMES:
        data["theme"] = "navy"
    from . import background, songthemes, timer as timermod, transitions, versethemes
    data["song_theme"] = songthemes.clean(data["song_theme"])
    data["song_custom"] = songthemes.clean_custom(data["song_custom"])
    data["verse_theme"] = versethemes.clean(data["verse_theme"])
    data["timer_template"] = timermod.clean(data["timer_template"])
    data["timer_mode"] = timermod.clean_mode(data["timer_mode"])
    data["timer_source"] = timermod.clean_source(data["timer_source"])
    data["timer_message"] = timermod.clean_message(data["timer_message"])
    data["timer_font_family"] = timermod.clean_font(data["timer_font_family"])
    data["timer_manual_hour"], data["timer_manual_minute"], data["timer_manual_second"] = timermod.clamp_time(
        data["timer_manual_hour"], data["timer_manual_minute"], data["timer_manual_second"])
    data["timer_format"] = timermod.clean_format(data["timer_format"])
    data["timer_style"] = timermod.clean_style(data["timer_style"])
    for k in ("timer_text_color", "timer_bg_color"):
        if data[k] and not valid_color(data[k]):
            data[k] = ""
    if not isinstance(data["timer_ampm"], bool):
        data["timer_ampm"] = bool(data["timer_ampm"])
    if not isinstance(data["timer_show_shape"], bool):
        data["timer_show_shape"] = bool(data["timer_show_shape"])
    data["timer_text_scale"] = timermod.clean_text_scale(data["timer_text_scale"])
    data["timer_duration"] = timermod.clamp_duration(data["timer_duration"])
    data["timer_speaker"] = timermod.clean_speaker(data["timer_speaker"])
    if not isinstance(data["timer_show_speaker"], bool):
        data["timer_show_speaker"] = bool(data["timer_show_speaker"])
    data["timer_speaker_label_font"] = (
        timermod.clean_font(data["timer_speaker_label_font"]) if data["timer_speaker_label_font"] else "")
    data["timer_speaker_name_font"] = (
        timermod.clean_font(data["timer_speaker_name_font"]) if data["timer_speaker_name_font"] else "")
    for k in ("timer_speaker_label_color", "timer_speaker_name_color"):
        if data[k] and not valid_color(data[k]):
            data[k] = ""
    data.update(background.clean(data))
    data.update(transitions.clean(data))
    return data


def save(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)
