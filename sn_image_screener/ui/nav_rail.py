"""Collapsible left icon-rail navigation.

The rail replaces the older horizontal ``QTabWidget`` and provides a
brutalist-styled vertical navigation strip at the very left of the
window:

* SN logo at the top (always visible).
* A small collapse / expand toggle directly below the logo.
* One :class:`RailButton` per mode (``Technical Quality``,
  ``AI Anatomy Inspector``), each with a programmatically-drawn icon
  and a label that is hidden when the rail is collapsed.

When collapsed the rail is a narrow icon-only strip; hovering an icon
reveals a native tooltip with the mode name. When expanded each button
shows ``icon + label``. The active mode is highlighted with the same
brutalist orange-on-ink block used elsewhere in the app.

This widget contains *no* analysis or backend logic — it is purely
navigation chrome. The owner connects to :attr:`NavRail.mode_changed`
to swap the body of the window.
"""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import (
    QColor, QFont, QIcon, QPainter, QPen, QPixmap,
)
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
    QSpacerItem, QToolButton, QVBoxLayout, QWidget,
)

from . import theme
from .icons import logo_pixmap


# Width of the rail in each state. Both numbers are deliberate: collapsed
# leaves room for a 40px square icon button + 2px frame border, expanded
# is wide enough for "AI ANATOMY INSPECTOR" in the body font.
RAIL_WIDTH_COLLAPSED = 64
RAIL_WIDTH_EXPANDED = 232  # widened so labels never clip on default fonts

# Square size of every rail button (and therefore the painted icons).
BTN_SIZE = 44
ICON_PX = 22


# --- Icon drawing helpers --------------------------------------------------


def _stroked(pm: QPixmap, draw) -> QPixmap:
    """Run ``draw(painter)`` against a pre-zeroed transparent pixmap."""
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(QColor(theme.INK))
    pen.setWidth(2)
    pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    try:
        draw(p)
    finally:
        p.end()
    return pm


