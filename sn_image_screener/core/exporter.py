"""Export scan results as CSV / JSON and copy good files to a target folder.

All operations are read-only with respect to the source images: we only
ever copy files out, never write back to the originals.
"""

from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path
from typing import Iterable, List, Mapping, Optional

from .classifier import Status
from .scanner import ScanItem


REPORT_FIELDS = [
    "path", "filename", "status", "score",
    "width", "height", "file_kb",
    "blur", "noise", "exposure_mean",
    "exposure_clip_low", "exposure_clip_high",
    "dynamic_range", "artifact", "issues",
]

# AI Anatomy Inspector fields (appended when AI results are supplied).
AI_REPORT_FIELDS = [
    "ai_status", "ai_screening_result", "ai_quality_score",
    "ai_primary_physical_issue", "ai_defect_tags",
    "ai_defect_region_count", "ai_provider_used", "ai_key_label_used",
    "ai_scan_depth", "ai_tile_count", "ai_recommended_action",
    "ai_confidence", "ai_overall_summary", "ai_error",
]


def _row(item: ScanItem) -> dict:
    m = item.metrics
    return {
        "path": str(item.path),
        "filename": item.path.name,
        "status": item.status.value,
        "score": item.score,
        "width": m.width if m else 0,
        "height": m.height if m else 0,
        "file_kb": round(m.file_kb, 2) if m else 0.0,
        "blur": round(m.blur, 2) if m else 0.0,
        "noise": round(m.noise, 2) if m else 0.0,
        "exposure_mean": round(m.exposure_mean, 2) if m else 0.0,
        "exposure_clip_low": round(m.exposure_clip_low, 4) if m else 0.0,
        "exposure_clip_high": round(m.exposure_clip_high, 4) if m else 0.0,
        "dynamic_range": round(m.dynamic_range, 2) if m else 0.0,
        "artifact": round(m.artifact, 2) if m else 0.0,
        "issues": "; ".join(i.label for i in item.verdict.issues) if item.verdict else (item.error or ""),
    }


def _ai_row(result) -> dict:
    """Flatten an :class:`AnatomyResult` into the CSV-friendly columns."""
    if result is None:
        return {f: "" for f in AI_REPORT_FIELDS}
    return {
        "ai_status":               result.status.value,
        "ai_screening_result":     result.screening_result.value,
        "ai_quality_score":        result.quality_score,
        "ai_primary_physical_issue": result.primary_physical_issue,
        "ai_defect_tags":          "; ".join(result.defect_tags),
        "ai_defect_region_count":  len(result.defect_regions),
        "ai_provider_used":        result.provider_used or "",
        "ai_key_label_used":       result.key_label_used or "",
        "ai_scan_depth":           result.scan_depth.value,
        "ai_tile_count":           result.tile_count,
        "ai_recommended_action":   result.recommended_action,
        "ai_confidence":           result.confidence.value,
        "ai_overall_summary":      result.overall_summary,
        "ai_error":                result.error or "",
    }


def _ai_full_dict(result) -> Optional[dict]:
    """Full nested AI result for JSON export (defect_regions etc.)."""
    if result is None:
        return None
    return {
        "status":               result.status.value,
        "screening_result":     result.screening_result.value,
        "quality_score":        result.quality_score,
        "physical_defect_detected": result.physical_defect_detected,
        "primary_physical_issue":   result.primary_physical_issue,
        "defect_tags":          list(result.defect_tags),
        "main_defects_found":   [
            {
                "category":   d.category.value,
                "severity":   d.severity.value,
                "location":   d.location,
                "description": d.description,
                "why_it_matters": d.why_it_matters,
            }
            for d in result.main_defects_found
        ],
        "defect_regions":       [
            {
                "id": r.id,
                "label": r.label,
                "category": r.category.value,
                "severity": r.severity.value,
                "confidence": r.confidence.value,
                "shape": r.shape.value,
                "box_2d": list(r.box_2d),
                "description": r.description,
                "related_defect_index": r.related_defect_index,
                "needs_manual_review": r.needs_manual_review,
            }
            for r in result.defect_regions
        ],
        "anatomy_check": {
            "has_people":     result.anatomy_check.has_people,
            "hands_visible":  result.anatomy_check.hands_visible,
            "face_visible":   result.anatomy_check.face_visible,
            "body_visible":   result.anatomy_check.body_visible,
            "issues":         list(result.anatomy_check.issues),
        },
        "object_check": {
            "main_objects":   list(result.object_check.main_objects),
            "object_defects": list(result.object_check.object_defects),
        },
        "technical_secondary_notes": list(result.technical_secondary_notes),
        "overall_summary":           result.overall_summary,
        "recommended_action":        result.recommended_action,
        "confidence":                result.confidence.value,
        "provider_used":             result.provider_used,
        "key_label_used":            result.key_label_used,
        "scan_depth":                result.scan_depth.value,
        "tile_count":                result.tile_count,
        "duration_seconds":          result.duration_seconds,
        "error":                     result.error,
    }


def export_csv(
    items: Iterable[ScanItem],
    out_path: Path,
    ai_results: Optional[Mapping[str, object]] = None,
) -> Path:
    """Write a CSV report. If ``ai_results`` is provided (mapping
    ``file_name → AnatomyResult``) the AI columns are appended.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(REPORT_FIELDS)
    if ai_results:
        fields = fields + list(AI_REPORT_FIELDS)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for it in items:
            row = _row(it)
            if ai_results is not None:
                row.update(_ai_row(ai_results.get(it.path.name)))
            writer.writerow(row)
    return out_path


def export_json(
    items: Iterable[ScanItem],
    out_path: Path,
    ai_results: Optional[Mapping[str, object]] = None,
) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for it in items:
        row = _row(it)
        if ai_results is not None:
            row["ai"] = _ai_full_dict(ai_results.get(it.path.name))
        rows.append(row)
    out_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    return out_path


def copy_by_status(
    items: Iterable[ScanItem],
    target_dir: Path,
    statuses: Optional[List[Status]] = None,
    *,
    split_subfolders: bool = True,
) -> List[Path]:
    """Copy each item whose status is in `statuses` into `target_dir`.

    When `split_subfolders=True` (default) each file is dropped into a
    subfolder named after its status, i.e.::

        target_dir/
            PASS/    01_pass_sharp.jpg
            REVIEW/  03_review_jpeg.jpg
            REJECT/  06_reject_blurry.jpg

    so the user immediately sees a tidy split between good and bad
    photos. Pass `split_subfolders=False` to dump everything in
    `target_dir` flat (legacy behaviour).

    Returns the list of destination paths actually written. Source files
    are NEVER modified. If a name collision occurs the destination
    filename is suffixed with " (N)".
    """
    if statuses is None:
        statuses = [Status.PASS, Status.REVIEW]

    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    written: List[Path] = []

    for item in items:
        if item.status not in statuses:
            continue
        if split_subfolders:
            bucket = target_dir / item.status.value
            bucket.mkdir(parents=True, exist_ok=True)
        else:
            bucket = target_dir
        dest = bucket / item.path.name
        if dest.exists():
            stem = dest.stem
            suffix = dest.suffix
            n = 1
            while dest.exists():
                dest = bucket / f"{stem} ({n}){suffix}"
                n += 1
        shutil.copy2(item.path, dest)
        written.append(dest)

    return written
