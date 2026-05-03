"""Typed data structures for the AI Anatomy Inspector pipeline.

The shapes mirror the JSON contract documented in
`prompts/anatomy_prompt.py` so that the rest of the application can
treat the AI response as plain Python objects, while still being able
to round-trip through CSV/JSON exports.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ProviderName(str, Enum):
    GEMINI = "gemini"
    OPENAI = "openai"
    GROQ = "groq"


class ScanDepth(str, Enum):
    """How aggressively to subdivide an image before inspection."""

    FAST = "fast"          # 1 inspection: full image only
    DETAILED = "detailed"  # 1 + 9 = 10 inspections (3×3 tiles)
    ULTRA = "ultra"        # 1 + 16 = 17 inspections (4×4 tiles)


def tiles_for_depth(depth: ScanDepth) -> int:
    """Number of tile inspections (excluding the full-image pass)."""
    return {ScanDepth.FAST: 0, ScanDepth.DETAILED: 9, ScanDepth.ULTRA: 16}[depth]


def grid_size(depth: ScanDepth) -> int:
    """Side length of the tile grid (0 = no tiling)."""
    return {ScanDepth.FAST: 0, ScanDepth.DETAILED: 3, ScanDepth.ULTRA: 4}[depth]


class AIStatus(str, Enum):
    PASS = "pass"
    REVIEW = "review"
    FAIL = "fail"
    ERROR = "error"


class ScreeningResult(str, Enum):
    LIKELY_SAFE = "likely_safe"
    NEEDS_HUMAN_REVIEW = "needs_human_review"
    HIGH_RISK = "high_risk"


class DefectCategory(str, Enum):
    HANDS_FINGERS = "hands_fingers"
    FACE_HEAD = "face_head"
    TEETH_MOUTH_EYES = "teeth_mouth_eyes"
    BODY_ANATOMY = "body_anatomy"
    OBJECT_DEFORMATION = "object_deformation"
    CLOTHING_ACCESSORY = "clothing_accessory"
    BACKGROUND_GEOMETRY = "background_geometry"
    TEXT_LOGO_WATERMARK = "text_logo_watermark"
    TECHNICAL_SECONDARY = "technical_secondary"


class Severity(str, Enum):
    MINOR = "minor"
    MODERATE = "moderate"
    MAJOR = "major"
    CRITICAL = "critical"


class Confidence(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Shape(str, Enum):
    BOX = "box"
    CIRCLE = "circle"


class KeyStatus(str, Enum):
    UNTESTED = "untested"
    ACTIVE = "active"
    FAILED = "failed"
    RATE_LIMITED = "rate_limited"
    EXHAUSTED = "exhausted"


class TechSeverity(str, Enum):
    """Three-step severity used by the AI technical side-check."""

    NONE = "none"
    MILD = "mild"
    HEAVY = "heavy"


class ExposureIssue(str, Enum):
    """Exposure verdict from the AI technical side-check."""

    NONE = "none"
    UNDEREXPOSED = "underexposed"
    OVEREXPOSED = "overexposed"
    BLOWN_HIGHLIGHTS = "blown_highlights"
    CRUSHED_SHADOWS = "crushed_shadows"


# ---------------------------------------------------------------------------
# AI response shapes
# ---------------------------------------------------------------------------

@dataclass
class DefectFinding:
    category: DefectCategory
    severity: Severity
    location: str = ""
    description: str = ""
    why_it_matters: str = ""

    def to_dict(self) -> dict:
        return {
            "category": self.category.value,
            "severity": self.severity.value,
            "location": self.location,
            "description": self.description,
            "why_it_matters": self.why_it_matters,
        }


@dataclass
class DefectRegion:
    """Bounding box (or circle) for a visible defect.

    `box_2d` follows the prompt contract: ``[y_min, x_min, y_max, x_max]``
    in normalised coordinates 0..1000. The conversion back to pixel
    space happens at render time.
    """

    id: str
    label: str
    category: DefectCategory
    severity: Severity
    confidence: Confidence
    shape: Shape
    box_2d: List[int] = field(default_factory=lambda: [0, 0, 0, 0])
    description: str = ""
    related_defect_index: int = 0
    needs_manual_review: bool = True

    def is_valid(self) -> bool:
        if len(self.box_2d) != 4:
            return False
        y0, x0, y1, x1 = self.box_2d
        return 0 <= x0 < x1 <= 1000 and 0 <= y0 < y1 <= 1000

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "category": self.category.value,
            "severity": self.severity.value,
            "confidence": self.confidence.value,
            "shape": self.shape.value,
            "box_2d": list(self.box_2d),
            "description": self.description,
            "related_defect_index": self.related_defect_index,
            "needs_manual_review": self.needs_manual_review,
        }


@dataclass
class AnatomyCheck:
    has_people: bool = False
    hands_visible: bool = False
    face_visible: bool = False
    body_visible: bool = False
    issues: List[str] = field(default_factory=list)


@dataclass
class ObjectCheck:
    main_objects: List[str] = field(default_factory=list)
    object_defects: List[str] = field(default_factory=list)


@dataclass
class TechnicalQuality:
    """AI-judged technical quality side-check.

    Lives on every :class:`AnatomyResult`. Defaults are deliberately
    benign so that legacy responses (or providers that ignore the new
    block) keep producing PASS-able results.

    The key field for AI-generated portraits is
    :attr:`bokeh_is_intentional` -- it lets the verdict layer treat
    "subject sharp + heavily blurred background" as acceptable instead
    of forcing a REVIEW. A rule-based local check can never make that
    distinction reliably.
    """

    blur_severity: TechSeverity = TechSeverity.NONE
    bokeh_is_intentional: bool = False
    noise_severity: TechSeverity = TechSeverity.NONE
    exposure_issue: ExposureIssue = ExposureIssue.NONE
    artifact_severity: TechSeverity = TechSeverity.NONE
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "blur_severity": self.blur_severity.value,
            "bokeh_is_intentional": self.bokeh_is_intentional,
            "noise_severity": self.noise_severity.value,
            "exposure_issue": self.exposure_issue.value,
            "artifact_severity": self.artifact_severity.value,
            "notes": self.notes,
        }

    def has_concern(self) -> bool:
        """True when at least one technical axis is heavy / non-none."""
        if (
            self.blur_severity is TechSeverity.HEAVY
            and not self.bokeh_is_intentional
        ):
            return True
        if self.noise_severity is TechSeverity.HEAVY:
            return True
        if self.artifact_severity is TechSeverity.HEAVY:
            return True
        if self.exposure_issue not in (ExposureIssue.NONE,):
            # Only the strong exposure verdicts. "underexposed" /
            # "overexposed" without a stronger qualifier could be
            # artistic, so we let the AI flag it but don't treat
            # mild light/dark as a concern on its own.
            return self.exposure_issue in (
                ExposureIssue.BLOWN_HIGHLIGHTS,
                ExposureIssue.CRUSHED_SHADOWS,
            )
        return False


@dataclass
class AnatomyResult:
    """Full inspection result for a single image (after tile merge)."""

    file_name: str
    status: AIStatus
    screening_result: ScreeningResult
    quality_score: int = 0
    physical_defect_detected: bool = False
    primary_physical_issue: str = ""
    defect_tags: List[str] = field(default_factory=list)
    main_defects_found: List[DefectFinding] = field(default_factory=list)
    defect_regions: List[DefectRegion] = field(default_factory=list)
    anatomy_check: AnatomyCheck = field(default_factory=AnatomyCheck)
    object_check: ObjectCheck = field(default_factory=ObjectCheck)
    technical_secondary_notes: List[str] = field(default_factory=list)
    technical_quality: TechnicalQuality = field(default_factory=TechnicalQuality)
    overall_summary: str = ""
    recommended_action: str = "review manually"
    confidence: Confidence = Confidence.MEDIUM

    # Bookkeeping that lives outside the prompt contract.
    provider_used: str = ""
    key_label_used: str = ""
    scan_depth: ScanDepth = ScanDepth.DETAILED
    tile_count: int = 0
    duration_seconds: float = 0.0
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "file_name": self.file_name,
            "status": self.status.value,
            "screening_result": self.screening_result.value,
            "quality_score": self.quality_score,
            "physical_defect_detected": self.physical_defect_detected,
            "primary_physical_issue": self.primary_physical_issue,
            "defect_tags": list(self.defect_tags),
            "main_defects_found": [d.to_dict() for d in self.main_defects_found],
            "defect_regions": [r.to_dict() for r in self.defect_regions],
            "anatomy_check": {
                "has_people": self.anatomy_check.has_people,
                "hands_visible": self.anatomy_check.hands_visible,
                "face_visible": self.anatomy_check.face_visible,
                "body_visible": self.anatomy_check.body_visible,
                "issues": list(self.anatomy_check.issues),
            },
            "object_check": {
                "main_objects": list(self.object_check.main_objects),
                "object_defects": list(self.object_check.object_defects),
            },
            "technical_secondary_notes": list(self.technical_secondary_notes),
            "technical_quality": self.technical_quality.to_dict(),
            "overall_summary": self.overall_summary,
            "recommended_action": self.recommended_action,
            "confidence": self.confidence.value,
            "provider_used": self.provider_used,
            "key_label_used": self.key_label_used,
            "scan_depth": self.scan_depth.value,
            "tile_count": self.tile_count,
            "duration_seconds": round(self.duration_seconds, 3),
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# Provider request / response wrappers
# ---------------------------------------------------------------------------

@dataclass
class ImageInput:
    """Image payload sent to a provider.

    `data` is raw image bytes. The provider implementation is responsible
    for any base64 encoding it needs.
    """

    data: bytes
    mime: str = "image/jpeg"
    filename: str = "image.jpg"


@dataclass
class ProviderResponse:
    """Result of a single provider call (full image or tile)."""

    raw_text: str
    parsed: Optional[dict] = None
    error: Optional[str] = None
    rate_limited: bool = False
    invalid_key: bool = False


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

@dataclass
class KeyEntry:
    """A single API key row in Settings."""

    provider: ProviderName
    label: str
    key: str
    model: str
    enabled: bool = True
    priority: int = 0
    status: KeyStatus = KeyStatus.UNTESTED
    last_error: str = ""
    last_used_at: float = 0.0

    def to_dict(self) -> dict:
        return {
            "provider": self.provider.value,
            "label": self.label,
            "key": self.key,
            "model": self.model,
            "enabled": self.enabled,
            "priority": self.priority,
            "status": self.status.value,
            "last_error": self.last_error,
            "last_used_at": self.last_used_at,
        }

    @staticmethod
    def from_dict(d: dict) -> "KeyEntry":
        return KeyEntry(
            provider=ProviderName(d["provider"]),
            label=d.get("label", ""),
            key=d.get("key", ""),
            model=d.get("model", ""),
            enabled=bool(d.get("enabled", True)),
            priority=int(d.get("priority", 0)),
            status=KeyStatus(d.get("status", "untested")),
            last_error=d.get("last_error", ""),
            last_used_at=float(d.get("last_used_at", 0.0)),
        )


def now_ts() -> float:
    return time.time()


# ---------------------------------------------------------------------------
# Tile bookkeeping
# ---------------------------------------------------------------------------

@dataclass
class Tile:
    """One sub-region of an image used for detailed inspection."""

    index: int          # 0-based tile number
    x: int              # left in pixels
    y: int              # top in pixels
    w: int
    h: int
    image: "Optional[Path]" = None  # path to the rendered tile bytes / temp file

    def offset_box_to_full(
        self, box_2d: List[int], full_w: int, full_h: int,
    ) -> List[int]:
        """Convert a 0..1000 box from tile-local space to full-image 0..1000.

        Returns ``[y_min, x_min, y_max, x_max]`` in full-image normalised
        coordinates.
        """
        y0, x0, y1, x1 = box_2d
        # Pixels inside the tile.
        px0 = self.x + (x0 / 1000.0) * self.w
        py0 = self.y + (y0 / 1000.0) * self.h
        px1 = self.x + (x1 / 1000.0) * self.w
        py1 = self.y + (y1 / 1000.0) * self.h
        # Back to 0..1000 of the full image.
        return [
            int(round(py0 / full_h * 1000.0)),
            int(round(px0 / full_w * 1000.0)),
            int(round(py1 / full_h * 1000.0)),
            int(round(px1 / full_w * 1000.0)),
        ]
