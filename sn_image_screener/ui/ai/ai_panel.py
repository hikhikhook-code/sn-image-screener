"""AI Anatomy Inspector tab.

Three column layout (a single root widget plopped into the main
``QTabWidget``):

    ┌──────────────┬───────────────────────┬────────────────┐
    │  CONTROLS    │  GALLERY / QUEUE      │  REPORT        │
    │  (depth,     │  (thumbnail + status) │  (selected     │
    │   run, etc.) │                       │   image)       │
    └──────────────┴───────────────────────┴────────────────┘

The gallery shares its file list with the existing Technical Quality
tab through :class:`AIPanel.set_files` so users can scan in either tab
without re-importing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QButtonGroup, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QMessageBox, QProgressBar, QPushButton, QRadioButton, QSizePolicy,
    QSpinBox, QSplitter, QVBoxLayout, QWidget,
)

from ...services.ai import KeyManager
from ...services.ai.types import (
    AIStatus, AnatomyResult, ScanDepth,
)
from .inspection_worker import InspectionWorker
from .key_settings_dialog import KeySettingsDialog
from .marker_view import MarkerView
from .report_panel import ReportPanel
from .review_dialog import AIReviewDialog


_DEPTH_LABEL = {
    ScanDepth.FAST: "FAST · full image only (1 inspection)",
    ScanDepth.DETAILED: "DETAILED · 3 × 3 tiles (10 inspections) — default",
    ScanDepth.ULTRA: "ULTRA · 4 × 4 tiles (17 inspections)",
}


class AIPanel(QWidget):
    """The AI Anatomy Inspector tab widget."""

    log_line = Signal(str)

    def __init__(
        self,
        key_manager: KeyManager,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.km = key_manager
        self._files: List[Path] = []
        self._results: Dict[str, AnatomyResult] = {}
        self._worker: Optional[InspectionWorker] = None
        self._build()

    # ------------------------------------------------------------------
    # Build UI
    # ------------------------------------------------------------------

    def _build(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_left_controls())
        splitter.addWidget(self._build_centre_gallery())
        splitter.addWidget(self._build_right_preview())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 2)
        splitter.setStretchFactor(2, 2)
        splitter.setSizes([300, 540, 540])
        root.addWidget(splitter)

    def _build_left_controls(self) -> QWidget:
        w = QWidget()
        w.setMaximumWidth(360)
        w.setMinimumWidth(280)
        v = QVBoxLayout(w)
        v.setContentsMargins(14, 14, 14, 14)
        v.setSpacing(10)

        header = QLabel("AI ANATOMY INSPECTOR")
        f = header.font()
        f.setBold(True)
        f.setPointSize(f.pointSize() + 2)
        header.setFont(f)
        header.setStyleSheet("letter-spacing:2px;")
        v.addWidget(header)

        sub = QLabel(
            "Detects physical defects (anatomy, hands, faces, objects, "
            "logos, AI artifacts) using a vision model. The Technical "
            "Quality tab still handles blur / noise / exposure locally."
        )
        sub.setWordWrap(True)
        sub.setStyleSheet("color:#555555;")
        v.addWidget(sub)

        v.addWidget(_section_label("SCAN DEPTH"))
        self.rb_depth: Dict[ScanDepth, QRadioButton] = {}
        depth_group = QButtonGroup(self)
        for depth in (ScanDepth.FAST, ScanDepth.DETAILED, ScanDepth.ULTRA):
            rb = QRadioButton(_DEPTH_LABEL[depth])
            rb.setStyleSheet("padding:2px 0;")
            self.rb_depth[depth] = rb
            depth_group.addButton(rb)
            v.addWidget(rb)
        self.rb_depth[ScanDepth.DETAILED].setChecked(True)

        v.addWidget(_section_label("API KEYS"))
        self.lbl_keys = QLabel()
        self.lbl_keys.setWordWrap(True)
        v.addWidget(self.lbl_keys)
        self.btn_keys = QPushButton("MANAGE API KEYS")
        self.btn_keys.clicked.connect(self._on_manage_keys)
        v.addWidget(self.btn_keys)

        v.addWidget(_section_label("PARALLEL WORKERS"))
        wk_row = QHBoxLayout()
        wk_row.setSpacing(6)
        self.sp_workers = QSpinBox()
        self.sp_workers.setRange(1, 32)
        self.sp_workers.setValue(1)
        self.sp_workers.setMinimumWidth(70)
        wk_row.addWidget(self.sp_workers)
        self.btn_auto_workers = QPushButton("AUTO")
        self.btn_auto_workers.setToolTip(
            "Set workers = number of usable API keys (capped at 16)."
        )
        self.btn_auto_workers.clicked.connect(self._on_auto_workers)
        wk_row.addWidget(self.btn_auto_workers)
        wk_row.addStretch(1)
        v.addLayout(wk_row)
        self.lbl_workers_hint = QLabel(
            "1 = sequential. Higher = run multiple inspections in parallel "
            "across keys. AUTO uses every usable key."
        )
        self.lbl_workers_hint.setWordWrap(True)
        self.lbl_workers_hint.setStyleSheet("color:#777777; font-size:11px;")
        v.addWidget(self.lbl_workers_hint)

        v.addWidget(_section_label("RUN"))

        self.btn_run = QPushButton("▶  RUN AI ANATOMY CHECK")
        self.btn_run.setMinimumHeight(44)
        self.btn_run.setStyleSheet(
            "QPushButton{background:#FF4D2E; color:#111111;"
            "border:2px solid #111111; font-weight:bold; letter-spacing:1px;}"
            "QPushButton:hover{background:#FF6A4F;}"
            "QPushButton:disabled{background:#C9C2B2; color:#8A8377;}"
        )
        self.btn_run.clicked.connect(self._on_run)
        v.addWidget(self.btn_run)

        self.btn_stop = QPushButton("STOP")
        self.btn_stop.clicked.connect(self._on_stop)
        self.btn_stop.setEnabled(False)
        v.addWidget(self.btn_stop)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        v.addWidget(self.progress)

        self.lbl_progress = QLabel("Idle.")
        self.lbl_progress.setStyleSheet("color:#555555;")
        v.addWidget(self.lbl_progress)

        v.addStretch(1)

        self._refresh_keys_label()
        return w

    def _build_centre_gallery(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(6)

        head = QHBoxLayout()
        head.addWidget(_section_label("QUEUE"))
        head.addStretch(1)
        self.btn_review = QPushButton("OPEN FULL REVIEW")
        self.btn_review.setEnabled(False)
        self.btn_review.clicked.connect(self._on_open_review)
        head.addWidget(self.btn_review)
        v.addLayout(head)

        self.lst_queue = QListWidget()
        self.lst_queue.setStyleSheet(
            "QListWidget{border:2px solid #111111; background:#FFFFFF;}"
            "QListWidget::item{padding:8px; border-bottom:1px solid #C9C2B2;}"
            "QListWidget::item:selected{background:#D6EE2C; color:#111111;}"
        )
        self.lst_queue.itemSelectionChanged.connect(self._on_queue_selection)
        self.lst_queue.itemDoubleClicked.connect(
            lambda _i: self._on_open_review()
        )
        v.addWidget(self.lst_queue, 1)
        return w

    def _build_right_preview(self) -> QWidget:
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        self.marker = MarkerView()
        self.report = ReportPanel()
        self.marker.region_clicked.connect(self.report.highlight)
        self.report.region_clicked.connect(self.marker.set_highlight)

        h.addWidget(self.marker, 3)
        h.addWidget(self.report, 2)
        return w

    # ------------------------------------------------------------------
    # External API
    # ------------------------------------------------------------------

    def set_files(self, files: List[Path]) -> None:
        """Replace the queue with `files`. Existing results are kept where
        the file path still matches."""
        self._files = list(files)
        existing = self._results
        self._results = {p.name: existing[p.name] for p in files
                         if p.name in existing}
        self._refresh_queue()

    def results(self) -> Dict[str, AnatomyResult]:
        """All AI results so far, keyed by file name."""
        return dict(self._results)

    # ------------------------------------------------------------------
    # Queue rendering
    # ------------------------------------------------------------------

    def _refresh_queue(self) -> None:
        self.lst_queue.clear()
        for p in self._files:
            res = self._results.get(p.name)
            item = QListWidgetItem(_queue_text(p, res))
            item.setData(Qt.ItemDataRole.UserRole, str(p))
            item.setSizeHint(item.sizeHint())
            self.lst_queue.addItem(item)
        self.btn_review.setEnabled(bool(self._files))

    def _row_for_file(self, file_name: str) -> int:
        for i in range(self.lst_queue.count()):
            item = self.lst_queue.item(i)
            p = Path(item.data(Qt.ItemDataRole.UserRole))
            if p.name == file_name:
                return i
        return -1

    def _update_row(self, file_name: str, status_text: str) -> None:
        i = self._row_for_file(file_name)
        if i < 0:
            return
        item = self.lst_queue.item(i)
        p = Path(item.data(Qt.ItemDataRole.UserRole))
        res = self._results.get(file_name)
        item.setText(_queue_text(p, res, override_status=status_text))

    def _on_queue_selection(self) -> None:
        items = self.lst_queue.selectedItems()
        if not items:
            self.marker.set_image(None)
            self.marker.set_regions([])
            self.report.set_result(None)
            return
        path = Path(items[0].data(Qt.ItemDataRole.UserRole))
        pix = QPixmap(str(path))
        self.marker.set_image(pix if not pix.isNull() else None)
        res = self._results.get(path.name)
        self.marker.set_regions(res.defect_regions if res else [])
        self.marker.set_highlight(None)
        self.report.set_result(res)

    # ------------------------------------------------------------------
    # Controls
    # ------------------------------------------------------------------

    def _refresh_keys_label(self) -> None:
        usable = self.km.usable_keys()
        total = self.km.count()
        if total == 0:
            self.lbl_keys.setText(
                "<b>No keys configured.</b> Add a Gemini, OpenAI, or Groq "
                "API key in Manage API Keys before running."
            )
            self.btn_run.setEnabled(False)
        else:
            self.lbl_keys.setText(
                f"{len(usable)} usable · {total} total"
            )
            self.btn_run.setEnabled(True)

    def _selected_depth(self) -> ScanDepth:
        for d, rb in self.rb_depth.items():
            if rb.isChecked():
                return d
        return ScanDepth.DETAILED

    def _on_manage_keys(self) -> None:
        dlg = KeySettingsDialog(self.km, self)
        dlg.exec()
        # KeyManager is mutated in-place + saved, regardless of dialog
        # acceptance — refresh the button state.
        self._refresh_keys_label()

    def _on_auto_workers(self) -> None:
        usable = max(1, len(self.km.usable_keys()))
        self.sp_workers.setValue(min(usable, 16))

    def _on_run(self) -> None:
        if self._worker is not None:
            return
        if not self._files:
            QMessageBox.information(
                self, "Nothing to scan",
                "Add some images in the Technical Quality tab first.",
            )
            return
        if not self.km.usable_keys():
            QMessageBox.warning(
                self, "No usable API key",
                "Add and enable at least one API key in Manage API Keys.",
            )
            return

        depth = self._selected_depth()
        self.progress.setRange(0, len(self._files))
        self.progress.setValue(0)
        self.lbl_progress.setText("Starting…")
        self.btn_run.setEnabled(False)
        self.btn_stop.setEnabled(True)

        self._worker = InspectionWorker(
            self.km, list(self._files), depth,
            max_workers=self.sp_workers.value(),
        )
        self._worker.image_started.connect(self._on_image_started)
        self._worker.image_progress.connect(self._on_image_progress)
        self._worker.image_done.connect(self._on_image_done)
        self._worker.log_line.connect(self.log_line)
        self._worker.finished_all.connect(self._on_finished)
        self._worker.start()

    def _on_stop(self) -> None:
        if self._worker is not None:
            self._worker.request_stop()
            self.lbl_progress.setText("Stopping…")
            self.btn_stop.setEnabled(False)

    def _on_image_started(self, file_name: str) -> None:
        self._update_row(file_name, "Preparing…")
        self.lbl_progress.setText(f"Inspecting {file_name}")

    def _on_image_progress(
        self, file_name: str, event: str, payload: dict,
    ) -> None:
        if event == "preparing":
            self._update_row(file_name, "Preparing image tiles…")
        elif event == "full":
            self._update_row(file_name, "Checking full image…")
        elif event == "tile":
            ti = payload.get("tile_index", 0)
            tot = payload.get("total_tiles", 0)
            self._update_row(file_name, f"Checking tile {ti}/{tot}…")
        elif event == "merging":
            self._update_row(file_name, "Merging results…")
        elif event == "key_switch":
            origin = payload.get("from", "")
            reason = payload.get("reason", "")
            self._update_row(
                file_name, f"Key switch ({origin} · {reason})",
            )

    def _on_image_done(self, file_name: str, result: AnatomyResult) -> None:
        self._results[file_name] = result
        i = self._row_for_file(file_name)
        if i >= 0:
            item = self.lst_queue.item(i)
            p = Path(item.data(Qt.ItemDataRole.UserRole))
            item.setText(_queue_text(p, result))
        # If the user is currently looking at this image, refresh preview.
        sel = self.lst_queue.selectedItems()
        if sel and Path(sel[0].data(Qt.ItemDataRole.UserRole)).name == file_name:
            self.marker.set_regions(result.defect_regions)
            self.marker.set_highlight(None)
            self.report.set_result(result)
        self.progress.setValue(self.progress.value() + 1)

    def _on_finished(self) -> None:
        self.btn_run.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.lbl_progress.setText("Complete.")
        self._worker = None
        self._refresh_keys_label()

    def _on_open_review(self) -> None:
        if not self._files:
            return
        items = []
        for p in self._files:
            res = self._results.get(p.name)
            if res is not None:
                items.append((p, res))
        if not items:
            QMessageBox.information(
                self, "No AI results yet",
                "Run the AI anatomy check first, then open the full review.",
            )
            return
        # Start at the currently-selected row if it has a result.
        start = 0
        sel = self.lst_queue.selectedItems()
        if sel:
            sel_name = Path(sel[0].data(Qt.ItemDataRole.UserRole)).name
            for i, (p, _) in enumerate(items):
                if p.name == sel_name:
                    start = i
                    break
        dlg = AIReviewDialog(items, start_index=start, parent=self)
        dlg.exec()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        "background:#111111; color:#F4F1EA; padding:4px 8px; "
        "letter-spacing:2px; font-weight:bold;"
    )
    lbl.setSizePolicy(
        QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed,
    )
    return lbl


def _queue_text(
    path: Path,
    result: Optional[AnatomyResult] = None,
    override_status: Optional[str] = None,
) -> str:
    if override_status:
        return f"{path.name}\n  {override_status}"
    if result is None:
        return f"{path.name}\n  (not inspected yet)"
    if result.status == AIStatus.ERROR:
        return f"{path.name}\n  ERROR — {result.error or 'unknown error'}"
    primary = result.primary_physical_issue or "no primary issue"
    return (
        f"{path.name}\n"
        f"  {result.status.value.upper()} · score {result.quality_score} · "
        f"{len(result.defect_regions)} marker(s) · "
        f"{result.provider_used or '—'} · {primary}"
    )
