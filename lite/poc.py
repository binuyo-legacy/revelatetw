"""RevelateTW Lite proof of concept (PyQt5). Logo + brand colours, manual verse lookup,
second projection window. Reads the bundled Bible .sqlite packs with plain sqlite3.
Run from the repo root:  python lite\\poc.py
"""
import os
import re
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from revelatetw.books import BOOKS, name_forms  # noqa: E402
from revelatetw.ui_tokens import COLORS as C, TYPE as T, SPACE as S  # noqa: E402

BIBLE_DIR = os.path.join(ROOT, "data", "bible")
LOGO = os.path.join(ROOT, "revelatetw", "assets", "logo.png")


def list_translations():
    return sorted(f[:-7] for f in os.listdir(BIBLE_DIR) if f.endswith(".sqlite"))


def get_verse(translation, book_id, chapter, verse):
    """Return verse text or None. Opens read-only, closes right away (low memory)."""
    path = os.path.join(BIBLE_DIR, translation + ".sqlite")
    conn = sqlite3.connect("file:" + path.replace("\\", "/") + "?mode=ro", uri=True)
    try:
        row = conn.execute("SELECT text FROM verses WHERE book_id=? AND chapter=? AND verse=?",
                           (book_id, chapter, verse)).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def _book_lookup():
    """Every spelling (full names, abbreviations, '1cor', 'first john') -> book_id."""
    out = {}
    for b in BOOKS:
        for form in name_forms(b.book_id):
            out[form] = b.book_id
    return out


_BOOK_LOOKUP = _book_lookup()


def find_book(text):
    key = re.sub(r"\s+", " ", text.lower().replace(".", " ")).strip()
    return _BOOK_LOOKUP.get(key)


def parse_reference(text):
    """'John 3:16', 'Rom 8:28', '1 cor 13:4', 'ps 23:1-3' -> (book_id, chapter, verse, last_verse).
    last_verse equals verse for a single verse. Returns None if it cannot be read."""
    m = re.match(r"^\s*(.+?)\s*(\d+)\s*[:. ]\s*(\d+)\s*(?:[-\u2013]\s*(\d+))?\s*$", text)
    if not m:
        return None
    book = find_book(m.group(1))
    if book is None:
        return None
    v1 = int(m.group(3))
    v2 = int(m.group(4)) if m.group(4) else v1
    if v2 < v1:
        return None
    return book, int(m.group(2)), v1, v2


def get_passage(translation, book_id, chapter, v1, v2):
    """Text for v1..v2 (single verse: plain text; range: verses joined with numbers). None if missing."""
    parts = []
    for v in range(v1, v2 + 1):
        t = get_verse(translation, book_id, chapter, v)
        if t is None:
            break
        parts.append(t)
    if not parts:
        return None
    if v1 == v2:
        return parts[0]
    return " ".join(f"{v1 + i} {t}" for i, t in enumerate(parts))


QSS = f"""
QWidget {{ background:{C.bg}; color:{C.text}; font-size:{T.body}px; }}
QLineEdit, QComboBox {{ background:{C.surface_input}; border:1px solid {C.border_control};
  padding:6px; border-radius:4px; }}
QPushButton {{ background:{C.surface_raised}; border:1px solid {C.border_control};
  padding:7px 14px; border-radius:4px; }}
QPushButton:hover {{ border-color:{C.border_hover}; }}
QPushButton#primary {{ background:{C.accent}; color:{C.accent_on}; border:none; font-weight:bold; }}
QPushButton#primary:hover {{ background:{C.accent_hover}; }}
QFrame#card {{ background:{C.surface_alt}; border:1px solid {C.border_card}; border-radius:6px; }}
QLabel#ref {{ color:{C.accent}; font-size:{T.emphasis}px; font-weight:bold; background:transparent; }}
QLabel#status {{ color:{C.text_muted}; background:transparent; }}
"""


