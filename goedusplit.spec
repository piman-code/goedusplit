# PyInstaller spec — macOS .app / Windows .exe 공통 빌드 정의.
# 다음 명령으로 빌드한다:
#   python -m PyInstaller goedusplit.spec   (Mac/Win 동일)
# 결과물:
#   - macOS:  dist/Goedu-Split.app
#   - Windows: dist/Goedu-Split/Goedu-Split.exe

# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path

ROOT = Path(globals().get("SPECPATH", ".")).resolve()
sys.path.insert(0, str(ROOT))

from app import __version__ as APP_VERSION

block_cipher = None
APP_NAME = "Goedu-Split"
APP_ICON_ICNS = ROOT / "assets" / "app_icon" / "goedusplit.icns"
APP_ICON_ICO = ROOT / "assets" / "app_icon" / "goedusplit.ico"
WINDOWS_ICON = str(APP_ICON_ICO) if sys.platform.startswith("win") and APP_ICON_ICO.exists() else None
MAC_ICON = str(APP_ICON_ICNS) if sys.platform == "darwin" and APP_ICON_ICNS.exists() else None

hiddenimports = [
    "matplotlib.backends.backend_qtagg",
    "matplotlib.backends.backend_pdf",
    "PySide6.QtSvg",
    "PySide6.QtWebChannel",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "pypdf",
]

a = Analysis(
    ["run.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("assets/fonts", "assets/fonts"),
        ("assets/app_icon", "assets/app_icon"),
        ("app/spliter_ox_web", "app/spliter_ox_web"),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["PyQt5", "PyQt6", "tkinter", "test"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# Third-party demo datasets are not runtime assets for this application.
a.datas = [entry for entry in a.datas if not entry[0].replace("\\", "/").startswith("matplotlib/mpl-data/sample_data/")]

# PyInstaller's PySide6 hooks copy nearly every Qt module. The app only uses Core/Gui/Widgets/Network,
# SVG/PrintSupport/OpenGL, QtQuick (QQuickWidget), WebEngine, WebChannel and QtTest (synthetic QA), so
# leave out Qt modules nothing imports. Matches path components: "Qt3DCore", "Qt63DCore.dll", "QtPdf.framework",
# "qml/QtQuick3D" ... but never "QtQuick" itself or the WebEngine/Qml pieces.
import re
_UNUSED_QT = re.compile(
    r"(?:^|/)(?:lib/)?Qt6?(?:3D|Quick3D|Charts|DataVisualization|Graphs|Location|Multimedia|Pdf|Sensors|"
    r"VirtualKeyboard|TextToSpeech|WebView|WebSockets|Scxml|RemoteObjects|SerialPort|SpatialAudio|StateMachine|"
    r"Sql|Bluetooth|Nfc|HttpServer|NetworkAuth|ShaderTools)[A-Za-z0-9]*"
    r"(?:\.framework|\.dll|\.dylib|\.pyd|\.abi3\.so|/|$)"
)
_UNUSED_QT_PLUGINS = ("libqpdf.", "qpdf.dll")   # image-format plugin that needs the removed QtPdf


def _unused_qt(dest):
    dest = dest.replace("\\", "/")
    return bool(_UNUSED_QT.search(dest)) or dest.rsplit("/", 1)[-1].startswith(_UNUSED_QT_PLUGINS)


a.binaries = [entry for entry in a.binaries if not _unused_qt(entry[0])]
a.datas = [entry for entry in a.datas if not _unused_qt(entry[0])]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False, bootloader_ignore_signals=False, strip=False,
    upx=False, upx_exclude=[],
    runtime_tmpdir=None,
    console=False,                       # GUI 앱이므로 콘솔 숨김
    disable_windowed_traceback=False,
    target_arch=None, codesign_identity=None, entitlements_file=None,
    icon=WINDOWS_ICON,
)

coll = COLLECT(
    exe, a.binaries, a.zipfiles, a.datas,
    strip=False, upx=False, upx_exclude=[],
    name=APP_NAME,
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name=f"{APP_NAME}.app",
        icon=MAC_ICON,
        bundle_identifier="com.goedu.split",
        info_plist={
            "NSHighResolutionCapable": True,
            "LSApplicationCategoryType": "public.app-category.education",
            "CFBundleShortVersionString": APP_VERSION,
            "CFBundleVersion": APP_VERSION,
            "NSRequiresAquaSystemAppearance": False,
        },
    )
