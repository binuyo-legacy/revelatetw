"""Tests for the text outline setting and the six new screen effects. Headless (offscreen Qt).
They do NOT prove smoothness on a real Windows 8.1 32-bit / 2 GB PC; that needs a hardware check.
Run: python -m pytest lite/tests/test_outline_and_new_effects.py"""
import os
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from PyQt5 import QtCore, QtGui, QtWidgets
from revelatelite import app as lite_app, background as bg, settings, transitions as T
from revelatelite.projection import ProjectionWindow, SlideView

NEW = ["checkerboard", "diagonal", "iris", "zoom", "mosaic", "clock"]


_QA = []


def qapp():
    qa = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    _QA[:] = [qa]       # keep a reference so Qt is not torn down between tests
    qa.setStyleSheet(lite_app.QSS)
    return qa


def poly_area(pts):
    a = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        a += x1 * y2 - x2 * y1
    return abs(a) / 2


def covered(rects, w, h):
    img = QtGui.QImage(w, h, QtGui.QImage.Format_RGB32)
    img.fill(0)
    p = QtGui.QPainter(img)
    for x, y, rw, rh in rects:
        p.fillRect(x, y, rw, rh, QtGui.QColor("#ffffff"))
    p.end()
    return sum(1 for x in range(w) for y in range(h) if img.pixel(x, y) & 0xffffff)


class Effects(unittest.TestCase):
    def test_six_new_distinct_effects_registered(self):
        for k in NEW:
            self.assertIn(k, T.EFFECT_KEYS)
        self.assertEqual(len(T.EFFECT_KEYS), 13)     # cut + 6 old animated + 6 new
        self.assertEqual(len(set(T.EFFECT_KEYS)), 13)

    def test_every_new_effect_plans_animated(self):
        for k in NEW:
            self.assertTrue(T.plan(T.ON, {"transition_effect": k, "transition_ms": 300}).animated)
            self.assertFalse(T.plan(T.ON, {"transition_effect": k, "transition_ms": 0}).animated)
            self.assertEqual(T.clean({"transition_effect": k})["transition_effect"], k)

    def test_tile_effects_start_empty_end_full(self):
        for fn in (T.checkerboard_rects, T.mosaic_rects):
            self.assertEqual(covered(fn(200, 120, 0), 200, 120), 0)
            self.assertEqual(covered(fn(200, 120, 1), 200, 120), 200 * 120)
            self.assertTrue(0 < covered(fn(200, 120, 0.5), 200, 120) < 200 * 120)

    def test_diagonal_iris_clock_geometry(self):
        for d in ("left", "right", "up", "down"):
            self.assertLess(poly_area(T.diagonal_polygon(d, 100, 60, 0.0)) if len(T.diagonal_polygon(d, 100, 60, 0.0)) >= 3 else 0, 1)
            self.assertAlmostEqual(poly_area(T.diagonal_polygon(d, 100, 60, 1.0)), 6000)
            self.assertTrue(0 < poly_area(T.diagonal_polygon(d, 100, 60, 0.5)) < 6000)
        self.assertEqual(T.iris_circle(100, 60, 0)[2], 0)
        self.assertGreaterEqual(T.iris_circle(100, 60, 1)[2], (100 ** 2 + 60 ** 2) ** 0.5 / 2)
        self.assertEqual((T.clock_degrees(0), T.clock_degrees(1), T.clock_degrees(0.5)), (0, 360, 180))

    def test_zoom_states_end_on_new(self):
        self.assertEqual(T.zoom_states(0), ((1.0, 1.0), (0.85, 0.0)))
        (_, oa), (ns, na) = T.zoom_states(1)
        self.assertEqual((oa, ns, na), (0.0, 1.0, 1.0))

    def test_only_diagonal_is_directed(self):
        self.assertIn("diagonal", T.DIRECTED)
        for k in ("checkerboard", "iris", "zoom", "mosaic", "clock"):
            self.assertNotIn(k, T.DIRECTED)


