"""Timer tab tests. Run: python -m pytest tests/test_timer_tab.py -q"""
import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
try:
    from PyQt5 import QtWidgets
    from revelatelite import app as lite_app
    from revelatelite import timer as tm
    from revelatelite import settings as cfg
except ImportError:
    QtWidgets = None


@unittest.skipIf(QtWidgets is None, "PyQt5 not installed")
class TimerLogic(unittest.TestCase):
    def test_timer_logic(self):
        import datetime as _dt
        dt = _dt.datetime(2026, 11, 15, 11, 8, 30)
        assert tm.format_clock(dt, "24", True) == ("11:08", "")
        assert tm.format_clock(dt, "12", True) == ("11:08", "AM")
        assert tm.format_clock(dt, "12", False, True)[0] == "11:08:30"
        assert tm.format_clock(dt, "24", True, True)[0] == "11:08:30"
        assert tm.format_countdown(300) == "05:00"
        assert tm.format_countdown(3661) == "1:01:01"
        assert tm.format_countdown(-5) == "00:00"
        e = tm.TimerEngine(mode="countdown", duration=120)
        assert e.snapshot()["text"] == "02:00"
        e.start()
        assert e.tick()["remaining"] == 119
        e.pause()
        assert e.tick()["state"] == "PAUSED"
        e.reset()
        assert e.snapshot()["remaining"] == 120
        assert tm.clean_style("weird") == "digital"
        assert tm.clean_style("analog") == "analog"
        s = tm.TimerEngine(mode="clock", style="analog").snapshot(_dt.datetime(2026, 1, 1, 3, 30, 0))
        assert s["style"] == "analog" and s["dial"]["hour"] is not None
        r = tm.resolve("revelate", "#ff0000", "#00ff00")
        assert r["text"] == "#ff0000" and r["bg1"] == "#00ff00"

    def test_settings_defaults(self):
        d = cfg.DEFAULTS
        for k in ("timer_template", "timer_mode", "timer_format", "timer_ampm", "timer_duration", "timer_style", "timer_show_seconds"):
            assert k in d
        loaded = cfg.load("/nonexistent/settings.json")
        assert loaded["timer_style"] == "digital"
        assert loaded["timer_mode"] == "clock"


@unittest.skipIf(QtWidgets is None, "PyQt5 not installed")
class TimerQt(unittest.TestCase):
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
        w = lite_app.Main()
        w.st["transition_ms"] = 0
        return w

    def test_projection_and_app_timer(self):
        from revelatelite.projection import PreviewView
        pv = PreviewView()
        pv.resize(320, 180)
        snap = tm.TimerEngine(mode="clock", fmt="12", show_ampm=True).snapshot()
        pv.show_timer(snap)
        assert pv.timer_snap is not None and pv.live
        pv.show_slide("John 3:16", "For God so loved", "")
        assert pv.timer_snap is None

        w = self.make()
        w.show()
        labels = [w.tabs.tabText(i) for i in range(w.tabs.count())]
        assert "Timer" in labels
        # Timer sits before Settings, as an original new tab
        assert labels.index("Timer") == labels.index("Settings") - 1
        assert hasattr(w, "timer_start_b") and hasattr(w, "timer_pause_b") and hasattr(w, "timer_reset_b")
        timer_idx = labels.index("Timer")
        w.tabs.setCurrentIndex(timer_idx)
        self.qa.processEvents()
        assert w.timer_snap is not None and w.preview.timer_snap is not None
        w.timer_mode_cb.setCurrentIndex(w.timer_mode_cb.findData("countdown"))
        self.qa.processEvents()
        w._on_timer_tick()
        assert w.preview.timer_snap["mode"] == "countdown"
        w.project()
        assert w.proj.timer_snap is not None
        w.close()


if __name__ == "__main__":
    unittest.main()
