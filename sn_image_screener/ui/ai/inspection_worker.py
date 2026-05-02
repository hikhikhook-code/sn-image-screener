"""QThread wrapper for AnatomyRunner.

Drives the Anatomy Inspector pipeline for a list of images and forwards
progress events to the UI as Qt signals so the gallery can update its
"Checking tile 3/9" labels without blocking the GUI.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

from PySide6.QtCore import QThread, Signal

from ...services.ai import AnatomyRunner, KeyManager
from ...services.ai.types import AnatomyResult, ScanDepth


class InspectionWorker(QThread):
    """Run :class:`AnatomyRunner` for many images in a background thread."""

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
    ) -> None:
        super().__init__()
        self.keys = keys
        self.files = list(files)
        self.depth = depth
        self._stop = False

    def request_stop(self) -> None:
        self._stop = True

    def run(self) -> None:  # noqa: D401
        runner = AnatomyRunner(self.keys)
        self.keys.reset_run_state()
        for path in self.files:
            if self._stop:
                self.log_line.emit("AI inspection cancelled")
                break
            self.image_started.emit(path.name)
            try:
                result: AnatomyResult = runner.run(
                    path, self.depth,
                    progress=lambda evt, payload, p=path.name:
                        self._on_progress(p, evt, payload),
                )
            except Exception as exc:  # noqa: BLE001
                self.log_line.emit(f"{path.name}: {exc}")
                continue
            self.image_done.emit(path.name, result)
            if result.error:
                self.log_line.emit(f"{path.name}: ERROR — {result.error}")
            else:
                self.log_line.emit(
                    f"{path.name}: {result.status.value.upper()} "
                    f"(score {result.quality_score}, "
                    f"{len(result.defect_regions)} marker(s))"
                )
        self.finished_all.emit()

    def _on_progress(self, file_name: str, event: str, payload: dict) -> None:
        self.image_progress.emit(file_name, event, payload)
        if event == "key_switch":
            origin = payload.get("from", "")
            reason = payload.get("reason", "")
            self.log_line.emit(
                f"{file_name}: {origin} {reason} — switching to next key"
            )
