"""Entry point for SN Image Screener."""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

from . import __app_name__, __version__
from .ui.icons import app_icon
from .ui.main_window import MainWindow


def _force_light_palette(app: QApplication) -> None:
    """Override Windows 11 / KDE dark mode so our brutalist palette stays
    readable. We pick the Fusion style so the QSS rules behave the same
    on every platform, then reset every role to a light value before
    the stylesheet is applied on top."""
    app.setStyle("Fusion")

    pal = QPalette()
    bg = QColor("#F4F1EA")
    surface = QColor("#FFFFFF")
    ink = QColor("#111111")
    soft = QColor("#555555")
    lime = QColor("#D6EE2C")

    pal.setColor(QPalette.ColorRole.Window, bg)
    pal.setColor(QPalette.ColorRole.WindowText, ink)
    pal.setColor(QPalette.ColorRole.Base, surface)
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor("#EAE6DC"))
    pal.setColor(QPalette.ColorRole.Text, ink)
    pal.setColor(QPalette.ColorRole.Button, surface)
    pal.setColor(QPalette.ColorRole.ButtonText, ink)
    pal.setColor(QPalette.ColorRole.Highlight, lime)
    pal.setColor(QPalette.ColorRole.HighlightedText, ink)
    pal.setColor(QPalette.ColorRole.PlaceholderText, soft)
    pal.setColor(QPalette.ColorRole.ToolTipBase, ink)
    pal.setColor(QPalette.ColorRole.ToolTipText, lime)
    app.setPalette(pal)


def main() -> int:
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName(__app_name__)
    app.setApplicationVersion(__version__)
    app.setOrganizationName("SN")
    app.setWindowIcon(app_icon())

    _force_light_palette(app)

    # Reasonable default UI font.
    f = QFont("Inter", 10)
    app.setFont(f)

    win = MainWindow()
    win.setWindowIcon(app_icon())
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
