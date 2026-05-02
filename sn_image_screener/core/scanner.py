"""Scan-result model and pure helpers (no Qt)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional

from .classifier import Verdict, Status, classify
from .detection import IMAGE_EXTS, Metrics, compute_metrics, is_image
from .presets import Rules


@dataclass
class ScanItem:
    path: Path
    metrics: Optional[Metrics] = None
    verdict: Optional[Verdict] = None
    error: Optional[str] = None

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def status(self) -> Status:
        if self.error is not None:
            return Status.ERROR
        if self.verdict is None:
            return Status.ERROR
        return self.verdict.status

    @property
    def score(self) -> int:
        return self.verdict.score if self.verdict else 0


def collect_paths(folders: Iterable[Path], files: Iterable[Path]) -> List[Path]:
    """Resolve a mix of folders and individual files into a deduped list of image paths.

    Folders are scanned non-recursively to mirror the behaviour of the
    original tool. Hidden files are skipped.
    """
    seen: set[Path] = set()
    out: List[Path] = []

    for f in files:
        p = Path(f)
        if p.is_file() and is_image(p):
            rp = p.resolve()
            if rp not in seen:
                seen.add(rp)
                out.append(rp)

    for d in folders:
        d = Path(d)
        if not d.is_dir():
            continue
        for child in sorted(d.iterdir()):
            if child.name.startswith("."):
                continue
            if child.is_file() and is_image(child):
                rp = child.resolve()
                if rp not in seen:
                    seen.add(rp)
                    out.append(rp)
    return out


def screen_one(path: Path, rules: Rules) -> ScanItem:
    """Read-only screening of a single file. Never modifies the input."""
    try:
        m = compute_metrics(path)
    except Exception as exc:  # pragma: no cover - defensive
        return ScanItem(path=path, error=f"{type(exc).__name__}: {exc}")

    if m is None:
        return ScanItem(path=path, error="Could not decode image")

    verdict = classify(m, rules)
    return ScanItem(path=path, metrics=m, verdict=verdict)
