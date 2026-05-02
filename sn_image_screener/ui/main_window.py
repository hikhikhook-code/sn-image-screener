"""Main window — assembles the brutalist layout."""

from __future__ import annotations

import platform
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt, QThread
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QMainWindow,
    QMessageBox, QProgressBar, QSizePolicy, QSplitter, QStatusBar,
    QVBoxLayout, QWidget,
)

from .. import __app_name__, __subtitle__, __version__
from ..core.classifier import Status
from ..core.exporter import copy_by_status, export_csv, export_json
from ..core.scanner import collect_paths
from . import theme
from .command_bar import CommandBar
from .control_panel import ControlPanel
from .inspector import Inspector
from .log_panel import LogPanel
from .results_table import ResultsTable
from .toast import Toaster
from .widgets import HardDivider, label
from .workers import ScanWorker


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{__app_name__}  ·  {__subtitle__}")
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
        layout.addWidget(self.command_bar)

        # Body splitter --------------------------------------------------
        self.h_split = QSplitter(Qt.Horizontal)
        self.h_split.setHandleWidth(2)
        self.h_split.setChildrenCollapsible(False)

        # Left ---------------------------------------------------------
        self.control_panel = ControlPanel()
        self.control_panel.add_folder_clicked.connect(self.add_folder)
        self.control_panel.add_files_clicked.connect(self.add_files)
        self.control_panel.clear_sources_clicked.connect(self.clear_sources)
        self.control_panel.start_clicked.connect(self.start_scan)
        self.h_split.addWidget(self.control_panel)

        # Center: results + bottom log via vertical splitter -----------
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
        ctl.addWidget(self.results, 1)

        center_split.addWidget(center_top)

        self.log_panel = LogPanel()
        center_split.addWidget(self.log_panel)
        center_split.setStretchFactor(0, 5)
        center_split.setStretchFactor(1, 1)

        self.h_split.addWidget(center_split)

        # Right --------------------------------------------------------
        self.inspector = Inspector()
        self.h_split.addWidget(self.inspector)

        self.h_split.setStretchFactor(0, 0)
        self.h_split.setStretchFactor(1, 5)
        self.h_split.setStretchFactor(2, 0)
        self.h_split.setSizes([330, 760, 360])

        layout.addWidget(self.h_split, 1)

        # Status bar ----------------------------------------------------
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage(
            f"{__app_name__} v{__version__}  ·  {__subtitle__}  ·  "
            f"local · offline · originals never modified"
        )

        # Welcome log
        self.log_panel.info(f"{__app_name__} v{__version__} ready")
        self.log_panel.info("Add a folder or files, choose a preset, then Start Scan")

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
        self.log_panel.info(f"{added} file(s) added")
        if added:
            self.toaster.ok("Files added", f"{added} image(s) queued")

    def clear_sources(self) -> None:
        self._folders.clear()
        self._files.clear()
        self.control_panel.update_source_summary(self._folders, self._files)
        self._refresh_source_state()
        self.log_panel.info("Sources cleared")
        self.toaster.info("Sources cleared")

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
            # CSV / JSON reports
            if self.control_panel.chk_export_csv.isChecked():
                csv_path = out / f"report_{ts}.csv"
                export_csv(items, csv_path)
                self.log_panel.ok(f"CSV report → {csv_path}")
            if self.control_panel.chk_export_json.isChecked():
                json_path = out / f"report_{ts}.json"
                export_json(items, json_path)
                self.log_panel.ok(f"JSON report → {json_path}")

            # Copy good files
            statuses_to_copy = []
            if self.control_panel.chk_copy_pass.isChecked():
                statuses_to_copy.append(Status.PASS)
            if self.control_panel.chk_copy_review.isChecked():
                statuses_to_copy.append(Status.REVIEW)
            if statuses_to_copy:
                target = out / "selected"
                written = copy_by_status(items, target, statuses_to_copy)
                self.log_panel.ok(f"Copied {len(written)} file(s) → {target}")

            self.statusBar().showMessage(f"Export complete · {out}")
            self.toaster.ok("Export complete", str(out))
        except Exception as exc:  # noqa: BLE001
            self.log_panel.err(f"Export failed · {exc}")
            self.toaster.err("Export failed", str(exc))
            return

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
