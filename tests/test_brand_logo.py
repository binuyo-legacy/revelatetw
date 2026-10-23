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


def test_brand_mark_uses_logo_when_present():
    lab = ui._brand_mark(30)
    assert lab.objectName() == "brandLogo"
    assert not lab.pixmap().isNull()
    assert lab.pixmap().height() == 30


def test_brand_mark_falls_back_to_r_badge_when_logo_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(ui, "_LOGO_PATH", tmp_path / "missing.jpg")
    lab = ui._brand_mark(30)
    assert isinstance(lab, QLabel) and lab.text() == "R" and lab.objectName() == "brand"
    assert ui._logo_pixmap(96) is None
