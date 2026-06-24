"""
앱 테마 (Light / Dark / Auto-by-time) 관리 모듈.

- QApplication에 QPalette + 스타일시트(QSS) 적용
- matplotlib rcParams를 테마와 동기화 (차트 텍스트·축·배경색)
- '자동' 모드: 18:00~06:00 사이는 다크, 그 외 라이트 (간단·예측 가능)

다른 모듈에서:
    from .theme import ThemeManager
    tm = ThemeManager(app)
    tm.set_mode('dark' | 'light' | 'auto')
    tm.colors  # 현재 차트용 색 팔레트 dict
    tm.changed.connect(lambda: ...)  # 테마 바뀔 때 호출
"""
from __future__ import annotations

import base64
import datetime as dt

import matplotlib
from matplotlib import rcParams as _rc
from PySide6.QtCore import QObject, Signal, QTimer
from PySide6.QtGui import QColor, QPalette

from .palettes import LIGHT, DARK   # noqa: F401


def _arrow_data_url(direction: str, color: str) -> str:
    """라이트/다크에 따라 색이 바뀌는 작은 화살표 SVG를 base64로 인라인.

    direction: 'up' | 'down'
    """
    if direction == "up":
        path = "M2 9 L7 3 L12 9 Z"
    else:
        path = "M2 4 L7 10 L12 4 Z"
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="14" height="13" '
        f'viewBox="0 0 14 13"><path d="{path}" fill="{color}"/></svg>'
    )
    b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{b64}"


