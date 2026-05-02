"""Right side image inspector — preview + metric block + issue chips."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QScrollArea, QSizePolicy,
    QStackedLayout, QVBoxLayout, QWidget,
)

from . import theme
from .widgets import EmptyState, IssueChip, StatusTag, label, make_card
from ..core.scanner import ScanItem


class _MetricBlock(QFrame):
    """Stacked metric value + caption, with a charcoal border."""

    def __init__(self, caption: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("brutal-card-alt")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(2)

        self._cap = QLabel(caption.upper())
        self._cap.setObjectName("metric-label")
        layout.addWidget(self._cap)

        self._val = QLabel("—")
        self._val.setObjectName("metric-value")
        layout.addWidget(self._val)

    def set_value(self, text: str) -> None:
        self._val.setText(text)


class Inspector(QFrame):
    """Right column: large preview, headline tags, metric grid, issue chips."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("brutal-card")
        self.setMinimumWidth(320)
        self.setMaximumWidth(520)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 14, 14, 14)
        outer.setSpacing(12)

        # Header ---------------------------------------------------------
        hdr = QHBoxLayout()
        hdr.setSpacing(10)

        self.tag = StatusTag("PASS")
        hdr.addWidget(self.tag)

        title = QLabel("INSPECTOR")
        title.setObjectName("section-title")
        hdr.addWidget(title)
        hdr.addStretch(1)

        outer.addLayout(hdr)

        # Preview --------------------------------------------------------
        # The preview slot stacks the actual image label and an empty-
        # state placeholder so the inspector looks intentional, not
        # broken, before the user has selected a row.
        preview_host = QFrame()
        preview_host.setMinimumHeight(220)
        preview_host.setStyleSheet("background:transparent;")
        self._preview_stack = QStackedLayout(preview_host)
        self._preview_stack.setStackingMode(QStackedLayout.StackingMode.StackOne)
        self._preview_stack.setContentsMargins(0, 0, 0, 0)

        self.preview = QLabel()
        self.preview.setMinimumHeight(220)
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setStyleSheet(
            f"background:{theme.SURFACE_ALT};"
            f"border:2px solid {theme.INK};"
        )
        self._preview_stack.addWidget(self.preview)

        self._preview_empty = EmptyState(
            title="SELECT AN IMAGE",
            body="Pick a row from the results table to preview it here.",
        )
        self._preview_stack.addWidget(self._preview_empty)
        self._preview_stack.setCurrentIndex(1)
        outer.addWidget(preview_host)

        # Detailed metrics container — hidden until a scan has run so
        # the empty inspector doesn't read as "broken with dashes".
        # The body shows a single empty-state card in that case via
        # ``_metrics_empty``.
        self._metrics_empty = EmptyState(
            title="NO METRICS YET",
            body="Run a scan to see metrics and issues for each image.",
        )
        outer.addWidget(self._metrics_empty)

        self._metrics_box = QFrame()
        self._metrics_box.setObjectName("inspector-metrics")
        self._metrics_box.setStyleSheet("background:transparent;")
        mv = QVBoxLayout(self._metrics_box)
        mv.setContentsMargins(0, 0, 0, 0)
        mv.setSpacing(12)

        # Filename + headline numbers -----------------------------------
        self.lbl_name = label("—", bold=True, size=12)
        self.lbl_name.setWordWrap(True)
        mv.addWidget(self.lbl_name)

        info_row = QHBoxLayout()
        info_row.setSpacing(8)
        self.lbl_dim = label("—", mono=True, soft=True, size=10)
        self.lbl_size = label("—", mono=True, soft=True, size=10)
        info_row.addWidget(self.lbl_dim)
        info_row.addWidget(self.lbl_size)
        info_row.addStretch(1)
        mv.addLayout(info_row)

        # Metric grid ---------------------------------------------------
        grid = QGridLayout()
        grid.setSpacing(8)
        self.m_score    = _MetricBlock("Quality Score")
        self.m_blur     = _MetricBlock("Blur (Laplacian σ²)")
        self.m_noise    = _MetricBlock("Noise (HF stddev)")
        self.m_exposure = _MetricBlock("Exposure (μ)")
        self.m_artifact = _MetricBlock("JPEG Artifact")
        self.m_dyn      = _MetricBlock("Dynamic Range")
        grid.addWidget(self.m_score,    0, 0, 1, 2)
        grid.addWidget(self.m_blur,     1, 0)
        grid.addWidget(self.m_noise,    1, 1)
        grid.addWidget(self.m_exposure, 2, 0)
        grid.addWidget(self.m_artifact, 2, 1)
        grid.addWidget(self.m_dyn,      3, 0, 1, 2)
        mv.addLayout(grid)

        # Issues --------------------------------------------------------
        issues_caption = QLabel("ISSUES")
        issues_caption.setObjectName("metric-label")
        mv.addWidget(issues_caption)

        self.issues_host = QFrame()
        self.issues_layout = QHBoxLayout(self.issues_host)
        self.issues_layout.setContentsMargins(0, 0, 0, 0)
        self.issues_layout.setSpacing(6)
        self.issues_layout.addStretch(1)
        mv.addWidget(self.issues_host)

        outer.addWidget(self._metrics_box)
        outer.addStretch(1)

        # Default: no scan results yet → metrics hidden, only the empty
        # state card and the preview empty state are visible.
        self.set_metrics_visible(False)

    # ----------------------------------------------------------------- API

    def set_metrics_visible(self, visible: bool) -> None:
        """Show or hide the metric grid + issues row.

        MainWindow calls this whenever the results table grows from 0
        rows to non-empty (and vice versa), so users never see a row of
        "—" placeholders before the first scan.
        """
        self._metrics_box.setVisible(visible)
        self._metrics_empty.setVisible(not visible)

    def show_item(self, item: Optional[ScanItem]) -> None:
        if item is None:
            self._clear()
            return

        # Preview --------------------------------------------------------
        pm = QPixmap(str(item.path))
        if pm.isNull():
            self.preview.setText("preview unavailable")
            self.preview.setPixmap(QPixmap())
        else:
            target = self.preview.size()
            scaled = pm.scaled(
                target.width() - 4, target.height() - 4,
                Qt.KeepAspectRatio, Qt.SmoothTransformation,
            )
            self.preview.setPixmap(scaled)
            self.preview.setText("")
        self._preview_stack.setCurrentIndex(0)

        # Header tag + filename -----------------------------------------
        self.tag.set_status(item.status.value)
        self.lbl_name.setText(item.path.name)

        # Metrics --------------------------------------------------------
        m = item.metrics
        v = item.verdict
        self.m_score.set_value(f"{item.score} / 100" if v else "—")

        if m:
            self.lbl_dim.setText(f"{m.width} × {m.height} px")
            self.lbl_size.setText(f"{m.file_kb:,.1f} KB")
            self.m_blur.set_value(f"{m.blur:.1f}")
            self.m_noise.set_value(f"{m.noise:.1f}")
            self.m_exposure.set_value(f"{m.exposure_mean:.0f}")
            self.m_artifact.set_value(f"{m.artifact:.1f}" if m.is_jpeg else "n/a")
            self.m_dyn.set_value(f"{m.dynamic_range:.0f}")
        else:
            self.lbl_dim.setText("—")
            self.lbl_size.setText("—")
            for blk in (self.m_blur, self.m_noise, self.m_exposure,
                        self.m_artifact, self.m_dyn):
                blk.set_value("—")

        # Issues ---------------------------------------------------------
        self._set_issues(item)

    # ------------------------------------------------------------ private

    def _clear(self) -> None:
        self.preview.setPixmap(QPixmap())
        self.preview.setText("")
        self._preview_stack.setCurrentIndex(1)
        self.tag.set_status("PASS")
        self.lbl_name.setText("—")
        self.lbl_dim.setText("—")
        self.lbl_size.setText("—")
        for blk in (self.m_score, self.m_blur, self.m_noise,
                    self.m_exposure, self.m_artifact, self.m_dyn):
            blk.set_value("—")
        self._set_issues(None)

    def _set_issues(self, item: Optional[ScanItem]) -> None:
        # Remove all chips except the trailing stretch.
        while self.issues_layout.count() > 1:
            child = self.issues_layout.takeAt(0)
            w = child.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

        if item is None:
            return

        if item.error:
            chip = IssueChip("ERROR", "reject")
            chip.setToolTip(item.error)
            self.issues_layout.insertWidget(self.issues_layout.count() - 1, chip)
            return

        if not item.verdict or not item.verdict.issues:
            chip = IssueChip("CLEAN", "review")
            chip.setStyleSheet(
                f"background:{theme.PASS_BG}; color:{theme.PASS_FG};"
                f"border:2px solid {theme.INK};"
                f"padding:2px 8px; font-size:10px; font-weight:900; letter-spacing:1.5px;"
            )
            self.issues_layout.insertWidget(self.issues_layout.count() - 1, chip)
            return

        seen: set[str] = set()
        for issue in item.verdict.issues:
            if issue.code in seen:
                continue
            seen.add(issue.code)
            chip = IssueChip(issue.code, issue.severity)
            chip.setToolTip(issue.label)
            self.issues_layout.insertWidget(self.issues_layout.count() - 1, chip)

    # Keep the preview pixmap proportional on resize -----------------

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        # Re-render the current pixmap if any
        pm = self.preview.pixmap()
        if pm and not pm.isNull():
            target = self.preview.size()
            self.preview.setPixmap(
                pm.scaled(target.width() - 4, target.height() - 4,
                          Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
