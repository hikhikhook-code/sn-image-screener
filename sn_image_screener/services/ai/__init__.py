"""AI Anatomy Inspector services package.

Public surface
--------------
:class:`KeyManager` (`from .key_manager import KeyManager`) — manages
the persistent list of API keys with priority and per-run cooldown.

:class:`AnatomyRunner` (`from .run_anatomy_check import AnatomyRunner`)
— runs the full anatomy-inspection pipeline (tile, send, merge,
failover) for one image and returns an :class:`AnatomyResult`.

The Qt UI in :mod:`sn_image_screener.ui.ai` wraps the runner in a
QThread so the desktop app stays responsive.
"""

from .key_manager import KeyManager, MAX_KEYS, default_keys_path, user_data_dir
from .run_anatomy_check import (
    AnatomyRunner, EVT_COMPLETE, EVT_ERROR, EVT_FULL, EVT_KEY_SWITCH,
    EVT_MERGE, EVT_PREPARE, EVT_TILE,
)
from .types import (
    AIStatus, AnatomyResult, Confidence, DefectCategory, DefectFinding,
    DefectRegion, KeyEntry, KeyStatus, ProviderName, ScanDepth,
    ScreeningResult, Severity, Shape, grid_size, tiles_for_depth,
)

__all__ = [
    "KeyManager", "MAX_KEYS", "default_keys_path", "user_data_dir",
    "AnatomyRunner",
    "EVT_PREPARE", "EVT_FULL", "EVT_TILE", "EVT_MERGE", "EVT_COMPLETE",
    "EVT_KEY_SWITCH", "EVT_ERROR",
    "AIStatus", "AnatomyResult", "Confidence", "DefectCategory",
    "DefectFinding", "DefectRegion", "KeyEntry", "KeyStatus",
    "ProviderName", "ScanDepth", "ScreeningResult", "Severity", "Shape",
    "grid_size", "tiles_for_depth",
]
