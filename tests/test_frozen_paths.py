"""Bundled data/assets resolve from the bundle root, both from a checkout and in a frozen build."""
import sys
from pathlib import Path

import revelatetw.paths as paths

REPO = Path(__file__).resolve().parent.parent


def test_dev_bundle_root_is_repo_root(monkeypatch):
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    assert paths.bundle_root() == REPO


def test_frozen_bundle_root_uses_meipass(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert paths.bundle_root() == tmp_path
    assert paths.bundled("data", "sample_kjv.json") == tmp_path / "data" / "sample_kjv.json"


def test_resolve_data_arg_falls_back_to_bundle(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "sample_kjv.json").write_text("{}", encoding="utf-8")
    monkeypatch.chdir(tmp_path.parent)  # a cwd where data/ does not exist
    assert Path(paths.resolve_data_arg("data/sample_kjv.json")) == tmp_path / "data" / "sample_kjv.json"


def test_resolve_data_arg_keeps_existing_relative_path(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "nowhere"), raising=False)
    monkeypatch.chdir(REPO)
    assert paths.resolve_data_arg("data/sample_kjv.json") == "data/sample_kjv.json"


def test_frozen_store_loads_sample_from_meipass(monkeypatch):
    """Frozen: the store reads sample_kjv.json from the bundle, not the cwd."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(REPO), raising=False)
    monkeypatch.chdir(REPO.parent)
    from revelatetw.store import VerseStore
    s = VerseStore.from_json("data/sample_kjv.json")
    assert s.translation_id
