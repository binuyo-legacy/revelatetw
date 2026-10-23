"""Service history: what was projected, per day. Stored as data/history/YYYY-MM-DD.json.

Each entry: {"time": "HH:MM:SS", "ts": epoch, "type": verse|song|sermon|media, "ref": str, "title": str, "text": str}
Writes are atomic (temp file + replace). Reads never raise on a corrupt day file; it is skipped.
"""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import date, datetime
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HISTORY_DIR = REPO_ROOT / "data" / "history"
TYPES = ("verse", "song", "sermon", "media")


class ServiceHistory:
    def __init__(self, folder: Path | str | None = None, clock=time.time):
        self.folder = Path(folder) if folder else DEFAULT_HISTORY_DIR
        self._clock = clock
        self._lock = threading.Lock()

    def _day_file(self, day: str) -> Path:
        return self.folder / f"{day}.json"

    def record(self, kind: str, ref: str = "", title: str = "", text: str = "") -> dict:
        if kind not in TYPES:
            raise ValueError(f"unknown history type: {kind}")
        ts = float(self._clock())
        local = datetime.fromtimestamp(ts)
        entry = {"time": local.strftime("%H:%M:%S"), "ts": ts, "type": kind,
                 "ref": str(ref)[:300], "title": str(title)[:300], "text": str(text)[:2000]}
        day = local.date().isoformat()
        with self._lock:
            self.folder.mkdir(parents=True, exist_ok=True)
            entries = self._read_day(day)
            entries.append(entry)
            tmp = self.folder / f".{day}.tmp"
            tmp.write_text(json.dumps(entries, ensure_ascii=False, indent=1), encoding="utf-8")
            os.replace(tmp, self._day_file(day))
        return entry

    def _read_day(self, day: str) -> list[dict]:
        p = self._day_file(day)
        if not p.exists():
            return []
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        return [e for e in data if isinstance(e, dict)] if isinstance(data, list) else []

    def day(self, day: Optional[str] = None) -> list[dict]:
        day = day or date.fromtimestamp(self._clock()).isoformat()
        return self._read_day(day)

    def days(self) -> list[str]:
        if not self.folder.exists():
            return []
        return sorted((p.stem for p in self.folder.glob("*.json")), reverse=True)

    def to_text(self, day: Optional[str] = None) -> str:
        day = day or date.fromtimestamp(self._clock()).isoformat()
        lines = [f"Service history {day}", ""]
        for e in self._read_day(day):
            label = " - ".join(x for x in (e.get("title"), e.get("ref")) if x)
            lines.append(f"{e.get('time', '')}  [{e.get('type', '')}] {label}".rstrip())
            if e.get("text"):
                lines.append(f"    {e['text']}")
        if len(lines) == 2:
            lines.append("(nothing projected)")
        return "\n".join(lines) + "\n"

    def export_text(self, path: Path | str, day: Optional[str] = None) -> Path:
        out = Path(path)
        out.write_text(self.to_text(day), encoding="utf-8")
        return out
