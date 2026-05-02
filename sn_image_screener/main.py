"""Entry point for SN Image Screener."""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from . import __app_name__, __version__
from .ui.icons import app_icon
from .ui.main_window import MainWindow


def main() -> int:
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName(__app_name__)
    app.setApplicationVersion(__version__)
    app.setOrganizationName("SN")
    app.setWindowIcon(app_icon())

    # Reasonable default UI font.
    f = QFont("Inter", 10)
    app.setFont(f)

    win = MainWindow()
    win.setWindowIcon(app_icon())
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
