"""Verify CSV / JSON export merges AI Anatomy results when supplied."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from sn_image_screener.core.exporter import (
    AI_REPORT_FIELDS, REPORT_FIELDS, export_csv, export_json,
)
from sn_image_screener.core.presets import PRESETS
from sn_image_screener.core.scanner import screen_one
from sn_image_screener.services.ai.types import (
    AIStatus, AnatomyResult, Confidence, DefectCategory, DefectRegion,
    ExposureIssue, ScanDepth, ScreeningResult, Severity, Shape,
    TechSeverity, TechnicalQuality,
)


def _fake_result(file_name: str) -> AnatomyResult:
    return AnatomyResult(
        file_name=file_name,
        status=AIStatus.REVIEW,
        screening_result=ScreeningResult.NEEDS_HUMAN_REVIEW,
        quality_score=72,
        physical_defect_detected=True,
        primary_physical_issue="suspicious left hand geometry",
        defect_tags=["hands_fingers"],
        defect_regions=[
            DefectRegion(
                id="r1",
                label="left hand",
                category=DefectCategory.HANDS_FINGERS,
                severity=Severity.MAJOR,
                confidence=Confidence.MEDIUM,
                shape=Shape.BOX,
                box_2d=(100, 100, 400, 400),
                description="extra finger visible",
                related_defect_index=0,
                needs_manual_review=True,
            ),
        ],
        overall_summary="One hand looks off; review manually.",
        recommended_action="review manually",
        confidence=Confidence.MEDIUM,
        technical_quality=TechnicalQuality(
            blur_severity=TechSeverity.HEAVY,
            bokeh_is_intentional=True,
            noise_severity=TechSeverity.MILD,
            exposure_issue=ExposureIssue.NONE,
            artifact_severity=TechSeverity.NONE,
            notes="Subject sharp; background heavily defocused.",
        ),
        provider_used="gemini",
        key_label_used="prod-1",
        scan_depth=ScanDepth.DETAILED,
        tile_count=10,
        duration_seconds=4.2,
    )


def test_csv_appends_ai_columns(tmp_path: Path, sample_dir: Path):
    rules = PRESETS["Normal"]
    items = [
        screen_one(p, rules)
        for p in sample_dir.iterdir()
        if p.suffix.lower() in {".jpg", ".jpeg", ".png"}
    ]
    assert items, "fixture sample_dir produced no items"

    ai_results = {items[0].path.name: _fake_result(items[0].path.name)}
    csv_path = export_csv(items, tmp_path / "report.csv", ai_results=ai_results)

    rows = list(csv.DictReader(csv_path.open()))
    assert len(rows) == len(items)

    # Schema includes both base + AI fields.
    fieldnames = list(rows[0].keys())
    for f in REPORT_FIELDS + AI_REPORT_FIELDS:
        assert f in fieldnames, f"Missing column: {f}"

    # Row with AI result is populated; others stay blank.
    by_name = {r["filename"]: r for r in rows}
    target = by_name[items[0].path.name]
    assert target["ai_status"] == "review"
    assert target["ai_quality_score"] == "72"
    assert target["ai_provider_used"] == "gemini"
    assert target["ai_key_label_used"] == "prod-1"
    assert target["ai_scan_depth"] == "detailed"
    assert target["ai_defect_region_count"] == "1"
    # New AI technical-quality columns are populated.
    assert target["ai_blur_severity"] == "heavy"
    assert target["ai_bokeh_is_intentional"] == "true"
    assert target["ai_noise_severity"] == "mild"
    assert target["ai_exposure_issue"] == "none"
    assert target["ai_artifact_severity"] == "none"

    # Other rows have blank AI columns.
    others = [r for n, r in by_name.items() if n != items[0].path.name]
    for r in others:
        assert r["ai_status"] == ""


def test_json_includes_full_ai_payload(tmp_path: Path, sample_dir: Path):
    rules = PRESETS["Normal"]
    items = [
        screen_one(p, rules)
        for p in sample_dir.iterdir()
        if p.suffix.lower() in {".jpg", ".jpeg", ".png"}
    ]
    assert items
    target = items[0].path.name
    ai_results = {target: _fake_result(target)}

    json_path = export_json(items, tmp_path / "report.json", ai_results=ai_results)
    payload = json.loads(json_path.read_text())

    by_name = {r["filename"]: r for r in payload}
    row = by_name[target]
    ai = row["ai"]
    assert ai is not None
    assert ai["status"] == "review"
    assert ai["screening_result"] == "needs_human_review"
    assert len(ai["defect_regions"]) == 1
    region = ai["defect_regions"][0]
    assert region["id"] == "r1"
    assert region["category"] == "hands_fingers"
    assert region["box_2d"] == [100, 100, 400, 400]
    assert region["needs_manual_review"] is True
    assert ai["scan_depth"] == "detailed"
    assert ai["tile_count"] == 10
    # New technical_quality block round-trips through JSON.
    assert ai["technical_quality"]["blur_severity"] == "heavy"
    assert ai["technical_quality"]["bokeh_is_intentional"] is True
    assert ai["technical_quality"]["noise_severity"] == "mild"
    assert (
        ai["technical_quality"]["notes"]
        == "Subject sharp; background heavily defocused."
    )

    # Files without AI data have ai=None.
    for n, r in by_name.items():
        if n != target:
            assert r["ai"] is None


def test_csv_without_ai_keeps_old_schema(tmp_path: Path, sample_dir: Path):
    """Backwards compatibility: omitting ai_results yields the legacy schema."""
    rules = PRESETS["Normal"]
    items = [
        screen_one(p, rules)
        for p in sample_dir.iterdir()
        if p.suffix.lower() in {".jpg", ".jpeg", ".png"}
    ]
    csv_path = export_csv(items, tmp_path / "legacy.csv")
    rows = list(csv.DictReader(csv_path.open()))
    assert list(rows[0].keys()) == REPORT_FIELDS
