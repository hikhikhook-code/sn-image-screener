"""Integration tests for the AnatomyRunner orchestrator (no real network)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from sn_image_screener.services.ai.key_manager import KeyManager
from sn_image_screener.services.ai.run_anatomy_check import AnatomyRunner
from sn_image_screener.services.ai.types import (
    AIStatus, ExposureIssue, KeyEntry, KeyStatus, ProviderName,
    ProviderResponse, ScanDepth, ScreeningResult, TechSeverity,
)


@pytest.fixture
def km(tmp_path: Path) -> KeyManager:
    p = tmp_path / "keys.json"
    km = KeyManager(p)
    km.add(KeyEntry(
        provider=ProviderName.GEMINI, label="primary", key="sk-1",
        model="gemini-1.5-flash", enabled=True, priority=0,
    ))
    km.reset_run_state()
    return km


@pytest.fixture
def img(tmp_path: Path) -> Path:
    p = tmp_path / "test.jpg"
    Image.new("RGB", (1024, 768), color=(255, 0, 0)).save(p, "JPEG")
    return p


def _good_response() -> ProviderResponse:
    return ProviderResponse(raw_text=json.dumps({
        "file_name": "test.jpg",
        "status": "pass",
        "screening_result": "likely_safe",
        "quality_score": 95,
        "physical_defect_detected": False,
        "primary_physical_issue": "",
        "defect_tags": [],
        "main_defects_found": [],
        "defect_regions": [],
        "anatomy_check": {"has_people": False, "hands_visible": False,
                          "face_visible": False, "body_visible": False,
                          "issues": []},
        "object_check": {"main_objects": ["red square"], "object_defects": []},
        "technical_secondary_notes": [],
        "overall_summary": "All good",
        "recommended_action": "use",
        "confidence": "high",
    }))


def _fail_response() -> ProviderResponse:
    return ProviderResponse(raw_text=json.dumps({
        "file_name": "test.jpg",
        "status": "fail",
        "screening_result": "high_risk",
        "quality_score": 30,
        "physical_defect_detected": True,
        "primary_physical_issue": "broken hand",
        "defect_tags": ["hand"],
        "main_defects_found": [{
            "category": "hands_fingers",
            "severity": "critical",
            "location": "left hand",
            "description": "extra finger",
            "why_it_matters": "obvious AI artifact",
        }],
        "defect_regions": [{
            "id": "r1", "label": "left hand",
            "category": "hands_fingers",
            "severity": "critical",
            "confidence": "high",
            "shape": "box",
            "box_2d": [400, 300, 600, 500],
            "description": "extra finger",
            "related_defect_index": 0,
            "needs_manual_review": True,
        }],
        "anatomy_check": {"has_people": True, "hands_visible": True,
                          "face_visible": False, "body_visible": False,
                          "issues": ["extra finger"]},
        "object_check": {"main_objects": [], "object_defects": []},
        "technical_secondary_notes": [],
        "overall_summary": "Broken hand visible",
        "recommended_action": "reject",
        "confidence": "high",
    }))


def test_no_keys_returns_error_result(tmp_path: Path, img: Path):
    km = KeyManager(tmp_path / "keys.json")
    km.reset_run_state()
    runner = AnatomyRunner(km)
    result = runner.run(img, ScanDepth.FAST)
    assert result.status == AIStatus.ERROR
    assert "No usable API key" in (result.error or "")


def test_fast_scan_pass(km: KeyManager, img: Path):
    with patch(
        "sn_image_screener.services.ai.providers.gemini_provider.GeminiProvider.analyze",
        return_value=_good_response(),
    ):
        runner = AnatomyRunner(km)
        result = runner.run(img, ScanDepth.FAST)
    assert result.status == AIStatus.PASS
    assert result.quality_score == 95
    assert result.tile_count == 0
    assert result.provider_used == "gemini"
    assert result.key_label_used == "primary"


def test_detailed_scan_invokes_full_plus_nine_tiles(km: KeyManager, img: Path):
    with patch(
        "sn_image_screener.services.ai.providers.gemini_provider.GeminiProvider.analyze",
        return_value=_good_response(),
    ) as mock:
        AnatomyRunner(km).run(img, ScanDepth.DETAILED)
    # 1 full + 9 tiles
    assert mock.call_count == 10


def test_failover_on_rate_limit(tmp_path: Path, img: Path):
    p = tmp_path / "keys.json"
    km = KeyManager(p)
    km.add(KeyEntry(
        provider=ProviderName.GEMINI, label="primary", key="sk-1",
        model="m", enabled=True, priority=0,
    ))
    km.add(KeyEntry(
        provider=ProviderName.GEMINI, label="backup", key="sk-2",
        model="m", enabled=True, priority=1,
    ))
    km.reset_run_state()

    rate_limited = ProviderResponse(
        raw_text="", error="HTTP 429", rate_limited=True,
    )
    responses = [rate_limited, _good_response()]
    with patch(
        "sn_image_screener.services.ai.providers.gemini_provider.GeminiProvider.analyze",
        side_effect=responses,
    ):
        result = AnatomyRunner(km).run(img, ScanDepth.FAST)

    assert result.status == AIStatus.PASS
    # The first key got marked as rate-limited.
    primary = next(k for k in km.all() if k.label == "primary")
    assert primary.status == KeyStatus.RATE_LIMITED
    backup = next(k for k in km.all() if k.label == "backup")
    assert backup.status == KeyStatus.ACTIVE
    assert result.key_label_used == "backup"


def test_all_keys_failed_returns_error(km: KeyManager, img: Path):
    with patch(
        "sn_image_screener.services.ai.providers.gemini_provider.GeminiProvider.analyze",
        return_value=ProviderResponse(
            raw_text="", error="HTTP 401: bad", invalid_key=True,
        ),
    ):
        result = AnatomyRunner(km).run(img, ScanDepth.FAST)
    assert result.status == AIStatus.ERROR
    # Orchestrator surfaces either the last per-call error or the
    # generic "all keys failed" sentinel — either is acceptable.
    err = result.error or ""
    assert err  # non-empty
    primary = next(k for k in km.all() if k.label == "primary")
    assert primary.status == KeyStatus.FAILED


def test_fail_response_shapes_result(km: KeyManager, img: Path):
    with patch(
        "sn_image_screener.services.ai.providers.gemini_provider.GeminiProvider.analyze",
        return_value=_fail_response(),
    ):
        result = AnatomyRunner(km).run(img, ScanDepth.FAST)
    assert result.status == AIStatus.FAIL
    assert result.physical_defect_detected is True
    assert result.primary_physical_issue == "broken hand"
    assert len(result.defect_regions) == 1
    assert result.defect_regions[0].label == "left hand"


def _good_response_with_tech(**tq) -> ProviderResponse:
    """Like ``_good_response`` but with a technical_quality block.

    Defaults to all-NONE; pass keyword args to override specific axes.
    """
    payload = json.loads(_good_response().raw_text)
    payload["technical_quality"] = {
        "blur_severity":      tq.get("blur_severity", "none"),
        "bokeh_is_intentional": tq.get("bokeh_is_intentional", False),
        "noise_severity":     tq.get("noise_severity", "none"),
        "exposure_issue":     tq.get("exposure_issue", "none"),
        "artifact_severity":  tq.get("artifact_severity", "none"),
        "notes":              tq.get("notes", ""),
    }
    return ProviderResponse(raw_text=json.dumps(payload))


def test_technical_quality_propagates_from_full_response(
    km: KeyManager, img: Path,
):
    """The AI's technical_quality block survives merge into AnatomyResult."""
    resp = _good_response_with_tech(
        blur_severity="heavy",
        bokeh_is_intentional=True,
        noise_severity="mild",
        exposure_issue="none",
        artifact_severity="none",
        notes="Heavy bokeh, subject sharp",
    )
    with patch(
        "sn_image_screener.services.ai.providers.gemini_provider.GeminiProvider.analyze",
        return_value=resp,
    ):
        result = AnatomyRunner(km).run(img, ScanDepth.FAST)

    tq = result.technical_quality
    assert tq.blur_severity is TechSeverity.HEAVY
    assert tq.bokeh_is_intentional is True
    assert tq.noise_severity is TechSeverity.MILD
    assert tq.exposure_issue is ExposureIssue.NONE
    assert tq.notes == "Heavy bokeh, subject sharp"
    # Bokeh is intentional, so the orchestrator must NOT downgrade
    # an otherwise-clean PASS to REVIEW.
    assert result.status is AIStatus.PASS
    assert result.screening_result is ScreeningResult.LIKELY_SAFE


