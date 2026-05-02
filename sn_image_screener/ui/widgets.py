"""Reusable brutalist widgets: status tag, issue chip, collapsible group, etc."""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFontMetrics, QPainter, QPen, QColor, QPalette, QFont
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
    QVBoxLayout, QWidget,
)

from . import theme


# --- Status tag -------------------------------------------------------------


_STATUS_COLORS = {
    "PASS":   (theme.PASS_BG,   theme.PASS_FG),
    "REVIEW": (theme.REVIEW_BG, theme.REVIEW_FG),
    "REJECT": (theme.REJECT_BG, theme.REJECT_FG),
    "ERROR":  (theme.ERROR_BG,  theme.ERROR_FG),
}


class StatusTag(QLabel):
    """Hard-edged status block, e.g. PASS / REVIEW / REJECT / ERROR."""

    def __init__(self, status: str = "PASS", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        f = self.font()
        f.setBold(True)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.5)
        f.setPointSize(max(f.pointSize(), 10))
        self.setFont(f)
        self.setMinimumWidth(74)
        self.setMinimumHeight(24)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.set_status(status)

    def set_status(self, status: str) -> None:
        status = (status or "ERROR").upper()
        if status not in _STATUS_COLORS:
            status = "ERROR"
        bg, fg = _STATUS_COLORS[status]
        self.setText(status)
        self.setStyleSheet(
            f"background:{bg}; color:{fg};"
            f"border:2px solid {theme.INK};"
            f"padding:2px 10px;"
            f"font-weight:900; letter-spacing:1.5px;"
        )


class IssueChip(QLabel):
    """Small black chip used for issue codes (BLUR, NOISE, EXPOSURE...)."""

    def __init__(self, text: str, severity: str = "review", parent: Optional[QWidget] = None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignCenter)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        bg = theme.REJECT_BG if severity == "reject" else theme.CHIP_BG
        fg = theme.REJECT_FG if severity == "reject" else theme.CHIP_FG
        self.setStyleSheet(
            f"background:{bg}; color:{fg};"
            f"border:2px solid {theme.INK};"
            f"padding:2px 8px;"
            f"font-size:10px; font-weight:900; letter-spacing:1.5px;"
        )


# --- Section header ---------------------------------------------------------


class SectionHeader(QWidget):
    """Numbered section title used inside the control panel."""

    def __init__(self, num: str, title: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        n = QLabel(num)
        n.setObjectName("section-num")
        layout.addWidget(n)

        t = QLabel(title)
        t.setObjectName("section-title")
        layout.addWidget(t, 1)


class HardDivider(QFrame):
    """A 2px charcoal line used to separate sections."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("brutal-divider")
        self.setFrameShape(QFrame.NoFrame)
        self.setFixedHeight(2)


# --- Collapsible group ------------------------------------------------------


class CollapsibleGroup(QWidget):
    """A brutalist accordion section.

    The header is a heavy black bar with the section title; the body is
    a hard-bordered card that can be hidden/shown.
    """

    toggled = Signal(bool)

    def __init__(self, title: str, expanded: bool = True, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._title = title

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.toggle_btn = QPushButton(self._render_title(expanded))
        self.toggle_btn.setObjectName("group-toggle")
        self.toggle_btn.setCheckable(True)
        self.toggle_btn.setChecked(expanded)
        self.toggle_btn.setCursor(Qt.PointingHandCursor)
        self.toggle_btn.clicked.connect(self._on_toggled)
        outer.addWidget(self.toggle_btn)

        self.body = QFrame()
        self.body.setObjectName("group-body")
        body_l = QVBoxLayout(self.body)
        body_l.setContentsMargins(12, 12, 12, 12)
        body_l.setSpacing(8)
        outer.addWidget(self.body)
        self.body.setVisible(expanded)

    def _render_title(self, expanded: bool) -> str:
        arrow = "▾" if expanded else "▸"
        return f"  {arrow}   {self._title.upper()}"

    def _on_toggled(self, checked: bool) -> None:
        self.body.setVisible(checked)
        self.toggle_btn.setText(self._render_title(checked))
        self.toggled.emit(checked)

    def add(self, widget: QWidget) -> None:
        self.body.layout().addWidget(widget)

    def add_layout(self, layout) -> None:
        self.body.layout().addLayout(layout)


# --- Misc helpers -----------------------------------------------------------


def make_card(parent: Optional[QWidget] = None, alt: bool = False) -> QFrame:
    f = QFrame(parent)
    f.setObjectName("brutal-card-alt" if alt else "brutal-card")
    return f


def label(text: str, *, mono: bool = False, soft: bool = False, bold: bool = False, size: int = 11) -> QLabel:
    l = QLabel(text)
    f = l.font()
    f.setPointSize(size)
    f.setBold(bold)
    if mono:
        f.setFamily("JetBrains Mono")
        f.setStyleHint(QFont.Monospace)
    l.setFont(f)
    if soft:
        l.setStyleSheet(f"color:{theme.INK_SOFT};")
    return l
