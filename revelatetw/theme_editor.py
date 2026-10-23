"""Theme editor screen (spec F3): edit frames, backgrounds, colours, typography and transitions.

Opens from the operator window. Saves and loads theme JSON in the same format as theme.py
(Theme.save / Theme.load), so themes made here work on any machine and the six ready-made
themes can be loaded, tweaked and saved as new files.

Importing PyQt6 is needed only to open the editor. The model logic (apply_edits, presets)
lives in theme.py and is tested headless.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDialog, QDoubleSpinBox,
                             QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                             QListWidget, QMessageBox, QPushButton, QSpinBox, QVBoxLayout,
                             QWidget)

from .theme import (BACKGROUND_KINDS, FRAMES, LAYOUTS, TRANSITIONS, Background, Theme,
                    is_hex_color, ready_made_themes)


class ColorButton(QPushButton):
    def __init__(self, value: str):
        super().__init__()
        self.set_color(value)
        self.clicked.connect(self._pick)

    def set_color(self, value: str) -> None:
        self._value = value
        self.setText(value)
        self.setStyleSheet(f"background:{value[:7]};color:{'#000' if _light(value) else '#fff'};")

    def color(self) -> str:
        return self._value

    def _pick(self) -> None:
        c = QColorDialog.getColor(QColor(self._value[:7]), self, "Pick colour")
        if c.isValid():
            self.set_color(c.name())


def _light(hex_value: str) -> bool:
    r, g, b = (int(hex_value[i:i + 2], 16) for i in (1, 3, 5))
    return (0.299 * r + 0.587 * g + 0.114 * b) > 150


class ThemeEditor(QDialog):
    """Modal editor. Call exec(); on accept, self.theme holds the edited theme."""

    def __init__(self, theme: Theme | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("RevelateTW theme editor")
        self.theme = theme or Theme()
        self.path: str | None = None

        root = QHBoxLayout(self)
        self.library = QListWidget()
        self.library.addItems([t.name for t in ready_made_themes()])
        self.library.currentRowChanged.connect(self._load_preset)
        root.addWidget(self.library, 1)

        form_host = QWidget()
        form = QFormLayout(form_host)
        self.name = QLineEdit()
        self.bg_kind = QComboBox(); self.bg_kind.addItems(BACKGROUND_KINDS)
        self.bg_color1 = ColorButton("#0F0B2E")
        self.bg_color2 = ColorButton("#4C1D95")
        self.bg_image = QLineEdit(); self.bg_image.setPlaceholderText("image path (kind = image)")
        self.bg_video = QLineEdit(); self.bg_video.setPlaceholderText("video path (kind = video)")
        self.text_color = ColorButton("#F5F3FF")
        self.ref_color = ColorButton("#D4A017")
        self.font_family = QLineEdit()
        self.font_size = QSpinBox(); self.font_size.setRange(12, 300)
        self.font_weight = QSpinBox(); self.font_weight.setRange(100, 900); self.font_weight.setSingleStep(100)
        self.line_height = QDoubleSpinBox(); self.line_height.setRange(0.8, 3.0); self.line_height.setSingleStep(0.05)
        self.shadow = QCheckBox("text shadow")
        self.outline = QSpinBox(); self.outline.setRange(0, 12)
        self.frame = QComboBox(); self.frame.addItems(FRAMES)
        self.frame_inset = QSpinBox(); self.frame_inset.setRange(0, 400)
        self.layout_box = QComboBox(); self.layout_box.addItems(LAYOUTS)
        self.transition = QComboBox(); self.transition.addItems(TRANSITIONS)
        self.transition_ms = QSpinBox(); self.transition_ms.setRange(0, 5000); self.transition_ms.setSuffix(" ms")
        self.warning = QLabel(""); self.warning.setWordWrap(True)

        form.addRow("Name", self.name)
        form.addRow("Background", self.bg_kind)
        form.addRow("Colour 1 / top", self.bg_color1)
        form.addRow("Colour 2 / bottom", self.bg_color2)
        form.addRow("Image file", self.bg_image)
        form.addRow("Video file", self.bg_video)
        form.addRow("Text colour", self.text_color)
        form.addRow("Reference colour", self.ref_color)
        form.addRow("Font", self.font_family)
        form.addRow("Font size", self.font_size)
        form.addRow("Font weight", self.font_weight)
        form.addRow("Line height", self.line_height)
        form.addRow("", self.shadow)
        form.addRow("Outline", self.outline)
        form.addRow("Frame", self.frame)
        form.addRow("Frame inset", self.frame_inset)
        form.addRow("Layout", self.layout_box)
        form.addRow("Transition", self.transition)
        form.addRow("Transition time", self.transition_ms)
        form.addRow("", self.warning)
        root.addWidget(form_host, 3)

        bar = QVBoxLayout()
        for text, fn in [("Open theme file...", self._open), ("Save theme file...", self._save),
                         ("Apply to output", self.accept), ("Cancel", self.reject)]:
            b = QPushButton(text); b.clicked.connect(fn); bar.addWidget(b)
        bar.addStretch(1)
        root.addLayout(bar, 1)

        self._fill(self.theme)

    # ---- model <-> widgets -----------------------------------------------------------
    def _fill(self, t: Theme) -> None:
        self.name.setText(t.name)
        self.bg_kind.setCurrentText(t.background.kind)
        cols = t.background.colors + ["#000000"]
        self.bg_color1.set_color(cols[0])
        self.bg_color2.set_color(cols[1] if len(t.background.colors) > 1 else cols[0])
        self.bg_image.setText(t.background.image_path or "")
        self.bg_video.setText(t.background.video_path or "")
        self.text_color.set_color(t.text_color)
        self.ref_color.set_color(t.reference_color)
        self.font_family.setText(t.font_family)
        self.font_size.setValue(t.font_size_px)
        self.font_weight.setValue(t.font_weight)
        self.line_height.setValue(t.line_height)
        self.shadow.setChecked(t.shadow)
        self.outline.setValue(t.outline_px)
        self.frame.setCurrentText(t.frame)
        self.frame_inset.setValue(t.frame_inset_px)
        self.layout_box.setCurrentText(t.layout)
        self.transition.setCurrentText(t.transition)
        self.transition_ms.setValue(t.transition_ms)
        self._check()

    def read(self) -> Theme:
        """Build a Theme from the widgets. Solid and image/video use colour 1 only."""
        kind = self.bg_kind.currentText()
        colors = [self.bg_color1.color()]
        if kind in ("linear", "radial"):
            colors.append(self.bg_color2.color())
        bg = Background(kind=kind, colors=colors,
                        image_path=self.bg_image.text() or None,
                        video_path=self.bg_video.text() or None)
        return Theme(name=self.name.text().strip() or "Untitled", background=bg,
                     text_color=self.text_color.color(), reference_color=self.ref_color.color(),
                     font_family=self.font_family.text() or "Georgia",
                     font_size_px=self.font_size.value(), font_weight=self.font_weight.value(),
                     line_height=self.line_height.value(), shadow=self.shadow.isChecked(),
                     outline_px=self.outline.value(), frame=self.frame.currentText(),
                     frame_inset_px=self.frame_inset.value(), layout=self.layout_box.currentText(),
                     transition=self.transition.currentText(), transition_ms=self.transition_ms.value(),
                     translation_accents=dict(self.theme.translation_accents))

    def _check(self) -> None:
        errs = self.read().problems()
        self.warning.setText("" if not errs else "Fix before applying: " + "; ".join(errs))
        self.warning.setStyleSheet("color:#DC2626;" if errs else "")

    def _load_preset(self, row: int) -> None:
        if row >= 0:
            self._fill(ready_made_themes()[row])

    # ---- files -----------------------------------------------------------------------
    def _open(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open theme", "", "Theme JSON (*.json)")
        if not path:
            return
        try:
            t = Theme.load(path)
        except (ValueError, KeyError, TypeError) as exc:
            QMessageBox.warning(self, "Theme not loaded", str(exc))
            return
        self.path = path
        self._fill(t)

    def _save(self) -> None:
        t = self.read()
        errs = t.problems()
        if errs:
            QMessageBox.warning(self, "Theme not saved", "; ".join(errs))
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save theme", f"{t.name}.json", "Theme JSON (*.json)")
        if path:
            t.save(path)
            self.path = path

    def accept(self) -> None:  # noqa: D401 - Qt override
        errs = self.read().problems()
        if errs:
            QMessageBox.warning(self, "Theme not applied", "; ".join(errs))
            return
        self.theme = self.read()
        super().accept()