def test_intentional_bokeh_does_not_downgrade(km: KeyManager, img: Path):
    """Heavy blur + bokeh_is_intentional must preserve the PASS verdict."""
    resp = _good_response_with_tech(
        blur_severity="heavy", bokeh_is_intentional=True,
    )
    with patch(
        "sn_image_screener.services.ai.providers.gemini_provider.GeminiProvider.analyze",
        return_value=resp,
    ):
        result = AnatomyRunner(km).run(img, ScanDepth.FAST)
    assert result.status is AIStatus.PASS


def test_unintentional_blur_bumps_pass_to_review(km: KeyManager, img: Path):
    """Heavy blur with bokeh_is_intentional=false bumps PASS to REVIEW."""
    resp = _good_response_with_tech(
        blur_severity="heavy", bokeh_is_intentional=False,
    )
    with patch(
        "sn_image_screener.services.ai.providers.gemini_provider.GeminiProvider.analyze",
        return_value=resp,
    ):
        result = AnatomyRunner(km).run(img, ScanDepth.FAST)
    assert result.status is AIStatus.REVIEW
    assert result.screening_result is ScreeningResult.NEEDS_HUMAN_REVIEW


def test_blown_highlights_bumps_pass_to_review(km: KeyManager, img: Path):
    """Severe exposure findings bump PASS to REVIEW even without blur."""
    resp = _good_response_with_tech(exposure_issue="blown_highlights")
    with patch(
        "sn_image_screener.services.ai.providers.gemini_provider.GeminiProvider.analyze",
        return_value=resp,
    ):
        result = AnatomyRunner(km).run(img, ScanDepth.FAST)
    assert result.status is AIStatus.REVIEW


