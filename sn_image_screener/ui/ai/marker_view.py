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
    QBrush, QColor, QFont, QMouseEvent, QPainter, QPen, QPixmap, QResizeEvent,
    QWheelEvent,
)
from PySide6.QtWidgets import QWidget

from ...services.ai.types import DefectRegion, Severity, Shape


SEVERITY_COLORS = {
    Severity.MINOR: QColor("#FFC700"),      # yellow
    Severity.MODERATE: QColor("#FF8A1F"),   # orange
    Severity.MAJOR: QColor("#FF3B30"),      # red
    Severity.CRITICAL: QColor("#B30000"),   # deep red
}


# Zoom limits and the per-wheel-notch multiplier. Each notch (one
# physical detent on a typical mouse wheel) multiplies / divides the
# current zoom by ``_WHEEL_STEP``. The cap mirrors :meth:`set_zoom`'s
# clamp so the +/- buttons and the wheel agree on the maximum.
_MIN_ZOOM = 0.1
_MAX_ZOOM = 8.0
_WHEEL_STEP = 1.25


class MarkerView(QWidget):
    """Image preview with optional defect-marker overlay.

    Supports mouse-wheel zoom (anchored at the cursor so the point under
    the cursor stays put), click-and-drag panning when zoomed in, and
    double-click to reset zoom + pan to the default fit. The zoom level
    is also reachable programmatically via :meth:`set_zoom` / the
    existing toolbar buttons; both code paths emit
    :pyattr:`zoom_changed` so external % labels stay in sync.
    """

    region_clicked = Signal(str)   # emits region.id when a marker is hit
    zoom_changed = Signal(float)   # emits new zoom factor (1.0 == fit)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(320, 240)
        self.setAutoFillBackground(False)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.WheelFocus)
        self._pixmap: Optional[QPixmap] = None
        self._regions: List[DefectRegion] = []
        self._show_markers: bool = True
        self._highlight_id: Optional[str] = None
        self._zoom: float = 1.0
        # Pan offset in widget pixels, applied on top of the centred
        # fit rect. Reset whenever zoom returns to 1.0 so the image is
        # re-centred.
        self._pan_x: int = 0
        self._pan_y: int = 0
        # Drag-pan state.
        self._dragging: bool = False
        self._drag_anchor: Optional[QPointF] = None
        self._drag_pan_start: tuple[int, int] = (0, 0)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_image(self, pixmap: Optional[QPixmap]) -> None:
        prev_pixmap = self._pixmap
        self._pixmap = pixmap
        # When the user navigates between images, reset zoom + pan so
        # the new picture comes up at fit, not at whatever zoom the
        # previous one was left at.
        if pixmap is not prev_pixmap:
            self._dragging = False
            self._drag_anchor = None
            self.unsetCursor()
            if self._zoom != 1.0 or self._pan_x or self._pan_y:
                self._pan_x = 0
                self._pan_y = 0
                if self._zoom != 1.0:
                    self._zoom = 1.0
                    self.zoom_changed.emit(self._zoom)
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
        new_zoom = max(_MIN_ZOOM, min(_MAX_ZOOM, factor))
        if new_zoom == self._zoom:
            return
        self._zoom = new_zoom
        # Returning to (or below) fit recentres the image — there is
        # no useful place to keep panning to once the whole image fits
        # the viewport.
        if self._zoom <= 1.0:
            self._pan_x = 0
            self._pan_y = 0
        else:
            self._clamp_pan()
        self.zoom_changed.emit(self._zoom)
        self.update()

    def zoom(self) -> float:
        return self._zoom

    def reset_view(self) -> None:
        """Reset zoom to fit and re-centre the image."""
        self._pan_x = 0
        self._pan_y = 0
        self.set_zoom(1.0)

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
        """Position the pixmap (aspect-fit + zoom + pan) inside the widget."""
        if self._pixmap is None:
            return self.rect()
        pw, ph = self._pixmap.width(), self._pixmap.height()
        if pw == 0 or ph == 0:
            return self.rect()
        aw, ah = self.width(), self.height()
        scale = min(aw / pw, ah / ph) * self._zoom
        w = int(pw * scale)
        h = int(ph * scale)
        x = (aw - w) // 2 + self._pan_x
        y = (ah - h) // 2 + self._pan_y
        return QRect(x, y, w, h)

    def _clamp_pan(self) -> None:
        """Stop the user from dragging the image entirely off-screen.

        When the image is larger than the viewport (zoom > fit), pan is
        clamped so the image edges do not move past the viewport edges.
        When the image is smaller than the viewport, pan is forced to
        zero so the image stays centred.
        """
        if self._pixmap is None or self._pixmap.isNull():
            self._pan_x = 0
            self._pan_y = 0
            return
        pw, ph = self._pixmap.width(), self._pixmap.height()
        if pw == 0 or ph == 0:
            self._pan_x = 0
            self._pan_y = 0
            return
        aw, ah = self.width(), self.height()
        scale = min(aw / pw, ah / ph) * self._zoom
        w = int(pw * scale)
        h = int(ph * scale)
        # Horizontal: when w <= aw the image is centred regardless of
        # pan. When w > aw, pan range is +/- (w - aw) / 2.
        if w <= aw:
            self._pan_x = 0
        else:
            limit = (w - aw) // 2
            self._pan_x = max(-limit, min(limit, self._pan_x))
        if h <= ah:
            self._pan_y = 0
        else:
            limit = (h - ah) // 2
            self._pan_y = max(-limit, min(limit, self._pan_y))

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
        if self._pixmap is None:
            return super().mousePressEvent(ev)
        pos: QPointF = (
            ev.position() if hasattr(ev, "position") else QPointF(ev.x(), ev.y())
        )
        # Marker hit-test takes priority over panning so users can
        # always click a defect even while zoomed in.
        if self._show_markers and ev.button() == Qt.MouseButton.LeftButton:
            frame = self._fit_rect()
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
        # Otherwise: begin panning if the user has zoomed in (otherwise
        # there is nothing to pan to).
        if ev.button() == Qt.MouseButton.LeftButton and self._zoom > 1.0:
            self._dragging = True
            self._drag_anchor = QPointF(pos)
            self._drag_pan_start = (self._pan_x, self._pan_y)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            ev.accept()
            return
        return super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev: QMouseEvent) -> None:
        if self._dragging and self._drag_anchor is not None:
            pos: QPointF = (
                ev.position()
                if hasattr(ev, "position")
                else QPointF(ev.x(), ev.y())
            )
            dx = int(round(pos.x() - self._drag_anchor.x()))
            dy = int(round(pos.y() - self._drag_anchor.y()))
            self._pan_x = self._drag_pan_start[0] + dx
            self._pan_y = self._drag_pan_start[1] + dy
            self._clamp_pan()
            self.update()
            ev.accept()
            return
        return super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev: QMouseEvent) -> None:
        if self._dragging and ev.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self._drag_anchor = None
            self.unsetCursor()
            ev.accept()
            return
        return super().mouseReleaseEvent(ev)

    def mouseDoubleClickEvent(self, ev: QMouseEvent) -> None:
        """Reset zoom + pan back to the default fit."""
        if ev.button() == Qt.MouseButton.LeftButton and self._pixmap is not None:
            self.reset_view()
            ev.accept()
            return
        return super().mouseDoubleClickEvent(ev)

    def wheelEvent(self, ev: QWheelEvent) -> None:
        """Zoom in / out at the cursor position.

        ``angleDelta().y() > 0`` (wheel up) zooms in, ``< 0`` zooms out.
        The zoom is anchored at the cursor: the image point currently
        under the cursor stays under the cursor after the zoom step.
        """
        if self._pixmap is None or self._pixmap.isNull():
            return super().wheelEvent(ev)
        steps = ev.angleDelta().y() / 120.0
        if steps == 0:
            return super().wheelEvent(ev)
        factor = _WHEEL_STEP ** steps
        new_zoom = max(_MIN_ZOOM, min(_MAX_ZOOM, self._zoom * factor))
        if new_zoom == self._zoom:
            ev.accept()
            return
        cursor: QPointF = (
            ev.position()
            if hasattr(ev, "position")
            else QPointF(ev.x(), ev.y())
        )
        old_frame = self._fit_rect()
        if old_frame.width() <= 0 or old_frame.height() <= 0:
            self._zoom = new_zoom
            self.zoom_changed.emit(self._zoom)
            ev.accept()
            self.update()
            return
        # Image-relative fraction at the cursor before the zoom step.
        frac_x = (cursor.x() - old_frame.x()) / old_frame.width()
        frac_y = (cursor.y() - old_frame.y()) / old_frame.height()
        # Apply the zoom and recompute the centred frame (pan = 0) so
        # we know where the cursor's image fraction maps to without any
        # offset, then derive the pan that puts it back under the
        # cursor.
        self._zoom = new_zoom
        old_pan = (self._pan_x, self._pan_y)
        self._pan_x = 0
        self._pan_y = 0
        centred = self._fit_rect()
        target_x = centred.x() + frac_x * centred.width()
        target_y = centred.y() + frac_y * centred.height()
        self._pan_x = int(round(cursor.x() - target_x))
        self._pan_y = int(round(cursor.y() - target_y))
        if self._zoom <= 1.0:
            # Below fit, panning has no purpose — keep the image centred.
            self._pan_x = 0
            self._pan_y = 0
        else:
            self._clamp_pan()
        # No-op fast path: if zoom + pan ended up exactly where they
        # started, suppress redraw and signal.
        if (
            self._zoom == self._zoom
            and (self._pan_x, self._pan_y) == old_pan
            and old_frame == self._fit_rect()
        ):
            ev.accept()
            return
        self.zoom_changed.emit(self._zoom)
        self.update()
        ev.accept()

    def resizeEvent(self, ev: QResizeEvent) -> None:
        # The pan is expressed in widget pixels; clamp so the image
        # never strands itself off-canvas after a window resize.
        self._clamp_pan()
        self.update()
        return super().resizeEvent(ev)
