"""Headless tests for the media library: scan, index cache, search/filter, import."""
import json
import tempfile
import unittest
from pathlib import Path

from revelatetw import media as m


def _fake_probe(duration):
    calls = []

    def probe(path):
        calls.append(Path(path).name)
        return duration

    probe.calls = calls
    return probe


def _fake_thumb(calls):
    def make(src, dst, kind):
        calls.append(Path(src).name)
        dst.write_bytes(b"jpg")
        return True
    return make


class MediaKindTests(unittest.TestCase):
    def test_extensions_case_insensitive(self):
        self.assertEqual(m.media_kind("a.PNG"), "image")
        self.assertEqual(m.media_kind("b.Jpeg"), "image")
        self.assertEqual(m.media_kind("c.MKV"), "video")
        self.assertIsNone(m.media_kind("d.txt"))
        self.assertIsNone(m.media_kind("e.mp3"))

    def test_duration_label(self):
        self.assertEqual(m.format_duration(75.4), "1:15")
        self.assertEqual(m.format_duration(3725), "1:02:05")
        self.assertEqual(m.parse_duration_output("12.5\n"), 12.5)
        self.assertIsNone(m.parse_duration_output(""))
        self.assertIsNone(m.parse_duration_output("N/A"))
        self.assertIsNone(m.parse_duration_output("-3"))


class ScanTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self._tmp.name) / "media"
        self.folder.mkdir()
        (self.folder / "Welcome.png").write_bytes(b"png")
        (self.folder / "loop.mp4").write_bytes(b"mp4data")
        (self.folder / "notes.txt").write_text("skip me")

    def tearDown(self):
        self._tmp.cleanup()

    def test_scan_finds_only_media_with_types_and_duration(self):
        probe = _fake_probe(42.0)
        lib = m.MediaLibrary(self.folder, probe=probe, make_thumb=_fake_thumb([]))
        items = lib.rescan()
        self.assertEqual([i.name for i in items], ["loop", "Welcome"])
        video = items[0]
        self.assertTrue(video.is_video)
        self.assertEqual(video.duration_label(), "0:42")
        self.assertEqual(items[1].duration_label(), "")
        self.assertEqual(lib.probe_calls, 1)

    def test_unknown_duration_when_probe_fails(self):
        lib = m.MediaLibrary(self.folder, probe=_fake_probe(None), make_thumb=_fake_thumb([]))
        video = [i for i in lib.rescan() if i.is_video][0]
        self.assertIsNone(video.duration_s)
        self.assertEqual(video.duration_label(), "length unknown")

    def test_index_cache_skips_probe_and_thumb_on_second_scan(self):
        probe = _fake_probe(10.0)
        thumbs = []
        lib = m.MediaLibrary(self.folder, probe=probe, make_thumb=_fake_thumb(thumbs))
        lib.rescan()
        self.assertTrue((self.folder / m.INDEX_NAME).is_file())
        first_thumbs = len(thumbs)

        lib2 = m.MediaLibrary(self.folder, probe=probe, make_thumb=_fake_thumb(thumbs))
        items = lib2.rescan()
        self.assertEqual(lib2.probe_calls, 0)
        self.assertEqual(len(thumbs), first_thumbs)
        self.assertEqual([i.name for i in items], ["loop", "Welcome"])
        self.assertTrue(all(i.thumb for i in items))

    def test_changed_file_is_reindexed(self):
        lib = m.MediaLibrary(self.folder, probe=_fake_probe(10.0), make_thumb=_fake_thumb([]))
        lib.rescan()
        (self.folder / "loop.mp4").write_bytes(b"a much longer mp4 payload")
        lib2 = m.MediaLibrary(self.folder, probe=_fake_probe(99.0), make_thumb=_fake_thumb([]))
        items = lib2.rescan()
        video = [i for i in items if i.is_video][0]
        self.assertEqual(video.duration_s, 99.0)
        self.assertEqual(lib2.probe_calls, 1)

    def test_deleted_file_drops_out_of_scan(self):
        lib = m.MediaLibrary(self.folder, probe=_fake_probe(1.0), make_thumb=_fake_thumb([]))
        lib.rescan()
        (self.folder / "Welcome.png").unlink()
        self.assertEqual([i.name for i in lib.rescan()], ["loop"])

    def test_corrupt_index_is_ignored_not_fatal(self):
        (self.folder / m.INDEX_NAME).write_text("{not json", encoding="utf-8")
        lib = m.MediaLibrary(self.folder, probe=_fake_probe(5.0), make_thumb=_fake_thumb([]))
        self.assertEqual(len(lib.rescan()), 2)

    def test_load_cached_reads_index_without_probing(self):
        lib = m.MediaLibrary(self.folder, probe=_fake_probe(7.0), make_thumb=_fake_thumb([]))
        lib.rescan()
        fresh = m.MediaLibrary(self.folder, probe=_fake_probe(0.0), make_thumb=_fake_thumb([]))
        items = fresh.load_cached()
        self.assertEqual(fresh.probe_calls, 0)
        self.assertEqual([i.name for i in items], ["loop", "Welcome"])
        self.assertEqual(items[0].duration_s, 7.0)

    def test_broken_thumbnail_does_not_stop_scan(self):
        def boom(src, dst, kind):
            raise RuntimeError("bad file")
        lib = m.MediaLibrary(self.folder, probe=_fake_probe(1.0), make_thumb=boom)
        items = lib.rescan()
        self.assertEqual(len(items), 2)
        self.assertTrue(all(i.thumb == "" for i in items))

    def test_index_version_mismatch_is_ignored(self):
        (self.folder / m.INDEX_NAME).write_text(json.dumps({"version": 99, "items": []}), encoding="utf-8")
        lib = m.MediaLibrary(self.folder, probe=_fake_probe(1.0), make_thumb=_fake_thumb([]))
        self.assertEqual(len(lib.rescan()), 2)


class SearchAndImportTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.folder = self.root / "media"
        self.items = [
            m.MediaItem(path="x/Sunrise Hymn.jpg", name="Sunrise Hymn", kind="image"),
            m.MediaItem(path="x/sunset loop.mp4", name="sunset loop", kind="video", duration_s=5),
            m.MediaItem(path="x/Welcome Slide.png", name="Welcome Slide", kind="image"),
        ]

    def tearDown(self):
        self._tmp.cleanup()

    def test_filter_by_type_and_search(self):
        self.assertEqual(len(m.filter_items(self.items, "", "all")), 3)
        self.assertEqual([i.name for i in m.filter_items(self.items, "", "images")],
                         ["Sunrise Hymn", "Welcome Slide"])
        self.assertEqual([i.name for i in m.filter_items(self.items, "", "videos")], ["sunset loop"])
        self.assertEqual([i.name for i in m.filter_items(self.items, "SUN")],
                         ["Sunrise Hymn", "sunset loop"])
        self.assertEqual([i.name for i in m.filter_items(self.items, "sun", "video")], ["sunset loop"])
        self.assertEqual(m.filter_items(self.items, "nope"), [])

    def test_multi_word_search_needs_every_word(self):
        self.assertEqual([i.name for i in m.filter_items(self.items, "welcome slide")], ["Welcome Slide"])
        self.assertEqual(m.filter_items(self.items, "welcome hymn"), [])

    def test_import_copies_media_and_skips_others_without_overwriting(self):
        src = self.root / "src"
        src.mkdir()
        (src / "pic.png").write_bytes(b"one")
        (src / "doc.pdf").write_bytes(b"pdf")
        lib = m.MediaLibrary(self.folder, probe=_fake_probe(1.0), make_thumb=_fake_thumb([]))
        copied, skipped = lib.import_files([src / "pic.png", src / "doc.pdf"])
        self.assertEqual([p.name for p in copied], ["pic.png"])
        self.assertEqual(skipped, ["doc.pdf"])
        copied2, _ = lib.import_files([src / "pic.png"])
        self.assertEqual(copied2[0].name, "pic (2).png")
        self.assertEqual((self.folder / "pic.png").read_bytes(), b"one")
        self.assertEqual(len(lib.rescan()), 2)


if __name__ == "__main__":
    unittest.main()
