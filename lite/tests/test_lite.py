"""Tests for RevelateTW Lite. No PyQt needed.  Run:  python lite\tests\test_lite.py"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from revelatelite import layout, settings  # noqa: E402
from revelatelite.bible import BibleStore, clean_text, format_reference, parse_reference  # noqa: E402
from revelatelite.servicelist import ServiceList  # noqa: E402

B = BibleStore()


class Parse(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(parse_reference("John 3:16"), (43, 3, 16, 16))
        self.assertEqual(parse_reference("  rom 8:28 "), (45, 8, 28, 28))
        self.assertEqual(parse_reference("1 cor 13:4"), (46, 13, 4, 4))
        self.assertEqual(parse_reference("1cor 13:4"), (46, 13, 4, 4))
        self.assertEqual(parse_reference("first john 4:8"), (62, 4, 8, 8))
        self.assertEqual(parse_reference("Ps 23:1-3"), (19, 23, 1, 3))
        self.assertEqual(parse_reference("Gen. 1:1"), (1, 1, 1, 1))

    def test_chapter_only_means_verse_one(self):
        self.assertEqual(parse_reference("John 3"), (43, 3, 1, 1))

    def test_bad(self):
        for bad in ("", "Nope 1:1", "John 3:18-16", "John 0:1", "John", None):
            self.assertIsNone(parse_reference(bad), bad)

    def test_format(self):
        self.assertEqual(format_reference(43, 3, 16, 16), "John 3:16")
        self.assertEqual(format_reference(19, 23, 1, 3), "Psalms 23:1-3")


class Bible(unittest.TestCase):
    def test_packs_present(self):
        self.assertGreaterEqual(set(B.translations()), {"KJV", "ASV", "WEB", "Yoruba"})

    def test_known_text(self):
        self.assertTrue(B.verse("KJV", 43, 3, 16).startswith("For God so loved the world"))
        self.assertIn("Lord is my shepherd", B.verse("KJV", 19, 23, 1))

    def test_range_numbers(self):
        t = B.passage("KJV", 43, 3, 16, 17)
        self.assertTrue(t.startswith("16 For God") and " 17 " in t)

    def test_range_stops_at_chapter_end(self):
        last = B.last_verse("KJV", 43, 3)
        t = B.passage("KJV", 43, 3, last - 1, last + 10)
        self.assertEqual(len(t.split(" %d " % last)), 2)

    def test_missing(self):
        self.assertIsNone(B.passage("KJV", 43, 3, 999, 999))
        self.assertIsNone(B.verse("KJV", 43, 99, 1))

    def test_all_translations_core_verses(self):
        for tr in B.translations():
            for r in ("Genesis 1:1", "Ps 23:1", "Rom 8:28", "1 cor 13:4", "Rev 22:21", "Matt 5:3", "John 3:16"):
                self.assertTrue(B.passage(tr, *parse_reference(r)), (tr, r))

    def test_clean_text(self):
        self.assertEqual(clean_text("\u24d9 \u201cN\u00edtor\u00ed\u202fO"), "\u201cN\u00edtor\u00ed O")
        self.assertNotRegex(B.verse("Yoruba", 43, 3, 16), "[\u24b6-\u24e9]")

    def test_yoruba_has_credit_kjv_does_not(self):
        self.assertIn("Biblica", B.credit("Yoruba"))
        self.assertEqual(B.credit("KJV"), "")
        self.assertLess(len(B.short_credit("Yoruba")), 60)
        self.assertIn("CC BY-SA 4.0", B.short_credit("Yoruba"))

    def test_step_across_edges(self):
        self.assertEqual(B.step("KJV", 43, 3, 16, 1), (43, 3, 17))
        self.assertEqual(B.step("KJV", 43, 3, B.last_verse("KJV", 43, 3), 1), (43, 4, 1))
        self.assertEqual(B.step("KJV", 43, 4, 1, -1), (43, 3, B.last_verse("KJV", 43, 3)))
        self.assertEqual(B.step("KJV", 1, 1, 1, 1), (1, 1, 2))
        self.assertIsNone(B.step("KJV", 1, 1, 1, -1))
        self.assertEqual(B.step("KJV", 40, 1, 1, -1)[0], 39)
        self.assertIsNone(B.step("KJV", 66, 22, B.last_verse("KJV", 66, 22), 1))

    def test_search(self):
        hits = B.search("KJV", "loved world", 10)
        self.assertIn((43, 3, 16), [(b, c, v) for b, c, v, _ in hits])
        self.assertEqual(B.search("KJV", "   "), [])
        self.assertEqual(B.search("KJV", "100%_"), [])   # LIKE wildcards are escaped

    def test_unknown_translation(self):
        with self.assertRaises(KeyError):
            BibleStore().verse("NOPE", 1, 1, 1)


class Display(unittest.TestCase):
    def test_second_screen_chosen(self):
        r = [(0, 0, 1366, 768), (1366, 0, 1920, 1080)]
        self.assertEqual(layout.pick_display(r, 0), (1, True))
        self.assertEqual(layout.pick_display(r, 1), (0, True))

    def test_single_screen(self):
        self.assertEqual(layout.pick_display([(0, 0, 1366, 768)], 0), (0, False))
        self.assertEqual(layout.pick_display([], 0), (0, False))

    def test_wanted(self):
        r = [(0, 0, 10, 10), (10, 0, 10, 10), (20, 0, 10, 10)]
        self.assertEqual(layout.pick_display(r, 0, 2), (2, True))
        self.assertEqual(layout.pick_display(r, 0, 9), (1, True))   # bad choice falls back to automatic

    def test_mirrored(self):
        self.assertTrue(layout.is_mirrored([(0, 0, 1, 1), (0, 0, 1, 1)]))
        self.assertFalse(layout.is_mirrored([(0, 0, 1, 1), (1, 0, 1, 1)]))

    def test_fit_font(self):
        self.assertEqual(layout.fit_font_size(lambda s: s <= 57, 14, 200), 57)
        self.assertEqual(layout.fit_font_size(lambda s: False, 14, 200), 14)
        self.assertEqual(layout.fit_font_size(lambda s: True, 14, 90), 90)


class Files(unittest.TestCase):
    def test_settings_defaults_and_clamp(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "s.json")
        self.assertEqual(settings.load(p)["translation"], "KJV")
        with open(p, "w") as f:
            f.write("{not json")
        self.assertEqual(settings.load(p)["font_scale"], 100)
        s = settings.load(p)
        s["font_scale"] = 500
        s["theme"] = "pink"
        settings.save(p, s)
        s2 = settings.load(p)
        self.assertEqual((s2["font_scale"], s2["theme"]), (200, "navy"))

    def test_service_list_roundtrip(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "l.json")
        sl = ServiceList()
        self.assertTrue(sl.add("John 3:16", "KJV"))
        self.assertFalse(sl.add("John 3:16", "KJV"))
        sl.add("Rom 8:28", "WEB")
        sl.add("Ps 23:1", "ASV")
        self.assertEqual(sl.move(2, -1), 1)
        self.assertEqual(sl.move(0, -1), 0)
        sl.remove(0)
        sl.save(p)
        self.assertEqual([i["ref"] for i in ServiceList.load(p).items], ["Ps 23:1", "Rom 8:28"])
        self.assertEqual(ServiceList.load(os.path.join(d, "none.json")).items, [])


if __name__ == "__main__":
    unittest.main()
