"""End-to-end orchestrator for the AI Anatomy Inspector.

Pipeline (per image)
--------------------
1. Build tiles for the requested :class:`ScanDepth`.
2. Inspect the full image (always).
3. For ``DETAILED`` / ``ULTRA``: inspect every tile.
4. Translate each tile's ``defect_regions`` back to full-image coords.
5. Merge overlapping regions across full + tile responses.
6. Emit a single :class:`AnatomyResult`.

Failover
--------
At any step, if the chosen API key fails (rate limit / invalid key /
provider error) we mark it in the :class:`KeyManager` and retry the
*same* inspection with the next available key. The cooldown only lasts
for the current run.

Limits (matching the task spec):
    * max retries per single inspection : 2
    * max provider/key switches per image: 20
    * never invent a result — if everything fails, the image is marked
      ERROR and the caller can offer Retry.

The orchestrator runs synchronously inside the worker thread that
called it. UI code uses the :class:`InspectionWorker` Qt wrapper in
``ui/ai/`` to listen for progress signals.
"""

from __future__ import annotations

import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

from .key_manager import KeyManager
from .prompts.anatomy_prompt import ANATOMY_PROMPT, tile_prompt
from .providers import provider_for
from .providers.base import parse_json_loose
from .region_merge import merge_regions
from .tiling import build_tiles, encode_for_provider, read_tile_bytes
from .types import (
    AIStatus, AnatomyCheck, AnatomyResult, Confidence, DefectCategory,
    DefectFinding, DefectRegion, ImageInput, KeyStatus,
    ObjectCheck, ScanDepth, ScreeningResult, Severity, Shape, Tile,
    tiles_for_depth,
)


# Spec-mandated safety limits.
MAX_RETRIES_PER_INSPECTION = 2
MAX_KEY_SWITCHES_PER_IMAGE = 20


# Public progress event names (UI consumes these as plain strings).
EVT_PREPARE = "preparing"
EVT_FULL = "full"
EVT_TILE = "tile"
EVT_MERGE = "merging"
EVT_COMPLETE = "complete"
EVT_KEY_SWITCH = "key_switch"
EVT_ERROR = "error"


ProgressFn = Callable[[str, dict], None]
"""Signature: ``(event, payload)`` where payload is event-specific."""


