"""Image tiling for the AI Anatomy Inspector.

Why tile?
---------
A vision model that looks at a 4K image rescaled to ~768px loses fine
detail (broken fingers, melted text, tiny logos). For Detailed and
Ultra modes we additionally cut the image into a 3×3 / 4×4 grid and
inspect each tile so small defects are still resolvable.

Public API
----------
- :func:`build_tiles(image_path, depth)` — split an image into tiles
  and write each tile to a temp file. Returns ``(full_path, [Tile])``
  where ``full_path`` is the original image (or a recompressed
  version if it was huge) and each :class:`~.types.Tile` carries its
  pixel offset back into the original.
"""

from __future__ import annotations

import io
import tempfile
from pathlib import Path
from typing import List, Tuple

from PIL import Image

from .types import ScanDepth, Tile, grid_size


# Hard cap for the full-image inspection: vision providers reject very
# large payloads, and the prompt does not benefit from more pixels than
# the model can resolve. 1568 px on the long edge keeps Gemini /
# OpenAI / Groq happy while still giving the model enough detail.
MAX_FULL_LONG_EDGE = 1568

# Tile encode quality. JPEG keeps the request small without losing
# enough detail to matter for a 768-pixel-tall ML inspection.
TILE_JPEG_QUALITY = 88
TILE_LONG_EDGE_CAP = 1024


# Vision providers reject degenerate images: Groq returns
# ``HTTP 400 "Image must have at least 2 pixels in each dimension"``,
# so anything we send must have both width and height ≥ this floor.
# This also covers extreme aspect ratios where ``_resize_long_edge``
# would otherwise round the short edge down to 0 or 1 px.
_MIN_DIM = 2


def _resize_long_edge(img: Image.Image, max_long: int) -> Image.Image:
    """Resize so the long edge ≤ ``max_long`` and both dims ≥ ``_MIN_DIM``.

    For typical screenshots this is a no-op when the image is already
    small enough. For images with extreme aspect ratios (e.g.
    ``4000×3``), naive proportional scaling collapses the short edge to
    1 px, which the vision providers then reject — so we clamp both
    output dims to at least ``_MIN_DIM`` even if it slightly distorts
    the aspect ratio.
    """
    w, h = img.size
    long_edge = max(w, h)
    if long_edge <= max_long and min(w, h) >= _MIN_DIM:
        return img
    if long_edge > max_long:
        scale = max_long / long_edge
        new_w = int(round(w * scale))
        new_h = int(round(h * scale))
    else:
        new_w, new_h = w, h
    new_w = max(_MIN_DIM, new_w)
    new_h = max(_MIN_DIM, new_h)
    return img.resize((new_w, new_h), Image.LANCZOS)


def encode_for_provider(
    image_path: Path, max_long: int = MAX_FULL_LONG_EDGE,
    quality: int = TILE_JPEG_QUALITY,
) -> Tuple[bytes, str]:
    """Encode `image_path` as JPEG, resized so the long edge ≤ `max_long`.

    Returns ``(bytes, mime)``. Always JPEG to keep payloads predictable.
    """
    with Image.open(image_path) as im:
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGB")
        im = _resize_long_edge(im, max_long)
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=quality, optimize=True)
        return buf.getvalue(), "image/jpeg"


def build_tiles(
    image_path: Path, depth: ScanDepth, *, tmp_dir: Path | None = None,
) -> Tuple[int, int, List[Tile]]:
    """Split `image_path` into tiles for the requested scan depth.

    Returns ``(full_w, full_h, tiles)`` where ``full_w/full_h`` are the
    pixel dimensions of the ORIGINAL image and `tiles` is the list of
    sub-regions. For :data:`ScanDepth.FAST` `tiles` is empty and only
    the full image is inspected.

    The caller is responsible for cleaning up `tmp_dir` once the run
    is finished. If `tmp_dir` is ``None`` a fresh directory is created
    under the system temp folder.
    """
    n = grid_size(depth)
    image_path = Path(image_path)

    with Image.open(image_path) as im:
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGB")
        full_w, full_h = im.size

        if n == 0:
            return full_w, full_h, []

        if tmp_dir is None:
            tmp_dir = Path(tempfile.mkdtemp(prefix="sn_ai_tiles_"))
        else:
            tmp_dir.mkdir(parents=True, exist_ok=True)

        tiles: List[Tile] = []
        # Use floor division for the first n-1 tiles and absorb the
        # remainder into the last column / row so tiles still cover the
        # whole image even when full_w/full_h is not divisible by n.
        col_edges = [round(i * full_w / n) for i in range(n + 1)]
        row_edges = [round(i * full_h / n) for i in range(n + 1)]

        idx = 0
        for ry in range(n):
            for cx in range(n):
                x0 = col_edges[cx]
                x1 = col_edges[cx + 1]
                y0 = row_edges[ry]
                y1 = row_edges[ry + 1]
                tile_w = x1 - x0
                tile_h = y1 - y0

                # Tiny source images can produce degenerate tiles
                # (e.g. a 3-px-wide image split into a 4×4 grid yields
                # zero-width columns). Skip those — they can't carry
                # any signal and the vision provider would reject them
                # with "Image must have at least 2 pixels in each
                # dimension".
                if tile_w < _MIN_DIM or tile_h < _MIN_DIM:
                    continue

                tile_im = im.crop((x0, y0, x1, y1))
                tile_im = _resize_long_edge(tile_im, TILE_LONG_EDGE_CAP)
                tile_path = tmp_dir / f"tile_{idx:02d}.jpg"
                tile_im.save(
                    tile_path, format="JPEG",
                    quality=TILE_JPEG_QUALITY, optimize=True,
                )

                tiles.append(Tile(
                    index=idx,
                    x=x0, y=y0,
                    w=tile_w, h=tile_h,
                    image=tile_path,
                ))
                idx += 1

        return full_w, full_h, tiles


def read_tile_bytes(tile: Tile) -> bytes:
    """Read the encoded bytes of a previously-built tile."""
    if tile.image is None:
        raise ValueError(f"Tile {tile.index} has no rendered image path")
    return tile.image.read_bytes()
