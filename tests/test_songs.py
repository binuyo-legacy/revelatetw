import json
import pytest

from revelatetw.songs import Song, SongLibrary, Slide, normalize_label, split_lyrics
from revelatetw.sermon import SermonInfo


LYRICS = """[Verse 1]
Amazing grace how sweet the sound
That saved a wretch like me

Chorus:
I once was lost but now am found
Was blind but now I see
"""


def test_split_labels_sections_and_blank_lines():
    slides = split_lyrics(LYRICS)
    assert [s.label for s in slides] == ["Verse 1", "Chorus"]
    assert slides[0].lines == ["Amazing grace how sweet the sound", "That saved a wretch like me"]
    assert slides[1].lines[1] == "Was blind but now I see"


def test_split_caps_lines_per_slide_and_marks_continuation():
    text = "Verse 1\na\nb\nc\nd\ne"
    slides = split_lyrics(text, max_lines=2)
    assert [s.label for s in slides] == ["Verse 1", "Verse 1 (cont.)", "Verse 1 (cont.)"]
    assert [len(s.lines) for s in slides] == [2, 2, 1]


def test_unlabelled_blocks_get_numbered_names_and_lyric_word_is_not_a_header():
    slides = split_lyrics("Tag along with me\n\nSecond block here")
    assert [s.label for s in slides] == ["Slide 1", "Slide 2"]
    assert slides[0].lines == ["Tag along with me"]


def test_split_rejects_bad_max_lines():
    with pytest.raises(ValueError):
        split_lyrics("x", max_lines=0)


def test_split_empty_text_gives_no_slides():
    assert split_lyrics("   \n\n  ") == []


@pytest.mark.parametrize("raw,expected", [("verse 1", "Verse 1"), ("PRE-CHORUS", "Pre-Chorus"),
                                          ("  chorus   2 ", "Chorus 2")])
def test_normalize_label(raw, expected):
    assert normalize_label(raw) == expected


def test_song_requires_title_and_safe_id():
    with pytest.raises(ValueError):
        Song(title="   ")
    with pytest.raises(ValueError):
        Song(title="x", id="../evil")


def test_song_round_trip_and_library_save_load_search(tmp_path):
    lib = SongLibrary(tmp_path / "songs")
    song = Song(title="Amazing Grace", artist="John Newton", slides=split_lyrics(LYRICS))
    path = lib.save(song)
    assert path.exists() and json.loads(path.read_text())["format"] == "revelatetw-song"
    other = Song(title="Be Thou My Vision", slides=[Slide("Verse 1", ["Be thou my vision"])])
    lib.save(other)
    loaded = lib.load_all()
    assert [s.title for s in loaded] == ["Amazing Grace", "Be Thou My Vision"]
    assert loaded[0].slides[1].lines[0] == "I once was lost but now am found"
    assert [s.title for s in lib.search("newton")] == ["Amazing Grace"]
    assert [s.title for s in lib.search("found see")] == ["Amazing Grace"]
    assert lib.search("zzz") == []
    assert len(lib.search("")) == 2


def test_save_refuses_song_without_slides(tmp_path):
    with pytest.raises(ValueError):
        SongLibrary(tmp_path).save(Song(title="Empty"))


def test_corrupt_song_file_is_skipped(tmp_path):
    lib = SongLibrary(tmp_path)
    lib.save(Song(title="Good", slides=[Slide("Verse 1", ["ok"])]))
    (tmp_path / "bad.json").write_text("{not json")
    assert [s.title for s in lib.load_all()] == ["Good"]


def test_sermon_info_lines_skip_empty_fields():
    assert SermonInfo(title="Faith", reference="John 3:16 (KJV)").lines() == ["Faith", "John 3:16 (KJV)"]
    assert SermonInfo().lines() == []
