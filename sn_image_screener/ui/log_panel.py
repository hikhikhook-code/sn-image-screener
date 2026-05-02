"""Bottom activity log with Clear / Copy buttons and an internal scroll."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton,
    QSizePolicy, QVBoxLayout, QWidget,
)

from . import theme


class LogPanel(QFrame):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("brutal-card")
        self.setMinimumHeight(120)
        self.setMaximumHeight(220)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 6, 8, 8)
        outer.setSpacing(6)

        # Header --------------------------------------------------------
        hdr = QHBoxLayout()
        hdr.setSpacing(6)
        title = QLabel("ACTIVITY LOG")
        title.setObjectName("section-title")
        hdr.addWidget(title)
        hdr.addStretch(1)

        self.btn_copy = QPushButton("COPY LOG")
        self.btn_copy.setObjectName("brutal-flat")
        self.btn_copy.clicked.connect(self._copy_log)
        hdr.addWidget(self.btn_copy)

        self.btn_clear = QPushButton("CLEAR LOG")
        self.btn_clear.setObjectName("brutal-flat")
        self.btn_clear.clicked.connect(self._clear_log)
        hdr.addWidget(self.btn_clear)

        outer.addLayout(hdr)

        # Body ----------------------------------------------------------
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setLineWrapMode(QPlainTextEdit.NoWrap)
        outer.addWidget(self.text, 1)

    # ----------------------------------------------------------------- API

    def info(self, msg: str) -> None:
        self._append(msg, theme.LIME)

    def warn(self, msg: str) -> None:
        self._append(msg, theme.YELLOW)

    def err(self, msg: str) -> None:
        self._append(msg, theme.REJECT_BG)

    def ok(self, msg: str) -> None:
        self._append(msg, theme.PASS_BG)

    # ------------------------------------------------------------ helpers

    def _append(self, msg: str, color: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"<span style='color:{color}'>[{ts}]</span> {msg}"
        # appendHtml respects existing styling; we keep things minimal.
        self.text.appendHtml(line)
        self.text.moveCursor(QTextCursor.End)

    def _copy_log(self) -> None:
        QApplication.clipboard().setText(self.text.toPlainText())

    def _clear_log(self) -> None:
        self.text.clear()
