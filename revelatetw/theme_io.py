"""Share theme designs as .json files. Uses the same schema validation as Theme.load."""
from __future__ import annotations

import json
from pathlib import Path

from .theme import Theme


def export_theme(theme: Theme, path: Path | str) -> Path:
    problems = theme.problems()
    if problems:
        raise ValueError("theme has problems and cannot be exported: " + "; ".join(problems))
    out = Path(path)
    out.write_text(json.dumps(theme.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def import_theme(path: Path | str) -> Theme:
    """Load and validate a shared theme. Raises ValueError with a plain message on bad files."""
    p = Path(path)
    try:
        data = json.loads(p.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"could not read theme file: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("theme file must contain a JSON object")
    theme = Theme.from_dict(data)
    problems = theme.problems()
    if problems:
        raise ValueError("theme file is not valid: " + "; ".join(problems))
    return theme