def test_legacy_response_without_tech_block_still_passes(
    km: KeyManager, img: Path,
):
    """Providers that ignore the new prompt block still produce PASS."""
    with patch(
        "sn_image_screener.services.ai.providers.gemini_provider.GeminiProvider.analyze",
        return_value=_good_response(),
    ):
        result = AnatomyRunner(km).run(img, ScanDepth.FAST)
    assert result.status is AIStatus.PASS
    assert result.technical_quality.blur_severity is TechSeverity.NONE
    assert result.technical_quality.bokeh_is_intentional is False


def test_fail_response_not_rescued_by_clean_tech(km: KeyManager, img: Path):
    """A FAIL anatomy verdict must never be softened to REVIEW by tech."""
    payload = json.loads(_fail_response().raw_text)
    payload["technical_quality"] = {
        "blur_severity": "none", "bokeh_is_intentional": False,
        "noise_severity": "none", "exposure_issue": "none",
        "artifact_severity": "none", "notes": "",
    }
    with patch(
        "sn_image_screener.services.ai.providers.gemini_provider.GeminiProvider.analyze",
        return_value=ProviderResponse(raw_text=json.dumps(payload)),
    ):
        result = AnatomyRunner(km).run(img, ScanDepth.FAST)
    assert result.status is AIStatus.FAIL


def _pass_full_with_dirty_tile() -> tuple[ProviderResponse, ProviderResponse]:
    """Full-image PASS but a tile finds a moderate hand defect.

    Used to exercise the merge-time escalation rule: tile-level findings
    above the minor threshold should bump the verdict away from PASS.
    """
    full = _good_response()
    tile_payload = json.loads(_good_response().raw_text)
    tile_payload["main_defects_found"] = [{
        "category": "hands_fingers",
        "severity": "moderate",
        "location": "thumb",
        "description": "Unnatural crease on thumb",
        "why_it_matters": "Distorts natural anatomy.",
    }]
    tile_payload["defect_regions"] = [{
        "id": "r1", "label": "thumb",
        "category": "hands_fingers", "severity": "moderate",
        "confidence": "high", "shape": "box",
        "box_2d": [400, 300, 600, 500],
        "description": "Unnatural crease on thumb",
        "related_defect_index": 0,
        "needs_manual_review": True,
    }]
    return full, ProviderResponse(raw_text=json.dumps(tile_payload))


