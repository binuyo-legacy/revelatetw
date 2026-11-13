"""RevelateTW Lite operator window (PyQt5). Same palette/type/spacing as the main app."""
import os
import sys

from PyQt5 import QtCore, QtGui, QtWidgets

from revelatetw.ui_tokens import COLORS as C, TYPE as T, SPACE as S

from . import __version__, paths, settings as cfg
from .bible import BibleStore, format_reference, parse_reference, book_name
from .projection import ProjectionWindow
from .servicelist import ServiceList

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


class Main(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RevelateTW Lite")
        self.bible = BibleStore()
        self.settings_path = os.path.join(paths.user_dir(), "settings.json")
        self.list_path = os.path.join(paths.user_dir(), "service.json")
        self.st = cfg.load(self.settings_path)
        self.services = ServiceList.load(self.list_path)
        self.proj = ProjectionWindow()
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

        row = QtWidgets.QHBoxLayout()
        self.trans = QtWidgets.QComboBox()
        names = self.bible.translations()
        for t in names:
            self.trans.addItem(t, t)
        if self.st["translation"] in names:
            self.trans.setCurrentText(self.st["translation"])
        self.box = QtWidgets.QLineEdit(self.st["last_reference"])
        self.box.setPlaceholderText("Type a verse, e.g. John 3:16 or Rom 8:28-30")
        go = QtWidgets.QPushButton("Look up")
        row.addWidget(self.trans)
        row.addWidget(self.box, 1)
        row.addWidget(go)
        lay.addLayout(row)

        card = QtWidgets.QFrame()
        card.setObjectName("card")
        cl = QtWidgets.QVBoxLayout(card)
        cl.setContentsMargins(S.panel_x, S.panel_y, S.panel_x, S.panel_y)
        self.ref_lbl = QtWidgets.QLabel("")
        self.ref_lbl.setObjectName("ref")
        self.verse_lbl = QtWidgets.QLabel("")
        self.verse_lbl.setObjectName("verse")
        self.verse_lbl.setWordWrap(True)
        self.verse_lbl.setAlignment(QtCore.Qt.AlignTop | QtCore.Qt.AlignLeft)
        self.verse_lbl.setTextInteractionFlags(QtCore.Qt.NoTextInteraction)
        cl.addWidget(self.ref_lbl)
        cl.addWidget(self.verse_lbl, 1)
        lay.addWidget(card, 2)

        nav = QtWidgets.QHBoxLayout()
        self.prev_b = QtWidgets.QPushButton("< Previous verse")
        self.next_b = QtWidgets.QPushButton("Next verse >")
        self.add_b = QtWidgets.QPushButton("Add to service list")
        nav.addWidget(self.prev_b)
        nav.addWidget(self.next_b)
        nav.addStretch(1)
        nav.addWidget(self.add_b)
        lay.addLayout(nav)

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
        self.show_ref_cb = QtWidgets.QCheckBox("Show verse reference on screen")
        self.show_ref_cb.setChecked(self.st["show_reference"])
        og.addRow("Projector screen", self.display_cb)
        og.addRow("Colours", self.theme_cb)
        og.addRow("Text size", self.size_sp)
        og.addRow("", self.show_ref_cb)
        tabs.addTab(ow, "Screen")
        lay.addWidget(tabs, 3)

        bottom = QtWidgets.QHBoxLayout()
        self.status = QtWidgets.QLabel("")
        self.status.setObjectName("status")
        self.blank_b = QtWidgets.QPushButton("Black screen (Esc)")
        self.project_b = QtWidgets.QPushButton("Project (F5)")
        self.project_b.setObjectName("primary")
        self.project_b.setEnabled(False)
        bottom.addWidget(self.status, 1)
        bottom.addWidget(self.blank_b)
        bottom.addWidget(self.project_b)
        lay.addLayout(bottom)
        self.credit_lbl = QtWidgets.QLabel("")
        self.credit_lbl.setObjectName("hint")
        self.credit_lbl.setWordWrap(True)
        lay.addWidget(self.credit_lbl)

        self.refresh_displays()
        self.refresh_service_list()

        go.clicked.connect(lambda: self.lookup(self.box.text()))
        self.box.returnPressed.connect(lambda: self.lookup(self.box.text()))
        self.trans.currentIndexChanged.connect(self.on_translation)
        self.prev_b.clicked.connect(lambda: self.step(-1))
        self.next_b.clicked.connect(lambda: self.step(1))
        self.add_b.clicked.connect(self.add_to_list)
        self.rm_b.clicked.connect(self.remove_item)
        self.up_b.clicked.connect(lambda: self.move_item(-1))
        self.down_b.clicked.connect(lambda: self.move_item(1))
        self.service_list.itemClicked.connect(self.pick_item)
        self.service_list.itemDoubleClicked.connect(lambda _: self.project())
        self.results.itemClicked.connect(self.pick_result)
        self.results.itemDoubleClicked.connect(lambda _: self.project())
        sb.clicked.connect(self.do_search)
        self.search_box.returnPressed.connect(self.do_search)
        self.project_b.clicked.connect(self.project)
        self.blank_b.clicked.connect(self.blank)
        self.theme_cb.currentIndexChanged.connect(self._style_changed)
        self.size_sp.valueChanged.connect(self._style_changed)
        self.show_ref_cb.stateChanged.connect(self._style_changed)
        self.display_cb.currentIndexChanged.connect(self._style_changed)
        for key, fn in ((QtCore.Qt.Key_F5, self.project), (QtCore.Qt.Key_Escape, self.blank)):
            QtWidgets.QShortcut(QtGui.QKeySequence(key), self, activated=fn)
        QtWidgets.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_PageDown), self, activated=lambda: self.step(1, True))
        QtWidgets.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_PageUp), self, activated=lambda: self.step(-1, True))
        self.resize(760, 780)

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
        self.proj.set_style(self.theme_cb.currentText(), self.size_sp.value(), self.show_ref_cb.isChecked())

    def _style_changed(self, *_):
        self.st["theme"] = self.theme_cb.currentText()
        self.st["font_scale"] = self.size_sp.value()
        self.st["show_reference"] = self.show_ref_cb.isChecked()
        self.st["display"] = self.display_cb.currentData()
        self._apply_style()
        self.save_settings()

    def save_settings(self):
        try:
            cfg.save(self.settings_path, self.st)
        except OSError:
            pass

    # ---------------- lookup ----------------
    def lookup(self, text, quiet=False):
        parsed = parse_reference(text)
        self.project_b.setEnabled(False)
        self.cur = None
        if not parsed:
            self.ref_lbl.setText("")
            self.verse_lbl.setText("I could not read that. Try: John 3:16  or  Rom 8:28-30  or  1 Cor 13")
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
        self.verse_lbl.setText(body)
        self.box.setText(ref)
        self.st["last_reference"] = ref
        self.credit_lbl.setText(self.bible.credit(t))
        self.project_b.setEnabled(True)
        if not quiet:
            self.say("")
        self.save_settings()

    def on_translation(self, *_):
        self.st["translation"] = self.tr_name()
        self.lookup(self.box.text(), quiet=True)
        if self.proj.live and self.cur:
            self.project()

    def step(self, delta, project_now=False):
        if not self.cur:
            return
        b, ch, v1, v2, t = self.cur
        nxt = self.bible.step(t, b, ch, v2 if delta > 0 else v1, delta)
        if nxt is None:
            self.say("That is the end of the Bible." if delta > 0 else "That is the start of the Bible.")
            return
        self.lookup(format_reference(nxt[0], nxt[1], nxt[2], nxt[2]))
        if project_now or self.proj.live:
            self.project()

    # ---------------- search ----------------
    def do_search(self):
        t = self.tr_name()
        self.results.clear()
        if not t:
            return
        hits = self.bible.search(t, self.search_box.text(), 60)
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

    # ---------------- projection ----------------
    def project(self):
        if not self.cur:
            return
        b, ch, v1, v2, t = self.cur
        body = self.bible.passage(t, b, ch, v1, v2)
        ref = "%s  (%s)" % (format_reference(b, ch, v1, v2), t)
        self.proj.set_content(ref, body, self.bible.short_credit(t))
        if not self.proj.isVisible():
            idx, ext = self.proj.open_on(self.st["display"], self)
            if not ext:
                self.say("Only one screen found, so the projection is a window. Plug in the projector and choose it under Screen.")
        self.live_badge.setText("LIVE")
        self.live_badge.setStyleSheet(
            "color:%s; background:%s; border:1px solid %s; border-radius:4px; padding:3px 8px; font-weight:bold;"
            % (C.live_on_text, C.live_on_bg, C.live_on_border))
        if self.status.text().startswith("Only one"):
            return
        self.say("On screen: " + ref)

    def blank(self):
        self.proj.blank()
        self.live_badge.setText("")
        self.live_badge.setStyleSheet("")
        self.say("Screen is black.")

    def closeEvent(self, e):
        self.proj.close()
        self.bible.close()
        e.accept()


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
