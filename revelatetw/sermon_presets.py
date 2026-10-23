"""Sermon info presets: a named title / speaker / church line saved as one JSON file each.

Stored in a folder (data/sermons by default). A preset is put on the live sermon slide from
the Songs & sermon tab. Names are unique (case-insensitive): saving under an existing name
overwrites that preset and keeps its id.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .sermon import SermonInfo

_FORMAT = "revelatetw-sermon-preset"


def _safe_id(preset_id: str) -> bool:
    return bool(preset_id) and len(preset_id) <= 64 and all(c.isalnum() or c in "-_" for c in preset_id)


@dataclass
class SermonPreset:
    name: str
    title: str = ""
    speaker: str = ""
    church: str = ""
    id: str = ""

    def __post_init__(self) -> None:
        self.name = (self.name or "").strip()
        self.title = (self.title or "").strip()
        self.speaker = (self.speaker or "").strip()
        self.church = (self.church or "").strip()
        if not self.name:
            raise ValueError("a sermon preset needs a name")
        if not self.title:
            raise ValueError("a sermon preset needs a sermon title")
        if not self.id:
            self.id = uuid.uuid4().hex[:12]
        if not _safe_id(self.id):
            raise ValueError("bad preset id")

    def info(self, reference: str = "") -> SermonInfo:
        return SermonInfo(title=self.title, speaker=self.speaker, reference=reference, church=self.church)

    def to_dict(self) -> dict:
        return {"format": _FORMAT, "version": 1, "id": self.id, "name": self.name,
                "title": self.title, "speaker": self.speaker, "church": self.church}

    @classmethod
    def from_dict(cls, data: dict) -> "SermonPreset":
        return cls(name=str(data.get("name", "")), title=str(data.get("title", "")),
                   speaker=str(data.get("speaker", "")), church=str(data.get("church", "")),
                   id=str(data.get("id", "")))


class SermonPresetLibrary:
    """One JSON file per preset. Corrupt files are skipped, never fatal."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def load_all(self) -> list[SermonPreset]:
        out: list[SermonPreset] = []
        for path in sorted(self.root.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and data.get("format") == _FORMAT:
                    out.append(SermonPreset.from_dict(data))
            except Exception:
                continue
        return sorted(out, key=lambda p: p.name.lower())

    def find_by_name(self, name: str) -> Optional[SermonPreset]:
        key = (name or "").strip().lower()
        return next((p for p in self.load_all() if p.name.lower() == key), None)

    def get(self, preset_id: str) -> Optional[SermonPreset]:
        if not _safe_id(preset_id):
            return None
        return next((p for p in self.load_all() if p.id == preset_id), None)

    def save(self, preset: SermonPreset) -> SermonPreset:
        """Save under its name: an existing preset with that name is overwritten (same id)."""
        existing = self.find_by_name(preset.name)
        if existing is not None:
            preset.id = existing.id
        path = self.root / f"{preset.id}.json"
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(preset.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
        return preset

    def delete(self, preset_id: str) -> bool:
        if not _safe_id(preset_id):
            return False
        path = self.root / f"{preset_id}.json"
        if not path.exists():
            return False
        path.unlink()
        return True
