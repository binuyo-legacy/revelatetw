import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

import revelatetw.splash as splash

_APP = QApplication.instance() or QApplication([])


def test_shipped_assets_exist():
    assert splash.SPLASH_PATH.is_file()
    assert splash.LOGO_PATH.is_file()
    assert splash.SPLASH_PATH.parent == Path(splash.__file__).resolve().parent / "assets"


def test_fallback_chain(tmp_path):
    logo = tmp_path / "logo.png"
    logo.write_bytes(b"x")
    missing = tmp_path / "splash.png"
    assert splash.splash_source(missing, logo) == logo
    card = tmp_path / "card.png"
    card.write_bytes(b"x")
    assert splash.splash_source(card, logo) == card
    assert splash.splash_source(missing, tmp_path / "nologo.png") is None


def test_build_pixmap_from_card_and_scaled_to_width():
    pix = splash.build_splash_pixmap(splash.SPLASH_PATH)
    assert pix is not None and not pix.isNull()
    assert pix.width() == splash.MAX_WIDTH


def test_build_pixmap_from_logo_fallback_and_bar_position():
    pix = splash.build_splash_pixmap(splash.LOGO_PATH, bar_fraction=0.5)
    assert pix is not None and not pix.isNull()
    assert pix.width() <= splash.MAX_WIDTH


def test_build_pixmap_unreadable_returns_none(tmp_path):
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not an image")
    assert splash.build_splash_pixmap(bad) is None


def test_start_splash_no_image_is_noop(tmp_path):
    assert splash.start_splash(tmp_path / "none.png") is None


def test_start_splash_unreadable_is_noop_no_crash(tmp_path):
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"junk")
    assert splash.start_splash(bad) is None


def test_start_and_finish_splash_offscreen():
    win = splash.start_splash(splash.SPLASH_PATH)
    assert win is not None
    assert win.width() == splash.MAX_WIDTH
    assert win.windowFlags() & Qt.WindowType.FramelessWindowHint
    assert win.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    splash.finish_splash(win)
    splash.finish_splash(None)  # no-op


def test_no_splash_flag_parsing():
    assert splash.wants_splash([]) is True
    assert splash.wants_splash(["--gui"]) is True
    assert splash.wants_splash(["--gui", "--no-splash"]) is False


def test_app_icon_path_is_logo():
    assert splash.app_icon_path() == splash.LOGO_PATH
