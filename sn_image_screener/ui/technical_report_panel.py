"""Technical inspection report — used inside the Full Review dialog.

Mirrors the structure of the AI Anatomy ``ReportPanel`` but speaks
:class:`~sn_image_screener.core.scanner.ScanItem` instead. Backend
untouched.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget,
)

from . import theme
from .widgets import EmptyState, IssueChip, StatusTag, label
from ..core.classifier import Status
from ..core.scanner import ScanItem


_STATUS_RECOMMENDATION = {
    Status.PASS:   ("ACCEPT",  "#6FE34D", "#0B2D00"),
    Status.REVIEW: ("REVIEW",  theme.REVIEW_BG, theme.REVIEW_FG),
    Status.REJECT: ("REJECT",  theme.REJECT_BG, theme.REJECT_FG),
    Status.ERROR:  ("ERROR",   theme.INK,       theme.YELLOW),
}


class _StatBox(QFrame):
    """Caption + bold value, hard-bordered."""

    def __init__(self, caption: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(
            f"background:{theme.SURFACE}; border:2px solid {theme.INK};"
        )
        v = QVBoxLayout(self)
        v.setContentsMargins(8, 6, 8, 8)
        v.setSpacing(2)
        cap = QLabel(caption.upper())
        cap.setStyleSheet(
            f"color:{theme.INK_MUTED}; font-size:10px; letter-spacing:1px;"
        )
        v.addWidget(cap)
        self._val = QLabel("—")
        f = QFont(self._val.font())
        f.setBold(True)
        f.setPointSize(f.pointSize() + 4)
        self._val.setFont(f)
        v.addWidget(self._val)

    def set_value(self, text: str) -> None:
        self._val.setText(text)


class TechnicalReportPanel(QWidget):
    """Right-hand inspection card for the Technical Quality scan."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(320)
        self._build()
        self.show_item(None)

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        # Empty state — shown when no item is selected (e.g. dialog
        # opened with an unscored row, or set_item(None) called).
        self._empty = EmptyState(
            title="NO INSPECTION REPORT",
            body="Run a scan, then open this image to see its technical "
                 "metrics and issues.",
        )
        root.addWidget(self._empty)

        self._body = QFrame()
        self._body.setStyleSheet("background:transparent;")
        body = QVBoxLayout(self._body)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(10)
        root.addWidget(self._body, 1)

        # Decision card -------------------------------------------------
        decision = QFrame()
        decision.setStyleSheet(
            f"background:{theme.SURFACE}; border:2px solid {theme.INK};"
        )
        dec = QVBoxLayout(decision)
        dec.setContentsMargins(12, 10, 12, 12)
        dec.setSpacing(8)

        dec_title = QLabel("INSPECTION RESULT")
        dec_title.setStyleSheet(
            f"color:{theme.INK_MUTED}; font-weight:bold; letter-spacing:1.5px;"
        )
        dec.addWidget(dec_title)

        head = QHBoxLayout()
        head.setSpacing(10)
        self.tag = StatusTag("PASS")
        head.addWidget(self.tag)
        head.addStretch(1)
        self.lbl_recommendation = QLabel("ACCEPT")
        self.lbl_recommendation.setAlignment(
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
        )
        f = QFont(self.lbl_recommendation.font())
        f.setBold(True)
        f.setPointSize(f.pointSize() + 1)
        self.lbl_recommendation.setFont(f)
        head.addWidget(self.lbl_recommendation)
        dec.addLayout(head)

        self.lbl_main_issue = QLabel("")
        self.lbl_main_issue.setWordWrap(True)
        self.lbl_main_issue.setStyleSheet(
            f"background:{theme.SURFACE_ALT}; border:2px solid {theme.INK}; "
            f"padding:6px 10px;"
        )
        dec.addWidget(self.lbl_main_issue)

        body.addWidget(decision)

        # Filename + dim + size ----------------------------------------
        self.lbl_filename = label("—", bold=True, size=12)
        self.lbl_filename.setWordWrap(True)
        body.addWidget(self.lbl_filename)
        info_row = QHBoxLayout()
        info_row.setSpacing(8)
        self.lbl_dim = label("—", mono=True, soft=True, size=10)
        self.lbl_size = label("—", mono=True, soft=True, size=10)
        info_row.addWidget(self.lbl_dim)
        info_row.addWidget(self.lbl_size)
        info_row.addStretch(1)
        body.addLayout(info_row)

        # Metric grid --------------------------------------------------
        grid = QGridLayout()
        grid.setSpacing(8)
        self.m_score    = _StatBox("Quality Score")
        self.m_risk     = _StatBox("Reject Risk")
        self.m_conf     = _StatBox("Confidence")
        self.m_blur     = _StatBox("Blur (sharpness)")
        self.m_noise    = _StatBox("Noise")
        self.m_exposure = _StatBox("Exposure (μ)")
        self.m_artifact = _StatBox("JPEG Artifact")
        self.m_dyn      = _StatBox("Dynamic Range")
        grid.addWidget(self.m_score,    0, 0)
        grid.addWidget(self.m_risk,     0, 1)
        grid.addWidget(self.m_conf,     0, 2)
        grid.addWidget(self.m_blur,     1, 0)
        grid.addWidget(self.m_noise,    1, 1)
        grid.addWidget(self.m_exposure, 1, 2)
        grid.addWidget(self.m_artifact, 2, 0, 1, 2)
        grid.addWidget(self.m_dyn,      2, 2)
        body.addLayout(grid)

        # Summary / notes ----------------------------------------------
        summary_caption = QLabel("INSPECTION SUMMARY")
        summary_caption.setStyleSheet(
            f"color:{theme.INK_MUTED}; font-weight:bold; letter-spacing:1.5px;"
        )
        body.addWidget(summary_caption)
        self.lbl_summary = QLabel("")
        self.lbl_summary.setWordWrap(True)
        self.lbl_summary.setStyleSheet(f"color:{theme.INK};")
        body.addWidget(self.lbl_summary)

        # Issues -------------------------------------------------------
        issues_caption = QLabel("DETECTED ISSUES")
        issues_caption.setStyleSheet(
            f"color:{theme.INK_MUTED}; font-weight:bold; letter-spacing:1.5px;"
        )
        body.addWidget(issues_caption)

        self._issues_host = QFrame()
        self._issues_layout = QHBoxLayout(self._issues_host)
        self._issues_layout.setContentsMargins(0, 0, 0, 0)
        self._issues_layout.setSpacing(6)
        self._issues_layout.addStretch(1)
        body.addWidget(self._issues_host)

        body.addStretch(1)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def show_item(self, item: Optional[ScanItem]) -> None:
        if item is None:
            self._empty.setVisible(True)
            self._body.setVisible(False)
            return

        self._empty.setVisible(False)
        self._body.setVisible(True)

        st = item.status
        rec, bg, fg = _STATUS_RECOMMENDATION.get(
            st, ("ERROR", theme.INK, theme.YELLOW),
        )
        self.tag.set_status(st.value)
        self.lbl_recommendation.setText(rec)
        self.lbl_recommendation.setStyleSheet(
            f"background:{bg}; color:{fg}; "
            f"border:2px solid {theme.INK}; "
            f"padding:4px 10px; font-weight:900; letter-spacing:1.5px;"
        )

        self.lbl_filename.setText(item.path.name)

        m = item.metrics
        if m:
            self.lbl_dim.setText(f"{m.width} × {m.height}")
            self.lbl_size.setText(f"{m.file_kb:,.0f} KB")
        else:
            self.lbl_dim.setText("—")
            self.lbl_size.setText("—")

        # Headline issue (first issue, severity-priority).
        v = item.verdict
        primary_text = ""
        if item.error:
            primary_text = f"<b>Error:</b> {item.error}"
        elif v and v.issues:
            top = next(
                (i for i in v.issues if i.severity == "reject"),
                v.issues[0],
            )
            primary_text = f"<b>Main issue:</b> {top.label}"
        elif v:
            primary_text = "<b>No issues detected.</b>"
        self.lbl_main_issue.setText(primary_text)
        self.lbl_main_issue.setVisible(bool(primary_text))

        # Numeric stats.
        self.m_score.set_value(f"{item.score} / 100" if v else "—")
        # Synthesise a coarse risk + confidence from the verdict status,
        # so the top row mirrors the AI report layout for consistency.
        risk_txt = {
            Status.PASS:   "LOW",
            Status.REVIEW: "MED",
            Status.REJECT: "HIGH",
            Status.ERROR:  "—",
        }.get(st, "—")
        self.m_risk.set_value(risk_txt)
        conf_txt = "ERROR" if item.error else "RULE-BASED"
        self.m_conf.set_value(conf_txt)

        if m:
            self.m_blur.set_value(f"{m.blur:.0f}")
            self.m_noise.set_value(f"{m.noise:.1f}")
            self.m_exposure.set_value(f"{m.exposure_mean:.0f}")
            self.m_artifact.set_value(
                f"{m.artifact:.1f}" if m.is_jpeg else "n/a"
            )
            self.m_dyn.set_value(f"{m.dynamic_range:.0f}")
        else:
            for box in (
                self.m_blur, self.m_noise, self.m_exposure,
                self.m_artifact, self.m_dyn,
            ):
                box.set_value("—")

        # Summary copy.
        if item.error:
            summary = (
                f"This file could not be inspected: {item.error}. Verify the "
                "file is a supported image format and is readable."
            )
        elif v and v.issues:
            n_rej = sum(1 for i in v.issues if i.severity == "reject")
            n_rev = sum(1 for i in v.issues if i.severity != "reject")
            parts = []
            if n_rej:
                parts.append(f"{n_rej} reject-level issue(s)")
            if n_rev:
                parts.append(f"{n_rev} review-level issue(s)")
            summary = (
                f"Detected {' and '.join(parts)}. See the chips below for "
                "the full breakdown."
            )
        elif v:
            summary = (
                "No issues were detected by the technical scan. The image "
                "passes all gating rules in the active preset."
            )
        else:
            summary = ""
        self.lbl_summary.setText(summary)
        self.lbl_summary.setVisible(bool(summary))

        # Refresh issue chips.
        # Remove every chip but keep the trailing stretch.
        while self._issues_layout.count() > 1:
            child = self._issues_layout.takeAt(0)
            w = child.widget()
            if w is not None:
                w.deleteLater()
        if v and v.issues:
            for i in v.issues:
                chip = IssueChip(i.code, severity=i.severity)
                chip.setToolTip(i.label)
                self._issues_layout.insertWidget(
                    self._issues_layout.count() - 1, chip,
                )
        else:
            placeholder = QLabel(
                "no issues detected" if v and not item.error else "—",
            )
            placeholder.setStyleSheet(f"color:{theme.INK_MUTED};")
            self._issues_layout.insertWidget(
                self._issues_layout.count() - 1, placeholder,
            )
