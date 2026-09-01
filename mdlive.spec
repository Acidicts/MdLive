# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = ['uvicorn.logging', 'uvicorn.loops', 'uvicorn.loops.auto',
                  'uvicorn.protocols', 'uvicorn.protocols.http',
                  'uvicorn.protocols.http.auto', 'uvicorn.protocols.websockets',
                  'uvicorn.protocols.websockets.auto', 'uvicorn.lifespan',
                  'uvicorn.lifespan.on']

for pkg in ['starlette', 'watchfiles', 'websockets']:
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

hiddenimports += ['uvicorn.protocols.websockets.websockets_impl']

a = Analysis(
    ['run.py'],
    pathex=['.'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='mdlive',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windows_traceback=False,
    argv_emulation=False,
)
