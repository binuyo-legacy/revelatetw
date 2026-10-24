"""Song import/export: .rtsong round trip, raw-text splitting, validation, duplicates, many songs."""
import json

import pytest

from revelatetw.song_io import (EXTENSION, SongFileError, build_document, export_song, export_songs,
                                import_file, import_text, parse_rtsong, plan_import, slide_counts,
                                unique_title)
from revelatetw.songs import Slide, Song, SongLibrary, header_label, split_blocks, split_lyrics


def _song(title="Amazing Grace", artist="John Newton"):
    return Song(title=title, artist=artist, slides=[
        Slide("Verse 1", ["Amazing grace how sweet the sound", "That saved a wretch like me"]),
        Slide("Chorus", ["My chains are gone", "I've been set free"]),
        Slide("Verse 2", ["Through many dangers toils and snares"]),
    ])


def _sections(song):
    return [(s.label, list(s.lines)) for s in song.slides]


# ---- export round trip

def test_export_import_round_trip_keeps_sections(tmp_path):
    src = _song()
    path = export_song(src, tmp_path / ("grace" + EXTENSION))
    batch = import_file(path)
    assert batch.kind == "rtsong"
    assert len(batch.songs) == 1
    got = batch.songs[0]
    assert got.title == src.title
    assert got.artist == src.artist
    assert _sections(got) == _sections(src)


def test_export_writes_format_and_version(tmp_path):
    path = export_song(_song(), tmp_path / "x.rtsong")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["format"] == "rtsong"
    assert data["version"] == 1
    assert data["songs"][0]["sections"][0] == {"label": "Verse 1",
                                               "lines": ["Amazing grace how sweet the sound",
                                                         "That saved a wretch like me"]}


def test_author_omitted_when_unset(tmp_path):
    path = export_song(_song(artist=""), tmp_path / "x.rtsong")
    assert "author" not in json.loads(path.read_text(encoding="utf-8"))["songs"][0]


# ---- library export/import of many songs

def test_library_export_and_import_many_songs(tmp_path):
    songs = [_song(f"Song {i}") for i in range(60)]
    path = export_songs(songs, tmp_path / "set.rtsong")
    batch = import_file(path)
    assert [s.title for s in batch.songs] == [f"Song {i}" for i in range(60)]
    assert all(_sections(a) == _sections(b) for a, b in zip(songs, batch.songs))


# ---- raw text splitting

def test_raw_text_labels_and_blank_lines():
    text = "Amazing Grace\n\nVerse 1:\nline a\nline b\n\nChorus\nline c\n\nline d"
    slides = split_lyrics(text)
    assert len(slides) == 4
    assert slides[0].label == "Slide 1" and slides[0].lines == ["Amazing Grace"]
    assert slides[1].label == "Verse 1" and slides[1].lines == ["line a", "line b"]
    assert slides[2].label == "Chorus" and slides[2].lines == ["line c"]


@pytest.mark.parametrize("line,expected", [
    ("V1", "Verse 1"), ("v2", "Verse 2"), ("C", "Chorus"), ("CH 2", "Chorus 2"),
    ("Chorus:", "Chorus"), ("[Bridge]", "Bridge"), ("PC", "Pre-Chorus"), ("Verse 1:", "Verse 1"),
])
def test_header_abbreviations_and_colon(line, expected):
    assert header_label(line) == expected


@pytest.mark.parametrize("line", ["c", "b", "A", "Ab", "Tag along with me", "vs the world"])
def test_lowercase_single_letters_and_lyric_words_are_not_headers(line):
    assert header_label(line) is None


def test_repeated_block_is_lyric_text_not_auto_tagged_when_labelled():
    text = "Chorus\nla la\n\nVerse 1\nx\n\nChorus\nla la"
    labels = [s.label for s in split_lyrics(text)]
    assert labels == ["Chorus", "Verse 1", "Chorus"]


def test_split_blocks_ends_on_header_and_blank():
    blocks = split_blocks("Verse 1\na\nb\nChorus\nc")
    assert blocks == [("Verse 1", ["a", "b"]), ("Chorus", ["c"])]


def test_max_lines_creates_continuation():
    slides = split_lyrics("Verse 1\na\nb\nc\nd\ne", max_lines=2)
    assert [s.label for s in slides] == ["Verse 1", "Verse 1 (cont.)", "Verse 1 (cont.)"]


def test_slide_counts_summary():
    slides = [Slide("Verse 1", ["a"]), Slide("Verse 2", ["b"]), Slide("Chorus", ["c"]),
              Slide("Chorus (cont.)", ["d"])]
    assert slide_counts(slides) == "4 slides: 2 verses, 2 choruses"


def test_pasted_text_import_uses_first_line_as_title():
    batch = import_text("Blessed Assurance\n\nVerse 1\nthis is my story")
    assert batch.kind == "text"
    assert batch.songs[0].title == "Blessed Assurance"
    assert batch.format_label == "pasted lyrics \u00b7 1 song detected"


# ---- schema and version validation

def test_newer_version_is_refused(tmp_path):
    doc = build_document([_song()])
    doc["version"] = 2
    with pytest.raises(SongFileError, match="version"):
        parse_rtsong(json.dumps(doc))


def test_wrong_format_name_is_refused():
    with pytest.raises(SongFileError):
        parse_rtsong(json.dumps({"format": "something-else", "version": 1, "songs": []}))


def test_missing_title_is_refused():
    doc = {"format": "rtsong", "version": 1, "songs": [{"sections": []}]}
    with pytest.raises(SongFileError):
        parse_rtsong(json.dumps(doc))


def test_unknown_keys_are_ignored():
    doc = build_document([_song()])
    doc["created_by"] = "another tool"
    doc["songs"][0]["tempo"] = 72
    assert parse_rtsong(json.dumps(doc))[0].title == "Amazing Grace"


def test_malformed_rtsong_file_reports_clear_error(tmp_path):
    bad = tmp_path / "broken.rtsong"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(SongFileError, match="not valid JSON|could not|JSON"):
        import_file(bad)


def test_rtsong_with_no_songs_is_refused():
    with pytest.raises(SongFileError):
        parse_rtsong(json.dumps({"format": "rtsong", "version": 1, "songs": []}))


def test_empty_paste_is_refused():
    with pytest.raises(SongFileError):
        import_text("   \n  ")


# ---- duplicates

def test_unique_title_suffix_logic():
    assert unique_title("Grace", set()) == "Grace"
    assert unique_title("grace", {"grace"}) == "grace (2)"
    assert unique_title("Grace", {"grace", "grace (2)"}) == "Grace (3)"


def test_duplicate_in_library_gets_suffix_by_default(tmp_path):
    lib = SongLibrary(tmp_path)
    lib.save(_song())
    plan = plan_import([_song()], lib.load_all(), replace=False)
    assert plan[0].action == "renamed"
    assert plan[0].title == "Amazing Grace (2)"


def test_replace_keeps_existing_id(tmp_path):
    lib = SongLibrary(tmp_path)
    original = _song()
    lib.save(original)
    plan = plan_import([_song()], lib.load_all(), replace=True)
    assert plan[0].action == "replace"
    assert plan[0].song.id == original.id


def test_duplicates_within_one_batch_are_suffixed(tmp_path):
    plan = plan_import([_song("Grace"), _song("Grace")], [], replace=False)
    assert [p.title for p in plan] == ["Grace", "Grace (2)"]
