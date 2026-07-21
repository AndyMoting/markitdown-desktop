# -*- mode: python ; coding: utf-8 -*-
"""
InkDrop - PyInstaller spec
Entry script updated by build.ps1 per version. Do not edit a.scripts by hand.
"""

import site
from pathlib import Path

_aspose_resources = []
for _d in site.getsitepackages():
    _blank = Path(_d) / 'aspose' / 'words_foss' / 'docx_writer' / 'resources' / 'blank.docx'
    if _blank.exists():
        _aspose_resources.append(
            (str(_blank), 'aspose/words_foss/docx_writer/resources')
        )
        break

a = Analysis(
    ['inkdrop_gui.py'],              # <-- entry point for v2.0 GUI
    pathex=[],
    binaries=[],
    datas=_aspose_resources,
    hiddenimports=[
        'fitz', 'pymupdf',                        # PDF engine (PyMuPDF)
        'sniffer', 'filetype',                     # magika -> filetype shim
        'pdf_engine', 'doc_engine',                # thin wrappers
        'aspose.words_foss',                       # .doc conversion
        'PIL', 'PIL.Image', 'PIL.ImageTk',         # image gallery
        'tkinterdnd2',                             # drag-and-drop
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'pypdfium2', 'pypdfium2_raw',              # unused, saves ~7MB
        'magika', 'onnxruntime', 'flatbuffers', 'protobuf',  # filetype shim, saves ~42MB
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='InkDrop',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,                                      # UPX compresses if available
    console=False,                                 # --windowed
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[
        'python312.dll',                           # UPX may break loading
        'libcrypto-3.dll',
        'libssl-3.dll',
    ],
    name='InkDrop',
)
