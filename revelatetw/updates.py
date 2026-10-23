"""Update check against GitHub Releases. Stdlib only; never raises into the UI.

Result kinds: "current" | "update" | "offline" | "error". The fetch runs on a worker thread
(see start_background_check) and only when the operator asks, or when check_updates_on_startup is on.
"""
from __future__ import annotations

import json
import re
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable, Optional

from .store import APP_VERSION

LATEST_URL = "https://api.github.com/repos/binuyo-legacy/revelatetw/releases/latest"
RELEASES_PAGE = "https://github.com/binuyo-legacy/revelatetw/releases/latest"
TIMEOUT_S = 8.0


@dataclass(frozen=True)
class UpdateResult:
    kind: str                  # current | update | offline | error
    current: str
    latest: str = ""
    url: str = RELEASES_PAGE
    message: str = ""


def parse_version(text: str) -> tuple[int, ...]:
    """'v0.2.0' -> (0, 2, 0). Non-numeric tails are ignored ('0.2.0-beta' -> (0, 2, 0))."""
    m = re.match(r"^\s*v?(\d+(?:\.\d+)*)", text or "")
    if not m:
        raise ValueError(f"not a version: {text!r}")
    return tuple(int(p) for p in m.group(1).split("."))


def _fetch_latest(url: str = LATEST_URL) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                               "User-Agent": f"RevelateTW/{APP_VERSION}"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
        return json.loads(resp.read().decode("utf-8"))


def check_for_update(current: str = APP_VERSION, fetch: Optional[Callable[[], dict]] = None) -> UpdateResult:
    """Compare the latest GitHub release tag with the running version. Never raises."""
    try:
        data = (fetch or _fetch_latest)()
    except (urllib.error.URLError, OSError, TimeoutError):
        return UpdateResult("offline", current, message="Couldn't reach GitHub. Check your internet connection and try again.")
    except ValueError:
        return UpdateResult("error", current, message="The update server sent something unexpected. Try again later.")
    except Exception:  # defensive: the UI must never crash on a bad response
        return UpdateResult("error", current, message="The update check failed. Try again later.")
    tag = str(data.get("tag_name") or "").strip() if isinstance(data, dict) else ""
    url = str(data.get("html_url") or RELEASES_PAGE) if isinstance(data, dict) else RELEASES_PAGE
    try:
        latest_v = parse_version(tag)
        current_v = parse_version(current)
    except ValueError:
        return UpdateResult("error", current, latest=tag, url=url,
                            message="The latest release tag could not be read. Try again later.")
    if latest_v > current_v:
        return UpdateResult("update", current, latest=tag.lstrip("vV"), url=url,
                            message=f"Update available: {tag.lstrip('vV')}. You are on {current}.")
    return UpdateResult("current", current, latest=tag.lstrip("vV"), url=url,
                        message=f"You're up to date ({current}).")


def start_background_check(callback: Callable[[UpdateResult], None], fetch=None) -> threading.Thread:
    """Run the check on a daemon thread and hand the result to callback(result)."""
    def run():
        callback(check_for_update(fetch=fetch))
    t = threading.Thread(target=run, name="revelatetw-update-check", daemon=True)
    t.start()
    return t
