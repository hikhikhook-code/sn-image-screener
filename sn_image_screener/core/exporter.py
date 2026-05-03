"""Export scan results as CSV / JSON and copy good files to a target folder.

All operations are read-only with respect to the source images: we only
ever copy files out, never write back to the originals.
"""

from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional

from .classifier import Status
from .scanner import ScanItem


# Status → bucket-folder name mapping. Keep these stable: end-users may
# build automation around the resulting folder names.
BUCKET_PASS = "pass"
BUCKET_REVIEW = "review"
BUCKET_FAIL = "fail"
BUCKET_ERROR = "error"

_TOOL_A_BUCKET = {
    Status.PASS:   BUCKET_PASS,
    Status.REVIEW: BUCKET_REVIEW,
    Status.REJECT: BUCKET_FAIL,
    Status.ERROR:  BUCKET_ERROR,
}

# AI :class:`AIStatus` values (as ``str``) → bucket. We avoid importing the
# enum to keep this module Qt-/AI-agnostic; the AI status is read by its
# ``.value`` attribute when available.
_AI_BUCKET = {
    "pass":   BUCKET_PASS,
    "review": BUCKET_REVIEW,
    "fail":   BUCKET_FAIL,
    "error":  BUCKET_ERROR,
}


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
    "ai_blur_severity", "ai_bokeh_is_intentional",
    "ai_noise_severity", "ai_exposure_issue", "ai_artifact_severity",
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
    tq = result.technical_quality
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
        "ai_blur_severity":        tq.blur_severity.value,
        "ai_bokeh_is_intentional": "true" if tq.bokeh_is_intentional else "false",
        "ai_noise_severity":       tq.noise_severity.value,
        "ai_exposure_issue":       tq.exposure_issue.value,
        "ai_artifact_severity":    tq.artifact_severity.value,
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
        "technical_quality":         result.technical_quality.to_dict(),
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


# ---------------------------------------------------------------------------
# Auto-sort: move (or copy) files into pass / review / fail / error buckets.
# ---------------------------------------------------------------------------


def _resolve_bucket(item: ScanItem, ai_results: Optional[Mapping[str, object]]) -> Optional[str]:
    """Return the bucket folder name for this item.

    AI Inspector verdict (when present) takes precedence over the local
    Tool A verdict — the AI side encodes the user's primary intent
    ("did this AI portrait pass?"). Fall back to Tool A status for items
    that were never run through AI Inspector.
    """
    if ai_results:
        ai_r = ai_results.get(item.path.name)
        status_obj = getattr(ai_r, "status", None) if ai_r is not None else None
        status_value = getattr(status_obj, "value", None)
        if isinstance(status_value, str):
            bucket = _AI_BUCKET.get(status_value)
            if bucket is not None:
                return bucket
    return _TOOL_A_BUCKET.get(item.status)


def sort_results_into_buckets(
    items: Iterable[ScanItem],
    target_dir: Path,
    *,
    ai_results: Optional[Mapping[str, object]] = None,
    move: bool = True,
) -> Dict[str, List[Path]]:
    """Sort scanned files into ``pass`` / ``review`` / ``fail`` / ``error``
    subfolders inside ``target_dir`` based on their verdict.

    Parameters
    ----------
    items
        Iterable of :class:`ScanItem`. Each item's ``path`` must point at
        the source image on disk.
    target_dir
        Destination root. Bucket subfolders are created on demand;
        empty buckets do **not** create empty folders.
    ai_results
        Optional mapping ``filename → AnatomyResult`` from the AI
        Inspector. When provided, the AI verdict outranks the local
        Tool A verdict. Items not present in this map fall back to
        Tool A's ``ScanItem.status``.
    move
        ``True`` (default) moves the source file into the bucket via
        :func:`shutil.move`. ``False`` copies via :func:`shutil.copy2`,
        leaving the source untouched.

    Returns
    -------
    Dict[str, List[Path]]
        Mapping ``bucket_name → list of destination Paths``. All four
        buckets are present in the return dict even when empty so that
        callers can reliably introspect counts.

    Notes
    -----
    * Filename collisions inside a bucket are resolved by appending
      ``" (N)"`` before the extension, so a destination file is never
      silently overwritten.
    * Items whose source path no longer exists (e.g. moved by a previous
      run, or the user deleted them out-of-band) are skipped silently.
    * The ``error`` bucket receives any item that failed to scan
      (Tool A ``ERROR`` or AI ``error`` status), so the user can
      inspect them without losing the original files.
    """
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    buckets: Dict[str, List[Path]] = {
        BUCKET_PASS: [],
        BUCKET_REVIEW: [],
        BUCKET_FAIL: [],
        BUCKET_ERROR: [],
    }

    op = shutil.move if move else shutil.copy2

    for item in items:
        bucket_name = _resolve_bucket(item, ai_results)
        if bucket_name is None:
            continue

        src = Path(item.path)
        if not src.exists():
            # Source was removed (e.g. earlier auto-sort run on the same
            # session). Skip rather than blowing up the whole export.
            continue

        b_dir = target_dir / bucket_name
        b_dir.mkdir(parents=True, exist_ok=True)

        dest = b_dir / src.name
        if dest.exists():
            stem, suffix = dest.stem, dest.suffix
            n = 1
            while dest.exists():
                dest = b_dir / f"{stem} ({n}){suffix}"
                n += 1

        op(str(src), str(dest))
        buckets[bucket_name].append(dest)

    return buckets
