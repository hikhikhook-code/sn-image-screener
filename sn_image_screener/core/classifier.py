"""Classify a Metrics record into PASS / REVIEW / REJECT and a 0-100 score."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List

from .detection import Metrics
from .presets import Rules


class Status(str, Enum):
    PASS = "PASS"
    REVIEW = "REVIEW"
    REJECT = "REJECT"
    ERROR = "ERROR"


@dataclass
class Issue:
    code: str          # short tag e.g. "BLUR"
    label: str         # human description
    severity: str      # "reject" | "review"


@dataclass
class Verdict:
    status: Status
    score: int                       # 0..100, higher = better
    issues: List[Issue] = field(default_factory=list)
    metric_scores: dict = field(default_factory=dict)  # per-metric 0..100


def _smooth(value: float, low: float, high: float) -> float:
    """Map value into 0..1 with linear ramp between low and high."""
    if high == low:
        return 1.0 if value >= low else 0.0
    if value <= low:
        return 0.0
    if value >= high:
        return 1.0
    return (value - low) / (high - low)


def _blur_score(blur: float, rules: Rules) -> float:
    return _smooth(blur, rules.blur_reject * 0.5, rules.blur_review * 1.5) * 100.0


def _noise_score(noise: float, rules: Rules) -> float:
    # Inverted: lower noise is better.
    return (1.0 - _smooth(noise, rules.noise_review * 0.5, rules.noise_reject * 1.5)) * 100.0


def _artifact_score(artifact: float, is_jpeg: bool, rules: Rules) -> float:
    if not is_jpeg:
        return 100.0
    return (1.0 - _smooth(artifact, rules.artifact_review * 0.5, rules.artifact_reject * 1.5)) * 100.0


def _exposure_score(m: Metrics, rules: Rules) -> float:
    # Penalise being far from the centre of the safe window
    center = (rules.exposure_review_low + rules.exposure_review_high) / 2.0
    half_safe = (rules.exposure_review_high - rules.exposure_review_low) / 2.0
    half_max = (rules.exposure_mean_max - rules.exposure_mean_min) / 2.0
    if half_max <= 0:
        return 100.0
    dist = abs(m.exposure_mean - center)
    if dist <= half_safe:
        base = 100.0
    elif dist >= half_max:
        base = 0.0
    else:
        base = (1.0 - (dist - half_safe) / max(half_max - half_safe, 1e-6)) * 100.0

    clip_pen = (
        max(0.0, m.exposure_clip_low - rules.clip_low_review) * 200.0 +
        max(0.0, m.exposure_clip_high - rules.clip_high_review) * 200.0
    )
    base -= min(50.0, clip_pen)
    return max(0.0, min(100.0, base))


def classify(m: Metrics, rules: Rules) -> Verdict:
    issues: List[Issue] = []

    # Per-metric 0..100 sub-scores (used for the overall quality score).
    blur_s = _blur_score(m.blur, rules)
    noise_s = _noise_score(m.noise, rules)
    artifact_s = _artifact_score(m.artifact, m.is_jpeg, rules)
    exposure_s = _exposure_score(m, rules)

    # Hard rejects: file too small / resolution too small.
    if m.file_kb < rules.min_file_kb:
        issues.append(Issue("FILESIZE", f"File too small ({m.file_kb:.0f} KB)", "reject"))
    if m.width < rules.min_width or m.height < rules.min_height:
        issues.append(Issue("RES", f"Resolution {m.width}x{m.height}", "reject"))

    # Blur
    if m.blur < rules.blur_reject:
        issues.append(Issue("BLUR", f"Blurry (sharpness {m.blur:.0f})", "reject"))
    elif m.blur < rules.blur_review:
        issues.append(Issue("BLUR", f"Slightly soft (sharpness {m.blur:.0f})", "review"))

    # Noise
    if m.noise > rules.noise_reject:
        issues.append(Issue("NOISE", f"Heavy noise ({m.noise:.1f})", "reject"))
    elif m.noise > rules.noise_review:
        issues.append(Issue("NOISE", f"Some noise ({m.noise:.1f})", "review"))

    # Artifacts (JPEG only)
    if m.is_jpeg:
        if m.artifact > rules.artifact_reject:
            issues.append(Issue("ARTIFACT", f"JPEG artefacts ({m.artifact:.1f})", "reject"))
        elif m.artifact > rules.artifact_review:
            issues.append(Issue("ARTIFACT", f"Mild JPEG artefacts ({m.artifact:.1f})", "review"))

    # Exposure
    if m.exposure_mean < rules.exposure_mean_min:
        issues.append(Issue("EXPOSURE", f"Underexposed (mean {m.exposure_mean:.0f})", "reject"))
    elif m.exposure_mean > rules.exposure_mean_max:
        issues.append(Issue("EXPOSURE", f"Overexposed (mean {m.exposure_mean:.0f})", "reject"))
    elif m.exposure_mean < rules.exposure_review_low:
        issues.append(Issue("EXPOSURE", f"Dark (mean {m.exposure_mean:.0f})", "review"))
    elif m.exposure_mean > rules.exposure_review_high:
        issues.append(Issue("EXPOSURE", f"Bright (mean {m.exposure_mean:.0f})", "review"))

    if m.exposure_clip_low > rules.clip_low_reject:
        issues.append(Issue("CLIP", f"Crushed shadows ({m.exposure_clip_low * 100:.0f}%)", "reject"))
    elif m.exposure_clip_low > rules.clip_low_review:
        issues.append(Issue("CLIP", f"Shadow clipping ({m.exposure_clip_low * 100:.0f}%)", "review"))

    if m.exposure_clip_high > rules.clip_high_reject:
        issues.append(Issue("CLIP", f"Blown highlights ({m.exposure_clip_high * 100:.0f}%)", "reject"))
    elif m.exposure_clip_high > rules.clip_high_review:
        issues.append(Issue("CLIP", f"Highlight clipping ({m.exposure_clip_high * 100:.0f}%)", "review"))

    if m.dynamic_range < rules.dynamic_range_review:
        issues.append(Issue("FLAT", f"Low dynamic range ({m.dynamic_range:.0f})", "review"))

    # Determine status: any reject -> REJECT, any review -> REVIEW, else PASS
    has_reject = any(i.severity == "reject" for i in issues)
    has_review = any(i.severity == "review" for i in issues)
    if has_reject:
        status = Status.REJECT
    elif has_review:
        status = Status.REVIEW
    else:
        status = Status.PASS

    # Aggregate quality score: weighted mean of sub-scores, then penalised
    # by gating issues so a tiny file never gets a glamorous score.
    weighted = (
        0.35 * blur_s +
        0.25 * noise_s +
        0.20 * exposure_s +
        0.20 * artifact_s
    )
    if any(i.code in ("FILESIZE", "RES") for i in issues):
        weighted = min(weighted, 35.0)
    if status is Status.REJECT:
        weighted = min(weighted, 49.0)
    elif status is Status.REVIEW:
        weighted = min(weighted, 79.0)

    return Verdict(
        status=status,
        score=int(round(max(0.0, min(100.0, weighted)))),
        issues=issues,
        metric_scores={
            "blur": int(round(blur_s)),
            "noise": int(round(noise_s)),
            "exposure": int(round(exposure_s)),
            "artifact": int(round(artifact_s)),
        },
    )
