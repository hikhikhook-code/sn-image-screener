"""Defect-marker overlay on top of an image preview.

Renders the original image untouched and paints :class:`DefectRegion`
shapes (boxes / circles) on top using a ``QPainter`` overlay. The user
can:

    * toggle markers on/off
    * highlight a single region (e.g. when its row in the report is
      clicked) — the highlighted marker is drawn thicker and gets a
      label tag
    * click a marker to emit :pyattr:`region_clicked` so the report
      panel can reflect the selection
"""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush, QColor, QFont, QPainter, QPen, QPixmap, QResizeEvent, QMouseEvent,
)
from PySide6.QtWidgets import QWidget

from ...services.ai.types import DefectRegion, Severity, Shape


SEVERITY_COLORS = {
    Severity.MINOR: QColor("#FFC700"),      # yellow
    Severity.MODERATE: QColor("#FF8A1F"),   # orange
    Severity.MAJOR: QColor("#FF3B30"),      # red
    Severity.CRITICAL: QColor("#B30000"),   # deep red
}


class MarkerView(QWidget):
    """Image preview with optional defect-marker overlay."""

    region_clicked = Signal(str)   # emits region.id when a marker is hit

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(320, 240)
        self.setAutoFillBackground(False)
        self._pixmap: Optional[QPixmap] = None
        self._regions: List[DefectRegion] = []
        self._show_markers: bool = True
        self._highlight_id: Optional[str] = None
        self._zoom: float = 1.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_image(self, pixmap: Optional[QPixmap]) -> None:
        self._pixmap = pixmap
        self.update()

    def set_regions(self, regions: List[DefectRegion]) -> None:
        self._regions = list(regions)
        self.update()

    def set_show_markers(self, show: bool) -> None:
        self._show_markers = bool(show)
        self.update()

    def show_markers(self) -> bool:
        return self._show_markers

    def set_highlight(self, region_id: Optional[str]) -> None:
        self._highlight_id = region_id
        self.update()

    def set_zoom(self, factor: float) -> None:
        self._zoom = max(0.1, min(8.0, factor))
        self.update()

    def zoom(self) -> float:
        return self._zoom

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def paintEvent(self, _ev) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(self.rect(), QColor("#111111"))

        if self._pixmap is None or self._pixmap.isNull():
            p.setPen(QColor("#888888"))
            p.drawText(
                self.rect(),
                int(Qt.AlignmentFlag.AlignCenter),
                "No image loaded",
            )
            return

        target = self._fit_rect()
        p.drawPixmap(target, self._pixmap, self._pixmap.rect())

        if not self._show_markers:
            return

        for r in self._regions:
            self._paint_region(p, r, target)

    def _fit_rect(self) -> QRect:
        """Position the pixmap (aspect-fit + zoom) inside the widget."""
        if self._pixmap is None:
            return self.rect()
        pw, ph = self._pixmap.width(), self._pixmap.height()
        if pw == 0 or ph == 0:
            return self.rect()
        aw, ah = self.width(), self.height()
        scale = min(aw / pw, ah / ph) * self._zoom
        w = int(pw * scale)
        h = int(ph * scale)
        x = (aw - w) // 2
        y = (ah - h) // 2
        return QRect(x, y, w, h)

    def _paint_region(self, p: QPainter, r: DefectRegion, frame: QRect) -> None:
        if not r.is_valid():
            return
        y0, x0, y1, x1 = r.box_2d
        # Translate from 0..1000 to pixel coords inside `frame`.
        rx = frame.x() + x0 / 1000.0 * frame.width()
        ry = frame.y() + y0 / 1000.0 * frame.height()
        rw = (x1 - x0) / 1000.0 * frame.width()
        rh = (y1 - y0) / 1000.0 * frame.height()
        rect = QRectF(rx, ry, rw, rh)

        is_highlight = (r.id == self._highlight_id)
        base = SEVERITY_COLORS.get(r.severity, QColor("#FF3B30"))
        pen_w = 4 if is_highlight else 2
        pen = QPen(base, pen_w)
        pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        p.setPen(pen)
        # Soft fill (alpha) for visibility against busy images.
        fill = QColor(base)
        fill.setAlpha(60 if is_highlight else 30)
        p.setBrush(QBrush(fill))

        if r.shape == Shape.CIRCLE:
            p.drawEllipse(rect)
        else:
            p.drawRect(rect)

        # Label tag in the top-left corner of the region.
        if r.label or r.id:
            label = (r.label or r.id).upper()
            font = QFont(self.font())
            font.setBold(True)
            font.setPointSize(max(8, font.pointSize() - 1))
            p.setFont(font)
            metrics = p.fontMetrics()
            pad_x, pad_y = 6, 2
            text_w = metrics.horizontalAdvance(label) + pad_x * 2
            text_h = metrics.height() + pad_y * 2
            tag_rect = QRectF(rect.x(), rect.y() - text_h, text_w, text_h)
            # Keep tag inside the frame.
            if tag_rect.y() < frame.y():
                tag_rect.moveTop(rect.y())
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(base))
            p.drawRect(tag_rect)
            p.setPen(QColor("#FFFFFF" if r.severity in (Severity.MAJOR, Severity.CRITICAL) else "#111111"))
            p.drawText(tag_rect, int(Qt.AlignmentFlag.AlignCenter), label)

    # ------------------------------------------------------------------
    # Mouse — click on a marker emits its id
    # ------------------------------------------------------------------

    def mousePressEvent(self, ev: QMouseEvent) -> None:
        if not self._show_markers or self._pixmap is None:
            return super().mousePressEvent(ev)
        frame = self._fit_rect()
        pos: QPointF = ev.position() if hasattr(ev, "position") else QPointF(ev.x(), ev.y())
        # Walk in reverse so top-most region wins.
        for r in reversed(self._regions):
            if not r.is_valid():
                continue
            y0, x0, y1, x1 = r.box_2d
            rx = frame.x() + x0 / 1000.0 * frame.width()
            ry = frame.y() + y0 / 1000.0 * frame.height()
            rw = (x1 - x0) / 1000.0 * frame.width()
            rh = (y1 - y0) / 1000.0 * frame.height()
            if QRectF(rx, ry, rw, rh).contains(pos):
                self._highlight_id = r.id
                self.region_clicked.emit(r.id)
                self.update()
                return
        return super().mousePressEvent(ev)

    def resizeEvent(self, ev: QResizeEvent) -> None:
        self.update()
        return super().resizeEvent(ev)
