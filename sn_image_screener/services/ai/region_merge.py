"""Merge overlapping defect regions reported across full image + tiles.

A 3×3 / 4×4 tile grid will often surface the same physical defect from
both the full image inspection and one of the tile inspections (and in
the worst case from neighbouring tiles when the defect straddles a tile
edge). This module deduplicates them so the user sees one marker per
real-world issue.

Strategy
--------
For each pair of regions in the same defect category:
    1. compute IoU on their normalised box_2d boxes;
    2. if IoU ≥ 0.30 → keep the higher-severity / higher-confidence one;
    3. otherwise keep both.

Regions whose `box_2d` is invalid (zero-size, out of range) are dropped
silently — the prompt explicitly tells the model not to invent
coordinates, and we'd rather drop a bad marker than render it on top of
the wrong part of the image.
"""

from __future__ import annotations

from typing import Iterable, List

from .types import Confidence, DefectRegion, Severity


_SEVERITY_RANK = {
    Severity.MINOR: 1,
    Severity.MODERATE: 2,
    Severity.MAJOR: 3,
    Severity.CRITICAL: 4,
}

_CONFIDENCE_RANK = {
    Confidence.LOW: 1,
    Confidence.MEDIUM: 2,
    Confidence.HIGH: 3,
}

DEFAULT_IOU_THRESHOLD = 0.30


def _box_iou(a: List[int], b: List[int]) -> float:
    """IoU of two ``[y_min, x_min, y_max, x_max]`` boxes."""
    ay0, ax0, ay1, ax1 = a
    by0, bx0, by1, bx1 = b
    iy0 = max(ay0, by0)
    ix0 = max(ax0, bx0)
    iy1 = min(ay1, by1)
    ix1 = min(ax1, bx1)
    iw = max(0, ix1 - ix0)
    ih = max(0, iy1 - iy0)
    inter = iw * ih
    if inter == 0:
        return 0.0
    area_a = max(0, ay1 - ay0) * max(0, ax1 - ax0)
    area_b = max(0, by1 - by0) * max(0, bx1 - bx0)
    union = area_a + area_b - inter
    if union <= 0:
        return 0.0
    return inter / union


def _score(r: DefectRegion) -> tuple:
    """Sort key — higher is better."""
    return (
        _SEVERITY_RANK.get(r.severity, 0),
        _CONFIDENCE_RANK.get(r.confidence, 0),
        # tie-break: prefer larger boxes (more contextful)
        max(0, r.box_2d[2] - r.box_2d[0]) * max(0, r.box_2d[3] - r.box_2d[1]),
    )


def merge_regions(
    regions: Iterable[DefectRegion],
    *,
    iou_threshold: float = DEFAULT_IOU_THRESHOLD,
) -> List[DefectRegion]:
    """Deduplicate overlapping defect regions.

    Two regions are considered duplicates when:

    - they share the same defect category, AND
    - their boxes overlap with IoU ≥ `iou_threshold`.

    The keeper is whichever region has the higher severity / confidence
    / area (in that order). Invalid boxes are dropped.
    """
    valid = [r for r in regions if r.is_valid()]

    # Re-id IDs so duplicates from different tiles do not collide on
    # the marker layer. We keep the original ID inside `description`
    # only if the model populated it.
    result: List[DefectRegion] = []
    for cand in valid:
        replaced = False
        for i, kept in enumerate(result):
            if kept.category != cand.category:
                continue
            if _box_iou(kept.box_2d, cand.box_2d) < iou_threshold:
                continue
            # Same physical defect — keep the better one.
            if _score(cand) > _score(kept):
                cand_clone = DefectRegion(**{**kept.__dict__, **cand.__dict__})
                cand_clone.id = kept.id  # keep stable ID for the UI
                result[i] = cand_clone
            replaced = True
            break
        if not replaced:
            result.append(cand)

    # Deterministic order: critical defects first, then by area.
    result.sort(key=_score, reverse=True)

    # Re-number IDs so the UI can display "1 of N" predictably.
    for i, r in enumerate(result, start=1):
        if not r.id:
            r.id = f"r{i}"
    return result