@dataclass
class _OneInspection:
    """Result of a single full-image-or-tile inspection."""

    parsed: Optional[dict]
    provider: str
    key_label: str
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class AnatomyRunner:
    """Run the AI Anatomy Inspector pipeline for one image."""

    def __init__(
        self,
        keys: KeyManager,
        *,
        timeout_seconds: int = 60,
    ) -> None:
        self.keys = keys
        self.timeout = timeout_seconds

    def run(
        self,
        image_path: Path,
        depth: ScanDepth,
        *,
        progress: Optional[ProgressFn] = None,
    ) -> AnatomyResult:
        progress = progress or (lambda _e, _p: None)
        image_path = Path(image_path)
        started = time.time()
        usable = self.keys.usable_keys()
        if not usable:
            err = (
                "No usable API key. Add at least one enabled key in "
                "Settings → AI Keys before running."
            )
            progress(EVT_ERROR, {"message": err})
            return _error_result(image_path, depth, err, started)

        progress(EVT_PREPARE, {"depth": depth.value})

        tmp_dir = Path(tempfile.mkdtemp(prefix="sn_ai_run_"))
        try:
            full_w, full_h, tiles = build_tiles(image_path, depth, tmp_dir=tmp_dir)
            full_bytes, full_mime = encode_for_provider(image_path)

            switches = 0

            # 1. Full image
            progress(EVT_FULL, {"file": image_path.name})
            full_input = ImageInput(
                data=full_bytes, mime=full_mime, filename=image_path.name,
            )
            full_pass = self._inspect_with_failover(
                full_input, ANATOMY_PROMPT,
                progress=progress, switches_remaining=MAX_KEY_SWITCHES_PER_IMAGE,
            )
            switches += full_pass.switches_used
            full_inspection = full_pass.inspection

            # 2. Tile inspections
            tile_inspections: List[_OneInspection] = []
            total_tiles = len(tiles)
            for ti, tile in enumerate(tiles):
                progress(EVT_TILE, {
                    "tile_index": ti + 1, "total_tiles": total_tiles,
                })
                tprompt = ANATOMY_PROMPT + tile_prompt(ti, total_tiles)
                tinput = ImageInput(
                    data=read_tile_bytes(tile),
                    mime="image/jpeg",
                    filename=f"{image_path.stem}_tile{ti}.jpg",
                )
                tpass = self._inspect_with_failover(
                    tinput, tprompt,
                    progress=progress,
                    switches_remaining=MAX_KEY_SWITCHES_PER_IMAGE - switches,
                )
                switches += tpass.switches_used
                if tpass.inspection.parsed is not None:
                    # Translate tile-local regions back to full-image space.
                    _translate_tile_regions_in_place(
                        tpass.inspection.parsed, tile, full_w, full_h,
                    )
                tile_inspections.append(tpass.inspection)

            progress(EVT_MERGE, {})
            result = _merge_inspections(
                image_path,
                full_inspection,
                tile_inspections,
                depth,
                started,
            )
            progress(EVT_COMPLETE, {
                "status": result.status.value,
                "score": result.quality_score,
            })
            return result
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    # Largest cooldown window we are willing to wait for inside a single
    # inspection. Anything longer than this and we surface the error to
    # the caller instead of blocking the worker thread.
    MAX_COOLDOWN_WAIT_S = 10.0

    def _inspect_with_failover(
        self,
        image: ImageInput,
        prompt: str,
        *,
        progress: ProgressFn,
        switches_remaining: int,
    ) -> "_FailoverResult":
        """Single inspection (full or tile) with retry + key failover."""
        switches_used = 0
        last_error = ""

        while switches_remaining > 0:
            key = self.keys.next_available()
            if key is None:
                # All keys are currently cooling down. If at least one
                # is going to recover soon, wait briefly and try again
                # — that lets the parallel runner with one key recover
                # instead of erroring out the moment a 429 hits.
                expiry = self.keys.soonest_cooldown_expiry()
                if expiry is not None:
                    wait_s = expiry - time.time()
                    if 0 < wait_s <= self.MAX_COOLDOWN_WAIT_S:
                        time.sleep(wait_s)
                        continue
                return _FailoverResult(
                    inspection=_OneInspection(
                        parsed=None, provider="", key_label="",
                        error=last_error or "All enabled API keys failed",
                    ),
                    switches_used=switches_used,
                )

            provider = provider_for(key.provider)

            # `MAX_RETRIES_PER_INSPECTION` retries for transient errors.
            attempt_error: Optional[str] = None
            for attempt in range(MAX_RETRIES_PER_INSPECTION + 1):
                resp = provider.analyze(
                    key, image, prompt, timeout=self.timeout,
                )

                if resp.invalid_key:
                    self.keys.set_status(
                        key, KeyStatus.FAILED,
                        error=resp.error or "Invalid key",
                    )
                    progress(EVT_KEY_SWITCH, {
                        "from": f"{key.provider.value}/{key.label}",
                        "reason": "invalid_key",
                        "message": resp.error or "",
                    })
                    attempt_error = resp.error or "Invalid key"
                    break  # don't retry an invalid key

                if resp.rate_limited:
                    self.keys.set_status(
                        key, KeyStatus.RATE_LIMITED,
                        error=resp.error or "Rate limited",
                    )
                    progress(EVT_KEY_SWITCH, {
                        "from": f"{key.provider.value}/{key.label}",
                        "reason": "rate_limited",
                        "message": resp.error or "",
                    })
                    attempt_error = resp.error or "Rate limited"
                    break

                if resp.error:
                    attempt_error = resp.error
                    if attempt < MAX_RETRIES_PER_INSPECTION:
                        time.sleep(0.5 * (attempt + 1))
                        continue
                    self.keys.set_status(
                        key, KeyStatus.FAILED, error=resp.error,
                    )
                    progress(EVT_KEY_SWITCH, {
                        "from": f"{key.provider.value}/{key.label}",
                        "reason": "provider_error",
                        "message": resp.error,
                    })
                    break

                # Success.
                parsed = parse_json_loose(resp.raw_text)
                if parsed is None:
                    attempt_error = "Malformed JSON in provider response"
                    if attempt < MAX_RETRIES_PER_INSPECTION:
                        continue
                    self.keys.set_status(
                        key, KeyStatus.FAILED, error=attempt_error,
                    )
                    progress(EVT_KEY_SWITCH, {
                        "from": f"{key.provider.value}/{key.label}",
                        "reason": "malformed_json",
                        "message": attempt_error,
                    })
                    break

                self.keys.set_status(key, KeyStatus.ACTIVE)
                return _FailoverResult(
                    inspection=_OneInspection(
                        parsed=parsed,
                        provider=key.provider.value,
                        key_label=key.label,
                    ),
                    switches_used=switches_used,
                )

            # If we get here the key failed; advance to the next one.
            switches_used += 1
            switches_remaining -= 1
            last_error = attempt_error or last_error

        return _FailoverResult(
            inspection=_OneInspection(
                parsed=None, provider="", key_label="",
                error=last_error or "All enabled API keys failed",
            ),
            switches_used=switches_used,
        )


