from __future__ import annotations

import csv
import json
from pathlib import Path

from sn_image_screener.core.classifier import Status
from sn_image_screener.core.exporter import (
    copy_by_status, export_csv, export_json,
)
from sn_image_screener.core.presets import PRESETS
from sn_image_screener.core.scanner import collect_paths, screen_one


def _hash_file(p: Path) -> bytes:
    return p.read_bytes()


def test_collect_paths_dedupes_and_filters(sample_dir: Path):
    extra_txt = sample_dir / "notes.txt"
    extra_txt.write_text("hello")
    paths = collect_paths([sample_dir], [sample_dir / "ok.jpg"])
    names = sorted(p.name for p in paths)
    # The text file is excluded; ok.jpg appears only once.
    assert "notes.txt" not in names
    assert names.count("ok.jpg") == 1


def test_screen_one_does_not_mutate_source(sample_dir: Path):
    target = sample_dir / "ok.jpg"
    before = _hash_file(target)
    item = screen_one(target, PRESETS["Normal"])
    after = _hash_file(target)
    assert before == after
    assert item.metrics is not None


def test_export_csv_and_json(tmp_path: Path, sample_dir: Path):
    rules = PRESETS["Normal"]
    items = [screen_one(p, rules) for p in sample_dir.iterdir()
             if p.suffix.lower() in {".jpg", ".jpeg", ".png"}]

    csv_path = export_csv(items, tmp_path / "report.csv")
    json_path = export_json(items, tmp_path / "report.json")

    rows = list(csv.DictReader(csv_path.open()))
    assert len(rows) == len(items)
    assert {"status", "score", "filename"} <= set(rows[0].keys())

    payload = json.loads(json_path.read_text())
    assert isinstance(payload, list)
    assert len(payload) == len(items)


def test_copy_by_status_only_targeted(tmp_path: Path, sample_dir: Path):
    rules = PRESETS["Normal"]
    items = [screen_one(p, rules) for p in sample_dir.iterdir()
             if p.suffix.lower() in {".jpg", ".jpeg"}]
    out = tmp_path / "out"
    written = copy_by_status(items, out, [Status.PASS, Status.REVIEW])

    expected = {it.path.name for it in items
                if it.status in (Status.PASS, Status.REVIEW)}
    actual = {p.name for p in written}
    assert actual == expected

    # Each copy lives in its status-named subfolder (PASS/, REVIEW/).
    for p in written:
        assert p.parent.name in {"PASS", "REVIEW"}

    # Originals untouched
    for it in items:
        assert it.path.exists()


def test_copy_by_status_split_subfolders(tmp_path: Path, sample_dir: Path):
    """Asking for all three buckets writes them into separate subfolders."""
    rules = PRESETS["Normal"]
    items = [screen_one(p, rules) for p in sample_dir.iterdir()
             if p.suffix.lower() in {".jpg", ".jpeg"}]
    out = tmp_path / "out"
    written = copy_by_status(
        items, out, [Status.PASS, Status.REVIEW, Status.REJECT],
    )
    # Every output path is exactly two segments below `out`:
    # out/<STATUS>/<filename>
    for p in written:
        assert p.parent.parent == out
        assert p.parent.name in {"PASS", "REVIEW", "REJECT"}


def test_copy_by_status_flat_legacy(tmp_path: Path, sample_dir: Path):
    """Legacy flat layout (no subfolders) still available via flag."""
    rules = PRESETS["Normal"]
    items = [screen_one(p, rules) for p in sample_dir.iterdir()
             if p.suffix.lower() in {".jpg", ".jpeg"}]
    out = tmp_path / "flat"
    written = copy_by_status(
        items, out, [Status.PASS, Status.REVIEW],
        split_subfolders=False,
    )
    for p in written:
        assert p.parent == out
