# fatrocu.spec
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

block_cipher = None

a = Analysis(
    ['fatrocu_v16.py'],
    pathex=[],
    binaries=collect_dynamic_libs('PySide6'),
    datas=[
        *collect_data_files('playwright'),
        *collect_data_files('PySide6'),
    ],
    hiddenimports=[
        'playwright',
        'playwright.sync_api',
        'PySide6.QtWidgets',
        'PySide6.QtCore',
        'PySide6.QtGui',
        'pandas',
        'openpyxl',
        'pyperclip',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'scipy', 'PIL'],
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name='FATROCU_DB',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # GUI app, konsol penceresi çıkmasın
    icon='icon.ico',        # varsa
)

coll = COLLECT(
    exe, a.binaries, a.zipfiles, a.datas,
    strip=False,
    upx=True,
    name='FATROCU_DB',
)