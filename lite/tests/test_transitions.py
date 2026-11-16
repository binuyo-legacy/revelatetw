"""Transition tests. Headless: pure helpers plus offscreen Qt. They check choice, duration, direction,
settings persistence and the safety rules. They CANNOT show that the animation looks smooth on a real
Windows 8.1 PC or projector. Run: python -m pytest lite/tests/test_transitions.py"""
import json
import os
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from revelatelite import settings, transitions as T
try:
    from PyQt5 import QtWidgets, QtTest
    from revelatelite import app as lite_app
except ImportError:  # pragma: no cover
    QtWidgets = None


class Pure(unittest.TestCase):
    def test_at_least_five_distinct_animated_effects(self):
        animated = [k for k in T.EFFECT_KEYS if k != "cut"]
        self.assertGreaterEqual(len(animated), 5)
        self.assertEqual(len(set(T.EFFECT_KEYS)), len(T.EFFECT_KEYS))
        for k, label, desc in T.EFFECTS:
            self.assertTrue(label and desc)
            self.assertEqual(T.describe(k), desc)

    def test_defaults_and_cleaning(self):
        c = T.clean({})
        self.assertEqual((c["transition_effect"], c["transition_ms"], c["transition_dir"]), ("dissolve", 400, "auto"))
        c = T.clean({"transition_effect": "spin", "transition_ms": "abc", "transition_dir": "x"})
        self.assertEqual((c["transition_effect"], c["transition_ms"], c["transition_dir"]), ("dissolve", 400, "auto"))
        self.assertEqual(T.clean({"transition_ms": 99999})["transition_ms"], T.MS_MAX)
        self.assertEqual(T.clean({"transition_ms": -5})["transition_ms"], 0)

    def test_plan_instant_fallbacks(self):
        st = {"transition_effect": "wipe", "transition_ms": 500}
        self.assertTrue(T.plan(T.ON, st).animated)
        self.assertFalse(T.plan(T.ON, dict(st, transition_ms=0)).animated)
        self.assertFalse(T.plan(T.ON, dict(st, transition_effect="cut")).animated)
        self.assertFalse(T.plan(T.ON, dict(st, transition_onoff=False)).animated)
        self.assertFalse(T.plan(T.OFF, dict(st, transition_onoff=False)).animated)
        self.assertTrue(T.plan(T.SWITCH, dict(st, transition_onoff=False)).animated)
        self.assertFalse(T.plan(T.SWITCH, dict(st, transition_switch=False)).animated)
        self.assertFalse(T.plan(T.SWITCH, st, same_picture=True).animated)
        self.assertEqual(T.plan(T.ON, dict(st, transition_ms=0)).ms, 0)

    def test_every_effect_is_selectable(self):
        for k in T.EFFECT_KEYS:
            p = T.plan(T.SWITCH, {"transition_effect": k, "transition_ms": 300})
            self.assertEqual(p.effect, k if k != "cut" else "cut")
            self.assertEqual(p.animated, k != "cut")

    def test_direction_follows_next_previous(self):
        self.assertEqual(T.resolve_direction("auto", +1), "left")
        self.assertEqual(T.resolve_direction("auto", -1), "right")
        self.assertEqual(T.resolve_direction("auto", 0), "left")
        self.assertEqual(T.resolve_direction("up", -1), "up")
        self.assertEqual(T.plan(T.SWITCH, {"transition_effect": "slide"}, -1).direction, "right")

    def test_fade_and_dissolve(self):
        self.assertEqual(T.fade_alphas(0), (1.0, 0.0))
        self.assertEqual(T.fade_alphas(0.5), (0.0, 0.0))
        self.assertEqual(T.fade_alphas(1), (0.0, 1.0))
        self.assertEqual((T.dissolve_alpha(0), T.dissolve_alpha(1)), (0.0, 1.0))
        self.assertEqual((T.ease(0), T.ease(1)), (0.0, 1.0))

    def test_wipe_slide_open_geometry(self):
        w, h = 1000, 500
        for d in ("left", "right", "up", "down"):
            self.assertEqual(T.wipe_rect(d, w, h, 0)[2] * T.wipe_rect(d, w, h, 0)[3], 0)
            self.assertEqual(T.wipe_rect(d, w, h, 1), (0, 0, w, h))
            self.assertEqual(T.open_rect(d, w, h, 1), (0, 0, w, h))
            self.assertEqual(T.slide_offsets(d, w, h, 1)[1], (0, 0))
            self.assertEqual(T.slide_offsets(d, w, h, 0)[0], (0, 0))
        self.assertEqual(T.wipe_rect("left", w, h, 0.25), (750, 0, 250, h))
        self.assertEqual(T.slide_offsets("left", w, h, 0.5), ((-500, 0), (500, 0)))
        self.assertEqual(T.open_rect("left", w, h, 0.5), (250, 0, 500, h))

    def test_blinds_cover_whole_screen_at_end(self):
        w, h = 800, 400
        for d in ("left", "right", "up", "down"):
            end = T.blinds_rects(d, w, h, 1)
            self.assertEqual(len(end), T.BLIND_COUNT)
            self.assertEqual(sum(r[2] * r[3] for r in end), w * h)
            start = T.blinds_rects(d, w, h, 0)
            self.assertEqual(sum(r[2] * r[3] for r in start), 0)
            mid = sum(r[2] * r[3] for r in T.blinds_rects(d, w, h, 0.5))
            self.assertTrue(0 < mid < w * h)

    def test_settings_roundtrip_and_bad_file(self):
        d = tempfile.mkdtemp()
        path = os.path.join(d, "s.json")
        st = settings.load(path)
        self.assertEqual(st["transition_effect"], "dissolve")
        st.update(transition_effect="blinds", transition_ms=750, transition_dir="up", transition_onoff=False, transition_switch=False)
        settings.save(path, st)
        st2 = settings.load(path)
        self.assertEqual((st2["transition_effect"], st2["transition_ms"], st2["transition_dir"],
                          st2["transition_onoff"], st2["transition_switch"]), ("blinds", 750, "up", False, False))
        with open(path, "w") as f:
            json.dump({"transition_effect": "bogus", "transition_ms": 10 ** 9, "transition_dir": 5}, f)
        st3 = settings.load(path)
        self.assertEqual((st3["transition_effect"], st3["transition_ms"], st3["transition_dir"]), ("dissolve", T.MS_MAX, "auto"))


