"""RevelateTW Lite operator window (PyQt5). Same palette/type/spacing as the main app."""
import os
import sys

from PyQt5 import QtCore, QtGui, QtWidgets

from revelatetw.ui_tokens import COLORS as C, TYPE as T, SPACE as S

from . import __version__, background as bgm, paths, settings as cfg, songthemes, tabanimate, theme, transitions as trn, versethemes
from .bible import BibleStore, format_reference, parse_reference, book_name, find_book, SEGMENTS, suggest, reference_spans, adjust_reference, check_reference, partial_problem, _is_bare_ordinal, _has_chapter_number
from .hintfade import HintFade
from .refedit import RefEdit
from .projection import PreviewView, ProjectionWindow, SlideView
from .servicelist import ServiceList
from .songs import Song, SongLibrary, split_lyrics, lyrics_text, import_rtsong, import_song_json, export_songs, safe_filename

QSS = theme.build_qss()


SEARCH_DELAY_MS = 200   # typing pause before live word search runs
SEARCH_MIN_CHARS = 2


class Main(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RevelateTW Lite")
        self.bible = BibleStore()
        self.settings_path = os.path.join(paths.user_dir(), "settings.json")
        self.list_path = os.path.join(paths.user_dir(), "service.json")
        self.st = cfg.load(self.settings_path)
        self.services = ServiceList.load(self.list_path)
        self.songs = SongLibrary(os.path.join(paths.user_dir(), "songs"))
        self.song_all = self.songs.load_all()
        self.song = None          # the song open in the Songs tab
        self.slide_meta = None    # song slide details (None for verses)
        self.slide = None         # (heading, body, credit): THE one slide the preview shows (verse or song slide)
        self.proj = ProjectionWindow()
        self.preview = PreviewView()
        self.cur = None   # (book, chapter, v1, v2, translation)
        self._build()
        self._apply_style()
        self.lookup(self.st["last_reference"], quiet=True)

    # ---------------- layout ----------------
    def _build(self):
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(S.xl, S.xl, S.xl, S.xl)
        lay.setSpacing(S.gap)
        head = QtWidgets.QHBoxLayout()
        logo = QtWidgets.QLabel()
        pm = QtGui.QPixmap(paths.logo_path())
        if not pm.isNull():
            logo.setPixmap(pm.scaledToHeight(40, QtCore.Qt.SmoothTransformation))
        else:
            logo.setText("RevelateTW")
        head.addWidget(logo)
        lite = QtWidgets.QLabel("LITE")
        lite.setObjectName("ref")
        head.addWidget(lite)
        head.addStretch(1)
        self.live_badge = QtWidgets.QLabel("")
        head.addWidget(self.live_badge)
        lay.addLayout(head)

        # Two columns: LEFT = operator work area (find + library tabs), RIGHT = the one shared
        # preview with its own controls. No second copy of the verse anywhere.
        body = QtWidgets.QHBoxLayout()
        body.setSpacing(S.gap)
        lay.addLayout(body, 1)
        leftc = QtWidgets.QVBoxLayout()
        leftc.setSpacing(S.gap)
        body.addLayout(leftc, 3)

        find = QtWidgets.QFrame()
        find.setObjectName("card")
        fl = QtWidgets.QVBoxLayout(find)
        fl.setContentsMargins(S.panel_x, S.panel_y, S.panel_x, S.panel_y)
        fl.setSpacing(6)
        cap_f = QtWidgets.QLabel("Find a verse")
        cap_f.setObjectName("hint")
        fl.addWidget(cap_f)
        row = QtWidgets.QHBoxLayout()
        self.trans = QtWidgets.QComboBox()
        names = self.bible.translations()
        for t in names:
            self.trans.addItem(t, t)
        if self.st["translation"] in names:
            self.trans.setCurrentText(self.st["translation"])
        self.trans.setMinimumWidth(90)
        self.box = RefEdit(self.st["last_reference"])
        self.box.setPlaceholderText("Type a verse, e.g. John 3:16 or Rom 8:28-30")
        go = QtWidgets.QPushButton("Look up")
        self.add_bible_b = QtWidgets.QPushButton("Add Bible...")
        self.add_bible_b.setToolTip("Convert and add your own licensed Bible file (USFM, OSIS or text)")
        self.sug_model = QtCore.QStringListModel(self)
        self.completer = QtWidgets.QCompleter(self.sug_model, self)
        self.completer.setCompletionMode(QtWidgets.QCompleter.UnfilteredPopupCompletion)
        self.completer.setCaseSensitivity(QtCore.Qt.CaseInsensitive)
        self.completer.setMaxVisibleItems(8)
        self.box.setCompleter(self.completer)
        row.addWidget(self.trans)
        row.addWidget(self.box, 1)
        row.addWidget(go)
        row.addWidget(self.add_bible_b)
        fl.addLayout(row)
        # message line only (errors / hints). The verse text itself lives ONLY in the preview.
        self.verse_lbl = QtWidgets.QLabel("")
        self.verse_lbl.setObjectName("hint")
        self.verse_lbl.setWordWrap(True)
        self.verse_lbl.setTextInteractionFlags(QtCore.Qt.NoTextInteraction)
        fl.addWidget(self.verse_lbl)
        # Out-of-range hint: soft fade-in (see hintfade.py), then it clears by itself. No modal.
        self._hint_fade = HintFade(self.verse_lbl)
        self._hint_timer = QtCore.QTimer(self)
        self._hint_timer.setSingleShot(True)
        self._hint_timer.setInterval(4500)
        self._hint_timer.timeout.connect(self.clear_ref_hint)
        self._hint_on = False
        leftc.addWidget(find)

        tabs = tabanimate.AnimatedTabWidget()
        self.service_list = QtWidgets.QListWidget()
        sl = QtWidgets.QWidget()
        sv = QtWidgets.QHBoxLayout(sl)
        sv.addWidget(self.service_list, 1)
        side = QtWidgets.QVBoxLayout()
        self.up_b, self.down_b, self.rm_b = (QtWidgets.QPushButton(x) for x in ("Move up", "Move down", "Remove"))
        for b in (self.up_b, self.down_b, self.rm_b):
            side.addWidget(b)
        side.addStretch(1)
        sv.addLayout(side)
        tabs.addTab(sl, "Service list")

        sw = QtWidgets.QWidget()
        sg = QtWidgets.QVBoxLayout(sw)
        sr = QtWidgets.QHBoxLayout()
        self.search_box = QtWidgets.QLineEdit()
        self.search_box.setPlaceholderText("Search words, e.g. loved world")
        sb = QtWidgets.QPushButton("Search")
        sr.addWidget(self.search_box, 1)
        sr.addWidget(sb)
        sg.addLayout(sr)
        self.results = QtWidgets.QListWidget()
        sg.addWidget(self.results, 1)
        tabs.addTab(sw, "Search words")

        sgw = QtWidgets.QWidget()
        sgl = QtWidgets.QHBoxLayout(sgw)
        left = QtWidgets.QVBoxLayout()
        self.song_search = QtWidgets.QLineEdit()
        self.song_search.setPlaceholderText("Find a song by title or words")
        self.song_list = QtWidgets.QListWidget()
        left.addWidget(self.song_search)
        left.addWidget(self.song_list, 1)
        sgl.addLayout(left, 1)
        mid_s = QtWidgets.QVBoxLayout()
        cap_s = QtWidgets.QLabel("Slides (click one, or use Up/Down, to see it in the preview)")
        cap_s.setObjectName("hint")
        self.slide_list = QtWidgets.QListWidget()
        mid_s.addWidget(cap_s)
        mid_s.addWidget(self.slide_list, 1)
        sgl.addLayout(mid_s, 1)
        sside = QtWidgets.QVBoxLayout()
        self.song_new_b, self.song_edit_b, self.song_del_b, self.song_imp_b = (
            QtWidgets.QPushButton(x) for x in ("New song...", "Edit...", "Delete", "Import..."))
        self.song_exp_b = QtWidgets.QPushButton("Export song...")
        self.song_expall_b = QtWidgets.QPushButton("Export all...")
        for b in (self.song_new_b, self.song_edit_b, self.song_del_b, self.song_imp_b, self.song_exp_b, self.song_expall_b):
            sside.addWidget(b)
        sside.addStretch(1)
        sgl.addLayout(sside)
        self.song_edit_b.setEnabled(False)
        self.song_del_b.setEnabled(False)
        self.song_exp_b.setEnabled(False)
        self.song_expall_b.setEnabled(bool(self.song_all))
        tabs.addTab(sgw, "Songs")

        ow = QtWidgets.QWidget()
        og = QtWidgets.QFormLayout(ow)
        self.display_cb = QtWidgets.QComboBox()
        self.theme_cb = QtWidgets.QComboBox()
        self.theme_cb.addItems(["navy", "black", "gold"])
        self.theme_cb.setCurrentText(self.st["theme"])
        self.size_sp = QtWidgets.QSpinBox()
        self.size_sp.setRange(50, 200)
        self.size_sp.setSingleStep(10)
        self.size_sp.setSuffix(" %")
        self.size_sp.setValue(self.st["font_scale"])
        self.font_cb = QtWidgets.QComboBox()
        self._fill_fonts()
        self.bold_cb = QtWidgets.QCheckBox("Bold text")
        self.bold_cb.setChecked(self.st["bold"])
        self.bg_b = QtWidgets.QPushButton("Background colour...")
        self.fg_b = QtWidgets.QPushButton("Text colour...")
        self.reset_b = QtWidgets.QPushButton("Reset colours")
        self.outline_cb = QtWidgets.QCheckBox("Outline around text")
        self.outline_cb.setChecked(self.st["outline_on"])
        self.outline_b = QtWidgets.QPushButton("Outline colour...")
        self.outline_auto_b = QtWidgets.QPushButton("Auto")
        self.outline_auto_b.setToolTip("Pick the outline colour for me (dark outline on light text, light on dark text).")
        self.outline_sp = QtWidgets.QSpinBox()
        self.outline_sp.setRange(cfg.OUTLINE_MIN, cfg.OUTLINE_MAX)
        self.outline_sp.setValue(self.st["outline_px"])
        self.outline_sp.setToolTip("How thick the outline is (1 thin, 10 thick). Same look on the preview and the screen.")
        self.outline_lbl = QtWidgets.QLabel("")
        self.outline_lbl.setObjectName("hint")
        self.outline_lbl.setWordWrap(True)
        ob = QtWidgets.QHBoxLayout()
        for w_ in (self.outline_b, self.outline_auto_b, QtWidgets.QLabel("Thickness"), self.outline_sp):
            ob.addWidget(w_)
        cb = QtWidgets.QHBoxLayout()
        for w_ in (self.bg_b, self.fg_b, self.reset_b):
            cb.addWidget(w_)
        self.show_ref_cb = QtWidgets.QCheckBox("Show verse reference on screen")
        self.show_ref_cb.setChecked(self.st["show_reference"])
        og.addRow("Projector screen", self.display_cb)
        self.song_theme_lw = QtWidgets.QListWidget()
        self.song_theme_lw.setViewMode(QtWidgets.QListView.IconMode)
        self.song_theme_lw.setMovement(QtWidgets.QListView.Static)
        self.song_theme_lw.setResizeMode(QtWidgets.QListView.Adjust)
        self.song_theme_lw.setIconSize(QtCore.QSize(160, 90))
        self.song_theme_lw.setSpacing(6)
        self.song_theme_lw.setWrapping(True)
        self.song_theme_lw.setFixedHeight(280)
        self.song_theme_lw.setToolTip("Pick how song slides look. Verses are not affected. Reaches the screen after you press Project.")
        self._fill_song_themes()
        self.song_theme_lbl = QtWidgets.QLabel(songthemes.blurb(self.st["song_theme"]))
        self.song_theme_lbl.setObjectName("hint")
        self.song_theme_lbl.setWordWrap(True)
        self.verse_theme_lw = QtWidgets.QListWidget()
        self.verse_theme_lw.setViewMode(QtWidgets.QListView.IconMode)
        self.verse_theme_lw.setMovement(QtWidgets.QListView.Static)
        self.verse_theme_lw.setResizeMode(QtWidgets.QListView.Adjust)
        self.verse_theme_lw.setIconSize(QtCore.QSize(128, 72))
        self.verse_theme_lw.setSpacing(6)
        self.verse_theme_lw.setWrapping(True)
        self.verse_theme_lw.setFixedHeight(220)
        self.verse_theme_lw.setToolTip("Pick how Bible verse slides look. Songs are not affected. Reaches the screen after you press Project.")
        self._fill_verse_themes()
        self.verse_theme_lbl = QtWidgets.QLabel(versethemes.blurb(self.st["verse_theme"]))
        self.verse_theme_lbl.setObjectName("hint")
        self.verse_theme_lbl.setWordWrap(True)
        og.addRow("Bible verse style", self.verse_theme_lw)
        og.addRow("", self.verse_theme_lbl)
        og.addRow("Song slide style", self.song_theme_lw)
        og.addRow("", self.song_theme_lbl)
        og.addRow("", self._build_song_custom())
        og.addRow("Colours", self.theme_cb)
        og.addRow("Text size", self.size_sp)
        og.addRow("Font", self.font_cb)
        og.addRow("", self.bold_cb)
        og.addRow("Custom colours", cb)
        og.addRow("Text outline", self.outline_cb)
        og.addRow("", ob)
        og.addRow("", self.outline_lbl)
        og.addRow("", self.show_ref_cb)
        # --- background: solid colour, gradient, or a picture ---
        self.bgkind_cb = QtWidgets.QComboBox()
        for k, label in bgm.KINDS:
            self.bgkind_cb.addItem(label, k)
        self.bgkind_cb.setCurrentIndex(max(self.bgkind_cb.findData(self.st["bg_kind"]), 0))
        self.g1_b = QtWidgets.QPushButton("Colour 1...")
        self.g2_b = QtWidgets.QPushButton("Colour 2...")
        self.gswap_b = QtWidgets.QPushButton("Swap")
        gb = QtWidgets.QHBoxLayout()
        for w_ in (self.g1_b, self.g2_b, self.gswap_b):
            gb.addWidget(w_)
        self.gdir_cb = QtWidgets.QComboBox()
        for k, label in bgm.DIRECTIONS:
            self.gdir_cb.addItem(label, k)
        self.gdir_cb.setCurrentIndex(max(self.gdir_cb.findData(self.st["grad_direction"]), 0))
        self.img_b = QtWidgets.QPushButton("Choose picture...")
        self.imgx_b = QtWidgets.QPushButton("Remove picture")
        ib = QtWidgets.QHBoxLayout()
        ib.addWidget(self.img_b)
        ib.addWidget(self.imgx_b)
        self.imgmode_cb = QtWidgets.QComboBox()
        for k, label in bgm.IMAGE_MODES:
            self.imgmode_cb.addItem(label, k)
        self.imgmode_cb.setCurrentIndex(max(self.imgmode_cb.findData(self.st["image_mode"]), 0))
        self.imgdim_sp = QtWidgets.QSpinBox()
        self.imgdim_sp.setRange(0, bgm.DIM_MAX)
        self.imgdim_sp.setSingleStep(10)
        self.imgdim_sp.setSuffix(" %")
        self.imgdim_sp.setValue(self.st["image_dim"])
        self.imgdim_sp.setToolTip("Darkens the picture so the words stay easy to read.")
        self.img_lbl = QtWidgets.QLabel("")
        self.img_lbl.setObjectName("hint")
        self.img_lbl.setWordWrap(True)
        og.addRow("Background", self.bgkind_cb)
        og.addRow("Gradient colours", gb)
        og.addRow("Gradient direction", self.gdir_cb)
        og.addRow("Picture", ib)
        og.addRow("Picture size", self.imgmode_cb)
        og.addRow("Darken picture", self.imgdim_sp)
        og.addRow("", self.img_lbl)
        self.tfx_cb = QtWidgets.QComboBox()
        for k, label, _d in trn.EFFECTS:
            self.tfx_cb.addItem(label, k)
        self.tfx_cb.setCurrentIndex(max(self.tfx_cb.findData(self.st["transition_effect"]), 0))
        self.tdir_cb = QtWidgets.QComboBox()
        for k, label in trn.DIRECTIONS:
            self.tdir_cb.addItem(label, k)
        self.tdir_cb.setCurrentIndex(max(self.tdir_cb.findData(self.st["transition_dir"]), 0))
        self.tms_sp = QtWidgets.QSpinBox()
        self.tms_sp.setRange(0, trn.MS_MAX)
        self.tms_sp.setSingleStep(trn.MS_STEP)
        self.tms_sp.setSuffix(" ms")
        self.tms_sp.setValue(self.st["transition_ms"])
        self.tms_sp.setToolTip("How long the effect takes. 0 = instant.")
        self.tonoff_cb = QtWidgets.QCheckBox("Animate Project and Project Off")
        self.tonoff_cb.setChecked(self.st["transition_onoff"])
        self.tsw_cb = QtWidgets.QCheckBox("Animate when the screen changes")
        self.tsw_cb.setToolTip("Animate when the screen changes (Next / Previous, then Project)")
        self.tsw_cb.setChecked(self.st["transition_switch"])
        self.tfx_lbl = QtWidgets.QLabel("")
        self.tfx_lbl.setObjectName("hint")
        self.tfx_lbl.setWordWrap(True)
        og.addRow("Screen effect", self.tfx_cb)
        og.addRow("Effect direction", self.tdir_cb)
        self.pon_cb, self.poff_cb = QtWidgets.QComboBox(), QtWidgets.QComboBox()
        for cb, key, tip in ((self.pon_cb, "proj_on_effect", "Effect when Project turns the full-screen display on."),
                             (self.poff_cb, "proj_off_effect", "Effect when Project Off turns the full-screen display off.")):
            for k, label, _d in trn.EFFECTS:
                cb.addItem(label, k)
            cb.setCurrentIndex(max(cb.findData(self.st[key]), 0))
            cb.setToolTip(tip + " Separate from the Screen effect above.")
        og.addRow("Projection On", self.pon_cb)
        og.addRow("Projection Off", self.poff_cb)
        og.addRow("Effect speed", self.tms_sp)
        og.addRow("", self.tonoff_cb)
        og.addRow("", self.tsw_cb)
        og.addRow("", self.tfx_lbl)
        note = QtWidgets.QLabel("Changes show in the preview first. Click Project to send them to the screen.")
        note.setObjectName("hint")
        note.setWordWrap(True)
        og.addRow("", note)
        self._fit_settings_width(ow)
        sc = QtWidgets.QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QtWidgets.QFrame.NoFrame)
        sc.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)   # Settings scrolls up/down only
        sc.setWidget(ow)
        self.settings_scroll = sc
        tabs.addTab(sc, "Settings")
        self.tabs = tabs
        self._build_quick(tabs)
        leftc.addWidget(tabs, 1)


        rightc = QtWidgets.QVBoxLayout()
        rightc.setSpacing(4)
        body.addLayout(rightc, 2)
        cap = QtWidgets.QLabel("Live preview (what the screen shows)")
        cap.setObjectName("hint")
        self.ref_lbl = QtWidgets.QLabel("")
        self.ref_lbl.setObjectName("ref")
        rightc.addWidget(cap)
        self.tv_frame = theme.TvFrame(self.preview)   # cosmetic bezel only; the preview inside is unchanged
        rightc.addWidget(self.tv_frame)
        self.ref_lbl.hide()      # the preview already shows the reference
        nav = QtWidgets.QHBoxLayout()
        self.prev_b = QtWidgets.QPushButton("< Previous")
        self.next_b = QtWidgets.QPushButton("Next >")
        self.add_b = QtWidgets.QPushButton("Add to service list")
        nav.addWidget(self.prev_b)
        nav.addWidget(self.next_b)
        rightc.addLayout(nav)
        rightc.addWidget(self.add_b)
        rightc.addStretch(1)
        self.status = QtWidgets.QLabel("")
        self.status.setObjectName("status")
        self.status.setWordWrap(True)
        self.blank_b = QtWidgets.QPushButton("Project Off (Esc)")
        self.blank_b.setEnabled(False)
        self.project_b = QtWidgets.QPushButton("Project (F5)")
        self.project_b.setToolTip("Sends what you see in the preview to the full-screen display. Nothing goes out until you click this.")
        self.project_b.setObjectName("primary")
        self.project_b.setEnabled(False)
        rightc.addWidget(self.status)
        pb = QtWidgets.QHBoxLayout()
        pb.addWidget(self.blank_b)
        pb.addWidget(self.project_b, 1)
        rightc.addLayout(pb)
        self.credit_lbl = QtWidgets.QLabel("")
        self.credit_lbl.setObjectName("hint")
        self.credit_lbl.setWordWrap(True)
        lay.addWidget(self.credit_lbl)

        self._sync_bg_controls()
        self.refresh_displays()
        self.refresh_service_list()
        self.refresh_songs()

        go.clicked.connect(lambda: self.lookup(self.box.text()))
        self.box.returnPressed.connect(lambda: self.lookup(self.box.text()))
        self.box.textEdited.connect(self.show_suggestions)
        self.box.adjustRequested.connect(self.edit_segment)
        self.box.jumpHandler = self.jump_from_typing
        self.box.typedDigitHandler = self._digit_typed
        self.completer.activated[str].connect(self.suggestion_picked)
        self.trans.currentIndexChanged.connect(self.on_translation)
        self.prev_b.clicked.connect(lambda: self.step(-1))
        self.next_b.clicked.connect(lambda: self.step(1))
        self.add_b.clicked.connect(self.add_to_list)
        self.rm_b.clicked.connect(self.remove_item)
        self.up_b.clicked.connect(lambda: self.move_item(-1))
        self.down_b.clicked.connect(lambda: self.move_item(1))
        self.service_list.itemClicked.connect(self.pick_item)
        self.results.itemClicked.connect(self.pick_result)
        sb.clicked.connect(self.do_search)
        self.search_box.returnPressed.connect(self.do_search)
        # live search: wait for a short typing pause so a slow PC is not hit on every key
        self.search_timer = QtCore.QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(SEARCH_DELAY_MS)
        self.search_timer.timeout.connect(self.do_search)
        self.search_box.textChanged.connect(self.search_typed)
        self.song_search.textChanged.connect(lambda *_: self.refresh_songs())
        self.song_list.currentRowChanged.connect(self.pick_song)
        self.slide_list.currentRowChanged.connect(self.pick_slide)
        self.song_new_b.clicked.connect(lambda: self.edit_song(None))
        self.song_edit_b.clicked.connect(lambda: self.edit_song(self.song))
        self.song_del_b.clicked.connect(self.delete_song)
        self.song_imp_b.clicked.connect(self.import_songs)
        self.song_exp_b.clicked.connect(self.export_song)
        self.add_bible_b.clicked.connect(self.import_bible)
        self.song_expall_b.clicked.connect(self.export_all_songs)
        self.project_b.clicked.connect(self.project)
        self.blank_b.clicked.connect(self.project_off)
        self.proj.offRequested.connect(self.project_off)
        self.proj.projectRequested.connect(self.project)
        self.proj.closedByUser.connect(self._projector_closed)
        self.theme_cb.currentIndexChanged.connect(self._style_changed)
        self.song_theme_lw.currentRowChanged.connect(self._song_theme_changed)
        self.verse_theme_lw.currentRowChanged.connect(self._verse_theme_changed)
        self.size_sp.valueChanged.connect(self._style_changed)
        self.show_ref_cb.stateChanged.connect(self._style_changed)
        self.font_cb.currentIndexChanged.connect(self._style_changed)
        self.bold_cb.stateChanged.connect(self._style_changed)
        self.bg_b.clicked.connect(lambda: self.pick_color("bg_color"))
        self.fg_b.clicked.connect(lambda: self.pick_color("text_color"))
        self.reset_b.clicked.connect(self.reset_colors)
        self.outline_cb.stateChanged.connect(self._style_changed)
        self.outline_sp.valueChanged.connect(self._style_changed)
        self.outline_b.clicked.connect(self.pick_outline)
        self.outline_auto_b.clicked.connect(self.outline_auto)
        self.display_cb.currentIndexChanged.connect(self._style_changed)
        self.bgkind_cb.currentIndexChanged.connect(self._bg_changed)
        self.gdir_cb.currentIndexChanged.connect(self._bg_changed)
        self.imgmode_cb.currentIndexChanged.connect(self._bg_changed)
        self.imgdim_sp.valueChanged.connect(self._bg_changed)
        self.g1_b.clicked.connect(lambda: self.pick_grad("grad_color1"))
        self.g2_b.clicked.connect(lambda: self.pick_grad("grad_color2"))
        self.gswap_b.clicked.connect(self.swap_grad)
        self.img_b.clicked.connect(self.choose_image)
        self.imgx_b.clicked.connect(self.remove_image)
        for sig in (self.tfx_cb.currentIndexChanged, self.tdir_cb.currentIndexChanged, self.tms_sp.valueChanged,
                    self.tonoff_cb.stateChanged, self.tsw_cb.stateChanged,
                    self.pon_cb.currentIndexChanged, self.poff_cb.currentIndexChanged):
            sig.connect(self._transition_changed)
        self._sync_transition_controls()
        self._sync_outline()
        for key, fn in ((QtCore.Qt.Key_F5, self.project), (QtCore.Qt.Key_Escape, self.project_off)):
            QtWidgets.QShortcut(QtGui.QKeySequence(key), self, activated=fn)
        QtWidgets.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_PageDown), self, activated=lambda: self.step(1))
        QtWidgets.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_PageUp), self, activated=lambda: self.step(-1))
        self.resize(1000, 640)

    # ---------------- quick controls (in the tab row, right of the tabs) ----------------
    QUICK_EFFECT_SHORT = {"cut": "Cut", "fade": "Fade", "dissolve": "Blend", "wipe": "Wipe", "slide": "Slide",
                          "blinds": "Blinds", "open": "Open", "checkerboard": "Chess", "diagonal": "Diag",
                          "iris": "Iris", "zoom": "Zoom", "mosaic": "Mosaic", "clock": "Clock"}
    QUICK_SONG_SHORT = {"standard": "Std", "midnight": "Night", "classic": "Black", "sunrise": "Sun",
                        "light": "Ivory", "royal": "Royal"}
    QUICK_SPEEDS = (0, 200, 400, 800, 1500)
    QUICK_SIZES = (60, 80, 100, 120, 140)
    QUICK_W = {"effect": 66, "screen": 54, "speed": 54, "style": 62, "size": 58}

    def _quick_combo(self, key, tip):
        cb = QtWidgets.QComboBox()
        cb.setObjectName("quick")
        cb.setToolTip(tip)
        cb.setFixedWidth(self.QUICK_W[key])
        cb.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLength)
        cb.setMinimumContentsLength(3)
        cb.setStyleSheet("QComboBox{padding:3px 4px;} QComboBox::drop-down{width:14px;}")
        return cb

    def _build_quick(self, tabs):
        """Three short controls per tab, in the tab bar's own row (a corner widget), so no vertical room is used.
        They only mirror existing Settings widgets: choosing here sets that widget, which stores and saves as before."""
        host = QtWidgets.QWidget()
        host.setObjectName("quickbar")
        stack = QtWidgets.QStackedLayout(host)
        stack.setContentsMargins(0, 0, 0, 0)
        self.quick_host, self.quick_stack = host, stack

        def page(widgets):
            w = QtWidgets.QWidget()
            h = QtWidgets.QHBoxLayout(w)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(4)
            for x in widgets:
                h.addWidget(x)
            stack.addWidget(w)
            return w

        def pair(src_effect=True):
            eff = self._quick_combo("effect", "Screen effect (same as Settings > Screen effect)")
            for k, label, d in trn.EFFECTS:
                eff.addItem(self.QUICK_EFFECT_SHORT.get(k, label), k)
                eff.setItemData(eff.count() - 1, label + ": " + d, QtCore.Qt.ToolTipRole)
            return eff

        self.q_sl_effect = pair()
        self.q_sl_screen = self._quick_combo("screen", "Projector screen (same as Settings > Projector screen)")
        self.q_sl_speed = self._quick_combo("speed", "Effect speed (same as Settings > Effect speed)")
        self.q_sg_style = self._quick_combo("style", "Song slide style (same as Settings > Song slide style)")
        for k in songthemes.KEYS:
            self.q_sg_style.addItem(self.QUICK_SONG_SHORT.get(k, songthemes.label(k)), k)
            self.q_sg_style.setItemData(self.q_sg_style.count() - 1, songthemes.label(k), QtCore.Qt.ToolTipRole)
        self.q_sg_effect = pair()
        self.q_sg_size = self._quick_combo("size", "Song words size for the chosen song style (same as Settings > Words size). "
                                                  "Pick a song style other than Standard to use it.")
        self.q_sl_page = page([self.q_sl_effect, self.q_sl_screen, self.q_sl_speed])
        self.q_sg_page = page([self.q_sg_style, self.q_sg_effect, self.q_sg_size])
        self.q_none_page = page([])
        self.quick_controls = {0: [self.q_sl_effect, self.q_sl_screen, self.q_sl_speed],
                               2: [self.q_sg_style, self.q_sg_effect, self.q_sg_size]}
        for cb, fn in ((self.q_sl_effect, self._q_effect), (self.q_sg_effect, self._q_effect),
                       (self.q_sl_screen, self._q_screen), (self.q_sl_speed, self._q_speed),
                       (self.q_sg_style, self._q_style), (self.q_sg_size, self._q_size)):
            cb.activated.connect(fn)
        self.quick_ok = True
        tabs.setCornerWidget(host, QtCore.Qt.TopRightCorner)
        tabs.currentChanged.connect(self._quick_page)
        tabs.installEventFilter(self)
        self._quick_sync()
        self._quick_page(tabs.currentIndex())

    def _quick_page(self, i):
        self.quick_stack.setCurrentWidget({0: self.q_sl_page, 2: self.q_sg_page}.get(i, self.q_none_page))
        self.quick_host.setFixedSize(self.quick_stack.currentWidget().sizeHint())
        self._quick_fit()

    def _quick_fit(self):
        """If the tab row is too narrow for tabs plus controls (very small window), hide the controls
        rather than squeeze the tabs. Every option is still in Settings."""
        t = self.tabs
        need = t.tabBar().sizeHint().width() + self.quick_host.width() + 6
        if t.width() > 0:
            self.quick_host.setVisible(t.width() >= need)

    def eventFilter(self, obj, ev):
        if obj is getattr(self, "tabs", None) and ev.type() == QtCore.QEvent.Resize and getattr(self, "quick_ok", False):
            self._quick_fit()
        return super().eventFilter(obj, ev)

    def _q_set_items(self, cb, value, label):
        """Quick lists show presets; a value stored in settings that is not a preset gets its own item."""
        k = cb.findData(value)
        if k < 0:
            cb.addItem(label(value), value)
            k = cb.count() - 1
        cb.setCurrentIndex(k)

    def _quick_sync(self, *_):
        """Show the current stored settings in the quick controls (no changes are stored)."""
        if not getattr(self, "quick_ok", False):
            return
        for cb in (self.q_sl_effect, self.q_sg_effect):
            cb.blockSignals(True)
            cb.setCurrentIndex(max(cb.findData(self.st["transition_effect"]), 0))
            cb.blockSignals(False)
        cb = self.q_sl_speed
        cb.blockSignals(True)
        cb.clear()
        for ms in sorted(set(self.QUICK_SPEEDS) | {self.st["transition_ms"]}):
            cb.addItem("0" if ms == 0 else ("%gs" % (ms / 1000.0)), ms)
            cb.setItemData(cb.count() - 1, "Instant" if ms == 0 else "%d ms" % ms, QtCore.Qt.ToolTipRole)
        cb.setCurrentIndex(max(cb.findData(self.st["transition_ms"]), 0))
        cb.setEnabled(self.st["transition_effect"] != "cut")
        cb.blockSignals(False)
        cb = self.q_sl_screen
        cb.blockSignals(True)
        cb.clear()
        cb.addItem("Auto", -1)
        cb.setItemData(0, "Automatic (second screen if plugged in)", QtCore.Qt.ToolTipRole)
        for i, s in enumerate(QtWidgets.QApplication.screens()):
            g = s.geometry()
            cb.addItem("Scr %d" % (i + 1), i)
            cb.setItemData(cb.count() - 1, "Screen %d: %dx%d" % (i + 1, g.width(), g.height()), QtCore.Qt.ToolTipRole)
        cb.setCurrentIndex(max(cb.findData(self.st["display"]), 0))
        cb.blockSignals(False)
        cb = self.q_sg_style
        cb.blockSignals(True)
        cb.setCurrentIndex(max(cb.findData(self.st["song_theme"]), 0))
        cb.blockSignals(False)
        cb = self.q_sg_size
        key = self._sc_key()
        cb.blockSignals(True)
        cb.clear()
        cur = self.sc_scale_sp.value()
        for v in sorted(set(self.QUICK_SIZES) | {cur}):
            cb.addItem("%d%%" % v, v)
        cb.setCurrentIndex(max(cb.findData(cur), 0))
        cb.setEnabled(key is not None)
        cb.blockSignals(False)

    def _q_effect(self, i):
        cb = self.sender()
        self.tfx_cb.setCurrentIndex(max(self.tfx_cb.findData(cb.itemData(i)), 0))

    def _q_screen(self, i):
        k = self.display_cb.findData(self.q_sl_screen.itemData(i))
        if k >= 0:
            self.display_cb.setCurrentIndex(k)

    def _q_speed(self, i):
        self.tms_sp.setValue(int(self.q_sl_speed.itemData(i)))

    def _q_style(self, i):
        k = songthemes.KEYS.index(self.q_sg_style.itemData(i))
        self.song_theme_lw.setCurrentRow(k)

    def _q_size(self, i):
        if self._sc_key() is not None:
            self.sc_scale_sp.setValue(int(self.q_sg_size.itemData(i)))

    # ---------------- helpers ----------------
    def tr_name(self):
        return self.trans.currentData()

    def say(self, msg):
        self.status.setText(msg)

    def refresh_displays(self):
        self.display_cb.blockSignals(True)
        self.display_cb.clear()
        self.display_cb.addItem("Automatic (second screen if plugged in)", -1)
        for i, s in enumerate(QtWidgets.QApplication.screens()):
            g = s.geometry()
            self.display_cb.addItem("Screen %d: %dx%d" % (i + 1, g.width(), g.height()), i)
        k = self.display_cb.findData(self.st["display"])
        self.display_cb.setCurrentIndex(max(k, 0))
        self.display_cb.blockSignals(False)
        self._quick_sync()

    @staticmethod
    def _installed_fonts():
        return QtGui.QFontDatabase().families()

    def _fill_fonts(self):
        """Grouped font list. Only fonts really installed on this PC are offered (Georgia always stays)."""
        have = {f.lower() for f in self._installed_fonts()}
        self.font_cb.clear()
        model = self.font_cb.model()
        for title, names in cfg.FONT_GROUPS:
            ok = [n for n in names if n.lower() in have or n == "Georgia"]
            if not ok:
                continue
            self.font_cb.addItem("-- " + title + " --")
            model.item(self.font_cb.count() - 1).setFlags(QtCore.Qt.NoItemFlags)   # heading, cannot be picked
            for n in ok:
                self.font_cb.addItem(n)
        k = self.font_cb.findText(self.st["font_family"])
        self.font_cb.setCurrentIndex(k if k >= 0 else self.font_cb.findText("Georgia"))

    # ---- song style customiser (songs only; Bible verse settings are never touched from here) ----
    SONG_COLORS = (("text", "Words colour..."), ("accent", "Highlight (1st line, bar)..."), ("tag", "Section colour..."),
                   ("dim", "Title colour..."), ("bg1", "Background 1..."), ("bg2", "Background 2..."))
    SONG_CHECKS = (("show_label", "Show section name (Verse, Chorus...)"), ("upper", "Section name in CAPITALS"),
                   ("show_footer", "Show song title and artist"), ("show_count", "Show slide count (2/8)"),
                   ("two_tone", "First line in highlight colour"), ("divider", "Thin divider line"),
                   ("pill", "Rounded tags"), ("shadow", "Soft shadow behind words"), ("bold", "Bold words"))

    def _fit_settings_width(self, page):
        """Keep the Settings page narrow enough for its column (vertical scrolling only).
        Long labels used to set a wide minimum width; now the form wraps a long label above its
        field when needed, drop-downs may shrink (the full choice still shows in the list and
        tooltip) and long check-box / button texts keep their full text as a tooltip.
        The label column size is sized to the longest label, not to the gallery
        or wide field, so controls start right after the labels with one small
        gap instead of a wide blank column (Settings column only)."""
        LABEL_GAP = 12   # small consistent space between the labels and their controls
        def shrink(root):
            for cb in root.findChildren(QtWidgets.QComboBox):
                cb.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
                cb.setMinimumContentsLength(8)
            for lay in [root.layout()] + [g.layout() for g in root.findChildren(QtWidgets.QGroupBox)]:
                if isinstance(lay, QtWidgets.QFormLayout):
                    lay.setRowWrapPolicy(QtWidgets.QFormLayout.WrapLongRows)
                    lay.setLabelAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
                    lay.setHorizontalSpacing(LABEL_GAP)
                    lay.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)
                    # Largest label in this form (bare string labels become QLabels). Pinning
                    # every label to that width stops the label column stretching past the
                    # longest label, which left a wide blank column before the controls.
                    longest = 0
                    for row in range(lay.rowCount()):
                        item = lay.itemAt(row, 0)
                        if item is not None and item.widget() is not None:
                            longest = max(longest, item.widget().sizeHint().width())
                    if longest:
                        for row in range(lay.rowCount()):
                            item = lay.itemAt(row, 0)
                            if item is not None and item.widget() is not None:
                                item.widget().setFixedWidth(longest)
        shrink(page)

    def _build_song_custom(self):
        gb = QtWidgets.QGroupBox("Customise the selected song style")
        gb.setToolTip("Songs only. Bible verses are not affected.")
        f = QtWidgets.QFormLayout(gb)
        self.sc_hint = QtWidgets.QLabel("")
        self.sc_hint.setObjectName("hint")
        self.sc_hint.setWordWrap(True)
        f.addRow(self.sc_hint)
        self.sc_color_b = {}
        grid = QtWidgets.QGridLayout()
        for i, (k, label) in enumerate(self.SONG_COLORS):
            b = QtWidgets.QPushButton(label)
            self.sc_color_b[k] = b
            grid.addWidget(b, i // 2, i % 2)
        f.addRow("Colours", grid)
        self.sc_bg_cb = QtWidgets.QComboBox()
        for k, lab in (("solid", "Plain colour (Background 1)"), ("linear", "Two-colour fade"), ("radial", "Soft glow in the middle")):
            self.sc_bg_cb.addItem(lab, k)
        self.sc_frame_cb = QtWidgets.QComboBox()
        for k, lab in (("none", "No frame"), ("single", "Thin rounded frame"), ("bar", "Bar on the left"), ("card", "Soft card behind words")):
            self.sc_frame_cb.addItem(lab, k)
        self.sc_align_cb = QtWidgets.QComboBox()
        for k, lab in (("left", "Left"), ("center", "Centre"), ("right", "Right")):
            self.sc_align_cb.addItem(lab, k)
        self.sc_valign_cb = QtWidgets.QComboBox()
        for k, lab in (("top", "Top"), ("middle", "Middle"), ("bottom", "Bottom")):
            self.sc_valign_cb.addItem(lab, k)
        self.sc_scale_sp = QtWidgets.QSpinBox()
        self.sc_scale_sp.setRange(songthemes.SCALE_MIN, songthemes.SCALE_MAX)
        self.sc_scale_sp.setSingleStep(10)
        self.sc_scale_sp.setSuffix(" %")
        self.sc_scale_sp.setToolTip("Makes the words of this song style bigger or smaller. Long verses still shrink to fit.")
        self.sc_font_cb = QtWidgets.QComboBox()
        self.sc_font_cb.addItem("Same as Settings font", "")
        for n in cfg.FONTS:
            self.sc_font_cb.addItem(n, n)
        f.addRow("Background type", self.sc_bg_cb)
        f.addRow("Frame", self.sc_frame_cb)
        f.addRow("Words across", self.sc_align_cb)
        f.addRow("Words up/down", self.sc_valign_cb)
        f.addRow("Words size", self.sc_scale_sp)
        f.addRow("Words font", self.sc_font_cb)
        self.sc_check = {}
        for k, lab in self.SONG_CHECKS:
            c = QtWidgets.QCheckBox(lab)
            self.sc_check[k] = c
            f.addRow("", c)
        self.sc_reset_b = QtWidgets.QPushButton("Reset this style to its original look")
        f.addRow("", self.sc_reset_b)
        self._sc_widgets = (list(self.sc_color_b.values()) + [self.sc_bg_cb, self.sc_frame_cb, self.sc_align_cb, self.sc_valign_cb,
                                                              self.sc_scale_sp, self.sc_font_cb, self.sc_reset_b]
                            + list(self.sc_check.values()))
        for k, b in self.sc_color_b.items():
            b.clicked.connect(lambda _=False, k=k: self._sc_pick_color(k))
        for cb_, k in ((self.sc_bg_cb, "bg_kind"), (self.sc_frame_cb, "frame"), (self.sc_align_cb, "align"),
                       (self.sc_valign_cb, "valign"), (self.sc_font_cb, "font")):
            cb_.currentIndexChanged.connect(lambda _=0, cb_=cb_, k=k: self._sc_set(k, cb_.currentData()))
        self.sc_scale_sp.valueChanged.connect(lambda v: self._sc_set("scale", int(v)))
        for k, c in self.sc_check.items():
            c.toggled.connect(lambda v, k=k: self._sc_set(k, bool(v)))
        self.sc_reset_b.clicked.connect(self._sc_reset)
        self._sc_sync()
        return gb

    def _sc_key(self):
        k = self.st["song_theme"]
        return k if k in songthemes.TEMPLATES else None

    def _sc_sync(self):
        """Show the selected template's current values in the controls (no changes are stored)."""
        key = self._sc_key()
        self._sc_loading = True
        try:
            for w_ in self._sc_widgets:
                w_.setEnabled(key is not None)
            if key is None:
                self.sc_hint.setText("Standard uses your normal Settings look, so there is nothing to customise here. "
                                     "Pick one of the other song styles above, then change it below.")
                for b in self.sc_color_b.values():
                    b.setStyleSheet("")
                return
            t = songthemes.resolve(key, self.st["song_custom"])
            n = len(songthemes.changed_fields(key, self.st["song_custom"]))
            self.sc_hint.setText("Editing: %s%s. Changes show in the preview first; click Project to send them to the screen."
                                 % (t["name"], " (customised)" if n else " (original look)"))
            for k, b in self.sc_color_b.items():
                b.setStyleSheet("border-left:14px solid %s;" % t[k])
            for cb_, k in ((self.sc_bg_cb, "bg_kind"), (self.sc_frame_cb, "frame"), (self.sc_align_cb, "align"),
                           (self.sc_valign_cb, "valign"), (self.sc_font_cb, "font")):
                cb_.setCurrentIndex(max(cb_.findData(t[k]), 0))
            self.sc_scale_sp.setValue(t["scale"])
            for k, c in self.sc_check.items():
                c.setChecked(bool(t[k]))
            self.sc_reset_b.setEnabled(n > 0)
            self.sc_color_b["bg2"].setEnabled(t["bg_kind"] != "solid")
        finally:
            self._sc_loading = False
            self._quick_sync()

    def _sc_set(self, field, value):
        key = self._sc_key()
        if key is None or getattr(self, "_sc_loading", False):
            return
        ov = dict(self.st["song_custom"].get(key, {}))
        ov[field] = value
        self._sc_store(key, ov)

    def _sc_store(self, key, ov):
        """Keep only values that differ from the original preset, then redraw the preview (never the live screen)."""
        base = songthemes.resolve(key, None)
        ov = {f: v for f, v in songthemes.clean_overrides(ov).items() if base.get(f) != v}
        custom = songthemes.copy_custom(self.st["song_custom"])
        if ov:
            custom[key] = ov
        else:
            custom.pop(key, None)
        self.st["song_custom"] = custom
        self._sc_sync()
        self._refresh_song_icon(key)
        self._apply_style()
        self.save_settings()

    def _sc_pick_color(self, field):
        key = self._sc_key()
        if key is None:
            return
        cur = songthemes.resolve(key, self.st["song_custom"])[field]
        c = QtWidgets.QColorDialog.getColor(QtGui.QColor(cur), self, "Choose a colour")
        if c.isValid():
            self._sc_set(field, c.name())

    def _sc_reset(self):
        key = self._sc_key()
        if key is not None:
            self._sc_store(key, {})

    def _song_icon(self, k):
        v = SlideView()
        v.set_style("navy", 100, True, self.st["font_family"], self.st["bold"], self.st["bg_color"], self.st["text_color"],
                    bgm.spec_from(self.st), False, "", 3, k, self.st["song_custom"])
        v.set_content("x", songthemes.SAMPLE_BODY, "", songthemes.SAMPLE_META)
        return QtGui.QIcon(v.snapshot(QtCore.QSize(320, 180)).scaled(160, 90, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation))

    def _refresh_song_icon(self, key):
        if key in songthemes.KEYS:
            self.song_theme_lw.item(songthemes.KEYS.index(key)).setIcon(self._song_icon(key))

    def _fill_song_themes(self):
        """Gallery of the song templates, each with a small picture drawn by the same code as the projector."""
        self.song_theme_lw.blockSignals(True)
        self.song_theme_lw.clear()
        for k in songthemes.KEYS:
            it = QtWidgets.QListWidgetItem(self._song_icon(k), songthemes.label(k))
            it.setData(QtCore.Qt.UserRole, k)
            self.song_theme_lw.addItem(it)
        self.song_theme_lw.setCurrentRow(max(songthemes.KEYS.index(self.st["song_theme"]), 0))
        self.song_theme_lw.blockSignals(False)

    def _verse_icon(self, k):
        v = SlideView()
        v.set_style("navy", 100, True, self.st["font_family"], self.st["bold"], self.st["bg_color"], self.st["text_color"],
                    bgm.spec_from(self.st), False, "", 3, songthemes.STANDARD, None, k)
        v.set_content(versethemes.SAMPLE_REF, versethemes.SAMPLE_BODY, "")
        return QtGui.QIcon(v.snapshot(QtCore.QSize(256, 144)).scaled(128, 72, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation))

    def _fill_verse_themes(self):
        """Gallery of the verse templates, each drawn by the same code as the projector."""
        self.verse_theme_lw.blockSignals(True)
        self.verse_theme_lw.clear()
        for k in versethemes.KEYS:
            it = QtWidgets.QListWidgetItem(self._verse_icon(k), versethemes.label(k))
            it.setData(QtCore.Qt.UserRole, k)
            self.verse_theme_lw.addItem(it)
        self.verse_theme_lw.setCurrentRow(max(versethemes.KEYS.index(self.st["verse_theme"]), 0))
        self.verse_theme_lw.blockSignals(False)

    def _verse_theme_changed(self, row):
        """Only stores the choice and redraws the preview. The screen changes after Project."""
        if not (0 <= row < len(versethemes.KEYS)):
            return
        self.st["verse_theme"] = versethemes.KEYS[row]
        self.verse_theme_lbl.setText(versethemes.blurb(self.st["verse_theme"]))
        self._apply_style()
        self.save_settings()

    def _song_theme_changed(self, row):
        """Only stores the choice and redraws the preview. The screen changes after Project."""
        if not (0 <= row < len(songthemes.KEYS)):
            return
        self.st["song_theme"] = songthemes.KEYS[row]
        self.song_theme_lbl.setText(songthemes.blurb(self.st["song_theme"]))
        self._sc_sync()
        self._apply_style()
        self.save_settings()

    def _apply_style(self):
        args = (self.theme_cb.currentText(), self.size_sp.value(), self.show_ref_cb.isChecked(),
                self.font_cb.currentText(), self.bold_cb.isChecked(), self.st["bg_color"], self.st["text_color"], bgm.spec_from(self.st),
                self.st["outline_on"], self.st["outline_color"], self.st["outline_px"], self.st["song_theme"], songthemes.copy_custom(self.st["song_custom"]),
                self.st["verse_theme"])
        self._style_args = args
        self.preview.set_style(*args)
        if not self.proj.live:      # a live projector keeps its look until Project is clicked again
            self.proj.set_style(*args)
        self._refresh_live_state()

    def _text_color_now(self):
        """The text colour actually drawn right now (theme, custom, or the auto pick for a gradient)."""
        kind = bgm.spec_from(self.st)[0]
        bgc = self.st["bg_color"]
        if kind == "gradient":
            bgc = bgm.mix(self.st["grad_color1"], self.st["grad_color2"])
        elif kind == "image":
            bgc = "#0b0f19"
        return cfg.resolve_colors(self.st["theme"], bgc, self.st["text_color"])[1]

    def pick_outline(self):
        cur = cfg.resolve_outline(self._text_color_now(), self.st["outline_color"])
        c = QtWidgets.QColorDialog.getColor(QtGui.QColor(cur), self, "Choose the outline colour")
        if c.isValid():
            self.st["outline_color"] = c.name()
            self.outline_cb.setChecked(True)
            self._style_changed()

    def outline_auto(self):
        self.st["outline_color"] = ""
        self._style_changed()

    def pick_color(self, key):
        cur = cfg.resolve_colors(self.st["theme"], self.st["bg_color"], self.st["text_color"])
        start = QtGui.QColor(cur[0] if key == "bg_color" else cur[1])
        c = QtWidgets.QColorDialog.getColor(start, self, "Choose a colour")
        if c.isValid():
            self.st[key] = c.name()
            self._style_changed()

    # ---- background (preview only until Project) ----
    def pick_grad(self, key):
        c = QtWidgets.QColorDialog.getColor(QtGui.QColor(self.st[key]), self, "Choose a colour")
        if c.isValid():
            self.st[key] = c.name()
            self._bg_changed()

    def swap_grad(self):
        self.st["grad_color1"], self.st["grad_color2"] = self.st["grad_color2"], self.st["grad_color1"]
        self._bg_changed()

    def choose_image(self, path=None):
        if not path:
            start = os.path.dirname(self.st["bg_image"]) if self.st["bg_image"] else ""
            path, _ = QtWidgets.QFileDialog.getOpenFileName(
                self, "Choose a background picture", start, "Pictures (*.png *.jpg *.jpeg *.bmp *.gif)")
        if not path:
            return
        ok, msg = bgm.check_image_file(path)
        if ok:
            msg = bgm.load_image(path)[1]
        if msg:
            self.img_lbl.setText(msg)
            self.say(msg)
            return          # keep the old background; a bad file is never accepted
        self.st["bg_image"] = path
        self.bgkind_cb.blockSignals(True)
        self.bgkind_cb.setCurrentIndex(self.bgkind_cb.findData("image"))
        self.bgkind_cb.blockSignals(False)
        self._bg_changed()

    def remove_image(self):
        self.st["bg_image"] = ""
        if self.st["bg_kind"] == "image":
            self.bgkind_cb.blockSignals(True)
            self.bgkind_cb.setCurrentIndex(self.bgkind_cb.findData("color"))
            self.bgkind_cb.blockSignals(False)
        self._bg_changed()

    def _bg_changed(self, *_):
        self.st["bg_kind"] = self.bgkind_cb.currentData()
        self.st["grad_direction"] = self.gdir_cb.currentData()
        self.st["image_mode"] = self.imgmode_cb.currentData()
        self.st["image_dim"] = self.imgdim_sp.value()
        self._sync_bg_controls()
        self._style_changed()

    def _sync_bg_controls(self):
        kind = self.st["bg_kind"]
        for w_ in (self.g1_b, self.g2_b, self.gswap_b, self.gdir_cb):
            w_.setEnabled(kind == "gradient")
        for w_ in (self.imgmode_cb, self.imgdim_sp):
            w_.setEnabled(kind == "image")
        self.img_b.setEnabled(True)
        self.imgx_b.setEnabled(bool(self.st["bg_image"]))
        for b, key in ((self.g1_b, "grad_color1"), (self.g2_b, "grad_color2")):
            col = self.st[key]
            b.setStyleSheet("border-left:14px solid %s;" % col)
        self.bg_b.setEnabled(kind == "color")
        msg = ""
        if self.st["bg_image"]:
            msg = bgm.image_problem(self.st["bg_image"]) or ("Picture: " + os.path.basename(self.st["bg_image"]))
            if kind == "image" and bgm.image_problem(self.st["bg_image"]):
                msg += " (showing the plain colour)"
            if kind == "image" and not bgm.image_problem(self.st["bg_image"]):
                hint = bgm.image_hint(self.st["bg_image"], self.st["image_dim"])
                if hint:
                    msg += "\n" + hint
        elif kind == "image":
            msg = "No picture chosen yet. Click Choose picture..."
        self.img_lbl.setText(msg)

    def reset_colors(self):
        self.st["bg_color"] = self.st["text_color"] = self.st["outline_color"] = ""
        self._style_changed()

    def _style_changed(self, *_):
        self.st["theme"] = self.theme_cb.currentText()
        self.st["font_scale"] = self.size_sp.value()
        self.st["show_reference"] = self.show_ref_cb.isChecked()
        self.st["display"] = self.display_cb.currentData()
        self.st["font_family"] = self.font_cb.currentText()
        self.st["bold"] = self.bold_cb.isChecked()
        self.st["outline_on"] = self.outline_cb.isChecked()
        self.st["outline_px"] = self.outline_sp.value()
        self._sync_outline()
        self._quick_sync()
        self._apply_style()
        self.save_settings()

    def _sync_outline(self):
        self.outline_b.setEnabled(self.st["outline_on"])
        self.outline_auto_b.setEnabled(self.st["outline_on"])
        self.outline_sp.setEnabled(self.st["outline_on"])
        oc = cfg.resolve_outline(self._text_color_now(), self.st["outline_color"])
        self.outline_b.setStyleSheet("border-left:14px solid %s;" % oc)
        self.outline_lbl.setText(cfg.outline_hint(self._text_color_now(), self.st["outline_color"]) if self.st["outline_on"]
                                 else "")

    def _transition_changed(self, *_):
        """Only stores the choice. Nothing is animated or sent to the screen from here."""
        self.st["transition_effect"] = self.tfx_cb.currentData()
        self.st["transition_dir"] = self.tdir_cb.currentData()
        self.st["proj_on_effect"] = self.pon_cb.currentData()
        self.st["proj_off_effect"] = self.poff_cb.currentData()
        self.st["transition_ms"] = self.tms_sp.value()
        self.st["transition_onoff"] = self.tonoff_cb.isChecked()
        self.st["transition_switch"] = self.tsw_cb.isChecked()
        self._sync_transition_controls()
        self._quick_sync()
        self.save_settings()

    def _sync_transition_controls(self):
        eff = self.tfx_cb.currentData()
        self.tdir_cb.setEnabled(eff in trn.DIRECTED)
        self.tms_sp.setEnabled(eff != "cut")
        text = trn.describe(eff)
        if eff == "cut" or self.tms_sp.value() == 0:
            text = "Instant: the screen changes at once."
        self.tfx_lbl.setText(text + " Only the full-screen display animates; the preview always shows the final result at once.")

    def save_settings(self):
        try:
            cfg.save(self.settings_path, self.st)
        except OSError:
            pass

    # ---------------- typing suggestions ----------------
    def show_ref_hint(self, msg):
        """Inline, non-modal hint under the reference box (fade-in, auto-clears). Never touches the preview."""
        self.verse_lbl.setStyleSheet("color:%s;" % C.danger_text)
        self.verse_lbl.setText(msg)
        self._hint_on = True
        self._hint_fade.play()
        self._hint_timer.start()

    def clear_ref_hint(self):
        self._hint_timer.stop()
        if self._hint_on:
            self._hint_on = False
            self._hint_fade.stop()
            self.verse_lbl.setStyleSheet("")
            self.verse_lbl.setText("")
        self.box.set_invalid(False)

    def _digit_typed(self, before, after):
        """A digit was typed at the end. If the number is now above the book's (or chapter's) limit,
        no longer number can fix it, so the digit is not accepted: the box goes back to what it was
        and the hint explains why. Digits that may still grow into a valid number ('Psalms 15' on the
        way to 150) are always accepted."""
        t = self.tr_name()
        if not t or partial_problem(self.bible, t, before):
            return
        msg = partial_problem(self.bible, t, after)
        if msg:
            self.box.setText(before)
            self.box.setCursorPosition(len(before))
            self.show_suggestions(before)
            self.show_ref_hint(msg)

    def show_suggestions(self, text):
        t = self.tr_name()
        problem = partial_problem(self.bible, t, text) if t else None
        if problem:                      # e.g. pasted text: keep it, mark it, explain; preview untouched
            self.box.set_invalid(True)
            self.show_ref_hint(problem)
        elif self._hint_on or self.box.property("invalid"):
            self.clear_ref_hint()
        items = suggest(text, self.bible, t) if t else []
        self.sug_model.setStringList(items)
        if items:
            self.completer.setCompletionPrefix(text)
            self.completer.complete()
            self._inline_fill(text, items)
        else:
            self.completer.popup().hide()

    def _inline_fill(self, typed, items):
        """Typing a book prefix ('jo') pre-fills the top book ('Job ') with the extra letters
        selected, so Right/Left can accept it straight away. Never while erasing."""
        first = items[0]
        # Numbered books ('1 jo' -> '1 John '): the digit starts the BOOK, not a
        # chapter, so the inline fill applies just like a plain book prefix.
        if self.box.erasing() or not first.endswith(" "):
            return
        if first.lower().startswith(typed.lower()) and len(first) > len(typed) \
                and self.box.text() == typed:
            self.box.fill_suggestion(typed + first[len(typed):])

    def jump_from_typing(self, direction):
        """Left/Right while typing: accept the book/chapter being typed (or the filled-in book),
        show it in the preview only (never projects) and highlight a part. Right = next part,
        Left = previous. Returns False when the text cannot be read, so the key acts as usual."""
        t = self.tr_name()
        typed = self.box.typed_text()
        full = self.box.text()
        if not t or not typed.strip():
            return False
        # A book is being typed when it has no chapter yet: plain books
        # ('joh'), a lone ordinal ('1'), or a numbered book ('1 jo'). Those must
        # be routed to the book part, never to chapter/verse (see bible.suggest).
        if _is_bare_ordinal(typed) or not _has_chapter_number(typed):
            book = find_book(full)
            if book is None:
                top = suggest(typed, self.bible, t)
                book = find_book(top[0]) if top and top[0].endswith(" ") else None
            if book is None:
                return False
            ref, seg = book_name(book), "book"
        else:
            if not parse_reference(typed):
                return False
            ref = typed
            seg = "verse" if ":" in typed else "chapter"
        i = SEGMENTS.index(seg) + direction
        target = SEGMENTS[max(0, min(len(SEGMENTS) - 1, i))]
        self.completer.popup().hide()
        self.lookup(ref, segment=target)
        return self.cur is not None

    def suggestion_picked(self, text):
        """Book or chapter picked: keep typing with the next list. A verse: look it up.
        After a committed pick the box is left focused with the whole reference
        selected, so the next keystroke starts a fresh search (no double-click)."""
        def after():
            self.box.setText(text)
            if text.endswith(" ") or text.endswith(":"):
                self.box.setFocus()
                self.show_suggestions(text)
            else:
                self.lookup(text)
                self.box.select_all_for_replacement()
        QtCore.QTimer.singleShot(0, after)

    # ---------------- lookup ----------------
    def lookup(self, text, quiet=False, segment=None):
        parsed = parse_reference(text)
        t0 = self.tr_name()
        if t0 is not None:
            # Wrong chapter/verse (or unreadable text) must never blank the preview or drop the
            # last good verse: say what is wrong, mark the box, and leave everything else alone.
            bad = check_reference(self.bible, t0, parsed) if parsed else (
                "read", "I could not read that. Try: John 3:16  or  Rom 8:28-30  or  1 Cor 13", None)
            if bad:
                self._reject_reference(parsed, bad)
                return
        self.clear_ref_hint()
        self.verse_lbl.setText("")
        self._set_slide(None)
        self.cur = None
        if not parsed:
            self.box.forget_reference()
            self.ref_lbl.setText("")
            self.verse_lbl.setText("I could not read that. Try: John 3:16  or  Rom 8:28-30  or  1 Cor 13  (start typing a book name to see suggestions)")
            return
        b, ch, v1, v2 = parsed
        t = self.tr_name()
        if t is None:
            self.verse_lbl.setText("No Bible files found in the data/bible folder.")
            return
        body = self.bible.passage(t, b, ch, v1, v2)
        ref = format_reference(b, ch, v1, v2)
        if body is None:
            self.ref_lbl.setText("")
            self.verse_lbl.setText("%s is not in %s." % (ref, t))
            return
        self.cur = (b, ch, v1, v2, t)
        self.ref_lbl.setText("%s  (%s)" % (ref, t))
        self.verse_lbl.setText("")
        self._set_slide(("%s  (%s)" % (ref, t), body, self.bible.short_credit(t)))
        self.box.set_reference(ref, reference_spans(b, ch, v1, v2),
                               self.box.hasFocus() or self.box.segment() is not None, segment)
        self.st["last_reference"] = ref
        self.credit_lbl.setText(self.bible.credit(t))
        if not quiet:
            self.say("")
        self._refresh_live_state()
        self.save_settings()

    def _reject_reference(self, parsed, bad):
        """Committed (Enter / Look up) reference that is out of range or unreadable.
        Keeps the last valid preview and self.cur, puts the last valid reference back in the box
        with the offending part highlighted (so typing replaces it), and shows the hint."""
        kind, msg = bad[0], bad[1]
        self.show_ref_hint(msg)
        if kind in ("chapter", "verse") and self.cur is not None:
            b, ch, v1, v2, _t = self.cur
            ref = format_reference(b, ch, v1, v2)
            self.box.set_reference(ref, reference_spans(b, ch, v1, v2), True, kind)
            self.box.set_invalid(False)
        else:
            self.box.set_invalid(True)

    def _set_slide(self, slide, meta=None):
        """The ONE place the preview content changes (verses and song slides both come through here).
        meta is set for song slides only (title, artist, section, number, total) and picks the song template."""
        self.slide = slide
        self.slide_meta = meta if slide else None
        self._step_hint = 0
        if slide:
            self.preview.show_slide(*slide, meta=self.slide_meta)
        else:
            self.preview.show_slide("", "")
        self.project_b.setEnabled(bool(slide))

    def edit_segment(self, segment, delta):
        """Up/Down on the highlighted book/chapter/verse: keeps the highlight, updates the preview,
        and never touches the full-screen display (only the Project button does that)."""
        t = self.tr_name()
        if not self.cur or t is None:
            return
        new, msg = adjust_reference(self.bible, t, self.cur[:4], segment, delta)
        if new is None:
            self.say(msg)
            return
        self.lookup(format_reference(*new))

    def on_translation(self, *_):
        self.st["translation"] = self.tr_name()
        if self.search_box.text().strip():
            self.do_search()    # keep the word-search results in the chosen translation
        if self.cur is None and self.song is not None and self.slide:
            return      # a song slide is showing: a Bible translation change must not replace it
        frame_ref = self.box.text()
        self.lookup(frame_ref, quiet=True)
        # The operator just picked a translation: put the cursor in the reference
        # box with the whole reference selected, ready to type a new search.
        # Only when the box holds a committed reference; a half-typed search or a
        # song slide keeps the focus where the operator left it. When a song slide
        # is showing, the pick only retargets future lookups: the box is not
        # focused, so the operator's place is not disturbed.
        if self.cur is not None and self.box.text() == frame_ref and self.box.text().strip():
            self.box.select_all_for_replacement()

    def step(self, delta):
        before = self.slide
        self._step_to(delta)
        if self.slide != before:
            self._step_hint = delta       # lets Project pick the effect direction (Next / Previous)

    def _step_to(self, delta):
        if self.cur is None and self.song is not None and self.slide:
            r = self.slide_list.currentRow() + delta
            if 0 <= r < self.slide_list.count():
                self.slide_list.setCurrentRow(r)       # pick_slide updates the preview
            else:
                self.say("That is the last slide." if delta > 0 else "That is the first slide.")
            return
        if not self.cur:
            return
        b, ch, v1, v2, t = self.cur
        nxt = self.bible.step(t, b, ch, v2 if delta > 0 else v1, delta)
        if nxt is None:
            self.say("That is the end of the Bible." if delta > 0 else "That is the start of the Bible.")
            return
        self.lookup(format_reference(nxt[0], nxt[1], nxt[2], nxt[2]))

    # ---------------- search ----------------
    def search_typed(self, *_):
        """Called on every keystroke: restart the short wait, search when typing pauses."""
        if not self.search_box.text().strip():
            self.search_timer.stop()
            self.results.clear()
            self.say("Type words to search the Bible.")
            return
        self.search_timer.start()

    def do_search(self):
        self.search_timer.stop()
        t = self.tr_name()
        self.results.clear()
        q = self.search_box.text().strip()
        if not t or not q:
            return
        if len(q) < SEARCH_MIN_CHARS:
            self.say("Keep typing: at least %d letters." % SEARCH_MIN_CHARS)
            return
        hits = self.bible.search(t, q, 60)
        for b, c, v, text in hits:
            ref = format_reference(b, c, v, v)
            it = QtWidgets.QListWidgetItem("%s  %s" % (ref, text[:110]))
            it.setData(QtCore.Qt.UserRole, ref)
            self.results.addItem(it)
        self.say("%d match%s%s" % (len(hits), "" if len(hits) == 1 else "es", " (showing first 60)" if len(hits) >= 60 else ""))

    def pick_result(self, item):
        self.lookup(item.data(QtCore.Qt.UserRole))

    # ---------------- service list ----------------
    def refresh_service_list(self, select=None):
        self.service_list.clear()
        for it in self.services.items:
            self.service_list.addItem("%s  (%s)" % (it["ref"], it["translation"]))
        if select is not None and 0 <= select < self.service_list.count():
            self.service_list.setCurrentRow(select)

    def persist_list(self):
        try:
            self.services.save(self.list_path)
        except OSError:
            self.say("Could not save the service list.")

    def add_to_list(self):
        if not self.cur:
            self.say("The service list holds Bible verses. Look up a verse first.")
            return
        b, ch, v1, v2, t = self.cur
        ok = self.services.add(format_reference(b, ch, v1, v2), t)
        self.refresh_service_list(len(self.services.items) - 1)
        self.persist_list()
        self.say("Added." if ok else "Already in the list.")

    def remove_item(self):
        r = self.service_list.currentRow()
        self.services.remove(r)
        self.refresh_service_list(min(r, len(self.services.items) - 1))
        self.persist_list()

    def move_item(self, d):
        r = self.service_list.currentRow()
        self.refresh_service_list(self.services.move(r, d))
        self.persist_list()

    def pick_item(self, _):
        r = self.service_list.currentRow()
        if 0 <= r < len(self.services.items):
            it = self.services.items[r]
            self.trans.blockSignals(True)
            if self.trans.findData(it["translation"]) >= 0:
                self.trans.setCurrentIndex(self.trans.findData(it["translation"]))
            self.trans.blockSignals(False)
            self.lookup(it["ref"])

    # ---------------- songs and lyrics ----------------
    # Choosing a song or slide only changes the preview (same single preview as verses).
    def refresh_songs(self, select_id=None):
        shown = SongLibrary.search(self.song_all, self.song_search.text())
        self._shown_songs = shown
        self.song_list.blockSignals(True)
        self.song_list.clear()
        for sg in shown:
            self.song_list.addItem(sg.title + ("  (%s)" % sg.artist if sg.artist else ""))
        row = -1
        for i, sg in enumerate(shown):
            if select_id and sg.id == select_id:
                row = i
        if row < 0 and self.song is not None:
            row = next((i for i, sg in enumerate(shown) if sg.id == self.song.id), -1)
        if row >= 0:
            self.song_list.setCurrentRow(row)
        self.song_list.blockSignals(False)
        if row < 0:
            self._fill_slides(None)
        self.song_edit_b.setEnabled(self.song is not None)
        self.song_del_b.setEnabled(self.song is not None)
        self.song_exp_b.setEnabled(self.song is not None)
        self.song_expall_b.setEnabled(bool(self.song_all))

    def _fill_slides(self, song, show=-1):
        self.song = song
        self.slide_list.blockSignals(True)
        self.slide_list.clear()
        if song:
            for i, sl in enumerate(song.slides):
                self.slide_list.addItem("%s: %s" % (sl["label"], sl["lines"][0]))
            if 0 <= show < len(song.slides):
                self.slide_list.setCurrentRow(show)
        self.slide_list.blockSignals(False)
        self.song_edit_b.setEnabled(song is not None)
        self.song_del_b.setEnabled(song is not None)
        self.song_exp_b.setEnabled(song is not None)

    def pick_song(self, row):
        if not (0 <= row < len(self._shown_songs)):
            return
        self._fill_slides(self._shown_songs[row], 0)
        self.pick_slide(0)

    def pick_slide(self, row):
        sg = self.song
        if sg is None or not (0 <= row < len(sg.slides)):
            return
        self.cur = None
        self.box.forget_reference()
        self.ref_lbl.setText(sg.slide_ref(row))
        self.verse_lbl.setText("")
        self.credit_lbl.setText("")
        self._set_slide((sg.slide_ref(row), sg.slide_body(row), sg.artist), songthemes.meta_for(sg, row))
        self.say("")
        self._refresh_live_state()

    def edit_song(self, song):
        dlg = SongDialog(self, song)
        if dlg.exec_() != QtWidgets.QDialog.Accepted:
            return
        new = dlg.result_song()
        try:
            self.songs.save(new)
        except (OSError, ValueError) as ex:
            self.say("Could not save the song: %s" % ex)
            return
        self.song_all = self.songs.load_all()
        self.song_search.blockSignals(True)
        self.song_search.clear()
        self.song_search.blockSignals(False)
        self.song = new
        self.refresh_songs(new.id)
        self._fill_slides(next((x for x in self.song_all if x.id == new.id), new), 0)
        self.pick_slide(0)
        self.say("Song saved.")

    def delete_song(self):
        sg = self.song
        if sg is None:
            return
        ans = QtWidgets.QMessageBox.question(self, "Delete song", "Delete \"%s\"? This cannot be undone." % sg.title,
                                             QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, QtWidgets.QMessageBox.No)
        if ans != QtWidgets.QMessageBox.Yes:
            return
        self.songs.delete(sg.id)
        self.song_all = self.songs.load_all()
        self.song = None
        self.refresh_songs()
        self.say("Song deleted. The preview is unchanged.")

    def import_songs(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Import songs", "", "Songs and lyrics (*.rtsong *.json *.txt)")
        if path:
            self.import_song_file(path)

    def import_song_file(self, path):
        try:
            with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
                text = f.read()
            if path.lower().endswith(".rtsong"):
                new = import_rtsong(text)
            elif path.lower().endswith(".json"):
                new = import_song_json(text)
            else:
                title = os.path.splitext(os.path.basename(path))[0]
                slides = split_lyrics(text)
                if not slides:
                    raise ValueError("no lyrics found in this file")
                new = [Song(title, "", slides)]
            have = {x.title.lower() for x in self.song_all}
            for sg in new:                       # never overwrite: a same-title song becomes 'Title (2)'
                base, n = sg.title, 2
                while sg.title.lower() in have:
                    sg.title = "%s (%d)" % (base, n)
                    n += 1
                have.add(sg.title.lower())
                self.songs.save(sg)
        except (OSError, ValueError) as ex:
            self.say("Could not import: %s" % ex)
            return 0
        self.song_all = self.songs.load_all()
        self.refresh_songs()
        self.say("Imported %d song%s." % (len(new), "" if len(new) == 1 else "s"))
        return len(new)

    def export_song(self):
        if self.song is None:
            return 0
        start = os.path.join(self._export_dir(), safe_filename(self.song.title) + ".rtsong")
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Export song", start, "RevelateTW song (*.rtsong)")
        return self.export_song_file(path, [self.song]) if path else 0

    def export_all_songs(self):
        start = os.path.join(self._export_dir(), "RevelateTW songs.rtsong")
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Export all songs", start, "RevelateTW song (*.rtsong)")
        return self.export_song_file(path, self.song_all) if path else 0

    def _export_dir(self):
        d = os.path.join(os.path.expanduser("~"), "Documents")
        return d if os.path.isdir(d) else os.path.expanduser("~")

    def export_song_file(self, path, songs):
        """Write songs to a .rtsong file (same format as the main app). Preview and projection are not touched."""
        try:
            out = export_songs(songs, path)
        except (OSError, ValueError) as ex:
            self.say("Could not export: %s" % ex)
            return 0
        self.say("Exported %d song%s to %s" % (len(songs), "" if len(songs) == 1 else "s", out))
        return len(songs)

    # ---------------- Bible import ----------------
    def import_bible(self):
        from .bibleimport import ImportBibleDialog
        dlg = ImportBibleDialog(self, self.bible.user_directory, self.bible.translations())
        if dlg.exec_() == QtWidgets.QDialog.Accepted and dlg.imported_code:
            self.refresh_translations(dlg.imported_code)

    def refresh_translations(self, select=None):
        """Re-read the pack folders. Does not change what the preview shows."""
        self.trans.blockSignals(True)
        self.trans.clear()
        for t in self.bible.translations():
            self.trans.addItem(t, t)
        want = select or self.st["translation"]
        if want in self.bible.translations():
            self.trans.setCurrentText(want)
        self.trans.blockSignals(False)
        self.say("Added %s. Choose it from the list at the top to use it." % select if select else "Bible list updated.")

    # ---------------- projection ----------------
    # Safety rule: Enter, Left/Right/Up/Down, Next/Previous, translation and look changes only
    # change the in-app preview. The full-screen display changes ONLY in project() and project_off().
    def _preview_pair(self):
        return self.slide

    def _refresh_live_state(self):
        live = self.proj.live and self.proj.isVisible()
        self.preview.on_air = live
        self.preview.update()
        self.tv_frame.set_on_air(live)
        self.blank_b.setEnabled(live)
        if not live:
            self.live_badge.setText("")
            self.live_badge.setStyleSheet("")
            return
        pair = self._preview_pair()
        same = bool(pair) and (pair[0], pair[1]) == (self.proj.ref, self.proj.body) \
            and getattr(self, "_style_args", None) == self._sent_style
        self.live_badge.setText("LIVE" if same else "LIVE (preview not sent yet)")
        self.live_badge.setStyleSheet(
            "color:%s; background:%s; border:1px solid %s; border-radius:4px; padding:3px 8px; font-weight:bold;"
            % (C.live_on_text, C.live_on_bg, C.live_on_border))

    _sent_style = None

    _step_hint = 0

    def project(self):
        """Send exactly what the preview shows (text and look) to the full-screen display.
        The screen effect (if any) plays on the full-screen display only."""
        pair = self._preview_pair()
        if not pair:
            self.say("Look up a verse first, then press Project.")
            return
        ref, body, credit = pair
        args = getattr(self, "_style_args", None)
        was_live = bool(self.proj.live and self.proj.isVisible())
        same = was_live and (ref, body, credit) == (self.proj.ref, self.proj.body, self.proj.credit) \
            and args == self._sent_style
        plan = trn.plan(trn.SWITCH if was_live else trn.ON, self.st, self._step_hint, same_picture=same)
        windowed = []

        def change():
            if args:
                self.proj.set_style(*args)
                self._sent_style = args
            self.proj.set_content(ref, body, credit, getattr(self, "slide_meta", None))
            if not self.proj.isVisible():
                idx, ext = self.proj.open_on(self.st["display"], self)
                windowed.append(not ext)

        self.proj.transition(plan, change)
        self._step_hint = 0
        self._refresh_live_state()
        if windowed and windowed[0]:
            self.say("Only one screen found, so the projection is a window. Plug in the projector and choose it under Screen.")
        else:
            self.say("On screen: " + ref)

    def project_off(self):
        """Close the full-screen display. Preview, selection, service list and settings stay as they are."""
        was_live = bool(self.proj.live and self.proj.isVisible())
        plan = trn.plan(trn.OFF, self.st, 0, same_picture=not was_live)

        def change():
            self.proj.blank()

        def after():
            self.proj.hide()
            self.proj.set_style(*self._style_args)

        self.proj.transition(plan, change, after)
        self._sent_style = None
        self._refresh_live_state()
        self.say("Projection is off. Your preview is unchanged.")

    blank = project_off   # old name

    def _projector_closed(self):
        """Projector window closed by Alt+F4 or similar: treat it like Project Off."""
        self.proj.live = False
        self._sent_style = None
        self._refresh_live_state()
        self.say("Projection window closed. Your preview is unchanged.")

    def closeEvent(self, e):
        self.proj.closedByUser.disconnect()
        self.proj.close()
        self.bible.close()
        e.accept()


class SongDialog(QtWidgets.QDialog):
    """New song / edit song: title, artist and pasted lyrics. Slides are cut automatically."""

    def __init__(self, parent, song=None):
        super().__init__(parent)
        self.setWindowTitle("Edit song" if song else "New song")
        self._song = song
        lay = QtWidgets.QVBoxLayout(self)
        self.title_e = QtWidgets.QLineEdit(song.title if song else "")
        self.title_e.setPlaceholderText("Song title")
        self.artist_e = QtWidgets.QLineEdit(song.artist if song else "")
        self.artist_e.setPlaceholderText("Artist (optional)")
        self.lyrics_e = QtWidgets.QPlainTextEdit(lyrics_text(song.slides) if song else "")
        self.lyrics_e.setPlaceholderText("Paste or type the lyrics.\nLeave a blank line between slides.\n"
                                         "Put [Verse 1], [Chorus] on its own line to name a slide.")
        self.info = QtWidgets.QLabel("")
        self.info.setObjectName("hint")
        self.msg = QtWidgets.QLabel("")
        self.msg.setObjectName("hint")
        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel)
        self.save_b = btns.button(QtWidgets.QDialogButtonBox.Save)
        for w_ in (self.title_e, self.artist_e, self.lyrics_e, self.info, self.msg, btns):
            lay.addWidget(w_)
        btns.accepted.connect(self._ok)
        btns.rejected.connect(self.reject)
        self.lyrics_e.textChanged.connect(self._count)
        self._count()
        self.resize(520, 520)

    def _count(self):
        n = len(split_lyrics(self.lyrics_e.toPlainText()))
        self.info.setText("%d slide%s" % (n, "" if n == 1 else "s"))

    def _ok(self):
        if not self.title_e.text().strip():
            self.msg.setText("Give the song a title.")
            return
        if not split_lyrics(self.lyrics_e.toPlainText()):
            self.msg.setText("Add some lyrics first.")
            return
        self.accept()

    def result_song(self):
        return Song(self.title_e.text(), self.artist_e.text(), split_lyrics(self.lyrics_e.toPlainText()),
                    self._song.id if self._song else "")


def main(argv=None):
    argv = list(sys.argv if argv is None else argv)
    app = QtWidgets.QApplication(argv)
    app.setApplicationName("RevelateTW Lite")
    app.setStyleSheet(QSS)
    w = Main()
    w.show()
    if "--smoke" in argv:
        w.project()
        QtCore.QTimer.singleShot(1500, lambda: (print(report_memory()), app.quit()))
    return app.exec_()


def report_memory():
    try:
        import resource
        return "peak memory: %d MB" % (resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024)
    except ImportError:
        import ctypes
        from ctypes import wintypes

        class PMC(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                        ("a", ctypes.c_size_t), ("b", ctypes.c_size_t), ("c", ctypes.c_size_t),
                        ("d", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t),
                        ("PeakPagefileUsage", ctypes.c_size_t)]
        pmc = PMC()
        pmc.cb = ctypes.sizeof(PMC)
        ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.windll.kernel32.GetCurrentProcess(),
                                                 ctypes.byref(pmc), pmc.cb)
        return "peak memory: %d MB" % (pmc.PeakWorkingSetSize / 1048576)
