"""Bible file converter for Lite (no Qt). It reuses the main app's own converter, so USFM, OSIS and plain
text files are read exactly the same way in both editions, and the pack it writes is the same
.sqlite file the main app writes (tables verses and meta). Nothing new is installed.

Only the Python standard library is used (re, sqlite3, xml.etree), so no extra packages are needed on
the Windows 8.1 32-bit PC. A file is read in one go; a whole Bible is only a few MB of text.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from revelatetw.bible import BibleImportError, ID_RE, RESERVED_IDS  # noqa: E402
from revelatetw.bible_import import (SUPPORTED_FORMATS_HELP, UnsupportedFormatError,  # noqa: E402,F401
                                     convert_file, write_import)

FILE_FILTER = "Bible files (*.usfm *.usfm3 *.sfm *.osis *.xml *.txt)"
MAX_FILE_MB = 60   # a whole Bible is a few MB; far bigger is not a Bible text and could exhaust a 2 GB PC


def convert(path):
    """Read and parse a Bible file. Raises BibleImportError with a plain message. Saves nothing."""
    try:
        size = os.path.getsize(path)
    except OSError:
        raise BibleImportError("%s was not found" % os.path.basename(str(path)))
    if size > MAX_FILE_MB * 1024 * 1024:
        raise BibleImportError("%s is %d MB, far larger than a Bible text file. Choose the USFM, OSIS or "
                               "text file itself." % (os.path.basename(str(path)), size // (1024 * 1024)))
    return convert_file(path)


def check_code(code, taken):
    """Plain-language problem with a short code, or '' when fine. taken = codes already installed."""
    code = (code or "").strip()
    if not ID_RE.match(code):
        return "Short code must be 2 to 16 letters, digits, - or _ (for example NKJV)."
    if code.upper() in RESERVED_IDS or code.upper() in {t.upper() for t in taken}:
        return "%s is already installed. Pick another short code." % code
    return ""


def save(result, name, code, license_text, user_folder, taken=()):
    """Write the converted Bible as <code>.sqlite in user_folder (created on first use).
    Never overwrites an installed translation. Returns the code."""
    problem = check_code(code, taken)
    if problem:
        raise BibleImportError(problem)
    tr = write_import(result, name=name, code=code.strip(), license_text=license_text, folder=user_folder)
    return tr.id


def remove(code, store):
    """Delete a Bible the church imported. Bundled packs are never removed. True when deleted."""
    if not store.is_user_imported(code):
        return False
    path = os.path.join(store.user_directory, code + ".sqlite")
    store.close()
    os.remove(path)
    return True
