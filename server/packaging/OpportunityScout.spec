# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

SPEC_DIR = Path(SPECPATH)
SERVER_ROOT = SPEC_DIR.parent
REPO_ROOT = SERVER_ROOT.parent
WEB_DIST = REPO_ROOT / "web" / "dist"
ICON = SPEC_DIR / "OpportunityScout.icns"

if not (WEB_DIST / "index.html").is_file():
    raise SystemExit(
        f"Frontend build not found at {WEB_DIST}. Run `npm --prefix ../web run build` first."
    )

hiddenimports = []
for package in (
    "uvicorn",
    "apscheduler",
    "amazon_creatorsapi",
    "creatorsapi_python_sdk",
    "pytrends",
):
    hiddenimports += collect_submodules(package)

datas = [(str(WEB_DIST), "app/static/web")]

a = Analysis(
    [str(SERVER_ROOT / "app" / "desktop.py")],
    pathex=[str(SERVER_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "pytest",
        "_pytest",
        "IPython",
        "matplotlib",
        "scipy",
        "tkinter",
        "PyQt5",
        "PySide6",
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
    name="Opportunity Scout",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
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
    upx=False,
    upx_exclude=[],
    name="Opportunity Scout",
)

app = BUNDLE(
    coll,
    name="Opportunity Scout.app",
    icon=str(ICON) if ICON.is_file() else None,
    bundle_identifier="com.opportunityscout.desktop",
    info_plist={
        "CFBundleDisplayName": "Opportunity Scout",
        "CFBundleShortVersionString": "0.1.0",
        "CFBundleVersion": "1",
        "LSMinimumSystemVersion": "12.0",
        "LSApplicationCategoryType": "public.app-category.productivity",
        "NSHighResolutionCapable": True,
        "NSRequiresAquaSystemAppearance": False,
    },
)
