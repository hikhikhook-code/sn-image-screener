#!/bin/bash
set -euxo pipefail
# Build "SN Image Screener.exe" inside a Wine + Windows Python 3.12 docker container.
# Output: dist/"SN Image Screener.exe" (single-file Windows executable).

cd /src
wine python.exe -m pip install --upgrade --no-warn-script-location pip wheel
wine python.exe -m pip install --no-warn-script-location \
    "PySide6>=6.6" "opencv-python>=4.8" "scikit-image>=0.22" \
    "numpy>=1.24,<2" "Pillow>=10" "Send2Trash>=1.8" \
    "pyinstaller==5.13.2"

# Build using the existing spec (PyInstaller 5.x — no isolated subprocess
# hook discovery, plays nice with Wine ucrtbase)
wine python.exe -m PyInstaller --clean --noconfirm sn_image_screener.spec

ls -la dist/
