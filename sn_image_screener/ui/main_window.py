"""Main window — assembles the brutalist layout."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt, QThread
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QMainWindow, QProgressBar, QSplitter, QStackedWidget,
    QStatusBar, QVBoxLayout, QWidget,
)

from .. import __app_name__, __subtitle__, __version__
from ..core.classifier import Status
from ..core.deleter import human_size, total_size, trash_files
from ..core.exporter import (
    BUCKET_ERROR,
    BUCKET_FAIL,
    BUCKET_PASS,
    BUCKET_REVIEW,
    export_csv,
    export_json,
    sort_results_into_buckets,
)
from ..core.scanner import collect_paths
from ..services.ai import KeyManager
from . import theme
from .ai import AIPanel
from .delete_dialog import DeleteConfirmDialog
from .command_bar import CommandBar
from .control_panel import ControlPanel
from .full_review import FullReviewDialog, FullReviewItem
from .inspector import Inspector
from .log_panel import LogPanel
from .nav_rail import NavRail, ai_anatomy_icon, technical_quality_icon
from .results_table import ResultsTable
from .technical_report_panel import TechnicalReportPanel
from .toast import Toaster
from .workers import ScanWorker

# Maps :class:`Status` to the badge string used by the Full Review
# toolbar. ``REJECT`` becomes ``FAIL`` so PASS / REVIEW / FAIL / ERROR
# stay consistent with the AI Inspector.
_TECH_BADGE = {
    Status.PASS:   "PASS",
    Status.REVIEW: "REVIEW",
    Status.REJECT: "FAIL",
    Status.ERROR:  "ERROR",
}


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(__app_name__)
        self.setMinimumSize(1180, 720)
        self.resize(1366, 820)

        # State
        self._folders: List[Path] = []
        self._files: List[Path] = []
        self._thread: Optional[QThread] = None
        self._worker: Optional[ScanWorker] = None
        self._counts = {"PASS": 0, "REVIEW": 0, "REJECT": 0, "ERROR": 0}

        # Apply stylesheet
        QApplication.instance().setStyleSheet(theme.QSS)

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)

        layout = QVBoxLayout(root)
        layout.setContentsMargins(10, 10, 10, 6)
        layout.setSpacing(8)

        # Top command bar -----------------------------------------------
        self.command_bar = CommandBar()
        self.command_bar.add_folder_clicked.connect(self.add_folder)
        self.command_bar.add_files_clicked.connect(self.add_files)
        self.command_bar.start_clicked.connect(self.start_scan)
        self.command_bar.stop_clicked.connect(self.stop_scan)
        self.command_bar.export_clicked.connect(self.export_results)
        self.command_bar.delete_clicked.connect(self.delete_rejected)
        layout.addWidget(self.command_bar)

        # ---- Build the Technical Quality tab body ---------------------
        self.h_split = QSplitter(Qt.Horizontal)
        self.h_split.setHandleWidth(2)
        self.h_split.setChildrenCollapsible(False)

        # Left — Add Folder / Add Files signals were removed from
        # ControlPanel because the same actions live in the always-
        # visible top command bar. Only Clear Sources and Start are
        # surfaced here now.
        self.control_panel = ControlPanel()
        self.control_panel.clear_sources_clicked.connect(self.clear_sources)
        self.control_panel.start_clicked.connect(self.start_scan)
        # The compact "No source added" footer surfaces its own mini
        # Add Folder / Add Files buttons; route them to the same slots
        # as the top command bar so behaviour is identical.
        self.control_panel.add_folder_clicked.connect(self.add_folder)
        self.control_panel.add_files_clicked.connect(self.add_files)
        self.h_split.addWidget(self.control_panel)

        # Center: results + bottom log via vertical splitter
        center_split = QSplitter(Qt.Vertical)
        center_split.setHandleWidth(2)
        center_split.setChildrenCollapsible(False)

        center_top = QWidget()
        ctl = QVBoxLayout(center_top)
        ctl.setContentsMargins(0, 0, 0, 0)
        ctl.setSpacing(8)

        self.summary_bar = self._build_summary_bar()
        ctl.addWidget(self.summary_bar)

        self.results = ResultsTable()
        self.results.selection_changed.connect(self._on_row_selected)
        # Double-clicking a result row opens the Full Review workspace
        # for the selected item.
        self.results.item_activated.connect(self._open_technical_full_review)
        # Quick actions inside the empty state of the results table:
        # 0 = Add Folder, 1 = Add Files (mirrors the top command bar).
        self.results.empty_action_clicked.connect(
            lambda i: (self.add_folder if i == 0 else self.add_files)()
        )
        ctl.addWidget(self.results, 1)

        center_split.addWidget(center_top)

        self.log_panel = LogPanel()
        center_split.addWidget(self.log_panel)
        center_split.setStretchFactor(0, 5)
        center_split.setStretchFactor(1, 1)

        self.h_split.addWidget(center_split)

        # Right
        self.inspector = Inspector()
        self.h_split.addWidget(self.inspector)

        self.h_split.setStretchFactor(0, 0)
        self.h_split.setStretchFactor(1, 5)
        self.h_split.setStretchFactor(2, 0)
        self.h_split.setSizes([330, 760, 360])

        # ---- Build the AI Anatomy Inspector tab -----------------------
        self.key_manager = KeyManager()
        self.ai_panel = AIPanel(self.key_manager)
        self.ai_panel.log_line.connect(self._on_ai_log)

        # ---- Mode pages (Technical Quality / AI Anatomy Inspector) ----
        # The two former tab bodies become pages of a QStackedWidget so
        # the new collapsible left rail can swap between them.
        self.mode_stack = QStackedWidget()
        self.mode_stack.addWidget(self.h_split)
        self.mode_stack.addWidget(self.ai_panel)

        # ---- Collapsible left navigation rail -------------------------
        # Short labels ("TECHNICAL", "AI INSPECTOR") render next to the
        # icon when the rail is expanded; the long-form name appears as
        # a tooltip on hover (and is also what users read when the rail
        # is collapsed).
        self.nav_rail = NavRail()
        self.nav_rail.add_mode(
            "TECHNICAL",
            technical_quality_icon(),
            tooltip="Technical Quality",
        )
        self.nav_rail.add_mode(
            "AI INSPECTOR",
            ai_anatomy_icon(),
            tooltip="AI Anatomy Inspector",
        )
        self.nav_rail.mode_changed.connect(self._on_mode_changed)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(8)
        body.addWidget(self.nav_rail)
        body.addWidget(self.mode_stack, 1)
        layout.addLayout(body, 1)

        # Status bar ----------------------------------------------------
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage(
            f"{__app_name__} v{__version__}  ·  {__subtitle__}  ·  "
            f"local · offline · originals never modified"
        )

        # Welcome log
        self.log_panel.info(f"{__app_name__} v{__version__} ready")
        self.log_panel.info("Add a folder or files, choose a preset, then Start Scan")

        # Initial empty-state wiring — quiet the Export / Delete buttons
        # and hide the inspector's metric grid until results exist.
        self._refresh_delete_button()

        # Toast notifications (top-right corner)
        self.toaster = Toaster(self)
        self.control_panel.cmb_preset.currentTextChanged.connect(
            lambda name: self.toaster.info("Preset", f"Switched to {name}")
        )

    # =====================================================================
    # Layout helpers
    # =====================================================================

    def _build_summary_bar(self) -> QFrame:
        """Counters strip + progress bar above the results table."""
        wrap = QFrame()
        wrap.setObjectName("brutal-card")
        outer = QVBoxLayout(wrap)
        outer.setContentsMargins(12, 8, 12, 8)
        outer.setSpacing(6)

        row = QHBoxLayout()
        row.setSpacing(10)

        self._counter_widgets = {}
        for status, color, fg in [
            ("TOTAL",  theme.INK,        theme.SURFACE),
            ("PASS",   theme.PASS_BG,    theme.PASS_FG),
            ("REVIEW", theme.REVIEW_BG,  theme.REVIEW_FG),
            ("REJECT", theme.REJECT_BG,  theme.REJECT_FG),
            ("ERROR",  theme.ERROR_BG,   theme.ERROR_FG),
        ]:
            cell = QFrame()
            cell.setStyleSheet(
                f"background:{color}; color:{fg};"
                f"border:2px solid {theme.INK};"
            )
            cl = QVBoxLayout(cell)
            cl.setContentsMargins(10, 6, 10, 6)
            cl.setSpacing(0)
            lbl_v = QLabel("0")
            f = lbl_v.font()
            f.setPointSize(18)
            f.setBold(True)
            lbl_v.setFont(f)
            lbl_v.setAlignment(Qt.AlignCenter)
            cl.addWidget(lbl_v)
            lbl_t = QLabel(status)
            lbl_t.setAlignment(Qt.AlignCenter)
            tf = lbl_t.font()
            tf.setBold(True)
            tf.setPointSize(9)
            tf.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.5)
            lbl_t.setFont(tf)
            cl.addWidget(lbl_t)
            self._counter_widgets[status] = lbl_v
            row.addWidget(cell, 1)

        outer.addLayout(row)

        prog_row = QHBoxLayout()
        prog_row.setSpacing(8)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("READY")
        prog_row.addWidget(self.progress, 1)
        outer.addLayout(prog_row)

        return wrap

    # =====================================================================
    # Source management
    # =====================================================================

    def add_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Select source folder")
        if not d:
            return
        p = Path(d).resolve()
        if p in self._folders:
            return
        self._folders.append(p)
        self.control_panel.update_source_summary(self._folders, self._files)
        self._refresh_source_state()
        self._sync_ai_files()
        self.log_panel.info(f"Folder added · {p}")
        self.toaster.ok("Folder added", p.name or str(p))

    def add_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select images",
            filter="Images (*.jpg *.jpeg *.png *.bmp *.tif *.tiff *.gif *.webp)",
        )
        if not files:
            return
        added = 0
        for f in files:
            p = Path(f).resolve()
            if p not in self._files:
                self._files.append(p)
                added += 1
        self.control_panel.update_source_summary(self._folders, self._files)
        self._refresh_source_state()
        self._sync_ai_files()
        self.log_panel.info(f"{added} file(s) added")
        if added:
            self.toaster.ok("Files added", f"{added} image(s) queued")

    def clear_sources(self) -> None:
        self._folders.clear()
        self._files.clear()
        self.control_panel.update_source_summary(self._folders, self._files)
        self._refresh_source_state()
        self._sync_ai_files()
        self.log_panel.info("Sources cleared")
        self.toaster.info("Sources cleared")

    def _sync_ai_files(self) -> None:
        """Push the current source list into the AI tab's queue."""
        try:
            paths = collect_paths(self._folders, self._files)
        except Exception:  # noqa: BLE001
            paths = []
        self.ai_panel.set_files(paths)

    def _on_mode_changed(self, index: int) -> None:
        """Adjust the command bar to match the active mode.

        Technical Quality (index 0) keeps Start / Export / Delete enabled;
        AI Anatomy Inspector (index 1) shows the same command bar but
        Start / Export / Delete are disabled because the AI mode has its
        own RUN button and uses Export Results from the Technical mode
        for now.
        """
        self.mode_stack.setCurrentIndex(index)
        is_technical = (index == 0)
        self.command_bar.set_can_start(
            is_technical and (bool(self._folders) or bool(self._files))
        )
        self.command_bar.set_scanning(False)
        # Push the latest file list into the AI mode whenever the user
        # switches over so the queue is always fresh.
        if not is_technical:
            self._sync_ai_files()

    def _on_ai_log(self, line: str) -> None:
        """Forward AI worker log lines into the activity log panel."""
        # Use info level — errors carry their own marker text.
        if "ERROR" in line.upper() or "FAILED" in line.upper():
            self.log_panel.err(f"AI · {line}")
        elif "switching" in line.lower():
            self.log_panel.warn(f"AI · {line}")
        else:
            self.log_panel.info(f"AI · {line}")

    def _refresh_source_state(self) -> None:
        """Mirror the disabled-when-empty state to the command bar START button."""
        has_source = bool(self._folders) or bool(self._files)
        self.command_bar.set_can_start(has_source)

    # =====================================================================
    # Scanning
    # =====================================================================

    def start_scan(self) -> None:
        if self._thread is not None:
            return  # already scanning

        paths = collect_paths(self._folders, self._files)
        if not paths:
            self.toaster.warn(
                "Nothing to scan",
                "Add a folder or files first",
            )
            return

        rules = self.control_panel.current_rules()

        # Reset visible state
        self.results.clear()
        self._counts = {"PASS": 0, "REVIEW": 0, "REJECT": 0, "ERROR": 0}
        self._update_counters(total=0)
        self.progress.setValue(0)
        self._refresh_delete_button()

        self.command_bar.set_scanning(True)
        self.command_bar.set_status("SCANNING")
        self.statusBar().showMessage(
            f"Scanning {len(paths)} file(s) — preset {self.control_panel.cmb_preset.currentText()}"
        )
        self.log_panel.info(f"Scan started · {len(paths)} file(s) · preset {self.control_panel.cmb_preset.currentText()}")
        self.toaster.info(
            "Scan started",
            f"{len(paths)} image(s) · preset {self.control_panel.cmb_preset.currentText()}",
        )

        # Spin up worker thread
        self._thread = QThread(self)
        self._worker = ScanWorker(paths, rules)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.started.connect(self._on_scan_started)
        self._worker.item_done.connect(self._on_item_done)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_scan_finished)
        self._worker.finished.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup_worker)
        self._thread.start()

    def stop_scan(self) -> None:
        if self._worker is None:
            return
        self._worker.stop()
        self.command_bar.set_status("STOPPED")
        self.log_panel.warn("Stop requested…")
        self.toaster.warn("Stop requested", "Finishing the current image…")

    # ----- worker signals -----

    def _on_scan_started(self, total: int) -> None:
        self.progress.setRange(0, max(1, total))
        self.progress.setFormat("0 / %m")
        self.progress.setValue(0)

    def _on_item_done(self, item) -> None:
        self.results.add_or_update(item)
        st = item.status.value
        if st in self._counts:
            self._counts[st] += 1
        total = sum(self._counts.values())
        self._update_counters(total)
        self._refresh_delete_button()

        if item.error:
            self.log_panel.err(f"{item.path.name} · {item.error}")
        else:
            tag = item.status.value
            self.log_panel.info(
                f"{tag:<6}  {item.path.name}  ·  score {item.score}"
            )

    def _on_progress(self, i: int, n: int) -> None:
        self.progress.setMaximum(max(1, n))
        self.progress.setValue(i)
        self.progress.setFormat(f"{i} / {n}")

    def _on_scan_finished(self, stopped: bool) -> None:
        if stopped:
            self.command_bar.set_status("STOPPED")
            self.log_panel.warn("Scan stopped.")
            self.statusBar().showMessage("Scan stopped.")
            self.toaster.warn(
                "Scan stopped",
                f"PASS {self._counts['PASS']}  ·  REVIEW {self._counts['REVIEW']}  ·  REJECT {self._counts['REJECT']}",
            )
        else:
            self.command_bar.set_status("COMPLETED")
            self.log_panel.ok(
                f"Scan complete · "
                f"PASS {self._counts['PASS']}  "
                f"REVIEW {self._counts['REVIEW']}  "
                f"REJECT {self._counts['REJECT']}  "
                f"ERROR {self._counts['ERROR']}"
            )
            self.statusBar().showMessage("Scan complete.")
            self.toaster.ok(
                "Scan complete",
                f"PASS {self._counts['PASS']}  ·  REVIEW {self._counts['REVIEW']}  ·  REJECT {self._counts['REJECT']}",
            )
        self.command_bar.set_scanning(False)
        self._refresh_delete_button()

    def _refresh_delete_button(self) -> None:
        """Enable the Delete button only when at least one REJECT row exists."""
        items = self.results.items()
        n_reject = sum(1 for it in items if it.status == Status.REJECT)
        self.command_bar.set_can_delete(n_reject > 0, n_reject)
        self.command_bar.set_can_export(len(items) > 0, len(items))
        # The right-hand inspector should only show its detailed metric
        # grid once the user has *something* to look at.
        self.inspector.set_metrics_visible(len(items) > 0)

    def _cleanup_worker(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None
        if self._thread is not None:
            self._thread.deleteLater()
            self._thread = None

    # =====================================================================
    # Selection / inspector
    # =====================================================================

    def _on_row_selected(self, item) -> None:
        self.inspector.show_item(item)

    def _open_technical_full_review(self, _scan_item) -> None:
        """Open the Full Review dialog from a results-table double-click."""
        scan_items = self.results.items()
        if not scan_items:
            return
        review_items: List[FullReviewItem] = []
        for it in scan_items:
            review_items.append(
                FullReviewItem(
                    path=it.path,
                    status=_TECH_BADGE.get(it.status, "ERROR"),
                    regions=[],
                    payload=it,
                )
            )
        start = self.results.selected_index() or 0

        report = TechnicalReportPanel()

        def _update_report(item: Optional[FullReviewItem]) -> None:
            report.show_item(
                item.payload if item is not None else None,
            )

        dlg = FullReviewDialog(
            review_items,
            report_widget=report,
            on_item_changed=_update_report,
            start_index=start,
            title="Technical Quality — Full Review",
            parent=self,
        )
        dlg.exec()

    def _update_counters(self, total: int) -> None:
        self._counter_widgets["TOTAL"].setText(str(total))
        for k in ("PASS", "REVIEW", "REJECT", "ERROR"):
            self._counter_widgets[k].setText(str(self._counts[k]))

    # =====================================================================
    # Export
    # =====================================================================

    def export_results(self) -> None:
        items = self.results.items()
        if not items:
            self.toaster.warn("Nothing to export", "Run a scan first")
            return

        out = self.control_panel.output_dir()
        if out is None:
            d = QFileDialog.getExistingDirectory(self, "Choose export folder")
            if not d:
                return
            out = Path(d)
            self.control_panel.ed_output.setText(str(out))

        out.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")

        try:
            # If the user has run the AI Anatomy Inspector, fold those
            # results into the report (CSV gets extra columns, JSON gets
            # a nested ``ai`` block per row including defect_regions).
            ai_results = self.ai_panel.results() if hasattr(self, "ai_panel") else {}

            # CSV / JSON reports
            if self.control_panel.chk_export_csv.isChecked():
                csv_path = out / f"report_{ts}.csv"
                export_csv(items, csv_path, ai_results=ai_results or None)
                self.log_panel.ok(f"CSV report → {csv_path}")
            if self.control_panel.chk_export_json.isChecked():
                json_path = out / f"report_{ts}.json"
                export_json(items, json_path, ai_results=ai_results or None)
                self.log_panel.ok(f"JSON report → {json_path}")

            # Auto-sort: MOVE every scanned file into pass / review /
            # fail / error subfolders based on its verdict. The AI
            # Inspector verdict (if present) takes precedence over the
            # local Tool A verdict.
            buckets = sort_results_into_buckets(
                items, out, ai_results=ai_results or None, move=True,
            )
            n_pass = len(buckets[BUCKET_PASS])
            n_review = len(buckets[BUCKET_REVIEW])
            n_fail = len(buckets[BUCKET_FAIL])
            n_error = len(buckets[BUCKET_ERROR])
            total_moved = n_pass + n_review + n_fail + n_error
            if total_moved:
                self.log_panel.ok(
                    f"Sorted {total_moved} file(s) → {out}  "
                    f"(pass: {n_pass}, review: {n_review}, "
                    f"fail: {n_fail}, error: {n_error})"
                )

            self.statusBar().showMessage(f"Export complete · {out}")
            self.toaster.ok(
                "Export complete",
                f"{out}\npass {n_pass} · review {n_review} · "
                f"fail {n_fail} · error {n_error}",
            )
        except Exception as exc:  # noqa: BLE001
            self.log_panel.err(f"Export failed · {exc}")
            self.toaster.err("Export failed", str(exc))
            return

    # =====================================================================
    # Delete
    # =====================================================================

    def delete_rejected(self) -> None:
        """Show confirm dialog and trash REJECT (and optionally REVIEW) files."""
        items = self.results.items()
        rej = [it for it in items if it.status == Status.REJECT]
        rev = [it for it in items if it.status == Status.REVIEW]
        if not rej and not rev:
            self.toaster.warn("Nothing to delete", "Run a scan first")
            return

        dlg = DeleteConfirmDialog(
            self,
            n_reject=len(rej),
            size_reject=total_size(it.path for it in rej),
            n_review=len(rev),
            size_review=total_size(it.path for it in rev),
            permanent_default=self.control_panel.chk_permanent_delete.isChecked(),
        )
        if dlg.exec() != QDialog.Accepted:
            return

        targets: List[Path] = []
        if dlg.include_reject:
            targets += [it.path for it in rej]
        if dlg.include_review:
            targets += [it.path for it in rev]
        if not targets:
            return

        permanent = dlg.permanent
        # Snapshot sizes before deletion so we can show a useful toast.
        size_before = total_size(targets)
        deleted, errors = trash_files(targets, permanent=permanent)

        if deleted:
            self.results.remove_paths(deleted)
            for it in items:
                if it.path in deleted:
                    if it.status == Status.REJECT:
                        self._counts["REJECT"] = max(0, self._counts["REJECT"] - 1)
                    elif it.status == Status.REVIEW:
                        self._counts["REVIEW"] = max(0, self._counts["REVIEW"] - 1)
            self._update_counters(sum(self._counts.values()))

        action = "Permanently deleted" if permanent else "Moved to Recycle Bin"
        if deleted and not errors:
            self.toaster.ok(
                f"{action}",
                f"{len(deleted)} file(s) · {human_size(size_before)}",
            )
            self.log_panel.ok(f"{action} · {len(deleted)} file(s)")
        elif deleted and errors:
            self.toaster.warn(
                f"{action} (partial)",
                f"{len(deleted)} ok, {len(errors)} error(s)",
            )
            for p, msg in errors:
                self.log_panel.err(f"Delete failed: {p.name} · {msg}")
        else:
            self.toaster.err(
                "Delete failed",
                f"{len(errors)} error(s) — see activity log",
            )
            for p, msg in errors:
                self.log_panel.err(f"Delete failed: {p.name} · {msg}")

        self._refresh_delete_button()

    # =====================================================================
    # Lifecycle
    # =====================================================================

    def closeEvent(self, event):  # noqa: N802
        if self._worker is not None:
            self._worker.stop()
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(2000)
        super().closeEvent(event)
