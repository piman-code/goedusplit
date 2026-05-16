"""
앱 시작 시 번들된 한글 폰트(Gowun Dodum, NanumGothic)를 Qt와 matplotlib에
등록한다. 시스템 폰트와 충돌하지 않도록 idempotent하게 동작한다.

폰트 위치:
- 개발 환경:        <project_root>/assets/fonts/*.ttf
- PyInstaller 번들: sys._MEIPASS/assets/fonts/*.ttf
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
from matplotlib import font_manager as fm


def font_dir() -> Path:
    """번들 환경/개발 환경 모두에서 동작하는 폰트 폴더 경로."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / "assets" / "fonts"
    return Path(__file__).resolve().parent.parent / "assets" / "fonts"


def register_fonts():
    """폰트 디렉토리의 모든 .ttf/.otf를 등록.

    - matplotlib: fm.fontManager.addfont
    - Qt: QFontDatabase.addApplicationFont
    Qt는 QApplication 생성 후에만 등록 가능하므로 main_window 진입 시점에 호출.
    """
    fdir = font_dir()
    if not fdir.exists():
        return []

    files = sorted([p for p in fdir.iterdir() if p.suffix.lower() in (".ttf", ".otf")])
    registered = []
    # matplotlib
    for p in files:
        try:
            fm.fontManager.addfont(str(p))
            registered.append(p.name)
        except Exception:
            pass
    matplotlib.rcParams["axes.unicode_minus"] = False

    # Qt (QApplication 생성 이후일 때만)
    try:
        from PySide6.QtCore import QCoreApplication
        from PySide6.QtGui import QFontDatabase
        if QCoreApplication.instance() is not None:
            for p in files:
                QFontDatabase.addApplicationFont(str(p))
    except ImportError:
        pass
    return registered


def pick_korean_font() -> str:
    """matplotlib에서 사용할 한글 폰트 이름 (우선순위 탐색)."""
    candidates = [
        "Gowun Dodum",
        "NanumGothic",
        "Nanum Gothic",
        "Pretendard",
        "Apple SD Gothic Neo",
        "AppleGothic",
        "Malgun Gothic",
        "맑은 고딕",
        "Noto Sans CJK KR",
        "DejaVu Sans",
    ]
    available = {f.name for f in fm.fontManager.ttflist}
    for c in candidates:
        if c in available:
            return c
    return matplotlib.rcParams["font.family"][0] if matplotlib.rcParams["font.family"] else "DejaVu Sans"
