"""Move Up / Move Down must select the moved service item (common pathway).

Covers: visible gold/current row, model service order, Bible reference box,
in-app preview, no projection, and song slide selection still working.
Not a Windows 8.1 hardware check: run offscreen on Linux.
"""
import os
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

try:
    from PyQt5 import QtWidgets
    from revelatelite import app as lite_app
    from revelatelite import songs as S
except ImportError:  # pragma: no cover
    QtWidgets = None

LYR = "[Verse 1]\nAmazing grace\nHow sweet the sound\n\nChorus:\nMy chains are gone\nI've been set free\n"


@unittest.skipIf(QtWidgets is None, "PyQt5 not installed")
class MoveSelectsServiceItem(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qa = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        cls.qa.setStyleSheet(lite_app.QSS)

    def make(self, with_song=False):
        from revelatelite import paths
        d = tempfile.mkdtemp()
        paths.user_dir = lambda: d
        lite_app.paths.user_dir = lambda: d
        if with_song:
            lib = S.SongLibrary(os.path.join(d, "songs"))
            lib.save(S.Song("Amazing Grace", "Newton", S.split_lyrics(LYR)))
        w = lite_app.Main()
        w.st["transition_ms"] = 0
        self.addCleanup(w.close)
        # service list in the exact screenshot order: Zechariah, 1 Peter, 1 John
        w.services.add("Zechariah 1:4", "KJV")
        w.services.add("1 Peter 1:2", "KJV")
        w.services.add("1 John 3:16", "KJV")
        w.refresh_service_list()
        w.persist_list()
        # start from the last row, as if clicked there: lookup happens via pick
        w.service_list.setCurrentRow(2)
        w.pick_item(w.service_list.currentItem())
        return w

    def refs(self, w):
        return [it["ref"] for it in w.services.items]

    def test_move_up_bible_selects_moved_item_without_projecting(self):
        w = self.make()
        self.assertEqual(w.service_list.currentRow(), 2)
        self.assertEqual(w.box.text(), "1 John 3:16")
        self.assertIn("1 John 3:16", w.preview.ref)
        proj_before = w.proj.ref if hasattr(w.proj, "ref") else None
        live_before = w.proj.isVisible()

        w.move_item(-1)

        self.assertEqual(self.refs(w), ["Zechariah 1:4", "1 John 3:16", "1 Peter 1:2"])
        self.assertEqual(w.service_list.currentRow(), 1)                    # gold row = moved item
        self.assertEqual(w.service_list.item(1).text(), "1 John 3:16  (KJV)")
        self.assertEqual(w.box.text(), "1 John 3:16")                       # Find a verse / reference field
        self.assertIn("1 John 3:16", w.preview.ref)                         # in-app preview updated
        self.assertNotIn("1 Peter", w.preview.ref)
        self.assertEqual(w.cur[:4], (62, 3, 16, 16))
        self.assertFalse(w.proj.isVisible())
        self.assertEqual(live_before, w.proj.isVisible())
        if proj_before is not None:
            self.assertEqual(w.proj.ref, proj_before)                       # projector untouched

    def test_move_up_again_selects_new_position(self):
        w = self.make()
        w.move_item(-1)
        w.move_item(-1)
        self.assertEqual(self.refs(w), ["1 John 3:16", "Zechariah 1:4", "1 Peter 1:2"])
        self.assertEqual(w.service_list.currentRow(), 0)
        self.assertEqual(w.box.text(), "1 John 3:16")
        self.assertIn("1 John 3:16", w.preview.ref)
        self.assertFalse(w.proj.isVisible())

    def test_move_down_bible_selects_moved_item_without_projecting(self):
        w = self.make()
        # select 1 Peter (row 1) via the normal mouse pathway first
        w.service_list.setCurrentRow(1)
        w.pick_item(w.service_list.currentItem())
        self.assertEqual(w.box.text(), "1 Peter 1:2")
        self.assertIn("1 Peter 1:2", w.preview.ref)

        w.move_item(1)

        self.assertEqual(self.refs(w), ["Zechariah 1:4", "1 John 3:16", "1 Peter 1:2"])
        self.assertEqual(w.service_list.currentRow(), 2)
        self.assertEqual(w.service_list.item(2).text(), "1 Peter 1:2  (KJV)")
        self.assertEqual(w.box.text(), "1 Peter 1:2")
        self.assertIn("1 Peter 1:2", w.preview.ref)
        self.assertNotIn("1 John", w.preview.ref)
        self.assertEqual(w.cur[:4], (60, 1, 2, 2))
        self.assertFalse(w.proj.isVisible())

    def test_move_at_boundary_keeps_current_selection(self):
        w = self.make()
        w.service_list.setCurrentRow(0)
        w.pick_item(w.service_list.currentItem())
        self.assertEqual(w.box.text(), "Zechariah 1:4")
        w.move_item(-1)  # already at top: no move, selection must stay true
        self.assertEqual(self.refs(w), ["Zechariah 1:4", "1 Peter 1:2", "1 John 3:16"])
        self.assertEqual(w.service_list.currentRow(), 0)
        self.assertEqual(w.box.text(), "Zechariah 1:4")
        self.assertIn("Zechariah 1:4", w.preview.ref)
        self.assertFalse(w.proj.isVisible())

    def test_keyboard_selection_uses_same_pathway(self):
        w = self.make()
        w.service_list.setCurrentRow(0)          # keyboard/arrow equivalent: row change
        w.pick_item(w.service_list.currentItem())
        self.assertEqual(w.box.text(), "Zechariah 1:4")
        self.assertIn("Zechariah 1:4", w.preview.ref)

    def test_song_move_still_selects_correctly(self):
        # Service list holds Bible items; the Songs tab holds song slides.
        # A service Move must select the moved Bible item into the shared
        # preview (not project), and picking a song slide afterwards must
        # still select correctly via the same preview pathway.
        w = self.make(with_song=True)
        w.song_list.setCurrentRow(0)
        w.pick_song(0)
        self.assertIn("Amazing Grace", w.preview.ref)
        song_ref = w.preview.ref
        w.service_list.setCurrentRow(2)
        w.move_item(-1)
        self.assertEqual(w.service_list.currentRow(), 1)
        self.assertEqual(w.box.text(), "1 John 3:16")   # moved Bible item now current
        self.assertIn("1 John 3:16", w.preview.ref)
        self.assertFalse(w.proj.isVisible())
        # picking the song again still works via the same preview pathway
        w.pick_song(0)
        self.assertEqual(w.preview.ref, song_ref)
        # and stepping through slides still selects the next slide
        w.slide_list.setCurrentRow(1)
        self.assertIn("Chorus", w.preview.ref)
        self.assertFalse(w.proj.isVisible())


if __name__ == "__main__":
    unittest.main()
