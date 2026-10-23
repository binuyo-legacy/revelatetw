"""Settings tab (blueprint): General, Output, Audio, Transcription, Detection, About.

The page edits one AppSettings object in place and emits changed(key) on every edit.
The operator window decides what to apply (see OperatorWindow._apply_settings) and saves the JSON.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout,
                             QLabel, QLineEdit, QListWidget, QMessageBox, QPushButton, QSlider, QStackedWidget,
                             QVBoxLayout, QWidget)

from .store import APP_VERSION, AppSettings

SECTIONS = ["General", "Output", "Audio", "Transcription", "Detection", "About"]
MODEL_SIZES = ["small", "medium", "large"]
WHISPER_LANGS = [("en", "English"), ("fr", "French"), ("yo", "Yoruba"), ("ha", "Hausa"), ("sw", "Swahili")]
RESOLUTIONS = ["auto", "1920x1080", "1280x720", "3840x2160"]
WARN_STYLE = "color:#f59e0b;font-size:11px;"


def _note(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setWordWrap(True)
    lab.setObjectName("liveNote")
    return lab


class SettingsPage(QWidget):
    changed = pyqtSignal(str)   # settings key that changed

    def __init__(self, settings: AppSettings, check_updates_cb=None, parent=None):
        super().__init__(parent)
        self.s = settings
        self._check_updates_cb = check_updates_cb or (lambda: "Updates are not set up in this build yet. You are on " + APP_VERSION + ".")
        self._loading = True
        root = QHBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 10)
        self.nav = QListWidget()
        self.nav.setFixedWidth(160)
        self.stack = QStackedWidget()
        for name, page in [("General", self._general()), ("Output", self._output()),
                           ("Audio", self._audio()), ("Transcription", self._transcription()),
                           ("Detection", self._detection()), ("About", self._about())]:
            self.nav.addItem(name)
            self.stack.addWidget(page)
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.setCurrentRow(0)
        root.addWidget(self.nav)
        root.addWidget(self.stack, 1)
        self._loading = False

    def select_section(self, name: str) -> None:
        if name in SECTIONS:
            self.nav.setCurrentRow(SECTIONS.index(name))

    def _emit(self, key: str) -> None:
        if not self._loading:
            self.changed.emit(key)

    # --- helpers --------------------------------------------------------------------------
    def _check(self, label: str, key: str, value: bool, tip: str = "") -> QCheckBox:
        cb = QCheckBox(label)
        cb.setChecked(value)
        if tip:
            cb.setToolTip(tip)
        cb.toggled.connect(lambda v, k=key: self._set(k, bool(v)))
        return cb

    def _set(self, key: str, value) -> None:
        setattr(self.s, key, value)
        self.s.clean()
        self._emit(key)

    def _page(self) -> tuple[QWidget, QFormLayout]:
        w = QWidget()
        lay = QFormLayout(w)
        lay.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        return w, lay

    # --- General ----------------------------------------------------------------------------
    def _general(self) -> QWidget:
        w, lay = self._page()
        lay.addRow(self._check("Start with live output ON", "startup_live_on", self.s.startup_live_on,
                               "When the app opens, the projection window is shown."))
        lay.addRow(self._check("Check for updates on startup", "check_updates", self.s.check_updates))
        self.language = QComboBox()
        self.language.addItem("English", "en")
        self.language.setToolTip("Interface language. English only in this build.")
        lay.addRow("Language", self.language)
        return w

    # --- Output -----------------------------------------------------------------------------
    def _output(self) -> QWidget:
        w, lay = self._page()
        self.display_combo = QComboBox()
        self.display_combo.setToolTip("Monitor for the live output (same list as the toolbar)")
        self.display_combo.currentIndexChanged.connect(self._on_display_combo)
        lay.addRow("Output display", self.display_combo)
        self.resolution = QComboBox()
        self.resolution.addItems(RESOLUTIONS)
        self.resolution.setCurrentText(self.s.default_resolution if self.s.default_resolution in RESOLUTIONS else "auto")
        self.resolution.setToolTip("The output window fills the chosen display. A fixed size is saved for later; "
                                   "it does not change the monitor mode yet.")
        self.resolution.currentTextChanged.connect(lambda t: self._set("default_resolution", t))
        lay.addRow("Default resolution", self.resolution)
        lay.addRow(self._check("Borderless fullscreen", "borderless_fullscreen", self.s.borderless_fullscreen,
                               "Off = a normal window on the chosen display."))
        vc = self._check("Virtual camera output", "virtual_camera", self.s.virtual_camera,
                         "Saved for when the virtual camera driver lands. Today, use OBS window capture.")
        lay.addRow(vc)
        lay.addRow(_note("Virtual camera: the setting is saved, but no virtual camera driver is built yet. "
                         "For now, capture the output window in OBS."))
        self.media_folder_edit = QLineEdit(self.s.media_folder or "")
        self.media_folder_edit.setPlaceholderText("data/media (default)")
        self.media_folder_edit.setToolTip("Folder the Media tab scans for images and videos")
        self.media_folder_edit.editingFinished.connect(
            lambda: self._set("media_folder", self.media_folder_edit.text().strip()))
        browse = QPushButton("Browse...")
        browse.clicked.connect(self._pick_media_folder)
        row = QHBoxLayout()
        row.addWidget(self.media_folder_edit, 1)
        row.addWidget(browse)
        box = QWidget()
        box.setLayout(row)
        lay.addRow("Media folder", box)
        return w

    def _pick_media_folder(self) -> None:
        start = self.s.media_folder or ""
        folder = QFileDialog.getExistingDirectory(self, "Choose the media folder", start)
        if folder:
            self.media_folder_edit.setText(folder)
            self._set("media_folder", folder)

    def set_displays(self, labels: list[str], current: int) -> None:
        self._loading = True
        self.display_combo.clear()
        self.display_combo.addItems(labels or ["No display found"])
        self.display_combo.setCurrentIndex(min(max(current, 0), max(len(labels) - 1, 0)))
        self._loading = False

    def _on_display_combo(self, idx: int) -> None:
        if idx >= 0 and not self._loading:
            self.s.output_display = idx
            self._emit("output_display")

    # --- Audio ------------------------------------------------------------------------------
    def _audio(self) -> QWidget:
        w, lay = self._page()
        self.input_combo = QComboBox()
        self.input_combo.setToolTip("Audio input. Same list as the toolbar picker.")
        self.input_combo.currentIndexChanged.connect(self._on_input_combo)
        lay.addRow("Input device", self.input_combo)
        lay.addRow(self._check("WASAPI loopback (mixing desk output)", "wasapi_loopback", self.s.wasapi_loopback,
                               "Lists sound desk outputs as inputs. Windows only."))
        self.gate_slider = QSlider(Qt.Orientation.Horizontal)
        self.gate_slider.setRange(-80, -10)
        self.gate_slider.setValue(int(self.s.noise_gate_db))
        self.gate_label = QLabel()
        self.gate_slider.valueChanged.connect(self._on_gate)
        row = QHBoxLayout()
        row.addWidget(self.gate_slider, 1)
        row.addWidget(self.gate_label)
        lay.addRow("Noise gate", row)
        self._on_gate(self.gate_slider.value(), emit=False)
        return w

    def set_input_devices(self, names: list[str]) -> None:
        self._loading = True
        self.input_combo.clear()
        self.input_combo.addItems(names or ["No input device found"])
        if self.s.input_device_name in names:
            self.input_combo.setCurrentIndex(names.index(self.s.input_device_name))
        self._loading = False

    def _on_input_combo(self, idx: int) -> None:
        if self._loading or idx < 0:
            return
        name = self.input_combo.itemText(idx)
        if name and not name.startswith("No input"):
            self._set("input_device_name", name)

    def _on_gate(self, value: int, emit: bool = True) -> None:
        self.gate_label.setText(f"{value} dB")
        if emit:
            self._set("noise_gate_db", float(value))

    # --- Transcription ----------------------------------------------------------------------
    def _transcription(self) -> QWidget:
        w, lay = self._page()
        self.model_combo = QComboBox()
        self.model_combo.addItems(MODEL_SIZES)
        self.model_combo.setCurrentText(self.s.model_size)
        self.model_combo.setToolTip("Bigger models are more accurate and slower. Loads on the first mic start.")
        self.model_combo.currentTextChanged.connect(lambda t: self._set("model_size", t))
        lay.addRow("Model size", self.model_combo)
        self.lang_combo = QComboBox()
        for code, label in WHISPER_LANGS:
            self.lang_combo.addItem(label, code)
        idx = max(0, self.lang_combo.findData(self.s.whisper_language))
        self.lang_combo.setCurrentIndex(idx)
        self.lang_combo.currentIndexChanged.connect(
            lambda i: self._set("whisper_language", self.lang_combo.itemData(i)))
        lay.addRow("Spoken language", self.lang_combo)
        self.det_slider = QSlider(Qt.Orientation.Horizontal)
        self.det_slider.setRange(0, 100)
        self.det_slider.setValue(self.s.detection_threshold)
        self.det_label = QLabel()
        self.det_slider.valueChanged.connect(lambda v: self._on_threshold(v, "detection_threshold"))
        row = QHBoxLayout()
        row.addWidget(self.det_slider, 1)
        row.addWidget(self.det_label)
        lay.addRow("Detection threshold", row)
        self._update_label(self.det_label, self.det_slider.value())
        lay.addRow(_note("Detection threshold and the paraphrase threshold on the Detection tab are the same setting."))
        return w

    def _update_label(self, label: QLabel, v: int) -> None:
        label.setText(str(v))

    def _on_threshold(self, value: int, origin: str) -> None:
        """Keep the Transcription and Detection sliders as one value (paraphrase threshold)."""
        self._update_label(self.det_label, value)
        if hasattr(self, "para_slider") and self.para_slider.value() != value:
            self._loading = True
            self.para_slider.setValue(value)
            self._update_label(self.para_label, value)
            self._loading = False
        if self._loading:
            return
        self.s.detection_threshold = value
        self.s.paraphrase_threshold = value
        self.s.clean()
        self._emit("paraphrase_threshold")

    # --- Detection --------------------------------------------------------------------------
    def _detection(self) -> QWidget:
        w, lay = self._page()
        self.para_slider = QSlider(Qt.Orientation.Horizontal)
        self.para_slider.setRange(0, 100)
        self.para_slider.setValue(self.s.paraphrase_threshold)
        self.para_label = QLabel()
        self.para_slider.valueChanged.connect(lambda v: self._on_threshold(v, "paraphrase_threshold"))
        row = QHBoxLayout()
        row.addWidget(self.para_slider, 1)
        row.addWidget(self.para_label)
        lay.addRow("Paraphrase threshold", row)
        self._update_label(self.para_label, self.para_slider.value())
        lay.addRow(_note("Lower finds more paraphrases (and more false hits). Same as --paraphrase-threshold."))
        self.dedupe = QDoubleSpinBox()
        self.dedupe.setRange(0, 60)
        self.dedupe.setSingleStep(0.5)
        self.dedupe.setSuffix(" min")
        self.dedupe.setValue(self.s.dedupe_minutes)
        self.dedupe.setToolTip("A verse that was already queued in this window is not queued again.")
        self.dedupe.valueChanged.connect(lambda v: self._set("dedupe_minutes", float(v)))
        lay.addRow("Dedupe window", self.dedupe)
        self.auto = QCheckBox("Auto-approve detected verses (OFF by default)")
        self.auto.setChecked(self.s.auto_approve)
        self.auto.toggled.connect(self._on_auto_toggle)
        lay.addRow(self.auto)
        warn = _note("WARNING: when on, detected verses go to the screen without an operator approving them. "
                     "This bypasses the operator approval rule. Leave it off unless you accept that.")
        warn.setStyleSheet(WARN_STYLE)
        lay.addRow(warn)
        return w

    def _on_auto_toggle(self, on: bool) -> None:
        if self._loading:
            return
        if on:
            ans = QMessageBox.question(
                self, "Auto-approve",
                "Turn on auto-approve? Detected verses will be projected without operator approval, "
                "which bypasses the approval rule.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if ans != QMessageBox.StandardButton.Yes:
                self.auto.blockSignals(True)
                self.auto.setChecked(False)
                self.auto.blockSignals(False)
                return
        self._set("auto_approve", bool(on))

    # --- About ------------------------------------------------------------------------------
    def _about(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel(f"RevelateTW version {APP_VERSION}"))
        lay.addWidget(_note("Verse detection and live output for church services."))
        btn = QPushButton("Check for updates")
        self.update_msg = _note("")
        btn.clicked.connect(lambda: self.update_msg.setText(self._check_updates_cb()))
        lay.addWidget(btn)
        lay.addWidget(self.update_msg)
        lay.addStretch(1)
        return w
