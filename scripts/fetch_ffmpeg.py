"""Download a static Windows x64 ffmpeg build and place ffmpeg.exe and ffprobe.exe in the app's bin folder.

Run this on a machine with internet before building the installer:
    python scripts/fetch_ffmpeg.py
The binaries go to revelatetw/assets/bin/ (or --dest). They are NOT committed to git
(see .gitignore). The app finds them there first, so end users install nothing.

Source: gyan.dev release builds (https://www.gyan.dev/ffmpeg/builds/). The default is the
"release-essentials" zip. Check that build's license before commercial distribution (see SETUP.md).

Safety checks:
  - the zip must be a valid archive containing bin/ffmpeg.exe and bin/ffprobe.exe
  - size sanity: the zip must be at least 20 MB, each exe at least 1 MB
  - SHA-256: pass --sha256 <hex> to pin the exact build (recommended for releases). Without it the
    script prints the computed hash so you can record and verify it. gyan.dev publishes a
    checksum next to each build, which can be compared by hand.
  - the exes are run once with -version to confirm they work (skip with --no-run-check)
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

DEFAULT_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DEST = REPO_ROOT / "revelatetw" / "assets" / "bin"
MIN_ZIP_BYTES = 20 * 1024 * 1024
MIN_EXE_BYTES = 1 * 1024 * 1024
TOOLS = ("ffmpeg.exe", "ffprobe.exe")


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, target: Path) -> None:
    print(f"downloading {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "revelatetw-fetch-ffmpeg/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp, target.open("wb") as out:
        shutil.copyfileobj(resp, out, length=1 << 20)


def extract_tools(zip_path: Path, dest: Path) -> list[Path]:
    """Copy bin/ffmpeg.exe and bin/ffprobe.exe out of the zip (any top folder name works)."""
    if not zipfile.is_zipfile(zip_path):
        raise SystemExit(f"not a zip archive: {zip_path}")
    dest.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    with zipfile.ZipFile(zip_path) as zf:
        for tool in TOOLS:
            members = [m for m in zf.namelist() if m.replace("\\", "/").split("/")[-2:] == ["bin", tool]]
            if not members:
                raise SystemExit(f"{tool} not found under bin/ in the archive")
            member = members[0]
            out = dest / tool
            with zf.open(member) as src, out.open("wb") as dst:
                shutil.copyfileobj(src, dst, length=1 << 20)
            if out.stat().st_size < MIN_EXE_BYTES:
                raise SystemExit(f"{tool} is suspiciously small ({out.stat().st_size} bytes); aborting")
            written.append(out)
    return written


def run_check(exe: Path) -> str:
    r = subprocess.run([str(exe), "-version"], capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise SystemExit(f"{exe.name} -version failed (exit {r.returncode})")
    return (r.stdout.splitlines() or ["?"])[0]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dest", type=Path, default=DEFAULT_DEST, help="folder for ffmpeg.exe and ffprobe.exe")
    ap.add_argument("--url", default=DEFAULT_URL, help="zip URL (default: gyan.dev release-essentials)")
    ap.add_argument("--zip", type=Path, help="use an already downloaded zip instead of fetching")
    ap.add_argument("--sha256", help="expected SHA-256 of the zip (recommended)")
    ap.add_argument("--force", action="store_true", help="overwrite existing ffmpeg.exe/ffprobe.exe")
    ap.add_argument("--no-run-check", action="store_true", help="skip running -version on the result")
    args = ap.parse_args(argv)

    dest: Path = args.dest.resolve()
    existing = [dest / t for t in TOOLS if (dest / t).exists()]
    if existing and not args.force:
        print(f"already present: {', '.join(p.name for p in existing)} in {dest}. Use --force to replace.")
        return 0

    with tempfile.TemporaryDirectory() as tmp:
        zip_path = Path(args.zip) if args.zip else Path(tmp) / "ffmpeg.zip"
        if not args.zip:
            try:
                download(args.url, zip_path)
            except Exception as exc:  # network errors: say what happened, no traceback spam
                print(f"download failed: {exc}", file=sys.stderr)
                return 1
        size = zip_path.stat().st_size
        if size < MIN_ZIP_BYTES:
            print(f"download too small ({size} bytes), expected a full build. Aborting.", file=sys.stderr)
            return 1
        digest = sha256_of(zip_path)
        print(f"zip size {size} bytes, sha256 {digest}")
        if args.sha256 and digest.lower() != args.sha256.strip().lower():
            print("SHA-256 mismatch: the file is not the build you pinned. Nothing was installed.", file=sys.stderr)
            return 1
        if not args.sha256:
            print("no --sha256 given: check this hash against the build's published checksum.")

        written = extract_tools(zip_path, dest)

    for exe in written:
        print(f"installed {exe} ({exe.stat().st_size} bytes)")
    if not args.no_run_check:
        for exe in written:
            print(run_check(exe))
    print("done. The app will use these automatically (Settings > Output shows 'ffmpeg: bundled').")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
