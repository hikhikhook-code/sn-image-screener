"""Brutalism-inspired theme for SN Image Screener.

Design notes:
* Warm off-white base, charcoal text and 2px hard borders.
* Vivid accent blocks used sparingly for action surfaces and status tags.
* Flat surfaces, no gradients, square or 2px-rounded corners.
* Large bold headings, compact monospaced numbers.
"""

from __future__ import annotations

# --- Palette ---------------------------------------------------------------

BG          = "#F4F1EA"   # warm cream base
SURFACE     = "#FFFFFF"   # cards / panels
SURFACE_ALT = "#EAE6DC"   # secondary surface (sidebar, log)
INK         = "#111111"   # charcoal text + borders
INK_SOFT    = "#555555"   # secondary text
INK_MUTED   = "#8A8377"   # tertiary / placeholder
LINE        = "#111111"   # primary border (same as INK for strong frames)
LINE_SOFT   = "#C9C2B2"   # subtle divider

# Accent blocks
ORANGE      = "#FF4D2E"   # primary action
LIME        = "#D6EE2C"   # secondary action / highlight
COBALT      = "#1F36C7"   # info / link
YELLOW      = "#FFC700"   # warning
INK_FILL    = "#111111"   # inverted action

# Status palette (for tags)
PASS_BG     = "#6FE34D"
PASS_FG     = "#0B2D00"
REVIEW_BG   = "#FFB627"
REVIEW_FG   = "#3A2200"
REJECT_BG   = "#FF3B30"
REJECT_FG   = "#FFFFFF"
ERROR_BG   = "#111111"
ERROR_FG   = "#FFC700"

# Issue chip palette
CHIP_BG     = "#111111"
CHIP_FG     = "#F4F1EA"

# --- Typography ------------------------------------------------------------

FAMILY      = "Inter, 'Segoe UI', 'Helvetica Neue', Arial, sans-serif"
MONO        = "'JetBrains Mono', 'Consolas', 'Menlo', monospace"


# --- Stylesheet ------------------------------------------------------------

