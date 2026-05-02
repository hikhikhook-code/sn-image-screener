"""QThread wrapper for the AI Anatomy Inspector pipeline.

Drives :class:`ParallelAnatomyRunner` for a list of images and forwards
progress events to the UI as Qt signals so the gallery can update its
"Checking tile 3/9" labels without blocking the GUI.

When ``max_workers == 1`` we still use the parallel runner with one
worker — that keeps the worker plumbing single-codepath while behaving
like the legacy serial runner on the wire.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

from PySide6.QtCore import QThread, Signal

from ...services.ai import KeyManager, ParallelAnatomyRunner
from ...services.ai.types import AnatomyResult, ScanDepth


class InspectionWorker(QThread):
    """Run the AI Anatomy pipeline for many images in a background thread."""

    image_started = Signal(str)                # file_name
    image_progress = Signal(str, str, dict)    # file_name, event, payload
    image_done = Signal(str, object)           # file_name, AnatomyResult
    log_line = Signal(str)
    finished_all = Signal()

    def __init__(
        self,
        keys: KeyManager,
        files: List[Path],
        depth: ScanDepth,
        *,
        max_workers: int = 0,
    ) -> None:
        super().__init__()
        self.keys = keys
        self.files = list(files)
        self.depth = depth
        self.max_workers = max_workers
        self._runner: ParallelAnatomyRunner | None = None

    def request_stop(self) -> None:
        self.log_line.emit("AI inspection cancellation requested")
        if self._runner is not None:
            self._runner.stop()

    def run(self) -> None:  # noqa: D401
        self.keys.reset_run_state()
        usable = len(self.keys.usable_keys()) or 1
        workers = self.max_workers if self.max_workers > 0 else usable
        self._runner = ParallelAnatomyRunner(
            self.keys, max_workers=workers,
        )
        self.log_line.emit(
            f"Dispatching {len(self.files)} image(s) with "
            f"{self._runner.max_workers} parallel worker(s)"
        )

        try:
            self._runner.run_batch(
                self.files, self.depth,
                on_image_started=lambda p: self.image_started.emit(p.name),
                on_image_progress=self._on_progress,
                on_image_done=self._on_done,
            )
        except Exception as exc:  # noqa: BLE001 - surface any unexpected error
            self.log_line.emit(f"AI batch crashed: {exc}")
        finally:
            self.finished_all.emit()

    # ------------------------------------------------------------------
    # Callbacks (run on the worker thread)
    # ------------------------------------------------------------------

    def _on_progress(self, path: Path, event: str, payload: dict) -> None:
        self.image_progress.emit(path.name, event, payload)
        if event == "key_switch":
            origin = payload.get("from", "")
            reason = payload.get("reason", "")
            self.log_line.emit(
                f"{path.name}: {origin} {reason} — switching to next key"
            )
        elif event == "error":
            msg = payload.get("message", "")
            self.log_line.emit(f"{path.name}: {msg}")

    def _on_done(self, path: Path, result: AnatomyResult) -> None:
        self.image_done.emit(path.name, result)
        if result.error:
            self.log_line.emit(f"{path.name}: ERROR — {result.error}")
        else:
            self.log_line.emit(
                f"{path.name}: {result.status.value.upper()} "
                f"(score {result.quality_score}, "
                f"{len(result.defect_regions)} marker(s))"
            )
