"""Center results table — the visual heart of the app."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPalette, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QFrame, QHBoxLayout, QHeaderView, QLabel, QSizePolicy,
    QStackedLayout, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from . import theme
from .widgets import EmptyState, StatusTag
from ..core.classifier import Status
from ..core.scanner import ScanItem


COLUMNS = [
    ("Thumb",   72),
    ("File",    280),
    ("Status",  100),
    ("Score",   80),
    ("Issues",  280),
    ("Size",    90),
    ("Dim",     90),
]


class _ScoreLabel(QLabel):
    """Draws a chunky 0..100 quality score with a status-coloured bar."""

    def __init__(self, score: int, status: Status, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._score = max(0, min(100, int(score)))
        self._status = status
        self.setMinimumSize(60, 28)
        self.setAttribute(Qt.WA_TranslucentBackground)

    def paintEvent(self, event):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)
        rect = self.rect().adjusted(2, 4, -2, -4)

        # Background frame
        p.setPen(QPen(QColor(theme.INK), 2))
        p.setBrush(QColor(theme.SURFACE))
        p.drawRect(rect)

        # Fill bar
        if self._status is Status.PASS:
            fill = QColor(theme.PASS_BG)
        elif self._status is Status.REVIEW:
            fill = QColor(theme.REVIEW_BG)
        elif self._status is Status.REJECT:
            fill = QColor(theme.REJECT_BG)
        else:
            fill = QColor(theme.YELLOW)
        bar = rect.adjusted(2, 2, -2, -2)
        bar.setWidth(int(bar.width() * (self._score / 100.0)))
        p.setBrush(fill)
        p.setPen(Qt.NoPen)
        p.drawRect(bar)

        # Number on top
        p.setPen(QColor(theme.INK))
        f = self.font()
        f.setPointSize(11)
        f.setBold(True)
        p.setFont(f)
        p.drawText(rect, Qt.AlignCenter, f"{self._score}")
        p.end()


def _make_thumb_pixmap(path: Path, size: int = 60) -> QPixmap:
    pm = QPixmap(str(path))
    if pm.isNull():
        pm2 = QPixmap(size, size)
        pm2.fill(QColor(theme.SURFACE_ALT))
        return pm2
    return pm.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)


def _truncate_issues(item: ScanItem, max_chars: int = 80) -> str:
    if item.error:
        return f"⚠ {item.error}"
    if not item.verdict:
        return ""
    parts = [i.code for i in item.verdict.issues]
    if not parts:
        return "—"
    seen = []
    for p in parts:
        if p not in seen:
            seen.append(p)
    text = "  ".join(seen)
    if len(text) > max_chars:
        text = text[: max_chars - 1] + "…"
    return text


class ResultsTable(QFrame):
    """A QTableWidget wrapped in a brutalist card."""

    selection_changed = Signal(object)  # ScanItem | None
    empty_action_clicked = Signal(int)  # 0 = Add Folder, 1 = Add Files
    item_activated = Signal(object)     # ScanItem — emitted on row double-click

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("brutal-card")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(2, 2, 2, 2)
        outer.setSpacing(0)

        # The table and the empty-state placeholder share one slot via
        # a stacked layout. ``_refresh_empty_state`` flips between them
        # based on row count.
        host = QFrame()
        host.setStyleSheet("background:transparent;")
        self._stack = QStackedLayout(host)
        self._stack.setStackingMode(QStackedLayout.StackingMode.StackOne)

        self.table = QTableWidget()
        self.table.setColumnCount(len(COLUMNS))
        self.table.setHorizontalHeaderLabels([c[0] for c in COLUMNS])
        for i, (_, w) in enumerate(COLUMNS):
            self.table.setColumnWidth(i, w)

        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(64)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)

        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setIconSize(QSize(56, 56))
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        # Row double-click → open the Full Review dialog. Forward the
        # ScanItem upward so MainWindow owns the dialog construction.
        self.table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        self._stack.addWidget(self.table)

        self._empty = EmptyState(
            title="NO RESULTS YET",
            body="Add images, choose a preset, then start scan.",
        )
        # Quick actions: forward the EmptyState clicks so MainWindow
        # can route them to its existing ``add_folder`` / ``add_files``
        # slots.
        self._empty.set_actions(["Add Folder", "Add Files"])
        self._empty.action_clicked.connect(self.empty_action_clicked.emit)
        self._stack.addWidget(self._empty)

        outer.addWidget(host)

        # row index -> ScanItem
        self._items: Dict[int, ScanItem] = {}
        self._refresh_empty_state()

    # ----------------------------------------------------------------- API

    def clear(self) -> None:
        self.table.setRowCount(0)
        self._items.clear()
        self._refresh_empty_state()

    def add_or_update(self, item: ScanItem) -> None:
        """Append a row for the new item. (No update path needed yet — each
        scan starts from a cleared table.)"""
        row = self.table.rowCount()
        self.table.insertRow(row)
        self._items[row] = item
        self._refresh_empty_state()

        # Thumbnail ----------------------------------------------------
        thumb_lbl = QLabel()
        thumb_lbl.setAlignment(Qt.AlignCenter)
        pm = _make_thumb_pixmap(item.path, 56)
        thumb_lbl.setPixmap(pm)
        self.table.setCellWidget(row, 0, thumb_lbl)

        # Filename -----------------------------------------------------
        name_item = QTableWidgetItem(item.path.name)
        name_item.setToolTip(str(item.path))
        f = name_item.font()
        f.setBold(True)
        name_item.setFont(f)
        self.table.setItem(row, 1, name_item)

        # Status -------------------------------------------------------
        tag = StatusTag(item.status.value)
        tag_wrap = QWidget()
        wl = QHBoxLayout(tag_wrap)
        wl.setContentsMargins(6, 6, 6, 6)
        wl.addWidget(tag)
        wl.addStretch(1)
        self.table.setCellWidget(row, 2, tag_wrap)

        # Score --------------------------------------------------------
        score_lbl = _ScoreLabel(item.score, item.status)
        score_wrap = QWidget()
        sl = QHBoxLayout(score_wrap)
        sl.setContentsMargins(6, 8, 6, 8)
        sl.addWidget(score_lbl)
        self.table.setCellWidget(row, 3, score_wrap)

        # Issues -------------------------------------------------------
        issues_item = QTableWidgetItem(_truncate_issues(item))
        if item.error:
            issues_item.setForeground(QColor(theme.REJECT_BG))
        self.table.setItem(row, 4, issues_item)

        # Size ---------------------------------------------------------
        m = item.metrics
        size_text = f"{m.file_kb:,.0f} KB" if m else "—"
        size_item = QTableWidgetItem(size_text)
        size_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.table.setItem(row, 5, size_item)

        # Dim ---------------------------------------------------------
        dim_text = f"{m.width}×{m.height}" if m else "—"
        dim_item = QTableWidgetItem(dim_text)
        dim_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.table.setItem(row, 6, dim_item)

    def items(self) -> List[ScanItem]:
        return [self._items[r] for r in sorted(self._items)]

    def remove_paths(self, paths) -> int:
        """Remove rows whose item.path is in `paths`. Returns count removed."""
        targets = {Path(p).resolve() for p in paths}
        rows_to_remove = sorted(
            (r for r, it in self._items.items()
             if it.path.resolve() in targets),
            reverse=True,
        )
        for r in rows_to_remove:
            self.table.removeRow(r)
        # Rebuild the index because row numbers shifted.
        new_items: Dict[int, ScanItem] = {}
        new_row = 0
        for r in sorted(self._items):
            if r in rows_to_remove:
                continue
            new_items[new_row] = self._items[r]
            new_row += 1
        self._items = new_items
        self._refresh_empty_state()
        return len(rows_to_remove)

    def _refresh_empty_state(self) -> None:
        self._stack.setCurrentIndex(0 if self.table.rowCount() else 1)

    def selected_item(self) -> Optional[ScanItem]:
        rows = {idx.row() for idx in self.table.selectedIndexes()}
        if not rows:
            return None
        row = sorted(rows)[0]
        return self._items.get(row)

    def selected_index(self) -> Optional[int]:
        rows = {idx.row() for idx in self.table.selectedIndexes()}
        if not rows:
            return None
        return sorted(rows)[0]

    # ----------------------------------------------------------- private

    def _on_selection_changed(self) -> None:
        self.selection_changed.emit(self.selected_item())

    def _on_cell_double_clicked(self, row: int, _col: int) -> None:
        item = self._items.get(row)
        if item is not None:
            self.item_activated.emit(item)
