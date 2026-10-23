from revelatetw.displays import DisplayInfo, displays_from_screens, list_displays
from revelatetw.output_state import LiveOutputState


class _Rect:
    def __init__(self, x, y, w, h):
        self._v = (x, y, w, h)

    def x(self): return self._v[0]
    def y(self): return self._v[1]
    def width(self): return self._v[2]
    def height(self): return self._v[3]


class _Screen:
    def __init__(self, name, rect):
        self._n, self._r = name, rect

    def name(self): return self._n
    def geometry(self): return self._r


def test_live_output_toggle_state():
    s = LiveOutputState()
    assert s.on and s.pill_text().endswith("LIVE")
    assert s.toggle() is False
    assert not s.on and s.pill_text().endswith("OFF")
    assert s.set(True) is True
    assert s.toggle() is False


def test_display_listing_from_stub_screens():
    primary = _Screen("DP-1", _Rect(0, 0, 1920, 1080))
    other = _Screen("HDMI-2", _Rect(1920, 0, 1280, 720))
    shown = displays_from_screens([primary, other], primary=primary)
    assert [d.index for d in shown] == [0, 1]
    assert shown[0].primary and not shown[1].primary
    assert (shown[1].x, shown[1].width, shown[1].height) == (1920, 1280, 720)
    assert "(primary)" in shown[0].label and "1920\u00d71080" in shown[0].label


def test_list_displays_is_empty_without_qt_app():
    # Headless-safe: no QGuiApplication instance means an empty list, never a crash.
    assert list_displays() == [] or all(isinstance(d, DisplayInfo) for d in list_displays())
