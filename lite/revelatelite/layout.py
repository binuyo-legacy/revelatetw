"""Pure helpers for the projection screen (no Qt, so they are unit tested)."""


def pick_display(rects, primary_index, wanted=-1):
    """rects: [(x, y, w, h)] per screen. wanted >= 0 picks that screen if it exists.
    Automatic (-1): the first screen that is not the primary one, else the primary.
    Returns (index, is_extended)."""
    if not rects:
        return 0, False
    if 0 <= wanted < len(rects):
        return wanted, len(rects) > 1
    for i in range(len(rects)):
        if i != primary_index and len(rects) > 1:
            return i, True
    return min(max(primary_index, 0), len(rects) - 1), False


def is_mirrored(rects):
    """Windows 'Duplicate' mode reports every screen at the same origin."""
    return len(rects) > 1 and len({(r[0], r[1]) for r in rects}) == 1


def fit_font_size(fits, lo, hi):
    """Largest size in [lo, hi] for which fits(size) is True (binary search). lo if none fit."""
    best = lo
    while lo <= hi:
        mid = (lo + hi) // 2
        if fits(mid):
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return best


def height_for_width(w):
    """16:9 preview height for a given width."""
    return int(round(w * 9 / 16))


def clamp_startup_geometry(want_w, want_h, avail_x, avail_y, avail_w, avail_h):
    """Startup geometry for the operator window.

    The window must open wholly inside the intended screen's available
    geometry (avail_x/avail_y/avail_w/avail_h) on any screen size, so a
    window sized for a big display is shrunk to fit a small one and never
    overflows past the right or bottom edge, and its top-left is kept
    inside the screen so it cannot hang off the left or top edge either.
    Returns (x, y, w, h). Negative or zero available sizes fall back to
    the wanted size positioned at the given origin.
    """
    if avail_w <= 0 or avail_h <= 0:
        return avail_x, avail_y, want_w, want_h
    w = max(1, min(want_w, avail_w))
    h = max(1, min(want_h, avail_h))
    # Centre on the available area so the whole window sits inside it.
    x = avail_x + max(0, (avail_w - w) // 2)
    y = avail_y + max(0, (avail_h - h) // 2)
    return x, y, w, h