def main():
    from PyQt5 import QtCore, QtGui, QtWidgets
    app = QtWidgets.QApplication(sys.argv)
    app.setStyleSheet(QSS)

    # projection window (second window; goes to 2nd monitor if one exists)
    proj = QtWidgets.QWidget()
    proj.setWindowTitle("RevelateTW Lite - Projection")
    proj.setStyleSheet("background:#000;")
    pl = QtWidgets.QVBoxLayout(proj)
    pl.setContentsMargins(60, 40, 60, 40)
    pref = QtWidgets.QLabel("")
    pref.setStyleSheet(f"color:{C.accent}; font-size:36px; font-weight:bold; background:transparent;")
    pref.setAlignment(QtCore.Qt.AlignCenter)
    ptext = QtWidgets.QLabel("")
    ptext.setWordWrap(True)
    ptext.setAlignment(QtCore.Qt.AlignCenter)
    ptext.setStyleSheet("color:#fff; font-size:44px; background:transparent;")
    pl.addWidget(pref)
    pl.addWidget(ptext, 1)
    proj.resize(960, 540)

    win = QtWidgets.QWidget()
    win.setWindowTitle("RevelateTW Lite (proof of concept)")
    lay = QtWidgets.QVBoxLayout(win)
    lay.setContentsMargins(S.xl, S.xl, S.xl, S.xl)
    lay.setSpacing(S.gap)
    logo = QtWidgets.QLabel()
    pm = QtGui.QPixmap(LOGO)
    if not pm.isNull():
        logo.setPixmap(pm.scaledToHeight(48, QtCore.Qt.SmoothTransformation))
    logo.setStyleSheet("background:transparent;")
    lay.addWidget(logo)

    row = QtWidgets.QHBoxLayout()
    trans = QtWidgets.QComboBox()
    trans.addItems(list_translations())
    if "KJV" in list_translations():
        trans.setCurrentText("KJV")
    box = QtWidgets.QLineEdit("John 3:16")
    find = QtWidgets.QPushButton("Look up")
    row.addWidget(trans)
    row.addWidget(box, 1)
    row.addWidget(find)
    lay.addLayout(row)

    card = QtWidgets.QFrame()
    card.setObjectName("card")
    cl = QtWidgets.QVBoxLayout(card)
    ref = QtWidgets.QLabel("")
    ref.setObjectName("ref")
    body = QtWidgets.QLabel("Type a reference like John 3:16 and press Look up.")
    body.setWordWrap(True)
    cl.addWidget(ref)
    cl.addWidget(body)
    lay.addWidget(card, 1)

    status = QtWidgets.QLabel("")
    status.setObjectName("status")
    project = QtWidgets.QPushButton("Project")
    project.setObjectName("primary")
    project.setEnabled(False)
    bottom = QtWidgets.QHBoxLayout()
    bottom.addWidget(status, 1)
    bottom.addWidget(project)
    lay.addLayout(bottom)

    current = {}

    def do_lookup():
        parsed = parse_reference(box.text())
        project.setEnabled(False)
        if not parsed:
            ref.setText("")
            body.setText("Could not read that reference. Try: John 3:16 or Rom 8:28")
            return
        b, ch, v, v2 = parsed
        t = trans.currentText()
        text = get_passage(t, b, ch, v, v2)
        name = BOOKS[b - 1].name
        shown = f"{ch}:{v}" if v == v2 else f"{ch}:{v}-{v2}"
        if text is None:
            ref.setText("")
            body.setText(f"{name} {shown} is not in {t}.")
            return
        current["ref"] = f"{name} {shown} ({t})"
        current["text"] = text
        ref.setText(current["ref"])
        body.setText(text)
        project.setEnabled(True)

    def do_project():
        pref.setText(current["ref"])
        ptext.setText(current["text"])
        proj.show()
        proj.raise_()
        screens = app.screens()
        if len(screens) > 1:
            proj.windowHandle().setScreen(screens[1])
            proj.showFullScreen()
        status.setText("Projected. Projection window is open.")

    find.clicked.connect(do_lookup)
    box.returnPressed.connect(do_lookup)
    project.clicked.connect(do_project)
    win.resize(640, 420)
    win.show()
    do_lookup()
    if "--smoke" in sys.argv:  # opens, looks up, projects, prints memory, exits
        do_project()
        QtCore.QTimer.singleShot(1500, lambda: (print(report_memory()), app.quit()))
    sys.exit(app.exec_())


def report_memory():
    try:
        import resource  # Linux/mac
        mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    except ImportError:  # Windows: use ctypes, no extra packages
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
        mb = pmc.PeakWorkingSetSize / 1048576
    return f"peak memory: {mb:.0f} MB"


if __name__ == "__main__":
    main()
