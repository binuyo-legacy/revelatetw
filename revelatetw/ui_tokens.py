"""Design tokens and the operator-window stylesheet.

Pure Python, no Qt import, so the palette can be unit-tested (see tests/test_ui_tokens.py).
Every colour, font size and spacing value used by the operator window lives here. Change a value once
and the whole window follows; do not add hex codes or pixel sizes to ui.py.

Rules the palette follows:
  * Gold (`accent`) marks the one thing that is selected or is the primary action. It is not used for
    hover states, badges or decoration, so it keeps its meaning.
  * Text on every surface meets WCAG AA contrast (4.5:1); disabled text meets 3:1.
  * Nothing is smaller than `Type.caption` (12 px). The sermon transcript, which the operator reads
    while the preacher speaks, is the largest body text on screen.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Colors:
    # surfaces, darkest to lightest
    bg: str = "#0b0f19"             # window background
    surface_input: str = "#0f1522"  # text boxes, lists, status bar
    surface: str = "#131926"        # panels
    surface_alt: str = "#161c2a"    # cards and tiles
    toolbar: str = "#171d2b"
    surface_raised: str = "#1d2535"  # buttons, tabs
    selected_bg: str = "#1b2231"    # selected card, first queue row
    # borders
    border: str = "#232b3b"         # hairlines between regions
    border_card: str = "#2a3346"
    border_control: str = "#33405a"  # buttons and inputs
    border_hover: str = "#52668c"   # neutral hover (gold is reserved for selection)
    # text
    text: str = "#e5e7eb"
    text_strong: str = "#f8fafc"
    text_muted: str = "#a3b1c6"
    text_faint: str = "#8b9ab0"     # timestamps and other tertiary text
    text_disabled: str = "#6f7e94"
    # accent (gold): selection and the primary action only
    accent: str = "#facc15"
    accent_hover: str = "#fde047"
    accent_on: str = "#0b0f19"      # text on an accent fill
    accent_soft: str = "#2a2412"    # tinted background behind accent text
    # states
    success_text: str = "#86efac"
    success_bg: str = "#1f3a2e"
    approve_bg: str = "#2f9e62"
    approve_hover: str = "#38b273"
    approve_on: str = "#04120a"
    approve_border: str = "#3cc47e"
    danger_text: str = "#fca5a5"
    danger_bg: str = "#3a1f2a"
    danger_border: str = "#7f2a38"
    danger_quiet: str = "#d4909b"   # text of the low-emphasis delete button
    danger_quiet_border: str = "#4a2a32"
    warning: str = "#f59e0b"
    warning_bg: str = "#2a2110"
    warning_border: str = "#6b4e12"
    live_on_text: str = "#4ade80"
    live_on_bg: str = "#14532d"
    live_on_border: str = "#22c55e"


@dataclass(frozen=True)
class Type:
    """Font sizes in px (before the optional scale factor)."""
    caption: int = 12      # smallest text allowed: footers, hints, badges, tile labels
    body: int = 13         # buttons, inputs, tabs, general labels
    emphasis: int = 14     # titles inside panels, verse text, scripture references
    title: int = 16        # app title
    transcript: int = 15   # live sermon transcript: read at a glance during the service
    icon: int = 36         # large empty-state glyphs


@dataclass(frozen=True)
class Space:
    """Spacing in px, for layouts."""
    xs: int = 4
    sm: int = 6
    md: int = 8
    lg: int = 12
    xl: int = 16
    panel_x: int = 12      # inner padding of a panel, sides
    panel_y: int = 10      # inner padding of a panel, top and bottom
    gap: int = 10          # space between neighbouring panels
    row_height: int = 38   # approval-queue rows: easy to hit with a mouse and to read at a glance


COLORS = Colors()
TYPE = Type()
SPACE = Space()

# (foreground role, background role, minimum ratio). tests/test_ui_tokens.py checks every pair.
CONTRAST_PAIRS: tuple[tuple[str, str, float], ...] = (
    ("text", "bg", 4.5), ("text", "surface", 4.5), ("text", "surface_alt", 4.5),
    ("text", "surface_input", 4.5), ("text", "surface_raised", 4.5), ("text", "selected_bg", 4.5),
    ("text_strong", "surface", 4.5), ("text_strong", "toolbar", 4.5),
    ("text_muted", "bg", 4.5), ("text_muted", "surface", 4.5), ("text_muted", "surface_alt", 4.5),
    ("text_muted", "surface_input", 4.5), ("text_muted", "surface_raised", 4.5),
    ("text_muted", "toolbar", 4.5),
    ("text_faint", "surface", 4.5), ("text_faint", "surface_input", 4.5),
    ("text_disabled", "surface_raised", 3.0), ("text_disabled", "surface", 3.0),
    ("accent", "surface", 4.5), ("accent", "selected_bg", 4.5), ("accent", "accent_soft", 4.5),
    ("accent", "bg", 4.5),
    ("accent_on", "accent", 4.5), ("accent_on", "accent_hover", 4.5),
    ("success_text", "success_bg", 4.5), ("success_text", "surface_input", 4.5),
    ("approve_on", "approve_bg", 4.5), ("approve_on", "approve_hover", 4.5),
    ("danger_text", "danger_bg", 4.5), ("danger_quiet", "surface", 4.5),
    ("danger_quiet", "surface_input", 4.5),
    ("warning", "bg", 4.5), ("warning", "warning_bg", 4.5), ("warning", "surface_input", 4.5),
    ("live_on_text", "live_on_bg", 4.5),
    ("text_strong", "surface_input", 4.5),
)


def _channel(c: float) -> float:
    c /= 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def luminance(hex_color: str) -> float:
    """WCAG relative luminance of '#rrggbb'."""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def contrast_ratio(fg: str, bg: str) -> float:
    """WCAG contrast ratio between two '#rrggbb' colours (1.0 to 21.0)."""
    a, b = luminance(fg), luminance(bg)
    hi, lo = (a, b) if a >= b else (b, a)
    return (hi + 0.05) / (lo + 0.05)


def build_qss(c: Colors = COLORS, t: Type = TYPE, scale: float = 1.0) -> str:
    """The operator-window stylesheet. `scale` multiplies every font size (for a future text-size setting)."""
    def px(n: int) -> str:
        return f"{max(1, round(n * scale))}px"

    return f"""
