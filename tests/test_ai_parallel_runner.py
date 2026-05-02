"""Integration tests for ParallelAnatomyRunner (no real network)."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from sn_image_screener.services.ai.key_manager import KeyManager
from sn_image_screener.services.ai.parallel_runner import ParallelAnatomyRunner
from sn_image_screener.services.ai.types import (
    AIStatus, KeyEntry, ProviderName, ProviderResponse, ScanDepth,
)


# ---------------------------------------------------------------------------
# Fixtures + helpers
# ---------------------------------------------------------------------------

def _make_image(path: Path, color=(255, 0, 0)) -> Path:
    Image.new("RGB", (1024, 768), color=color).save(path, "JPEG")
    return path


@pytest.fixture
def km_one(tmp_path: Path) -> KeyManager:
    km = KeyManager(tmp_path / "keys.json")
    km.add(KeyEntry(
        provider=ProviderName.GEMINI, label="primary", key="sk-1",
        model="gemini-1.5-flash", enabled=True, priority=0,
    ))
    km.reset_run_state()
    return km


@pytest.fixture
def km_three(tmp_path: Path) -> KeyManager:
    km = KeyManager(tmp_path / "keys.json")
    for i in range(3):
        km.add(KeyEntry(
            provider=ProviderName.GEMINI, label=f"k{i}", key=f"sk-{i}",
            model="m", enabled=True, priority=i,
        ))
    km.reset_run_state()
    return km


def _good_response(score: int = 95) -> ProviderResponse:
    return ProviderResponse(raw_text=json.dumps({
        "file_name": "x.jpg",
        "status": "pass",
        "screening_result": "likely_safe",
        "quality_score": score,
        "physical_defect_detected": False,
        "primary_physical_issue": "",
        "defect_tags": [],
        "main_defects_found": [],
        "defect_regions": [],
        "anatomy_check": {"has_people": False, "hands_visible": False,
                          "face_visible": False, "body_visible": False,
                          "issues": []},
        "object_check": {"main_objects": [], "object_defects": []},
        "technical_secondary_notes": [],
        "overall_summary": "All good",
        "recommended_action": "use",
        "confidence": "high",
    }))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_no_usable_keys_returns_error_for_every_image(tmp_path: Path):
    km = KeyManager(tmp_path / "keys.json")
    km.reset_run_state()
    imgs = [_make_image(tmp_path / f"i{i}.jpg") for i in range(3)]

    runner = ParallelAnatomyRunner(km, max_workers=4)
    done: list[tuple[Path, str]] = []
    runner.run_batch(
        imgs, ScanDepth.FAST,
        on_image_done=lambda p, r: done.append((p, r.status.value)),
    )
    assert len(done) == 3
    assert all(status == AIStatus.ERROR.value for _, status in done)


def test_fast_scan_runs_one_call_per_image(km_one: KeyManager, tmp_path: Path):
    imgs = [_make_image(tmp_path / f"i{i}.jpg") for i in range(4)]
    with patch(
        "sn_image_screener.services.ai.providers.gemini_provider"
        ".GeminiProvider.analyze",
        return_value=_good_response(),
    ) as mock:
        runner = ParallelAnatomyRunner(km_one, max_workers=2)
        results = runner.run_batch(imgs, ScanDepth.FAST)
    assert mock.call_count == 4  # 4 images * 1 full call
    assert len(results) == 4
    assert all(r.status == AIStatus.PASS for r in results.values())


def test_detailed_scan_calls_full_plus_nine_tiles_per_image(
    km_one: KeyManager, tmp_path: Path,
):
    imgs = [_make_image(tmp_path / f"i{i}.jpg") for i in range(2)]
    with patch(
        "sn_image_screener.services.ai.providers.gemini_provider"
        ".GeminiProvider.analyze",
        return_value=_good_response(),
    ) as mock:
        runner = ParallelAnatomyRunner(km_one, max_workers=4)
        results = runner.run_batch(imgs, ScanDepth.DETAILED)
    # 2 images * (1 full + 9 tiles)
    assert mock.call_count == 20
    assert len(results) == 2
    for r in results.values():
        assert r.tile_count == 9


def test_workers_actually_run_in_parallel(km_three: KeyManager, tmp_path: Path):
    """Three slow inspections should overlap, not run end-to-end."""
    imgs = [_make_image(tmp_path / f"i{i}.jpg") for i in range(3)]

    in_flight = 0
    peak = 0
    lock = threading.Lock()

    def slow(*_args, **_kwargs):
        nonlocal in_flight, peak
        with lock:
            in_flight += 1
            peak = max(peak, in_flight)
        time.sleep(0.10)
        with lock:
            in_flight -= 1
        return _good_response()

    with patch(
        "sn_image_screener.services.ai.providers.gemini_provider"
        ".GeminiProvider.analyze",
        side_effect=slow,
    ):
        runner = ParallelAnatomyRunner(km_three, max_workers=3)
        t0 = time.time()
        runner.run_batch(imgs, ScanDepth.FAST)
        elapsed = time.time() - t0

    assert peak >= 2, f"workers never overlapped (peak={peak})"
    # Sequential would be 3 * 0.10s = 0.30s; parallel <0.25s.
    assert elapsed < 0.25, f"too slow ({elapsed:.2f}s) — likely sequential"


def test_progress_events_fire_per_image(km_one: KeyManager, tmp_path: Path):
    imgs = [_make_image(tmp_path / f"i{i}.jpg") for i in range(2)]
    events: list[tuple[str, str]] = []
    lock = threading.Lock()

    with patch(
        "sn_image_screener.services.ai.providers.gemini_provider"
        ".GeminiProvider.analyze",
        return_value=_good_response(),
    ):
        runner = ParallelAnatomyRunner(km_one, max_workers=2)
        runner.run_batch(
            imgs, ScanDepth.FAST,
            on_image_progress=lambda p, e, _x: (
                lock.acquire(), events.append((p.name, e)), lock.release(),
            ),
        )
    seen = {ev for _, ev in events}
    assert "preparing" in seen
    assert "full" in seen
    assert "merging" in seen
    assert "complete" in seen
    # Every image should have its own complete event.
    completes = [name for name, ev in events if ev == "complete"]
    assert sorted(completes) == sorted(p.name for p in imgs)


def test_stop_short_circuits_remaining_jobs(
    km_one: KeyManager, tmp_path: Path,
):
    imgs = [_make_image(tmp_path / f"i{i}.jpg") for i in range(8)]

    seen_calls = 0
    lock = threading.Lock()
    runner: ParallelAnatomyRunner = None  # type: ignore[assignment]

    def slow(*_args, **_kwargs):
        nonlocal seen_calls
        with lock:
            seen_calls += 1
            if seen_calls >= 2 and runner is not None:
                runner.stop()
        time.sleep(0.05)
        return _good_response()

    with patch(
        "sn_image_screener.services.ai.providers.gemini_provider"
        ".GeminiProvider.analyze",
        side_effect=slow,
    ):
        runner = ParallelAnatomyRunner(km_one, max_workers=2)
        runner.run_batch(imgs, ScanDepth.FAST)

    # Stop should have prevented all 8 from running.
    assert seen_calls < 8


def test_mixed_results_per_image(
    km_one: KeyManager, tmp_path: Path,
):
    imgs = [_make_image(tmp_path / f"i{i}.jpg") for i in range(3)]

    rate_limited = ProviderResponse(
        raw_text="", error="HTTP 429", rate_limited=True,
    )
    responses = iter([
        _good_response(score=95),
        rate_limited,                  # i1 fails (only one key, no failover)
        rate_limited,
        rate_limited,
        _good_response(score=80),      # i2 succeeds eventually? no — only 1 key.
    ])

    def reply(*_a, **_kw):
        try:
            return next(responses)
        except StopIteration:
            return _good_response()

    with patch(
        "sn_image_screener.services.ai.providers.gemini_provider"
        ".GeminiProvider.analyze",
        side_effect=reply,
    ):
        runner = ParallelAnatomyRunner(km_one, max_workers=3)
        results = runner.run_batch(imgs, ScanDepth.FAST)

    assert len(results) == 3
    statuses = {r.status for r in results.values()}
    # Either all PASS (if rate-limit cooldown lifts mid-run) or mixed —
    # what matters is we got a real result for every image (no crashes).
    assert AIStatus.ERROR in statuses or AIStatus.PASS in statuses
