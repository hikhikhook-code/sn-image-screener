# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for SN Image Screener (single-file Windows build)."""

import os
from pathlib import Path

import PySide6
from PyInstaller.utils.hooks import collect_data_files

block_cipher = None


# ---------------------------------------------------------------------------
# Qt platform plugins.
#
# The `qwindows.dll` platform plugin in `PySide6/plugins/platforms/`
# is what initialises the Qt event loop on Windows. PyInstaller's auto
# detection sometimes misses it, which causes:
#   "This application failed to start because no Qt platform plugin
#    could be initialised."
#
# We grab it (and a small set of plugin folders we actually use)
# explicitly. Everything else from PySide6 is left to PyInstaller's
# default hook so the binary stays small.
# ---------------------------------------------------------------------------

_pyside_root = Path(PySide6.__file__).parent
_plugin_root = _pyside_root / 'plugins'

_plugin_dirs = (
    'platforms',         # qwindows.dll — REQUIRED for Qt to start on Windows
    'styles',            # native windows style
    'imageformats',      # qjpeg, qpng, etc. — for the Inspector preview
    'iconengines',       # SVG icon engine if Qt needs it
    'platformthemes',    # Win 11 dark/light theme support
)

extra_datas = []
for sub in _plugin_dirs:
    src = _plugin_root / sub
    if src.is_dir():
        # Each .dll inside is shipped as a data file under
        # the destination "PySide6/plugins/<sub>" so Qt can find them.
        for f in src.iterdir():
            if f.is_file():
                extra_datas.append(
                    (str(f), os.path.join('PySide6', 'plugins', sub))
                )


a = Analysis(
    ['run.py'],
    pathex=['.'],
    binaries=[],
    datas=extra_datas + [
        ('sn_image_screener/assets/*.png', 'sn_image_screener/assets'),
        ('sn_image_screener/assets/*.ico', 'sn_image_screener/assets'),
    ],
    hiddenimports=[
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'cv2',
        'numpy',
        'PIL.Image',
        'skimage',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Keep the binary lean: SN Image Screener does not use these.
        'PySide6.Qt3DAnimation',
        'PySide6.Qt3DCore',
        'PySide6.Qt3DExtras',
        'PySide6.Qt3DInput',
        'PySide6.Qt3DLogic',
        'PySide6.Qt3DRender',
        'PySide6.QtBluetooth',
        'PySide6.QtCharts',
        'PySide6.QtDataVisualization',
        'PySide6.QtMultimedia',
        'PySide6.QtNfc',
        'PySide6.QtQml',
        'PySide6.QtQuick',
        'PySide6.QtQuick3D',
        'PySide6.QtRemoteObjects',
        'PySide6.QtSensors',
        'PySide6.QtSerialPort',
        'PySide6.QtTest',
        'PySide6.QtWebChannel',
        'PySide6.QtWebEngineCore',
        'PySide6.QtWebEngineWidgets',
        'PySide6.QtWebSockets',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='SN Image Screener',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='sn_image_screener/assets/logo.ico',
)