QMainWindow, QWidget#root {{ background: {c.bg}; }}
QFrame#toolbar {{ background: {c.toolbar}; border-bottom: 1px solid {c.border}; }}
QFrame#panel {{ background: {c.surface}; border: 1px solid {c.border}; border-radius: 10px; }}
QFrame#card {{ background: {c.surface_alt}; border: 1px solid {c.border_card}; border-radius: 10px; }}
QFrame#card[selected="true"] {{ border: 2px solid {c.accent}; background: {c.selected_bg}; }}
QFrame#tile {{ background: {c.surface_alt}; border: 1px solid {c.border_card}; border-radius: 8px; }}
QFrame#slide {{ background: {c.bg}; border: 2px solid {c.accent}; border-radius: 6px; }}
QFrame#setupBody {{ background: {c.surface_input}; border: 1px solid {c.border_card}; border-radius: 8px; }}
QFrame#checklist {{ background: {c.surface_input}; border: 1px solid {c.border_card}; border-radius: 10px; }}
QFrame#liveNote {{ background: {c.warning_bg}; border: 1px solid {c.warning_border}; border-radius: 8px; }}
QFrame#liveNote QLabel {{ color: {c.warning}; background: transparent; }}

QLabel {{ color: {c.text}; font-size: {px(t.body)}; }}
QLabel#brand {{ color: {c.accent_on}; background: {c.accent}; border-radius: 8px; font-weight: 800; font-size: {px(t.emphasis + 1)}; padding: 2px 7px; }}
QLabel#title {{ color: {c.text_strong}; font-size: {px(t.title)}; font-weight: 700; }}
QLabel#sub {{ color: {c.text_muted}; font-size: {px(t.caption)}; }}
QLabel#fieldLabel {{ color: {c.text_muted}; font-size: {px(t.caption)}; font-weight: 600; }}
QLabel#panelTitle {{ color: {c.text_strong}; font-size: {px(t.emphasis)}; font-weight: 700; }}
QLabel#badge {{ color: {c.text_muted}; background: {c.surface_raised}; border-radius: 9px; padding: 2px 8px; font-size: {px(t.caption)}; font-weight: 600; }}
QLabel#badgeGreen {{ color: {c.success_text}; background: {c.success_bg}; border-radius: 9px; padding: 2px 8px; font-size: {px(t.caption)}; font-weight: 700; }}
QLabel#live {{ color: {c.danger_text}; background: {c.danger_bg}; border: 1px solid {c.danger_border}; border-radius: 12px; padding: 3px 10px; font-weight: 800; }}
QLabel#timer {{ color: {c.accent}; font-family: Consolas, monospace; font-size: {px(t.emphasis)}; font-weight: 700; }}
QLabel#tileLabel {{ color: {c.text_muted}; font-size: {px(t.caption)}; }}
QLabel#tileValue {{ color: {c.text_strong}; font-size: {px(t.body)}; font-weight: 600; }}
QLabel#verse {{ color: {c.text}; font-style: italic; font-size: {px(t.emphasis)}; }}
QLabel#ref {{ color: {c.accent}; font-weight: 700; font-size: {px(t.emphasis)}; }}
QLabel#transcript {{ color: {c.text}; font-size: {px(t.transcript)}; }}
QLabel#time {{ color: {c.text_faint}; font-family: Consolas, monospace; font-size: {px(t.caption)}; }}
QLabel#hit {{ color: {c.accent}; background: rgba(250,204,21,0.14); border-radius: 4px; padding: 0 3px; font-weight: 700; }}
QLabel#footer {{ color: {c.text_muted}; font-size: {px(t.caption)}; }}
QLabel#footerOk {{ color: {c.success_text}; font-size: {px(t.caption)}; }}
QLabel#footerWarn {{ color: {c.warning}; font-size: {px(t.caption)}; font-weight: 700; }}
QLabel#slideRef {{ color: {c.accent}; font-weight: 700; font-size: {px(t.body)}; }}
QLabel#slideText {{ color: {c.text_strong}; font-family: Georgia; font-size: {px(t.emphasis)}; }}
QLabel#checkTitle {{ color: {c.text_strong}; font-size: {px(t.emphasis)}; font-weight: 700; background: transparent; }}
QLabel#checkText {{ color: {c.text}; font-size: {px(t.body)}; background: transparent; }}
QLabel#checkOk {{ color: {c.success_text}; font-size: {px(t.emphasis)}; font-weight: 800; background: transparent; }}
QLabel#checkWarn {{ color: {c.warning}; font-size: {px(t.emphasis)}; font-weight: 800; background: transparent; }}
QLabel#checkInfo {{ color: {c.text_muted}; font-size: {px(t.emphasis)}; font-weight: 800; background: transparent; }}
QLabel#liveNote {{ color: {c.warning}; font-size: {px(t.caption)}; }}
QLabel#emptyIcon {{ color: #8a7224; font-size: {px(t.icon)}; }}
QLabel#emptyHint {{ color: {c.text_muted}; font-size: {px(t.caption)}; }}
QLabel#emptyIconBook {{ color: #5b6478; font-size: {px(t.icon - 4)}; }}
QLabel#mediaEmptyIcon {{ color: #5b6478; font-size: {px(t.icon)}; }}

