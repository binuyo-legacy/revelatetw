"""Programs panel (live mirror of the real projector window) + Project buttons in the middle stack.
Offscreen Qt. Run: python -m pytest lite/tests/test_programs_mirror.py"""
import os
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
try:
    from PyQt5 import QtWidgets, QtCore, QtGui
    from revelatelite import app as lite_app
    from revelatelite.projection import ProgramsView
except ImportError:  # pragma: no cover
    QtWidgets = None


def img_of(widget_or_fn, w, h):
    im = QtGui.QImage(w, h, QtGui.QImage.Format_RGB32)
    im.fill(QtGui.QColor("#000000"))
    p = QtGui.QPainter(im)
    widget_or_fn(p, QtCore.QRect(0, 0, w, h))
    p.end()
    return im


@unittest.skipIf(QtWidgets is None, "PyQt5 not installed")
class ProgramsMirror(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qa = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        cls.qa.setStyleSheet(lite_app.QSS)

    def make(self):
        from revelatelite import paths
        d = tempfile.mkdtemp()
        paths.user_dir = lambda: d
        lite_app.paths.user_dir = lambda: d
        w = lite_app.Main()
        w.st["transition_effect"] = "cut"
        w.st["proj_on_effect"] = "cut"
        w.st["proj_off_effect"] = "cut"
        w.show()
        self.qa.processEvents()
        return w

    def pump(self, ms=50):
        self.qa.processEvents()

    def mirror_img(self, w):
        pv = w.programs
        return pv.grab().toImage()

    def expected(self, w):
        """What the Programs widget itself paints, including its adaptive scaling."""
        r = w.programs.screen_rect()
        return img_of(lambda p, rect: w.proj.render_frame_adaptive(p, rect), r.width(), r.height())

    def center_matches(self, w):
        got = self.mirror_img(w)
        r = w.programs.screen_rect()
        exp = self.expected(w)
        for (x, y) in ((5, 5), (r.width() // 2, r.height() // 2), (r.width() - 6, r.height() - 6), (r.width() // 3, r.height() // 2)):
            if got.pixel(r.x() + x, r.y() + y) != exp.pixel(x, y):
                return False
        return True

    # ---- layout ----
    def test_buttons_moved_to_middle_stack(self):
        w = self.make()
        side = w.up_b.parentWidget()
        self.assertIs(w.project_b.parentWidget(), side)
        self.assertIs(w.blank_b.parentWidget(), side)
        self.assertIs(w.rm_b.parentWidget(), side)
        names = [b.text() for b in side.findChildren(QtWidgets.QPushButton)
                 if b in (w.project_b, w.blank_b, w.up_b, w.down_b, w.rm_b)]
        self.assertEqual(set(names), {"Project (F5)", "Project Off (Esc)", "Move up", "Move down", "Remove"})
        # not under the preview any more
        self.assertLess(w.project_b.x() + w.project_b.width(), w.tv_frame.mapTo(w, QtCore.QPoint(0, 0)).x())
        self.assertEqual(w.project_b.objectName(), "primary")
        self.assertFalse(w.blank_b.isEnabled())

    def test_tab_row_and_order_untouched(self):
        w = self.make()
        self.assertEqual([w.tabs.tabText(i) for i in range(w.tabs.count())],
                         ["Service list", "Search words", "Songs", "Settings"])
        self.assertEqual((w.width(), w.height()), (1000, 640))
        self.assertFalse(w.isMaximized())
        self.assertTrue(w.quick_host.isVisible())

    def test_programs_same_frame_and_size_below_preview(self):
        w = self.make()
        self.assertEqual(w.programs_frame.size(), w.tv_frame.size())
        self.assertEqual(w.programs.size(), w.preview.size())
        self.assertEqual(w.programs.height(), w.preview.height())
        a = w.tv_frame.mapTo(w, QtCore.QPoint(0, 0))
        b = w.programs_frame.mapTo(w, QtCore.QPoint(0, 0))
        self.assertEqual(a.x(), b.x())
        self.assertGreater(b.y(), a.y() + w.tv_frame.height() - 1)
        self.assertIsInstance(w.programs, ProgramsView)
        self.assertIsNot(w.programs, w.preview)

    def test_programs_fits_in_window(self):
        w = self.make()
        bottom = w.programs_frame.mapTo(w, QtCore.QPoint(0, w.programs_frame.height())).y()
        self.assertLessEqual(bottom, w.height())
        self.assertLessEqual(w.add_b.mapTo(w, QtCore.QPoint(0, w.add_b.height())).y(), w.height())
        self.assertGreater(w.add_b.mapTo(w, QtCore.QPoint(0, 0)).y(),
                           w.programs_frame.mapTo(w, QtCore.QPoint(0, 0)).y())

    def test_compact_nav_buttons_still_work(self):
        w = self.make()
        for b in (w.prev_b, w.next_b, w.add_b):
            self.assertLessEqual(b.height(), 30)
        w.lookup("John 3:16")
        before = w.cur
        w.next_b.click()
        self.assertNotEqual(w.cur, before)

    def test_programs_not_interactive(self):
        w = self.make()
        self.assertEqual(w.programs.focusPolicy(), QtCore.Qt.NoFocus)
        self.assertTrue(w.programs.testAttribute(QtCore.Qt.WA_TransparentForMouseEvents))

    # ---- sync with the real output ----
    def test_off_until_project_and_edits_are_preview_only(self):
        w = self.make()
        w.lookup("John 3:16")
        self.assertFalse(w.proj.isVisible())
        self.assertFalse(w.programs_frame.on_air)
        self.assertTrue(w.preview.body)
        self.assertEqual(w.proj.body, "")                    # nothing sent
        self.assertTrue(self.center_matches(w))              # mirror = black (projector hidden)
        before = self.mirror_img(w)
        w.lookup("John 3:17")
        w.step(1)
        self.assertFalse(w.proj.isVisible())
        self.assertEqual(w.proj.body, "")
        self.assertEqual(self.mirror_img(w), before)         # preview edits never reach Programs
        w.q_sl_effect.setCurrentIndex(1)

    def test_project_then_content_then_off(self):
        w = self.make()
        w.lookup("John 3:16")
        w.project()
        self.pump()
        self.assertTrue(w.proj.isVisible())
        self.assertTrue(w.programs_frame.on_air)
        self.assertTrue(self.center_matches(w))
        shown = w.proj.body
        # edit in the preview: Programs keeps the on-air slide
        w.lookup("Psalm 23:1")
        self.assertNotEqual(w.preview.body, shown)
        self.assertEqual(w.proj.body, shown)
        self.assertTrue(self.center_matches(w))
        self.assertIn("LIVE (preview not sent yet)", w.live_badge.text())
        # Project again: mirror follows the new on-air content
        old = self.mirror_img(w)
        w.project()
        self.pump()
        self.assertEqual(w.proj.body, w.preview.body)
        self.assertNotEqual(self.mirror_img(w), old)
        self.assertTrue(self.center_matches(w))
        # Project Off
        w.project_off()
        self.pump()
        self.assertFalse(w.proj.isVisible())
        self.assertFalse(w.programs_frame.on_air)
        self.assertEqual(self.mirror_img(w).pixel(5, 5), 0xff000000)
        self.assertTrue(w.preview.body)                      # operator preview untouched

    def test_alt_f4_close_updates_programs(self):
        w = self.make()
        w.lookup("John 3:16")
        w.project()
        self.pump()
        w.proj.close()
        self.qa.processEvents()
        self.assertFalse(w.programs_frame.on_air)
        self.assertEqual(self.mirror_img(w).pixel(5, 5), 0xff000000)

    def test_style_changes_follow_only_after_project(self):
        w = self.make()
        w.lookup("John 3:16")
        w.project()
        self.pump()
        live = self.mirror_img(w)
        i = (w.theme_cb.currentIndex() + 1) % w.theme_cb.count()
        w.theme_cb.setCurrentIndex(i)
        w.font_cb.setCurrentIndex((w.font_cb.currentIndex() + 1) % w.font_cb.count())
        self.qa.processEvents()
        self.assertEqual(self.mirror_img(w), live)           # edit look stays preview-only
        self.assertTrue(self.center_matches(w))
        w.project()
        self.pump()
        self.assertTrue(self.center_matches(w))
        self.assertNotEqual(self.mirror_img(w), live)        # new look is on air now

    def test_song_slide_uses_projector_look(self):
        w = self.make()
        w._set_slide(("Title - Verse 1", "Line one\nLine two", ""), ("Title", "Artist", "Verse 1", 1, 2))
        w.project()
        self.pump()
        self.assertIsNotNone(w.proj.meta)
        self.assertTrue(self.center_matches(w))

    def test_mirror_shows_running_transition_frame(self):
        w = self.make()
        w.st["proj_on_effect"] = "wipe"
        w.st["transition_ms"] = 1500
        w.st["transition_onoff"] = True
        w.lookup("John 3:16")
        w.project()
        if not w.proj.transitioning:
            self.skipTest("transition not animated in this setup")
        mid = []
        w.proj.frameChanged.connect(lambda: mid.append(1))
        w.proj._tx["p"] = 0.5
        w.proj.update()
        self.assertTrue(mid)                                  # signal fired for the frame
        self.assertTrue(self.center_matches(w))               # Programs drew the same frame
        w.proj.finish_transition()
        self.assertTrue(self.center_matches(w))

    def test_signal_driven_no_timers(self):
        w = self.make()
        n = []
        w.programs.update = lambda *a: n.append(1)
        w.proj.frameChanged.disconnect()
        w.proj.frameChanged.connect(w.programs.update)
        w.proj.update()
        self.assertTrue(n)
        timers = [t for t in w.programs.findChildren(QtCore.QTimer)]
        self.assertEqual(timers, [])
    # ---- adaptive scaling: the slide fills the Programs box like the TV preview ----

    def test_screen_rect_is_the_whole_widget(self):
        w = self.make()
        self.assertEqual(w.programs.screen_rect(), w.programs.rect())

    def test_slide_fills_box_edges_not_letterboxed(self):
        """Corners/edges carry the slide background, not the old black sidebars."""
        w = self.make()
        w.lookup("John 3:16")
        w.project()
        self.pump()
        im = self.mirror_img(w)
        r = w.programs.rect()
        black = 0xff000000
        navies = {0xff0b0f19}
        for (x, y) in ((2, 2), (r.width() - 3, 2), (2, r.height() - 3), (r.width() - 3, r.height() - 3),
                       (r.width() // 2, 2), (2, r.height() // 2), (r.width() - 3, r.height() // 2), (r.width() // 2, r.height() - 3)):
            self.assertNotEqual(im.pixel(x, y), black, (x, y))
            self.assertIn(im.pixel(x, y), navies, (x, y))

    def test_adaptation_follows_programs_widget_size(self):
        """Resizing the Programs widget re-scales the slide to its own box (no fixed bar inset)."""
        from revelatelite.projection import ProgramsView
        import tempfile
        from revelatelite import paths
        d = tempfile.mkdtemp()
        paths.user_dir = lambda: d
        lite_app.paths.user_dir = lambda: d
        w = lite_app.Main()
        w.show()
        self.qa.processEvents()
        pv = w.programs
        w.lookup("John 3:16")
        w.project()
        self.pump()
        self.assertTrue(pv.screen_rect().isValid())
        # a tall, narrow box gets the full height through the same fit path
        pv.resize(300, 400)
        self.qa.processEvents()
        self.assertEqual(pv.screen_rect(), pv.rect())
        fr = w.proj.fit_rect(pv.rect())
        self.assertLessEqual(fr.width(), pv.width())
        self.assertLessEqual(fr.height(), pv.height())
        self.assertGreater(fr.width(), 0)
        self.assertGreater(fr.height(), 0)
        # and painting still works at the new shape
        im = pv.grab().toImage()
        self.assertGreater(im.width(), 0)

    # ---- green live frame (Programs only) ----

    def test_programs_glow_is_green_tv_stays_gold(self):
        w = self.make()
        from revelatetw.ui_tokens import COLORS as C
        self.assertEqual(w.programs_frame.glow_hex, C.live_on_border)
        g = QtGui.QColor(w.programs_frame.glow_hex)
        self.assertGreater(g.green(), g.red())          # green, not gold
        self.assertEqual(w.tv_frame.glow_hex, C.accent)  # TV preview keeps gold
        gold = QtGui.QColor(C.accent)
        self.assertGreater(gold.red(), gold.green())

    def test_green_frame_lights_and_dims_with_live_state(self):
        os.environ["REVELATELITE_NO_GLOW_ANIMATION"] = "1"
        try:
            w = self.make()
            self.assertEqual(w.programs_frame.glow, 0.0)     # off: subdued
            self.assertFalse(w.programs_frame.on_air)
            w.lookup("John 3:16")
            w.project()
            self.pump()
            self.assertTrue(w.programs_frame.on_air)
            self.assertEqual(w.programs_frame.glow, 1.0)     # live: fully lit green
            self.assertEqual(w.tv_frame.glow, 1.0)           # tv also lit (gold, unchanged)
            w.project_off()
            self.pump()
            self.assertFalse(w.programs_frame.on_air)
            self.assertEqual(w.programs_frame.glow, 0.0)     # off again: dims out
        finally:
            os.environ.pop("REVELATELITE_NO_GLOW_ANIMATION", None)

    # ---- no size/layout change ----

    def test_frames_same_size_and_no_layout_shift_on_live(self):
        w = self.make()
        w.lookup("John 3:16")
        w.project()
        self.pump()
        # sizes while live (frames have settled at their final geometry)
        self.assertEqual(w.programs_frame.size(), w.tv_frame.size())
        self.assertEqual(w.programs.height(), w.preview.height())
        w.project_off()
        self.pump()
        self.assertEqual(w.programs_frame.size(), w.tv_frame.size())


if __name__ == "__main__":
    unittest.main()


@unittest.skipIf(QtWidgets is None, "PyQt5 not installed")
class ProgramsTransitionNoFlash(ProgramsMirror):
    """Project ON / OFF transitions: Programs must fill its own box on EVERY frame (no projector-shaped
    black side bars), while the real projector keeps its native size and aspect."""
    EFFECTS = ("fade", "dissolve", "wipe", "slide", "checkerboard")

    def tearDown(self):
        for w in getattr(self, "_made", []):
            try:
                w.proj.finish_transition()
                w.proj.hide()
                w.close()
            except RuntimeError:
                pass
        self._made = []
        self.qa.processEvents()

    def setup_anim(self, eff, ms=2000):
        w = self.make()
        self.__dict__.setdefault("_made", []).append(w)
        w.st.update(transition_effect=eff, proj_on_effect=eff, proj_off_effect=eff,
                    transition_ms=ms, transition_onoff=True, transition_switch=True)
        w.proj.resize(960, 540)           # projector shape differs from the Programs box
        w.programs.resize(300, 300)       # clearly not the projector's aspect: any fitted frame has bars
        self.qa.processEvents()
        return w

    def bars_at(self, w):
        """True if the Programs panel shows black side bars (pure black at the left/right edges while
        the middle is not black)."""
        im = w.programs.grab().toImage()
        r = w.programs.rect()
        black = 0xff000000
        y = r.height() // 2
        edges = (im.pixel(1, y) == black and im.pixel(r.width() - 2, y) == black)
        mid = im.pixel(r.width() // 2, 2) != black
        return edges and mid

    def sweep(self, w, collect):
        tx = w.proj._tx
        self.assertIsNotNone(tx)
        for pr in (0.0, 0.1, 0.3, 0.5, 0.7, 0.9, 1.0):
            tx["p"] = pr
            w.proj.update()
            self.qa.processEvents()
            collect(pr)

    def test_on_transition_never_shows_projector_shaped_bars(self):
        for eff in self.EFFECTS:
            w = self.setup_anim(eff)
            w.lookup("John 3:16")
            w.project()
            self.assertTrue(w.proj.transitioning, eff)
            tx = w.proj._tx
            # box pictures are exactly the Programs box, projector pictures stay native
            self.assertEqual(tx["m_old"].size(), w.programs.size(), eff)
            self.assertEqual(tx["m_new"].size(), w.programs.size(), eff)
            self.assertEqual(tx["old"].size(), w.proj.size(), eff)
            self.assertEqual(tx["new"].size(), w.proj.size(), eff)
            seen = []
            self.sweep(w, lambda pr: seen.append(self.bars_at(w)))
            self.assertFalse(any(seen), eff)
            w.proj.finish_transition()
            self.qa.processEvents()
            self.assertFalse(self.bars_at(w), eff)
            self.assertTrue(self.center_matches(w), eff)
            self.tearDown()

    def test_off_transition_never_shows_projector_shaped_bars(self):
        for eff in self.EFFECTS:
            w = self.setup_anim(eff)
            w.lookup("John 3:16")
            w.st["transition_ms"] = 0
            w.project()
            self.qa.processEvents()
            w.st["transition_ms"] = 2000
            w.project_off()
            self.assertTrue(w.proj.transitioning, eff)
            tx = w.proj._tx
            self.assertEqual(tx["m_old"].size(), w.programs.size(), eff)
            self.assertEqual(tx["m_new"].size(), w.programs.size(), eff)
            seen = []
            self.sweep(w, lambda pr: seen.append(self.bars_at(w)))
            self.assertFalse(any(seen), eff)
            w.proj.finish_transition()
            self.qa.processEvents()
            self.assertFalse(w.proj.isVisible())
            self.assertEqual(w.programs.grab().toImage().pixel(1, 1), 0xff000000)
            self.tearDown()

    def test_first_frame_after_project_is_not_native_shape(self):
        """The very first frames (window shown, animation not yet stepped) are box-shaped / black, never a native frame."""
        w = self.setup_anim("dissolve")
        frames = []
        w.proj.frameChanged.connect(lambda: frames.append(self.bars_at(w)))
        w.lookup("John 3:16")
        w.project()
        self.qa.processEvents()
        self.assertTrue(frames)
        self.assertFalse(any(frames))

    def test_box_resize_mid_transition_stays_box_shaped(self):
        w = self.setup_anim("dissolve")
        w.lookup("John 3:16")
        w.project()
        w.proj._tx["p"] = 0.8
        w.programs.resize(420, 250)
        self.qa.processEvents()
        self.assertEqual(w.proj.mirror_size, w.programs.size())
        self.assertFalse(self.bars_at(w))
        w.proj.finish_transition()

    def test_projector_output_stays_native_size_and_aspect(self):
        for eff in ("dissolve", "wipe", "slide"):
            w = self.setup_anim(eff)
            w.lookup("John 3:16")
            w.project()
            tx = w.proj._tx
            self.assertEqual(tx["old"].size(), w.proj.size())
            self.assertEqual(tx["new"].size(), w.proj.size())
            tx["p"] = 0.6
            pw, ph = w.proj.width(), w.proj.height()
            im = img_of(lambda p, rect: w.proj.render_frame(p, rect), pw, ph)
            self.assertEqual(im.size(), QtCore.QSize(pw, ph))
            # native render is unchanged by Programs: identical with a different Programs box
            w.programs.resize(500, 200)
            self.qa.processEvents()
            im2 = img_of(lambda p, rect: w.proj.render_frame(p, rect), pw, ph)
            self.assertEqual(im, im2)
            self.assertEqual(w.proj.size(), QtCore.QSize(pw, ph))
            w.proj.finish_transition()
            # still slide on the projector fills its native frame
            im3 = img_of(lambda p, rect: w.proj.render_frame(p, rect), pw, ph)
            self.assertNotEqual(im3.pixel(2, ph // 2), 0xff000000)
            self.assertNotEqual(im3.pixel(pw - 3, ph // 2), 0xff000000)
            self.tearDown()

    def test_tv_preview_unchanged(self):
        w = self.setup_anim("dissolve")
        w.lookup("John 3:16")
        sz = w.preview.size()
        before = w.preview.snapshot(sz).toImage()
        w.project()
        w.proj._tx["p"] = 0.5
        w.proj.update()
        self.qa.processEvents()
        self.assertEqual(w.preview.snapshot(sz).toImage(), before)
        w.proj.finish_transition()


@unittest.skipIf(QtWidgets is None, "PyQt5 not installed")
class ProgramsContinuousNext(ProgramsTransitionNoFlash):
    """Pressing Next / Previous over and over while live: every Programs frame stays box-shaped."""

    def go_live(self, eff):
        w = self.setup_anim(eff, ms=1500)
        w.lookup("John 3:16")
        w.st["transition_ms"] = 0
        w.project()
        self.qa.processEvents()
        w.st["transition_ms"] = 1500
        return w

    def check_frames(self, w, label):
        tx = w.proj._tx
        if tx is None:
            self.assertFalse(self.bars_at(w), label)
            return
        self.assertEqual(tx["m_old"].size(), w.programs.size(), label)
        self.assertEqual(tx["m_new"].size(), w.programs.size(), label)
        self.assertEqual(tx["old"].size(), w.proj.size(), label)      # projector stays native
        self.assertEqual(tx["new"].size(), w.proj.size(), label)
        self.assertFalse(self.bars_at(w), label + " first")
        for pr in (0.0, 0.25, 0.5, 0.75, 1.0):
            tx["p"] = pr
            w.proj.update()
            self.qa.processEvents()
            self.assertFalse(self.bars_at(w), "%s p=%s" % (label, pr))

    def test_repeated_next_every_frame_box_shaped(self):
        for eff in ("fade", "dissolve", "wipe", "slide", "checkerboard"):
            w = self.go_live(eff)
            bodies = set()
            for i in range(6):
                w.next_b.click()
                w.project()
                self.qa.processEvents()
                self.assertTrue(w.proj.isVisible(), eff)
                bodies.add(w.proj.body)
                self.check_frames(w, "%s next %d" % (eff, i))
            self.assertGreater(len(bodies), 1, eff)               # it really moved through verses
            w.proj.finish_transition()
            self.qa.processEvents()
            self.assertFalse(self.bars_at(w), eff)
            self.assertTrue(self.center_matches(w), eff)
            self.tearDown()

    def test_next_then_previous_mixed(self):
        w = self.go_live("slide")
        for i, b in enumerate((w.next_b, w.next_b, w.prev_b, w.next_b, w.prev_b, w.prev_b)):
            b.click()
            w.project()
            self.qa.processEvents()
            self.check_frames(w, "mixed %d" % i)

    def test_next_interrupting_running_transition_never_flashes(self):
        w = self.go_live("dissolve")
        seen = []
        w.proj.frameChanged.connect(lambda: seen.append(self.bars_at(w)))
        for _ in range(5):
            w.next_b.click()             # no finish in between: each Next interrupts the last
            w.project()
            self.qa.processEvents()
        self.assertTrue(seen)
        self.assertFalse(any(seen))
        w.proj.finish_transition()

    def test_song_slides_next_box_shaped(self):
        w = self.go_live("wipe")
        for i in range(3):
            w._set_slide(("Title - Verse %d" % i, "Line one\nLine two", ""), ("Title", "Artist", "Verse %d" % i, i + 1, 3))
            w.project()
            self.qa.processEvents()
            self.check_frames(w, "song %d" % i)

    def test_next_projector_native_and_tv_unchanged(self):
        w = self.go_live("dissolve")
        pw, ph = w.proj.width(), w.proj.height()
        w.next_b.click()
        w.project()
        w.proj._tx["p"] = 0.5
        a = img_of(lambda p, r: w.proj.render_frame(p, r), pw, ph)
        w.programs.resize(500, 220)
        self.qa.processEvents()
        b = img_of(lambda p, r: w.proj.render_frame(p, r), pw, ph)
        self.assertEqual(a, b)
        self.assertEqual((w.proj.width(), w.proj.height()), (pw, ph))
        w.proj.finish_transition()