@dataclass
class _FailoverResult:
    inspection: _OneInspection
    switches_used: int


# ---------------------------------------------------------------------------
# Translation + merging
# ---------------------------------------------------------------------------

def _translate_tile_regions_in_place(
    parsed: dict, tile: Tile, full_w: int, full_h: int,
) -> None:
    """Move tile-local box_2d coordinates into the full-image space."""
    for region in parsed.get("defect_regions", []) or []:
        box = region.get("box_2d") or [0, 0, 0, 0]
        if not isinstance(box, list) or len(box) != 4:
            region["box_2d"] = [0, 0, 0, 0]
            continue
        try:
            translated = tile.offset_box_to_full([int(v) for v in box], full_w, full_h)
        except (TypeError, ValueError):
            translated = [0, 0, 0, 0]
        region["box_2d"] = translated


def _merge_inspections(
    image_path: Path,
    full: _OneInspection,
    tiles: List[_OneInspection],
    depth: ScanDepth,
    started: float,
) -> AnatomyResult:
    """Combine the full-image and tile parsed dicts into one AnatomyResult."""
    parsed = full.parsed or {}
    if not parsed and not any(t.parsed for t in tiles):
        # Nothing came back from anyone — surface a clear error result.
        err = full.error or next(
            (t.error for t in tiles if t.error), "AI inspection failed",
        )
        return _error_result(image_path, depth, err, started, full=full)

    primary = parsed if parsed else next(
        (t.parsed for t in tiles if t.parsed), {}
    ) or {}
    result = _result_from_dict(primary, image_path)
    result.scan_depth = depth
    result.tile_count = tiles_for_depth(depth)
    result.duration_seconds = time.time() - started
    result.provider_used = full.provider or next(
        (t.provider for t in tiles if t.provider), ""
    )
    result.key_label_used = full.key_label or next(
        (t.key_label for t in tiles if t.key_label), ""
    )

    # Collect every region across full + tiles, then merge.
    all_regions: List[DefectRegion] = list(result.defect_regions)
    seen_findings: List[DefectFinding] = list(result.main_defects_found)
    for t in tiles:
        if not t.parsed:
            continue
        all_regions.extend(_regions_from_dict(t.parsed))
        seen_findings.extend(_findings_from_dict(t.parsed))

    merged = merge_regions(all_regions)
    result.defect_regions = merged
    # Findings: dedupe by (category, description) but keep highest severity.
    result.main_defects_found = _dedupe_findings(seen_findings)

    # If the merged data shows no defects, force a benign status.
    if not merged and not result.main_defects_found:
        if result.status == AIStatus.ERROR:
            pass  # leave ERROR alone
        elif result.quality_score >= 90 or not result.physical_defect_detected:
            result.status = AIStatus.PASS
            result.screening_result = ScreeningResult.LIKELY_SAFE

    return result


def _dedupe_findings(items: List[DefectFinding]) -> List[DefectFinding]:
    seen: dict[tuple, DefectFinding] = {}
    rank = {Severity.MINOR: 1, Severity.MODERATE: 2, Severity.MAJOR: 3, Severity.CRITICAL: 4}
    for f in items:
        key = (f.category, f.description.strip().lower())
        if key not in seen or rank[f.severity] > rank[seen[key].severity]:
            seen[key] = f
    return list(seen.values())


# ---------------------------------------------------------------------------
# Dict -> dataclass conversion (loose, schema-tolerant)
# ---------------------------------------------------------------------------

def _safe_enum(enum_cls, value, default):
    if value is None:
        return default
    try:
        return enum_cls(str(value).lower())
    except ValueError:
        return default