QPushButton {{ background: {c.surface_raised}; color: {c.text}; border: 1px solid {c.border_control}; border-radius: 7px; padding: 5px 12px; font-size: {px(t.body)}; font-weight: 600; }}
QPushButton:hover {{ border-color: {c.border_hover}; }}
QPushButton:disabled {{ color: {c.text_disabled}; }}
QPushButton#approve {{ background: {c.approve_bg}; color: {c.approve_on}; border: 1px solid {c.approve_border}; font-size: {px(t.emphasis)}; font-weight: 800; min-height: 26px; }}
QPushButton#approve:hover {{ background: {c.approve_hover}; }}
QPushButton#approve:disabled {{ background: {c.surface_raised}; color: {c.text_disabled}; border-color: {c.border_control}; }}
QPushButton#reject {{ background: {c.danger_bg}; color: {c.danger_text}; border: 1px solid {c.danger_border}; font-weight: 700; }}
QPushButton#reject:hover {{ border-color: {c.danger_text}; }}
QPushButton#seg {{ background: {c.surface_raised}; color: {c.text_muted}; border: 1px solid {c.border_control}; border-radius: 0px; padding: 5px 12px; }}
QPushButton#seg[active="true"] {{ background: {c.accent}; color: {c.accent_on}; border-color: {c.accent}; font-weight: 800; }}
QPushButton#nav {{ background: {c.surface_raised}; color: {c.text}; border: 1px solid {c.border_control}; font-weight: 700; padding: 5px 12px; }}
QPushButton#nav:disabled {{ color: {c.text_disabled}; border-color: {c.border_card}; }}
QPushButton#live {{ background: {c.live_on_bg}; color: {c.live_on_text}; border: 1px solid {c.live_on_border}; border-radius: 12px; padding: 3px 12px; font-weight: 800; }}
QPushButton#live[on="false"] {{ background: {c.danger_bg}; color: {c.danger_text}; border: 1px solid {c.danger_border}; }}
QPushButton#ghost {{ background: transparent; border: 1px solid {c.border_control}; color: {c.text}; }}
QPushButton#primary {{ background: {c.accent}; color: {c.accent_on}; border: 1px solid {c.accent}; font-weight: 800; padding: 5px 12px; }}
QPushButton#primary:hover {{ background: {c.accent_hover}; }}
QPushButton#subtle {{ background: {c.surface_alt}; color: {c.text}; border: 1px solid {c.border_control}; }}
QPushButton#subtle:disabled {{ color: {c.text_disabled}; border-color: {c.border_card}; }}
QPushButton#danger {{ background: transparent; color: {c.danger_quiet}; border: 1px solid {c.danger_quiet_border}; font-weight: 600; }}
QPushButton#danger:disabled {{ color: {c.text_disabled}; border-color: {c.border_card}; }}
QPushButton#small {{ padding: 3px 10px; font-size: {px(t.caption)}; }}
QPushButton#disclosure {{ background: transparent; border: none; color: {c.text_muted}; text-align: left; padding: 6px 2px; font-weight: 700; }}
QPushButton#disclosure:hover {{ color: {c.text_strong}; }}
QPushButton#disclosure:checked {{ color: {c.text_strong}; }}