class Outline(unittest.TestCase):
    def test_defaults_persist_and_cleaning(self):
        path = os.path.join(tempfile.mkdtemp(), "s.json")
        st = settings.load(path)
        self.assertEqual((st["outline_on"], st["outline_color"], st["outline_px"]), (False, "", 3))
        st.update(outline_on=True, outline_color="#112233", outline_px=7)
        settings.save(path, st)
        st = settings.load(path)
        self.assertEqual((st["outline_on"], st["outline_color"], st["outline_px"]), (True, "#112233", 7))
        st.update(outline_color="red", outline_px=99)
        settings.save(path, st)
        st = settings.load(path)
        self.assertEqual((st["outline_color"], st["outline_px"]), ("", settings.OUTLINE_MAX))

    def test_auto_colour_thickness_and_hint(self):
        self.assertEqual(settings.resolve_outline("#ffffff"), "#0b0f19")
        self.assertEqual(settings.resolve_outline("#000000"), "#f8fafc")
        self.assertEqual(settings.resolve_outline("#ffffff", "#ff0000"), "#ff0000")
        self.assertGreater(settings.outline_pixels(1080, 5), settings.outline_pixels(180, 5))
        self.assertGreaterEqual(settings.outline_pixels(100, 1), 1)
        self.assertTrue(settings.outline_hint("#ffffff", "#fafafa"))
        self.assertEqual(settings.outline_hint("#ffffff", "#000000"), "")

    def _render(self, bg_spec=None, **kw):
        qapp()
        v = SlideView()
        v.resize(320, 180)
        v.set_style("navy", 100, False, "Arial", True, "", "", bg_spec, **kw)
        v.set_content("John 3:16", "For God so loved the world")
        return v.snapshot(QtCore.QSize(320, 180)).toImage()

    def test_outline_cache_hit_on_repeated_verse_paint(self):
        """A verse paint draws its reference line and its body: both rings must survive one
        paint instead of evicting each other, so a second identical paint renders no ring."""
        qapp()
        v = SlideView()
        v.resize(960, 540)
        v.set_style("navy", 100, True, "Georgia", False, "", "", None,
                    outline_on=True, outline_color="", outline_px=6)
        v.set_content("John 3:16",
                      "For God so loved the world that he gave his one and only Son, that whoever "
                      "believes in him shall not perish but have eternal life. Amen.")
        pm = QtGui.QPixmap(960, 540)
        p = QtGui.QPainter(pm)
        v._draw(p, v.rect())
        p.end()
        first = v._oc_renders
        self.assertGreater(first, 0)                          # first paint renders the rings
        self.assertGreaterEqual(len(v._oc), 2)                # body and reference coexist
        v._oc_renders = 0
        for _ in range(3):
            painting = QtGui.QPainter(pm)
            v._draw(painting, v.rect())
            painting.end()
        self.assertEqual(v._oc_renders, 0)                    # then every repaint blits
        self.assertEqual(first <= 8, True)

    def test_outline_cache_hit_on_repeated_song_paint(self):
        """Song slides call _text per title/line block: the cache must hold them all at once."""
        qapp()
        v = SlideView()
        v.resize(960, 540)
        v.set_style("navy", 100, True, "Georgia", False, "", "", None,
                    outline_on=True, outline_color="", outline_px=6)
        v.set_content("Song",
                      "Amazing grace how sweet the sound that saved a wretch like me",
                      "", meta=("Amazing Grace", "John Newton", "Verse", 1, 3))
        pm = QtGui.QPixmap(960, 540)
        p = QtGui.QPainter(pm)
        v._draw(p, v.rect())
        p.end()
        first = v._oc_renders
        self.assertGreater(first, 0)
        self.assertGreaterEqual(len(v._oc), 1)
        v._oc_renders = 0
        for _ in range(3):
            painting = QtGui.QPainter(pm)
            v._draw(painting, v.rect())
            painting.end()
        self.assertEqual(v._oc_renders, 0)

    def test_translated_paint_uses_cache_and_is_identical(self):
        """The real projector and the Programs mirror paint with translate(r.x, r.y). Two
        identical translated paints must be byte-identical and the second must blit (no ring
        render), so the mirror no longer stamps the ring every repaint."""
        qapp()
        v = SlideView()
        v.resize(400, 300)
        v.set_style("navy", 100, False, "Georgia", False, "", "", None,
                    outline_on=True, outline_color="", outline_px=5)
        v.set_content("John 3:16", "Test outline text here")
        def render_translated():
            img = QtGui.QImage(400, 300, QtGui.QImage.Format_RGB32)
            img.fill(QtGui.QColor("#000000"))
            q = QtGui.QPainter(img)
            q.translate(50, 30)
            q.setClipRect(QtCore.QRect(0, 0, 400, 300))
            v._draw(q, QtCore.QRect(0, 0, 400, 300))
            q.end()
            return img
        a = render_translated()
        v._oc_renders = 0
        b = render_translated()
        self.assertEqual(v._oc_renders, 0)
        self.assertEqual(a, b)

    def test_outline_changes_pixels_only_when_on(self):
        off1 = self._render()
        off2 = self._render(outline_on=False, outline_color="#ff0000", outline_px=9)
        on = self._render(outline_on=True, outline_color="#ff0000", outline_px=6)
        self.assertEqual(off1, off2)
        self.assertNotEqual(off1, on)
        reds = sum(1 for x in range(320) for y in range(180)
                   if on.pixelColor(x, y).red() > 200 and on.pixelColor(x, y).green() < 60)
        self.assertGreater(reds, 50)

    def test_outline_on_gradient_and_image(self):
        grad = bg.spec_from({"bg_kind": "gradient", "grad_color1": "#ffffff", "grad_color2": "#eeeeee",
                             "grad_direction": "vertical"})
        self.assertNotEqual(self._render(grad), self._render(grad, outline_on=True, outline_px=4))
        pic = os.path.join(tempfile.mkdtemp(), "p.png")
        im = QtGui.QImage(64, 64, QtGui.QImage.Format_RGB32)
        im.fill(QtGui.QColor("#dddddd"))
        im.save(pic)
        spec = bg.spec_from({"bg_kind": "image", "bg_image": pic, "image_mode": "fill", "image_dim": 0})
        self.assertNotEqual(self._render(spec), self._render(spec, outline_on=True, outline_px=4))

    def test_settings_tab_to_preview_and_projector(self):
        qapp()
        from revelatelite import paths
        d = tempfile.mkdtemp()
        paths.user_dir = lambda: d
        lite_app.paths.user_dir = lambda: d
        w = lite_app.Main()
        w.lookup("John 3:16")
        w.outline_cb.setChecked(True)
        w.outline_sp.setValue(6)
        self.assertTrue(w.preview.outline_on)
        self.assertEqual(w.preview.outline_px, 6)
        self.assertFalse(w.proj.isVisible())          # nothing reached the screen yet
        w.project()
        w.proj.finish_transition()
        self.assertTrue(w.proj.outline_on and w.proj.outline_px == 6)
        w.outline_cb.setChecked(False)                # live projector keeps its look until Project
        self.assertFalse(w.preview.outline_on)
        self.assertTrue(w.proj.outline_on)
        w.project()
        w.proj.finish_transition()
        self.assertFalse(w.proj.outline_on)
        w.project_off()
        w.proj.finish_transition()
        w.proj.close()
        w.close()
        import json
        with open(w.settings_path) as f:
            saved = json.load(f)
        self.assertEqual((saved["outline_on"], saved["outline_px"]), (False, 6))


