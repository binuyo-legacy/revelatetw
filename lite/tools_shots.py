"""Offscreen screenshots of the operator window, one per tab (visual check, not a pass/fail test).
Run: python lite/tools_shots.py [output_folder]"""
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from PyQt5 import QtWidgets  # noqa: E402
from revelatelite import app as lite_app, paths  # noqa: E402


def shoot(out):
    os.makedirs(out, exist_ok=True)
    qa = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    qa.setStyleSheet(lite_app.QSS)
    d = tempfile.mkdtemp()
    paths.user_dir = lambda: d
    lite_app.paths.user_dir = lambda: d
    w = lite_app.Main()
    w.resize(1100, 720)
    w.show()
    w.lookup("John 3:16")
    tabs = w.findChild(QtWidgets.QTabWidget)
    files = []
    for i in range(tabs.count()):
        tabs.setCurrentIndex(i)
        qa.processEvents()
        f = os.path.join(out, "tab%d_%s.png" % (i + 1, tabs.tabText(i).lower().replace(" ", "_")))
        w.grab().save(f)
        files.append(f)
    w.close()
    return files


if __name__ == "__main__":
    for f in shoot(sys.argv[1] if len(sys.argv) > 1 else "shots"):
        print(f)
