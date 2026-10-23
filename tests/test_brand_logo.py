import os
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QApplication, QLabel

import revelatetw.ui as ui

_APP = QApplication.instance() or QApplication([])


def test_logo_file_ships_in_package():
    assert ui._LOGO_PATH.is_file()
    assert ui._LOGO_PATH.parent == ui.Path(ui.__file__).resolve().parent / "assets"


def test_logo_is_png_with_alpha():
    assert ui._LOGO_PATH.name == "logo.png"
    from PyQt6.QtGui import QImage
    img = QImage(str(ui._LOGO_PATH))
    assert not img.isNull() and img.hasAlphaChannel()
    assert img.pixelColor(0, 0).alpha() == 0


def test_brand_mark_uses_logo_when_present():
    lab = ui._brand_mark(30)
    assert lab.objectName() == "brandLogo"
    assert not lab.pixmap().isNull()
    assert lab.pixmap().height() == 30
    assert "background" not in lab.styleSheet()
    assert lab.styleSheet() == ""


def test_brand_mark_falls_back_to_r_badge_when_logo_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(ui, "_LOGO_PATH", tmp_path / "missing.png")
    lab = ui._brand_mark(30)
    assert isinstance(lab, QLabel) and lab.text() == "R" and lab.objectName() == "brand"
    assert ui._logo_pixmap(96) is None
