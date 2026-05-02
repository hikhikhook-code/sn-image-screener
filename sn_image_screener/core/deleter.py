"""Safe file deletion utilities.

By default, files are moved to the OS Recycle Bin / Trash via `send2trash`,
so they can be recovered. A `permanent=True` flag will perform an
unrecoverable `os.remove`.

Returns a `(deleted, errors)` tuple so the caller can show a per-file
report rather than aborting the whole batch on a single failure.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, List, Tuple


def trash_files(
    paths: Iterable[Path],
    permanent: bool = False,
) -> Tuple[List[Path], List[Tuple[Path, str]]]:
    """Move (or permanently delete) the given files.

    Returns:
        (deleted, errors)
        deleted: paths that were successfully removed.
        errors:  list of (path, message) for failures.
    """
    deleted: List[Path] = []
    errors: List[Tuple[Path, str]] = []

    if not permanent:
        try:
            from send2trash import send2trash  # type: ignore
        except ImportError:
            errors.append((
                Path(""),
                "Send2Trash is not installed. Install it with "
                "`pip install Send2Trash` or enable 'Permanent delete' in Advanced.",
            ))
            return deleted, errors
    else:
        send2trash = None  # type: ignore

    for p in paths:
        try:
            if not p.exists():
                errors.append((p, "file no longer exists"))
                continue
            if permanent:
                os.remove(p)
            else:
                send2trash(str(p))  # type: ignore[misc]
            deleted.append(p)
        except Exception as exc:  # noqa: BLE001
            errors.append((p, str(exc)))

    return deleted, errors


def total_size(paths: Iterable[Path]) -> int:
    """Sum file sizes (best-effort; missing files counted as zero)."""
    total = 0
    for p in paths:
        try:
            total += p.stat().st_size
        except OSError:
            pass
    return total


def human_size(n: int) -> str:
    """Format byte count as a short human-readable string."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024.0:
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024.0
    return f"{n:.1f} PB"