def _build_qss(c: dict, base_pt: int = 13) -> str:
    arrow_color = c['text']
    return f"""
    /* 한글이 섞인 환경에서 자연스러운 글꼴을 우선순위로 적용
       (앱 시작 시 fonts.register_fonts()가 번들 폰트를 등록한다) */
    * {{
        font-family: "NanumGothic";
        font-size: {base_pt}px;
    }}
    QWidget {{
        background-color: {c['bg']};
        color: {c['text']};
        font-size: {base_pt}px;
    }}
    /* 헤더바 */
    QFrame[role="headerbar"] {{
        background: {c['panel']}; border: 1px solid {c['border']};
        border-radius: 8px; padding: 4px;
    }}
    QLabel[role="appname"] {{ font-size: {base_pt + 3}px; font-weight: 700; color: {c['text']}; }}
    QToolButton[role="iconbtn"] {{
        background: {c['card']}; color: {c['text']};
        border: 1px solid {c['border']}; border-radius: 7px;
        padding: 4px 10px; min-width: 32px; min-height: 28px;
        font-size: {base_pt + 1}px; font-weight: 700;
    }}
    QToolButton[role="iconbtn"]:hover {{ background: {c['accent']}; color: white; border-color: {c['accent']}; }}
    QToolButton[role="iconbtn"]:pressed {{ background: {c['accent_hover']}; }}
    QToolButton[role="collapsebtn"] {{
        background: transparent; color: {c['text']}; border: none;
        padding: 6px 4px; font-weight: 700; text-align: left;
    }}
    QToolButton[role="collapsebtn"]:hover {{ color: {c['accent']}; }}

    /* StepperSpinBox 의 ± 버튼 */
    QPushButton[role="stepper"] {{
        background: {c['card']}; color: {c['text']};
        border: 1px solid {c['border']}; border-radius: 6px;
        padding: 0; min-height: 28px;
        font-size: {base_pt + 4}px; font-weight: 700;
    }}
    QPushButton[role="stepper"]:hover {{ background: {c['accent']}; color: white; border-color: {c['accent']}; }}
    QPushButton[role="stepper"]:pressed {{ background: {c['accent_hover']}; }}
    QFrame[role="card"], QGroupBox {{
        background: {c['panel']};
        border: 1px solid {c['border']};
        border-radius: 8px;
    }}
    QGroupBox {{
        margin-top: 12px;
        padding: 14px 12px 10px 12px;
        font-weight: 600;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 10px; padding: 0 6px;
        color: {c['muted']};
    }}
    QFrame[role="kpi"] {{
        background: {c['panel']};
        border: 1px solid {c['border']};
        border-radius: 8px;
        padding: 10px 14px;
    }}
    QLabel[role="kpi-label"] {{ color: {c['muted']}; font-size: {base_pt - 1}px; }}
    QLabel[role="kpi-value"] {{ color: {c['text']}; font-size: {base_pt + 9}px; font-weight: 700; }}
    QLabel[role="title"] {{ font-size: {base_pt + 3}px; font-weight: 700; color: {c['text']}; }}
    QLabel[role="muted"] {{ color: {c['muted']}; font-size: {max(7, base_pt - 1)}px; }}
    QLabel[role="credit"] {{
        color: {c['muted']}; font-size: {max(7, base_pt - 2)}px; padding-top: 6px;
        border-top: 1px solid {c['border']};
    }}

    QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox {{
        background: {c['panel']}; border: 1px solid {c['border']};
        border-radius: 6px; padding: 6px 10px; color: {c['text']};
        selection-background-color: {c['accent']};
        min-height: 22px;
    }}
    QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus {{
        border: 1px solid {c['accent']};
    }}
    /* 스핀박스 위/아래 화살표 — SVG 인라인으로 항상 또렷 */
    QDoubleSpinBox, QSpinBox {{ padding-right: 28px; }}
    QDoubleSpinBox::up-button, QSpinBox::up-button {{
        subcontrol-origin: border; subcontrol-position: top right;
        width: 26px; height: 50%; border-left: 1px solid {c['border']};
        border-top-right-radius: 6px;
        background: {c['card']};
    }}
    QDoubleSpinBox::down-button, QSpinBox::down-button {{
        subcontrol-origin: border; subcontrol-position: bottom right;
        width: 26px; height: 50%; border-left: 1px solid {c['border']};
        border-top: 1px solid {c['border']};
        border-bottom-right-radius: 6px;
        background: {c['card']};
    }}
    QDoubleSpinBox::up-button:hover, QSpinBox::up-button:hover,
    QDoubleSpinBox::down-button:hover, QSpinBox::down-button:hover {{
        background: {c['accent']};
    }}
    QDoubleSpinBox::up-arrow, QSpinBox::up-arrow {{
        image: url({_arrow_data_url('up', arrow_color)});
        width: 12px; height: 11px;
    }}
    QDoubleSpinBox::down-arrow, QSpinBox::down-arrow {{
        image: url({_arrow_data_url('down', arrow_color)});
        width: 12px; height: 11px;
    }}
    QDoubleSpinBox::up-arrow:hover, QSpinBox::up-arrow:hover {{
        image: url({_arrow_data_url('up', '#ffffff')});
    }}
    QDoubleSpinBox::down-arrow:hover, QSpinBox::down-arrow:hover {{
        image: url({_arrow_data_url('down', '#ffffff')});
    }}
    QComboBox::drop-down {{
        subcontrol-origin: padding; subcontrol-position: top right;
        width: 26px; border-left: 1px solid {c['border']};
        background: {c['card']};
    }}
    QComboBox::down-arrow {{
        image: url({_arrow_data_url('down', arrow_color)});
        width: 12px; height: 11px;
    }}
    QPushButton {{
        background: {c['panel']}; color: {c['text']};
        border: 1px solid {c['border']}; border-radius: 7px;
        padding: 6px 12px; min-height: 22px;
    }}
    QPushButton:hover {{ border-color: {c['accent']}; color: {c['accent']}; }}
    QPushButton[role="primary"] {{
        background: {c['accent']}; color: white; border: none; font-weight: 600;
    }}
    QPushButton[role="primary"]:hover {{ background: {c['accent_hover']}; }}
    QPushButton[role="primary-soft"] {{
        background: {c['card']}; color: {c['accent']};
        border: 1.5px dashed {c['accent']}; border-radius: 8px; font-weight: 600;
    }}
    QPushButton[role="primary-soft"]:hover {{ background: {c['accent']}; color: white; border-style: solid; }}

    QTabWidget::pane {{ border: 1px solid {c['border']}; border-radius: 8px; top: -1px; background: {c['panel']}; }}
    QTabBar::tab {{
        background: transparent; color: {c['muted']};
        padding: 7px 11px; border: 1px solid transparent;
        border-top-left-radius: 6px; border-top-right-radius: 6px;
        margin-right: 2px;
    }}
    QTabBar::tab:selected {{
        color: {c['accent']}; background: {c['panel']};
        border: 1px solid {c['border']}; border-bottom-color: {c['panel']};
        font-weight: 600;
    }}
    QTabBar::tab:hover:!selected {{ color: {c['text']}; }}

    QHeaderView::section {{
        background: {c['panel']}; color: {c['muted']};
        padding: 8px 10px; border: none; border-right: 1px solid {c['border']};
        border-bottom: 1px solid {c['border']}; font-weight: 600;
    }}
    QTableWidget {{
        background: {c['panel']}; alternate-background-color: {c['card']};
        gridline-color: {c['border']}; border: 1px solid {c['border']};
        border-radius: 8px; selection-background-color: {c['shade']};
        selection-color: {c['text']};
    }}
    QTableWidget::item {{ padding: 4px 8px; }}
    QStatusBar {{ background: {c['card']}; color: {c['muted']}; }}
    QMenuBar {{ background: {c['panel']}; color: {c['text']}; }}
    QMenuBar::item:selected {{ background: {c['card']}; }}
    QMenu {{ background: {c['panel']}; color: {c['text']}; border: 1px solid {c['border']}; }}
    QMenu::item:selected {{ background: {c['accent']}; color: white; }}

    QToolTip {{
        background: {c['panel']}; color: {c['text']};
        border: 1px solid {c['accent']}; border-radius: 6px;
        padding: 6px 10px;
    }}
    QSplitter::handle {{ background: {c['border']}; }}
    QSplitter::handle:horizontal {{ width: 6px; margin: 4px 0; border-radius: 3px; }}
    QSplitter::handle:vertical   {{ height: 6px; margin: 0 4px; border-radius: 3px; }}
    QSplitter::handle:hover {{ background: {c['accent']}; }}
    QScrollArea {{ border: none; }}
    QPlainTextEdit, QTextBrowser {{
        background: {c['panel']}; color: {c['text']};
        border: 1px solid {c['border']}; border-radius: 6px;
        padding: 10px;
        selection-background-color: {c['accent']};
    }}
    QCheckBox {{ color: {c['text']}; }}
    """


