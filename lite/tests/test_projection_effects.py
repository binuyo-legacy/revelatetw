"""Separate Projection On / Off effects (offscreen Qt). Run: python -m pytest lite/tests/test_projection_effects.py
Cannot show how the animation looks on a real Windows 8.1 PC or projector."""
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
    from PyQt5 import QtWidgets
    from revelatelite import app as lite_app
except ImportError:  # pragma: no cover
    QtWidgets = None


class Pure(unittest.TestCase):
    def test_on_off_use_own_effect_switch_uses_normal(self):
        st = {"transition_effect": "slide", "proj_on_effect": "iris", "proj_off_effect": "clock", "transition_ms": 300}
        self.assertEqual(T.plan(T.ON, st).effect, "iris")
        self.assertEqual(T.plan(T.OFF, st).effect, "clock")
        self.assertEqual(T.plan(T.SWITCH, st).effect, "slide")

    def test_off_can_be_cut_while_on_animates(self):
        st = {"transition_effect": "fade", "proj_on_effect": "wipe", "proj_off_effect": "cut", "transition_ms": 300}
        self.assertTrue(T.plan(T.ON, st).animated)
        self.assertFalse(T.plan(T.OFF, st).animated)

    def test_all_normal_effects_available_and_unknown_falls_back(self):
        self.assertEqual(len(T.EFFECT_KEYS), 13)
        for k in T.EFFECT_KEYS:
            self.assertEqual(T.plan(T.ON, {"proj_on_effect": k, "transition_ms": 200}).effect,
                             k if k != "cut" else "cut")
        c = T.clean({"transition_effect": "wipe", "proj_on_effect": "spin", "proj_off_effect": 5})
        self.assertEqual((c["proj_on_effect"], c["proj_off_effect"]), ("dissolve", "dissolve"))
        self.assertEqual(T.plan(T.OFF, {"proj_off_effect": "spin", "transition_ms": 200}).effect, "dissolve")

    def test_missing_keys_copy_normal_effect(self):
        c = T.clean({"transition_effect": "mosaic"})
        self.assertEqual((c["proj_on_effect"], c["proj_off_effect"]), ("mosaic", "mosaic"))

    def test_defaults_and_old_file_migration(self):
        self.assertEqual((settings.DEFAULTS["proj_on_effect"], settings.DEFAULTS["proj_off_effect"]), ("dissolve", "dissolve"))
        d = tempfile.mkdtemp()
        p = os.path.join(d, "s.json")
        json.dump({"transition_effect": "blinds"}, open(p, "w"))
        st = settings.load(p)
        self.assertEqual((st["proj_on_effect"], st["proj_off_effect"], st["transition_effect"]), ("blinds",) * 3)
        json.dump({"transition_effect": "blinds", "proj_on_effect": "zoom", "proj_off_effect": "cut"}, open(p, "w"))
        st = settings.load(p)
        self.assertEqual((st["proj_on_effect"], st["proj_off_effect"]), ("zoom", "cut"))
        json.dump({"proj_on_effect": "bogus"}, open(p, "w"))
        self.assertEqual(settings.load(p)["proj_on_effect"], "dissolve")


@unittest.skipIf(QtWidgets is None, "PyQt5 not installed")
class Ui(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qa = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        cls.qa.setStyleSheet(lite_app.QSS)

    def make(self):
        d = tempfile.mkdtemp()
        lite_app.paths.user_dir = lambda: d
        w = lite_app.Main()
        w.dir = d
        w.show()
        self.qa.processEvents()
        return w

    def saved(self, w):
        return json.load(open(os.path.join(w.dir, "settings.json")))

    def test_selectors_independent_and_persist(self):
        w = self.make()
        self.assertEqual(w.pon_cb.count(), len(T.EFFECTS))
        self.assertEqual(w.poff_cb.count(), len(T.EFFECTS))
        w.tfx_cb.setCurrentIndex(w.tfx_cb.findData("slide"))
        w.pon_cb.setCurrentIndex(w.pon_cb.findData("iris"))
        w.poff_cb.setCurrentIndex(w.poff_cb.findData("clock"))
        s = self.saved(w)
        self.assertEqual((s["transition_effect"], s["proj_on_effect"], s["proj_off_effect"]), ("slide", "iris", "clock"))
        w.tfx_cb.setCurrentIndex(w.tfx_cb.findData("wipe"))      # normal change must not move On/Off
        s = self.saved(w)
        self.assertEqual((s["proj_on_effect"], s["proj_off_effect"]), ("iris", "clock"))
        w.pon_cb.setCurrentIndex(w.pon_cb.findData("zoom"))      # On/Off change must not move normal
        s = self.saved(w)
        self.assertEqual((s["transition_effect"], s["proj_off_effect"]), ("wipe", "clock"))
        w2 = lite_app.Main()
        self.assertEqual((w2.pon_cb.currentData(), w2.poff_cb.currentData(), w2.tfx_cb.currentData()), ("zoom", "clock", "wipe"))

    def test_project_and_off_use_their_own_effects(self):
        w = self.make()
        w.tfx_cb.setCurrentIndex(w.tfx_cb.findData("slide"))
        w.pon_cb.setCurrentIndex(w.pon_cb.findData("iris"))
        w.poff_cb.setCurrentIndex(w.poff_cb.findData("clock"))
        w.tms_sp.setValue(1500)
        seen = []
        orig = w.proj.transition
        w.proj.transition = lambda plan, *a, **k: (seen.append((plan.kind, plan.effect)), orig(plan, *a, **k))[1]
        w.project()
        w.proj.finish_transition()
        w.project_off()
        w.proj.finish_transition()
        self.assertEqual(seen, [("on", "iris"), ("off", "clock")])
        self.assertFalse(w.proj.isVisible())

    def test_off_cut_hides_instantly_and_switch_uses_normal(self):
        w = self.make()
        w.tfx_cb.setCurrentIndex(w.tfx_cb.findData("slide"))
        w.poff_cb.setCurrentIndex(w.poff_cb.findData("cut"))
        seen = []
        orig = w.proj.transition
        w.proj.transition = lambda plan, *a, **k: (seen.append((plan.kind, plan.effect)), orig(plan, *a, **k))[1]
        w.project()
        w.proj.finish_transition()
        w.project()          # same picture: instant
        w.project_off()
        self.assertFalse(w.proj.isVisible())
        self.assertFalse(w.proj.transitioning)
        self.assertEqual(seen[-1], ("off", "cut"))


if __name__ == "__main__":
    unittest.main()
