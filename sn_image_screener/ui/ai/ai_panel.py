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
    QButtonGroup, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QMessageBox, QProgressBar, QPushButton, QRadioButton, QScrollArea,
    QSizePolicy, QSpinBox, QSplitter, QVBoxLayout, QWidget,
)

from ...services.ai import KeyManager
from ...services.ai.types import (
    AIStatus, AnatomyResult, ScanDepth,
)
from ..widgets import CollapsibleGroup, EmptyState
from .inspection_worker import InspectionWorker
from .key_settings_dialog import KeySettingsDialog
from .marker_view import MarkerView
from .report_panel import ReportPanel
from .review_dialog import AIReviewDialog


_DEPTH_LABEL = {
    ScanDepth.FAST: "FAST · 1 inspection",
    ScanDepth.DETAILED: "DETAILED · 10 inspections (default)",
    ScanDepth.ULTRA: "ULTRA · 17 inspections",
}

_DEPTH_HELP = {
    ScanDepth.FAST: "Whole image only — fastest, less precise.",
    ScanDepth.DETAILED: "3 × 3 tiles + whole image — recommended.",
    ScanDepth.ULTRA: "4 × 4 tiles + whole image — most thorough.",
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
        self._update_run_state()

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
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 4)   # preview gets the lion's share
        splitter.setSizes([340, 320, 840])
        root.addWidget(splitter)

    def _build_left_controls(self) -> QWidget:
        # The control list is taller than typical app windows, so wrap
        # it in a scroll area to guarantee every section stays reachable
        # on small screens.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # Bumped from 280 → 320 so headings, depth labels, and the
        # inline run-disabled reason no longer clip on the right edge.
        scroll.setMinimumWidth(320)
        scroll.setMaximumWidth(380)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(14, 14, 14, 14)
        v.setSpacing(10)

        # The rail already shows "AI INSPECTOR" — keep this header
        # short and add a single-line subtitle so this column is not
        # crowded.
        header = QLabel("AI ANATOMY INSPECTOR")
        f = header.font()
        f.setBold(True)
        f.setPointSize(f.pointSize() + 1)
        header.setFont(f)
        header.setStyleSheet("letter-spacing:2px;")
        v.addWidget(header)

        sub = QLabel(
            "Vision-model defect check · anatomy, hands, AI artifacts."
        )
        sub.setWordWrap(True)
        sub.setStyleSheet("color:#555555; font-size:11px;")
        v.addWidget(sub)

        # The "Add Folder / Add Files / Clear Sources" buttons used to
        # be mirrored here — they have been moved to the always-visible
        # top command bar so the AI panel is no longer cluttered with
        # duplicates. We still surface a tiny status line so the user
        # knows whether the queue is empty.
        self.lbl_source_count = QLabel("— no sources added —")
        self.lbl_source_count.setStyleSheet(
            "color:#777777; font-size:11px;"
        )
        self.lbl_source_count.setWordWrap(True)
        v.addWidget(self.lbl_source_count)

        # ── SETUP ────────────────────────────────────────────────────
        # Source hint + scan depth — everything the user has to decide
        # before pressing Run.
        grp_setup = CollapsibleGroup("Setup", expanded=True)
        v.addWidget(grp_setup)

        depth_lbl = QLabel("Scan depth")
        depth_lbl.setStyleSheet("font-weight:700; letter-spacing:1px;")
        grp_setup.add(depth_lbl)
        self.rb_depth: Dict[ScanDepth, QRadioButton] = {}
        depth_group = QButtonGroup(self)
        for depth in (ScanDepth.FAST, ScanDepth.DETAILED, ScanDepth.ULTRA):
            rb = QRadioButton(_DEPTH_LABEL[depth])
            rb.setStyleSheet("padding:2px 0;")
            rb.setToolTip(_DEPTH_HELP[depth])
            self.rb_depth[depth] = rb
            depth_group.addButton(rb)
            grp_setup.add(rb)
        self.rb_depth[ScanDepth.DETAILED].setChecked(True)

        # ── EXECUTION ────────────────────────────────────────────────
        # Run / Stop / progress + the inline run-disabled reason.
        grp_exec = CollapsibleGroup("Execution", expanded=True)
        v.addWidget(grp_exec)

        self.btn_run = QPushButton("\u25B6  RUN AI ANATOMY CHECK")
        self.btn_run.setMinimumHeight(44)
        # Run uses the brutalist *lime* primary now — orange is reserved
        # for warnings / reject badges so it doesn't read as an error.
        self.btn_run.setStyleSheet(
            "QPushButton{background:#D6EE2C; color:#111111;"
            "border:2px solid #111111; font-weight:bold; letter-spacing:1px;}"
            "QPushButton:hover{background:#E4F95B;}"
            "QPushButton:disabled{background:#C9C2B2; color:#8A8377;}"
        )
        self.btn_run.clicked.connect(self._on_run)
        grp_exec.add(self.btn_run)

        # Inline reason that explains *why* RUN is disabled. We keep a
        # separate label (not just a tooltip) so the message is always
        # visible without requiring hover. Re-using the alert style.
        self.lbl_run_reason = QLabel("")
        self.lbl_run_reason.setObjectName("run-reason")
        self.lbl_run_reason.setWordWrap(True)
        self.lbl_run_reason.setStyleSheet(
            "color:#B23A1F; font-size:11px; font-weight:700;"
            "padding:4px 6px; border:2px solid #B23A1F;"
            "background:#FFE2D9;"
        )
        self.lbl_run_reason.hide()
        grp_exec.add(self.lbl_run_reason)

        self.btn_stop = QPushButton("STOP")
        self.btn_stop.clicked.connect(self._on_stop)
        self.btn_stop.setEnabled(False)
        grp_exec.add(self.btn_stop)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        grp_exec.add(self.progress)

        self.lbl_progress = QLabel("Idle.")
        self.lbl_progress.setStyleSheet("color:#555555;")
        grp_exec.add(self.lbl_progress)

        # ── ADVANCED ─────────────────────────────────────────────────
        # API keys + parallel workers. Expanded by default per UX
        # request — both controls remain visible — but kept inside a
        # collapsible group so users on small windows can fold them
        # away and the column doesn't feel crowded.
        grp_adv = CollapsibleGroup("Advanced", expanded=True)
        v.addWidget(grp_adv)

        keys_lbl = QLabel("API keys")
        keys_lbl.setStyleSheet("font-weight:700; letter-spacing:1px;")
        grp_adv.add(keys_lbl)
        self.lbl_keys = QLabel()
        self.lbl_keys.setWordWrap(True)
        grp_adv.add(self.lbl_keys)
        self.btn_keys = QPushButton("MANAGE API KEYS")
        self.btn_keys.clicked.connect(self._on_manage_keys)
        grp_adv.add(self.btn_keys)

        workers_lbl = QLabel("Parallel workers")
        workers_lbl.setStyleSheet(
            "font-weight:700; letter-spacing:1px; padding-top:6px;"
        )
        grp_adv.add(workers_lbl)
        wk_row = QHBoxLayout()
        wk_row.setSpacing(6)
        self.sp_workers = QSpinBox()
        self.sp_workers.setRange(1, 32)
        self.sp_workers.setValue(1)
        self.sp_workers.setMinimumWidth(60)
        self.sp_workers.setToolTip(
            "Number of inspection requests to run in parallel."
        )
        wk_row.addWidget(self.sp_workers)
        self.btn_auto_workers = QPushButton("AUTO")
        self.btn_auto_workers.setToolTip(
            "Set workers = number of usable API keys (capped at 16)."
        )
        self.btn_auto_workers.clicked.connect(self._on_auto_workers)
        wk_row.addWidget(self.btn_auto_workers)
        wk_row.addStretch(1)
        grp_adv.add_layout(wk_row)

        v.addStretch(1)

        self._refresh_keys_label()
        scroll.setWidget(w)
        return scroll

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

        # Stack the queue list and an empty-state placeholder in the
        # same slot — toggled by ``_refresh_queue``. The placeholder
        # gives users a clear next step when no images are loaded.
        from PySide6.QtWidgets import QStackedLayout

        host = QFrame()
        host.setStyleSheet("background:transparent;")
        stack = QStackedLayout(host)
        stack.setStackingMode(QStackedLayout.StackingMode.StackOne)

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
        stack.addWidget(self.lst_queue)

        self._queue_empty = EmptyState(
            title="QUEUE EMPTY",
            body=(
                "Use Add Folder or Add Files in the top bar to queue up "
                "images for the AI anatomy check."
            ),
        )
        stack.addWidget(self._queue_empty)
        self._queue_stack = stack

        v.addWidget(host, 1)
        return w

    def _build_right_preview(self) -> QWidget:
        """Marker on top (landscape), compact report below.

        Stacking the marker and report vertically lets the marker view
        use the full panel width — natural for landscape photos and
        wide rendered scenes.
        """
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        self.marker = MarkerView()
        self.report = ReportPanel()
        self.marker.region_clicked.connect(self.report.highlight)
        self.report.region_clicked.connect(self.marker.set_highlight)

        # Inner splitter so the user can drag the divider if they want
        # more report or more image.
        inner = QSplitter(Qt.Orientation.Vertical)
        inner.addWidget(self.marker)
        inner.addWidget(self.report)
        inner.setStretchFactor(0, 5)   # image dominates
        inner.setStretchFactor(1, 2)
        inner.setSizes([520, 240])
        v.addWidget(inner)
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
        n = len(self._files)
        if n == 0:
            self.lbl_source_count.setText(
                "— no images yet · add via the top bar —"
            )
        else:
            self.lbl_source_count.setText(f"{n} image(s) ready")
        self._update_run_state()

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
        # Toggle the empty-state placeholder.
        self._queue_stack.setCurrentIndex(0 if self._files else 1)

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
                "key in Manage API Keys."
            )
        else:
            self.lbl_keys.setText(
                f"{len(usable)} usable · {total} total"
            )
        self._update_run_state()

    def _update_run_state(self) -> None:
        """Drive the Run button's enabled state + show *why* it is off.

        The button is disabled until both preconditions are met:
        images in the queue **and** at least one usable API key. The
        inline ``lbl_run_reason`` label below the button explains the
        first missing precondition in plain English so the user does
        not have to guess.
        """
        # If a worker is mid-flight the parent already manages enablement.
        if self._worker is not None:
            return

        reasons = []
        if not self._files:
            reasons.append(
                "Add images via the top bar (Add Folder / Add Files)."
            )
        if not self.km.usable_keys():
            reasons.append(
                "Add at least one API key (Manage API Keys)."
            )

        can_run = not reasons
        self.btn_run.setEnabled(can_run)
        if can_run:
            self.btn_run.setToolTip("Run AI Anatomy Inspector on the queue")
            self.lbl_run_reason.hide()
            self.lbl_run_reason.setText("")
        else:
            joined = "\n".join(f"• {r}" for r in reasons)
            self.btn_run.setToolTip(joined)
            self.lbl_run_reason.setText(joined)
            self.lbl_run_reason.show()

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
        self.btn_stop.setEnabled(False)
        self.lbl_progress.setText("Complete.")
        self._worker = None
        # Re-evaluate Run state — `_refresh_keys_label` calls
        # `_update_run_state` which restores both the enabled flag and
        # the inline reason if any precondition is now missing.
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