def technical_quality_icon(size: int = ICON_PX) -> QIcon:
    """Brutalist icon for the Technical Quality mode.

    A 2px-outlined square with three internal bars — a stylised
    quality-meter / histogram glyph.
    """
    pm = QPixmap(size, size)

    def draw(p: QPainter) -> None:
        # Outer square.
        p.drawRect(2, 2, size - 4, size - 4)
        # Three internal bars (left-anchored, increasing height) to
        # evoke a histogram / quality bar.
        bar_w = max(2, (size - 10) // 5)
        gap = max(1, bar_w // 2)
        x = 4
        heights = [size // 3, (size * 2) // 5, size // 2]
        base_y = size - 4
        for h in heights:
            p.fillRect(
                x, base_y - h, bar_w, h, QColor(theme.INK)
            )
            x += bar_w + gap

    return QIcon(_stroked(pm, draw))


def ai_anatomy_icon(size: int = ICON_PX) -> QIcon:
    """Brutalist icon for the AI Anatomy Inspector mode.

    A 2px-outlined circle with a crosshair through it — evokes an
    inspection target / lens.
    """
    pm = QPixmap(size, size)

    def draw(p: QPainter) -> None:
        margin = 2
        # Outer circle.
        p.drawEllipse(margin, margin, size - margin * 2, size - margin * 2)
        # Inner circle (small bullseye).
        inner = size // 4
        cx = size // 2
        cy = size // 2
        p.drawEllipse(cx - inner // 2, cy - inner // 2, inner, inner)
        # Crosshair lines extending past the circle.
        p.drawLine(cx, 0, cx, margin)
        p.drawLine(cx, size - margin, cx, size)
        p.drawLine(0, cy, margin, cy)
        p.drawLine(size - margin, cy, size, cy)

    return QIcon(_stroked(pm, draw))


def chevron_icon(direction: str, size: int = 16) -> QIcon:
    """Tiny chevron icon used by the collapse / expand toggle.

    ``direction`` is either ``"left"`` or ``"right"``.
    """
    pm = QPixmap(size, size)

    def draw(p: QPainter) -> None:
        pen = p.pen()
        pen.setWidth(2)
        p.setPen(pen)
        if direction == "left":
            p.drawLine(size - 4, 3, 4, size // 2)
            p.drawLine(4, size // 2, size - 4, size - 3)
        else:
            p.drawLine(4, 3, size - 4, size // 2)
            p.drawLine(size - 4, size // 2, 4, size - 3)

    return QIcon(_stroked(pm, draw))


# --- Widgets ----------------------------------------------------------------


class RailButton(QToolButton):
    """A single mode entry on the rail.

    Behaves as a checkable, exclusive toggle. In the collapsed rail it
    shows only its icon; in the expanded rail it shows ``icon + label``.
    The full label text is always available as a tooltip so the user
    can identify modes when the rail is collapsed.
    """

    def __init__(
        self,
        label: str,
        icon: QIcon,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._label = label
        self.setObjectName("rail-button")
        self.setCheckable(True)
        self.setAutoRaise(False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setIcon(icon)
        self.setIconSize(QSize(ICON_PX, ICON_PX))
        self.setText(label)
        self.setToolTip(label)
        # Label uppercase + bold matches the rest of the brutalist UI.
        f = self.font()
        f.setBold(True)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.2)
        self.setFont(f)
        self.set_collapsed(False)

    def set_collapsed(self, collapsed: bool) -> None:
        """Toggle between icon-only and icon + label layouts."""
        if collapsed:
            self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            self.setFixedSize(BTN_SIZE, BTN_SIZE)
            self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        else:
            self.setToolButtonStyle(
                Qt.ToolButtonStyle.ToolButtonTextBesideIcon
            )
            self.setMinimumSize(BTN_SIZE, BTN_SIZE)
            self.setMaximumHeight(BTN_SIZE)
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)


class NavRail(QFrame):
    """Vertical icon rail used as the primary mode switcher."""

    mode_changed = Signal(int)
    collapsed_changed = Signal(bool)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("nav-rail")
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        self._collapsed = False
        self._buttons: List[RailButton] = []
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._group.idClicked.connect(self._on_id_clicked)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 10, 8, 10)
        outer.setSpacing(8)

        # --- Logo block (always visible) ------------------------------
        self._logo = QLabel()
        self._logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._logo.setObjectName("rail-logo")
        self._logo.setPixmap(logo_pixmap(40))
        self._logo.setToolTip("SN Image Screener")
        outer.addWidget(self._logo)

        # --- Collapse / expand toggle ---------------------------------
        toggle_row = QHBoxLayout()
        toggle_row.setContentsMargins(0, 0, 0, 0)
        toggle_row.setSpacing(0)
        self._toggle = QToolButton()
        self._toggle.setObjectName("rail-toggle")
        self._toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle.setFixedHeight(28)
        self._toggle.setIcon(chevron_icon("left"))
        self._toggle.setIconSize(QSize(14, 14))
        self._toggle.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonIconOnly
        )
        self._toggle.setToolTip("Collapse navigation")
        self._toggle.clicked.connect(self.toggle)
        toggle_row.addWidget(self._toggle, 1)
        outer.addLayout(toggle_row)

        # Hairline divider between toggle and the mode list.
        sep = QFrame()
        sep.setObjectName("rail-divider")
        sep.setFrameShape(QFrame.Shape.NoFrame)
        sep.setFixedHeight(2)
        outer.addWidget(sep)

        # --- Mode list ------------------------------------------------
        self._modes_layout = QVBoxLayout()
        self._modes_layout.setContentsMargins(0, 0, 0, 0)
        self._modes_layout.setSpacing(8)
        outer.addLayout(self._modes_layout)

        outer.addItem(
            QSpacerItem(0, 0, QSizePolicy.Minimum, QSizePolicy.Expanding)
        )

        # Apply the initial (expanded) width.
        self._apply_width()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_mode(self, label: str, icon: QIcon) -> RailButton:
        """Append a new mode and return the underlying button."""
        btn = RailButton(label, icon, parent=self)
        btn.set_collapsed(self._collapsed)
        self._modes_layout.addWidget(btn)
        idx = len(self._buttons)
        self._group.addButton(btn, idx)
        self._buttons.append(btn)
        if idx == 0:
            btn.setChecked(True)
        return btn

    def set_active(self, index: int) -> None:
        """Programmatically select a mode without emitting ``mode_changed``."""
        if 0 <= index < len(self._buttons):
            self._buttons[index].setChecked(True)

    def is_collapsed(self) -> bool:
        return self._collapsed

    def set_collapsed(self, collapsed: bool) -> None:
        if collapsed == self._collapsed:
            return
        self._collapsed = collapsed
        for btn in self._buttons:
            btn.set_collapsed(collapsed)
        self._apply_width()
        self._toggle.setIcon(
            chevron_icon("right" if collapsed else "left")
        )
        self._toggle.setToolTip(
            "Expand navigation" if collapsed else "Collapse navigation"
        )
        self.collapsed_changed.emit(collapsed)

    def toggle(self) -> None:
        self.set_collapsed(not self._collapsed)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _apply_width(self) -> None:
        w = RAIL_WIDTH_COLLAPSED if self._collapsed else RAIL_WIDTH_EXPANDED
        self.setFixedWidth(w)

    def _on_id_clicked(self, idx: int) -> None:
        self.mode_changed.emit(idx)
