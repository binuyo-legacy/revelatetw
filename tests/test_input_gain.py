"""Input gain, settings and capture. Pure Python: no Qt and no audio hardware needed.
The Live-screen window tests are in test_input_gain_window.py."""
import json
import math

import pytest

from revelatetw.audio import AudioCapture, InputDevice, db_to_gain
from revelatetw.store import INPUT_GAIN_RANGE_DB, AppSettings, load_settings, save_settings


# --- settings (no Qt) -----------------------------------------------------------------------

def test_default_is_zero_db():
    assert AppSettings().input_gain_db == 0.0


def test_gain_roundtrips_through_the_settings_file(tmp_path):
    path = tmp_path / "settings.json"
    save_settings(path, AppSettings(input_gain_db=7.5))
    assert load_settings(path).input_gain_db == 7.5


@pytest.mark.parametrize("raw,expected", [
    (999, INPUT_GAIN_RANGE_DB[1]), (-999, INPUT_GAIN_RANGE_DB[0]), (20, 20.0), (-60, -60.0),
    ("3.5", 3.5), (None, 0.0), ("loud", 0.0), (math.nan, 0.0), (math.inf, 0.0), (-math.inf, 0.0),
])
def test_gain_is_always_a_valid_number(raw, expected):
    assert AppSettings(input_gain_db=raw).clean().input_gain_db == expected


def test_old_settings_file_without_gain_loads_at_zero(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"model_size": "small", "noise_gate_db": -40}), encoding="utf-8")
    assert load_settings(path).input_gain_db == 0.0


# --- capture (no Qt, no audio hardware) -----------------------------------------------------

def test_set_gain_changes_the_capture_gain_without_a_restart():
    cap = AudioCapture(InputDevice(1, "Mic", 1, 48000, "Windows WASAPI"), gain_db=0.0)
    assert cap.gain == pytest.approx(1.0)
    cap.set_gain(6.0)
    assert cap.gain == pytest.approx(db_to_gain(6.0)) and cap.gain == pytest.approx(1.995, abs=1e-3)
    cap.set_gain(-60.0)
    assert cap.gain == pytest.approx(0.001)
