"""Polished full review workspace — image left, inspection report right.

Single dialog used by both entry points:

    * AI Inspector → ``Open Full Review`` button or queue double-click.
    * Technical Quality → results-table row double-click.

The dialog itself is generic. Callers pass a list of
:class:`FullReviewItem`\\ s, the report widget to embed on the right,
and a callable that updates that widget for the current item.

Backend untouched — this module only wires existing widgets
(:class:`~sn_image_screener.ui.ai.marker_view.MarkerView` and any
caller-provided report panel) into a single workspace with a
brutalist toolbar, prev/next navigation, marker toggling, zoom
controls, and keyboard shortcuts (``Left`` / ``Right`` / ``Esc`` /
``M`` / ``+`` / ``-`` / ``0``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, List, Optional

from PySide6.QtCore import QEvent, QSize, Qt, Signal
from PySide6.QtGui import QGuiApplication, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QPushButton,
    QSizePolicy, QSplitter, QStackedLayout, QToolButton, QVBoxLayout, QWidget,
)

from . import theme
from .ai.marker_view import MarkerView
from .widgets import EmptyState


# ---------------------------------------------------------------------------
# Status badge styling — PASS = lime, REVIEW = orange, FAIL/REJECT = red,
# ERROR = dark / yellow. Matches the rest of the UI's palette so the badge
# in the toolbar reads identically to the row badge in the results table.
# ---------------------------------------------------------------------------

_STATUS_COLORS = {
    "PASS":   ("#6FE34D", "#0B2D00"),
    "REVIEW": (theme.REVIEW_BG, theme.REVIEW_FG),
    "FAIL":   (theme.REJECT_BG, theme.REJECT_FG),
    "REJECT": (theme.REJECT_BG, theme.REJECT_FG),
    "ERROR":  (theme.INK,       theme.YELLOW),
}


# ---------------------------------------------------------------------------
# Item shape used by the dialog. ``payload`` is an arbitrary object the
# caller hands back to its own ``on_item_changed`` callable so it can
# update the right-hand report panel however it likes (e.g. set an
# AnatomyResult, render technical metrics, etc.).
# ---------------------------------------------------------------------------


@dataclass
class FullReviewItem:
    path: Path
    status: str = "ERROR"
    regions: List[Any] = field(default_factory=list)
    payload: Any = None


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------


class FullReviewDialog(QDialog):
    """Image-left / report-right review workspace."""

    item_changed = Signal(int)  # current index (0-based)

    def __init__(
        self,
        items: List[FullReviewItem],
        *,
        report_widget: QWidget,
        on_item_changed: Callable[[Optional[FullReviewItem]], None],
        start_index: int = 0,
        title: str = "Full Review",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setObjectName("full-review")
        self.setSizeGripEnabled(True)
        self.resize(1320, 820)

        self._items: List[FullReviewItem] = list(items)
        self._index: int = (
            max(0, min(start_index, len(self._items) - 1))
            if self._items else 0
        )
        self._on_item_changed = on_item_changed
        self._report_widget = report_widget

        self._build_toolbar()
        self._build_body(report_widget)

        # Keyboard shortcuts. Use ``Qt.ApplicationShortcut`` so they fire
        # even if a child widget (e.g. the report list) currently has
        # keyboard focus.
        for keys, handler in (
            (Qt.Key.Key_Left,   self._prev),
            (Qt.Key.Key_Right,  self._next),
            (Qt.Key.Key_Escape, self.close),
            ("M",               self._toggle_markers),
            ("+",               self._zoom_in),
            ("=",               self._zoom_in),
            ("-",               self._zoom_out),
            ("0",               self._zoom_fit),
            ("F",               self._zoom_fit),
        ):
            sc = QShortcut(QKeySequence(keys), self, handler)
            sc.setContext(Qt.ShortcutContext.ApplicationShortcut)

        self._render_current()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_toolbar(self) -> None:
        """Top toolbar: back, status badge, filename + copy, counter,
        markers toggle, zoom controls, close.
        """
        bar = QFrame()
        bar.setObjectName("review-toolbar")
        bar.setMinimumHeight(54)
        bar.setStyleSheet(
            f"#review-toolbar {{"
            f"  background:{theme.SURFACE};"
            f"  border-bottom:2px solid {theme.INK};"
            f"}}"
        )
        h = QHBoxLayout(bar)
        h.setContentsMargins(12, 8, 12, 8)
        h.setSpacing(8)

        # Back to dashboard
        self.btn_back = QPushButton("◀  BACK TO DASHBOARD")
        self.btn_back.setObjectName("brutal-secondary")
        self.btn_back.setMinimumHeight(36)
        self.btn_back.clicked.connect(self.close)
        h.addWidget(self.btn_back)

        h.addSpacing(10)

        # Status badge — repainted via _set_status_badge() per item.
        self.lbl_status = QLabel("—")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_status.setMinimumWidth(72)
        self.lbl_status.setMinimumHeight(36)
        h.addWidget(self.lbl_status)

        # Filename — bold, elided when the toolbar is narrow.
        self.lbl_filename = QLabel("")
        self.lbl_filename.setObjectName("review-filename")
        f = self.lbl_filename.font()
        f.setBold(True)
        f.setPointSize(max(f.pointSize() + 1, 12))
        self.lbl_filename.setFont(f)
        self.lbl_filename.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred,
        )
        self.lbl_filename.setMinimumWidth(120)
        h.addWidget(self.lbl_filename, 1)

        self.btn_copy = QToolButton()
        self.btn_copy.setText("COPY")
        self.btn_copy.setToolTip("Copy filename")
        self.btn_copy.setMinimumHeight(32)
        self.btn_copy.clicked.connect(self._copy_filename)
        h.addWidget(self.btn_copy)

        # Counter
        self.lbl_counter = QLabel("0 of 0")
        self.lbl_counter.setStyleSheet(f"color:{theme.INK_MUTED};")
        self.lbl_counter.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_counter.setMinimumWidth(72)
        h.addWidget(self.lbl_counter)

        h.addSpacing(10)

        # Markers toggle
        self.btn_markers = QPushButton("HIDE MARKERS")
        self.btn_markers.setObjectName("brutal-secondary")
        self.btn_markers.setCheckable(True)
        self.btn_markers.setChecked(True)
        self.btn_markers.setMinimumHeight(36)
        self.btn_markers.clicked.connect(self._on_markers_clicked)
        h.addWidget(self.btn_markers)

        h.addSpacing(10)

        # Zoom controls. ``QPushButton``\\ s in this codebase carry a
        # 7px × 14px QSS padding that would clip ``+`` / ``-`` glyphs at
        # icon-sized buttons, so we use lighter ``QToolButton``\\ s and
        # restyle them to match the brutalist secondary look.
        zoom_qss = (
            f"QToolButton#review-zoom {{"
            f"  background:{theme.SURFACE}; color:{theme.INK};"
            f"  border:2px solid {theme.INK};"
            f"  font-weight:900; font-size:16px;"
            f"  padding:0; margin:0;"
            f"}}"
            f"QToolButton#review-zoom:hover {{"
            f"  background:{theme.INK}; color:{theme.LIME};"
            f"}}"
            f"QToolButton#review-zoom:pressed {{"
            f"  background:{theme.INK}; color:{theme.LIME};"
            f"}}"
        )

        def _zoom_btn(text: str, tooltip: str, width: int, handler) -> QToolButton:
            b = QToolButton()
            b.setObjectName("review-zoom")
            b.setText(text)
            b.setToolTip(tooltip)
            b.setStyleSheet(zoom_qss)
            b.setFixedSize(QSize(width, 36))
            b.clicked.connect(handler)
            return b

        self.btn_zoom_out   = _zoom_btn("−",    "Zoom out (−)",        40, self._zoom_out)
        self.btn_zoom_label = _zoom_btn("100%", "Reset zoom",          76, self._zoom_reset)
        self.btn_zoom_in    = _zoom_btn("+",    "Zoom in (+)",         40, self._zoom_in)
        self.btn_zoom_fit   = _zoom_btn("FIT",  "Fit to screen (F / 0)", 56, self._zoom_fit)
        for b in (
            self.btn_zoom_out, self.btn_zoom_label,
            self.btn_zoom_in, self.btn_zoom_fit,
        ):
            h.addWidget(b)

        h.addSpacing(10)

        self.btn_close = QPushButton("CLOSE")
        self.btn_close.setObjectName("brutal-ghost")
        self.btn_close.setMinimumHeight(36)
        self.btn_close.clicked.connect(self.close)
        h.addWidget(self.btn_close)

        self._toolbar = bar

    def _build_body(self, report_widget: QWidget) -> None:
        """Edge-to-edge image left, report right.

        Prev/next nav buttons are rendered as translucent overlay
        children of the image host so the photo fills its column with
        no surrounding margin.
        """
        # --- Image area --------------------------------------------------
        self.marker = MarkerView()
        self.marker.setMinimumSize(540, 360)
        self.marker.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding,
        )
        # Mouse-wheel zoom (and double-click reset) inside MarkerView
        # bypass the toolbar buttons, so subscribe to its zoom_changed
        # signal to keep the % label in the toolbar in sync.
        self.marker.zoom_changed.connect(self._on_marker_zoom_changed)

        # Empty-state placeholder + image stacked together so we can swap
        # them when the dialog is opened with zero items.
        self._image_stack_host = QFrame()
        self._image_stack_host.setObjectName("review-image-host")
        self._image_stack_host.setStyleSheet(
            f"#review-image-host {{ background:{theme.INK}; "
            f"  border:0px; }}"
        )
        self._image_stack = QStackedLayout(self._image_stack_host)
        self._image_stack.setContentsMargins(0, 0, 0, 0)
        self._image_stack.addWidget(self.marker)
        self._image_empty = EmptyState(
            title="NO IMAGE LOADED",
            body="Image failed to load. Try opening another item.",
        )
        # Empty state lives inside an ink-coloured panel, so override the
        # text colour for legibility.
        self._image_empty.setStyleSheet(
            f"#empty-state {{ background:{theme.INK}; "
            f"  border:2px dashed {theme.LIME}; }}"
            f"#empty-state-title, #empty-state-body {{ "
            f"  color:{theme.LIME}; }}"
        )
        self._image_stack.addWidget(self._image_empty)
        self._image_stack.setCurrentIndex(0)

        # --- Overlay nav buttons (children of the host, not laid out) ---
        # Fully transparent chevrons — no dark/grey rectangular backdrop,
        # no border. They are hidden until the cursor enters the image
        # area and re-hidden when it leaves, with a subtle lime-glow
        # hover effect that only colours the glyph itself.
        nav_style = (
            f"QToolButton#review-nav {{"
            f"  background:transparent;"
            f"  color:{theme.LIME};"
            f"  border:none;"
            f"  font-size:48px; font-weight:900;"
            f"  padding:0;"
            f"}}"
            f"QToolButton#review-nav:hover {{"
            f"  background:transparent;"
            f"  color:#FFFFFF;"
            f"  border:none;"
            f"}}"
            f"QToolButton#review-nav:disabled {{"
            f"  background:transparent;"
            f"  color:rgba(214,238,44,80);"
            f"  border:none;"
            f"}}"
        )
        self.btn_prev = QToolButton(self._image_stack_host)
        self.btn_prev.setObjectName("review-nav")
        self.btn_prev.setText("\u2039")  # single left-pointing chevron
        self.btn_prev.setToolTip("Previous image (Left arrow)")
        self.btn_prev.setFixedSize(QSize(64, 120))
        self.btn_prev.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_prev.setStyleSheet(nav_style)
        self.btn_prev.setAutoFillBackground(False)
        self.btn_prev.setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground, True,
        )
        self.btn_prev.clicked.connect(self._prev)
        self.btn_prev.hide()
        self.btn_prev.raise_()

        self.btn_next = QToolButton(self._image_stack_host)
        self.btn_next.setObjectName("review-nav")
        self.btn_next.setText("\u203A")  # single right-pointing chevron
        self.btn_next.setToolTip("Next image (Right arrow)")
        self.btn_next.setFixedSize(QSize(64, 120))
        self.btn_next.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_next.setStyleSheet(nav_style)
        self.btn_next.setAutoFillBackground(False)
        self.btn_next.setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground, True,
        )
        self.btn_next.clicked.connect(self._next)
        self.btn_next.hide()
        self.btn_next.raise_()

        # Track mouse movement on the host so the chevrons can fade in
        # only while the cursor is over the image area.
        self._image_stack_host.setMouseTracking(True)
        self.marker.setMouseTracking(True)
        self._image_stack_host.installEventFilter(self)

        image_pane = self._image_stack_host

        # --- Right report panel -----------------------------------------
        report_holder = QFrame()
        report_holder.setObjectName("brutal-card")
        rh = QVBoxLayout(report_holder)
        rh.setContentsMargins(2, 2, 2, 2)
        rh.setSpacing(0)
        rh.addWidget(report_widget, 1)
        report_holder.setMinimumWidth(360)

        # --- Splitter ---------------------------------------------------
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(image_pane)
        splitter.addWidget(report_holder)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([820, 480])

        # --- Root layout ------------------------------------------------
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._toolbar)
        root.addWidget(splitter, 1)

    # ------------------------------------------------------------------
    # Overlay nav button positioning
    # ------------------------------------------------------------------

    def eventFilter(self, obj, event):  # type: ignore[override]
        if obj is self._image_stack_host:
            t = event.type()
            if t == QEvent.Type.Resize:
                self._reposition_nav()
            elif t == QEvent.Type.Enter:
                self._set_nav_visible(True)
            elif t == QEvent.Type.Leave:
                self._set_nav_visible(False)
        return super().eventFilter(obj, event)

    def _set_nav_visible(self, visible: bool) -> None:
        """Show / hide the overlay chevrons.

        Chevrons stay hidden whenever the cursor is outside the image
        host or there is at most one item to navigate between, so they
        never read as a permanent UI element when there's nothing to do.
        """
        if visible and len(self._items) > 1:
            self.btn_prev.show()
            self.btn_next.show()
            self._reposition_nav()
        else:
            self.btn_prev.hide()
            self.btn_next.hide()

    def _reposition_nav(self) -> None:
        host = self._image_stack_host
        margin = 14
        y = (host.height() - self.btn_prev.height()) // 2
        self.btn_prev.move(margin, max(margin, y))
        self.btn_next.move(
            host.width() - self.btn_next.width() - margin,
            max(margin, y),
        )
        # Make sure the overlay buttons stay above the QStackedLayout
        # children that get re-stacked when the empty state toggles.
        self.btn_prev.raise_()
        self.btn_next.raise_()

    def showEvent(self, event):  # type: ignore[override]
        super().showEvent(event)
        # Defer one pass so widget sizes have settled before we move
        # the overlay buttons into place. They stay hidden until the
        # cursor enters the image host.
        self._reposition_nav()
        self.btn_prev.hide()
        self.btn_next.hide()

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _prev(self) -> None:
        if len(self._items) <= 1:
            return
        self._index = (self._index - 1) % len(self._items)
        self._render_current()

    def _next(self) -> None:
        if len(self._items) <= 1:
            return
        self._index = (self._index + 1) % len(self._items)
        self._render_current()

    # ------------------------------------------------------------------
    # Per-item rendering
    # ------------------------------------------------------------------

    def _render_current(self) -> None:
        n = len(self._items)
        if n == 0:
            self.lbl_filename.setText("(no items)")
            self.lbl_counter.setText("0 of 0")
            self._set_status_badge("ERROR")
            self.marker.set_image(None)
            self.marker.set_regions([])
            self.btn_prev.setEnabled(False)
            self.btn_next.setEnabled(False)
            self._on_item_changed(None)
            self._image_stack.setCurrentIndex(1)
            return

        item = self._items[self._index]
        self.lbl_filename.setText(item.path.name)
        self.lbl_filename.setToolTip(str(item.path))
        self.lbl_counter.setText(f"{self._index + 1} of {n}")
        self._set_status_badge(item.status)

        pix = QPixmap(str(item.path))
        if pix.isNull():
            self.marker.set_image(None)
            self._image_empty.setStyleSheet(
                f"#empty-state {{ background:{theme.INK}; "
                f"  border:2px dashed {theme.REJECT_BG}; }}"
                f"#empty-state-title, #empty-state-body {{ "
                f"  color:{theme.REJECT_BG}; }}"
            )
            self._image_empty.set_text(
                "IMAGE FAILED TO LOAD",
                f"Could not decode {item.path.name}. The file may be missing "
                "or corrupt.",
            )
            self._image_stack.setCurrentIndex(1)
        else:
            self.marker.set_image(pix)
            self._image_stack.setCurrentIndex(0)
        self.marker.set_zoom(1.0)
        self._update_zoom_label()
        self.marker.set_show_markers(True)
        self.btn_markers.setChecked(True)
        self.btn_markers.setText("HIDE MARKERS")
        self.marker.set_regions(item.regions or [])

        # Prev / next stay enabled even with one item but the cycle is
        # a no-op then; explicitly disable so the buttons don't read as
        # affordances when there's nothing to navigate to.
        single = n <= 1
        self.btn_prev.setEnabled(not single)
        self.btn_next.setEnabled(not single)

        self._on_item_changed(item)
        self.item_changed.emit(self._index)

    def _set_status_badge(self, status: str) -> None:
        s = (status or "ERROR").upper()
        if s not in _STATUS_COLORS:
            s = "ERROR"
        bg, fg = _STATUS_COLORS[s]
        self.lbl_status.setText(s)
        self.lbl_status.setStyleSheet(
            f"background:{bg}; color:{fg}; "
            f"border:2px solid {theme.INK}; "
            f"font-weight:900; letter-spacing:1.5px; padding:4px 10px;"
        )

    # ------------------------------------------------------------------
    # Toolbar handlers
    # ------------------------------------------------------------------

    def _on_markers_clicked(self) -> None:
        self._toggle_markers()

    def _toggle_markers(self) -> None:
        new = not self.marker.show_markers()
        self.marker.set_show_markers(new)
        self.btn_markers.setChecked(new)
        self.btn_markers.setText("HIDE MARKERS" if new else "SHOW MARKERS")

    def _zoom_in(self) -> None:
        self.marker.set_zoom(self.marker.zoom() * 1.25)
        self._update_zoom_label()

    def _zoom_out(self) -> None:
        self.marker.set_zoom(self.marker.zoom() * 0.8)
        self._update_zoom_label()

    def _zoom_fit(self) -> None:
        self.marker.set_zoom(1.0)
        self._update_zoom_label()

    _zoom_reset = _zoom_fit

    def _update_zoom_label(self) -> None:
        z = int(round(self.marker.zoom() * 100))
        self.btn_zoom_label.setText(f"{z}%")

    def _on_marker_zoom_changed(self, _factor: float) -> None:
        # MarkerView already knows the new zoom; just keep the toolbar
        # % label aligned with whatever the user did (wheel, drag,
        # toolbar button, double-click reset).
        self._update_zoom_label()

    def _copy_filename(self) -> None:
        if not self._items:
            return
        QGuiApplication.clipboard().setText(
            self._items[self._index].path.name
        )

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def current_item(self) -> Optional[FullReviewItem]:
        if not self._items:
            return None
        return self._items[self._index]
