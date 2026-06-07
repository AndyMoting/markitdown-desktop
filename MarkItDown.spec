# -*- mode: python ; coding: utf-8 -*-
"""
MarkItDown GUI — PyInstaller spec
入口由 build.ps1 按版本号动态替换，不要手动改 a.scripts。
"""

a = Analysis(
    ['v13_optimize.py'],                           # ← build.ps1 按版本替换此行
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'fitz', 'pymupdf',                        # PDF 引擎
        'sniffer', 'filetype',                     # magika→filetype shim
        'pdf_engine', 'doc_engine',                # 薄接口
        'aspose.words_foss',                       # .doc 转换
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'pypdfium2', 'pypdfium2_raw',              # 白占 7MB
        'magika', 'onnxruntime', 'flatbuffers', 'protobuf',  # filetype shim 替代, 省 ~42MB
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
    upx=True,                                      # UPX 可用时自动压缩
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
        'python312.dll',                           # UPX 压缩后可能加载失败
        'libcrypto-3.dll',
        'libssl-3.dll',
    ],
    name='MarkItDown',
)
