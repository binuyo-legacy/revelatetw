import json
import pytest

from revelatetw.books import name_forms, testament as book_testament
from revelatetw.navigation import suggest, step_verse, candidate_from_suggestion, continuation_suggestions
from revelatetw.store import VerseStore


@pytest.fixture
def store(tmp_path):
    verses = [{"book_id": 43, "chapter": 3, "verse": v, "text": f"v{v}"} for v in range(14, 19)]
    verses += [{"book_id": 62, "chapter": 1, "verse": 1, "text": "x"}]
    f = tmp_path / "v.json"
    f.write_text(json.dumps({"translation_id": "T", "verses": verses}))
    return VerseStore.from_json(f)


@pytest.mark.parametrize("query,expected", [
    ("first john", "1 John"), ("1 john", "1 John"), ("i john", "1 John"), ("1st john", "1 John"),
    ("2nd corinthians", "2 Corinthians"), ("second corinthians", "2 Corinthians"),
])
def test_ordinal_book_names_resolve(store, query, expected):
    labels = [s.label for s in suggest(query, store)]
    assert any(expected in l for l in labels), labels


def test_name_forms_cover_ordinal_and_roman():
    forms = name_forms(62)  # 1 John
    assert "1 john" in forms and "first john" in forms and "i john" in forms


def test_testament_split():
    assert book_testament(1) == "OT" and book_testament(39) == "OT"
    assert book_testament(40) == "NT" and book_testament(66) == "NT"


def test_step_verse_stays_in_chapter(store):
    assert step_verse(store, 43, 3, 16, 1).verse == 17
    assert step_verse(store, 43, 3, 16, -1).verse == 15
    assert step_verse(store, 43, 3, 18, 1) is None  # chapter edge, never crosses


def test_continuation_stays_in_chapter(store):
    s = continuation_suggestions(store, 43, 3, 16, "verse 17")
    assert s and all(x.chapter == 3 for x in s) and s[0].verse == 17


def test_candidate_from_suggestion(store):
    s = step_verse(store, 43, 3, 16, 1)
    c = candidate_from_suggestion(store, s, "navigation", 100, "x")
    assert c.reference.endswith("3:17")