def _findings_from_dict(d: dict) -> List[DefectFinding]:
    out: List[DefectFinding] = []
    for raw in d.get("main_defects_found") or []:
        if not isinstance(raw, dict):
            continue
        out.append(DefectFinding(
            category=_safe_enum(DefectCategory, raw.get("category"),
                                DefectCategory.TECHNICAL_SECONDARY),
            severity=_safe_enum(Severity, raw.get("severity"), Severity.MINOR),
            location=str(raw.get("location") or ""),
            description=str(raw.get("description") or ""),
            why_it_matters=str(raw.get("why_it_matters") or ""),
        ))
    return out


def _regions_from_dict(d: dict) -> List[DefectRegion]:
    out: List[DefectRegion] = []
    for i, raw in enumerate(d.get("defect_regions") or []):
        if not isinstance(raw, dict):
            continue
        box = raw.get("box_2d") or [0, 0, 0, 0]
        if not isinstance(box, list) or len(box) != 4:
            box = [0, 0, 0, 0]
        try:
            box = [max(0, min(1000, int(v))) for v in box]
        except (TypeError, ValueError):
            box = [0, 0, 0, 0]
        out.append(DefectRegion(
            id=str(raw.get("id") or f"r{i + 1}"),
            label=str(raw.get("label") or ""),
            category=_safe_enum(DefectCategory, raw.get("category"),
                                DefectCategory.TECHNICAL_SECONDARY),
            severity=_safe_enum(Severity, raw.get("severity"), Severity.MINOR),
            confidence=_safe_enum(Confidence, raw.get("confidence"),
                                  Confidence.MEDIUM),
            shape=_safe_enum(Shape, raw.get("shape"), Shape.BOX),
            box_2d=box,
            description=str(raw.get("description") or ""),
            related_defect_index=int(raw.get("related_defect_index") or 0),
            needs_manual_review=bool(raw.get("needs_manual_review", True)),
        ))
    return out


def _result_from_dict(d: dict, image_path: Path) -> AnatomyResult:
    anatomy = d.get("anatomy_check") or {}
    obj = d.get("object_check") or {}
    return AnatomyResult(
        file_name=str(d.get("file_name") or image_path.name),
        status=_safe_enum(AIStatus, d.get("status"), AIStatus.REVIEW),
        screening_result=_safe_enum(
            ScreeningResult, d.get("screening_result"),
            ScreeningResult.NEEDS_HUMAN_REVIEW,
        ),
        quality_score=_clamp_int(d.get("quality_score"), 0, 100, default=0),
        physical_defect_detected=bool(d.get("physical_defect_detected", False)),
        primary_physical_issue=str(d.get("primary_physical_issue") or ""),
        defect_tags=[str(t) for t in (d.get("defect_tags") or [])],
        main_defects_found=_findings_from_dict(d),
        defect_regions=_regions_from_dict(d),
        anatomy_check=AnatomyCheck(
            has_people=bool(anatomy.get("has_people", False)),
            hands_visible=bool(anatomy.get("hands_visible", False)),
            face_visible=bool(anatomy.get("face_visible", False)),
            body_visible=bool(anatomy.get("body_visible", False)),
            issues=[str(s) for s in (anatomy.get("issues") or [])],
        ),
        object_check=ObjectCheck(
            main_objects=[str(s) for s in (obj.get("main_objects") or [])],
            object_defects=[str(s) for s in (obj.get("object_defects") or [])],
        ),
        technical_secondary_notes=[
            str(s) for s in (d.get("technical_secondary_notes") or [])
        ],
        overall_summary=str(d.get("overall_summary") or ""),
        recommended_action=str(d.get("recommended_action") or "review manually"),
        confidence=_safe_enum(Confidence, d.get("confidence"), Confidence.MEDIUM),
    )


def _clamp_int(value, lo: int, hi: int, default: int) -> int:
    try:
        v = int(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


def _error_result(
    image_path: Path,
    depth: ScanDepth,
    error: str,
    started: float,
    *,
    full: Optional[_OneInspection] = None,
) -> AnatomyResult:
    return AnatomyResult(
        file_name=image_path.name,
        status=AIStatus.ERROR,
        screening_result=ScreeningResult.NEEDS_HUMAN_REVIEW,
        quality_score=0,
        physical_defect_detected=False,
        primary_physical_issue="",
        defect_tags=[],
        main_defects_found=[],
        defect_regions=[],
        overall_summary=error,
        recommended_action="review manually",
        confidence=Confidence.LOW,
        provider_used=full.provider if full else "",
        key_label_used=full.key_label if full else "",
        scan_depth=depth,
        tile_count=tiles_for_depth(depth),
        duration_seconds=time.time() - started,
        error=error,
    )
