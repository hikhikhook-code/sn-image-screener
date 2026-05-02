"""Generate a small set of sample images covering each verdict class.

Usage:
    python scripts/make_sample_images.py [out_dir]
"""

from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np


def _gradient(w: int, h: int) -> np.ndarray:
    """A textured gradient — non-trivial Laplacian variance."""
    rng = np.random.default_rng(42)
    x = np.linspace(40, 215, w, dtype=np.float32)
    y = np.linspace(40, 215, h, dtype=np.float32)
    g = (x[None, :] + y[:, None]) * 0.5
    # Sprinkle structure so the image has natural sharpness, not a perfect ramp
    texture = rng.normal(0, 6, g.shape).astype(np.float32)
    edges = np.zeros_like(g)
    for r in range(0, h, 60):
        edges[r:r + 2, :] = 30
    for c in range(0, w, 90):
        edges[:, c:c + 2] = -30
    g = np.clip(g + texture + edges, 0, 255).astype(np.uint8)
    return cv2.merge([g, g, g])


def _checkerboard(w: int, h: int, tile: int = 32) -> np.ndarray:
    img = np.zeros((h, w, 3), dtype=np.uint8)
    for y in range(0, h, tile):
        for x in range(0, w, tile):
            if ((x // tile) + (y // tile)) % 2 == 0:
                img[y:y + tile, x:x + tile] = 230
            else:
                img[y:y + tile, x:x + tile] = 30
    return img


def main(out_dir: Path) -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Crisp gradient → expected PASS
    sharp = _gradient(2000, 1500)
    cv2.imwrite(str(out_dir / "01_pass_sharp_gradient.jpg"), sharp,
                [cv2.IMWRITE_JPEG_QUALITY, 92])

    # 2. Slightly soft variant of the gradient → expected PASS (Normal) / REVIEW (Strict)
    soft = cv2.GaussianBlur(sharp, (5, 5), 0.55)
    cv2.imwrite(str(out_dir / "02_pass_soft.jpg"), soft,
                [cv2.IMWRITE_JPEG_QUALITY, 92])

    # 3. Heavy gaussian blur → expected REJECT (blur)
    blurred = cv2.GaussianBlur(sharp, (51, 51), 25)
    cv2.imwrite(str(out_dir / "03_reject_blurry.jpg"), blurred,
                [cv2.IMWRITE_JPEG_QUALITY, 92])

    # 4. Strong noise → expected REJECT (noise)
    rng = np.random.default_rng(7)
    noisy = sharp.astype(np.int32) + rng.normal(0, 70, sharp.shape).astype(np.int32)
    noisy = np.clip(noisy, 0, 255).astype(np.uint8)
    cv2.imwrite(str(out_dir / "04_reject_noisy.jpg"), noisy,
                [cv2.IMWRITE_JPEG_QUALITY, 92])

    # 5. Underexposed → expected REJECT (exposure)
    dark = (sharp * 0.08).astype(np.uint8)
    cv2.imwrite(str(out_dir / "05_reject_dark.jpg"), dark,
                [cv2.IMWRITE_JPEG_QUALITY, 92])

    # 6. Overexposed → expected REJECT (exposure)
    bright = np.clip(sharp.astype(np.int32) + 200, 0, 255).astype(np.uint8)
    cv2.imwrite(str(out_dir / "06_reject_bright.jpg"), bright,
                [cv2.IMWRITE_JPEG_QUALITY, 92])

    # 7. Mild jpeg artifacts on a smooth gradient → expected REVIEW
    cv2.imwrite(str(out_dir / "07_review_jpeg.jpg"), sharp,
                [cv2.IMWRITE_JPEG_QUALITY, 18])

    # 8. Tiny resolution → expected REJECT (resolution gate)
    tiny = cv2.resize(sharp, (160, 120), interpolation=cv2.INTER_AREA)
    cv2.imwrite(str(out_dir / "08_reject_tiny.jpg"), tiny,
                [cv2.IMWRITE_JPEG_QUALITY, 92])

    print(f"Wrote 8 sample images to {out_dir}")


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("out_samples")
    main(out)
