"""Top command bar: brand block + action buttons + status indicator."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout,
    QWidget,
)

from . import theme


_STATUS_PALETTE = {
    "READY":     (theme.LIME,    theme.INK),
    "SCANNING":  (theme.ORANGE,  theme.INK),
    "PAUSED":    (theme.YELLOW,  theme.INK),
    "COMPLETED": (theme.COBALT,  "#FFFFFF"),
    "STOPPED":   (theme.INK,     theme.LIME),
}


class StatusIndicator(QLabel):
    """Heavy block showing READY / SCANNING / COMPLETED."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        f = self.font()
        f.setBold(True)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2)
        f.setPointSize(max(f.pointSize(), 10))
        self.setFont(f)
        self.setMinimumHeight(34)
        self.setMinimumWidth(130)
        self.set_status("READY")

    def set_status(self, status: str) -> None:
        status = status.upper()
        bg, fg = _STATUS_PALETTE.get(status, (theme.LIME, theme.INK))
        self.setText("● " + status)
        self.setStyleSheet(
            f"background:{bg}; color:{fg};"
            f"border:2px solid {theme.INK};"
            f"padding:4px 14px;"
            f"font-weight:900; letter-spacing:2px;"
        )


class CommandBar(QFrame):
    add_folder_clicked = Signal()
    add_files_clicked = Signal()
    start_clicked = Signal()
    stop_clicked = Signal()
    export_clicked = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("brutal-card")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(12)

        # Brand block ------------------------------------------------------
        brand = QVBoxLayout()
        brand.setSpacing(0)

        title = QLabel("SN IMAGE SCREENER")
        title.setObjectName("brand-title")
        brand.addWidget(title)

        sub = QLabel("LOCAL  ·  IMAGE  ·  QUALITY  ·  SCREENING")
        sub.setObjectName("brand-sub")
        brand.addWidget(sub)

        brand_wrap = QFrame()
        brand_wrap.setLayout(brand)
        layout.addWidget(brand_wrap)

        layout.addStretch(1)

        # Actions ----------------------------------------------------------
        self.btn_add_folder = QPushButton("Add Folder")
        self.btn_add_folder.clicked.connect(self.add_folder_clicked.emit)
        layout.addWidget(self.btn_add_folder)

        self.btn_add_files = QPushButton("Add Files")
        self.btn_add_files.clicked.connect(self.add_files_clicked.emit)
        layout.addWidget(self.btn_add_files)

        self.btn_start = QPushButton("Start Scan")
        self.btn_start.setObjectName("brutal-primary")
        self.btn_start.clicked.connect(self.start_clicked.emit)
        layout.addWidget(self.btn_start)

        self.btn_stop = QPushButton("Stop")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop_clicked.emit)
        layout.addWidget(self.btn_stop)

        self.btn_export = QPushButton("Export Results")
        self.btn_export.setObjectName("brutal-secondary")
        self.btn_export.clicked.connect(self.export_clicked.emit)
        layout.addWidget(self.btn_export)

        # Status -----------------------------------------------------------
        self.status = StatusIndicator()
        layout.addWidget(self.status)

    # Convenience pass-throughs -----------------------------------------

    def set_status(self, status: str) -> None:
        self.status.set_status(status)

    def set_scanning(self, scanning: bool) -> None:
        self.btn_start.setEnabled(not scanning)
        self.btn_stop.setEnabled(scanning)
