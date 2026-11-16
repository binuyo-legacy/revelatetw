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
        e.start(now=100.0)
        assert e.tick(now=101.0)["remaining"] == 119
        e.pause(now=102.0)
        assert e.tick(now=500.0)["remaining"] == 118
        assert e.tick(now=500.0)["state"] == ""
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
        for k in ("timer_template", "timer_mode", "timer_format", "timer_ampm", "timer_duration", "timer_style", "timer_show_seconds",
                    "timer_source", "timer_message", "timer_font_family", "timer_text_color", "timer_bg_color",
                  "timer_manual_hour", "timer_manual_minute", "timer_manual_second",
                  "timer_show_shape", "timer_text_scale"):
            assert k in d
        loaded = cfg.load("/nonexistent/settings.json")
        assert loaded["timer_style"] == "digital"
        assert loaded["timer_mode"] == "time"
        assert loaded["timer_source"] == "live"
        assert loaded["timer_font_family"] == "Segoe UI"
        assert loaded["timer_message"] == ""


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


@unittest.skipIf(QtWidgets is None, "PyQt5 not installed")
class TimerRefinements(unittest.TestCase):
    def test_no_static_labels_or_state_in_any_mode(self):
        import datetime as _dt
        for mode, style in (("time", "digital"), ("time", "analog"), ("countdown", "digital"), ("countdown", "analog")):
            s = tm.TimerEngine(mode=mode, style=style, duration=300, message="Pastor leading prayer").snapshot(_dt.datetime(2026, 1, 1, 10, 0, 0))
            assert s["label"] == "" and s["state"] == "", (mode, style, s)
            assert "CLOCK" not in (s["text"] + s["message"]) and "COUNTDOWN" not in (s["text"] + s["message"])
            assert "RUNNING" not in (s["text"] + s["message"]) and "PAUSED" not in (s["text"] + s["message"])
            assert s["message"] == "Pastor leading prayer"

    def test_message_per_entry_and_cleaning(self):
        e = tm.TimerEngine(mode="countdown", duration=60, message="  Pastor   leading   prayer  ")
        assert e.snapshot()["message"] == "Pastor leading prayer"
        e.configure(message="Closing and benediction")
        assert e.snapshot()["message"] == "Closing and benediction"
        assert len(tm.clean_message("x" * 500)) == tm.MAX_MESSAGE
        s = tm.TimerEngine(mode="time", message="Opening service").snapshot()
        assert s["message"] == "Opening service"

    def test_manual_time_and_clock_alias(self):
        import datetime as _dt
        assert tm.clean_mode("clock") == "time"
        e = tm.TimerEngine(mode="time", source="manual", manual_hour=18, manual_minute=30, manual_second=5, show_seconds=True)
        s = e.snapshot(_dt.datetime(2026, 1, 1, 3, 3, 3))   # live now must be ignored
        assert s["text"] == "18:30:05"
        e.configure(manual_hour=9, manual_minute=0)
        assert e.snapshot()["text"] == "09:00:05"
        assert tm.clamp_time(25, 99, -1) == (23, 59, 0)
        assert tm.clean_source("manual") == "manual" and tm.clean_source("bogus") == "live"

    def test_font_and_colors_flow_to_snapshot_and_resolve(self):
        e = tm.TimerEngine(mode="time", font_family="Georgia", text_color="#FF0000", bg_color="#00FF00")
        s = e.snapshot()
        assert s["font_family"] == "Georgia"
        r = tm.resolve(s["template"], s["text_color"], s["bg_color"])
        assert r["text"] == "#ff0000" and r["bg1"] == "#00ff00"
        assert tm.clean_font("No Such Font") == "Segoe UI"
        assert tm.clean_font("Calibri") == "Calibri"

    def test_message_rect_stays_inside_template_shape(self):
        for w, h in ((1280, 720), (640, 360), (1920, 1080)):
            x, y, rw, rh = tm.inner_rect(w, h)
            assert 0 <= x and 0 <= y and x + rw <= w and y + rh <= h
            assert y >= h * 0.5 and y + rh <= h * 0.98   # inside, clear of outer frame
        # projection draws only the message, never a generic label, even for legacy snaps
        from revelatelite.projection import PreviewView
        pv = PreviewView()
        pv.resize(640, 360)
        legacy = dict(tm.TimerEngine(mode="countdown", duration=60, message="Final prayer").snapshot(),
                      label="COUNTDOWN", state="RUNNING")
        pv.show_timer(legacy)
        assert pv.timer_snap is not None and pv.live


