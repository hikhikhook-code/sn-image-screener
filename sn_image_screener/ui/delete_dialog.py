"""Confirmation dialog for deleting REJECT (and optionally REVIEW) files.

Defaults to "Move to Recycle Bin" — recoverable. The user must explicitly
tick "Permanent delete" to bypass the recycle bin.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFrame, QLabel, QVBoxLayout, QWidget,
)

from . import theme
from ..core.deleter import human_size


class DeleteConfirmDialog(QDialog):
    """Asks the user which buckets to delete and how (trash vs permanent)."""

    def __init__(
        self,
        parent: Optional[QWidget],
        *,
        n_reject: int,
        size_reject: int,
        n_review: int,
        size_review: int,
        permanent_default: bool = False,
    ):
        super().__init__(parent)
        self.setWindowTitle("Delete files")
        self.setModal(True)
        self.setMinimumWidth(420)
        self.setStyleSheet(
            f"QDialog {{ background:{theme.SURFACE}; }}"
            f"QLabel  {{ color:{theme.INK}; }}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        title = QLabel("DELETE FILES")
        title.setStyleSheet(
            f"color:{theme.INK}; font-size:18px; font-weight:900; "
            f"letter-spacing:2px;"
        )
        layout.addWidget(title)

        line = QFrame()
        line.setObjectName("brutal-divider")
        line.setStyleSheet(f"background:{theme.INK}; min-height:2px;")
        layout.addWidget(line)

        info = QLabel(
            "Pick which buckets to remove. Originals will be deleted from disk."
        )
        info.setWordWrap(True)
        info.setStyleSheet(
            f"color:{theme.INK_MUTED}; font-size:11px; font-weight:600;"
        )
        layout.addWidget(info)

        # REJECT checkbox -----------------------------------------------
        self.chk_reject = QCheckBox(
            f"Include REJECT  \u00b7  {n_reject} file(s)  \u00b7  {human_size(size_reject)}"
        )
        self.chk_reject.setChecked(n_reject > 0)
        self.chk_reject.setEnabled(n_reject > 0)
        self.chk_reject.setStyleSheet(
            f"font-weight:800; color:{theme.INK};"
        )
        layout.addWidget(self.chk_reject)

        # REVIEW checkbox -----------------------------------------------
        self.chk_review = QCheckBox(
            f"Also delete REVIEW  \u00b7  {n_review} file(s)  \u00b7  {human_size(size_review)}"
        )
        self.chk_review.setChecked(False)
        self.chk_review.setEnabled(n_review > 0)
        self.chk_review.setStyleSheet(
            f"font-weight:800; color:{theme.INK};"
        )
        layout.addWidget(self.chk_review)

        # Permanent-delete toggle ---------------------------------------
        self.chk_permanent = QCheckBox(
            "Permanent delete (skip Recycle Bin)"
        )
        self.chk_permanent.setChecked(permanent_default)
        self.chk_permanent.setStyleSheet(
            f"color:{theme.REJECT_BG}; font-weight:800;"
        )
        layout.addWidget(self.chk_permanent)

        explain = QLabel(
            "Off (recommended): files are moved to your OS Recycle Bin and can "
            "be recovered. On: files are removed permanently and cannot be "
            "recovered without backup software."
        )
        explain.setWordWrap(True)
        explain.setStyleSheet(
            f"color:{theme.INK_MUTED}; font-size:10px; font-weight:500;"
        )
        layout.addWidget(explain)

        # Buttons --------------------------------------------------------
        buttons = QDialogButtonBox(
            QDialogButtonBox.Cancel | QDialogButtonBox.Ok,
            parent=self,
        )
        buttons.button(QDialogButtonBox.Ok).setText("DELETE")
        buttons.button(QDialogButtonBox.Ok).setObjectName("brutal-danger")
        buttons.button(QDialogButtonBox.Cancel).setText("CANCEL")
        buttons.button(QDialogButtonBox.Cancel).setObjectName("brutal-ghost")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ---------------------------------------------------------------- API
    @property
    def include_reject(self) -> bool:
        return self.chk_reject.isChecked() and self.chk_reject.isEnabled()

    @property
    def include_review(self) -> bool:
        return self.chk_review.isChecked() and self.chk_review.isEnabled()

    @property
    def permanent(self) -> bool:
        return self.chk_permanent.isChecked()
