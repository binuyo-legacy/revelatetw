"""Operator approval queue (spec F2).

Invariant: nothing changes the live output except an explicit operator action
(approve / blank). Detection only calls add(). Every action is written to the session log.
"""
from __future__ import annotations

import itertools
import json
import threading
import time
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from .detection import Candidate

# Keyboard map (spec F2). Remappable in the UI settings later.
DEFAULT_KEYMAP = {
    "approve": "Return", "reject": "Escape", "edit": "E", "hold": "H",
    "next": "Down", "prev": "Up", "blank": "B",
}


class ApprovalQueue:
    def __init__(self, log_path: Optional[str | Path] = None, dedupe_seconds: float = 300.0):
        self._lock = threading.RLock()
        self._items: list[Candidate] = []
        self._ids = itertools.count(1)
        self._last_queued: dict[tuple[int, int, int], float] = {}
        self._dedupe = dedupe_seconds
        self.selected: int = 0
        self.live: Optional[Candidate] = None   # what the output shows right now
        self.blank: bool = False
        self.auto_approve: bool = False         # Settings > Detection; bypasses the operator rule
        self._log_path = Path(log_path) if log_path else None

    def set_auto_approve(self, on: bool) -> None:
        with self._lock:
            self.auto_approve = bool(on)

    def set_dedupe_seconds(self, seconds: float) -> None:
        with self._lock:
            self._dedupe = max(0.0, float(seconds))

    # --- status ------------------------------------------------------------
    @property
    def state(self) -> str:
        """'live', 'blank' or 'idle' for the live indicator."""
        if self.blank:
            return "blank"
        return "live" if self.live else "idle"

    def cleared_count(self) -> int:
        """Verses resolved this session (approved or rejected)."""
        with self._lock:
            return sum(1 for c in self._items if c.status in ("approved", "rejected"))

    def pending(self) -> list[Candidate]:
        with self._lock:
            return [c for c in self._items if c.status in ("pending", "held")]

    def selected_item(self) -> Optional[Candidate]:
        p = self.pending()
        return p[self.selected] if p and 0 <= self.selected < len(p) else None

    # --- detection side ------------------------------------------------------
    def add(self, candidates: list[Candidate], force: bool = False) -> list[Candidate]:
        added = []
        now = time.time()
        with self._lock:
            for c in candidates:
                key = (c.book_id, c.chapter, c.verse)
                if not force and now - self._last_queued.get(key, -1e9) < self._dedupe:
                    continue  # already queued recently
                c.id = f"c{next(self._ids)}"
                c.detected_at = now
                self._last_queued[key] = now
                self._items.append(c)
                added.append(c)
                self._log("detected", c)
                if self.auto_approve:
                    self.approve(c.id)          # operator-approved by setting, not by a click
        return added

    # --- operator side -------------------------------------------------------
    def _get(self, cid: str) -> Candidate:
        for c in self._items:
            if c.id == cid:
                return c
        raise KeyError(cid)

    def approve(self, cid: str) -> Candidate:
        with self._lock:
            c = self._get(cid)
            c.status = "approved"
            self.live = c
            self.blank = False
            self._log("approved", c)
            return c

    def reject(self, cid: str) -> None:
        with self._lock:
            c = self._get(cid)
            c.status = "rejected"
            self._log("rejected", c)

    def hold(self, cid: str) -> None:
        with self._lock:
            c = self._get(cid)
            c.status = "held"
            self._log("held", c)

    def edit(self, cid: str, new_text: str) -> None:
        with self._lock:
            c = self._get(cid)
            c.edited_text = new_text
            self._log("edited", c)

    def set_blank(self, on: bool = True) -> None:
        with self._lock:
            self.blank = on
            self._log("blank_on" if on else "blank_off", None)

    def move(self, delta: int) -> None:
        with self._lock:
            n = len(self.pending())
            if n:
                self.selected = max(0, min(n - 1, self.selected + delta))

    # --- session log -----------------------------------------------------------
    def _log(self, action: str, c: Optional[Candidate]) -> None:
        if not self._log_path:
            return
        rec = {"ts": time.time(), "action": action}
        if c is not None:
            rec.update({k: v for k, v in asdict(c).items() if k in
                        ("id", "reference", "translation", "confidence", "match_type",
                         "snippet", "status", "edited_text")})
        with self._log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