QSS = f"""
* {{
    color: {INK};
    font-family: {FAMILY};
}}

QMainWindow, QWidget#root {{
    background: {BG};
}}

/* Dialogs & message boxes — keep them on the light palette so user
   forms (API keys, delete confirmation, etc.) stay readable when the
   host OS is in dark mode. */
QDialog, QMessageBox {{
    background: {BG};
    color: {INK};
}}

QDialog QLabel, QMessageBox QLabel {{
    color: {INK};
}}

QFrame#brutal-card {{
    background: {SURFACE};
    border: 2px solid {INK};
}}

QFrame#brutal-card-alt {{
    background: {SURFACE_ALT};
    border: 2px solid {INK};
}}

QFrame#brutal-divider {{
    background: {INK};
    min-height: 2px;
    max-height: 2px;
}}

/* Left control panel (root + sticky footer) ----------------------------- */
QFrame#control-panel-root {{
    background: {SURFACE_ALT};
    border-right: 2px solid {INK};
}}

QFrame#control-sticky {{
    /* Cream sticky strip so the lime primary START SCAN button (and
       the compact "no source added" prompt) stand out against it. */
    background: {SURFACE_ALT};
    border-top: 2px solid {INK};
}}

QLabel#scroll-hint {{
    color: {INK};
    font-size: 10px;
    font-weight: 800;
    letter-spacing: 1px;
    background: transparent;
}}

QLabel#field-hint {{
    color: {INK_MUTED};
    font-size: 10px;
    font-weight: 500;
    background: transparent;
    margin-left: 2px;
}}

QLabel#brand-title {{
    font-size: 22px;
    font-weight: 900;
    letter-spacing: 1px;
    color: {INK};
}}

QLabel#brand-sub {{
    font-size: 11px;
    font-weight: 700;
    color: {INK_SOFT};
    letter-spacing: 0.5px;
}}

QLabel#section-title {{
    font-size: 11px;
    font-weight: 900;
    letter-spacing: 2px;
    color: {INK};
    background: transparent;
}}

QLabel#section-num {{
    font-size: 11px;
    font-weight: 900;
    color: {SURFACE};
    background: {INK};
    padding: 2px 6px;
    letter-spacing: 1px;
}}

QLabel#metric-value {{
    font-family: {MONO};
    font-size: 16px;
    font-weight: 700;
    color: {INK};
}}

QLabel#metric-label {{
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1.2px;
    color: {INK_SOFT};
}}

/* Buttons --------------------------------------------------------------- */

QPushButton {{
    background: {SURFACE};
    color: {INK};
    border: 2px solid {INK};
    padding: 7px 14px;
    font-size: 12px;
    font-weight: 800;
    letter-spacing: 1.2px;
    text-transform: uppercase;
}}

QPushButton:hover {{
    background: {INK};
    color: {SURFACE};
}}

QPushButton:pressed {{
    background: {INK};
    color: {LIME};
}}

QPushButton:disabled {{
    background: {SURFACE_ALT};
    color: {INK_MUTED};
    border-color: {INK_MUTED};
}}

QPushButton#brutal-primary {{
    /* Lime primary — orange/red are reserved for warnings + reject. */
    background: {LIME};
    color: {INK};
}}
QPushButton#brutal-primary:hover {{
    background: {INK};
    color: {LIME};
}}
QPushButton#brutal-primary:disabled {{
    background: {SURFACE_ALT};
    color: {INK_MUTED};
    border-color: {INK_MUTED};
}}

QPushButton#brutal-secondary {{
    /* Neutral filled secondary — quiet enough not to compete with the
       lime primary, but still hard-bordered + bold for the brutalist
       look. Used for things like "Add Folder" / "Add Files" mini
       buttons in empty states. */
    background: {SURFACE};
    color: {INK};
}}
QPushButton#brutal-secondary:hover {{
    background: {INK};
    color: {LIME};
}}
QPushButton#brutal-secondary:disabled {{
    background: {SURFACE_ALT};
    color: {INK_MUTED};
    border-color: {INK_MUTED};
}}

QPushButton#brutal-danger {{
    background: {REJECT_BG};
    color: #FFFFFF;
}}
QPushButton#brutal-danger:hover {{
    background: {INK};
    color: {REJECT_BG};
}}
QPushButton#brutal-danger:disabled {{
    background: {SURFACE_ALT};
    color: {INK_MUTED};
    border-color: {INK_MUTED};
}}

QPushButton#brutal-ghost {{
    background: transparent;
    border: 2px solid {INK};
    color: {INK};
}}

QPushButton#brutal-flat {{
    background: transparent;
    border: 0px;
    padding: 4px 6px;
    color: {INK_SOFT};
    text-transform: none;
    letter-spacing: 0.5px;
    font-weight: 700;
}}
QPushButton#brutal-flat:hover {{
    color: {INK};
    background: {SURFACE_ALT};
}}

QPushButton#group-toggle {{
    text-align: left;
    background: {INK};
    color: {SURFACE};
    border: 2px solid {INK};
    padding: 8px 12px;
    font-size: 11px;
    font-weight: 900;
    letter-spacing: 2px;
}}
QPushButton#group-toggle:hover {{
    background: {ORANGE};
    color: {INK};
}}
QPushButton#group-toggle:checked {{
    background: {INK};
    color: {LIME};
}}

/* Navigation rail -------------------------------------------------------- */

QFrame#nav-rail {{
    background: {SURFACE_ALT};
    border-right: 2px solid {INK};
}}

QFrame#rail-divider {{
    background: {INK};
    border: 0;
    min-height: 2px;
    max-height: 2px;
}}

QLabel#rail-logo {{
    background: transparent;
    padding: 4px 0px;
}}

QToolButton#rail-toggle {{
    background: {SURFACE};
    color: {INK};
    border: 2px solid {INK};
    padding: 2px 6px;
    font-weight: 900;
}}
QToolButton#rail-toggle:hover {{
    background: {INK};
    color: {LIME};
}}

QToolButton#rail-button {{
    background: {SURFACE};
    color: {INK};
    border: 2px solid {INK};
    padding: 6px 10px;
    font-size: 11px;
    font-weight: 900;
    letter-spacing: 1px;
    text-align: left;
}}
QToolButton#rail-button:hover {{
    background: {INK};
    color: {LIME};
}}
QToolButton#rail-button:checked {{
    /* Active mode uses lime + ink so it does not read as a warning.
       Orange/red are reserved for reject / error / warning states. */
    background: {LIME};
    color: {INK};
    border: 2px solid {INK};
}}
QToolButton#rail-button:checked:hover {{
    background: {LIME};
    color: {INK};
}}

/* Input fields ---------------------------------------------------------- */

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background-color: {SURFACE};
    color: {INK};
    border: 2px solid {INK};
    padding: 5px 8px;
    selection-background-color: {LIME};
    selection-color: {INK};
    font-family: {MONO};
    font-size: 12px;
}}

QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled,
QComboBox:disabled {{
    background-color: {SURFACE_ALT};
    color: {INK_MUTED};
}}

QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    background-color: {LIME};
    color: {INK};
}}

QComboBox::drop-down {{
    background: {INK};
    width: 22px;
    border: none;
}}

QComboBox::down-arrow {{
    image: none;
    width: 0;
    height: 0;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid {SURFACE};
}}

QComboBox QAbstractItemView {{
    background: {SURFACE};
    border: 2px solid {INK};
    selection-background-color: {LIME};
    selection-color: {INK};
    outline: 0;
}}

QCheckBox {{
    spacing: 8px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.5px;
}}

QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 2px solid {INK};
    background: {SURFACE};
}}
QCheckBox::indicator:checked {{
    background: {INK};
    image: none;
}}

/* Table ----------------------------------------------------------------- */

QTableWidget {{
    background: {SURFACE};
    border: 2px solid {INK};
    gridline-color: {LINE_SOFT};
    selection-background-color: {LIME};
    selection-color: {INK};
    alternate-background-color: {SURFACE_ALT};
    font-size: 12px;
}}

QHeaderView::section {{
    background: {INK};
    color: {SURFACE};
    border: 0;
    border-right: 1px solid {SURFACE_ALT};
    padding: 7px 10px;
    font-size: 10px;
    font-weight: 900;
    letter-spacing: 2px;
    text-transform: uppercase;
}}

QHeaderView::section:last {{
    border-right: 0;
}}

QTableWidget::item {{
    padding: 6px 8px;
    border-bottom: 1px solid {LINE_SOFT};
    color: {INK};
    background-color: {SURFACE};
}}

QTableWidget::item:selected {{
    background-color: {LIME};
    color: {INK};
}}

/* Scrollbars ------------------------------------------------------------ */

QScrollBar:vertical {{
    background: {SURFACE_ALT};
    width: 16px;
    border-left: 2px solid {INK};
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {INK};
    min-height: 36px;
    border: 2px solid {INK};
    margin: 2px;
}}
QScrollBar::handle:vertical:hover {{
    background: {COBALT};
    border: 2px solid {INK};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

/* High-contrast scroll for the left control panel ----------------------- */
QScrollArea#control-scroll > QScrollBar:vertical {{
    background: {LIME};
    width: 18px;
    border-left: 2px solid {INK};
}}
QScrollArea#control-scroll > QScrollBar::handle:vertical {{
    background: {INK};
    min-height: 50px;
    border: 2px solid {INK};
    margin: 2px;
}}
QScrollArea#control-scroll > QScrollBar::handle:vertical:hover {{
    background: {ORANGE};
}}

QScrollBar:horizontal {{
    background: {SURFACE_ALT};
    height: 12px;
    border-top: 2px solid {INK};
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {INK};
    min-width: 30px;
    border: 2px solid {INK};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

/* Splitter -------------------------------------------------------------- */

QSplitter::handle {{
    background: {INK};
}}

QSplitter::handle:horizontal {{
    width: 2px;
}}

QSplitter::handle:vertical {{
    height: 2px;
}}

/* Progress -------------------------------------------------------------- */

QProgressBar {{
    background: {SURFACE};
    border: 2px solid {INK};
    text-align: center;
    color: {INK};
    font-weight: 800;
    font-size: 10px;
    letter-spacing: 1.5px;
    padding: 0;
    height: 16px;
}}
QProgressBar::chunk {{
    background: {ORANGE};
}}

/* Plain text ------------------------------------------------------------ */

QPlainTextEdit, QTextEdit {{
    background: {INK};
    color: {LIME};
    border: 2px solid {INK};
    font-family: {MONO};
    font-size: 11px;
    padding: 6px;
    selection-background-color: {LIME};
    selection-color: {INK};
}}

/* Tooltip --------------------------------------------------------------- */

QToolTip {{
    background: {INK};
    color: {LIME};
    border: 2px solid {INK};
    padding: 4px 8px;
    font-weight: 700;
}}

/* Status bar ------------------------------------------------------------ */

QStatusBar {{
    background: {SURFACE_ALT};
    border-top: 2px solid {INK};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.5px;
}}

/* Group panel ---------------------------------------------------------- */

QFrame#group-body {{
    background: {SURFACE};
    border: 2px solid {INK};
    border-top: 0;
}}
"""