class DigitalLayout(unittest.TestCase):
    """Regression for the digital template layout: the message used to sit at
    74%..84% of the height, so it straddled the plate's bottom edge and the
    gold rule cut through it; the AM/PM marker was placed from the centre
    plus the full text width with no clip, so it could cross the inner curve
    while the falling digits animated."""

    def _inside(self, rect, outer):
        return (rect[0] >= outer[0] - 1e-9 and rect[1] >= outer[1] - 1e-9
                and rect[0] + rect[2] <= outer[0] + outer[2] + 1e-9
                and rect[1] + rect[3] <= outer[1] + outer[3] + 1e-9)

    def test_message_inside_shape_below_digits_clear_of_rule(self):
        for w, h in ((1280, 720), (640, 360), (1920, 1080), (800, 600)):
            for marker in ("", "AM", "PM"):
                lay = tm.digital_layout(w, h, marker=marker, show_shape=True)
                assert self._inside(lay["message_rect"], lay["plate"]), (w, h, marker, lay)
                # below the digit band, with a gap, and above the rule
                tr = lay["time_rect"]
                mr = lay["message_rect"]
                assert mr[1] >= tr[1] + tr[3] - 1e-9, (w, h, marker, lay)
                assert mr[1] + mr[3] <= lay["rule_y"] - 1e-9, (w, h, marker, lay)
                # moved down from the old straddling band (74%..84%)
                assert mr[1] / h >= 0.60 and mr[1] + mr[3] <= h * 0.78, (w, h, lay)

    def test_marker_reserved_inside_plate(self):
        for w, h in ((1280, 720), (1920, 1080)):
            lay = tm.digital_layout(w, h, marker="PM", show_shape=True)
            assert lay["marker_rect"][2] > 0
            assert self._inside(lay["marker_rect"], lay["plate"]), lay
            # no horizontal overlap between the digit band and the marker column
            assert not tm.rects_overlap(lay["time_rect"], lay["marker_rect"]), lay
            # no marker -> empty column, digits keep the full inner width
            lay2 = tm.digital_layout(w, h, marker="", show_shape=True)
            assert lay2["marker_rect"] == (0.0, 0.0, 0.0, 0.0)
            assert lay2["time_rect"][2] > lay["time_rect"][2]

    def test_shape_off_gives_full_width_keeps_message(self):
        w, h = 1280, 720
        lay = tm.digital_layout(w, h, marker="PM", show_shape=False)
        assert lay["show_shape"] is False
        # message may use (almost) the full screen width but stays below digits
        mr, tr = lay["message_rect"], lay["time_rect"]
        assert mr[2] >= w * 0.85, lay
        assert mr[1] >= tr[1] + tr[3] - 1e-9
        assert mr[1] + mr[3] <= h * 0.98

    def test_text_scale_clamped(self):
        assert tm.clean_text_scale(100) == 100
        assert tm.clean_text_scale(0) == tm.TEXT_SCALE_MIN
        assert tm.clean_text_scale(9999) == tm.TEXT_SCALE_MAX
        assert tm.clean_text_scale("150") == 150
        assert tm.clean_text_scale("junk") == tm.TEXT_SCALE_DEFAULT
        e = tm.TimerEngine(text_scale=9999)
        assert e.snapshot()["text_scale"] == tm.TEXT_SCALE_MAX
        e.configure(text_scale=50)
        assert e.snapshot()["text_scale"] == 50

    def test_shape_and_scale_flow_through_engine_and_settings(self):
        e = tm.TimerEngine(show_shape=False, text_scale=180)
        s = e.snapshot()
        assert s["show_shape"] is False and s["text_scale"] == 180
        e.configure(show_shape=True, text_scale=100)
        s = e.snapshot()
        assert s["show_shape"] is True and s["text_scale"] == 100
        loaded = cfg.load("/nonexistent/settings.json")
        assert loaded["timer_show_shape"] is True and loaded["timer_text_scale"] == 100
        # a saved file with the new keys round-trips
        import json
        import tempfile
        p = os.path.join(tempfile.mkdtemp(), "s.json")
        raw = dict(cfg.DEFAULTS, timer_show_shape=False, timer_text_scale=220)
        with open(p, "w") as fh:
            json.dump(raw, fh)
        again = cfg.load(p)
        assert again["timer_show_shape"] is False and again["timer_text_scale"] == 220

    def test_inner_rect_matches_message_band(self):
        for w, h in ((1280, 720), (640, 360)):
            lay = tm.digital_layout(w, h, show_shape=True)
            assert tm.inner_rect(w, h) == lay["message_rect"]


