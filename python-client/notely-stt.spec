# python-client/notely-stt.spec
# PyInstaller spec for notely-stt (Windows, onefile)
from PyInstaller.utils.hooks import (
    collect_submodules,
    collect_dynamic_libs,
    collect_data_files,
)

hidden = []
hidden += collect_submodules('faster_whisper')
hidden += collect_submodules('ctranslate2')
hidden += collect_submodules('tokenizers')
hidden += collect_submodules('sentencepiece')

# --- Native binaries (.dll/.pyd 등) ---
binaries = []
binaries += collect_dynamic_libs('ctranslate2')
binaries += collect_dynamic_libs('sounddevice')

# --- Data files (토크나이저 리소스 등) ---
datas = []
datas += collect_data_files('tokenizers')
datas += collect_data_files('sentencepiece')
# (선택) faster_whisper 내부 리소스가 필요하면 다음 줄도 추가
# datas += collect_data_files('faster_whisper')

block_cipher = None

a = Analysis(
    ['python_client/__main__.py'],
    pathex=['.'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name='notely-stt',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
