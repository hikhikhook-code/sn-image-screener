"""Icon loader.

Single source of truth for the SN IMAGE SCREENER logo so the same artwork
appears as the OS window icon, the in-app brand badge, and the bundled
.exe icon.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PySide6.QtGui import QIcon, QPixmap

# .../sn_image_screener/ui/icons.py -> .../sn_image_screener/assets
_ASSET_DIR = Path(__file__).resolve().parent.parent / "assets"


def asset_path(name: str) -> Path:
    """Absolute path to an asset file."""
    return _ASSET_DIR / name


@lru_cache(maxsize=1)
def app_icon() -> QIcon:
    """Multi-resolution app icon (used as the window/taskbar icon)."""
    icon = QIcon()
    for size in (16, 32, 64, 128, 256, 512):
        candidate = _ASSET_DIR / f"logo_{size}.png"
        if candidate.exists():
            icon.addFile(str(candidate), QPixmap(str(candidate)).size())
    if icon.isNull():
        # Fall back to the master logo if size-variants are missing.
        master = _ASSET_DIR / "logo.png"
        if master.exists():
            icon.addFile(str(master))
    return icon


def logo_pixmap(height: int) -> QPixmap:
    """Aspect-preserved pixmap of the brand logo, scaled to the requested height."""
    master = _ASSET_DIR / "logo.png"
    if master.exists():
        from PySide6.QtCore import Qt
        pm = QPixmap(str(master))
        return pm.scaledToHeight(
            height,
            Qt.TransformationMode.SmoothTransformation,
        )
    return QPixmap()
