"""Live Search-words tests (typing updates matches, debounce, translation, no projecting)."""
import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
try:
    from PyQt5 import QtWidgets, QtTest
    from revelatelite import app as lite_app
except ImportError:  # pragma: no cover
    QtWidgets = None


@unittest.skipIf(QtWidgets is None, "PyQt5 not installed")
class LiveSearch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qa = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        cls.qa.setStyleSheet(lite_app.QSS)

    def make(self):
        import tempfile
        from revelatelite import paths
        d = tempfile.mkdtemp()
        paths.user_dir = lambda: d
        lite_app.paths.user_dir = lambda: d
        return lite_app.Main()

    def wait(self):
        QtTest.QTest.qWait(lite_app.SEARCH_DELAY_MS + 150)

    def test_typing_updates_results_without_enter(self):
        w = self.make()
        self.assertEqual(w.results.count(), 0)
        w.search_box.setText("loved world")
        self.wait()
        self.assertGreater(w.results.count(), 0)
        self.assertIn("John 3:16", w.results.item(0).text() + " ".join(
            w.results.item(i).text() for i in range(w.results.count())))
        first = w.results.count()
        w.search_box.setText("loved world gave")   # narrower query refines the list
        self.wait()
        self.assertLessEqual(w.results.count(), first)
        self.assertGreater(w.results.count(), 0)
        w.close()

    def test_debounce_searches_once_per_pause(self):
        w = self.make()
        calls = []
        real = w.bible.search
        w.bible.search = lambda *a, **k: (calls.append(a[1]), real(*a, **k))[1]
        for q in ("lo", "lov", "love", "loved"):
            w.search_box.setText(q)
        self.assertEqual(calls, [])          # nothing yet: still inside the typing pause
        self.wait()
        self.assertEqual(calls, ["loved"])
        w.close()

    def test_clearing_and_short_query(self):
        w = self.make()
        w.search_box.setText("love")
        self.wait()
        self.assertGreater(w.results.count(), 0)
        w.search_box.setText("")
        self.assertEqual(w.results.count(), 0)   # clears at once, no waiting
        w.search_box.setText("l")
        self.wait()
        self.assertEqual(w.results.count(), 0)
        self.assertIn("Keep typing", w.status.text())
        w.close()

    def test_enter_still_searches_now(self):
        w = self.make()
        w.search_box.setText("loved world")
        w.search_box.returnPressed.emit()
        self.assertGreater(w.results.count(), 0)
        w.close()

    def test_translation_change_refreshes_results(self):
        w = self.make()
        names = [w.trans.itemText(i) for i in range(w.trans.count())]
        self.assertGreater(len(names), 1)
        w.search_box.setText("loved world")
        self.wait()
        w.trans.setCurrentIndex(names.index("KJV") if "KJV" in names else 0)
        a = w.results.item(0).text() if w.results.count() else ""
        w.trans.setCurrentIndex(names.index("WEB") if "WEB" in names else 1)
        b = w.results.item(0).text() if w.results.count() else ""
        self.assertTrue(a and b)
        self.assertNotEqual(a, b)
        w.close()

    def test_typing_never_projects_or_changes_preview(self):
        w = self.make()
        w.lookup("John 3:16")
        before = w.preview.ref
        w.search_box.setText("loved world")
        self.wait()
        self.assertEqual(w.preview.ref, before)
        self.assertFalse(w.proj.isVisible())
        w.results.setCurrentRow(0)
        w.pick_result(w.results.item(0))     # click: preview only
        self.assertFalse(w.proj.isVisible())
        w.close()


if __name__ == "__main__":
    unittest.main()