class NewEffectsPaint(unittest.TestCase):
    def test_new_effect_frames_paint_differ_and_end_on_new(self):
        qapp()
        pw = ProjectionWindow()
        pw.resize(320, 180)
        pw.set_content("A", "old")
        old = pw.snapshot(pw.size())
        old.fill(QtGui.QColor("#aa0000"))   # clearly different from the new picture everywhere
        pw.set_content("B", "new new new")
        new = pw.snapshot(pw.size())
        for eff in NEW:
            frames = []
            for pr in (0.0, 0.5, 1.0):
                pw._tx = {"old": old, "new": new, "p": pr, "effect": eff, "direction": "left", "after": None}
                frames.append(pw.grab().toImage())
            self.assertNotEqual(frames[0], frames[1], eff)
            self.assertNotEqual(frames[1], frames[2], eff)
            self.assertEqual(frames[0], old.toImage(), eff)
            self.assertEqual(frames[2], new.toImage(), eff)
        pw._tx = None

    def test_new_effects_run_through_project_and_off(self):
        qapp()
        from revelatelite import paths
        d = tempfile.mkdtemp()
        paths.user_dir = lambda: d
        lite_app.paths.user_dir = lambda: d
        w = lite_app.Main()
        w.lookup("John 3:16")
        for eff in NEW:
            w.st.update(transition_effect=eff, transition_ms=200)
            w.lookup("John 3:16")
            w.project()
            self.assertTrue(w.proj.transitioning, eff)
            w.proj.finish_transition()
            self.assertTrue(w.proj.live and w.proj.isVisible())
            w.project_off()
            self.assertTrue(w.proj.transitioning, eff)
            w.proj.finish_transition()
            self.assertFalse(w.proj.isVisible())
        w.close()


if __name__ == "__main__":
    unittest.main()
