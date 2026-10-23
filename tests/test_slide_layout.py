"""Headless tests: theme schema v2 (load + legacy fallback), chip text, footer, font-fit helper."""
import json
import os
import tempfile
import unittest
from pathlib import Path

from revelatetw.outputs import (MIN_FIT_PX, chip_text, display_section, fit_font_px, footer_text,
                                sermon_lines, wrap_lines)
from revelatetw.theme import (SCHEMA_VERSION, Background, Theme, import_background_image,
                              resolve_background_image, safe_background_name)


class ThemeSchemaV2(unittest.TestCase):
    def test_new_theme_is_v2_with_navy_gold_gradient_default(self):
        t = Theme()
        self.assertEqual(t.schema_version, SCHEMA_VERSION)
        self.assertEqual(t.background.kind, "linear")
        self.assertEqual(t.background.colors, ["#1E1B4B", "#0F0B2E"])
        self.assertEqual(t.accent_color, "#D4A017")
        t.validate()

    def test_v2_round_trip_keeps_new_fields(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "t.json"
            t = Theme(name="x", accent_color="#FFD700", dim_color="#808080",
                      church_line="Grace Chapel", image_scrim=0.5,
                      background=Background("image", [], image_path="bg.jpg"))
            t.save(p)
            back = Theme.load(p)
            self.assertEqual((back.accent_color, back.dim_color, back.church_line, back.image_scrim),
                             ("#FFD700", "#808080", "Grace Chapel", 0.5))
            self.assertEqual(back.background.image_path, "bg.jpg")

    def test_legacy_v1_file_loads_with_defaults_and_keeps_look(self):
        legacy = {"name": "Old", "background": {"kind": "solid", "colors": ["#000000"]},
                  "reference_color": "#00FF00", "frame": "thin", "font_size_px": 50}
        t = Theme.from_dict(legacy)
        t.validate()
        self.assertEqual(t.schema_version, SCHEMA_VERSION)
        self.assertEqual(t.accent_color, "#00FF00")           # accent follows old reference colour
        self.assertEqual(t.church_line, "")
        self.assertEqual(t.image_scrim, 0.4)
        self.assertEqual(t.background.colors, ["#000000"])
        self.assertTrue(Theme.is_legacy_data(legacy))
        self.assertFalse(Theme.is_legacy_data(Theme().to_dict()))

    def test_legacy_file_on_disk_loads(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "old.json"
            p.write_text(json.dumps({"name": "Old", "frame": "double"}), encoding="utf-8")
            t = Theme.load(p)
            self.assertEqual((t.name, t.frame), ("Old", "double"))

    def test_unknown_keys_ignored(self):
        t = Theme.from_dict({"name": "n", "future_knob": 3, "background": {"kind": "solid", "x": 1}})
        t.validate()

    def test_bad_v2_values_refused(self):
        self.assertTrue(Theme(accent_color="gold").problems())
        self.assertTrue(Theme(image_scrim=2.0).problems())
        self.assertTrue(Theme(background=Background("image", [], image_path=None)).problems())
        self.assertTrue(Theme(background=Background("image", [], image_path="/etc/x.png")).problems())
        self.assertTrue(Theme(background=Background("image", [], image_path="../x.png")).problems())

    def test_ready_made_themes_still_valid(self):
        from revelatetw.theme import ready_made_themes
        for t in ready_made_themes():
            self.assertEqual(t.problems(), [], t.name)

    def test_background_image_must_be_relative_and_resolves_in_folder(self):
        self.assertTrue(safe_background_name("cross.jpg"))
        self.assertFalse(safe_background_name("C:\\x.jpg"))
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            (folder / "cross.jpg").write_bytes(b"x")
            self.assertEqual(resolve_background_image("cross.jpg", folder), folder / "cross.jpg")
            self.assertIsNone(resolve_background_image("missing.jpg", folder))
            self.assertIsNone(resolve_background_image("../cross.jpg", folder))

    def test_import_copies_image_into_folder(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "pic.png"
            src.write_bytes(b"png")
            dest = Path(d) / "backgrounds"
            name = import_background_image(src, dest)
            self.assertEqual(name, "pic.png")
            self.assertTrue((dest / name).is_file())
            with self.assertRaises(ValueError):
                import_background_image(Path(d) / "x.txt", dest)


class ChipAndFooter(unittest.TestCase):
    def test_chorus_chip_text(self):
        self.assertEqual(chip_text("Chorus", 1, 8), "Chorus \u00b7 2/8")
        self.assertEqual(chip_text("Verse 1", 0, 4), "Verse 1 \u00b7 1/4")

    def test_blank_section_shows_position_only(self):
        self.assertEqual(chip_text("", 2, 5), "3/5")
        self.assertEqual(chip_text("  ", 0, 1), "1/1")

    def test_position_clamped_and_empty_song(self):
        self.assertEqual(chip_text("Outro", 99, 3), "Outro \u00b7 3/3")
        self.assertEqual(chip_text("Chorus", 0, 0), "")

    def test_generic_slide_label_hidden(self):
        self.assertEqual(display_section("Slide 3"), "")
        self.assertEqual(display_section("Chorus (cont.)"), "Chorus (cont.)")
        self.assertEqual(display_section("Pre-Chorus"), "Pre-Chorus")

    def test_footer(self):
        self.assertEqual(footer_text("Way Maker", "Sinach"), "Way Maker \u00b7 Sinach")
        self.assertEqual(footer_text("Way Maker", ""), "Way Maker")

    def test_sermon_lines(self):
        s = sermon_lines(" Grace ", "Faith", "", " John 3:16 ")
        self.assertEqual(s, {"church": "Grace", "title": "Faith", "speaker": "", "reference": "John 3:16"})


def _measure(text, px):
    return (int(len(text) * px * 0.5), px)


class FontFit(unittest.TestCase):
    def test_short_text_keeps_start_size(self):
        self.assertEqual(fit_font_px(["Hi"], 1000, 500, 64, 1.3, _measure), 64)

    def test_long_text_shrinks_into_box(self):
        lines = ["word " * 60]
        px = fit_font_px(lines, 800, 300, 96, 1.3, _measure)
        self.assertLess(px, 96)
        self.assertGreaterEqual(px, MIN_FIT_PX)
        wrapped = wrap_lines(lines[0], 800, px, _measure)
        self.assertLessEqual(len(wrapped) * px * 1.3, 300 + px * 1.3)

    def test_never_below_floor(self):
        px = fit_font_px(["x " * 2000], 50, 20, 200, 1.3, _measure)
        self.assertEqual(px, MIN_FIT_PX)

    def test_wrap_breaks_on_words_and_splits_long_words(self):
        self.assertEqual(wrap_lines("one two three", 60, 10, _measure), ["one two", "three"])
        parts = wrap_lines("supercalifragilistic", 40, 10, _measure)
        self.assertGreater(len(parts), 1)
        self.assertEqual("".join(parts), "supercalifragilistic")

    def test_degenerate_box(self):
        self.assertEqual(fit_font_px(["a"], 0, 100, 50, 1.3, _measure), MIN_FIT_PX)


if __name__ == "__main__":
    unittest.main()
