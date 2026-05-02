"""Full-screen review dialog: image left, report right.

Top bar shows the file name, image index (e.g. ``3 / 18``), show/hide
markers toggle, zoom in / zoom out, and a close button. Previous /
next arrow keys (or buttons) navigate through the queue.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPushButton, QSplitter,
    QVBoxLayout, QWidget,
)

from ...services.ai.types import AnatomyResult
from .marker_view import MarkerView
from .report_panel import ReportPanel


class AIReviewDialog(QDialog):
    """Image-left / report-right review window."""

    def __init__(
        self,
        items: List[tuple[Path, AnatomyResult]],
        start_index: int = 0,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("AI Anatomy — Review")
        self.resize(1280, 760)
        self._items = list(items)
        self._index = max(0, min(start_index, len(items) - 1)) if items else 0

        # ---- top bar ----------------------------------------------------
        self.lbl_title = QLabel("")
        self.lbl_title.setStyleSheet("font-weight:bold; font-size:14px;")
        self.lbl_index = QLabel("")
        self.lbl_index.setStyleSheet("color:#555555;")

        self.btn_prev = QPushButton("◀ PREV")
        self.btn_next = QPushButton("NEXT ▶")
        self.btn_markers = QPushButton("HIDE MARKERS")
        self.btn_zoom_out = QPushButton("−")
        self.btn_zoom_in = QPushButton("+")
        self.btn_zoom_reset = QPushButton("FIT")
        self.btn_close = QPushButton("CLOSE")

        for b in (self.btn_prev, self.btn_next, self.btn_markers,
                  self.btn_zoom_out, self.btn_zoom_in, self.btn_zoom_reset,
                  self.btn_close):
            b.setMinimumHeight(30)

        self.btn_prev.clicked.connect(self._prev)
        self.btn_next.clicked.connect(self._next)
        self.btn_markers.clicked.connect(self._toggle_markers)
        self.btn_zoom_in.clicked.connect(lambda: self._zoom(1.25))
        self.btn_zoom_out.clicked.connect(lambda: self._zoom(0.8))
        self.btn_zoom_reset.clicked.connect(self._zoom_reset)
        self.btn_close.clicked.connect(self.accept)

        top = QHBoxLayout()
        top.addWidget(self.lbl_title, 1)
        top.addWidget(self.lbl_index)
        top.addSpacing(12)
        top.addWidget(self.btn_prev)
        top.addWidget(self.btn_next)
        top.addSpacing(12)
        top.addWidget(self.btn_zoom_out)
        top.addWidget(self.btn_zoom_in)
        top.addWidget(self.btn_zoom_reset)
        top.addSpacing(12)
        top.addWidget(self.btn_markers)
        top.addWidget(self.btn_close)

        top_holder = QWidget()
        top_holder.setLayout(top)
        top_holder.setStyleSheet(
            "background:#F4F1EA; border-bottom:2px solid #111111;"
        )

        # ---- splitter ---------------------------------------------------
        self.marker = MarkerView()
        self.report = ReportPanel()
        self.marker.region_clicked.connect(self.report.highlight)
        self.report.region_clicked.connect(self.marker.set_highlight)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.marker)
        splitter.addWidget(self.report)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([800, 480])

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(top_holder)
        root.addWidget(splitter, 1)

        # Keyboard shortcuts
        QShortcut(QKeySequence(Qt.Key.Key_Left), self, self._prev)
        QShortcut(QKeySequence(Qt.Key.Key_Right), self, self._next)
        QShortcut(QKeySequence("M"), self, self._toggle_markers)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, self.accept)

        self._render_current()

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _prev(self) -> None:
        if not self._items:
            return
        self._index = (self._index - 1) % len(self._items)
        self._render_current()

    def _next(self) -> None:
        if not self._items:
            return
        self._index = (self._index + 1) % len(self._items)
        self._render_current()

    def _render_current(self) -> None:
        if not self._items:
            self.lbl_title.setText("(no items)")
            self.marker.set_image(None)
            self.report.set_result(None)
            return
        path, result = self._items[self._index]
        self.lbl_title.setText(path.name)
        self.lbl_index.setText(f"{self._index + 1} / {len(self._items)}")

        pix = QPixmap(str(path))
        if pix.isNull():
            self.marker.set_image(None)
        else:
            self.marker.set_image(pix)
        self.marker.set_zoom(1.0)
        self.marker.set_show_markers(True)
        self.btn_markers.setText("HIDE MARKERS")
        self.marker.set_regions(result.defect_regions)
        self.report.set_result(result)

    # ------------------------------------------------------------------
    # Toolbar handlers
    # ------------------------------------------------------------------

    def _toggle_markers(self) -> None:
        new = not self.marker.show_markers()
        self.marker.set_show_markers(new)
        self.btn_markers.setText("HIDE MARKERS" if new else "SHOW MARKERS")

    def _zoom(self, factor: float) -> None:
        self.marker.set_zoom(self.marker.zoom() * factor)

    def _zoom_reset(self) -> None:
        self.marker.set_zoom(1.0)
