"""Right-hand inspection report for the AI Anatomy Inspector.

Mirrors the contract returned by the AI prompt:

    * AI decision (PASS / REVIEW / FAIL / ERROR)
    * Screening result + recommended action
    * Quality score + reject risk + confidence
    * Primary issue + summary
    * Suspected defect areas list (clickable — emits :pyattr:`region_clicked`)
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QEvent, Signal, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QSizePolicy, QVBoxLayout, QWidget,
)

from ...services.ai.types import (
    AIStatus, AnatomyResult, ExposureIssue, ScreeningResult,
    Severity, TechSeverity, TechnicalQuality,
)
from ..widgets import EmptyState


_SCREENING_LABEL = {
    ScreeningResult.LIKELY_SAFE: "Likely Safe",
    ScreeningResult.NEEDS_HUMAN_REVIEW: "Needs Human Review",
    ScreeningResult.HIGH_RISK: "High Risk",
}

_STATUS_PALETTE = {
    AIStatus.PASS:   ("#6FE34D", "#0B2D00"),
    AIStatus.REVIEW: ("#FFB627", "#3A2200"),
    AIStatus.FAIL:   ("#FF3B30", "#FFFFFF"),
    AIStatus.ERROR:  ("#111111", "#FFC700"),
}


class ReportPanel(QWidget):
    """Inspection report widget for one :class:`AnatomyResult`."""

    region_clicked = Signal(str)   # emit region.id when a row is selected
    region_hovered = Signal(str)   # emit region.id on hover, "" on leave

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(320)
        self._result: Optional[AnatomyResult] = None
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        # Empty state — shown until ``set_result`` receives a real
        # AnatomyResult so the panel doesn't read as "broken with
        # dashes" before the AI scan has produced anything.
        self._empty = EmptyState(
            title="NO REPORT YET",
            body="Run a scan to see metrics and issues for the selected image.",
        )
        root.addWidget(self._empty)

        # All result-rendering widgets live inside ``_body`` so we can
        # hide them as a single block alongside the empty state.
        self._body = QFrame()
        self._body.setStyleSheet("background:transparent;")
        body = QVBoxLayout(self._body)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(10)
        root.addWidget(self._body, 1)

        # Status block
        self.lbl_status = QLabel("—")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        f = QFont(self.lbl_status.font())
        f.setBold(True)
        f.setPointSize(f.pointSize() + 8)
        self.lbl_status.setFont(f)
        self.lbl_status.setMinimumHeight(56)
        body.addWidget(self.lbl_status)

        # Decision row
        self.lbl_screening = QLabel("—")
        self.lbl_screening.setStyleSheet("color:#555555;")
        body.addWidget(self.lbl_screening)

        # Score + confidence row
        score_row = QHBoxLayout()
        self.lbl_score = self._stat_block("QUALITY")
        self.lbl_risk = self._stat_block("RISK")
        self.lbl_conf = self._stat_block("CONF")
        for w in (self.lbl_score, self.lbl_risk, self.lbl_conf):
            score_row.addWidget(w, 1)
        body.addLayout(score_row)

        # Primary issue / summary
        self.lbl_primary = QLabel("")
        self.lbl_primary.setWordWrap(True)
        self.lbl_primary.setStyleSheet(
            "background:#FFF4D6; border:2px solid #111111; padding:8px;"
        )
        body.addWidget(self.lbl_primary)

        self.lbl_summary = QLabel("")
        self.lbl_summary.setWordWrap(True)
        self.lbl_summary.setStyleSheet("color:#555555;")
        body.addWidget(self.lbl_summary)

        # Recommended action
        self.lbl_action = QLabel("")
        self.lbl_action.setStyleSheet(
            "background:#111111; color:#F4F1EA; padding:6px 10px;"
            "font-weight:bold; letter-spacing:1px;"
        )
        self.lbl_action.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body.addWidget(self.lbl_action)

        # Technical-quality side-check (AI-judged blur / noise /
        # exposure / artifact, with bokeh awareness). Hidden when the
        # AI didn't return any technical_quality block.
        self._tech_section = QFrame()
        self._tech_section.setStyleSheet("background:transparent;")
        tech_v = QVBoxLayout(self._tech_section)
        tech_v.setContentsMargins(0, 0, 0, 0)
        tech_v.setSpacing(4)
        tech_title = QLabel("TECHNICAL QUALITY (AI)")
        tech_title.setStyleSheet(
            "font-weight:bold; letter-spacing:1px; color:#111111;"
        )
        tech_v.addWidget(tech_title)
        tech_row = QHBoxLayout()
        tech_row.setSpacing(6)
        self._tech_blur = self._tech_pill("BLUR")
        self._tech_noise = self._tech_pill("NOISE")
        self._tech_exposure = self._tech_pill("EXPOSURE")
        self._tech_artifact = self._tech_pill("ARTIFACT")
        for w in (self._tech_blur, self._tech_noise,
                  self._tech_exposure, self._tech_artifact):
            tech_row.addWidget(w, 1)
        tech_v.addLayout(tech_row)
        self._tech_notes = QLabel("")
        self._tech_notes.setWordWrap(True)
        self._tech_notes.setStyleSheet("color:#555555; font-style:italic;")
        tech_v.addWidget(self._tech_notes)
        body.addWidget(self._tech_section)

        # Suspected defect list
        title = QLabel("SUSPECTED DEFECT AREAS")
        title.setStyleSheet("font-weight:bold; letter-spacing:1px;")
        body.addWidget(title)

        self.lst_defects = QListWidget()
        self.lst_defects.setStyleSheet(
            "QListWidget{border:2px solid #111111; background:#FFFFFF;}"
            "QListWidget::item{padding:6px; border-bottom:1px solid #C9C2B2;}"
            "QListWidget::item:selected{background:#D6EE2C; color:#111111;}"
        )
        self.lst_defects.itemClicked.connect(self._on_defect_clicked)
        # Hovering a row briefly highlights the corresponding marker in
        # the image preview, no click required.
        self.lst_defects.setMouseTracking(True)
        self.lst_defects.itemEntered.connect(self._on_defect_entered)
        self.lst_defects.viewport().installEventFilter(self)
        self.lst_defects.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding,
        )
        body.addWidget(self.lst_defects, 1)

        # Provider footer
        self.lbl_provider = QLabel("")
        self.lbl_provider.setStyleSheet("color:#8A8377; font-size:11px;")
        body.addWidget(self.lbl_provider)

        # Default: empty state visible, body hidden until a result
        # arrives via ``set_result``.
        self._body.setVisible(False)

    def _stat_block(self, title: str) -> QFrame:
        f = QFrame()
        f.setStyleSheet("border:2px solid #111111; background:#FFFFFF;")
        v = QVBoxLayout(f)
        v.setContentsMargins(6, 4, 6, 6)
        t = QLabel(title)
        t.setStyleSheet("color:#8A8377; font-size:10px; letter-spacing:1px;")
        v.addWidget(t)
        val = QLabel("—")
        font = QFont(val.font())
        font.setBold(True)
        font.setPointSize(font.pointSize() + 4)
        val.setFont(font)
        v.addWidget(val)
        f.value_label = val  # type: ignore[attr-defined]
        return f

    @staticmethod
    def _set_stat(block: QFrame, text: str) -> None:
        block.value_label.setText(text)  # type: ignore[attr-defined]

    @staticmethod
    def _tech_pill(title: str) -> QFrame:
        f = QFrame()
        f.setStyleSheet("border:2px solid #111111; background:#FFFFFF;")
        v = QVBoxLayout(f)
        v.setContentsMargins(6, 4, 6, 4)
        t = QLabel(title)
        t.setStyleSheet("color:#8A8377; font-size:10px; letter-spacing:1px;")
        v.addWidget(t)
        val = QLabel("—")
        font = QFont(val.font())
        font.setBold(True)
        val.setFont(font)
        val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(val)
        f.value_label = val  # type: ignore[attr-defined]
        return f

    @staticmethod
    def _set_tech_pill(pill: QFrame, text: str, *, severity: str) -> None:
        """Recolour a technical pill based on severity bucket.

        ``severity`` is one of ``"none" | "mild" | "heavy" | "ok"``;
        ``"ok"`` is the special bokeh-disengaja state.
        """
        palette = {
            "none":  ("#FFFFFF", "#111111", "#111111"),  # bg, fg, border
            "mild":  ("#FFF4D6", "#3A2200", "#FFB627"),
            "heavy": ("#FFE2E0", "#8A0F0A", "#FF3B30"),
            "ok":    ("#E9FBC4", "#0B2D00", "#5BC23A"),
        }
        bg, fg, border = palette.get(severity, palette["none"])
        pill.setStyleSheet(
            f"border:2px solid {border}; background:{bg};"
        )
        pill.value_label.setText(text)  # type: ignore[attr-defined]
        pill.value_label.setStyleSheet(  # type: ignore[attr-defined]
            f"color:{fg}; font-weight:bold;"
        )

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def set_result(self, result: Optional[AnatomyResult]) -> None:
        self._result = result
        if result is None:
            # Reset all the result-bound widgets so a future selection
            # never inherits stale data, then collapse the body in
            # favour of the empty-state card.
            self.lbl_status.setText("—")
            self.lbl_status.setStyleSheet("")
            self.lbl_screening.setText("—")
            self._set_stat(self.lbl_score, "—")
            self._set_stat(self.lbl_risk, "—")
            self._set_stat(self.lbl_conf, "—")
            self.lbl_primary.setText("")
            self.lbl_summary.setText("")
            self.lbl_action.setText("")
            self._tech_section.setVisible(False)
            self._tech_notes.setText("")
            self.lst_defects.clear()
            self.lbl_provider.setText("")
            self._body.setVisible(False)
            self._empty.setVisible(True)
            return

        self._empty.setVisible(False)
        self._body.setVisible(True)

        bg, fg = _STATUS_PALETTE[result.status]
        self.lbl_status.setText(result.status.value.upper())
        self.lbl_status.setStyleSheet(
            f"background:{bg}; color:{fg}; "
            f"border:2px solid #111111; padding:8px;"
        )

        self.lbl_screening.setText(
            _SCREENING_LABEL.get(result.screening_result, "—")
        )

        self._set_stat(self.lbl_score, f"{result.quality_score}")
        risk = (
            "HIGH" if result.quality_score < 65 else
            "MED"  if result.quality_score < 80 else
            "LOW"
        )
        self._set_stat(self.lbl_risk, risk)
        self._set_stat(self.lbl_conf, result.confidence.value.upper())

        if result.primary_physical_issue:
            self.lbl_primary.setText(
                f"<b>Primary issue:</b> {result.primary_physical_issue}"
            )
            self.lbl_primary.show()
        else:
            self.lbl_primary.hide()

        self.lbl_summary.setText(result.overall_summary or "")

        action = result.recommended_action.upper() if result.recommended_action else ""
        self.lbl_action.setText(action or "—")

        self._populate_technical(result.technical_quality)

        self.lst_defects.clear()
        if not result.defect_regions:
            empty = QListWidgetItem("No visible defect regions detected.")
            empty.setForeground(Qt.GlobalColor.gray)
            empty.setFlags(empty.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self.lst_defects.addItem(empty)
        else:
            for r in result.defect_regions:
                bullet = _SEV_BULLET.get(r.severity, "•")
                label = r.label or r.category.value.replace("_", " ").title()
                desc = r.description or label
                item = QListWidgetItem(
                    f"{bullet}  {label.upper()} — {desc}"
                )
                item.setData(Qt.ItemDataRole.UserRole, r.id)
                self.lst_defects.addItem(item)

        prov = result.provider_used or "—"
        klabel = result.key_label_used or "—"
        depth = result.scan_depth.value
        tiles = result.tile_count
        self.lbl_provider.setText(
            f"Provider: {prov} · key: {klabel} · "
            f"depth: {depth} ({tiles} tiles) · "
            f"{result.duration_seconds:.1f}s"
        )

    def _populate_technical(self, tq: TechnicalQuality) -> None:
        """Drive the four technical pills + notes line.

        Special-cases bokeh: when the AI flags blur as intentional
        depth-of-field, the BLUR pill is rendered as the green
        "BOKEH OK" state instead of an alarming red. That is the
        whole point of bringing this side-check inside the AI scan
        rather than running a separate rule-based pass.
        """
        # Hide the section entirely when the AI returned a default /
        # empty technical_quality block (legacy provider response).
        if not _has_any_tech_signal(tq):
            self._tech_section.setVisible(False)
            self._tech_notes.setText("")
            return
        self._tech_section.setVisible(True)

        # Blur — bokeh overrides "heavy" into a friendly "BOKEH OK"
        # so intentional shallow depth-of-field doesn't read like a
        # defect.
        if (
            tq.blur_severity is not TechSeverity.NONE
            and tq.bokeh_is_intentional
        ):
            self._set_tech_pill(self._tech_blur, "BOKEH OK", severity="ok")
        else:
            self._set_tech_pill(
                self._tech_blur,
                tq.blur_severity.value.upper(),
                severity=tq.blur_severity.value,
            )

        self._set_tech_pill(
            self._tech_noise,
            tq.noise_severity.value.upper(),
            severity=tq.noise_severity.value,
        )
        self._set_tech_pill(
            self._tech_artifact,
            tq.artifact_severity.value.upper(),
            severity=tq.artifact_severity.value,
        )

        exposure_severity = "none"
        if tq.exposure_issue is ExposureIssue.NONE:
            exposure_text = "NONE"
        elif tq.exposure_issue in (
            ExposureIssue.BLOWN_HIGHLIGHTS, ExposureIssue.CRUSHED_SHADOWS,
        ):
            exposure_text = tq.exposure_issue.value.replace("_", " ").upper()
            exposure_severity = "heavy"
        else:
            exposure_text = tq.exposure_issue.value.upper()
            exposure_severity = "mild"
        self._set_tech_pill(
            self._tech_exposure, exposure_text, severity=exposure_severity,
        )

        self._tech_notes.setText(tq.notes or "")
        self._tech_notes.setVisible(bool(tq.notes))

    def highlight(self, region_id: Optional[str]) -> None:
        for i in range(self.lst_defects.count()):
            item = self.lst_defects.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == region_id:
                self.lst_defects.setCurrentRow(i)
                return
        self.lst_defects.clearSelection()

    def _on_defect_clicked(self, item: QListWidgetItem) -> None:
        rid = item.data(Qt.ItemDataRole.UserRole)
        if rid:
            self.region_clicked.emit(str(rid))

    def _on_defect_entered(self, item: QListWidgetItem) -> None:
        rid = item.data(Qt.ItemDataRole.UserRole)
        if rid:
            self.region_hovered.emit(str(rid))

    def eventFilter(self, obj, event):  # type: ignore[override]
        # Clear the marker highlight when the cursor leaves the
        # defect-list viewport so the overlay doesn't stay frozen on
        # the last-hovered region.
        if obj is self.lst_defects.viewport() and event.type() == QEvent.Type.Leave:
            self.region_hovered.emit("")
        return super().eventFilter(obj, event)


_SEV_BULLET = {
    Severity.MINOR:    "·",
    Severity.MODERATE: "▲",
    Severity.MAJOR:    "■",
    Severity.CRITICAL: "✕",
}


def _has_any_tech_signal(tq: TechnicalQuality) -> bool:
    """Return True when the AI actually filled the technical_quality block.

    All-default / all-NONE responses (legacy provider, schema mismatch)
    keep the panel section hidden so the user doesn't see four empty
    "NONE" pills for every result.
    """
    if (
        tq.blur_severity is not TechSeverity.NONE
        or tq.noise_severity is not TechSeverity.NONE
        or tq.artifact_severity is not TechSeverity.NONE
        or tq.exposure_issue is not ExposureIssue.NONE
    ):
        return True
    return bool(tq.notes)