@unittest.skipIf(QtWidgets is None, "PyQt5 not installed")
class DigitalLayoutQt(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qa = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def make(self):
        import tempfile
        from revelatelite import paths
        d = tempfile.mkdtemp()
        paths.user_dir = lambda: d
        lite_app.paths.user_dir = lambda: d
        w = lite_app.Main()
        w.st["transition_ms"] = 0
        return w

    def test_controls_exist_and_wire_to_snapshot(self):
        w = self.make()
        w.show()
        for name in ("timer_shape_cb", "timer_textscale_sp"):
            assert hasattr(w, name), name
        labels = [w.tabs.tabText(i) for i in range(w.tabs.count())]
        w.tabs.setCurrentIndex(labels.index("Timer"))
        self.qa.processEvents()
        w.timer_shape_cb.setChecked(False)
        self.qa.processEvents()
        assert w.st["timer_show_shape"] is False
        assert w.timer.snapshot()["show_shape"] is False
        w.timer_textscale_sp.setValue(200)
        self.qa.processEvents()
        assert w.st["timer_text_scale"] == 200
        assert w.timer.snapshot()["text_scale"] == 200
        w.close()

    def test_projection_paints_with_shape_off_and_marker(self):
        from revelatelite.projection import PreviewView
        import datetime as _dt
        pv = PreviewView()
        pv.resize(640, 360)
        snap = tm.TimerEngine(mode="time", fmt="12", show_ampm=True,
                              message="Pastor leading prayer", show_shape=False,
                              text_scale=180).snapshot(_dt.datetime(2026, 1, 1, 10, 5, 0))
        pv.show_timer(snap)
        assert pv.timer_snap is not None and pv.live
        # a falling-digit animation frame must not raise either
        pv._fall_frames = tm.falling_centers("10:05", "10:06", 120)
        pv.repaint()
        self.qa.processEvents()
        pv._fall_frames = None
        pv.show_slide("John 3:16", "For God so loved", "")
        assert pv.timer_snap is None


@unittest.skipIf(QtWidgets is None, "PyQt5 not installed")
class TimerTabSwitchKeepsTicking(unittest.TestCase):
    """Regression: switching off the Timer tab used to stop the tick, so the
    live projector froze until the operator came back. A timer/timer clock
    that is on the projector must keep updating on every tick, off-tab."""

    @classmethod
    def setUpClass(cls):
        cls.qa = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def make(self):
        import tempfile
        from revelatelite import paths
        d = tempfile.mkdtemp()
        paths.user_dir = lambda: d
        lite_app.paths.user_dir = lambda: d
        w = lite_app.Main()
        w.st["transition_ms"] = 0
        return w

    def test_projected_countdown_keeps_ticking_off_timer_tab(self):
        fake = [8000.0]
        w = self.make()
        w.timer._clock = lambda: fake[0]
        w.show()
        labels = [w.tabs.tabText(i) for i in range(w.tabs.count())]
        w.tabs.setCurrentIndex(labels.index("Timer"))
        self.qa.processEvents()
        w.timer_mode_cb.setCurrentIndex(w.timer_mode_cb.findData("countdown"))
        self.qa.processEvents()
        w.timer.start()
        w._show_timer_slide()
        w.project()
        self.qa.processEvents()
        assert w.proj.timer_snap is not None and w.proj.live and w._timer_live
        before = w.proj.timer_snap["remaining"]
        # switch away to another tab (Songs/Bible side): preview returns to
        # the verse/song slide, but the tick must stay alive off-tab.
        other = next(i for i, t in enumerate(labels) if t != "Timer")
        w.tabs.setCurrentIndex(other)
        self.qa.processEvents()
        assert not w._timer_showing
        assert w._timer_tick.isActive(), "tick stopped when leaving the Timer tab"
        # the engine runs on its deadline, not on tick count: a tick with no
        # elapsed time must not move the value, and time passing while a
        # verse/song is on air must be counted in full
        w._on_timer_tick()
        assert w.proj.timer_snap["remaining"] == before, w.proj.timer_snap
        fake[0] += 2.0
        w._on_timer_tick()
        after = w.proj.timer_snap["remaining"]
        assert after == before - 2, (before, after)
        assert w.timer_snap is None  # preview is the verse/song slide again
        assert w.preview.timer_snap is None
        # back on the Timer tab the preview shows the live timer again
        w.tabs.setCurrentIndex(labels.index("Timer"))
        self.qa.processEvents()
        assert w._timer_showing and w.preview.timer_snap is not None
        assert w.preview.timer_snap["remaining"] == after
        w.close()

    def test_projected_clock_keeps_ticking_off_timer_tab(self):
        w = self.make()
        w.show()
        labels = [w.tabs.tabText(i) for i in range(w.tabs.count())]
        w.tabs.setCurrentIndex(labels.index("Timer"))
        self.qa.processEvents()
        w.timer_mode_cb.setCurrentIndex(w.timer_mode_cb.findData("time"))
        w.timer_style_cb.setCurrentIndex(w.timer_style_cb.findData("analog"))
        self.qa.processEvents()
        w._show_timer_slide()
        w.project()
        self.qa.processEvents()
        assert w.proj.timer_snap is not None and w._timer_live
        before = dict(w.proj.timer_snap["dial"])
        other = next(i for i, t in enumerate(labels) if t != "Timer")
        w.tabs.setCurrentIndex(other)
        self.qa.processEvents()
        assert w._timer_tick.isActive()
        w._on_timer_tick()
        assert w.proj.timer_snap["dial"] is not None
        assert w.proj.timer_snap["mode"] == "time"
        # dial seconds must have advanced (engine ticked, not frozen)
        assert w.proj.timer_snap["dial"]["second"] != before["second"] or \
               w.timer.snapshot()["dial"]["second"] is not None
        w.close()

    def test_unprojected_idle_timer_still_stops_off_tab(self):
        # an idle (not running, not projected) timer has nothing to keep
        # ticking off-tab, so the beat stops as before
        w = self.make()
        w.show()
        labels = [w.tabs.tabText(i) for i in range(w.tabs.count())]
        w.tabs.setCurrentIndex(labels.index("Timer"))
        self.qa.processEvents()
        assert w._timer_tick.isActive()
        other = next(i for i, t in enumerate(labels) if t != "Timer")
        w.tabs.setCurrentIndex(other)
        self.qa.processEvents()
        assert not w._timer_tick.isActive()
        assert not w._timer_live
        w.close()

    def test_unprojected_running_countdown_keeps_ticking_off_tab(self):
        # a running countdown is a live engine even with nothing projected:
        # it must keep its deadline (and the refresh beat) off the Timer tab
        w = self.make()
        w.show()
        labels = [w.tabs.tabText(i) for i in range(w.tabs.count())]
        w.tabs.setCurrentIndex(labels.index("Timer"))
        self.qa.processEvents()
        w.timer_mode_cb.setCurrentIndex(w.timer_mode_cb.findData("countdown"))
        self.qa.processEvents()
        w.timer.start()
        other = next(i for i, t in enumerate(labels) if t != "Timer")
        w.tabs.setCurrentIndex(other)
        self.qa.processEvents()
        assert w.timer.running
        assert w._timer_tick.isActive(), "running countdown stopped ticking off-tab"
        w.timer.pause()
        w._timer_tick_sync()
        assert not w._timer_tick.isActive()
        w.close()


if __name__ == "__main__":
    unittest.main()

@unittest.skipIf(QtWidgets is None, "PyQt5 not installed")
class TimerReportedFixes(unittest.TestCase):
    def test_background_color_tuple_and_keys_agree(self):
        # Regression: resolve() used to set bg_kind/bg1/bg2 but leave the legacy
        # "bg" tuple at the template navy, so a picked colour never painted.
        r = tm.resolve("revelate", "", "#00FF00")
        assert r["bg"] == ("solid", "#00ff00", "#00ff00"), r
        assert r["bg_kind"] == "solid" and r["bg1"] == "#00ff00" and r["bg2"] == "#00ff00"
        # every template: picked colour wins over the all keys
        for k in tm.KEYS:
            rr = tm.resolve(k, "", "#123456")
            assert rr["bg"] == ("solid", "#123456", "#123456"), (k, rr)
            assert rr["bg1"] == "#123456"
        # no pick -> template tuple untouched
        assert tm.resolve("revelate")["bg"] == ("solid", "#0b0f19", "#0b0f19")
        # snapshot carries it through to the renderer
        e = tm.TimerEngine(bg_color="#ABCDEF")
        s = e.snapshot()
        rr = tm.resolve(s["template"], s["text_color"], s["bg_color"])
        assert rr["bg"] == ("solid", "#abcdef", "#abcdef")

    def test_background_color_persists_through_settings(self):
        import json, tempfile
        p = tempfile.mktemp(suffix=".json")
        d = dict(cfg.DEFAULTS, timer_bg_color="#00ff00", timer_text_color="#ff0000")
        cfg.save(p, d)
        loaded = cfg.load(p)
        assert loaded["timer_bg_color"] == "#00ff00" and loaded["timer_text_color"] == "#ff0000"
        rr = tm.resolve(loaded["timer_template"], loaded["timer_text_color"], loaded["timer_bg_color"])
        assert rr["bg"] == ("solid", "#00ff00", "#00ff00")

    def test_analog_clock_positions_clockwise(self):
        import datetime as _dt
        # 3:00:00 -> hour=3 (pointing at 3), minute=0 (up), second=0 (up)
        s = tm.TimerEngine(mode="time", style="analog").snapshot(_dt.datetime(2026, 1, 1, 3, 0, 0))
        d = s["dial"]
        assert abs(d["hour"] - 3.0) < 1e-6 and d["minute"] == 0 and d["second"] == 0, d
        # 12:00:00 -> everything up (0/12/0)
        s = tm.TimerEngine(mode="time", style="analog").snapshot(_dt.datetime(2026, 1, 1, 12, 0, 0))
        d = s["dial"]
        assert d["hour"] == 0 and d["minute"] == 0 and d["second"] == 0, d
        # 6:30:00 -> hour halfway between 6 and 7 = 6.5, minute at 6 (=30)
        s = tm.TimerEngine(mode="time", style="analog").snapshot(_dt.datetime(2026, 1, 1, 6, 30, 0))
        d = s["dial"]
        assert abs(d["hour"] - 6.5) < 1e-6 and d["minute"] == 30, d
        # 11:08:30
        s = tm.TimerEngine(mode="time", style="analog").snapshot(_dt.datetime(2026, 11, 15, 11, 8, 30))
        d = s["dial"]
        assert abs(d["hour"] - (11 + 8/60.0 + 30/3600.0)) < 1e-6
        assert abs(d["minute"] - (8 + 30/60.0)) < 1e-6 and abs(d["second"] - 30) < 1e-6

    def test_analog_countdown_moves_clockwise_and_shows_remaining(self):
        e = tm.TimerEngine(mode="countdown", style="analog", duration=600)
        s0 = e.snapshot()
        e.start(now=100.0)
        e.tick(now=101.0)  # 1s elapsed
        s1 = e.tick(now=101.0)
        d0, d1 = s0["dial"], s1["dial"]
        # elapsed grows, so hands advance clockwise (larger values), never back
        assert d1["elapsed"] > d0["elapsed"]
        assert d1["second"] > d0["second"]  # sweeps forward
        assert d1["minute"] > d0["minute"] or d1["second"] > d0["second"]
        # remaining digits count DOWN
        assert s1["remaining"] < s0["remaining"]
        assert d1["remaining"] < d0["remaining"]
        assert d1["fraction"] < d0["fraction"]
        # fraction starts at 1 and decays to 0
        assert abs(s0["dial"]["fraction"] - 1.0) < 1e-9
        e.remaining = 0.0
        e.running = False
        e.finished = True
        s_end = e.snapshot()
        assert s_end["dial"]["fraction"] == 0.0 and s_end["text"] == "00:00"

    def test_analog_three_hands_in_snapshot(self):
        e = tm.TimerEngine(mode="time", style="analog", show_seconds=False)
        d = e.snapshot()["dial"]
        assert {"hour", "minute", "second"} <= set(d), d
        e2 = tm.TimerEngine(mode="countdown", style="analog", duration=120)
        d2 = e2.snapshot()["dial"]
        assert {"hour", "minute", "second", "elapsed", "remaining", "fraction"} <= set(d2), d2

    def test_falling_animation_frames(self):
        # settled: no offsets
        frames = tm.falling_centers("11:08", "11:09", tm.FALL_DURATION_MS)
        assert all(off == 0.0 and ooff == 0.0 for _n, _o, off, ooff in frames), frames
        assert [n for n, _o, _off, _ooff in frames] == list("11:09")
        # mid-fall: changed column is above its slot (negative), unchanged stay 0
        frames = tm.falling_centers("11:08", "11:09", 50)
        assert frames[-1][2] < 0 and frames[-1][0] == "9" and frames[-1][1] == "8", frames
        assert frames[0][2] == 0.0 and frames[2][2] == 0.0, frames
        # still moving at 300ms, settled by 350ms
        assert any(off != 0.0 for _n, _o, off, _ooff in tm.falling_centers("11:08", "11:09", 300))
        # deterministic
        assert tm.falling_centers("11:08", "11:09", 100) == tm.falling_centers("11:08", "11:09", 100)
        # digit-change detection: only real digits count
        assert tm.digit_changed("11:08", "11:09")
        assert not tm.digit_changed("11:08", "11:08")
        assert tm.digit_changed("59", "60")

    _SAMPLES = (0, 1, 50, 100, 175, 250, 300, 330, 349, 350)
    # video-reported clipping: second / minute / hour digit rolls, plus
    # multi-position changes (minute+second on a minute roll, hour change)
    _TRANSITIONS = (
        ("43:36", "43:35"),      # seconds, last digit (video case)
        ("43:30", "43:29"),      # seconds roll, two positions
        ("01:00", "00:59"),      # minute + second roll
        ("10:00", "09:59"),
        ("1:00:00", "0:59:59"),  # hour + minute + second roll
        ("11:08", "11:09"),
        ("09:59", "10:00"),
        ("2:59:59", "3:00:00"),
    )

    def test_falling_new_glyph_never_goes_below_slot(self):
        # the reported bug: the drawn (new) glyph was carried past its slot
        # to nearly +1.1 digit heights, clipping its lower leg under the row
        for old, new in self._TRANSITIONS:
            for ms in self._SAMPLES:
                frames = tm.falling_centers(old, new, ms)
                assert len(frames) == len(new), (old, new, ms, frames)
                for nw, o, off, ooff in frames:
                    assert off <= 1e-9, (old, new, ms, frames)
                    assert off >= tm.FALL_NEW_MIN - 1e-9, (old, new, ms, frames)
                    assert ooff >= -1e-9, (old, new, ms, frames)
                    assert ooff <= tm.FALL_OLD_MAX + 1e-9, (old, new, ms, frames)
                    if old and o == nw:
                        assert off == 0.0 and ooff == 0.0, (old, new, ms, frames)

    def test_falling_bottom_extent_is_bounded(self):
        # at every sample, every glyph's bottom edge (centre + half height +
        # offset) stays within [slot_top - travel, slot_bottom + travel]
        for old, new in self._TRANSITIONS:
            for ms in self._SAMPLES:
                for _nw, _o, off, ooff in tm.falling_centers(old, new, ms):
                    for o in (off, ooff):
                        assert -0.5 - tm.FALL_TRAVEL_FRAC - 1e-9 <= o <= 0.5 + tm.FALL_TRAVEL_FRAC + 1e-9, (old, new, ms, o)

    def test_falling_start_mid_end(self):
        old, new = "43:36", "43:35"
        start = tm.falling_centers(old, new, 0)
        assert start[-1][2] == tm.FALL_NEW_MIN and start[-1][3] == 0.0, start
        mid = tm.falling_centers(old, new, 175)
        assert tm.FALL_NEW_MIN < mid[-1][2] < 0.0, mid
        assert 0.0 < mid[-1][3] < tm.FALL_OLD_MAX, mid
        near = tm.falling_centers(old, new, 349)
        assert -0.01 < near[-1][2] <= 0.0, near
        end = tm.falling_centers(old, new, tm.FALL_DURATION_MS)
        assert all(off == 0.0 and ooff == 0.0 for _n, _o, off, ooff in end), end
        assert [n for n, _o, _off, _ooff in end] == list(new)

    def test_falling_monotonic_no_snap(self):
        for old, new in self._TRANSITIONS:
            prev = None
            for ms in range(0, tm.FALL_DURATION_MS, 10):
                f = tm.falling_centers(old, new, ms)
                if prev is not None:
                    for (nw, o, off, ooff), (pn, po, poff, pooff) in zip(f, prev):
                        assert off >= poff - 1e-9, (old, new, ms, f)
                        assert ooff >= pooff - 1e-9, (old, new, ms, f)
                prev = f
            end = tm.falling_centers(old, new, tm.FALL_DURATION_MS)
            assert all(off == 0.0 and ooff == 0.0 for _n, _o, off, ooff in end)

    def test_falling_non_digits_and_unchanged_stay_put(self):
        for ms in self._SAMPLES:
            f = tm.falling_centers("11:08", "11:09", ms)
            assert f[2][2] == 0.0 and f[2][3] == 0.0, (ms, f)
            assert all(fr[2] == 0.0 and fr[3] == 0.0 for fr in f[:4]), (ms, f)

    def test_falling_render_bottom_extent(self):
        # offscreen render: at start/mid/near-end the new glyph never paints
        # below the digit slot bottom; the old glyph is clipped at it
        from revelatelite.projection import PreviewView
        import PyQt5.QtGui as QtGui
        pv = PreviewView()
        pv.resize(640, 360)
        e = tm.TimerEngine(mode="countdown", duration=60)
        pv.show_timer(e.snapshot())
        pv._fall_frames = tm.falling_centers("00:59", "00:58", 300)
        pv._fall_prev_text = "00:58"
        pv.update()
        self.qa.processEvents() if hasattr(self, "qa") else None
        # model-level: new glyph bottom edge <= slot bottom at all samples
        for ms in self._SAMPLES:
            for _nw, _o, off, _ooff in tm.falling_centers("00:59", "00:58", ms):
                assert off <= 0.0, ms
        # render must not raise and must produce a frame
        img = QtGui.QImage(640, 360, QtGui.QImage.Format.Format_RGB32)
        pv.render(QtGui.QPainter(img))
        assert not img.isNull()
        pv._fall_frames = None
        pv.close()

    def test_projection_falling_integration(self):
        from revelatelite.projection import PreviewView
        pv = PreviewView()
        pv.resize(320, 180)
        e = tm.TimerEngine(mode="countdown", duration=60)
        s0 = e.snapshot()
        pv.show_timer(s0)
        assert pv.timer_snap is not None
        e.start(now=100.0)
        s1 = e.tick(now=101.0)  # 01:00 -> 00:59, digits change
        pv.show_timer(s1)
        # a fall was begun (frames present or timer running)
        assert pv._fall_timer.isActive() or pv._fall_frames is not None
        # analog snapshots do not trigger digit fall
        e2 = tm.TimerEngine(mode="countdown", style="analog", duration=60)
        pv.show_timer(e2.snapshot())
        assert pv._fall_frames is None or not pv._fall_timer.isActive()


@unittest.skipIf(QtWidgets is None, "PyQt5 not installed")
class AnalogLayoutSafety(unittest.TestCase):
    """Regression for the photo: remaining digits and message must not
    collide with the dial numerals/hands/ring (feedback after 25f495a)."""

    SIZES = ((1280, 720), (1920, 1080), (640, 360), (320, 180), (800, 600), (1024, 768), (384, 216), (1366, 768))
    MESSAGES = ("", "Prayer Time Limit", "A" * 120, "Prayer and intercession for the nations of the world today")

    def test_dial_digits_message_never_overlap(self):
        for w, h in self.SIZES:
            for msg in self.MESSAGES:
                lay = tm.analog_layout(w, h, has_subtext=bool(msg))
                cx, cy, r, arc_r = lay["cx"], lay["cy"], lay["r"], lay["arc_r"]
                dial_bbox = (cx - r, cy - r, r * 2, r * 2)
                arc_bbox = (cx - arc_r, cy - arc_r, arc_r * 2, arc_r * 2)
                digits = lay["digits_rect"]
                message = lay["message_rect"]
                # dial + full arc sit strictly above digits
                assert cy + arc_r <= digits[1] + 1e-6, (w, h, lay)
                assert not tm.rects_overlap(dial_bbox, digits), (w, h, lay)
                assert not tm.rects_overlap(arc_bbox, digits), (w, h, lay)
                # digits and message occupy distinct bands
                if msg:
                    assert not tm.rects_overlap(digits, message), (w, h, lay)
                    assert digits[1] + digits[3] <= message[1] + 1e-6, (w, h, lay)
                    # message stays on-screen and inside the card frame when present
                    assert message[1] + message[3] <= h * 0.985, (w, h, lay)
                # dial top stays inside the screen and above digits
                assert cy - r >= 0, (w, h, lay)
                # numerals drawn at 0.82r with 0.24r/0.16r boxes stay inside dial band
                # and below them nothing of the face is under digits: digits start after arc.
                # dial face must be at least 35% of height and not swallow the lower bands
                assert r * 2 < h * 0.62, (w, h, lay)
                assert lay["digits_rect"][1] + lay["digits_rect"][3] <= h, (w, h, lay)

    def test_layout_is_sane_for_edge_sizes(self):
        # zero size does not raise
        lay = tm.analog_layout(0, 0)
        assert lay["r"] == 0.0 and lay["digits_rect"][2] == 0.0
        # tiny offscreen preview still keeps dial above digits
        lay = tm.analog_layout(320, 180)
        assert lay["cy"] + lay["arc_r"] <= lay["digits_rect"][1]

    def test_analog_render_smoke_long_message_all_sizes(self):
        from PyQt5 import QtCore, QtGui
        from revelatelite.projection import SlideView
        for w, h in self.SIZES:
            for msg in self.MESSAGES:
                v = SlideView()
                v.resize(w, h)
                snap = tm.TimerEngine(
                    mode="countdown", style="analog", duration=300,
                    message=msg, template="signal").snapshot()
                # photo case: Prayer Time Limit with 02:25 remaining
                if msg == "Prayer Time Limit":
                    snap["text"] = "02:25"
                v.set_timer(snap)
                ppm = v.snapshot(QtCore.QSize(w, h))
                self.assertFalse(ppm.isNull(), (w, h, msg))
                # geometry must keep digits/message clear of dial for this snap too
                lay = tm.analog_layout(w, h, has_subtext=bool(msg))
                assert not tm.rects_overlap(
                    (lay["cx"] - lay["r"], lay["cy"] - lay["r"], lay["r"] * 2, lay["r"] * 2),
                    lay["digits_rect"]), (w, h, msg, lay)

    def test_digital_unaffected_by_analog_geometry(self):
        # digital snapshots still carry no dial and render without error
        from revelatelite.projection import PreviewView
        pv = PreviewView()
        pv.resize(640, 360)
        snap = tm.TimerEngine(mode="countdown", duration=60, message="Prayer Time Limit").snapshot()
        assert snap["dial"] is None
        pv.show_timer(snap)
        assert pv.timer_snap is not None

    def test_analog_time_readout_combines_text_and_marker(self):
        # 12h: text + marker; 24h: text only; legacy snapshots without a
        # marker still show the bare time instead of nothing.
        assert tm.analog_time_readout("5:04", "PM") == "5:04 PM"
        assert tm.analog_time_readout("5:04", "am") == "5:04 AM"
        assert tm.analog_time_readout("17:04", "") == "17:04"
        assert tm.analog_time_readout("17:04", None) == "17:04"
        assert tm.analog_time_readout("5:04:30", "PM") == "5:04:30 PM"
        assert tm.analog_time_readout("", "") == ""
        assert tm.analog_time_readout("  5:04 ", " pm ") == "5:04 PM"

    def test_analog_time_snapshot_feeds_readout(self):
        # every analog time snapshot must carry text+marker the readout needs
        import datetime as _dt
        s = tm.TimerEngine(mode="time", style="analog", fmt="12", show_ampm=True,
                           message="Prayer Time Limit").snapshot(_dt.datetime(2026, 11, 15, 17, 4, 0))
        assert tm.analog_time_readout(s["text"], s["marker"]) == "5:04 PM"
        assert s["dial"] is not None and s["message"] == "Prayer Time Limit"
        s24 = tm.TimerEngine(mode="time", style="analog", fmt="24",
                             message="Prayer Time Limit").snapshot(_dt.datetime(2026, 11, 15, 17, 4, 0))
        assert tm.analog_time_readout(s24["text"], s24["marker"]) == "17:04"

    def test_analog_time_readout_band_stays_clear(self):
        # the readout lives in digits_rect: below dial+arc, above message,
        # inside the frame, at every aspect size the projection uses
        from revelatelite.projection import SlideView
        from PyQt5 import QtCore
        for w, h in self.SIZES:
            for msg in self.MESSAGES:
                # full 12h-with-seconds string is the longest readout possible
                readout = tm.analog_time_readout("11:59:59", "PM")
                assert readout == "11:59:59 PM"
                lay = tm.analog_layout(w, h, has_subtext=bool(msg))
                digits, message = lay["digits_rect"], lay["message_rect"]
                assert lay["cy"] + lay["arc_r"] <= digits[1] + 1e-6, (w, h, lay)
                assert not tm.rects_overlap((lay["cx"] - lay["r"], lay["cy"] - lay["r"],
                                             lay["r"] * 2, lay["r"] * 2), digits), (w, h, lay)
                if msg:
                    assert not tm.rects_overlap(digits, message), (w, h, msg, lay)
                    assert digits[1] + digits[3] <= message[1] + 1e-6, (w, h, msg, lay)
                    assert message[1] + message[3] <= h * 0.985, (w, h, msg, lay)
                v = SlideView()
                v.resize(w, h)
                snap = tm.TimerEngine(mode="time", style="analog", fmt="12", show_ampm=True,
                                      show_seconds=True, message=msg).snapshot()
                v.set_timer(snap)
                self.assertFalse(v.snapshot(QtCore.QSize(w, h)).isNull(), (w, h, msg))

    def test_analog_time_render_not_marker_only(self):
        # smoke: analog time at the photo case renders with the full readout
        # band occupied (not empty like the old marker-only 24h case)
        from PyQt5 import QtCore
        from revelatelite.projection import SlideView
        v = SlideView()
        v.resize(1280, 720)
        snap = tm.TimerEngine(mode="time", style="analog", fmt="12", show_ampm=True,
                              message="Prayer Time Limit").snapshot()
        snap["text"], snap["marker"] = "5:04", "PM"
        v.set_timer(snap)
        self.assertFalse(v.snapshot(QtCore.QSize(1280, 720)).isNull())


# ---- falling-digit geometry regression (clipping fix) ----
def test_falling_new_glyph_never_below_slot():
    from revelatelite.timer import falling_centers, FALL_NEW_MIN
    for old, new in [("43:36", "43:35"), ("00:00", "00:01"),
                     ("59:59", "00:00"), ("99:59", "00:00")]:
        for t in range(0, 354, 7):
            for nw, o, new_off, old_off in falling_centers(old, new, t):
                assert new_off <= 0.0, (old, new, t, new_off)
                assert new_off >= FALL_NEW_MIN

def test_falling_old_glyph_bounded_and_settled():
    from revelatelite.timer import falling_centers, FALL_OLD_MAX, FALL_DURATION_MS
    for old, new in [("43:36", "43:35"), ("59:59", "00:00")]:
        for t in range(0, 354, 7):
            for nw, o, new_off, old_off in falling_centers(old, new, t):
                assert 0.0 <= old_off <= FALL_OLD_MAX
        end = falling_centers(old, new, FALL_DURATION_MS)
        assert all(no == 0.0 and oo == 0.0 for _nw, _o, no, oo in end)

def test_falling_each_digit_position_animated():
    from revelatelite.timer import falling_centers
    # seconds: only last column moves; minute: tens-of-minutes column moves
    frames = falling_centers("43:39", "43:40", 175)
    moved = [i for i, (nw, o, no, oo) in enumerate(frames) if no != 0.0 or oo != 0.0]
    assert moved, "expected at least one changed column mid-fall"
    frames = falling_centers("59:59", "00:00", 175)
    moved = [i for i, (nw, o, no, oo) in enumerate(frames) if no != 0.0 or oo != 0.0]
    assert len(moved) >= 2

def test_falling_bottom_extent_is_slot_for_new_glyph():
    # the new glyph's cell bottom never exceeds the row bottom slot line
    from revelatelite.timer import falling_centers, FALL_NEW_MIN
    digit_h = 100.0
    slot_top = 0.0
    slot_bottom = digit_h
    for t in range(0, 354, 7):
        for nw, o, new_off, old_off in falling_centers("43:36", "43:35", t):
            assert slot_top + (1.0 + new_off) * digit_h <= slot_bottom + 1e-9
            assert slot_top + (1.0 + old_off) * digit_h <= slot_bottom + FALL_NEW_MIN * -1 * digit_h + 1e-9


@unittest.skipIf(QtWidgets is None, "PyQt5 not installed")
class TimerContinuesUnderOtherProjection(unittest.TestCase):
    """Regression: projecting Bible verses or songs while a countdown ran
    used to freeze it. The engine now has a monotonic deadline independent
    of tab selection and of the shared projector's current content, so all
    elapsed time counts and the value on return is correct. A fake clock
    makes every step deterministic."""

    @classmethod
    def setUpClass(cls):
        cls.qa = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def make(self, fake):
        import tempfile
        from revelatelite import paths
        d = tempfile.mkdtemp()
        paths.user_dir = lambda: d
        lite_app.paths.user_dir = lambda: d
        w = lite_app.Main()
        w.st["transition_ms"] = 0
        w.timer._clock = lambda: fake[0]
        return w

    def _goto(self, w, labels, name):
        w.tabs.setCurrentIndex(labels.index(name))
        self.qa.processEvents()

    def test_engine_counts_all_time_with_no_ticks_at_all(self):
        fake = [1000.0]
        e = tm.TimerEngine(mode="countdown", duration=300, clock=lambda: fake[0])
        e.start()
        # no tick() calls at all for a long stretch: time must still elapse
        fake[0] += 90.0
        snap = e.snapshot()
        assert snap["remaining"] == 210, snap
        assert e.elapsed() == 90.0
        assert snap["text"] == "03:30"
        # ...and past the end it finishes instead of going negative
        fake[0] += 400.0
        snap = e.snapshot()
        assert snap["remaining"] == 0 and snap["text"] == "00:00"
        assert e.finished and not e.running

    def test_engine_pause_freezes_deadline_across_long_gap(self):
        fake = [0.0]
        e = tm.TimerEngine(mode="countdown", duration=120, clock=lambda: fake[0])
        e.start()
        fake[0] = 30.0
        e.pause()
        assert e.remaining == 90.0
        fake[0] = 9999.0
        assert e.snapshot()["remaining"] == 90
        e.start()
        fake[0] = 10000.0
        assert e.tick()["remaining"] == 89

    def test_live_clock_snapshot_is_current_after_time_away(self):
        import datetime as _dt
        e = tm.TimerEngine(mode="time", source="live")
        # live time is read at snapshot time, not cached at start
        assert e.snapshot(_dt.datetime(2026, 11, 15, 10, 15, 0))["text"] == "10:15"
        assert e.snapshot(_dt.datetime(2026, 11, 15, 12, 45, 0))["text"] == "12:45"
        m = tm.TimerEngine(mode="time", source="manual", manual_hour=9, manual_minute=30)
        assert m.snapshot(_dt.datetime(2026, 11, 15, 23, 59, 0))["text"] == "09:30"

    def test_countdown_survives_projecting_a_verse_then_returns(self):
        fake = [5000.0]
        w = self.make(fake)
        w.show()
        labels = [w.tabs.tabText(i) for i in range(w.tabs.count())]
        self._goto(w, labels, "Timer")
        w.timer_mode_cb.setCurrentIndex(w.timer_mode_cb.findData("countdown"))
        self.qa.processEvents()
        w.timer.configure(duration=300)
        w._timer_start()
        fake[0] += 5.0
        w.project()
        self.qa.processEvents()
        assert w.proj.timer_snap is not None and w._timer_live
        assert w.proj.timer_snap["remaining"] == 295

        # go to the Service list and project a verse instead
        self._goto(w, labels, "Service list")
        w.slide = ("John 3:16", "For God so loved the world", "")
        w.slide_meta = None
        w.project()
        self.qa.processEvents()
        assert w.proj.timer_snap is None, "verse should replace the timer on air"
        assert not w._timer_live
        assert w.timer.running, "countdown must keep running under the verse"

        # 120s pass with no return to the Timer tab and no tick at all
        fake[0] += 120.0
        assert w.timer.snapshot()["remaining"] == 175, w.timer.snapshot()
        assert w.timer.elapsed() == 125.0

        # back on Timer the preview already shows the true remaining time
        self._goto(w, labels, "Timer")
        assert w.preview.timer_snap is not None
        assert w.preview.timer_snap["remaining"] == 175
        assert w.preview.timer_snap["text"] == "02:55"

        # re-projecting the timer sends the current value, not the stale one
        w.project()
        self.qa.processEvents()
        assert w.proj.timer_snap is not None and w._timer_live
        assert w.proj.timer_snap["remaining"] == 175
        # and it keeps counting from there
        fake[0] += 10.0
        w._on_timer_tick()
        assert w.proj.timer_snap["remaining"] == 165
        w.close()

    def test_countdown_survives_projecting_a_song(self):
        fake = [7000.0]
        w = self.make(fake)
        w.show()
        labels = [w.tabs.tabText(i) for i in range(w.tabs.count())]
        self._goto(w, labels, "Timer")
        w.timer_mode_cb.setCurrentIndex(w.timer_mode_cb.findData("countdown"))
        self.qa.processEvents()
        w.timer.configure(duration=200)
        w._timer_start()
        fake[0] += 20.0
        # Songs tab: select a song slide and project that instead
        self._goto(w, labels, "Songs")
        w.slide = ("Amazing Grace", "Amazing grace how sweet the sound", "")
        w.slide_meta = {"song": True}
        w.project()
        self.qa.processEvents()
        assert w.proj.timer_snap is None
        fake[0] += 60.0
        self._goto(w, labels, "Timer")
        assert w.preview.timer_snap["remaining"] == 120, w.preview.timer_snap
        w.close()

    def test_live_clock_refreshes_after_other_projection(self):
        fake = [9000.0]
        w = self.make(fake)
        w.show()
        labels = [w.tabs.tabText(i) for i in range(w.tabs.count())]
        self._goto(w, labels, "Timer")
        w.timer_mode_cb.setCurrentIndex(w.timer_mode_cb.findData("time"))
        w.timer_source_cb.setCurrentIndex(w.timer_source_cb.findData("live"))
        self.qa.processEvents()
        w._show_timer_slide()
        first = w.preview.timer_snap["text"]
        self._goto(w, labels, "Service list")
        # off-tab while the clock is not projected: no idle tick, and no
        # stale value is held anywhere (the engine reads the clock live)
        assert not w._timer_tick.isActive()
        w.slide = ("Romans 8:28", "All things work together for good", "")
        w.slide_meta = None
        w.project()
        self.qa.processEvents()
        self._goto(w, labels, "Timer")
        second = w.preview.timer_snap["text"]
        import datetime as _dt
        now_text, _ = tm.format_clock(_dt.datetime.now(), "24", True)
        assert second == now_text, (second, now_text, first)
        w.close()
