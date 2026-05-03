from __future__ import annotations

import csv
import json
from pathlib import Path

from sn_image_screener.core.classifier import Status
from sn_image_screener.core.exporter import (
    BUCKET_ERROR,
    BUCKET_FAIL,
    BUCKET_PASS,
    BUCKET_REVIEW,
    copy_by_status,
    export_csv,
    export_json,
    sort_results_into_buckets,
)
from sn_image_screener.core.presets import PRESETS
from sn_image_screener.core.scanner import ScanItem, collect_paths, screen_one


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


# ---------------------------------------------------------------------------
# sort_results_into_buckets — auto-sort with move semantics + 4 buckets.
# ---------------------------------------------------------------------------


def _seed_pool(tmp_path: Path, sample_dir: Path) -> tuple[Path, list[ScanItem]]:
    """Copy fixture images into a fresh pool so 'move' is non-destructive."""
    pool = tmp_path / "pool"
    pool.mkdir()
    rules = PRESETS["Normal"]
    items: list[ScanItem] = []
    for src in sample_dir.iterdir():
        if src.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
            continue
        dst = pool / src.name
        dst.write_bytes(src.read_bytes())
        items.append(screen_one(dst, rules))
    return pool, items


def test_sort_results_into_buckets_moves_files(tmp_path: Path, sample_dir: Path):
    pool, items = _seed_pool(tmp_path, sample_dir)
    out = tmp_path / "out"

    buckets = sort_results_into_buckets(items, out, move=True)

    # All four bucket keys present, even if some are empty.
    assert set(buckets.keys()) == {
        BUCKET_PASS, BUCKET_REVIEW, BUCKET_FAIL, BUCKET_ERROR,
    }
    total_moved = sum(len(v) for v in buckets.values())
    assert total_moved == len(items)

    # Sources gone from pool (move semantics).
    for it in items:
        assert not it.path.exists(), f"{it.path.name} was not moved"

    # All destinations exist and live under the right bucket folder.
    for name, paths in buckets.items():
        for dst in paths:
            assert dst.exists()
            assert dst.parent == out / name


def test_sort_results_into_buckets_copy_mode_preserves_sources(
    tmp_path: Path, sample_dir: Path
):
    pool, items = _seed_pool(tmp_path, sample_dir)
    out = tmp_path / "out"

    buckets = sort_results_into_buckets(items, out, move=False)

    # Sources still present in the pool (copy mode).
    for it in items:
        assert it.path.exists(), f"{it.path.name} was lost during copy"

    # Destinations exist too.
    for paths in buckets.values():
        for dst in paths:
            assert dst.exists()


def test_sort_results_into_buckets_handles_collision(
    tmp_path: Path, sample_dir: Path
):
    """A pre-existing file in the destination must NOT be overwritten."""
    pool, items = _seed_pool(tmp_path, sample_dir)
    out = tmp_path / "out"

    # Pick the first non-error item — bucket name doesn't matter, we
    # just need a known destination to seed a collision.
    target_item = next(it for it in items if it.status is not Status.ERROR)
    target_bucket = {
        Status.PASS:   BUCKET_PASS,
        Status.REVIEW: BUCKET_REVIEW,
        Status.REJECT: BUCKET_FAIL,
    }[target_item.status]
    pre_existing = out / target_bucket / target_item.path.name
    pre_existing.parent.mkdir(parents=True, exist_ok=True)
    pre_existing.write_bytes(b"DO_NOT_OVERWRITE")

    sort_results_into_buckets(items, out, move=True)

    # Original collision target untouched.
    assert pre_existing.read_bytes() == b"DO_NOT_OVERWRITE"
    # The new file lives next to it with a numeric suffix.
    siblings = list(pre_existing.parent.iterdir())
    assert any(p.name != pre_existing.name and p.stem.startswith(pre_existing.stem)
               for p in siblings)


def test_sort_results_into_buckets_ai_takes_precedence(
    tmp_path: Path, sample_dir: Path
):
    """When AI Inspector ran on an image, its verdict outranks Tool A."""

    class _FakeStatus:
        def __init__(self, value: str): self.value = value

    class _FakeAIResult:
        def __init__(self, value: str): self.status = _FakeStatus(value)

    pool, items = _seed_pool(tmp_path, sample_dir)
    out = tmp_path / "out"

    # Force every item's AI verdict to "fail", regardless of Tool A status.
    ai_results = {it.path.name: _FakeAIResult("fail") for it in items}

    buckets = sort_results_into_buckets(
        items, out, ai_results=ai_results, move=True,
    )

    assert len(buckets[BUCKET_FAIL]) == len(items)
    assert buckets[BUCKET_PASS] == []
    assert buckets[BUCKET_REVIEW] == []
    assert buckets[BUCKET_ERROR] == []


def test_sort_results_into_buckets_routes_error_items(
    tmp_path: Path, sample_dir: Path
):
    """Items whose scan failed (Status.ERROR) land in error/."""
    pool, items = _seed_pool(tmp_path, sample_dir)
    out = tmp_path / "out"

    error_items = [it for it in items if it.status is Status.ERROR]
    assert error_items, "fixture must contain at least one ERROR item (corrupt.jpg)"

    buckets = sort_results_into_buckets(items, out, move=True)
    moved_error_names = {p.name for p in buckets[BUCKET_ERROR]}
    expected = {it.path.name for it in error_items}
    assert moved_error_names == expected


def test_sort_results_into_buckets_skips_missing_sources(
    tmp_path: Path, sample_dir: Path
):
    """Re-running auto-sort after files were already moved must not crash."""
    pool, items = _seed_pool(tmp_path, sample_dir)
    out = tmp_path / "out"

    sort_results_into_buckets(items, out, move=True)
    # Second pass: no sources left — function should gracefully no-op.
    buckets = sort_results_into_buckets(items, out, move=True)
    assert all(len(v) == 0 for v in buckets.values())
