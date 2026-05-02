"""Image quality detection metrics.

All formulas are deterministic and operate purely on a single image.
The functions return raw scalar scores; classification is handled
elsewhere so callers can re-classify without re-scoring.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import cv2
import numpy as np


IMAGE_EXTS = {
    ".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff",
    ".gif", ".webp",
}


@dataclass(frozen=True)
class Metrics:
    """Raw per-image metrics. Higher blur = sharper. Higher noise = noisier."""

    width: int
    height: int
    file_kb: float
    blur: float
    noise: float
    exposure_mean: float        # 0..255 average luminance
    exposure_clip_low: float    # fraction of pixels <= 5
    exposure_clip_high: float   # fraction of pixels >= 250
    dynamic_range: float        # p99 - p1 of luminance, 0..255
    artifact: float             # 0 if not jpeg
    is_jpeg: bool


def is_image(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_EXTS


def _laplacian_variance(gray: np.ndarray) -> float:
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _noise_estimate(gray: np.ndarray) -> float:
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    return float(np.std(cv2.absdiff(gray, blurred)))


def _jpeg_blockiness(gray: np.ndarray) -> float:
    """Simple 8x8 block-boundary differential. Higher = stronger artifacts."""
    h, w = gray.shape
    if h < 24 or w < 24:
        return 0.0
    g = gray.astype(np.float32)
    total = 0.0
    count = 0
    for y in range(8, h - 8, 8):
        total += float(np.mean(np.abs(g[y - 1] - g[y])))
        count += 1
    for x in range(8, w - 8, 8):
        total += float(np.mean(np.abs(g[:, x - 1] - g[:, x])))
        count += 1
    return total / count if count else 0.0


def _exposure(gray: np.ndarray) -> tuple[float, float, float, float]:
    """Returns (mean, clip_low_fraction, clip_high_fraction, dynamic_range)."""
    flat = gray.reshape(-1)
    mean = float(flat.mean())
    clip_low = float((flat <= 5).mean())
    clip_high = float((flat >= 250).mean())
    p1 = float(np.percentile(flat, 1))
    p99 = float(np.percentile(flat, 99))
    dynamic_range = p99 - p1
    return mean, clip_low, clip_high, dynamic_range


def load_image(path: Path) -> Optional[np.ndarray]:
    """Read an image as BGR. Returns None on failure. Never modifies the file."""
    try:
        # imdecode avoids cv2.imread issues with non-ASCII paths on Windows.
        with open(path, "rb") as f:
            data = f.read()
        arr = np.frombuffer(data, dtype=np.uint8)
        if arr.size == 0:
            return None
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            return None
        return img
    except Exception:
        return None


def compute_metrics(path: Path) -> Optional[Metrics]:
    """Compute all quality metrics for a single image. Returns None on failure."""
    img = load_image(path)
    if img is None:
        return None

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape

    blur = _laplacian_variance(gray)
    noise = _noise_estimate(gray)
    mean, clip_low, clip_high, dyn_range = _exposure(gray)

    is_jpeg = path.suffix.lower() in (".jpg", ".jpeg")
    artifact = _jpeg_blockiness(gray) if is_jpeg else 0.0

    try:
        kb = path.stat().st_size / 1024.0
    except OSError:
        kb = 0.0

    return Metrics(
        width=int(w),
        height=int(h),
        file_kb=float(kb),
        blur=float(blur),
        noise=float(noise),
        exposure_mean=mean,
        exposure_clip_low=clip_low,
        exposure_clip_high=clip_high,
        dynamic_range=dyn_range,
        artifact=float(artifact),
        is_jpeg=is_jpeg,
    )
