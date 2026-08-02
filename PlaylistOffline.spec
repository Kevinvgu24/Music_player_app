# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['APP\\music_player.py'],
    pathex=['APP'],
    binaries=[],
    datas=[('APP/style.qss', '.'), ('APP/app_icon.ico', '.'), ('APP/yt-dlp.exe', '.'), ('APP/fast_core.dll', '.')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='PlaylistOffline',
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
    icon=['APP\\app_icon.ico'],
)
