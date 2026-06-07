# -*- mode: python ; coding: utf-8 -*-
"""
MarkItDown GUI - PyInstaller spec
Entry script updated by build.ps1 per version. Do not edit a.scripts by hand.
"""

a = Analysis(
    ['versions/v13_optimize.py'],         # <-- build.ps1 replaces this line per version
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'fitz', 'pymupdf',                        # PDF engine (PyMuPDF)
        'sniffer', 'filetype',                     # magika -> filetype shim
        'pdf_engine', 'doc_engine',                # thin wrappers
        'aspose.words_foss',                       # .doc conversion
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
    name='MarkItDown',
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
    name='MarkItDown',
)
