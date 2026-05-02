"""Brutalist toast notifications.

A `Toaster` is attached to a parent QWidget (typically the main window).
It stacks small `Toast` cards in the top-right corner. Each toast has a
hard border, an accent block on the left, a title and a body line, and
auto-dismisses after a timeout. Click anywhere on the toast to dismiss
it immediately.
"""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import (
    QEasingCurve, QEvent, QObject, QPropertyAnimation, QRect, QTimer, Qt
)
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QSizePolicy,
    QVBoxLayout, QWidget,
)

from . import theme


_LEVEL_COLORS = {
    "info": theme.COBALT,
    "ok":   theme.PASS_BG,
    "warn": theme.REVIEW_BG,
    "err":  theme.REJECT_BG,
}


class Toast(QFrame):
    """A single dismissible toast card."""

    def __init__(
        self,
        parent: QWidget,
        title: str,
        body: str = "",
        level: str = "info",
        duration_ms: int = 3500,
    ):
        super().__init__(parent)
        self.setObjectName("toast-card")
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setFixedWidth(340)

        accent = _LEVEL_COLORS.get(level, theme.COBALT)
        self.setStyleSheet(
            f"QFrame#toast-card {{"
            f"  background: {theme.SURFACE};"
            f"  border: 2px solid {theme.INK};"
            f"  border-left: 10px solid {accent};"
            f"}}"
            f"QLabel#toast-title {{"
            f"  color: {theme.INK};"
            f"  font-size: 11px;"
            f"  font-weight: 900;"
            f"  letter-spacing: 1.2px;"
            f"}}"
            f"QLabel#toast-body {{"
            f"  color: {theme.INK};"
            f"  font-size: 12px;"
            f"  font-weight: 600;"
            f"}}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        text = QVBoxLayout()
        text.setSpacing(2)
        self.lbl_title = QLabel(title.upper())
        self.lbl_title.setObjectName("toast-title")
        self.lbl_body = QLabel(body)
        self.lbl_body.setObjectName("toast-body")
        self.lbl_body.setWordWrap(True)
        text.addWidget(self.lbl_title)
        if body:
            text.addWidget(self.lbl_body)
        layout.addLayout(text, 1)

        # Fade-in
        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity)
        self._fade_in = QPropertyAnimation(self._opacity, b"opacity", self)
        self._fade_in.setDuration(160)
        self._fade_in.setStartValue(0.0)
        self._fade_in.setEndValue(1.0)
        self._fade_in.setEasingCurve(QEasingCurve.OutCubic)

        self._fade_out = QPropertyAnimation(self._opacity, b"opacity", self)
        self._fade_out.setDuration(220)
        self._fade_out.setStartValue(1.0)
        self._fade_out.setEndValue(0.0)
        self._fade_out.setEasingCurve(QEasingCurve.InCubic)
        self._fade_out.finished.connect(self.deleteLater)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.dismiss)
        self._timer.start(duration_ms)

    def show_in(self) -> None:
        self.show()
        self._fade_in.start()

    def dismiss(self) -> None:
        if self._fade_out.state() == QPropertyAnimation.Running:
            return
        self._timer.stop()
        self._fade_out.start()

    def mousePressEvent(self, e: QMouseEvent) -> None:  # noqa: N802
        self.dismiss()
        super().mousePressEvent(e)


class Toaster:
    """Stacks toasts in the top-right corner of `parent`."""

    MARGIN = 18
    GAP    = 8

    def __init__(self, parent: QWidget):
        self._parent = parent
        self._toasts: List[Toast] = []
        # Listen for parent resizes to re-layout toast stack
        parent.installEventFilter(_ResizeForwarder(parent, self))

    def show(self, title: str, body: str = "", level: str = "info",
             duration_ms: int = 3500) -> None:
        toast = Toast(self._parent, title=title, body=body, level=level,
                      duration_ms=duration_ms)
        toast.destroyed.connect(lambda _=None, t=toast: self._remove(t))
        self._toasts.append(toast)
        self._reflow()
        toast.show_in()

    # Convenience helpers ---------------------------------------------------
    def info(self, title: str, body: str = "") -> None:
        self.show(title, body, level="info")

    def ok(self, title: str, body: str = "") -> None:
        self.show(title, body, level="ok")

    def warn(self, title: str, body: str = "") -> None:
        self.show(title, body, level="warn", duration_ms=4500)

    def err(self, title: str, body: str = "") -> None:
        self.show(title, body, level="err", duration_ms=5500)

    # Internals -------------------------------------------------------------
    def _remove(self, toast: Toast) -> None:
        if toast in self._toasts:
            self._toasts.remove(toast)
        self._reflow()

    def _reflow(self) -> None:
        try:
            pw = self._parent.width()
            ph = self._parent.height()
        except RuntimeError:
            # Parent was already deleted (app shutdown) — nothing to do.
            return
        # Anchor at the bottom-right; stack newest toast on top.
        bottom_offset = self.MARGIN + 28  # leave room for status bar
        # Build sized list first
        sized = []
        for t in self._toasts:
            t.adjustSize()
            sized.append((t, t.width(), t.sizeHint().height()))
        y = ph - bottom_offset
        # iterate reversed so newest (last appended) sits highest
        for t, w, h in reversed(sized):
            y -= h
            x = pw - w - self.MARGIN
            t.setGeometry(QRect(x, y, w, h))
            t.raise_()
            y -= self.GAP


class _ResizeForwarder(QObject):
    """Forwards parent resizes/shows so the Toaster can re-anchor toasts."""

    def __init__(self, parent: QWidget, toaster: Toaster):
        super().__init__(parent)
        self._toaster = toaster

    def eventFilter(self, obj, e):  # noqa: N802
        if e.type() in (QEvent.Resize, QEvent.Show):
            self._toaster._reflow()
        return False
