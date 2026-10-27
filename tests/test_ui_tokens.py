"""Design tokens: contrast, minimum type size, and stylesheet integrity. No Qt needed."""
import re

import pytest

from revelatetw.ui_tokens import (COLORS, CONTRAST_PAIRS, TYPE, Colors, build_qss,
                                  contrast_ratio, luminance)


def test_contrast_helper_known_values():
    assert contrast_ratio("#000000", "#ffffff") == pytest.approx(21.0, rel=1e-3)
    assert contrast_ratio("#777777", "#777777") == pytest.approx(1.0)
    assert luminance("#ffffff") == pytest.approx(1.0)
    assert luminance("#000000") == pytest.approx(0.0)


@pytest.mark.parametrize("fg,bg,minimum", CONTRAST_PAIRS)
def test_every_text_pair_meets_its_contrast_minimum(fg, bg, minimum):
    ratio = contrast_ratio(getattr(COLORS, fg), getattr(COLORS, bg))
    assert ratio >= minimum, f"{fg} on {bg} is {ratio:.2f}:1, needs {minimum}:1"


def test_all_colour_tokens_are_valid_hex():
    for name, value in vars(Colors()).items():
        assert re.fullmatch(r"#[0-9a-f]{6}", value), f"{name}={value!r}"


def test_no_font_size_below_caption():
    sizes = [int(m) for m in re.findall(r"font-size:\s*(\d+)px", build_qss())]
    assert sizes, "stylesheet has no font sizes"
    assert min(sizes) >= TYPE.caption


def test_transcript_is_the_largest_body_text():
    qss = build_qss()
    transcript = int(re.search(r"QLabel#transcript \{[^}]*font-size:\s*(\d+)px", qss).group(1))
    body = int(re.search(r"QLabel#tileValue \{[^}]*font-size:\s*(\d+)px", qss).group(1))
    assert transcript > body


def test_stylesheet_has_no_leftover_format_braces_or_none():
    qss = build_qss()
    assert "None" not in qss
    # every '{' opens a rule and every '}' closes one
    assert qss.count("{") == qss.count("}")


def test_scale_multiplies_font_sizes():
    base = [int(m) for m in re.findall(r"font-size:\s*(\d+)px", build_qss())]
    big = [int(m) for m in re.findall(r"font-size:\s*(\d+)px", build_qss(scale=1.5))]
    assert len(base) == len(big)
    assert all(b >= a for a, b in zip(base, big)) and max(big) > max(base)


# Selectors the operator window relied on before the tokens were introduced. Dropping one would
# silently unstyle a widget, so each must still exist.
LEGACY_SELECTORS = [
    "QMainWindow, QWidget#root", "QFrame#toolbar", "QFrame#panel", "QFrame#card",
    'QFrame#card[selected="true"]', "QFrame#tile", "QFrame#slide", "QLabel", "QLabel#brand",
    "QLabel#title", "QLabel#sub", "QLabel#panelTitle", "QLabel#badge", "QLabel#badgeGreen",
    "QLabel#live", "QLabel#timer", "QLabel#tileLabel", "QLabel#tileValue", "QLabel#verse",
    "QLabel#ref", "QLabel#transcript", "QLabel#time", "QLabel#hit", "QLabel#footer",
    "QLabel#footerOk", "QLabel#slideRef", "QLabel#slideText", "QPushButton", "QPushButton:hover",
    "QPushButton#approve", "QPushButton#reject", "QPushButton#seg", 'QPushButton#seg[active="true"]',
    "QPushButton#nav", "QPushButton#nav:disabled", "QPushButton#live", 'QPushButton#live[on="false"]',
    "QTabWidget::pane", "QTabBar::tab", "QTabBar::tab:selected", "QLabel#liveNote",
    "QPushButton#ghost", "QPushButton#primary", "QPushButton#primary:hover", "QPushButton#subtle",
    "QPushButton#subtle:disabled", "QPushButton#danger", "QPushButton#danger:disabled",
    "QPushButton#small", "QLabel#emptyIcon", "QLabel#emptyHint", "QLabel#emptyIconBook",
    "QLabel#mediaEmptyIcon", "QListWidget#mediaGrid", "QListWidget#mediaGrid::item",
    "QListWidget#mediaGrid::item:hover", "QListWidget#mediaGrid::item:selected",
    "QLineEdit, QComboBox", "QLineEdit:focus, QComboBox:focus", "QComboBox QAbstractItemView",
    "QListWidget", "QListWidget::item:selected", "QDoubleSpinBox", "QScrollArea",
    "QScrollArea > QWidget > QWidget", "QFrame#statusbar",
]


@pytest.mark.parametrize("selector", LEGACY_SELECTORS)
def test_legacy_selector_still_styled(selector):
    qss = build_qss()
    assert re.search(rf"^{re.escape(selector)} \{{", qss, re.M), f"{selector} lost its rule"
