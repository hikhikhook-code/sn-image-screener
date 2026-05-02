"""Quality-rule presets. A preset is a snapshot of all thresholds.

Three levels are exposed:

* Stock Strict — agency / microstock submission grade
* Normal       — general photo culling
* Loose        — minimum bar, tolerates slight blur / noise

These thresholds are intentionally conservative defaults; the user can
override any field through the Advanced settings drawer.
"""

from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class Rules:
    # File / dimension gating
    min_file_kb: float = 30.0
    min_width: int = 1024
    min_height: int = 1024

    # Sharpness — Laplacian variance. Higher = sharper.
    blur_reject: float = 60.0     # below this → REJECT
    blur_review: float = 120.0    # below this → REVIEW

    # Noise — std of high-pass residual. Higher = noisier.
    noise_reject: float = 28.0    # above this → REJECT
    noise_review: float = 18.0    # above this → REVIEW

    # JPEG block artifacts. Higher = worse.
    artifact_reject: float = 14.0
    artifact_review: float = 9.0

    # Exposure — luminance mean window and clipping fractions
    exposure_mean_min: float = 35.0      # below → underexposed reject
    exposure_mean_max: float = 225.0     # above → overexposed reject
    exposure_review_low: float = 55.0    # below → underexposed review
    exposure_review_high: float = 205.0  # above → overexposed review
    clip_low_reject: float = 0.35
    clip_high_reject: float = 0.20
    clip_low_review: float = 0.20
    clip_high_review: float = 0.10
    dynamic_range_review: float = 60.0


PRESET_STOCK_STRICT = Rules(
    min_file_kb=80.0,
    min_width=2000,
    min_height=2000,
    blur_reject=120.0,
    blur_review=200.0,
    noise_reject=18.0,
    noise_review=12.0,
    artifact_reject=10.0,
    artifact_review=6.0,
    exposure_mean_min=45.0,
    exposure_mean_max=215.0,
    exposure_review_low=65.0,
    exposure_review_high=195.0,
    clip_low_reject=0.20,
    clip_high_reject=0.10,
    clip_low_review=0.10,
    clip_high_review=0.05,
    dynamic_range_review=80.0,
)

PRESET_NORMAL = Rules()  # the dataclass defaults

PRESET_LOOSE = Rules(
    min_file_kb=10.0,
    min_width=640,
    min_height=480,
    blur_reject=30.0,
    blur_review=70.0,
    noise_reject=40.0,
    noise_review=28.0,
    artifact_reject=20.0,
    artifact_review=14.0,
    exposure_mean_min=20.0,
    exposure_mean_max=240.0,
    exposure_review_low=35.0,
    exposure_review_high=220.0,
    clip_low_reject=0.50,
    clip_high_reject=0.35,
    clip_low_review=0.35,
    clip_high_review=0.20,
    dynamic_range_review=40.0,
)


PRESETS: dict[str, Rules] = {
    "Stock Strict": PRESET_STOCK_STRICT,
    "Normal": PRESET_NORMAL,
    "Loose": PRESET_LOOSE,
}


def with_overrides(base: Rules, **overrides) -> Rules:
    return replace(base, **overrides)
