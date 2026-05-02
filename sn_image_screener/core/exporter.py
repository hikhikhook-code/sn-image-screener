"""Export scan results as CSV / JSON and copy good files to a target folder.

All operations are read-only with respect to the source images: we only
ever copy files out, never write back to the originals.
"""

from __future__ import annotations

import csv
import json
import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Iterable, List, Optional

from .classifier import Status
from .scanner import ScanItem


REPORT_FIELDS = [
    "path", "filename", "status", "score",
    "width", "height", "file_kb",
    "blur", "noise", "exposure_mean",
    "exposure_clip_low", "exposure_clip_high",
    "dynamic_range", "artifact", "issues",
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


def export_csv(items: Iterable[ScanItem], out_path: Path) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=REPORT_FIELDS)
        writer.writeheader()
        for it in items:
            writer.writerow(_row(it))
    return out_path


def export_json(items: Iterable[ScanItem], out_path: Path) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rows = [_row(it) for it in items]
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
