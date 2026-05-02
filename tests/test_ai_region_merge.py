"""Tests for cross-tile defect region deduplication."""

from __future__ import annotations

from sn_image_screener.services.ai.region_merge import merge_regions
from sn_image_screener.services.ai.types import (
    Confidence, DefectCategory, DefectRegion, Severity, Shape,
)


def _r(box, *, cat=DefectCategory.HANDS_FINGERS,
       sev=Severity.MAJOR, conf=Confidence.HIGH, label="hand") -> DefectRegion:
    return DefectRegion(
        id="", label=label, category=cat, severity=sev,
        confidence=conf, shape=Shape.BOX, box_2d=list(box),
    )


def test_invalid_boxes_are_dropped():
    # box with y_max <= y_min, and one out of range
    bad = [_r([0, 0, 0, 0]), _r([100, 100, 50, 200])]
    assert merge_regions(bad) == []


def test_duplicate_overlap_in_same_category_collapses():
    a = _r([100, 100, 400, 400], sev=Severity.MAJOR, conf=Confidence.HIGH)
    b = _r([110, 120, 390, 410], sev=Severity.MODERATE, conf=Confidence.MEDIUM)
    out = merge_regions([a, b])
    assert len(out) == 1
    # Higher severity / confidence wins.
    assert out[0].severity == Severity.MAJOR
    assert out[0].confidence == Confidence.HIGH


def test_different_categories_are_kept_separate():
    a = _r([100, 100, 400, 400], cat=DefectCategory.HANDS_FINGERS)
    b = _r([100, 100, 400, 400], cat=DefectCategory.FACE_HEAD)
    out = merge_regions([a, b])
    assert len(out) == 2


def test_low_iou_keeps_both():
    a = _r([100, 100, 200, 200])
    b = _r([800, 800, 900, 900])
    out = merge_regions([a, b])
    assert len(out) == 2


def test_critical_sorted_first():
    minor = _r([100, 100, 200, 200], sev=Severity.MINOR)
    crit = _r([700, 700, 900, 900], sev=Severity.CRITICAL)
    out = merge_regions([minor, crit])
    assert out[0].severity == Severity.CRITICAL


def test_ids_are_stable_after_dedupe():
    out = merge_regions([_r([100, 100, 400, 400]) for _ in range(3)])
    assert len(out) == 1
    assert out[0].id  # populated
