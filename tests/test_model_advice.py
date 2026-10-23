"""Large-model warning logic, Yoruba advisory dismissal persistence, and settings round-trip. Headless-safe."""
from revelatetw.model_advice import (LARGE_MODEL_WARNING, YORUBA_ADVISORY, is_large_model,
                                     is_yoruba, needs_large_model_warning, should_show_yoruba_advisory)
from revelatetw.store import AppSettings, load_settings, save_settings


def test_large_models_trigger_warning_and_small_do_not():
    assert is_large_model("large") and is_large_model("large-v3")
    for small in ("tiny", "base", "small", "medium"):
        assert not is_large_model(small)
    assert needs_large_model_warning("small", "large-v3")
    assert needs_large_model_warning("medium", "large")
    assert not needs_large_model_warning("small", "medium")
    assert not needs_large_model_warning("large", "large")   # already in use: no repeat prompt


def test_warning_text_matches_spec():
    assert LARGE_MODEL_WARNING == ("The large model needs a powerful PC (16GB+ RAM recommended). "
                                   "If your PC struggles, switch back to the smaller model.")


def test_large_v3_persists_and_unknown_model_falls_back(tmp_path):
    path = tmp_path / "settings.json"
    save_settings(path, AppSettings(model_size="large-v3"))
    assert load_settings(path).model_size == "large-v3"
    assert AppSettings(model_size="bogus").clean().model_size == "small"


def test_yoruba_advisory_only_for_yoruba_with_live_detection():
    assert is_yoruba("yo") and not is_yoruba("KJV")
    assert should_show_yoruba_advisory("yo", True, False)
    assert not should_show_yoruba_advisory("yo", False, False)
    assert not should_show_yoruba_advisory("KJV", True, False)
    assert "large-v3" in YORUBA_ADVISORY and "manual verse mode" in YORUBA_ADVISORY


def test_advisory_dismissal_persists(tmp_path):
    path = tmp_path / "settings.json"
    s = AppSettings(bible_translation="yo")
    assert should_show_yoruba_advisory(s.bible_translation, True, s.yoruba_advisory_dismissed)
    s.yoruba_advisory_dismissed = True
    save_settings(path, s)
    back = load_settings(path)
    assert back.yoruba_advisory_dismissed is True
    assert not should_show_yoruba_advisory(back.bible_translation, True, back.yoruba_advisory_dismissed)
