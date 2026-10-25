import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt6.QtWidgets")

from revelatetw.audio import InputDevice, pick_default_device  # noqa: E402


def _dev(i, name, loopback=False):
    return InputDevice(i, name, 2, 48000, "MME", loopback=loopback)


def test_pick_default_prefers_system_default_index(monkeypatch):
    import revelatetw.audio as audio
    monkeypatch.setattr(audio, "default_input_index", lambda: 3)
    devs = [_dev(1, "Speakers (loopback)", loopback=True), _dev(2, "Built-in mic"), _dev(3, "Headset Mic")]
    assert pick_default_device(devs).name == "Headset Mic"


def test_pick_default_never_returns_loopback(monkeypatch):
    import revelatetw.audio as audio
    monkeypatch.setattr(audio, "default_input_index", lambda: 9)   # default missing from the list
    devs = [_dev(1, "Speakers (loopback)", loopback=True), _dev(2, "Built-in mic")]
    assert pick_default_device(devs).name == "Built-in mic"


def test_pick_default_none_when_no_inputs():
    assert pick_default_device([]) is None
    assert pick_default_device([_dev(1, "Speakers (loopback)", loopback=True)]) is None
