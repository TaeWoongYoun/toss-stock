# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 스펙 — cli.py 를 단일 실행파일(.exe)로 빌드.
# 빌드:  build_exe.bat  (또는  pyinstaller toss-stock.spec)
# 종목 데이터 JSON 3개를 exe 안에 함께 넣습니다. (stocks.py 가 _MEIPASS 에서 읽음)

a = Analysis(
    ['cli.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('krx_stocks.json', '.'),
        ('kr_etf.json', '.'),
        ('us_stocks.json', '.'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['textual', 'tkinter', 'test', 'unittest'],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='toss-stock',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    runtime_tmpdir=None,
    console=True,          # 터미널 앱이므로 콘솔 창 유지
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