def _pass_full_with_minor_tile() -> tuple[ProviderResponse, ProviderResponse]:
    """Full-image PASS plus a tile that only flags a minor blemish."""
    full = _good_response()
    tile_payload = json.loads(_good_response().raw_text)
    tile_payload["main_defects_found"] = [{
        "category": "background_geometry",
        "severity": "minor",
        "location": "wall",
        "description": "Tiny seam on wall",
        "why_it_matters": "Subtle, easy to miss.",
    }]
    return full, ProviderResponse(raw_text=json.dumps(tile_payload))


def _pass_full_with_critical_tile() -> tuple[ProviderResponse, ProviderResponse]:
    """Full-image PASS plus a tile that flags a critical hand defect."""
    full = _good_response()
    tile_payload = json.loads(_good_response().raw_text)
    tile_payload["main_defects_found"] = [{
        "category": "hands_fingers",
        "severity": "critical",
        "location": "left hand",
        "description": "Six fingers on the left hand",
        "why_it_matters": "Severe AI artifact.",
    }]
    tile_payload["defect_regions"] = [{
        "id": "r1", "label": "left hand",
        "category": "hands_fingers", "severity": "critical",
        "confidence": "high", "shape": "box",
        "box_2d": [200, 100, 800, 600],
        "description": "Six fingers", "related_defect_index": 0,
        "needs_manual_review": True,
    }]
    return full, ProviderResponse(raw_text=json.dumps(tile_payload))


def test_moderate_tile_finding_bumps_pass_to_review(
    km: KeyManager, img: Path,
):
    """A clean full-image pass + a moderate tile finding => REVIEW."""
    full, tile = _pass_full_with_dirty_tile()
    # 1 full + 9 tiles, all 9 tiles return the same moderate finding.
    responses = [full] + [tile] * 9
    with patch(
        "sn_image_screener.services.ai.providers.gemini_provider.GeminiProvider.analyze",
        side_effect=responses,
    ):
        result = AnatomyRunner(km).run(img, ScanDepth.DETAILED)
    assert result.status is AIStatus.REVIEW
    assert result.screening_result is ScreeningResult.NEEDS_HUMAN_REVIEW
    assert result.physical_defect_detected is True
    assert any(
        d.severity.value == "moderate" for d in result.main_defects_found
    )


def test_minor_tile_finding_does_not_bump(km: KeyManager, img: Path):
    """A purely-minor tile finding should not escalate a clean PASS."""
    full, tile = _pass_full_with_minor_tile()
    responses = [full] + [tile] * 9
    with patch(
        "sn_image_screener.services.ai.providers.gemini_provider.GeminiProvider.analyze",
        side_effect=responses,
    ):
        result = AnatomyRunner(km).run(img, ScanDepth.DETAILED)
    assert result.status is AIStatus.PASS
    assert result.screening_result is ScreeningResult.LIKELY_SAFE


def test_critical_tile_finding_promotes_pass_to_fail(
    km: KeyManager, img: Path,
):
    """A critical tile finding (e.g. extra finger) flips PASS straight to FAIL."""
    full, tile = _pass_full_with_critical_tile()
    responses = [full] + [tile] * 9
    with patch(
        "sn_image_screener.services.ai.providers.gemini_provider.GeminiProvider.analyze",
        side_effect=responses,
    ):
        result = AnatomyRunner(km).run(img, ScanDepth.DETAILED)
    assert result.status is AIStatus.FAIL
    assert result.screening_result is ScreeningResult.HIGH_RISK
    assert result.physical_defect_detected is True


def test_progress_events_fire(km: KeyManager, img: Path):
    events: list[tuple[str, dict]] = []

    def on_progress(event: str, payload: dict) -> None:
        events.append((event, payload))

    with patch(
        "sn_image_screener.services.ai.providers.gemini_provider.GeminiProvider.analyze",
        return_value=_good_response(),
    ):
        AnatomyRunner(km).run(img, ScanDepth.DETAILED, progress=on_progress)

    names = [e for e, _ in events]
    assert "preparing" in names
    assert "full" in names
    assert "merging" in names
    assert "complete" in names
    # Nine tile progress events for 3×3.
    assert sum(1 for n in names if n == "tile") == 9
