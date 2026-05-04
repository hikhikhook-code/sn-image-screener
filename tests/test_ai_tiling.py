"""Tests for AI tiling and tile-coordinate translation."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from sn_image_screener.services.ai.tiling import build_tiles, encode_for_provider
from sn_image_screener.services.ai.types import ScanDepth, Tile


@pytest.fixture
def big_image(tmp_path: Path) -> Path:
    """A 4000×3000 dummy image (so tiles are non-trivial)."""
    p = tmp_path / "big.jpg"
    Image.new("RGB", (4000, 3000), color=(120, 80, 200)).save(p, "JPEG")
    return p


def test_fast_depth_no_tiles(big_image: Path):
    full_w, full_h, tiles = build_tiles(big_image, ScanDepth.FAST)
    assert full_w == 4000 and full_h == 3000
    assert tiles == []


def test_detailed_depth_3x3(big_image: Path):
    full_w, full_h, tiles = build_tiles(big_image, ScanDepth.DETAILED)
    assert len(tiles) == 9
    assert full_w == 4000 and full_h == 3000
    # Tiles cover the whole image with no gaps and no overlap.
    coverage = sum(t.w * t.h for t in tiles)
    assert coverage == full_w * full_h
    # Every tile actually wrote a JPEG.
    for t in tiles:
        assert t.image is not None and t.image.exists()
        assert t.image.stat().st_size > 0


def test_ultra_depth_4x4(big_image: Path):
    _, _, tiles = build_tiles(big_image, ScanDepth.ULTRA)
    assert len(tiles) == 16


def test_tile_offset_translation_round_trip(big_image: Path):
    full_w, full_h, tiles = build_tiles(big_image, ScanDepth.DETAILED)
    # Pick the centre tile (index 4 = row 1, col 1) and translate the
    # tile-local centre back to full-image coordinates.
    centre = tiles[4]
    box_local = [400, 400, 600, 600]  # 0..1000 inside the tile
    box_full = centre.offset_box_to_full(box_local, full_w, full_h)
    # Centre of the centre tile must land near (full_w/2, full_h/2)
    cy = (box_full[0] + box_full[2]) / 2
    cx = (box_full[1] + box_full[3]) / 2
    # Within ±20 (1000-scale) of centre.
    assert abs(cy - 500) <= 20
    assert abs(cx - 500) <= 20


def test_encode_for_provider_resizes_huge(big_image: Path):
    data, mime = encode_for_provider(big_image, max_long=512)
    assert mime == "image/jpeg"
    # Round-trip and check the long edge.
    from io import BytesIO
    im = Image.open(BytesIO(data))
    assert max(im.size) <= 512


def test_encode_for_provider_clamps_min_dim_on_thin_image(tmp_path: Path):
    """A 4000×3 strip would naively scale to 1568×1 and trigger Groq's
    "Image must have at least 2 pixels in each dimension" 400. The
    encoder must clamp every output dim to ≥ 2 px instead.
    """
    p = tmp_path / "thin.jpg"
    Image.new("RGB", (4000, 3), color=(0, 0, 0)).save(p, "JPEG")
    data, _ = encode_for_provider(p, max_long=1568)
    from io import BytesIO
    im = Image.open(BytesIO(data))
    assert min(im.size) >= 2, f"got degenerate dims {im.size}"


def test_encode_for_provider_keeps_tiny_image_above_min_dim(tmp_path: Path):
    """A 100×1 image (already short enough that no long-edge resize is
    needed) must still come out with both dims ≥ 2.
    """
    p = tmp_path / "tiny.jpg"
    Image.new("RGB", (100, 1), color=(0, 0, 0)).save(p, "JPEG")
    data, _ = encode_for_provider(p, max_long=1568)
    from io import BytesIO
    im = Image.open(BytesIO(data))
    assert min(im.size) >= 2


def test_build_tiles_skips_degenerate_tiles(tmp_path: Path):
    """Splitting a 3-px-wide image into a 4×4 grid produces zero-width
    columns that the vision provider would reject. Those tiles must be
    skipped, and any tile that IS produced must be ≥ 2 px on every side.
    """
    p = tmp_path / "narrow.jpg"
    Image.new("RGB", (3, 200), color=(0, 0, 0)).save(p, "JPEG")
    _, _, tiles = build_tiles(p, ScanDepth.ULTRA)
    for t in tiles:
        assert t.w >= 2 and t.h >= 2, f"tile {t.index} too small: {t.w}×{t.h}"
        assert t.image is not None and t.image.exists()
        with Image.open(t.image) as ti:
            assert min(ti.size) >= 2
