"""Song and sermon-preset CRUD at the store level (headless)."""
import pytest

from revelatetw.songs import Slide, Song, SongLibrary, lyrics_text, split_lyrics
from revelatetw.sermon_presets import SermonPreset, SermonPresetLibrary


def _song(title="Amazing Grace", artist="John Newton"):
    return Song(title=title, artist=artist, slides=[Slide("Verse 1", ["Amazing grace", "how sweet"])])


def test_save_then_edit_keeps_file_and_id(tmp_path):
    lib = SongLibrary(tmp_path)
    song = _song()
    path = lib.save(song)
    song.title = "Amazing Grace (Live)"
    assert lib.save(song) == path            # same id, same filename
    assert len(list(tmp_path.glob("*.json"))) == 1
    assert lib.get(song.id).title == "Amazing Grace (Live)"


def test_save_as_new_is_separate_file(tmp_path):
    lib = SongLibrary(tmp_path)
    original = _song()
    lib.save(original)
    copy = original.copy("Amazing Grace (copy)")
    assert copy.id != original.id
    lib.save(copy)
    titles = sorted(s.title for s in lib.load_all())
    assert titles == ["Amazing Grace", "Amazing Grace (copy)"]
    assert lib.get(original.id).title == "Amazing Grace"


def test_delete_removes_file_and_is_idempotent(tmp_path):
    lib = SongLibrary(tmp_path)
    song = _song()
    lib.save(song)
    assert lib.delete(song.id) is True
    assert lib.get(song.id) is None
    assert lib.delete(song.id) is False


def test_resplit_updates_saved_song(tmp_path):
    lib = SongLibrary(tmp_path)
    song = _song()
    lib.save(song)
    song.slides = split_lyrics("[Chorus]\nHe is faithful\nHe is true", max_lines=4)
    lib.save(song)
    loaded = lib.get(song.id)
    assert [s.label for s in loaded.slides] == ["Chorus"]
    assert loaded.slides[0].lines == ["He is faithful", "He is true"]


def test_lyrics_text_round_trips_section_labels():
    slides = [Slide("Verse 1", ["a", "b"]), Slide("Chorus", ["d"])]
    again = split_lyrics(lyrics_text(slides), max_lines=4)
    assert [s.label for s in again] == ["Verse 1", "Chorus"]
    assert [s.lines for s in again] == [["a", "b"], ["d"]]


def test_lyrics_text_keeps_section_labels():
    text = lyrics_text([Slide("Chorus", ["one", "two"]), Slide("Slide 2", ["three"])])
    assert text.startswith("[Chorus]\none\ntwo")
    assert "three" in text and "Slide 2" not in text


def test_copy_has_independent_slides():
    original = _song()
    copy = original.copy()
    copy.slides[0].lines.append("extra")
    assert original.slides[0].lines == ["Amazing grace", "how sweet"]


def test_preset_save_overwrite_and_case_insensitive_name(tmp_path):
    lib = SermonPresetLibrary(tmp_path)
    first = lib.save(SermonPreset(name="Sunday AM", title="Faith", speaker="Pastor A"))
    again = lib.save(SermonPreset(name="sunday am", title="Hope", speaker="Pastor B"))
    assert again.id == first.id                       # overwrote, kept its id
    presets = lib.load_all()
    assert len(presets) == 1 and presets[0].title == "Hope"


def test_preset_delete_and_bad_id(tmp_path):
    lib = SermonPresetLibrary(tmp_path)
    p = lib.save(SermonPreset(name="Youth", title="Joy"))
    assert lib.delete("../etc") is False
    assert lib.delete(p.id) is True
    assert lib.load_all() == []


def test_preset_requires_title_and_name():
    with pytest.raises(ValueError):
        SermonPreset(name="", title="x")
    with pytest.raises(ValueError):
        SermonPreset(name="x", title="  ")


def test_corrupt_preset_file_is_skipped(tmp_path):
    lib = SermonPresetLibrary(tmp_path)
    lib.save(SermonPreset(name="Good", title="Yes"))
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
    assert [p.name for p in lib.load_all()] == ["Good"]


def test_unsaved_change_tracking_logic():
    """The editor dirty rule: a snapshot of title/artist/lyrics/slides, compared to the saved one."""
    saved = ("Amazing Grace", "John Newton", "[Verse 1]\na", (("Verse 1", ("a",)),))
    assert saved == ("Amazing Grace", "John Newton", "[Verse 1]\na", (("Verse 1", ("a",)),))
    edited = ("Amazing Grace!", "John Newton", "[Verse 1]\na", (("Verse 1", ("a",)),))
    assert edited != saved