QTabWidget::pane {{ border: none; }}
QTabBar::tab {{ background: {c.surface_raised}; color: {c.text_muted}; padding: 6px 16px; margin-right: 3px; border-top-left-radius: 8px; border-top-right-radius: 8px; font-size: {px(t.body)}; }}
QTabBar::tab:last {{ margin-left: 28px; }}
QTabBar::tab:hover:!selected {{ color: {c.text_strong}; background: {c.selected_bg}; }}
QTabBar::tab:selected {{ background: {c.accent}; color: {c.accent_on}; font-weight: 800; }}

QListWidget#mediaGrid {{ background: {c.surface_input}; border: 1px solid {c.border_control}; border-radius: 10px; }}
QListWidget#mediaGrid::item {{ color: {c.text}; border: 2px solid transparent; border-radius: 8px; padding: 4px; }}
QListWidget#mediaGrid::item:hover {{ background: {c.surface_alt}; border-color: {c.border_control}; }}
QListWidget#mediaGrid::item:selected {{ background: {c.accent_soft}; color: {c.accent}; border: 2px solid {c.accent}; }}
QListWidget#queueList {{ font-size: {px(t.emphasis)}; }}

QLineEdit, QComboBox {{ background: {c.surface_input}; color: {c.text}; border: 1px solid {c.border_control}; border-radius: 7px; padding: 5px 8px; font-size: {px(t.body)}; }}
QLineEdit:focus, QComboBox:focus {{ border-color: {c.accent}; }}
QComboBox QAbstractItemView {{ background: {c.surface_input}; color: {c.text}; selection-background-color: {c.accent}; selection-color: {c.accent_on}; }}
QListWidget {{ background: {c.surface_input}; color: {c.text}; border: 1px solid {c.border_control}; border-radius: 8px; font-size: {px(t.body)}; }}
QListWidget::item:selected {{ background: {c.accent}; color: {c.accent_on}; }}
QDoubleSpinBox {{ background: {c.surface_input}; color: {c.text}; border: 1px solid {c.border_control}; border-radius: 8px; padding: 4px; font-size: {px(t.body)}; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QFrame#statusbar {{ background: {c.surface_input}; border-top: 1px solid {c.border}; }}
"""
