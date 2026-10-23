"""Headless tests for the ffmpeg/ffprobe resolver: order, caching, fallback text. Uses fakes only."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from revelatetw import fftools as f


def _tool(folder: Path, name: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    p = folder / name
    p.write_bytes(b"x")
    return p


def _which_from(mapping):
    return lambda name: mapping.get(name)


class ResolverOrderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.bundled = self.tmp / "app" / "assets" / "bin"
        self.settings = self.tmp / "custom"
        self.sys_dir = self.tmp / "syspath"

    def test_bundled_wins_over_settings_and_path(self):
        _tool(self.bundled, "ffmpeg.exe")
        _tool(self.bundled, "ffprobe.exe")
        _tool(self.settings, "ffmpeg.exe")
        _tool(self.settings, "ffprobe.exe")
        sys_ff = str(_tool(self.sys_dir, "ffmpeg"))
        sys_fp = str(_tool(self.sys_dir, "ffprobe"))
        t = f.locate(bundled=[self.bundled], configured_dir=self.settings,
                     which=_which_from({"ffmpeg": sys_ff, "ffprobe": sys_fp}))
        self.assertEqual(t.ffmpeg.source, f.SOURCE_BUNDLED)
        self.assertEqual(t.ffprobe.source, f.SOURCE_BUNDLED)
        self.assertTrue(t.ffmpeg.path.endswith("ffmpeg.exe"))

    def test_plain_names_next_to_package_count_as_bundled(self):
        _tool(self.bundled, "ffmpeg")       # no .exe, e.g. Linux or macOS dev box
        t = f.locate(bundled=[self.bundled], configured_dir=None, which=_which_from({}))
        self.assertEqual(t.ffmpeg.source, f.SOURCE_BUNDLED)
        self.assertIsNone(t.ffprobe.path)

    def test_settings_wins_over_path_when_no_bundle(self):
        _tool(self.settings, "ffmpeg.exe")
        _tool(self.settings, "ffprobe.exe")
        sys_ff = str(_tool(self.sys_dir, "ffmpeg"))
        t = f.locate(bundled=[self.tmp / "none"], configured_dir=self.settings,
                     which=_which_from({"ffmpeg": sys_ff, "ffprobe": sys_ff}))
        self.assertEqual(t.ffmpeg.source, f.SOURCE_SETTINGS)
        self.assertEqual(t.ffprobe.source, f.SOURCE_SETTINGS)

    def test_settings_folder_may_point_at_a_bin_subfolder(self):
        _tool(self.settings / "bin", "ffprobe.exe")
        t = f.locate(bundled=[], configured_dir=self.settings, which=_which_from({}))
        self.assertEqual(t.ffprobe.source, f.SOURCE_SETTINGS)
        self.assertIsNone(t.ffmpeg.path)

    def test_path_used_when_nothing_else(self):
        sys_ff = str(_tool(self.sys_dir, "ffmpeg"))
        sys_fp = str(_tool(self.sys_dir, "ffprobe"))
        t = f.locate(bundled=[self.tmp / "none"], configured_dir=None,
                     which=_which_from({"ffmpeg": sys_ff, "ffprobe": sys_fp}))
        self.assertEqual(t.ffmpeg, f.ToolPath(sys_ff, f.SOURCE_SYSTEM))
        self.assertEqual(t.ffprobe, f.ToolPath(sys_fp, f.SOURCE_SYSTEM))

    def test_none_when_nothing_anywhere(self):
        t = f.locate(bundled=[self.tmp / "none"], configured_dir=self.tmp / "missing",
                     which=_which_from({}))
        self.assertFalse(t.found)
        self.assertEqual(t.ffmpeg, f.ToolPath(None, None))

    def test_bundled_ffprobe_with_path_ffmpeg_mixes_sources(self):
        _tool(self.bundled, "ffprobe.exe")
        sys_ff = str(_tool(self.sys_dir, "ffmpeg"))
        t = f.locate(bundled=[self.bundled], configured_dir=None, which=_which_from({"ffmpeg": sys_ff}))
        self.assertEqual(t.ffprobe.source, f.SOURCE_BUNDLED)
        self.assertEqual(t.ffmpeg.source, f.SOURCE_SYSTEM)


class CacheAndStatusTests(unittest.TestCase):
    def setUp(self):
        f.reset_cache()
        f._configured_dir = None
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        f.reset_cache()
        f._configured_dir = None

    def test_lookup_is_cached(self):
        before = f._locate_calls
        with mock.patch.object(f, "locate", wraps=f.locate) as loc:
            with mock.patch("shutil.which", return_value=None):
                f.get_tools()
                f.get_tools()
                f.ffmpeg_path()
                f.ffprobe_path()
        self.assertEqual(loc.call_count, 1)
        self.assertEqual(f._locate_calls - before, 1)

    def test_refresh_forces_new_lookup(self):
        with mock.patch("shutil.which", return_value=None):
            f.get_tools()
            with mock.patch.object(f, "locate", wraps=f.locate) as loc:
                f.get_tools(refresh=True)
        self.assertEqual(loc.call_count, 1)

    def test_changing_settings_folder_clears_cache(self):
        with mock.patch("shutil.which", return_value=None):
            f.get_tools()
        self.assertIsNotNone(f._cache)
        f.set_configured_dir(str(self.tmp))
        self.assertIsNone(f._cache)
        with mock.patch("shutil.which", return_value=None):
            f.get_tools()
        self.assertIsNotNone(f._cache)
        f.set_configured_dir(str(self.tmp))       # same value: keep the cache
        self.assertIsNotNone(f._cache)

    def test_fallback_text_when_nothing_found(self):
        self.assertEqual(f.status_text(f.Tools(f.ToolPath(None, None), f.ToolPath(None, None))),
                         "ffmpeg: not found, video details unavailable")

    def test_status_text_names_source(self):
        ok_b = f.Tools(f.ToolPath("a", f.SOURCE_BUNDLED), f.ToolPath("b", f.SOURCE_BUNDLED))
        ok_s = f.Tools(f.ToolPath("a", f.SOURCE_SYSTEM), f.ToolPath("b", f.SOURCE_SYSTEM))
        self.assertEqual(f.status_text(ok_b), "ffmpeg: bundled")
        self.assertEqual(f.status_text(ok_s), "ffmpeg: system")

    def test_media_duration_falls_back_to_unknown_without_ffprobe(self):
        from revelatetw import media
        with mock.patch("shutil.which", return_value=None), \
             mock.patch.object(f, "locate", return_value=f.Tools(f.ToolPath(None, None), f.ToolPath(None, None))):
            f.reset_cache()
            self.assertIsNone(media.probe_duration(self.tmp / "clip.mp4"))
            self.assertFalse(media.make_thumbnail(self.tmp / "clip.mp4", self.tmp / "t.jpg", "video"))


class FetchScriptTests(unittest.TestCase):
    """scripts/fetch_ffmpeg.py: zip extraction and the size checks, with a fake archive. No network."""

    @classmethod
    def setUpClass(cls):
        import importlib.util, zipfile
        spec = importlib.util.spec_from_file_location(
            "fetch_ffmpeg", Path(__file__).resolve().parent.parent / "scripts" / "fetch_ffmpeg.py")
        cls.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.mod)
        cls.tmp = Path(tempfile.mkdtemp())
        cls.zip = cls.tmp / "fake.zip"
        with zipfile.ZipFile(cls.zip, "w") as zf:
            zf.writestr("ffmpeg-7.0-essentials/bin/ffmpeg.exe", b"0" * (1024 * 1024 + 10))
            zf.writestr("ffmpeg-7.0-essentials/bin/ffprobe.exe", b"0" * (1024 * 1024 + 20))
            zf.writestr("ffmpeg-7.0-essentials/doc/readme.txt", b"hi")

    def test_extracts_bin_tools_from_any_top_folder(self):
        dest = Path(tempfile.mkdtemp()) / "bin"
        written = self.mod.extract_tools(self.zip, dest)
        self.assertEqual(sorted(p.name for p in written), ["ffmpeg.exe", "ffprobe.exe"])
        self.assertTrue((dest / "ffprobe.exe").is_file())

    def test_small_exe_is_rejected(self):
        import zipfile
        bad = self.tmp / "small.zip"
        with zipfile.ZipFile(bad, "w") as zf:
            zf.writestr("x/bin/ffmpeg.exe", b"0" * 100)
            zf.writestr("x/bin/ffprobe.exe", b"0" * 100)
        with self.assertRaises(SystemExit):
            self.mod.extract_tools(bad, Path(tempfile.mkdtemp()) / "bin")

    def test_sha_mismatch_installs_nothing(self):
        dest = Path(tempfile.mkdtemp()) / "bin"
        with mock.patch.object(self.mod, "MIN_ZIP_BYTES", 1):
            rc = self.mod.main(["--zip", str(self.zip), "--dest", str(dest), "--sha256", "00" * 32,
                                "--no-run-check"])
        self.assertEqual(rc, 1)
        self.assertFalse((dest / "ffmpeg.exe").exists())
