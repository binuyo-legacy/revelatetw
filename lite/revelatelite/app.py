"""RevelateTW Lite operator window (PyQt5). Same palette/type/spacing as the main app."""
import os
import sys

from PyQt5 import QtCore, QtGui, QtWidgets

from revelatetw.ui_tokens import COLORS as C, TYPE as T, SPACE as S

from . import __version__, paths, settings as cfg
from .bible import BibleStore, format_reference, parse_reference, book_name, find_book, SEGMENTS, suggest, reference_spans, adjust_reference
from .refedit import RefEdit
from .projection import PreviewView, ProjectionWindow
from .servicelist import ServiceList
from .songs import Song, SongLibrary, split_lyrics, lyrics_text, import_rtsong, import_song_json, export_songs, safe_filename

QSS = """
QWidget {{ background:{bg}; color:{text}; font-size:{body}px; }}
QLineEdit, QComboBox, QListWidget, QSpinBox {{ background:{inp}; border:1px solid {bc}; padding:6px; border-radius:4px; }}
QListWidget::item {{ padding:6px; }}
QListWidget::item:selected {{ background:{sel}; color:{accent}; }}
QPushButton {{ background:{raised}; border:1px solid {bc}; padding:7px 14px; border-radius:4px; }}
QPushButton:hover {{ border-color:{bh}; }}
QPushButton:disabled {{ color:{dis}; }}
QPushButton#primary {{ background:{accent}; color:{on}; border:none; font-weight:bold; }}
QPushButton#primary:hover {{ background:{acch}; }}
QPushButton#primary:disabled {{ background:{raised}; color:{dis}; }}
QFrame#card {{ background:{alt}; border:1px solid {bcard}; border-radius:6px; }}
QLabel {{ background:transparent; }}
QLabel#ref {{ color:{accent}; font-size:{emph}px; font-weight:bold; }}
QLabel#verse {{ font-size:{trans}px; }}
QLabel#status, QLabel#hint {{ color:{muted}; font-size:{cap}px; }}
QLabel#live {{ color:{lt}; background:{lbg}; border:1px solid {lb}; border-radius:4px; padding:3px 8px; font-weight:bold; }}
QTabWidget::pane {{ border:1px solid {bcard}; }}
QTabBar::tab {{ background:{raised}; padding:6px 14px; border:1px solid {bc}; }}
QTabBar::tab:selected {{ color:{accent}; border-bottom-color:{accent}; }}
""".format(bg=C.bg, text=C.text, body=T.body, inp=C.surface_input, bc=C.border_control, sel=C.selected_bg,
           accent=C.accent, raised=C.surface_raised, bh=C.border_hover, dis=C.text_disabled, on=C.accent_on,
           acch=C.accent_hover, alt=C.surface_alt, bcard=C.border_card, emph=T.emphasis, trans=T.transcript,
           muted=C.text_muted, cap=T.caption, lt=C.live_on_text, lbg=C.live_on_bg, lb=C.live_on_border)


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
        leftc.addWidget(find)

        tabs = QtWidgets.QTabWidget()
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
        self.font_cb.addItems(cfg.FONTS)
        self.font_cb.setCurrentText(self.st["font_family"])
        self.bold_cb = QtWidgets.QCheckBox("Bold text")
        self.bold_cb.setChecked(self.st["bold"])
        self.bg_b = QtWidgets.QPushButton("Background colour...")
        self.fg_b = QtWidgets.QPushButton("Text colour...")
        self.reset_b = QtWidgets.QPushButton("Reset colours")
        cb = QtWidgets.QHBoxLayout()
        for w_ in (self.bg_b, self.fg_b, self.reset_b):
            cb.addWidget(w_)
        self.show_ref_cb = QtWidgets.QCheckBox("Show verse reference on screen")
        self.show_ref_cb.setChecked(self.st["show_reference"])
        og.addRow("Projector screen", self.display_cb)
        og.addRow("Colours", self.theme_cb)
        og.addRow("Text size", self.size_sp)
        og.addRow("Font", self.font_cb)
        og.addRow("", self.bold_cb)
        og.addRow("Custom colours", cb)
        og.addRow("", self.show_ref_cb)
        tabs.addTab(ow, "Look and screen")
        leftc.addWidget(tabs, 1)


        rightc = QtWidgets.QVBoxLayout()
        rightc.setSpacing(4)
        body.addLayout(rightc, 2)
        cap = QtWidgets.QLabel("Live preview (what the screen shows)")
        cap.setObjectName("hint")
        self.ref_lbl = QtWidgets.QLabel("")
        self.ref_lbl.setObjectName("ref")
        rightc.addWidget(cap)
        rightc.addWidget(self.preview)
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

        self.refresh_displays()
        self.refresh_service_list()
        self.refresh_songs()

        go.clicked.connect(lambda: self.lookup(self.box.text()))
        self.box.returnPressed.connect(lambda: self.lookup(self.box.text()))
        self.box.textEdited.connect(self.show_suggestions)
        self.box.adjustRequested.connect(self.edit_segment)
        self.box.jumpHandler = self.jump_from_typing
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
        self.size_sp.valueChanged.connect(self._style_changed)
        self.show_ref_cb.stateChanged.connect(self._style_changed)
        self.font_cb.currentIndexChanged.connect(self._style_changed)
        self.bold_cb.stateChanged.connect(self._style_changed)
        self.bg_b.clicked.connect(lambda: self.pick_color("bg_color"))
        self.fg_b.clicked.connect(lambda: self.pick_color("text_color"))
        self.reset_b.clicked.connect(self.reset_colors)
        self.display_cb.currentIndexChanged.connect(self._style_changed)
        for key, fn in ((QtCore.Qt.Key_F5, self.project), (QtCore.Qt.Key_Escape, self.project_off)):
            QtWidgets.QShortcut(QtGui.QKeySequence(key), self, activated=fn)
        QtWidgets.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_PageDown), self, activated=lambda: self.step(1))
        QtWidgets.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_PageUp), self, activated=lambda: self.step(-1))
        self.resize(1000, 640)

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

    def _apply_style(self):
        args = (self.theme_cb.currentText(), self.size_sp.value(), self.show_ref_cb.isChecked(),
                self.font_cb.currentText(), self.bold_cb.isChecked(), self.st["bg_color"], self.st["text_color"])
        self._style_args = args
        self.preview.set_style(*args)
        if not self.proj.live:      # a live projector keeps its look until Project is clicked again
            self.proj.set_style(*args)
        self._refresh_live_state()

    def pick_color(self, key):
        cur = cfg.resolve_colors(self.st["theme"], self.st["bg_color"], self.st["text_color"])
        start = QtGui.QColor(cur[0] if key == "bg_color" else cur[1])
        c = QtWidgets.QColorDialog.getColor(start, self, "Choose a colour")
        if c.isValid():
            self.st[key] = c.name()
            self._style_changed()

    def reset_colors(self):
        self.st["bg_color"] = self.st["text_color"] = ""
        self._style_changed()

    def _style_changed(self, *_):
        self.st["theme"] = self.theme_cb.currentText()
        self.st["font_scale"] = self.size_sp.value()
        self.st["show_reference"] = self.show_ref_cb.isChecked()
        self.st["display"] = self.display_cb.currentData()
        self.st["font_family"] = self.font_cb.currentText()
        self.st["bold"] = self.bold_cb.isChecked()
        self._apply_style()
        self.save_settings()

    def save_settings(self):
        try:
            cfg.save(self.settings_path, self.st)
        except OSError:
            pass

    # ---------------- typing suggestions ----------------
    def show_suggestions(self, text):
        t = self.tr_name()
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
        if self.box.erasing() or not first.endswith(" ") or any(c.isdigit() for c in typed):
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
        if not any(c.isdigit() for c in typed):          # a book is being typed
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
        """Book or chapter picked: keep typing with the next list. A verse: look it up."""
        def after():
            self.box.setText(text)
            if text.endswith(" ") or text.endswith(":"):
                self.box.setFocus()
                self.show_suggestions(text)
            else:
                self.lookup(text)
        QtCore.QTimer.singleShot(0, after)

    # ---------------- lookup ----------------
    def lookup(self, text, quiet=False, segment=None):
        parsed = parse_reference(text)
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

    def _set_slide(self, slide):
        """The ONE place the preview content changes (verses and song slides both come through here)."""
        self.slide = slide
        if slide:
            self.preview.show_slide(*slide)
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
        self.lookup(self.box.text(), quiet=True)

    def step(self, delta):
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
        self._set_slide((sg.slide_ref(row), sg.slide_body(row), sg.artist))
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

    def project(self):
        """Send exactly what the preview shows (text and look) to the full-screen display."""
        pair = self._preview_pair()
        if not pair:
            self.say("Look up a verse first, then press Project.")
            return
        ref, body, credit = pair
        args = getattr(self, "_style_args", None)
        if args:
            self.proj.set_style(*args)
            self._sent_style = args
        self.proj.set_content(ref, body, credit)
        windowed = False
        if not self.proj.isVisible():
            idx, ext = self.proj.open_on(self.st["display"], self)
            windowed = not ext
        self._refresh_live_state()
        if windowed:
            self.say("Only one screen found, so the projection is a window. Plug in the projector and choose it under Screen.")
        else:
            self.say("On screen: " + ref)

    def project_off(self):
        """Close the full-screen display. Preview, selection, service list and settings stay as they are."""
        self.proj.blank()
        self.proj.hide()
        self._sent_style = None
        self._refresh_live_state()
        self.proj.set_style(*self._style_args)
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
