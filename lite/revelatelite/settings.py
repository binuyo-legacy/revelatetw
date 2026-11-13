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
}

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
    if data["theme"] not in THEMES:
        data["theme"] = "navy"
    return data


def save(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)
