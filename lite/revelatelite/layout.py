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
