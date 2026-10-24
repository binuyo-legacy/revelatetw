"""Settings tab (blueprint): General, Output, Audio, Transcription, Detection, About.

The page edits one AppSettings object in place and emits changed(key) on every edit.
The operator window decides what to apply (see OperatorWindow._apply_settings) and saves the JSON.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout,
                             QLabel, QLineEdit, QListWidget, QMessageBox, QPushButton, QSlider, QStackedWidget,
                             QVBoxLayout, QWidget, QSpinBox)

from . import fftools
from .store import APP_VERSION, AppSettings

SECTIONS = ["General", "Output", "Audio", "Transcription", "Detection", "Bible", "About"]
MODEL_SIZES = ["tiny", "base", "small", "medium", "large", "large-v3"]
WHISPER_LANGS = [("en", "English"), ("fr", "French"), ("yo", "Yoruba"), ("ha", "Hausa"), ("sw", "Swahili")]
RESOLUTIONS = ["auto", "1920x1080", "1280x720", "3840x2160"]
WARN_STYLE = "color:#f59e0b;font-size:11px;"


def _note(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setWordWrap(True)
    lab.setObjectName("liveNote")
    return lab


class _NoUpdater:
    kind = "error"
    url = ""
    message = "Updates are not set up in this build yet. You are on " + APP_VERSION + "."


class SettingsPage(QWidget):
    changed = pyqtSignal(str)   # settings key that changed
    _update_result = pyqtSignal(object)
    _update_btn_enable = pyqtSignal(bool)

    def __init__(self, settings: AppSettings, check_updates_cb=None, parent=None):
        super().__init__(parent)
        self.s = settings
        self._check_updates_cb = check_updates_cb or (lambda done: done(_NoUpdater()))
        self._loading = True
        root = QHBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 10)
        self.nav = QListWidget()
        self.nav.setFixedWidth(160)
        self.stack = QStackedWidget()
        for name, page in [("General", self._general()), ("Output", self._output()),
                           ("Audio", self._audio()), ("Transcription", self._transcription()),
                           ("Detection", self._detection()), ("Bible", self._bible()),
                           ("About", self._about())]:
            self.nav.addItem(name)
            self.stack.addWidget(page)
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.setCurrentRow(0)
        root.addWidget(self.nav)
        root.addWidget(self.stack, 1)
        self._loading = False
        self.refresh_bible_list()

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
        self.ffmpeg_dir_edit = QLineEdit(self.s.ffmpeg_dir or "")
        self.ffmpeg_dir_edit.setPlaceholderText("(optional) folder with ffmpeg.exe and ffprobe.exe")
        self.ffmpeg_dir_edit.setToolTip("Only needed if ffmpeg is not bundled with the app and not on PATH. "
                                        "Leave empty for the default lookup.")
        self.ffmpeg_dir_edit.editingFinished.connect(
            lambda: self._set_ffmpeg_dir(self.ffmpeg_dir_edit.text().strip()))
        ff_browse = QPushButton("Browse...")
        ff_browse.clicked.connect(self._pick_ffmpeg_dir)
        ff_row = QHBoxLayout()
        ff_row.addWidget(self.ffmpeg_dir_edit, 1)
        ff_row.addWidget(ff_browse)
        ff_box = QWidget()
        ff_box.setLayout(ff_row)
        lay.addRow("ffmpeg folder", ff_box)
        self.ffmpeg_status = QLabel(fftools.status_text())
        self.ffmpeg_status.setWordWrap(True)
        self.ffmpeg_status.setObjectName("ffmpegStatus")
        lay.addRow("ffmpeg", self.ffmpeg_status)
        return w

    def _pick_ffmpeg_dir(self) -> None:
        start = self.s.ffmpeg_dir or ""
        folder = QFileDialog.getExistingDirectory(self, "Choose the folder with ffmpeg.exe and ffprobe.exe", start)
        if folder:
            self.ffmpeg_dir_edit.setText(folder)
            self._set_ffmpeg_dir(folder)

    def _set_ffmpeg_dir(self, folder: str) -> None:
        self._set("ffmpeg_dir", folder)
        self.refresh_ffmpeg_status()

    def refresh_ffmpeg_status(self) -> None:
        """Re-run the lookup (after the folder changes) and show the one-line source."""
        fftools.set_configured_dir(self.s.ffmpeg_dir)
        self.ffmpeg_status.setText(fftools.status_text())

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
        self.model_combo.currentIndexChanged.connect(self._on_model_pick)
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
        # Performance: whisper only loads on the first mic start and is freed when live detection
        # stops. int8 is the default (smallest, fastest on CPU). Threads 0 = automatic.
        lay.addRow(_note("Performance: whisper loads on the first mic start and is freed when live detection stops."))
        self.compute_combo = QComboBox()
        self.compute_combo.addItems(["int8", "int8_float32", "float32"])
        self.compute_combo.setCurrentText(self.s.compute_type)
        self.compute_combo.setToolTip("int8 is the default and the lightest on CPU. float32 is heavier and "
                                      "not faster on most church PCs.")
        self.compute_combo.currentTextChanged.connect(lambda t: self._set("compute_type", t))
        lay.addRow("Compute type", self.compute_combo)
        self.threads_spin = QSpinBox()
        self.threads_spin.setRange(0, 64)
        self.threads_spin.setSpecialValueText("Automatic")
        self.threads_spin.setValue(int(self.s.cpu_threads or 0))
        self.threads_spin.setToolTip("CPU threads for whisper. 0 = automatic. Lower it to leave CPU for the "
                                     "projection and other apps.")
        self.threads_spin.valueChanged.connect(lambda v: self._set("cpu_threads", int(v)))
        lay.addRow("CPU threads", self.threads_spin)
        return w

    def _on_model_pick(self, idx: int) -> None:
        """Large models ask first (Cancel keeps the previous model). The choice is persisted."""
        if getattr(self, "_loading", False):
            return
        from .model_advice import LARGE_MODEL_WARNING, needs_large_model_warning
        chosen = self.model_combo.itemText(idx)
        previous = self.s.model_size
        if needs_large_model_warning(previous, chosen):
            ans = QMessageBox.warning(self, "Large model", LARGE_MODEL_WARNING,
                                      QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
                                      QMessageBox.StandardButton.Cancel)
            if ans != QMessageBox.StandardButton.Ok:
                self.model_combo.blockSignals(True)
                self.model_combo.setCurrentText(previous)
                self.model_combo.blockSignals(False)
                return
        self._set("model_size", chosen)

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
    # --- Bible ------------------------------------------------------------------------------
    def _bible(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("Bible"))
        lay.addWidget(_note("Verse text for detection and projection. Only public-domain texts ship with the app; "
                            "any other translation is one you import with your own licence."))
        head = QLabel("BUNDLED TRANSLATIONS")
        head.setObjectName("footer")
        lay.addWidget(head)
        self.bible_bundled = QVBoxLayout()
        lay.addLayout(self.bible_bundled)
        head2 = QLabel("YOUR IMPORTS")
        head2.setObjectName("footer")
        lay.addWidget(head2)
        self.bible_imports = QVBoxLayout()
        lay.addLayout(self.bible_imports)
        self.bible_msg = _note("")
        lay.addWidget(self.bible_msg)
        btn_import = QPushButton("Import translation")
        btn_import.setObjectName("primary")
        btn_import.setToolTip("Import a USFM, OSIS or XML file of a translation you are licensed to use.")
        btn_import.clicked.connect(self._open_import_dialog)
        lay.addWidget(btn_import)
        lay.addWidget(_note("Add translation: import a licensed USFM, OSIS or XML file. Imported texts stay on this "
                            "computer and appear in the Verses tab dropdown."))
        lay.addWidget(self._check("Check for updates on startup", "check_updates_on_startup",
                                  self.s.check_updates_on_startup,
                                  "Sends one request to GitHub at startup. Off means the app makes no update requests."))
        lay.addStretch(1)
        self.refresh_bible_list()
        return w

    def _row(self, layout: QVBoxLayout, title: str, detail: str, remove_id: str | None = None) -> None:
        row = QHBoxLayout()
        text = QLabel(f"<b>{title}</b><br><span style='color:#9ca3af;'>{detail}</span>")
        text.setTextFormat(Qt.TextFormat.RichText)
        text.setWordWrap(True)
        row.addWidget(text, 1)
        if remove_id:
            btn = QPushButton("Remove")
            btn.setToolTip(f"Delete the imported translation {remove_id} from this computer.")
            btn.clicked.connect(lambda _=False, t=remove_id: self._remove_translation(t))
            row.addWidget(btn)
        box = QWidget()
        box.setLayout(row)
        layout.addWidget(box)

    def _clear(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._clear(item.layout())

    def refresh_bible_list(self) -> None:
        from .bible import BibleLibrary
        self._clear(self.bible_bundled)
        self._clear(self.bible_imports)
        lib = BibleLibrary()
        n_user = 0
        for t in lib.installed():
            if t.user_imported:
                n_user += 1
                self._row(self.bible_imports, t.label, self._detail(t), remove_id=t.id)
            elif t.bundled:
                self._row(self.bible_bundled, t.label, self._detail(t))
        if n_user == 0:
            self.bible_imports.addWidget(_note("No imported translations yet."))

    def _detail(self, t) -> str:
        from .bible import verse_count
        count = verse_count(t.path)
        count_txt = f"{count:,} verses" if count else "verses not counted"
        label = "Public domain" if t.license.lower().startswith("public domain") else t.license
        return f"{count_txt} \u00b7 {label}"

    def _open_import_dialog(self) -> None:
        from .import_dialog import ImportTranslationDialog
        dlg = ImportTranslationDialog(self, folder=None)
        if dlg.exec() == dlg.DialogCode.Accepted:
            self.refresh_bible_list()
            self.bible_msg.setText(dlg.result_message)
            self.changed.emit("bible_translation")

    def _remove_translation(self, tid: str) -> None:
        from .bible import remove_user_translation
        ans = QMessageBox.question(self, "Remove translation",
                                   f"Remove {tid} from this computer? You can import the file again later.",
                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                   QMessageBox.StandardButton.No)
        if ans != QMessageBox.StandardButton.Yes:
            return
        if remove_user_translation(tid):
            self.refresh_bible_list()
            self.bible_msg.setText(f"Removed {tid}.")
            self.changed.emit("bible_translation")
        else:
            self.bible_msg.setText(f"{tid} was kept: only your own imports can be removed.")

    def _start_update_check(self, btn) -> None:
        self.update_msg.setText("Checking for updates...")
        btn.setEnabled(False)

        def done(result):
            # runs on the worker thread; hop to the GUI thread via queued signals
            self._update_result.emit(result)
            self._update_btn_enable.emit(True)
        self._check_updates_cb(done)

    def _on_update_result(self, result) -> None:
        msg = result.message
        if result.kind == "update":
            msg += " Opening the release page..."
            import webbrowser
            try:
                webbrowser.open(result.url)
            except Exception:
                msg += f" If it did not open, go to {result.url}"
        self.update_msg.setText(msg)

    def _about(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel(f"RevelateTW version {APP_VERSION}"))
        lay.addWidget(_note("Verse detection and live output for church services."))
        lay.addWidget(_note("Bible credits: KJV, ASV and WEB are public domain. Yoruba Contemporary \u00a9 Biblica, CC BY-SA 4.0 "
                            "(attribution and license notes in data/bible/LICENSES.md)."))
        btn = QPushButton("Check for updates")
        self.update_msg = _note("")
        self._update_btn = btn
        self._update_result.connect(self._on_update_result)
        self._update_btn_enable.connect(btn.setEnabled)
        btn.clicked.connect(lambda: self._start_update_check(btn))
        lay.addWidget(btn)
        lay.addWidget(self.update_msg)
        lay.addStretch(1)
        return w