def _build_palette(c: dict) -> QPalette:
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(c['bg']))
    pal.setColor(QPalette.WindowText, QColor(c['text']))
    pal.setColor(QPalette.Base, QColor(c['panel']))
    pal.setColor(QPalette.AlternateBase, QColor(c['card']))
    pal.setColor(QPalette.Text, QColor(c['text']))
    pal.setColor(QPalette.Button, QColor(c['panel']))
    pal.setColor(QPalette.ButtonText, QColor(c['text']))
    pal.setColor(QPalette.Highlight, QColor(c['accent']))
    pal.setColor(QPalette.HighlightedText, QColor("white"))
    pal.setColor(QPalette.ToolTipBase, QColor(c['panel']))
    pal.setColor(QPalette.ToolTipText, QColor(c['text']))
    pal.setColor(QPalette.PlaceholderText, QColor(c['muted']))
    return pal


# ---------------------------------------------------------------------------
# 매니저
# ---------------------------------------------------------------------------

class ThemeManager(QObject):
    """애플리케이션 전역 테마 관리자.

    사용:
        tm = ThemeManager(app)
        tm.set_mode('auto')
        tm.changed.connect(window.refresh_charts)
    """
    changed = Signal(str)   # 새 테마 이름 ('light' | 'dark') 전달

    def __init__(self, app, base_pt: int = 13):
        super().__init__()
        self.app = app
        self._mode = "auto"
        self._effective = "light"
        self._base_pt = base_pt
        # auto 모드용 타이머 (5분마다 시각 확인)
        self._timer = QTimer(self)
        self._timer.setInterval(5 * 60 * 1000)
        self._timer.timeout.connect(self._tick)

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def effective(self) -> str:
        return self._effective

    @property
    def colors(self) -> dict:
        return DARK if self._effective == "dark" else LIGHT

    def set_mode(self, mode: str):
        if mode not in ("light", "dark", "auto"):
            mode = "auto"
        self._mode = mode
        if mode == "auto":
            self._timer.start()
        else:
            self._timer.stop()
        self._apply()

    def set_base_font_pt(self, pt: int):
        """줌 컨트롤 등에서 호출. QSS 전체를 새 폰트 크기로 다시 빌드해 적용."""
        pt = max(7, min(22, int(pt)))
        if pt == self._base_pt:
            return
        self._base_pt = pt
        self._apply()

    def _resolve_auto(self) -> str:
        # 18:00 이후 또는 06:00 이전이면 다크
        h = dt.datetime.now().hour
        return "dark" if (h >= 18 or h < 6) else "light"

    def _tick(self):
        if self._mode == "auto":
            target = self._resolve_auto()
            if target != self._effective:
                self._apply()

    def _apply(self):
        eff = self._mode if self._mode in ("light", "dark") else self._resolve_auto()
        self._effective = eff
        c = self.colors
        self.app.setPalette(_build_palette(c))
        self.app.setStyleSheet(_build_qss(c, self._base_pt))
        # QApplication 기본 폰트도 함께 업데이트해 다이얼로그/툴팁까지 반영
        try:
            f = self.app.font(); f.setPointSize(self._base_pt); self.app.setFont(f)
        except Exception:
            pass
        self._apply_matplotlib(c, self._base_pt)
        self.changed.emit(eff)

    @staticmethod
    def _apply_matplotlib(c: dict, base_pt: int = 13):
        _rc["axes.facecolor"] = c["chart_bg"]
        _rc["figure.facecolor"] = c["chart_bg"]
        _rc["savefig.facecolor"] = c["chart_bg"]
        _rc["axes.edgecolor"] = c["chart_grid"]
        _rc["axes.labelcolor"] = c["chart_text"]
        _rc["xtick.color"] = c["chart_text"]
        _rc["ytick.color"] = c["chart_text"]
        _rc["text.color"] = c["chart_text"]
        _rc["grid.color"] = c["chart_grid"]
        _rc["grid.linestyle"] = ":"
        _rc["grid.alpha"] = 0.45
        _rc["axes.titleweight"] = "bold"
        _rc["axes.spines.top"] = False
        _rc["axes.spines.right"] = False
        _rc["axes.unicode_minus"] = False
        # 줌과 동기화 (13pt = 100% 기준)
        scale = base_pt / 13.0
        _rc["font.size"] = max(8, 10 * scale)
        _rc["axes.titlesize"] = 12 * scale
        _rc["axes.labelsize"] = 10 * scale
        _rc["xtick.labelsize"] = 9 * scale
        _rc["ytick.labelsize"] = 9 * scale
        _rc["legend.fontsize"] = 9 * scale
