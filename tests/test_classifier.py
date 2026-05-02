from __future__ import annotations

from pathlib import Path

from sn_image_screener.core.classifier import Status, classify
from sn_image_screener.core.detection import compute_metrics
from sn_image_screener.core.presets import PRESETS


def test_blurred_image_classified_reject(sample_dir: Path):
    rules = PRESETS["Normal"]
    m = compute_metrics(sample_dir / "blur.jpg")
    assert m is not None
    v = classify(m, rules)
    assert v.status is Status.REJECT
    assert any(i.code == "BLUR" for i in v.issues)


def test_dark_image_classified_reject(sample_dir: Path):
    rules = PRESETS["Normal"]
    m = compute_metrics(sample_dir / "dark.jpg")
    assert m is not None
    v = classify(m, rules)
    assert v.status is Status.REJECT
    assert any(i.code == "EXPOSURE" for i in v.issues)


def test_tiny_image_classified_reject(sample_dir: Path):
    rules = PRESETS["Normal"]
    m = compute_metrics(sample_dir / "tiny.jpg")
    assert m is not None
    v = classify(m, rules)
    assert v.status is Status.REJECT
    assert any(i.code == "RES" for i in v.issues)


def test_loose_preset_is_more_permissive_than_strict(sample_dir: Path):
    m = compute_metrics(sample_dir / "ok.jpg")
    assert m is not None
    strict = classify(m, PRESETS["Stock Strict"])
    loose = classify(m, PRESETS["Loose"])
    # Strict can reject the same image that Loose passes, never the other way
    if strict.status is Status.PASS:
        assert loose.status is Status.PASS
    if loose.status is Status.REJECT:
        assert strict.status is Status.REJECT


def test_quality_score_in_bounds(sample_dir: Path):
    rules = PRESETS["Normal"]
    for f in sample_dir.glob("*.jpg"):
        m = compute_metrics(f)
        if m is None:
            continue
        v = classify(m, rules)
        assert 0 <= v.score <= 100
