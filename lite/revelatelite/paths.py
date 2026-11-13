"""Where things live. Works from source and from a PyInstaller build (frozen)."""
import os
import sys


def resource_root():
    """Folder that contains data/ and revelatetw/assets/ (repo root, or the unpacked bundle)."""
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def bible_dir():
    return os.path.join(resource_root(), "data", "bible")


def logo_path():
    return os.path.join(resource_root(), "revelatetw", "assets", "logo.png")


def user_dir():
    """Settings and service lists go here (%APPDATA%\\RevelateTWLite on Windows)."""
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    path = os.path.join(base, "RevelateTWLite")
    os.makedirs(path, exist_ok=True)
    return path


def user_bible_dir():
    """Bibles the church imports itself. Not created until the first import (the program folder may be read-only)."""
    return os.path.join(user_dir(), "bibles")
