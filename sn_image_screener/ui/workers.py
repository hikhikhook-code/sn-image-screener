"""Background workers for the scan pipeline.

The scanner runs in its own QThread so the GUI stays responsive. The
scanner only ever reads images; it never writes back to the source
files. Pause / resume / stop are cooperative.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

from PySide6.QtCore import QObject, QThread, Signal

from ..core.presets import Rules
from ..core.scanner import ScanItem, screen_one


class ScanWorker(QObject):
    """Workhorse QObject — moved onto a QThread by the main window.

    Signals:
        started:           emitted with the total file count.
        item_done(item):   one ScanItem completed.
        progress(i, n):    1-based index / total.
        finished(stopped): emitted at the end. stopped=True if user stopped.
    """

    started = Signal(int)
    item_done = Signal(object)        # ScanItem
    progress = Signal(int, int)
    finished = Signal(bool)

    def __init__(self, paths: List[Path], rules: Rules):
        super().__init__()
        self._paths = list(paths)
        self._rules = rules
        self._stop = False
        self._pause = False

    # Cooperative controls --------------------------------------------------

    def stop(self) -> None:
        self._stop = True

    def pause(self, value: bool) -> None:
        self._pause = bool(value)

    # Worker loop -----------------------------------------------------------

    def run(self) -> None:
        total = len(self._paths)
        self.started.emit(total)
        stopped = False

        for i, path in enumerate(self._paths, start=1):
            if self._stop:
                stopped = True
                break

            # Cooperative pause loop.
            while self._pause and not self._stop:
                QThread.msleep(120)
            if self._stop:
                stopped = True
                break

            item = screen_one(path, self._rules)
            self.item_done.emit(item)
            self.progress.emit(i, total)

        self.finished.emit(stopped)
