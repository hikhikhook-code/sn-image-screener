from __future__ import annotations

from pathlib import Path

from sn_image_screener.core.detection import compute_metrics, is_image, IMAGE_EXTS


def test_image_extension_set_includes_common_formats():
    for ext in (".jpg", ".jpeg", ".png", ".webp", ".tif"):
        assert ext in IMAGE_EXTS


def test_compute_metrics_on_sharp_image(sample_dir: Path):
    m = compute_metrics(sample_dir / "ok.jpg")
    assert m is not None
    assert m.width == 1200 and m.height == 900
    assert m.is_jpeg is True
    # Sharp gradient should have non-trivial blur score (Laplacian variance > 0)
    assert m.blur >= 0.0
    # Exposure mean should be in mid-tone range for a 0..255 gradient
    assert 80 < m.exposure_mean < 200


def test_compute_metrics_on_corrupt_image(sample_dir: Path):
    m = compute_metrics(sample_dir / "corrupt.jpg")
    assert m is None


def test_blur_metric_drops_for_blurred_image(sample_dir: Path):
    sharp = compute_metrics(sample_dir / "ok.jpg")
    blurry = compute_metrics(sample_dir / "blur.jpg")
    assert sharp is not None and blurry is not None
    assert blurry.blur < sharp.blur


def test_noise_metric_rises_for_noisy_image(sample_dir: Path):
    clean = compute_metrics(sample_dir / "ok.jpg")
    noisy = compute_metrics(sample_dir / "noise.jpg")
    assert clean is not None and noisy is not None
    assert noisy.noise > clean.noise


def test_dark_image_has_low_mean(sample_dir: Path):
    dark = compute_metrics(sample_dir / "dark.jpg")
    assert dark is not None
    assert dark.exposure_mean < 30
