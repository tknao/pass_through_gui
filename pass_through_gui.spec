# -*- mode: python ; coding: utf-8 -*-
#
# pass_through_gui — onefile ビルド用 spec
#   ffplay.exe / ffmpeg.exe を exe 内部に同梱し、依存 DLL は PyInstaller の
#   依存解析が自動収集する（avformat/avcodec/avdevice 等）。
#   ffmpeg の置き場所は環境変数 FFMPEG_BIN で指定できる（既定: C:/ffmpeg/bin）。
#
# 使い方（このフォルダで）:
#   python -m PyInstaller --noconfirm --clean pass_through_gui.spec
# 出力: dist/pass_through_gui.exe
#
# ※ 同梱する ffmpeg のライセンスについては THIRD_PARTY_NOTICES.md を参照。
#
import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

FFMPEG_BIN = os.environ.get("FFMPEG_BIN", "C:/ffmpeg/bin")

datas = [
    (os.path.join(FFMPEG_BIN, 'ffplay.exe'), 'ffmpeg'),
    (os.path.join(FFMPEG_BIN, 'ffmpeg.exe'), 'ffmpeg'),
]

a = Analysis(
    ['pass_through_gui.py'],
    pathex=[],
    binaries=[],
    datas=datas,
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
    name='pass_through_gui',
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
)
