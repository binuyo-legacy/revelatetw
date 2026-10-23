"""Sermon info slide: one slide type with a title, optional speaker and scripture reference.

The reference is filled from the last projected verse (current detection), so the operator
can put a sermon header on screen between verses. Rendering uses the normal theme engine.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SermonInfo:
    title: str = ""
    speaker: str = ""
    reference: str = ""   # e.g. "John 3:16 (KJV)"; empty when no verse has been projected
    church: str = ""      # church line from a preset; empty means the theme's church line

    def lines(self) -> list[str]:
        return [x for x in (self.title, self.speaker, self.reference) if x]