@unittest.skipIf(QtWidgets is None, "PyQt5 not installed")
class WithQt(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qa = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        cls.qa.setStyleSheet(lite_app.QSS)

    def make(self, **st):
        from revelatelite import paths
        d = tempfile.mkdtemp()
        paths.user_dir = lambda: d
        lite_app.paths.user_dir = lambda: d
        w = lite_app.Main()
        w.st.update(st)
        return w

    def test_settings_tab_choices_persist(self):
        w = self.make()
        w.tfx_cb.setCurrentIndex(w.tfx_cb.findData("slide"))
        w.tms_sp.setValue(650)
        w.tdir_cb.setCurrentIndex(w.tdir_cb.findData("down"))
        w.tonoff_cb.setChecked(False)
        with open(w.settings_path) as f:
            saved = json.load(f)
        self.assertEqual((saved["transition_effect"], saved["transition_ms"], saved["transition_dir"], saved["transition_onoff"]),
                         ("slide", 650, "down", False))
        self.assertFalse(w.proj.isVisible())          # choosing an effect never projects
        w.tfx_cb.setCurrentIndex(w.tfx_cb.findData("cut"))
        self.assertFalse(w.tms_sp.isEnabled())
        w.close()

    def test_zero_duration_is_instant(self):
        w = self.make(transition_effect="wipe", transition_ms=0)
        w.lookup("Rom 8:28")
        w.project()
        self.assertFalse(w.proj.transitioning)
        self.assertTrue(w.proj.isVisible() and w.proj.live)
        w.project_off()
        self.assertFalse(w.proj.transitioning)
        self.assertFalse(w.proj.isVisible())
        w.close()

    def test_every_effect_commits_then_ends_on_final_state(self):
        for eff in T.EFFECT_KEYS:
            w = self.make(transition_effect=eff, proj_on_effect=eff, proj_off_effect=eff, transition_ms=60)
            w.lookup("Rom 8:28")
            w.project()
            self.assertEqual(w.proj.transitioning, eff != "cut")
            self.assertTrue(w.proj.isVisible() and w.proj.live)
            w.proj.finish_transition()
            self.assertFalse(w.proj.transitioning)
            w.lookup("John 3:16")
            w.step(1)
            w.project()                                   # switch while live
            w.proj.finish_transition()
            self.assertIn("John 3:17", w.proj.ref)
            w.project_off()
            if eff != "cut":
                self.assertTrue(w.proj.transitioning)
                self.assertTrue(w.proj.isVisible())       # still fading out
            w.proj.finish_transition()
            self.assertFalse(w.proj.isVisible())
            self.assertFalse(w.proj.live)
            self.assertIn("John 3:17", w.preview.ref)     # operator preview untouched
            w.close()

    def test_animation_really_finishes_by_timer(self):
        w = self.make(transition_effect="dissolve", transition_ms=80)
        w.lookup("Rom 8:28")
        w.project()
        QtTest.QTest.qWait(400)
        self.assertFalse(w.proj.transitioning)
        w.proj.close()
        w.close()

    def test_next_previous_never_project_or_animate(self):
        w = self.make(transition_effect="slide", transition_ms=500)
        w.lookup("John 3:16")
        w.step(1)
        w.step(-1)
        self.assertFalse(w.proj.isVisible())
        self.assertFalse(w.proj.transitioning)
        w.project()
        w.proj.finish_transition()
        before = w.proj.ref
        w.step(1)
        self.assertEqual(w.proj.ref, before)              # screen unchanged until Project
        self.assertFalse(w.proj.transitioning)
        self.assertFalse(w.preview.transitioning if hasattr(w.preview, "transitioning") else False)
        w.proj.close()
        w.close()

    def test_direction_hint_comes_from_next_previous(self):
        w = self.make(transition_effect="slide", transition_ms=500, transition_dir="auto")
        w.lookup("John 3:16")
        w.project()
        w.proj.finish_transition()
        w.step(1)
        self.assertEqual(w._step_hint, 1)
        w.project()
        self.assertEqual(w.proj._tx["direction"], "left")
        w.proj.finish_transition()
        w.step(-1)
        w.project()
        self.assertEqual(w.proj._tx["direction"], "right")
        w.proj.close()
        w.close()

    def test_reprojecting_same_picture_does_not_animate(self):
        w = self.make(transition_effect="fade", transition_ms=500)
        w.lookup("John 3:16")
        w.project()
        w.proj.finish_transition()
        w.project()
        self.assertFalse(w.proj.transitioning)
        w.proj.close()
        w.close()

    def test_disabled_switch_animation_still_animates_on_off(self):
        w = self.make(transition_effect="fade", transition_ms=500, transition_switch=False)
        w.lookup("John 3:16")
        w.project()
        w.proj.finish_transition()
        w.lookup("Rom 8:28")
        w.project()
        self.assertFalse(w.proj.transitioning)
        w.project_off()
        self.assertTrue(w.proj.transitioning)
        w.proj.finish_transition()
        w.close()

    def test_timer_to_existing_verse_animates(self):
        w = self.make(transition_effect="fade", transition_ms=500)
        labels = [w.tabs.tabText(i) for i in range(w.tabs.count())]
        service_idx = labels.index("Service list")
        timer_idx = labels.index("Timer")
        w.lookup("John 3:16")
        # live: verse on screen, then Timer projected over it
        w.project()
        w.proj.finish_transition()
        self.assertIn("John 3:16", w.proj.ref)
        w.tabs.setCurrentIndex(timer_idx)
        self.qa.processEvents()
        w._show_timer_slide()
        w.project()
        w.proj.finish_transition()
        self.qa.processEvents()
        self.assertIsNotNone(w.proj.timer_snap)
        self.assertTrue(w.proj.live)
        # back to Service list WITHOUT changing the verse: preview
        # auto-restores the already-selected verse
        w.tabs.setCurrentIndex(service_idx)
        self.qa.processEvents()
        self.assertIsNone(w.timer_snap)
        self.assertIn("John 3:16", w.preview.ref)
        self.assertEqual(w.preview.body, w.proj.body)
        self.assertEqual(w.preview.ref, w.proj.ref)
        # timer is still ticking live off-tab before F1
        self.assertIsNotNone(w.proj.timer_snap)
        # F1 must animate Timer -> verse, not cut via stale same-picture
        w.project()
        self.assertTrue(w.proj.transitioning, "Timer->verse F1 cut instantly, no transition ran")
        self.assertIsNotNone(w.proj._tx)
        self.assertFalse(w.proj._tx.get("effect") == "cut")
        w.proj.finish_transition()
        self.assertFalse(w.proj.transitioning)
        self.assertIsNone(w.proj.timer_snap)
        self.assertIn("John 3:16", w.proj.ref)
        self.assertTrue(w.proj.live)
        # same-verse reproject with no timer in the way still does not animate
        w.project()
        self.assertFalse(w.proj.transitioning)
        # off-tab ticking is untouched by the fix: still active while live timer
        w.tabs.setCurrentIndex(timer_idx)
        self.qa.processEvents()
        w._show_timer_slide()
        w.project()
        w.proj.finish_transition()
        w.tabs.setCurrentIndex(service_idx)
        self.qa.processEvents()
        self.assertTrue(w._timer_tick.isActive())
        w.close()

    def test_live_badge_not_naive_same_while_timer_live(self):
        w = self.make()
        labels = [w.tabs.tabText(i) for i in range(w.tabs.count())]
        w.lookup("John 3:16")
        w.project()
        w.proj.finish_transition()
        w.tabs.setCurrentIndex(labels.index("Timer"))
        self.qa.processEvents()
        w._show_timer_slide()
        w.project()
        w.proj.finish_transition()
        self.qa.processEvents()
        w.tabs.setCurrentIndex(labels.index("Service list"))
        self.qa.processEvents()
        w._refresh_live_state()
        self.assertEqual(w.live_badge.text(), "LIVE (preview not sent yet)")
        w.close()

    def test_frames_paint_without_error(self):
        w = self.make(transition_effect="blinds", transition_ms=500)
        w.lookup("John 3:16")
        w.project()
        for eff in T.EFFECT_KEYS:
            w.proj._tx = dict(w.proj._tx or {"old": w.proj.snapshot(w.proj.size())}, effect=eff, direction="left", p=0.5,
                              new=w.proj.snapshot(w.proj.size()))
            w.proj.grab()
        w.proj.finish_transition()
        w.proj.close()
        w.close()


if __name__ == "__main__":
    unittest.main()
