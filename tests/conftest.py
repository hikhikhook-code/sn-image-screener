from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest


def _gradient(w: int, h: int) -> np.ndarray:
    x = np.linspace(0, 255, w, dtype=np.float32)
    y = np.linspace(0, 255, h, dtype=np.float32)
    g = (x[None, :] + y[:, None]) * 0.5
    g = np.clip(g, 0, 255).astype(np.uint8)
    return cv2.merge([g, g, g])


@pytest.fixture
def sample_dir(tmp_path: Path) -> Path:
    out = tmp_path / "samples"
    out.mkdir()
    base = _gradient(1200, 900)

    # PASS-ish sharp gradient
    cv2.imwrite(str(out / "ok.jpg"), base, [cv2.IMWRITE_JPEG_QUALITY, 92])

    # Heavy blur
    blurred = cv2.GaussianBlur(base, (51, 51), 25)
    cv2.imwrite(str(out / "blur.jpg"), blurred, [cv2.IMWRITE_JPEG_QUALITY, 92])

    # Noise
    rng = np.random.default_rng(7)
    noise = rng.normal(0, 50, base.shape).astype(np.int32)
    noisy = np.clip(base.astype(np.int32) + noise, 0, 255).astype(np.uint8)
    cv2.imwrite(str(out / "noise.jpg"), noisy, [cv2.IMWRITE_JPEG_QUALITY, 92])

    # Dark
    dark = (base * 0.08).astype(np.uint8)
    cv2.imwrite(str(out / "dark.jpg"), dark, [cv2.IMWRITE_JPEG_QUALITY, 92])

    # Tiny
    tiny = cv2.resize(base, (160, 120), interpolation=cv2.INTER_AREA)
    cv2.imwrite(str(out / "tiny.jpg"), tiny, [cv2.IMWRITE_JPEG_QUALITY, 92])

    # Corrupt
    (out / "corrupt.jpg").write_bytes(b"\x00\x01\x02not an image")

    return out
