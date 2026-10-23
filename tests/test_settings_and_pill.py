"""Settings persistence and LIVE pill state mapping. Headless-safe (no audio device, no display)."""
import json

from revelatetw.output_state import LiveOutputState, pill_state
from revelatetw.store import AppSettings, load_settings, save_settings


def test_pill_on_is_green_live():
    st = pill_state(True)
    assert st["text"].endswith("LIVE")
    assert st["on"] == "true"


def test_pill_off_is_dimmed_red_off():
    st = pill_state(False)
    assert st["text"].endswith("OFF")
    assert st["on"] == "false"


def test_state_toggles_and_matches_pill():
    out = LiveOutputState(on=True)
    assert out.pill()["on"] == "true"
    out.toggle()
    assert out.on is False and out.pill()["on"] == "false"
    out.toggle()
    assert out.on is True and out.pill()["on"] == "true"


def test_defaults_keep_human_approval():
    s = AppSettings()
    assert s.auto_approve is False
    assert s.startup_live_on is True


def test_roundtrip_persists(tmp_path):
    path = tmp_path / "settings.json"
    s = AppSettings(model_size="medium", paraphrase_threshold=72, dedupe_minutes=3.5,
                    noise_gate_db=-40.0, output_display=1, wasapi_loopback=True)
    save_settings(path, s)
    back = load_settings(path)
    assert back.model_size == "medium"
    assert back.paraphrase_threshold == 72
    assert back.dedupe_minutes == 3.5
    assert back.noise_gate_db == -40.0
    assert back.output_display == 1
    assert back.wasapi_loopback is True


def test_missing_file_gives_defaults(tmp_path):
    assert load_settings(tmp_path / "nope.json") == AppSettings()


def test_corrupt_file_gives_defaults(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{not json", encoding="utf-8")
    assert load_settings(path) == AppSettings()


def test_bad_values_are_coerced_and_unknown_keys_ignored(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"model_size": "huge", "noise_gate_db": 5,
                                "paraphrase_threshold": 500, "mystery": 1}), encoding="utf-8")
    s = load_settings(path)
    assert s.model_size == "small"
    assert s.noise_gate_db == -10.0
    assert s.paraphrase_threshold == 100


def test_save_is_atomic_no_tmp_left(tmp_path):
    path = tmp_path / "settings.json"
    save_settings(path, AppSettings())
    assert path.exists()
    assert not (tmp_path / "settings.json.tmp").exists()
