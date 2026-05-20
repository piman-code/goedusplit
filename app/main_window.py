"""
PySide6 기반 메인 윈도우 (KICE Shiny 웹앱 2.1.2 화면 구조에 맞춰 재구성).

화면 구조:
- 좌측 사이드바: 입력 파일, 분할점수, 옵션, 분석 실행
- 우측 탭: Data | 전체 성취도 | 문항 분석 | 답지반응분포 | 성취기준 분석 | 도움말

데이터는 모두 로컬에서만 처리되며, 외부로 전송되지 않는다.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import queue
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import traceback
import zipfile
from datetime import datetime
from pathlib import Path
import xml.etree.ElementTree as ET

from PySide6.QtCore import Qt, QSettings, QUrl, QSize, QTimer
from PySide6.QtGui import QAction, QActionGroup, QColor, QBrush, QFont, QKeySequence, QShortcut, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel,
    QPushButton, QLineEdit, QFileDialog, QFrame, QTabWidget, QGroupBox,
    QFormLayout, QDoubleSpinBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QSplitter, QComboBox, QSizePolicy, QCheckBox, QToolButton,
    QScrollArea, QAbstractItemView, QGridLayout, QTextBrowser, QPlainTextEdit, QInputDialog
)

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas

from .data_loader import load_exam, apply_perform, ExamData
from .analysis import (
    analyze_overall, analyze_items, build_score_matrix, analyze_serdap,
    grade_level, reliability_label, LEVELS,
)
from . import charts
from .theme import ThemeManager
from .cuts_loader import load_cut_scores
from .perform_loader import load_perform
from . import fonts as font_pack
from .ai_client import (
    AIProviderConfig, default_endpoint, default_model, list_ollama_models,
    list_openai_compatible_models, normalize_endpoint, parse_review_rows,
    probe_openai_compatible_chat, run_completion, scrub_personal_data,
)
from .widgets import (
    StepperSpinBox, ItemBarDelegate, attach_wheel_zoom, NaturalItem,
    install_frozen_columns, refresh_frozen_columns,
)
from . import __version__

try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
except Exception:
    QWebEngineView = None


APP_TITLE = "성취평가 결과 분석 (Goedu-Split)"
APP_AUTHOR = "이준서"
APP_VERSION = __version__
APP_COPYRIGHT = "© 2026 이준서. All rights reserved."
DEFAULT_CUTS = {"A": 90.0, "B": 80.0, "C": 70.0, "D": 60.0, "E": 40.0}
PERFORM_DEFAULT_RATES = {"A": 0.90, "B": 0.80, "C": 0.70, "D": 0.60, "E": 0.40}
LEVELS_AE = ["A", "B", "C", "D", "E"]
AI_EXPECTED_HEADERS = [f"{lv} 예상" for lv in LEVELS_AE]
AI_REVIEW_HEADERS = [
    "구분", "번호/요소", "성취기준 후보", "평가유형", "목표수준 후보", "난이도 후보",
    *AI_EXPECTED_HEADERS, "근거", "다음 확인",
]
AI_SOURCE_TEXT_LIMIT = 120_000
AI_REFERENCE_TEXT_LIMIT = 300_000
AI_SOURCE_CACHE_NAME = "_combined_ai_source_text.txt"
AI_REFERENCE_CACHE_NAME = "_combined_ai_reference_text.txt"
AI_REVIEW_LOCAL_CHUNK_SIZE = 3
AI_REVIEW_CLOUD_CHUNK_SIZE = 5
AI_REVIEW_CHUNK_SOURCE_LIMIT = 9_000
AI_REVIEW_CHUNK_REFERENCE_LIMIT = 8_000


def _app_icon_path() -> Path | None:
    here = Path(__file__).resolve()
    bundle_base = Path(getattr(sys, "_MEIPASS", here.parents[1]))
    candidates = [
        bundle_base / "assets" / "app_icon" / "goedusplit.png",
        here.parents[1] / "assets" / "app_icon" / "goedusplit.png",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _class_no_sort_value(text: str) -> tuple[int, int, str]:
    raw = (text or "").strip()
    if "/" in raw:
        try:
            a, b = raw.split("/", 1)
            return (int(a), int(b), raw)
        except Exception:
            pass
    return (10**9, 10**9, raw)


def _is_fixed_cut_scores(cuts: dict[str, float], tolerance: float = 0.005) -> bool:
    return all(abs(float(cuts.get(lv, -999)) - DEFAULT_CUTS[lv]) <= tolerance for lv in DEFAULT_CUTS)


def _normal_cdf(x: float, mean: float, std: float) -> float:
    if std <= 0:
        return 1.0 if x >= mean else 0.0
    return 0.5 * (1.0 + math.erf((x - mean) / (std * math.sqrt(2.0))))

LUCIDE_PATHS = {
    "menu": '<path d="M4 6h16"/><path d="M4 12h16"/><path d="M4 18h16"/>',
    "minus": '<path d="M5 12h14"/>',
    "plus": '<path d="M12 5v14"/><path d="M5 12h14"/>',
    "rotate": '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/>',
    "moon": '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/>',
    "chevron-down": '<path d="m6 9 6 6 6-6"/>',
    "chevron-right": '<path d="m9 18 6-6-6-6"/>',
}


def _lucide_icon(name: str, color: str, size: int = 18) -> QIcon:
    path = LUCIDE_PATHS.get(name, LUCIDE_PATHS["menu"])
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" '
        f'stroke-linecap="round" stroke-linejoin="round">{path}</svg>'
    )
    pix = QPixmap()
    pix.loadFromData(svg.encode("utf-8"), "SVG")
    return QIcon(pix)


# ---------------------------------------------------------------------------
# 헬퍼 위젯
# ---------------------------------------------------------------------------

class FileSelector(QWidget):
    """파일 경로 표시+선택 버튼 1줄."""
    def __init__(self, label: str, file_filter: str = "Excel (*.xlsx)", parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel(label); self.label.setMinimumWidth(140)
        self.path_edit = QLineEdit(); self.path_edit.setReadOnly(True)
        self.btn = QPushButton("찾아보기…")
        self.btn.clicked.connect(self._pick)
        layout.addWidget(self.label); layout.addWidget(self.path_edit, 1); layout.addWidget(self.btn)
        self.file_filter = file_filter

    def _pick(self):
        path, _ = QFileDialog.getOpenFileName(self, "파일 선택", "", self.file_filter)
        if path:
            self.path_edit.setText(path)

    def path(self) -> str:
        return self.path_edit.text().strip()


class CanvasHolder(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QVBoxLayout(self); self._layout.setContentsMargins(0, 0, 0, 0)
        self._canvas: FigureCanvas | None = None

    def set_figure(self, fig):
        if self._canvas is not None:
            self._layout.removeWidget(self._canvas); self._canvas.setParent(None); self._canvas.deleteLater()
        self._canvas = FigureCanvas(fig)
        self._canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # 마우스 휠로 줌, 더블클릭으로 원상 복귀
        attach_wheel_zoom(self._canvas)
        self._canvas.setToolTip("마우스 휠 = 확대/축소 · 더블클릭 = 원상복귀")
        self._layout.addWidget(self._canvas)


def _set_item(table: QTableWidget, r: int, c: int, value, *, align_right=False, bg=None,
              bold=False, align_left=False, tooltip: str | None = None):
    text = "" if value is None else str(value)
    item = QTableWidgetItem(text)
    if align_left:
        item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    elif align_right:
        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
    else:
        item.setTextAlignment(Qt.AlignCenter)
    if bg is not None:
        item.setBackground(QBrush(bg))
    if bold:
        f = item.font(); f.setBold(True); item.setFont(f)
    # 길게 잘릴 가능성 있는 셀은 무조건 툴팁(전체 텍스트). 외부에서 별도 지정하면 그것 우선.
    if tooltip:
        item.setToolTip(tooltip)
    elif len(text) > 8:
        item.setToolTip(text)
    table.setItem(r, c, item)
    return item


def _setup_table(t: QTableWidget, *, stretch_first: bool = False, word_wrap: bool = False,
                 horizontal_scroll: bool = False, row_height: int = 28):
    """공통 표 스타일: 한 줄 표시(말줄임) + 호버 툴팁 + 알맞은 행 높이."""
    t.verticalHeader().setVisible(False)
    t.setAlternatingRowColors(True)
    t.setSelectionBehavior(QTableWidget.SelectRows)
    t.setEditTriggers(QTableWidget.NoEditTriggers)
    t.setWordWrap(word_wrap)
    t.setTextElideMode(Qt.ElideRight)
    # 호버만으로 툴팁이 빨리 뜨도록 mouseTracking 활성화 + 툴팁 노출 시간 길게
    t.setMouseTracking(True)
    t.viewport().setMouseTracking(True)
    if not horizontal_scroll:
        t.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    else:
        t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        t.horizontalHeader().setStretchLastSection(False)
    if stretch_first:
        t.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
    # 행 높이 고정 → 줄바꿈으로 한 행이 너무 커지는 문제 방지
    t.setProperty("baseRowHeight", row_height)
    t.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
    t.verticalHeader().setDefaultSectionSize(row_height)


def _contrast_text_for_fill(hex_color: str) -> QColor:
    """셀 배경색 위에서 더 잘 보이는 흰색/진한색을 고른다."""
    try:
        h = hex_color.lstrip("#")
        if len(h) == 3:
            h = "".join(ch * 2 for ch in h)
        r, g, b = (int(h[i:i+2], 16) / 255 for i in (0, 2, 4))

        def lin(v):
            return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

        lum = 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
        return QColor("#ffffff" if lum < 0.179 else "#111827")
    except Exception:
        return QColor("#111827")


# ---------------------------------------------------------------------------
# 메인 윈도우
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self, theme_manager: ThemeManager | None = None):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        icon_path = _app_icon_path()
        if icon_path is not None:
            self.setWindowIcon(QIcon(str(icon_path)))
        self.resize(1320, 860)
        self.setMinimumSize(1080, 720)

        self.exam: ExamData | None = None
        self.overall = None
        self.item_stats: list = []
        self.perform_data = None
        self.spliter_view = None
        self._spliter_loaded = False
        self._spliter_pending_payload = None
        self._spliter_pending_project_payload = None
        self._perform_recalc_dirty = False
        self.settings = QSettings("GoeduSplit", "Goedu-Split")
        self.theme = theme_manager
        # 화면 배율(%). 100이 기본이고 50~160 사이에서 조절한다.
        self._zoom = 100
        self._base_font_pt = 13

        # Qt에 번들 폰트 등록 → 시스템에 Gowun Dodum/NanumGothic이 없어도 동작
        try: font_pack.register_fonts()
        except Exception: pass

        self._build_ui()
        self._build_menu()
        self._build_statusbar()
        self._install_shortcuts()
        if self.theme is not None:
            self.theme.changed.connect(self._on_theme_changed)
            charts.set_theme(self.theme.colors)
        self.statusBar().showMessage("좌측에서 정오표·문항정보표를 지정하고 '분석 실행'을 누르세요.")

    def _icon_color(self) -> str:
        if self.theme is not None:
            return self.theme.colors.get("accent", "#2a7770")
        return "#2a7770"

    def _apply_tool_icon(self, button: QToolButton, name: str):
        button.setText("")
        button.setIcon(_lucide_icon(name, self._icon_color()))
        button.setIconSize(QSize(18, 18))

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        central = QWidget()
        outer = QVBoxLayout(central); outer.setContentsMargins(12, 8, 12, 8); outer.setSpacing(8)
        outer.addWidget(self._build_header_bar())

        self.splitter = QSplitter(Qt.Horizontal, self)
        self.input_panel = self._build_input_panel()
        self.input_panel.setMinimumWidth(self._px(280))
        self.splitter.addWidget(self.input_panel)
        self.splitter.addWidget(self._build_tabs())
        self.splitter.setStretchFactor(0, 0); self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([330, 990])
        # 좁아질 때 자동 접힘 가능
        self.splitter.setCollapsible(0, True)
        self.splitter.setCollapsible(1, False)
        outer.addWidget(self.splitter, 1)
        self.setCentralWidget(central)

    def _build_header_bar(self) -> QWidget:
        bar = QFrame(); bar.setProperty("role", "headerbar")
        h = QHBoxLayout(bar); h.setContentsMargins(8, 4, 8, 4); h.setSpacing(8)

        # 사이드바 토글 (좁은 창에서 입력 패널 보이기/숨기기)
        self.btn_sidebar = QToolButton()
        self.btn_sidebar.setProperty("role", "iconbtn")
        self.btn_sidebar.setToolTip("입력 패널 보이기/숨기기")
        self.btn_sidebar.clicked.connect(self._toggle_sidebar)
        self._apply_tool_icon(self.btn_sidebar, "menu")
        h.addWidget(self.btn_sidebar)

        title = QLabel("성취평가 결과 분석")
        title.setProperty("role", "appname")
        h.addWidget(title)
        ver = QLabel(f"v{APP_VERSION}")
        ver.setProperty("role", "muted")
        h.addWidget(ver)
        h.addStretch(1)

        # 줌 컨트롤
        self.btn_zoom_out = QToolButton()
        self.btn_zoom_out.setToolTip("화면 축소 (Ctrl+−, 최소 50%)")
        self.btn_zoom_out.setProperty("role", "iconbtn")
        self.btn_zoom_out.clicked.connect(lambda: self._set_zoom(self._zoom - 10))
        self._apply_tool_icon(self.btn_zoom_out, "minus")
        self.lbl_zoom = QLabel("100%")
        self.lbl_zoom.setProperty("role", "muted")
        self.lbl_zoom.setMinimumWidth(self._px(46))
        self.lbl_zoom.setAlignment(Qt.AlignCenter)
        self.btn_zoom_in = QToolButton()
        self.btn_zoom_in.setToolTip("화면 확대 (Ctrl++, 최대 160%)")
        self.btn_zoom_in.setProperty("role", "iconbtn")
        self.btn_zoom_in.clicked.connect(lambda: self._set_zoom(self._zoom + 10))
        self._apply_tool_icon(self.btn_zoom_in, "plus")
        self.btn_zoom_reset = QToolButton()
        self.btn_zoom_reset.setToolTip("기본 크기로 (Ctrl+0)")
        self.btn_zoom_reset.setProperty("role", "iconbtn")
        self.btn_zoom_reset.clicked.connect(lambda: self._set_zoom(100))
        self._apply_tool_icon(self.btn_zoom_reset, "rotate")
        for b in (self.btn_zoom_out, self.lbl_zoom, self.btn_zoom_in, self.btn_zoom_reset):
            h.addWidget(b)

        spacer = QLabel("│"); spacer.setProperty("role", "muted"); h.addWidget(spacer)

        # 라이트/다크 토글
        self.btn_theme = QToolButton()
        self.btn_theme.setProperty("role", "iconbtn")
        self.btn_theme.setToolTip("라이트/다크 전환  (Ctrl+1: 라이트 / Ctrl+2: 다크 / Ctrl+3: 자동)")
        self.btn_theme.clicked.connect(self._toggle_theme_button)
        h.addWidget(self.btn_theme)
        self._update_theme_button_icon()
        return bar

    def _install_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+="), self, activated=lambda: self._set_zoom(self._zoom + 10))
        QShortcut(QKeySequence("Ctrl++"), self, activated=lambda: self._set_zoom(self._zoom + 10))
        QShortcut(QKeySequence("Ctrl+-"), self, activated=lambda: self._set_zoom(self._zoom - 10))
        QShortcut(QKeySequence("Ctrl+0"), self, activated=lambda: self._set_zoom(100))

    def _zoom_factor(self) -> float:
        return max(0.5, min(1.6, float(self._zoom) / 100.0))

    def _zoom_percent(self) -> int:
        return round(self._zoom_factor() * 100)

    def _px(self, value: int | float) -> int:
        return max(1, int(round(float(value) * self._zoom_factor())))

    def _set_scaled_column_width(self, table: QTableWidget, col: int, base_width: int):
        widths = dict(table.property("baseColumnWidths") or {})
        widths[int(col)] = int(base_width)
        table.setProperty("baseColumnWidths", widths)
        table.setColumnWidth(col, self._px(base_width))

    def _apply_zoom_to_surfaces(self):
        """QSS만으로는 안 바뀌는 고정 픽셀 표면까지 현재 배율에 맞춘다."""
        for table in self.findChildren(QTableWidget):
            base_row = table.property("baseRowHeight") or 28
            row_h = self._px(base_row)
            table.verticalHeader().setDefaultSectionSize(row_h)
            for r in range(table.rowCount()):
                table.setRowHeight(r, row_h)
            widths = table.property("baseColumnWidths") or {}
            for col, base_width in dict(widths).items():
                try:
                    table.setColumnWidth(int(col), self._px(float(base_width)))
                except Exception:
                    pass
            refresh_frozen_columns(table)
            table.viewport().update()
        for stepper in self.findChildren(StepperSpinBox):
            stepper.btn_minus.setFixedWidth(self._px(32))
            stepper.btn_plus.setFixedWidth(self._px(32))
        for selector in self.findChildren(FileSelector):
            selector.label.setMinimumWidth(self._px(140))
        for button in self.findChildren(QToolButton):
            button.setIconSize(QSize(self._px(18), self._px(18)))
        if hasattr(self, "btn_clear_search"):
            self.btn_clear_search.setFixedWidth(self._px(32))
        if hasattr(self, "lbl_zoom"):
            self.lbl_zoom.setMinimumWidth(max(42, self._px(46)))
        if hasattr(self, "input_panel"):
            self.input_panel.setMinimumWidth(max(180, self._px(280)))
        if hasattr(self, "table_serdap"):
            self.table_serdap.setMaximumHeight(max(70, self._px(110)))
        self._send_spliter_zoom()

    def _set_zoom(self, percent: int):
        percent = max(50, min(160, int(round(percent))))
        self._zoom = percent
        pt = max(7, int(round(self._base_font_pt * self._zoom_factor())))
        if self.theme is not None:
            # 1) QSS 재빌드 + matplotlib rcParams 동기화 + 시그널 → _on_theme_changed → 모든 차트 재렌더
            self.theme.set_base_font_pt(pt)
        else:
            f = self.font(); f.setPointSize(pt); self.setFont(f)
            app = QApplication.instance()
            if app is not None:
                af = app.font(); af.setPointSize(pt); app.setFont(af)
            # ThemeManager가 없을 때도 차트는 다시 그려야 폰트 반영
            self._refresh_all_charts()
        self._apply_zoom_to_surfaces()
        # % 라벨 갱신 (기본 13pt = 100%)
        pct = self._zoom_percent()
        if hasattr(self, "lbl_zoom"):
            self.lbl_zoom.setText(f"{pct}%")
        self.statusBar().showMessage(f"화면 배율 {pct}% · 글자 {pt}pt", 2500)

    def _toggle_sidebar(self):
        sizes = self.splitter.sizes()
        if sizes[0] <= 4:
            # 펼치기
            self.splitter.setSizes([330, max(600, sum(sizes) - 330)])
        else:
            # 접기
            self.splitter.setSizes([0, sum(sizes)])

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        try:
            w = self.width()
            sizes = self.splitter.sizes()
            if w < 1180 and sizes[0] > 0:
                self.splitter.setSizes([0, sum(sizes)])
            elif w >= 1280 and sizes[0] == 0:
                self.splitter.setSizes([330, max(600, sum(sizes) - 330)])
            # KPI 카드 자동 줄바꿈
            if hasattr(self, "_kpis") and self._kpis:
                content_w = max(300, w - sizes[0] - 60)
                cols = 3 if content_w >= 720 else (2 if content_w >= 480 else 1)
                # 현재 cols와 다르면 재배치
                cur_cols = max(1, self.kpi_grid.columnCount() or 1)
                if cur_cols != cols:
                    self._relayout_kpis(cols)
        except Exception:
            pass

    def _toggle_theme_button(self):
        if self.theme is None:
            return
        # auto이면 dark→light로 토글, dark이면 light로, light이면 dark로
        cur = self.theme.effective
        nxt = "light" if cur == "dark" else "dark"
        self.theme.set_mode(nxt)

    def _update_theme_button_icon(self):
        if self.theme is None:
            self._apply_tool_icon(self.btn_theme, "moon")
            return
        eff = self.theme.effective
        # 다크일 때는 해(라이트로 가는 버튼), 라이트일 때는 달(다크로 가는 버튼)
        self._apply_tool_icon(self.btn_theme, "sun" if eff == "dark" else "moon")

    def _refresh_header_icons(self):
        for button, icon_name in (
            (getattr(self, "btn_sidebar", None), "menu"),
            (getattr(self, "btn_zoom_out", None), "minus"),
            (getattr(self, "btn_zoom_in", None), "plus"),
            (getattr(self, "btn_zoom_reset", None), "rotate"),
        ):
            if button is not None:
                self._apply_tool_icon(button, icon_name)
        if hasattr(self, "btn_spliter_summary_toggle") and hasattr(self, "spliter_summary_body"):
            self._apply_tool_icon(
                self.btn_spliter_summary_toggle,
                "chevron-down" if self.spliter_summary_body.isVisible() else "chevron-right",
            )
        if hasattr(self, "btn_theme"):
            self._update_theme_button_icon()

    def _build_input_panel(self) -> QWidget:
        outer = QScrollArea(); outer.setWidgetResizable(True)
        w = QFrame(); outer.setWidget(w)
        v = QVBoxLayout(w); v.setContentsMargins(12, 12, 12, 12); v.setSpacing(10)

        title = QLabel("입력 데이터")
        title.setProperty("role", "title")
        v.addWidget(title)

        # 입력 파일 그룹
        files_box = QGroupBox()
        ff = QVBoxLayout(files_box); ff.setSpacing(8)

        # 폴더 일괄 업로드 버튼 (가장 위에 강조)
        folder_btn = QPushButton("📂  폴더에서 한 번에 불러오기")
        folder_btn.setProperty("role", "primary-soft")
        folder_btn.setMinimumHeight(34)
        folder_btn.clicked.connect(self._pick_folder_batch)
        folder_btn.setToolTip(
            "폴더 안의 정오표/문항정보표/추정분할점수/수행평가 파일을\n"
            "파일 이름 패턴으로 자동 분류해 한 번에 채워 넣습니다."
        )
        ff.addWidget(folder_btn)

        self.fs_response = FileSelector("학생답 정오표 data")
        self.fs_iteminfo = FileSelector("문항정보표")
        self.fs_cuts = FileSelector("예상추정분할점수 조회")
        self.fs_cuts.path_edit.textChanged.connect(self._on_cuts_path_changed)
        ff.addWidget(self.fs_response); ff.addWidget(self.fs_iteminfo); ff.addWidget(self.fs_cuts)
        cuts_help = QLabel("※ 추정분할점수 파일을 지정하면 아래 분할점수가 자동 입력됩니다.")
        cuts_help.setProperty("role", "muted"); cuts_help.setWordWrap(True)
        ff.addWidget(cuts_help)
        v.addWidget(files_box)

        # 수행평가 (선택)
        perf_box = QGroupBox("수행평가 (선택)")
        pf = QVBoxLayout(perf_box)
        self.chk_perform = QCheckBox("수행평가도 포함하여 분석합니다.")
        self.chk_perform.toggled.connect(self._toggle_perform)
        self.fs_perform = FileSelector("수행평가 결과 (.xlsx)")
        self.fs_perform.setEnabled(False)
        self.fs_perform.path_edit.textChanged.connect(self._on_perform_path_changed)
        self.lbl_perform_info = QLabel("(미설정)")
        self.lbl_perform_info.setProperty("role", "muted"); self.lbl_perform_info.setWordWrap(True)
        pf.addWidget(self.chk_perform); pf.addWidget(self.fs_perform); pf.addWidget(self.lbl_perform_info)
        v.addWidget(perf_box)

        # 점수 반영비율
        weight_box = QGroupBox("반영비율 (지필 + 수행 = 100)")
        wf = QFormLayout(weight_box); wf.setLabelAlignment(Qt.AlignRight)
        wf.setVerticalSpacing(8)
        self.spin_pencil_ratio = StepperSpinBox(value=100, minimum=0, maximum=100, step=5, decimals=0, suffix=" %")
        self.spin_perform_ratio = StepperSpinBox(value=0, minimum=0, maximum=100, step=5, decimals=0, suffix=" %")
        self.spin_perform_ratio.setEnabled(False)
        self.spin_pencil_ratio.valueChanged.connect(self._sync_pencil_to_perform)
        self.spin_perform_ratio.valueChanged.connect(self._sync_perform_to_pencil)
        wf.addRow("지필평가 반영비율", self.spin_pencil_ratio)
        wf.addRow("수행평가 반영비율", self.spin_perform_ratio)
        v.addWidget(weight_box)

        # 분할점수
        self.cuts_box = QGroupBox("분할점수 (고정 분할 방식)")
        form = QFormLayout(self.cuts_box); form.setLabelAlignment(Qt.AlignRight)
        form.setVerticalSpacing(8)
        self.spin_cuts = {}
        labels = {"A": "A/B 분할점수", "B": "B/C 분할점수",
                  "C": "C/D 분할점수", "D": "D/E 분할점수",
                  "E": "E/미도달 분할점수"}
        for lv in ["A", "B", "C", "D", "E"]:
            sp = StepperSpinBox(value=DEFAULT_CUTS[lv], minimum=0, maximum=100,
                                step=1.0, decimals=2)
            sp.valueChanged.connect(self._update_cut_box_title)
            self.spin_cuts[lv] = sp
            form.addRow(labels[lv], sp)
        v.addWidget(self.cuts_box)

        # 액션 버튼
        # 액션 버튼들
        run_btn = QPushButton("분석 실행")
        run_btn.setProperty("role", "primary")
        run_btn.setMinimumHeight(40)
        run_btn.clicked.connect(self.run_analysis)
        v.addWidget(run_btn)

        action_row = QHBoxLayout(); action_row.setSpacing(6)
        self.btn_revert = QPushButton("↺ 적용값 복원")
        self.btn_revert.setToolTip("마지막으로 분석 실행했을 때의 입력값으로 되돌립니다.\n실수로 분할점수나 파일 경로를 건드렸을 때 사용하세요.")
        self.btn_revert.clicked.connect(self._revert_inputs)
        self.btn_revert.setEnabled(False)
        action_row.addWidget(self.btn_revert)
        export_btn = QPushButton("결과 CSV 내보내기…")
        export_btn.clicked.connect(self.export_csv)
        action_row.addWidget(export_btn)
        v.addLayout(action_row)

        spliter_btn = QPushButton("예상정답률 근거 엑셀 내보내기…")
        spliter_btn.setToolTip("분석된 학생 성취수준과 문항 정오 데이터를 예상정답률 계산기 추천 근거 엑셀로 저장합니다.")
        spliter_btn.clicked.connect(self.export_spliter_evidence)
        v.addWidget(spliter_btn)

        v.addStretch(1)
        self.exam_info_lbl = QLabel("(분석 전)")
        self.exam_info_lbl.setWordWrap(True)
        self.exam_info_lbl.setProperty("role", "muted")
        v.addWidget(self.exam_info_lbl)

        credit = QLabel(APP_COPYRIGHT)
        credit.setProperty("role", "credit")
        credit.setAlignment(Qt.AlignRight)
        v.addWidget(credit)
        self._update_cut_box_title()
        return outer

    def _current_cut_scores_from_inputs(self) -> dict[str, float]:
        if not hasattr(self, "spin_cuts"):
            return dict(DEFAULT_CUTS)
        return {lv: float(self.spin_cuts[lv].value()) for lv in ["A", "B", "C", "D", "E"]}

    def _update_cut_box_title(self, *_):
        if not hasattr(self, "cuts_box"):
            return
        mode = "고정 분할 방식" if _is_fixed_cut_scores(self._current_cut_scores_from_inputs()) else "추정 분할 방식"
        self.cuts_box.setTitle(f"분할점수 ({mode})")

    def _snapshot_inputs(self):
        """현재 사이드바 입력값 전체를 dict로 보존 → 나중에 복원."""
        self._last_inputs = {
            "response": self.fs_response.path(),
            "iteminfo": self.fs_iteminfo.path(),
            "cuts_file": self.fs_cuts.path(),
            "perform": self.fs_perform.path(),
            "perform_on": self.chk_perform.isChecked(),
            "ratio_p": self.spin_pencil_ratio.value(),
            "ratio_f": self.spin_perform_ratio.value(),
            "cuts": {lv: self.spin_cuts[lv].value() for lv in ["A","B","C","D","E"]},
        }

    def _revert_inputs(self):
        s = getattr(self, "_last_inputs", None)
        if not s:
            return
        self.fs_response.path_edit.setText(s["response"])
        self.fs_iteminfo.path_edit.setText(s["iteminfo"])
        self.fs_cuts.path_edit.setText(s["cuts_file"])
        self.fs_perform.path_edit.setText(s["perform"])
        self.chk_perform.setChecked(s["perform_on"])
        self.spin_pencil_ratio.spin.blockSignals(True)
        self.spin_pencil_ratio.setValue(s["ratio_p"]); self.spin_pencil_ratio.spin.blockSignals(False)
        self.spin_perform_ratio.spin.blockSignals(True)
        self.spin_perform_ratio.setValue(s["ratio_f"]); self.spin_perform_ratio.spin.blockSignals(False)
        for lv in ["A","B","C","D","E"]:
            self.spin_cuts[lv].setValue(s["cuts"][lv])
        self._update_cut_box_title()
        self.statusBar().showMessage("마지막 분석값으로 입력을 복원했습니다.", 4000)

    def _search_terms(self, text: str) -> list[str]:
        return [part.strip().lower() for part in text.replace("\n", ",").split(",") if part.strip()]

    def _student_matches_terms(self, st, terms: list[str]) -> bool:
        if not terms:
            return True
        haystack = " ".join([
            str(st.name or ""),
            str(st.class_no or ""),
            str(st.sid or ""),
            str(st.grade_class or ""),
        ]).lower()
        return any(term in haystack for term in terms)

    def _matching_student_indices(self, text: str) -> list[int]:
        if self.exam is None:
            return []
        terms = self._search_terms(text)
        if not terms:
            return []
        return [i for i, st in enumerate(self.exam.students) if self._student_matches_terms(st, terms)]

    def _highlight_data_from_search(self, text: str) -> tuple[list[float], list[str]]:
        matches = self._matching_student_indices(text)
        scores, labels = [], []
        if self.exam is None:
            return scores, labels
        for idx in matches[:10]:
            st = self.exam.students[idx]
            name = st.name or st.class_no or st.sid
            scores.append(float(st.final_score))
            labels.append(f"{name} {st.final_score:.1f}")
        return scores, labels

    def _render_score_histogram_for_search(self, text: str = ""):
        if self.exam is None or self.overall is None:
            return
        totals = [s.final_score for s in self.exam.students]
        scores, labels = self._highlight_data_from_search(text)
        self.canvas_score_hist.set_figure(
            charts.fig_score_histogram_colored(
                totals,
                self.overall.levels_arr,
                highlight_scores=scores,
                highlight_labels=labels,
            )
        )

    def _sync_frozen_row_hidden(self, row: int, hidden: bool):
        frozen = getattr(self.table_data, "frozenView", None)
        if frozen is not None:
            frozen.setRowHidden(row, hidden)

    def _filter_data_table(self, text: str):
        """학생 응답표를 이름/반·번호로 즉시 필터링하고 그래프에 위치를 표시."""
        terms = self._search_terms(text)
        if not hasattr(self, "table_data") or self.table_data.rowCount() == 0:
            return
        # 컬럼 0: 반/번호, 컬럼 1: 이름
        visible_rows = []
        for r in range(self.table_data.rowCount()):
            if not terms:
                self.table_data.setRowHidden(r, False)
                self._sync_frozen_row_hidden(r, False)
                continue
            cls_item = self.table_data.item(r, 0)
            name_item = self.table_data.item(r, 1)
            cls = (cls_item.text() if cls_item else "").lower()
            name = (name_item.text() if name_item else "").lower()
            visible = any(term in cls or term in name for term in terms)
            self.table_data.setRowHidden(r, not visible)
            self._sync_frozen_row_hidden(r, not visible)
            if visible:
                visible_rows.append(r)
        if not terms:
            self.lbl_search_status.setText("")
        else:
            names = []
            for r in visible_rows[:4]:
                cls = self.table_data.item(r, 0).text() if self.table_data.item(r, 0) else ""
                name = self.table_data.item(r, 1).text() if self.table_data.item(r, 1) else ""
                score_item = self.table_data.item(r, 3) if self.table_data.columnCount() > 3 else None
                score = f" {score_item.text()}점" if score_item is not None else ""
                names.append(f"{name}({cls}{score})")
            more = f" 외 {len(visible_rows) - 4}명" if len(visible_rows) > 4 else ""
            self.lbl_search_status.setText(
                f"검색 {len(visible_rows)}명: {', '.join(names)}{more}" if visible_rows else "검색 결과 없음"
            )
        if visible_rows:
            self.table_data.selectRow(visible_rows[0])
            first_item = self.table_data.item(visible_rows[0], 0)
            if first_item is not None:
                self.table_data.scrollToItem(first_item, QAbstractItemView.PositionAtCenter)
        self._render_score_histogram_for_search(text)

    def _show_monitoring_dialog(self):
        if self.exam is None or self.overall is None:
            QMessageBox.information(self, "모니터링 지표", "먼저 분석을 실행해 주세요.")
            return
        observed_a = float(self.overall.level_dist_pct.get("A", 0.0))
        default_national = max(0.0, min(100.0, observed_a))
        national_a, ok = QInputDialog.getDouble(
            self,
            "전국 평균 A 비율",
            "비교할 전국 평균 A 비율(%)을 입력하세요.",
            default_national,
            0.0,
            100.0,
            1,
        )
        if not ok:
            return
        threshold, ok = QInputDialog.getDouble(
            self,
            "점검 기준",
            "전국 평균과 몇 %p 이상 차이 날 때 점검으로 볼까요?",
            10.0,
            0.0,
            100.0,
            1,
        )
        if not ok:
            return

        totals = [s.final_score for s in self.exam.students]
        mean = sum(totals) / len(totals) if totals else 0.0
        std = (sum((x - mean) ** 2 for x in totals) / max(1, len(totals) - 1)) ** 0.5 if len(totals) > 1 else 0.0
        expected_a = (1 - _normal_cdf(float(self.exam.cut_scores["A"]), mean, std)) * 100 if std > 0 else 0.0
        diff_national = observed_a - national_a
        diff_normal = observed_a - expected_a
        status = "점검 필요" if abs(diff_national) >= threshold else "참고 범위"
        QMessageBox.information(
            self,
            "모니터링 지표",
            f"<h3>성취평가 모니터링 지표</h3>"
            f"<p><b>판정:</b> {status}</p>"
            f"<table cellspacing='4'>"
            f"<tr><td>학생 수</td><td align='right'>{self.overall.n_students}명</td></tr>"
            f"<tr><td>평균 / 표준편차</td><td align='right'>{mean:.2f} / {std:.2f}</td></tr>"
            f"<tr><td>실제 A 비율</td><td align='right'>{observed_a:.1f}%</td></tr>"
            f"<tr><td>입력한 전국 평균 A 비율</td><td align='right'>{national_a:.1f}%</td></tr>"
            f"<tr><td>전국 평균 대비 차이</td><td align='right'>{diff_national:+.1f}%p</td></tr>"
            f"<tr><td>정규분포 기대 A 비율</td><td align='right'>{expected_a:.1f}%</td></tr>"
            f"<tr><td>정규분포 기대 대비 차이</td><td align='right'>{diff_normal:+.1f}%p</td></tr>"
            f"<tr><td>미도달 비율</td><td align='right'>{self.overall.level_dist_pct.get('미도달', 0):.1f}%</td></tr>"
            f"</table>"
            f"<p>기준: 전국 평균과의 차이가 ±{threshold:.1f}%p 이상이면 점검 필요로 표시했습니다.</p>"
        )

    def _open_monitoring_tab(self):
        if hasattr(self, "tab_monitor"):
            self.tabs.setCurrentWidget(self.tab_monitor)
            self._render_monitor_tab()

    def _pick_folder_batch(self):
        """폴더를 선택하면 안의 .xlsx 파일들을 이름 패턴으로 자동 분류해 채운다.

        매칭 점수 방식:
          - 카테고리별 키워드 목록(가중치 부여) 중 하나라도 파일명에 포함되면 점수 누적.
          - 같은 파일이 여러 카테고리에 걸리면 더 높은 점수 카테고리에 배정.
          - 카테고리별 후보 중 최고 점수가 같으면 가장 최근 수정된 파일 우선.
        """
        directory = QFileDialog.getExistingDirectory(self, "성취평가 자료가 들어있는 폴더 선택")
        if not directory:
            return
        from pathlib import Path
        folder = Path(directory)
        files = sorted([p for p in folder.glob("*.xlsx") if not p.name.startswith("~")])
        if not files:
            QMessageBox.information(self, "폴더 일괄 불러오기",
                                    "선택한 폴더에 .xlsx 파일이 없습니다.")
            return

        # 카테고리별 키워드 (점수). 더 구체적/특이적인 키워드일수록 점수 높음.
        rules = {
            "response": [           # 학생답 정오표
                ("학생답 정오표", 100), ("학생답 정오", 90), ("정오표", 70),
                ("정오 data", 60), ("학생답안", 50), ("응답", 30), ("answer", 30),
            ],
            "iteminfo": [           # 문항정보표
                ("문항정보표", 100), ("문항 정보표", 90), ("문항정보", 70),
                ("문항 정보", 70), ("item info", 60), ("문항 출제", 50),
            ],
            "cuts": [               # 예상추정분할점수
                ("예상추정분할점수", 100), ("추정분할점수", 95),
                ("추정 분할점수", 90), ("예상 분할점수", 80),
                ("분할점수 조회", 70), ("분할점수", 50), ("cut score", 50),
            ],
            "perform": [            # 수행평가
                ("수행평가 결과", 100), ("수행평가 조회", 95),
                ("수행평가", 80), ("수행 평가", 75),
                ("수행 결과", 60), ("performance", 50),
            ],
        }

        # macOS Finder는 한글 파일명을 NFD(분해 형태)로 저장하지만 우리 키워드는 NFC다.
        # 양쪽을 NFC로 정규화한 뒤 비교한다. (Windows는 보통 NFC라 무관)
        import unicodedata
        def _norm(s: str) -> str:
            return unicodedata.normalize("NFC", s).lower().replace(" ", "").replace("_", "").replace("-", "")
        def score(path: Path, kws):
            name = _norm(path.name)
            best_score = 0
            for kw, w in kws:
                k = _norm(kw)
                if k in name:
                    best_score = max(best_score, w)
            return best_score

        # 카테고리별 후보 + 점수
        cands = {cat: [] for cat in rules}
        for p in files:
            for cat, kws in rules.items():
                s = score(p, kws)
                if s > 0:
                    cands[cat].append((s, p.stat().st_mtime, p))
        # 한 파일이 여러 카테고리에 걸리지 않도록 — 더 높은 점수 카테고리에 배정
        chosen: dict[str, Path] = {}
        used: set[Path] = set()
        # 카테고리 → 점수 내림차순으로 한 번에 처리
        order = ["response", "iteminfo", "cuts", "perform"]
        # 첫 패스: 카테고리별 최고 점수 1개씩 잠정 배정
        prelim = {}
        for cat in order:
            lst = sorted(cands[cat], reverse=True)
            for s, mt, p in lst:
                prelim[cat] = (s, mt, p)
                break
        # 충돌(같은 파일이 여러 카테고리)이면 더 큰 점수 쪽이 가져감
        # → 점수 내림차순으로 카테고리 순회하며 안 쓰인 파일을 차지
        cat_by_score = sorted(prelim.items(), key=lambda kv: -kv[1][0])
        for cat, (s, mt, p) in cat_by_score:
            if p in used:
                # 다음 후보 시도
                lst = sorted(cands[cat], reverse=True)
                for s2, mt2, p2 in lst:
                    if p2 not in used:
                        chosen[cat] = p2; used.add(p2); break
            else:
                chosen[cat] = p; used.add(p)

        applied = []
        if "response" in chosen:
            self.fs_response.path_edit.setText(str(chosen["response"]))
            applied.append(("학생답 정오표 data", chosen["response"].name))
        if "iteminfo" in chosen:
            self.fs_iteminfo.path_edit.setText(str(chosen["iteminfo"]))
            applied.append(("문항정보표", chosen["iteminfo"].name))
        if "cuts" in chosen:
            self.fs_cuts.path_edit.setText(str(chosen["cuts"]))
            applied.append(("예상추정분할점수", chosen["cuts"].name))
        if "perform" in chosen:
            self.chk_perform.setChecked(True)
            self.fs_perform.path_edit.setText(str(chosen["perform"]))
            applied.append(("수행평가", chosen["perform"].name))

        if not applied:
            QMessageBox.information(
                self, "폴더 일괄 불러오기",
                f"폴더에 .xlsx 파일은 {len(files)}개 있지만 이름이 인식 가능한 패턴이 아닙니다.\n"
                "파일명에 다음 키워드 중 하나가 들어 있는지 확인해 주세요:\n"
                "  · 정오표 / 학생답\n  · 문항정보표 / 문항정보\n"
                "  · 추정분할점수 / 분할점수\n  · 수행평가"
            )
            return

        msg_lines = [f"• {k} ← {v}" for k, v in applied]
        skipped = [p.name for p in files if p not in used]
        msg = "다음 파일을 자동으로 채웠습니다:\n\n" + "\n".join(msg_lines)
        if skipped:
            msg += "\n\n인식 안 된 파일:\n" + "\n".join(f"  · {n}" for n in skipped[:6])
            if len(skipped) > 6:
                msg += f"\n  · … 외 {len(skipped) - 6}개"
        if not ("response" in chosen and "iteminfo" in chosen):
            msg += "\n\n⚠ 정오표·문항정보표 중 일부가 인식되지 않아, 수동으로 지정해 주세요."
        self.statusBar().showMessage(f"폴더 일괄 불러오기 · {len(applied)}개 채움", 5000)
        QMessageBox.information(self, "폴더 일괄 불러오기", msg)

    def _toggle_perform(self, on: bool):
        self.fs_perform.setEnabled(on)
        self.spin_perform_ratio.setEnabled(on)
        if not on:
            self.spin_perform_ratio.spin.blockSignals(True)
            self.spin_perform_ratio.setValue(0)
            self.spin_perform_ratio.spin.blockSignals(False)
            self.spin_pencil_ratio.spin.blockSignals(True)
            self.spin_pencil_ratio.setValue(100)
            self.spin_pencil_ratio.spin.blockSignals(False)

    def _sync_pencil_to_perform(self, v):
        if not self.chk_perform.isChecked():
            return
        self.spin_perform_ratio.spin.blockSignals(True)
        self.spin_perform_ratio.setValue(max(0, 100 - v))
        self.spin_perform_ratio.spin.blockSignals(False)

    def _sync_perform_to_pencil(self, v):
        self.spin_pencil_ratio.spin.blockSignals(True)
        self.spin_pencil_ratio.setValue(max(0, 100 - v))
        self.spin_pencil_ratio.spin.blockSignals(False)

    def _on_perform_path_changed(self, path: str):
        path = path.strip()
        if not path:
            self.lbl_perform_info.setText("(미설정)")
            return
        try:
            pd_obj = load_perform(path)
        except Exception as e:
            QMessageBox.warning(self, "수행평가 파일 오류", f"파일을 인식하지 못했습니다.\n{e}")
            self.lbl_perform_info.setText("(파일 인식 실패)")
            return
        areas_text = ", ".join(f"{a.name}({a.ratio_pct:.0f}%)" for a in pd_obj.areas)
        self.lbl_perform_info.setText(
            f"<b>{pd_obj.subject}</b><br>학생 {len(pd_obj.records)}명 · 영역 {len(pd_obj.areas)}개<br>{areas_text}"
        )
        # 영역 반영비율 합을 수행평가 반영비율 기본값으로 제안
        if pd_obj.ratio_total > 0:
            self.spin_perform_ratio.spin.blockSignals(True)
            self.spin_perform_ratio.setValue(round(pd_obj.ratio_total))
            self.spin_perform_ratio.spin.blockSignals(False)
            self.spin_pencil_ratio.spin.blockSignals(True)
            self.spin_pencil_ratio.setValue(max(0, 100 - round(pd_obj.ratio_total)))
            self.spin_pencil_ratio.spin.blockSignals(False)

    def _on_cuts_path_changed(self, path: str):
        path = path.strip()
        if not path:
            return
        try:
            cuts, extra = load_cut_scores(path)
        except Exception as e:
            QMessageBox.warning(self, "추정분할점수 파일 오류",
                                f"파일을 인식하지 못했습니다.\n{e}")
            return
        for lv, val in cuts.items():
            self.spin_cuts[lv].setValue(round(float(val), 2))
        self._update_cut_box_title()
        self.statusBar().showMessage(
            f"추정분할점수 자동 적용 · A {cuts['A']:.2f} / B {cuts['B']:.2f} / "
            f"C {cuts['C']:.2f} / D {cuts['D']:.2f} / E {cuts['E']:.2f}",
            8000
        )

    def _build_tabs(self) -> QWidget:
        self.tabs = QTabWidget()
        self.tabs.setMovable(True)
        self.tabs.setUsesScrollButtons(True)
        self.tab_data = QWidget(); self._init_tab_data()
        self.tabs.addTab(self.tab_data, "Data")
        self.tab_overview = QWidget(); self._init_tab_overview()
        self.tabs.addTab(self.tab_overview, "전체 성취도 분석")
        self.tab_perform = QWidget(); self._init_tab_perform()
        self.tabs.addTab(self.tab_perform, "수행평가 분석")
        self.tab_items = QWidget(); self._init_tab_items()
        self.tabs.addTab(self.tab_items, "문항 분석")
        self.tab_choice = QWidget(); self._init_tab_choice()
        self.tabs.addTab(self.tab_choice, "성취수준별 답지반응 분포")
        self.tab_standard = QWidget(); self._init_tab_standard()
        self.tabs.addTab(self.tab_standard, "성취기준 분석 결과")
        self.tab_ai_review = QWidget(); self._init_tab_ai_review()
        self.tabs.addTab(self.tab_ai_review, "AI 문항 검토")
        self.tab_spliter = QWidget(); self._init_tab_spliter()
        self.tabs.addTab(self.tab_spliter, "예상정답률 입력")
        self.tab_monitor = QWidget(); self._init_tab_monitor()
        self.tabs.addTab(self.tab_monitor, "모니터링")
        self.tab_help = QWidget(); self._init_tab_help()
        self.tabs.addTab(self.tab_help, "도움말")
        return self.tabs

    # ---- 예상정답률 입력 ----------------------------------------------
    def _init_tab_spliter(self):
        layout = QVBoxLayout(self.tab_spliter)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        self.spliter_toolbar = QFrame()
        self.spliter_toolbar.setProperty("role", "card")
        toolbar_layout = QHBoxLayout(self.spliter_toolbar)
        toolbar_layout.setContentsMargins(12, 10, 12, 10)
        toolbar_layout.setSpacing(8)

        self.lbl_spliter_status = QLabel("분석 전 · 계산기는 아래에서 바로 사용할 수 있습니다.")
        self.lbl_spliter_status.setProperty("role", "muted")
        self.lbl_spliter_status.setWordWrap(True)
        toolbar_layout.addWidget(self.lbl_spliter_status, 1)

        btn_send = QPushButton("현재 분석자료 바로 보내기")
        btn_send.setProperty("role", "primary")
        btn_send.clicked.connect(self.send_spliter_evidence_to_web)
        toolbar_layout.addWidget(btn_send)
        btn_import_paper = QPushButton("시험지 자동 반영…")
        btn_import_paper.setToolTip(
            "시험지 HWPX/PDF/자료를 읽어 문항 초안을 만들고 예상정답률 계산기에 바로 반영합니다. "
            "AI 없이 로컬 규칙으로 먼저 처리하며, AI 문항 검토 탭에서 보강할 수 있습니다."
        )
        btn_import_paper.clicked.connect(self.import_exam_paper_to_spliter)
        toolbar_layout.addWidget(btn_import_paper)
        btn_blueprint = QPushButton("문항 구성안 제안…")
        btn_blueprint.setToolTip(
            "문항 수를 입력하면 분석자료의 난이도·정답률·배점 분포를 참고해 "
            "성취수준 목표와 배점 초안을 예상정답률 계산기에 제안합니다."
        )
        btn_blueprint.clicked.connect(self.suggest_expected_rate_blueprint)
        toolbar_layout.addWidget(btn_blueprint)
        btn_export = QPushButton("예상정답률 근거 엑셀 내보내기…")
        btn_export.clicked.connect(self.export_spliter_evidence)
        toolbar_layout.addWidget(btn_export)
        btn_reload = QPushButton("새로고침")
        btn_reload.clicked.connect(self._load_spliter_web)
        toolbar_layout.addWidget(btn_reload)
        layout.addWidget(self.spliter_toolbar, 0)

        if QWebEngineView is None:
            self.lbl_spliter_web = QLabel(
                "이 Python 환경에는 Qt WebEngine이 없어 내장 계산기를 표시할 수 없습니다. "
                "근거 엑셀을 내보내 자료를 확인해 주세요."
            )
            self.lbl_spliter_web.setProperty("role", "muted")
            self.lbl_spliter_web.setWordWrap(True)
            layout.addWidget(self.lbl_spliter_web, 1)
        else:
            self.spliter_view = QWebEngineView()
            self.spliter_view.loadFinished.connect(self._on_spliter_loaded)
            layout.addWidget(self.spliter_view, 1)
            self._load_spliter_web()

    def _toggle_spliter_summary(self):
        if not hasattr(self, "spliter_summary_body"):
            return
        visible = self.spliter_summary_body.isVisible()
        self.spliter_summary_body.setVisible(not visible)
        self._apply_tool_icon(
            self.btn_spliter_summary_toggle,
            "chevron-right" if visible else "chevron-down",
        )

    def _spliter_web_index(self) -> Path | None:
        here = Path(__file__).resolve().parent
        bundle_base = Path(getattr(sys, "_MEIPASS", here))
        candidates = [
            here / "spliter_ox_web" / "index.html",
            bundle_base / "app" / "spliter_ox_web" / "index.html",
            bundle_base / "spliter_ox_web" / "index.html",
            here.parents[1] / "spliter-ox" / "dist" / "index.html",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None

    def _load_spliter_web(self):
        if self.spliter_view is None:
            return
        index = self._spliter_web_index()
        if index is None:
            self.lbl_spliter_status.setText(
                "예상정답률 계산기 파일을 찾지 못했습니다. "
                "/Users/piman/Projects/spliter-ox 에서 npm run build 후 다시 시도해 주세요."
            )
            return
        if self.exam is not None and self.overall is not None:
            self._spliter_pending_payload = self._build_spliter_evidence_payload()
        self._spliter_loaded = False
        self.spliter_view.setUrl(QUrl.fromLocalFile(str(index)))

    def _on_spliter_loaded(self, ok: bool):
        self._spliter_loaded = ok
        if ok:
            self._send_spliter_theme()
            self._send_spliter_zoom()
            QTimer.singleShot(450, self._send_spliter_zoom)
            QTimer.singleShot(1200, self._send_spliter_zoom)
            self._flush_spliter_project_payload()
            self._flush_spliter_payload()

    def _send_spliter_theme(self):
        if self.spliter_view is None or not self._spliter_loaded:
            return
        theme = self.theme.effective if self.theme is not None else "light"
        data = json.dumps(theme, ensure_ascii=False)
        script = (
            f"window.__GOEDUSPLIT_THEME__ = {data};"
            "window.postMessage({ type: 'goedusplit-theme', theme: window.__GOEDUSPLIT_THEME__ }, '*');"
        )
        self.spliter_view.page().runJavaScript(script)

    def _send_spliter_zoom(self):
        if self.spliter_view is None or not self._spliter_loaded:
            return
        zoom = self._zoom_percent()
        data = json.dumps(zoom, ensure_ascii=False)
        script = (
            f"window.__GOEDUSPLIT_ZOOM__ = {data};"
            "window.postMessage({ type: 'goedusplit-zoom', zoom: window.__GOEDUSPLIT_ZOOM__ }, '*');"
        )
        self.spliter_view.page().runJavaScript(script)

    def _flush_spliter_payload(self):
        if self.spliter_view is None or not self._spliter_loaded or self._spliter_pending_payload is None:
            return
        payload = self._spliter_pending_payload
        self._spliter_pending_payload = None
        data = json.dumps(payload, ensure_ascii=False)
        script = (
            f"window.__GOEDUSPLIT_EVIDENCE__ = {data};"
            "window.postMessage({ type: 'goedusplit-evidence', payload: window.__GOEDUSPLIT_EVIDENCE__ }, '*');"
        )
        self.spliter_view.page().runJavaScript(script)

    def _flush_spliter_project_payload(self):
        if self.spliter_view is None or not self._spliter_loaded or self._spliter_pending_project_payload is None:
            return
        payload = self._spliter_pending_project_payload
        self._spliter_pending_project_payload = None
        data = json.dumps(payload, ensure_ascii=False)
        script = (
            f"window.__GOEDUSPLIT_PROJECT__ = {data};"
            "window.postMessage({ type: 'goedusplit-project', payload: window.__GOEDUSPLIT_PROJECT__ }, '*');"
        )
        self.spliter_view.page().runJavaScript(script)

    def send_spliter_evidence_to_web(self):
        if self.exam is None or self.overall is None:
            QMessageBox.warning(self, "예상정답률 계산기", "먼저 분석을 실행해 주세요.")
            return
        payload = self._build_spliter_evidence_payload()
        self._spliter_pending_payload = payload
        self.tabs.setCurrentWidget(self.tab_spliter)
        if self.spliter_view is not None:
            if self._spliter_loaded:
                self._flush_spliter_payload()
            else:
                self._load_spliter_web()
        self.statusBar().showMessage("예상정답률 계산기에 현재 분석자료를 전달했습니다.", 6000)

    def import_exam_paper_to_spliter(self):
        if self.spliter_view is None:
            QMessageBox.information(self, "예상정답률 계산기", "이 환경에서는 내장 예상정답률 계산기를 열 수 없습니다.")
            return
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "시험지 또는 문항 자료 불러와 예상정답률에 반영",
            "",
            "시험지/문항 자료 (*.hwp *.hwpx *.pdf *.docx *.txt *.md *.csv *.json *.xlsx *.xlsm);;모든 파일 (*.*)",
        )
        if not paths:
            return
        existing = self._ai_review_source_text().strip()
        append_existing = False
        if existing:
            choice = QMessageBox.question(
                self,
                "시험지 자료 반영",
                f"AI 문항 검토 탭에 이미 문항 자료가 들어 있습니다.\n"
                f"선택한 {len(paths)}개 자료를 기존 자료 뒤에 추가할까요?\n\n"
                "예: 추가해서 함께 반영\n아니오: 기존 자료를 지우고 새 시험지만 반영",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                QMessageBox.No,
            )
            if choice == QMessageBox.Cancel:
                return
            append_existing = choice == QMessageBox.Yes
        parts = []
        failures = []
        for path_str in paths:
            path = Path(path_str)
            try:
                saved = self._store_ai_source_file(path)
                text = self._extract_text_from_review_file(str(path))
            except Exception as exc:
                failures.append(f"{path.name}: {exc}")
                continue
            parts.append(
                f"{self._format_ai_material_header(f'시험지/문항 자료: {path.name}', saved)}\n\n"
                f"{text}"
            )
        if not parts:
            QMessageBox.warning(
                self,
                "시험지 자동 반영",
                "선택한 시험지 자료를 읽지 못했습니다.\n" + "\n".join(failures[:5]),
            )
            return
        text = "\n\n".join(parts)
        if append_existing:
            text = f"{existing}\n\n{text}"
        self._set_ai_review_source_text(text, target="source")
        self._save_ai_source_cache(text)
        self._load_ai_reference_cache_if_empty()
        self._generate_ai_review_draft()
        self._send_ai_review_to_spliter()
        message = (
            f"시험지 자료 {len(parts)}개를 읽어 예상정답률 계산기에 반영했습니다. "
            "필요하면 AI 문항 검토 탭에서 성취기준·난이도·예상 O/X를 보강하세요."
        )
        if failures:
            message += f" 읽기 실패 {len(failures)}개."
            QMessageBox.warning(
                self,
                "일부 시험지 자료 읽기 실패",
                "다음 자료는 불러오지 못했습니다.\n" + "\n".join(failures[:8]),
            )
        self.statusBar().showMessage(message, 8000)

    def suggest_expected_rate_blueprint(self):
        if self.spliter_view is None:
            QMessageBox.information(self, "예상정답률 계산기", "이 환경에서는 내장 예상정답률 계산기를 열 수 없습니다.")
            return
        default_count = len(self.exam.items) if self.exam is not None and self.exam.items else 18
        count, ok = QInputDialog.getInt(
            self,
            "문항 구성안 제안",
            "새 시험의 문항 수를 입력하세요.",
            max(1, min(80, default_count)),
            1,
            80,
            1,
        )
        if not ok:
            return
        project = self._build_expected_rate_blueprint_project(count)
        self._spliter_pending_project_payload = project
        if self.exam is not None and self.overall is not None:
            self._spliter_pending_payload = self._build_spliter_evidence_payload()
        self.tabs.setCurrentWidget(self.tab_spliter)
        if self._spliter_loaded:
            self._flush_spliter_project_payload()
            self._flush_spliter_payload()
        else:
            self._load_spliter_web()
        basis = "현재 분석자료" if self.exam is not None and self.item_stats else "기본 100점 구성"
        self.statusBar().showMessage(f"{basis}를 바탕으로 {count}문항 구성안을 예상정답률 계산기에 제안했습니다.", 7000)

    def _build_expected_rate_blueprint_project(self, count: int) -> dict:
        count = max(1, min(80, int(count)))
        total_score = self._expected_rate_blueprint_total_score()
        levels = self._expected_rate_blueprint_level_sequence(count)
        points = self._expected_rate_blueprint_points(levels, total_score)
        source_items = self._expected_rate_blueprint_source_items(levels)
        items = []
        for idx, target in enumerate(levels, start=1):
            source = source_items[idx - 1] if idx - 1 < len(source_items) else None
            difficulty = self._expected_rate_blueprint_difficulty(target, source)
            item_type = getattr(source, "item_type", "") if source is not None else ""
            item_type = item_type if item_type in {"선택형", "서답형"} else "선택형"
            standard = ""
            content = ""
            if source is not None:
                standard = " ".join(
                    part for part in [getattr(source, "standard_code", ""), getattr(source, "standard", "")]
                    if part
                ).strip()
                content = getattr(source, "content_area", "") or ""
            expected = self._ai_default_ox_expected_values(target, difficulty)
            counts = {}
            sample_size = 3
            for lv in LEVELS_AE:
                count_value, denominator = self._parse_expected_count(expected.get(f"{lv} 예상", ""), sample_size)
                sample_size = denominator
                counts[lv] = 0 if count_value is None else count_value
            judgments = self._judgments_from_expected_counts(counts, sample_size)
            items.append({
                "id": f"blueprint-{idx}",
                "number": idx,
                "title": f"{idx}번 · {target} 수준 제안",
                "standard": standard,
                "points": points[idx - 1],
                "sampleSize": sample_size,
                "type": item_type,
                "difficulty": difficulty,
                "targetLevel": target,
                "judgmentsByJudge": {
                    "teacher-1": judgments,
                    "teacher-2": judgments,
                },
                "evidence": ["구성안 제안"],
                "note": self._expected_rate_blueprint_note(target, difficulty, points[idx - 1], content),
            })
        project = {
            "version": 1,
            "judges": [
                {"id": "teacher-1", "name": "교사 1"},
                {"id": "teacher-2", "name": "교사 2"},
            ],
            "activeJudgeId": "teacher-1",
            "items": items,
            "evidenceMode": "difficultyAverage",
        }
        if self.exam is not None and self.overall is not None:
            project["evidenceData"] = self._build_spliter_evidence_payload()
        return project

    def _expected_rate_blueprint_total_score(self) -> float:
        if self.exam is not None and self.exam.items:
            total = sum(float(getattr(item, "score", 0.0) or 0.0) for item in self.exam.items)
            if total > 0:
                return round(total, 2)
        return 100.0

    def _expected_rate_blueprint_level_sequence(self, count: int) -> list[str]:
        weights = {lv: 0 for lv in LEVELS_AE}
        if self.item_stats:
            for stat in self.item_stats:
                p_value = float(getattr(stat, "p_value", 0.0) or 0.0)
                if p_value >= 0.80:
                    target = "E"
                elif p_value >= 0.65:
                    target = "D"
                elif p_value >= 0.45:
                    target = "C"
                elif p_value >= 0.30:
                    target = "B"
                else:
                    target = "A"
                weights[target] += 1
        if not any(weights.values()):
            weights = {"A": 1, "B": 3, "C": 5, "D": 5, "E": 4}
        scaled = self._scale_counts_to_total(weights, count, ["E", "D", "C", "B", "A"])
        sequence = []
        for lv in ["E", "D", "C", "B", "A"]:
            sequence.extend([lv] * scaled.get(lv, 0))
        return sequence[:count] or ["C"] * count

    @staticmethod
    def _scale_counts_to_total(weights: dict[str, int | float], total: int, order: list[str]) -> dict[str, int]:
        total = max(1, int(total))
        weight_sum = sum(max(0.0, float(weights.get(key, 0.0))) for key in order)
        if weight_sum <= 0:
            weight_sum = float(len(order))
            weights = {key: 1.0 for key in order}
        raw = {key: max(0.0, float(weights.get(key, 0.0))) / weight_sum * total for key in order}
        counts = {key: int(math.floor(raw[key])) for key in order}
        remaining = total - sum(counts.values())
        for key in sorted(order, key=lambda k: raw[k] - counts[k], reverse=True):
            if remaining <= 0:
                break
            counts[key] += 1
            remaining -= 1
        while sum(counts.values()) > total:
            for key in reversed(order):
                if counts.get(key, 0) > 0 and sum(counts.values()) > total:
                    counts[key] -= 1
        return counts

    def _expected_rate_blueprint_points(self, levels: list[str], total_score: float) -> list[float]:
        if not levels:
            return []
        level_weights = {"E": 0.9, "D": 1.0, "C": 1.1, "B": 1.2, "A": 1.3}
        weights = [level_weights.get(lv, 1.0) for lv in levels]
        weight_sum = sum(weights) or 1.0
        raw = [max(1.0, total_score * weight / weight_sum) for weight in weights]
        points = [max(1, int(round(value))) for value in raw]
        diff = int(round(total_score - sum(points)))
        hard_order = sorted(range(len(levels)), key=lambda i: LEVELS_AE.index(levels[i]))
        easy_order = list(reversed(hard_order))
        guard = 0
        while diff != 0 and guard < 1000:
            order = hard_order if diff > 0 else easy_order
            changed = False
            for idx in order:
                if diff > 0:
                    points[idx] += 1
                    diff -= 1
                    changed = True
                elif points[idx] > 1:
                    points[idx] -= 1
                    diff += 1
                    changed = True
                if diff == 0:
                    break
            if not changed:
                break
            guard += 1
        return [float(value) for value in points]

    def _expected_rate_blueprint_source_items(self, levels: list[str]) -> list:
        if self.exam is None or not self.exam.items:
            return [None for _ in levels]
        source_items = sorted(
            self.exam.items,
            key=lambda item: (
                {"쉬움": 0, "보통": 1, "어려움": 2}.get(getattr(item, "difficulty", ""), 1),
                getattr(item, "number", 0),
            ),
        )
        if not source_items:
            return [None for _ in levels]
        return [source_items[(idx - 1) % len(source_items)] for idx in range(1, len(levels) + 1)]

    @staticmethod
    def _expected_rate_blueprint_difficulty(target: str, source) -> str:
        if source is not None and getattr(source, "difficulty", "") in {"쉬움", "보통", "어려움"}:
            return getattr(source, "difficulty", "")
        if target in {"A", "B"}:
            return "어려움"
        if target == "C":
            return "보통"
        return "쉬움"

    @staticmethod
    def _expected_rate_blueprint_note(target: str, difficulty: str, points: float, content: str) -> str:
        base = f"{target} 수준 문항 제안 · {difficulty} · {points:g}점"
        if content:
            base += f" · 참고 내용영역: {content}"
        return base

    def _render_spliter_tab(self):
        if not hasattr(self, "lbl_spliter_status"):
            return
        if self.exam is None or self.overall is None:
            self.lbl_spliter_status.setText("분석 전 · 계산기는 아래에서 바로 사용할 수 있습니다.")
            return
        select_count = len(self.exam.select_items)
        serdap_count = len(self.exam.serdap_items)
        serdap_text = f" · 서답형 {serdap_count}문항" if serdap_count else ""
        self.lbl_spliter_status.setText(
            f"<b>분석자료</b>: {self.exam.subject or '(과목 미상)'} · "
            f"학생 {len(self.exam.students)}명 · 선택형 근거 문항 {select_count}개{serdap_text} · "
            f"분할점수 A≥{self.exam.cut_scores['A']:.0f} B≥{self.exam.cut_scores['B']:.0f} "
            f"C≥{self.exam.cut_scores['C']:.0f} D≥{self.exam.cut_scores['D']:.0f} E≥{self.exam.cut_scores['E']:.0f}"
        )

    # ---- Data 탭 -----------------------------------------------------
    def _init_tab_data(self):
        layout = QVBoxLayout(self.tab_data)
        # KPI 카드 — 좁은 창에서 자동으로 2열/1열로 접힘
        self.kpi_grid = QGridLayout(); self.kpi_grid.setSpacing(8)
        self.kpi_n = self._kpi_card("전체 학생 수", "-")
        self.kpi_n_items = self._kpi_card("문항 수", "-")
        self.kpi_subject = self._kpi_card("과목", "-")
        self._kpis = [self.kpi_n, self.kpi_n_items, self.kpi_subject]
        self._relayout_kpis(cols=3)
        layout.addLayout(self.kpi_grid)

        # 학생 검색창 (이름·반/번호로 즉시 필터)
        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("학생 검색:"))
        self.le_search = QLineEdit()
        self.le_search.setPlaceholderText("이름 또는 반/번호 입력 · 여러 명은 쉼표로 구분 (예: 강예서, 신태빈, 1/3)")
        self.le_search.textChanged.connect(self._filter_data_table)
        search_row.addWidget(self.le_search, 1)
        self.lbl_search_status = QLabel("")
        self.lbl_search_status.setProperty("role", "muted")
        search_row.addWidget(self.lbl_search_status)
        btn_monitor = QPushButton("모니터링 탭")
        btn_monitor.clicked.connect(self._open_monitoring_tab)
        search_row.addWidget(btn_monitor)
        self.btn_clear_search = QPushButton("✕")
        self.btn_clear_search.setFixedWidth(self._px(32))
        self.btn_clear_search.clicked.connect(lambda: self.le_search.setText(""))
        search_row.addWidget(self.btn_clear_search)
        layout.addLayout(search_row)

        # 차트 ↔ 표 splitter
        data_split = QSplitter(Qt.Vertical)
        self.score_chart_tabs = QTabWidget()
        self.canvas_score_hist = CanvasHolder()
        self.score_chart_tabs.addTab(self.canvas_score_hist, "환산점수 분포")

        normal_page = QWidget()
        normal_layout = QVBoxLayout(normal_page); normal_layout.setContentsMargins(0, 0, 0, 0)
        self.canvas_score_normal = CanvasHolder()
        normal_layout.addWidget(self.canvas_score_normal, 1)
        self.lbl_normal_note = QLabel(
            "정규분포 곡선은 현재 학급 점수의 평균과 표준편차를 기준으로 한 참고선입니다. "
            "현장 모니터링에서는 실제 학교·교과 상황과 함께 해석하세요."
        )
        self.lbl_normal_note.setProperty("role", "muted"); self.lbl_normal_note.setWordWrap(True)
        normal_layout.addWidget(self.lbl_normal_note)
        self.score_chart_tabs.addTab(normal_page, "정규분포·점검")
        data_split.addWidget(self.score_chart_tabs)

        self.table_data = QTableWidget(0, 0)
        _setup_table(self.table_data, word_wrap=False, horizontal_scroll=True)
        self.table_data.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table_data.setSortingEnabled(True)  # 헤더 클릭으로 정렬
        data_split.addWidget(self.table_data)

        data_split.setStretchFactor(0, 1); data_split.setStretchFactor(1, 2)
        data_split.setSizes([240, 380])
        layout.addWidget(data_split, 1)

        self.lbl_data_note = QLabel(
            "▸ 표 머리글을 클릭하면 정렬됩니다 ▸ '학생 검색'으로 즉시 필터 ▸ 그래프 위 마우스 휠로 확대/축소\n"
            "성취수준은 반영비율을 고려한 100점 만점 환산점수를 반올림하여 정수로 변환한 원점수 기준."
        )
        self.lbl_data_note.setProperty("role", "muted"); self.lbl_data_note.setWordWrap(True)
        layout.addWidget(self.lbl_data_note)

    # ---- 모니터링 ------------------------------------------------------
    def _make_collapsible_panel(self, title: str, body: QWidget) -> QFrame:
        panel = QFrame()
        panel.setProperty("role", "card")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(8)

        toggle = QToolButton()
        toggle.setText(title)
        toggle.setCheckable(True)
        toggle.setChecked(True)
        toggle.setArrowType(Qt.DownArrow)
        toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        toggle.setProperty("role", "collapsebtn")

        def _sync(opened: bool):
            body.setVisible(opened)
            toggle.setArrowType(Qt.DownArrow if opened else Qt.RightArrow)

        toggle.toggled.connect(_sync)
        layout.addWidget(toggle)
        layout.addWidget(body)
        return panel

    def _init_tab_monitor(self):
        layout = QVBoxLayout(self.tab_monitor)
        head_row = QHBoxLayout()
        intro = QLabel(
            "현재 과목의 A 비율, 과목 평균, A/B 분할점수를 "
            "동일 학교유형·교과군의 전국 평균±표준편차 및 전년도 값과 비교합니다. "
            "전국 기준값은 외부 모니터링 자료가 있을 때 입력하세요."
        )
        intro.setProperty("role", "muted")
        intro.setWordWrap(True)
        head_row.addWidget(intro, 1)
        btn_refresh = QPushButton("새로고침")
        btn_refresh.clicked.connect(self._refresh_monitoring_tab)
        head_row.addWidget(btn_refresh)
        layout.addLayout(head_row)

        top_area = QWidget()
        top_layout = QVBoxLayout(top_area)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(8)
        current_grid = QGridLayout(); current_grid.setSpacing(8)
        self.monitor_current_cards = {
            "a_pct": self._kpi_card("현재 A 비율", "-"),
            "mean": self._kpi_card("현재 과목 평균", "-"),
            "std": self._kpi_card("현재 표준편차", "-"),
            "cut_a": self._kpi_card("현재 A/B 분할점수", "-"),
        }
        for i, card in enumerate(self.monitor_current_cards.values()):
            current_grid.addWidget(card, 0, i)
        top_layout.addLayout(current_grid)

        self.monitor_spins: dict[str, StepperSpinBox] = {}
        input_row = QSplitter(Qt.Horizontal)
        national_body = QWidget()
        national_form = QFormLayout(national_body); national_form.setLabelAlignment(Qt.AlignRight)
        self._add_monitor_spin(national_form, "ref_a_mean", "A 비율 평균", 0.0, suffix=" %")
        self._add_monitor_spin(national_form, "ref_a_sd", "A 비율 표준편차", 0.0, suffix=" %p")
        self._add_monitor_spin(national_form, "ref_mean_mean", "과목 평균", 0.0, suffix=" 점")
        self._add_monitor_spin(national_form, "ref_mean_sd", "과목 평균 표준편차", 0.0, suffix=" 점")
        self._add_monitor_spin(national_form, "ref_cut_mean", "A/B 분할점수 평균", 0.0, suffix=" 점")
        self._add_monitor_spin(national_form, "ref_cut_sd", "A/B 분할점수 표준편차", 0.0, suffix=" 점")
        national_box = self._make_collapsible_panel("동일 학교유형·교과군 전국 기준", national_body)
        input_row.addWidget(national_box)

        history_body = QWidget()
        history_form = QFormLayout(history_body); history_form.setLabelAlignment(Qt.AlignRight)
        self._add_monitor_spin(history_form, "prev_a_pct", "전년도 A 비율", 0.0, suffix=" %")
        self._add_monitor_spin(history_form, "prev_mean", "전년도 과목 평균", 0.0, suffix=" 점")
        self._add_monitor_spin(history_form, "prev_cut_a", "전년도 A/B 분할점수", 0.0, suffix=" 점")
        self._add_monitor_spin(history_form, "th_a_delta", "A 비율 증가 기준", 10.0, suffix=" %p")
        self._add_monitor_spin(history_form, "th_mean_stable", "평균 큰 변동 아님", 5.0, suffix=" 점")
        self._add_monitor_spin(history_form, "th_cut_delta", "분할점수 감소 기준", 10.0, suffix=" 점")
        history_box = self._make_collapsible_panel("전년도·판정 기준", history_body)
        input_row.addWidget(history_box)
        input_row.setStretchFactor(0, 1); input_row.setStretchFactor(1, 1)
        top_layout.addWidget(input_row, 1)

        body = QSplitter(Qt.Vertical)
        self.canvas_monitor = CanvasHolder()
        body.addWidget(self.canvas_monitor)

        flow_note = QLabel(
            "점검 흐름: 1단계 A 비율 변화 확인 → 2단계 대상교·학생 특성 확인 → "
            "3단계 지필평가 특성 확인 → 4단계 분할점수 재산출 → 5단계 A 비율 재산정"
        )
        flow_note.setProperty("role", "muted")
        flow_note.setWordWrap(True)

        table_wrap = QWidget()
        table_layout = QVBoxLayout(table_wrap); table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.addWidget(flow_note)
        self.table_monitor = QTableWidget(0, 5)
        self.table_monitor.setHorizontalHeaderLabels(["지표", "현재/변화", "기준", "판정", "해석·질문"])
        _setup_table(self.table_monitor, word_wrap=True, horizontal_scroll=True, row_height=42)
        self.table_monitor.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        table_layout.addWidget(self.table_monitor, 1)
        body.addWidget(table_wrap)
        body.setStretchFactor(0, 1); body.setStretchFactor(1, 2)
        body.setSizes([260, 360])
        monitor_split = QSplitter(Qt.Vertical)
        monitor_split.addWidget(top_area)
        monitor_split.addWidget(body)
        monitor_split.setStretchFactor(0, 0)
        monitor_split.setStretchFactor(1, 1)
        monitor_split.setSizes([250, 620])
        layout.addWidget(monitor_split, 1)
        self._render_monitor_tab()

    def _refresh_monitoring_tab(self):
        self._render_monitor_tab()
        self.statusBar().showMessage("모니터링 탭을 새로고침했습니다.", 2500)

    def _add_monitor_spin(self, form: QFormLayout, key: str, label: str, value: float,
                          *, suffix: str = ""):
        spin = StepperSpinBox(value=value, minimum=-100.0, maximum=200.0,
                              step=1.0, decimals=1, suffix=suffix)
        spin.valueChanged.connect(lambda *_: self._render_monitor_tab())
        self.monitor_spins[key] = spin
        form.addRow(label, spin)
        return spin

    def _monitor_value(self, key: str) -> float:
        spin = getattr(self, "monitor_spins", {}).get(key)
        return float(spin.value()) if spin is not None else 0.0

    def _monitor_z_status(self, value: float, ref: float, sd: float, *, low_is_risk: bool = False):
        if sd <= 0:
            return "기준 입력 필요", "전국 평균과 표준편차를 입력하면 Ⅰ/Ⅱ/Ⅲ 수준을 자동 판정합니다.", 0
        z = (ref - value) / sd if low_is_risk else (value - ref) / sd
        if z >= 2:
            return "Ⅲ 점검", f"전국 평균에서 {'아래로' if low_is_risk else '위로'} {z:.2f}σ 벗어났습니다.", 3
        if z >= 1:
            return "Ⅱ 주의", f"전국 평균에서 {'아래로' if low_is_risk else '위로'} {z:.2f}σ 벗어났습니다.", 2
        return "참고 범위", f"전국 평균±1σ 안쪽 또는 위험 방향이 아닙니다. z={z:.2f}", 1

    def _monitor_rows_and_benchmarks(self):
        if self.exam is None or self.overall is None:
            return [], []
        a_pct = float(self.overall.level_dist_pct.get("A", 0.0))
        mean = float(self.overall.mean)
        std = float(self.overall.std)
        cut_a = float(self.exam.cut_scores.get("A", 0.0))
        prev_a = self._monitor_value("prev_a_pct")
        prev_mean = self._monitor_value("prev_mean")
        prev_cut = self._monitor_value("prev_cut_a")
        th_a = self._monitor_value("th_a_delta")
        th_mean = self._monitor_value("th_mean_stable")
        th_cut = self._monitor_value("th_cut_delta")

        rows = []
        status, detail, sev = self._monitor_z_status(
            a_pct, self._monitor_value("ref_a_mean"), self._monitor_value("ref_a_sd")
        )
        rows.append((
            "필수 1 · 성취수준 A 비율이 높음",
            f"{a_pct:.1f}%",
            "전국 평균+1σ 이상: Ⅱ · +2σ 이상: Ⅲ",
            status,
            f"{detail} A 비율만으로 단정하지 않고 평균·분할점수와 함께 봅니다.",
            sev,
        ))

        if mean >= cut_a:
            status, detail, sev = "Ⅲ 점검", "과목 평균이 A/B 분할점수 이상입니다.", 3
        elif cut_a - mean <= 3:
            status, detail, sev = "Ⅱ 주의", "과목 평균이 A/B 분할점수에 매우 가깝습니다.", 2
        else:
            status, detail, sev = "참고 범위", "과목 평균이 A/B 분할점수보다 낮습니다.", 1
        rows.append((
            "필수 2 · 과목 평균이 A/B 분할점수보다 높음",
            f"평균 {mean:.1f}점 / A/B {cut_a:.1f}점",
            "평균 ≥ A/B 분할점수이면 점검",
            status,
            f"{detail} 평균 학생이 A 수준 경계 위에 놓이는지 보는 지표입니다.",
            sev,
        ))

        status, detail, sev = self._monitor_z_status(
            mean, self._monitor_value("ref_mean_mean"), self._monitor_value("ref_mean_sd")
        )
        rows.append((
            "특성 3 · 과목 평균이 높음",
            f"{mean:.1f}점",
            "전국 평균+1σ 이상: 주의 · +2σ 이상: 점검",
            status,
            f"{detail} 평가도구가 쉬웠는지, 학생 특성이 높은지 함께 봅니다.",
            sev,
        ))

        status, detail, sev = self._monitor_z_status(
            cut_a, self._monitor_value("ref_cut_mean"), self._monitor_value("ref_cut_sd"),
            low_is_risk=True,
        )
        rows.append((
            "특성 4 · A/B 분할점수가 낮음",
            f"{cut_a:.1f}점",
            "전국 평균-1σ 이하: 주의 · -2σ 이하: 점검",
            status,
            f"{detail} A 비율이 높은 원인이 낮은 분할점수인지 확인합니다.",
            sev,
        ))

        if prev_a <= 0 or prev_mean <= 0:
            status, detail, sev = "기준 입력 필요", "전년도 A 비율과 과목 평균을 입력하면 판정합니다.", 0
            current = "-"
        else:
            delta_a = a_pct - prev_a
            delta_mean = mean - prev_mean
            current = f"A {delta_a:+.1f}%p / 평균 {delta_mean:+.1f}점"
            if delta_a >= th_a and abs(delta_mean) <= th_mean:
                status, detail, sev = "특성 발생", "평균은 크게 변하지 않았는데 A 비율이 증가했습니다.", 3
            elif delta_a >= th_a:
                status, detail, sev = "Ⅱ 주의", "A 비율은 증가했지만 평균도 함께 변했습니다.", 2
            else:
                status, detail, sev = "참고 범위", "A 비율 증가 폭이 기준보다 작습니다.", 1
        rows.append((
            "특성 5 · 평균 큰 변동 없이 A 비율 증가",
            current,
            f"A 증가 ≥ {th_a:.1f}%p, 평균 변화 ≤ {th_mean:.1f}점",
            status,
            f"{detail} 역동적 성적 과대평가 가능성을 묻는 지표입니다.",
            sev,
        ))

        if prev_a <= 0 or prev_cut <= 0:
            status, detail, sev = "기준 입력 필요", "전년도 A 비율과 A/B 분할점수를 입력하면 판정합니다.", 0
            current = "-"
        else:
            delta_a = a_pct - prev_a
            cut_drop = prev_cut - cut_a
            current = f"A {delta_a:+.1f}%p / A/B {cut_a - prev_cut:+.1f}점"
            if delta_a >= th_a and cut_drop >= th_cut:
                status, detail, sev = "특성 발생", "A 비율 증가와 A/B 분할점수 감소가 함께 나타났습니다.", 3
            elif delta_a >= th_a and cut_drop > 0:
                status, detail, sev = "Ⅱ 주의", "A 비율 증가와 A/B 분할점수 감소가 함께 보입니다.", 2
            else:
                status, detail, sev = "참고 범위", "두 조건이 동시에 충분히 나타나지 않았습니다.", 1
        rows.append((
            "특성 6 · A 비율 증가 + A/B 분할점수 감소",
            current,
            f"A 증가 ≥ {th_a:.1f}%p, A/B 감소 ≥ {th_cut:.1f}점",
            status,
            f"{detail} 쉬워진 평가도구인지, 낮아진 분할점수인지 추가 확인합니다.",
            sev,
        ))

        benchmarks = [
            {
                "label": "A 비율",
                "value": a_pct,
                "ref": self._monitor_value("ref_a_mean") if self._monitor_value("ref_a_sd") > 0 else None,
                "sd": self._monitor_value("ref_a_sd") if self._monitor_value("ref_a_sd") > 0 else None,
                "color": "#ef4444",
            },
            {
                "label": "과목 평균",
                "value": mean,
                "ref": self._monitor_value("ref_mean_mean") if self._monitor_value("ref_mean_sd") > 0 else None,
                "sd": self._monitor_value("ref_mean_sd") if self._monitor_value("ref_mean_sd") > 0 else None,
                "color": "#f59e0b",
            },
            {
                "label": "A/B 분할점수",
                "value": cut_a,
                "ref": self._monitor_value("ref_cut_mean") if self._monitor_value("ref_cut_sd") > 0 else None,
                "sd": self._monitor_value("ref_cut_sd") if self._monitor_value("ref_cut_sd") > 0 else None,
                "color": "#2a7770",
            },
        ]
        return rows, benchmarks

    def _render_monitor_tab(self):
        if not hasattr(self, "table_monitor"):
            return
        if self.exam is None or self.overall is None:
            for card in getattr(self, "monitor_current_cards", {}).values():
                card.value_label.setText("-")
            self.table_monitor.setRowCount(0)
            if hasattr(self, "canvas_monitor"):
                self.canvas_monitor.set_figure(charts.fig_monitoring_benchmarks([]))
            return

        a_pct = float(self.overall.level_dist_pct.get("A", 0.0))
        self.monitor_current_cards["a_pct"].value_label.setText(f"{a_pct:.1f}%")
        self.monitor_current_cards["mean"].value_label.setText(f"{self.overall.mean:.1f}점")
        self.monitor_current_cards["std"].value_label.setText(f"{self.overall.std:.1f}점")
        self.monitor_current_cards["cut_a"].value_label.setText(f"{self.exam.cut_scores.get('A', 0):.1f}점")

        rows, benchmarks = self._monitor_rows_and_benchmarks()
        self.canvas_monitor.set_figure(charts.fig_monitoring_benchmarks(benchmarks))

        self.table_monitor.setSortingEnabled(False)
        self.table_monitor.setRowCount(len(rows))
        colors = self.theme.colors if self.theme else {}
        shade = QColor(colors.get("shade", "#e1e6ee"))
        warn = QColor("#f8dfa3"); warn.setAlpha(150)
        danger = QColor("#f5b5b5"); danger.setAlpha(165)
        ok = QColor(colors.get("card", "#f4f7f8"))
        for r, row in enumerate(rows):
            bg = danger if row[5] >= 3 else warn if row[5] == 2 else shade if row[5] == 0 else ok
            for c, value in enumerate(row[:5]):
                _set_item(
                    self.table_monitor,
                    r,
                    c,
                    value,
                    align_left=(c in (0, 4)),
                    bg=bg if c == 3 else None,
                    bold=(c == 3),
                    tooltip=str(value),
                )
        self.table_monitor.setSortingEnabled(False)
        for col, width in enumerate([250, 180, 260, 120, 520]):
            self._set_scaled_column_width(self.table_monitor, col, width)
        self._apply_zoom_to_surfaces()

    def _relayout_kpis(self, cols: int):
        """KPI 카드들을 cols 개수만큼 한 행에 배치."""
        # 기존 위치 모두 제거 (위젯은 보존)
        for k in self._kpis:
            self.kpi_grid.removeWidget(k)
        for i, k in enumerate(self._kpis):
            r, c = divmod(i, max(1, cols))
            self.kpi_grid.addWidget(k, r, c)

    def _kpi_card(self, label: str, value: str) -> QFrame:
        frame = QFrame()
        frame.setProperty("role", "kpi")
        v = QVBoxLayout(frame); v.setContentsMargins(14, 10, 14, 10); v.setSpacing(2)
        l1 = QLabel(label); l1.setProperty("role", "kpi-label")
        l2 = QLabel(value); l2.setProperty("role", "kpi-value")
        v.addWidget(l1); v.addWidget(l2)
        frame.value_label = l2
        return frame

    # ---- 전체 성취도 ----------------------------------------------------
    def _init_tab_overview(self):
        layout = QVBoxLayout(self.tab_overview)

        ov_split = QSplitter(Qt.Vertical)

        # 위쪽: 도넛 + 평균±표준편차
        top_widget = QWidget(); top_l = QHBoxLayout(top_widget); top_l.setContentsMargins(0,0,0,0)
        self.canvas_level_stack = CanvasHolder()
        self.canvas_level_means = CanvasHolder()
        top_l.addWidget(self.canvas_level_stack, 1)
        top_l.addWidget(self.canvas_level_means, 1)
        ov_split.addWidget(top_widget)

        # 가운데: 성취수준 표
        self.table_level = QTableWidget(0, 5)
        self.table_level.setHorizontalHeaderLabels(["성취수준", "학생수", "비율(%)", "평균(원점수)", "표준편차"])
        _setup_table(self.table_level)
        ov_split.addWidget(self.table_level)

        # 아래: 학급별 평균
        self.canvas_class = CanvasHolder()
        ov_split.addWidget(self.canvas_class)

        ov_split.setSizes([340, 200, 280])
        ov_split.setStretchFactor(0, 3); ov_split.setStretchFactor(1, 1); ov_split.setStretchFactor(2, 2)
        layout.addWidget(ov_split, 1)

    # ---- 수행평가 분석 --------------------------------------------------
    def _init_tab_perform(self):
        layout = QVBoxLayout(self.tab_perform)

        head_row = QHBoxLayout()
        self.lbl_perform_tab_note = QLabel(
            "수행평가 영역별 점수율, 지필총점과의 관계, 학생별 차이를 함께 봅니다. "
            "왼쪽 입력 패널에서 수행평가 파일을 지정하고 체크한 뒤 분석을 실행하세요."
        )
        self.lbl_perform_tab_note.setProperty("role", "muted")
        self.lbl_perform_tab_note.setWordWrap(True)
        head_row.addWidget(self.lbl_perform_tab_note, 1)
        btn_refresh = QPushButton("새로고침")
        btn_refresh.clicked.connect(self._refresh_perform_tab)
        head_row.addWidget(btn_refresh)
        layout.addLayout(head_row)

        grid = QGridLayout(); grid.setSpacing(8)
        self.perform_cards = {
            "ratio": self._kpi_card("수행 반영비율", "-"),
            "areas": self._kpi_card("수행 영역", "-"),
            "matched": self._kpi_card("매칭 학생", "-"),
            "corr": self._kpi_card("지필-수행 상관", "-"),
        }
        for i, card in enumerate(self.perform_cards.values()):
            grid.addWidget(card, 0, i)
        layout.addLayout(grid)

        split = QSplitter(Qt.Vertical)

        chart_row = QWidget()
        chart_layout = QHBoxLayout(chart_row); chart_layout.setContentsMargins(0, 0, 0, 0)
        self.canvas_perform_area = CanvasHolder()
        self.canvas_perform_scatter = CanvasHolder()
        chart_layout.addWidget(self.canvas_perform_area, 1)
        chart_layout.addWidget(self.canvas_perform_scatter, 1)
        split.addWidget(chart_row)

        table_tabs = QTabWidget()
        self.perform_table_tabs = table_tabs
        self.table_perform_areas = QTableWidget(0, 14)
        self.table_perform_areas.setHorizontalHeaderLabels([
            "영역", "만점", "반영비율", "평균", "표준편차", "평균점수율",
            "만점자", "50% 미만", "A", "B", "C", "D", "E", "미도달",
        ])
        _setup_table(self.table_perform_areas, word_wrap=False, horizontal_scroll=True, row_height=30)
        self.table_perform_areas.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self._perform_area_bar_delegate = ItemBarDelegate(self.table_perform_areas)
        self.table_perform_areas.setItemDelegateForColumn(5, self._perform_area_bar_delegate)
        table_tabs.addTab(self.table_perform_areas, "영역별 요약")

        self.table_perform_students = QTableWidget(0, 7)
        self.table_perform_students.setHorizontalHeaderLabels([
            "반/번호", "이름", "성취도", "지필총점", "수행환산", "수행-지필", "해석",
        ])
        _setup_table(self.table_perform_students, word_wrap=False, horizontal_scroll=True, row_height=30)
        self.table_perform_students.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        table_tabs.addTab(self.table_perform_students, "학생별 차이")

        recalc_page = QWidget()
        recalc_layout = QVBoxLayout(recalc_page)
        recalc_layout.setContentsMargins(8, 8, 8, 8)
        recalc_layout.setSpacing(8)

        recalc_head = QHBoxLayout()
        self.lbl_perform_recalc_note = QLabel(
            "평가요소별로 A~E 최소능력자가 받을 것으로 예상되는 점수를 넣으면 "
            "수행평가 분할점수가 자동 계산됩니다."
        )
        self.lbl_perform_recalc_note.setProperty("role", "muted")
        self.lbl_perform_recalc_note.setWordWrap(True)
        recalc_head.addWidget(self.lbl_perform_recalc_note, 1)
        btn_perf_recommend = QPushButton("자료 기준 딸깍 추천")
        btn_perf_recommend.clicked.connect(self._recommend_perform_recalc_rows)
        recalc_head.addWidget(btn_perf_recommend)
        btn_perf_default = QPushButton("기본안")
        btn_perf_default.clicked.connect(self._reset_perform_recalc_rows)
        recalc_head.addWidget(btn_perf_default)
        btn_perf_add = QPushButton("평가요소 추가")
        btn_perf_add.clicked.connect(self._add_perform_recalc_row)
        recalc_head.addWidget(btn_perf_add)
        btn_perf_del = QPushButton("선택 삭제")
        btn_perf_del.clicked.connect(self._delete_selected_perform_recalc_rows)
        recalc_head.addWidget(btn_perf_del)
        recalc_layout.addLayout(recalc_head)

        cut_grid = QGridLayout(); cut_grid.setSpacing(8)
        self.perform_recalc_cards = {
            "max": self._kpi_card("수행 만점", "-"),
            "A": self._kpi_card("A/B", "-"),
            "B": self._kpi_card("B/C", "-"),
            "C": self._kpi_card("C/D", "-"),
            "D": self._kpi_card("D/E", "-"),
            "E": self._kpi_card("E/미도달", "-"),
            "check": self._kpi_card("점검", "-"),
        }
        for i, card in enumerate(self.perform_recalc_cards.values()):
            cut_grid.addWidget(card, i // 4, i % 4)
        recalc_layout.addLayout(cut_grid)

        recalc_split = QSplitter(Qt.Vertical)
        self.table_perform_recalc = QTableWidget(0, 8)
        self.table_perform_recalc.setHorizontalHeaderLabels([
            "평가요소", "만점", "A 예상", "B 예상", "C 예상", "D 예상", "E 예상", "근거/메모",
        ])
        _setup_table(self.table_perform_recalc, word_wrap=False, horizontal_scroll=True, row_height=32)
        self.table_perform_recalc.setEditTriggers(
            QAbstractItemView.DoubleClicked
            | QAbstractItemView.EditKeyPressed
            | QAbstractItemView.AnyKeyPressed
        )
        self.table_perform_recalc.itemChanged.connect(self._render_perform_recalc_results)
        recalc_split.addWidget(self.table_perform_recalc)

        self.table_perform_recalc_results = QTableWidget(0, 4)
        self.table_perform_recalc_results.setHorizontalHeaderLabels(["경계", "원점수", "100점 환산", "의미"])
        _setup_table(self.table_perform_recalc_results, word_wrap=False, horizontal_scroll=True, row_height=30)
        recalc_split.addWidget(self.table_perform_recalc_results)
        recalc_split.setStretchFactor(0, 3)
        recalc_split.setStretchFactor(1, 1)
        recalc_split.setSizes([330, 170])
        recalc_layout.addWidget(recalc_split, 1)
        table_tabs.addTab(recalc_page, "분할점수 재산정")

        split.addWidget(table_tabs)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 2)
        split.setSizes([300, 430])
        layout.addWidget(split, 1)
        self._reset_perform_recalc_rows()
        self._render_perform_tab()

    def _refresh_perform_tab(self):
        self._render_perform_tab()
        self.statusBar().showMessage("수행평가 분석 탭을 새로고침했습니다.", 2500)

    def _set_perform_recalc_item(self, row: int, col: int, value, *, align_right=False):
        item = QTableWidgetItem("" if value is None else str(value))
        item.setTextAlignment((Qt.AlignRight if align_right else Qt.AlignLeft) | Qt.AlignVCenter)
        self.table_perform_recalc.setItem(row, col, item)
        return item

    def _add_perform_recalc_row(self, values: dict | None = None):
        if not hasattr(self, "table_perform_recalc"):
            return
        user_added = values is None
        values = values or {}
        if user_added:
            self._perform_recalc_dirty = True
        table = self.table_perform_recalc
        table.blockSignals(True)
        row = table.rowCount()
        table.insertRow(row)
        max_score = float(values.get("max_score", 10.0))
        name = values.get("name", f"평가요소 {row + 1}")
        self._set_perform_recalc_item(row, 0, name)
        self._set_perform_recalc_item(row, 1, f"{max_score:.1f}", align_right=True)
        for idx, lv in enumerate(LEVELS_AE, start=2):
            default = max_score * PERFORM_DEFAULT_RATES[lv]
            score = float(values.get(lv, default))
            self._set_perform_recalc_item(row, idx, f"{score:.1f}", align_right=True)
        self._set_perform_recalc_item(row, 7, values.get("memo", ""))
        table.blockSignals(False)
        self._render_perform_recalc_results()

    def _reset_perform_recalc_rows(self):
        if not hasattr(self, "table_perform_recalc"):
            return
        self._perform_recalc_dirty = False
        self.table_perform_recalc.blockSignals(True)
        self.table_perform_recalc.setRowCount(0)
        self.table_perform_recalc.blockSignals(False)
        if self.perform_data is not None and getattr(self.perform_data, "areas", None):
            self._recommend_perform_recalc_rows()
            return
        self._add_perform_recalc_row({"name": "평가요소 1", "max_score": 10.0, "memo": "성취율 기준 기본안"})
        self._add_perform_recalc_row({"name": "평가요소 2", "max_score": 10.0, "memo": "성취율 기준 기본안"})
        self._add_perform_recalc_row({"name": "평가요소 3", "max_score": 10.0, "memo": "성취율 기준 기본안"})

    def _delete_selected_perform_recalc_rows(self):
        if not hasattr(self, "table_perform_recalc"):
            return
        rows = sorted({idx.row() for idx in self.table_perform_recalc.selectedIndexes()}, reverse=True)
        if not rows:
            return
        self._perform_recalc_dirty = True
        self.table_perform_recalc.blockSignals(True)
        for row in rows:
            self.table_perform_recalc.removeRow(row)
        self.table_perform_recalc.blockSignals(False)
        self._render_perform_recalc_results()

    def _recommended_perform_scores_by_area(self):
        recommendations = []
        if self.perform_data is None or not getattr(self.perform_data, "areas", None):
            return recommendations
        matches = self._perform_matches()
        for area in self.perform_data.areas:
            values = {"name": area.name, "max_score": float(area.max_score)}
            for lv in LEVELS_AE:
                candidates = []
                for _, student, level, rec in matches:
                    if level != lv:
                        continue
                    candidates.append((float(student.final_score), float(rec.scores.get(area.name, 0.0))))
                candidates.sort(key=lambda item: item[0])
                if candidates:
                    chosen = candidates[: min(3, len(candidates))]
                    score = sum(score for _, score in chosen) / len(chosen)
                else:
                    score = float(area.max_score) * PERFORM_DEFAULT_RATES[lv]
                values[lv] = max(0.0, min(float(area.max_score), score))
            prev = float(area.max_score)
            for lv in LEVELS_AE:
                values[lv] = min(values[lv], prev)
                prev = values[lv]
            values["memo"] = "현재 자료의 성취수준별 하위 대표 3명 평균"
            recommendations.append(values)
        return recommendations

    def _recommend_perform_recalc_rows(self):
        if not hasattr(self, "table_perform_recalc"):
            return
        rows = self._recommended_perform_scores_by_area()
        if not rows:
            rows = [
                {"name": "평가요소 1", "max_score": 10.0, "memo": "자료 없음 · 성취율 기준"},
                {"name": "평가요소 2", "max_score": 10.0, "memo": "자료 없음 · 성취율 기준"},
                {"name": "평가요소 3", "max_score": 10.0, "memo": "자료 없음 · 성취율 기준"},
            ]
        self._perform_recalc_dirty = False
        table = self.table_perform_recalc
        table.blockSignals(True)
        table.setRowCount(0)
        table.blockSignals(False)
        for row in rows:
            self._add_perform_recalc_row(row)
        self.statusBar().showMessage("수행평가 분할점수 재산정 기본값을 적용했습니다.", 3000)

    def _perform_recalc_rows(self):
        if not hasattr(self, "table_perform_recalc"):
            return [], []
        rows = []
        warnings = []
        table = self.table_perform_recalc
        for r in range(table.rowCount()):
            name_item = table.item(r, 0)
            name = name_item.text().strip() if name_item else f"평가요소 {r + 1}"
            try:
                max_score = float((table.item(r, 1).text() if table.item(r, 1) else "0").replace(",", ""))
            except Exception:
                max_score = 0.0
                warnings.append(f"{name}: 만점 숫자 확인")
            level_scores = {}
            for idx, lv in enumerate(LEVELS_AE, start=2):
                try:
                    score = float((table.item(r, idx).text() if table.item(r, idx) else "0").replace(",", ""))
                except Exception:
                    score = 0.0
                    warnings.append(f"{name}: {lv} 예상점수 숫자 확인")
                if score < 0 or score > max_score:
                    warnings.append(f"{name}: {lv} 예상점수 범위 확인")
                level_scores[lv] = max(0.0, min(max_score, score))
            rows.append({"name": name, "max_score": max_score, "scores": level_scores})
        return rows, warnings

    def _render_perform_recalc_results(self, *changed_items):
        if not hasattr(self, "table_perform_recalc_results"):
            return
        if changed_items:
            self._perform_recalc_dirty = True
        rows, warnings = self._perform_recalc_rows()
        max_total = sum(row["max_score"] for row in rows)
        totals = {
            lv: sum(row["scores"].get(lv, 0.0) for row in rows)
            for lv in LEVELS_AE
        }
        for left, right in zip(LEVELS_AE, LEVELS_AE[1:]):
            if totals[left] + 1e-9 < totals[right]:
                warnings.append(f"{left}/{right} 역전")

        if hasattr(self, "perform_recalc_cards"):
            self.perform_recalc_cards["max"].value_label.setText(f"{max_total:.1f}")
            for lv in LEVELS_AE:
                self.perform_recalc_cards[lv].value_label.setText(f"{totals[lv]:.1f}")
            self.perform_recalc_cards["check"].value_label.setText(str(len(warnings)))

        result_rows = [
            ("A/B", totals["A"], "A 최소능력자 예상점수 합"),
            ("B/C", totals["B"], "B 최소능력자 예상점수 합"),
            ("C/D", totals["C"], "C 최소능력자 예상점수 합"),
            ("D/E", totals["D"], "D 최소능력자 예상점수 합"),
            ("E/미도달", totals["E"], "E 최소능력자 예상점수 합"),
        ]
        table = self.table_perform_recalc_results
        table.setSortingEnabled(False)
        table.setRowCount(len(result_rows) + (1 if warnings else 0))
        for r, (label, raw, meaning) in enumerate(result_rows):
            pct = raw / max_total * 100.0 if max_total > 0 else 0.0
            _set_item(table, r, 0, label)
            _set_item(table, r, 1, f"{raw:.2f}", align_right=True)
            _set_item(table, r, 2, f"{pct:.1f}", align_right=True)
            _set_item(table, r, 3, meaning, align_left=True, tooltip=meaning)
        if warnings:
            warn_text = " · ".join(dict.fromkeys(warnings))
            bg = QColor("#f8dfa3"); bg.setAlpha(150)
            r = len(result_rows)
            _set_item(table, r, 0, "점검", bg=bg, bold=True)
            _set_item(table, r, 1, len(warnings), align_right=True, bg=bg)
            _set_item(table, r, 2, "-", bg=bg)
            _set_item(table, r, 3, warn_text, align_left=True, bg=bg, tooltip=warn_text)
        table.setSortingEnabled(False)
        for col, width in enumerate([92, 90, 100, 360]):
            self._set_scaled_column_width(table, col, width)
        for col, width in enumerate([210, 76, 82, 82, 82, 82, 82, 260]):
            self._set_scaled_column_width(self.table_perform_recalc, col, width)

    # ---- 문항 분석 -----------------------------------------------------
    def _init_tab_items(self):
        layout = QVBoxLayout(self.tab_items)
        self.lbl_alpha = QLabel("지필평가 신뢰도 (Cronbach's alpha): -")
        f = self.lbl_alpha.font(); f.setPointSize(f.pointSize()+3); f.setBold(True); self.lbl_alpha.setFont(f)
        layout.addWidget(self.lbl_alpha)

        sub = QLabel("선다형 문항 분석 결과 (음영: 성취수준별 정답률 2/3 미만)")
        sub.setStyleSheet("color:#888;")
        layout.addWidget(sub)

        # 통합 문항분석 테이블 — 컬럼이 16개라 가로스크롤 허용
        headers = ["문항", "예상난이도", "정답률(%)", "변별도",
                   "1", "2", "3", "4", "5", "무응답",
                   "A", "B", "C", "D", "E", "미도달"]
        self.table_items = QTableWidget(0, len(headers))
        self.table_items.setHorizontalHeaderLabels(headers)
        _setup_table(self.table_items, word_wrap=False, horizontal_scroll=True, row_height=30)
        self.table_items.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        # 정답률(idx 2), 변별도(idx 3) 컬럼에 막대 그리기
        self._item_bar_delegate = ItemBarDelegate(self.table_items)
        self.table_items.setItemDelegateForColumn(2, self._item_bar_delegate)
        self.table_items.setItemDelegateForColumn(3, self._item_bar_delegate)

        # 서답형 분석 표 (별도) — 원본 웹앱과 동일 형식
        sub2 = QLabel("서답형 문항 분석 결과")
        f = sub2.font(); f.setBold(True); f.setPointSize(f.pointSize()+1); sub2.setFont(f)
        layout.addWidget(sub2)
        sd_headers = ["서답형", "최솟값", "최댓값", "평균", "표준편차", "정답률(%)", "변별도",
                      "A", "B", "C", "D", "E", "미도달"]
        self.table_serdap = QTableWidget(0, len(sd_headers))
        self.table_serdap.setHorizontalHeaderLabels(sd_headers)
        _setup_table(self.table_serdap, word_wrap=False, row_height=30)
        self.table_serdap.setMaximumHeight(self._px(110))
        # 정답률, 변별도 컬럼에 막대 표시
        self._serdap_bar_delegate = ItemBarDelegate(self.table_serdap)
        self.table_serdap.setItemDelegateForColumn(5, self._serdap_bar_delegate)
        self.table_serdap.setItemDelegateForColumn(6, self._serdap_bar_delegate)
        layout.addWidget(self.table_serdap)

        # 표와 보조 차트 사이를 splitter로 감싸 비율 조절 가능
        body = QSplitter(Qt.Vertical)
        body.addWidget(self.table_items)
        chart_row = QWidget(); chr_l = QHBoxLayout(chart_row); chr_l.setContentsMargins(0,0,0,0)
        self.canvas_pvalue = CanvasHolder()
        self.canvas_discr = CanvasHolder()
        chr_l.addWidget(self.canvas_pvalue, 1)
        chr_l.addWidget(self.canvas_discr, 1)
        body.addWidget(chart_row)
        body.setStretchFactor(0, 2); body.setStretchFactor(1, 1)
        body.setSizes([400, 280])
        layout.addWidget(body, 1)

    # ---- 답지반응분포 ---------------------------------------------------
    def _init_tab_choice(self):
        layout = QVBoxLayout(self.tab_choice)
        top = QHBoxLayout()
        top.addWidget(QLabel("답지반응분석 문항:"))
        self.combo_item = QComboBox()
        self.combo_item.currentIndexChanged.connect(self._refresh_choice)
        top.addWidget(self.combo_item, 1)
        layout.addLayout(top)

        self.lbl_choice_info = QLabel("")
        self.lbl_choice_info.setWordWrap(True)
        self.lbl_choice_info.setProperty("role", "muted")
        layout.addWidget(self.lbl_choice_info)

        # 표↔차트 사이 splitter (사용자가 비율 조절)
        choice_split = QSplitter(Qt.Vertical)
        # 매트릭스 표
        self.table_choice = QTableWidget(0, 8)
        self.table_choice.setHorizontalHeaderLabels(
            ["성취수준", "정답률(%)", "1", "2", "3", "4", "5", "무응답"])
        _setup_table(self.table_choice)
        choice_split.addWidget(self.table_choice)
        # 답지반응분포 차트
        self.canvas_choice = CanvasHolder()
        choice_split.addWidget(self.canvas_choice)
        choice_split.setStretchFactor(0, 1); choice_split.setStretchFactor(1, 2)
        choice_split.setSizes([240, 360])
        layout.addWidget(choice_split, 1)

    # ---- 성취기준 분석 --------------------------------------------------
    def _init_tab_standard(self):
        layout = QVBoxLayout(self.tab_standard)
        sub = QLabel("성취기준별 평균 정답률 (음영: 성취율 50% 이하 · 셀 안 막대 = 정답률)")
        sub.setProperty("role", "muted"); layout.addWidget(sub)
        headers = ["성취기준", "문항수", "전체(%)", "A", "B", "C", "D", "E", "미도달"]
        self.table_std = QTableWidget(0, len(headers))
        self.table_std.setHorizontalHeaderLabels(headers)
        # 첫 컬럼은 Stretch, 나머지는 Fixed
        _setup_table(self.table_std, word_wrap=False, row_height=30)
        self.table_std.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        hh = self.table_std.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        for i in range(1, len(headers)):
            hh.setSectionResizeMode(i, QHeaderView.Fixed)
            self._set_scaled_column_width(self.table_std, i, 72)
        self.table_std.setSortingEnabled(True)
        # 전체 성취율 컬럼에 막대 그리기
        self._std_bar_delegate = ItemBarDelegate(self.table_std)
        self.table_std.setItemDelegateForColumn(2, self._std_bar_delegate)
        # 표/차트를 splitter로 묶어서 사용자가 비율 조절 + 차트는 ScrollArea로 잘림 방지
        std_split = QSplitter(Qt.Vertical)
        std_split.addWidget(self.table_std)
        self.canvas_std = CanvasHolder()
        std_chart_scroll = QScrollArea(); std_chart_scroll.setWidgetResizable(True)
        std_chart_scroll.setWidget(self.canvas_std)
        std_split.addWidget(std_chart_scroll)
        std_split.setStretchFactor(0, 2); std_split.setStretchFactor(1, 3)
        std_split.setSizes([280, 420])
        layout.addWidget(std_split, 1)

    # ---- AI 문항 검토 --------------------------------------------------
    def _init_tab_ai_review(self):
        layout = QVBoxLayout(self.tab_ai_review)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        head = QHBoxLayout()
        head.addStretch(1)
        self.btn_ai_load_source = QPushButton("문항 자료")
        self.btn_ai_load_source.setToolTip(
            "시험 문제 HWPX/PDF, 문항정보표, 수행평가 채점기준표를 문항 자료 칸으로 불러옵니다."
        )
        self.btn_ai_load_source.clicked.connect(self._load_ai_review_file)
        head.addWidget(self.btn_ai_load_source)
        btn_reference = QPushButton("성취기준·수준 자료")
        btn_reference.setToolTip("성취기준, 성취수준, 최소능력자 설명 자료를 참고자료 칸에 불러옵니다.")
        btn_reference.clicked.connect(self._load_ai_reference_file)
        head.addWidget(btn_reference)
        btn_written_example = QPushButton("지필 예시")
        btn_written_example.setToolTip("지필평가 문항 예시를 원문 칸에 넣어 흐름을 테스트합니다.")
        btn_written_example.clicked.connect(lambda: self._insert_ai_review_example("written"))
        head.addWidget(btn_written_example)
        btn_perform_example = QPushButton("수행 예시")
        btn_perform_example.setToolTip("수행평가 채점기준표 예시를 원문 칸에 넣어 흐름을 테스트합니다.")
        btn_perform_example.clicked.connect(lambda: self._insert_ai_review_example("perform"))
        head.addWidget(btn_perform_example)
        btn_exam = QPushButton("현재 문항정보표")
        btn_exam.clicked.connect(self._load_ai_review_from_exam)
        head.addWidget(btn_exam)
        self.btn_ai_generate = QPushButton("검토 초안 생성")
        self.btn_ai_generate.setProperty("role", "primary")
        self.btn_ai_generate.clicked.connect(self._generate_ai_review_draft)
        head.addWidget(self.btn_ai_generate)
        self.btn_ai_enrich = QPushButton("AI로 보강")
        self.btn_ai_enrich.setToolTip("AI 설정에 지정한 로컬/클라우드 모델로 검토 초안을 보강합니다.")
        self.btn_ai_enrich.clicked.connect(self._run_ai_review_completion)
        head.addWidget(self.btn_ai_enrich)
        self.btn_ai_review_stop = QPushButton("보강 중지")
        self.btn_ai_review_stop.setToolTip("현재 응답 중인 묶음이 끝난 뒤 AI 보강을 멈춥니다.")
        self.btn_ai_review_stop.clicked.connect(self._request_ai_review_stop)
        self.btn_ai_review_stop.setEnabled(False)
        head.addWidget(self.btn_ai_review_stop)
        self.btn_ai_review_resume = QPushButton("이어하기")
        self.btn_ai_review_resume.setToolTip("중지된 AI 보강을 다음 묶음부터 이어서 진행합니다.")
        self.btn_ai_review_resume.clicked.connect(self._resume_ai_review_completion)
        self.btn_ai_review_resume.setEnabled(False)
        head.addWidget(self.btn_ai_review_resume)
        btn_to_spliter = QPushButton("지필→예상정답률")
        btn_to_spliter.clicked.connect(self._send_ai_review_to_spliter)
        head.addWidget(btn_to_spliter)
        btn_to_perform = QPushButton("수행→재산정")
        btn_to_perform.clicked.connect(self._send_ai_review_to_perform_recalc)
        head.addWidget(btn_to_perform)
        btn_export = QPushButton("CSV 내보내기…")
        btn_export.clicked.connect(self._export_ai_review_csv)
        head.addWidget(btn_export)
        layout.addLayout(head)

        card_grid = QGridLayout(); card_grid.setSpacing(8)
        self.ai_review_cards = {
            "rows": self._kpi_card("검토 항목", "-"),
            "standards": self._kpi_card("성취기준", "-"),
            "warnings": self._kpi_card("점검", "-"),
            "mode": self._kpi_card("AI 상태", "로컬 초안"),
        }
        for i, card in enumerate(self.ai_review_cards.values()):
            card_grid.addWidget(card, 0, i)
        layout.addLayout(card_grid)

        split = QSplitter(Qt.Horizontal)
        left = QWidget()
        left_layout = QVBoxLayout(left); left_layout.setContentsMargins(0, 0, 0, 0); left_layout.setSpacing(6)
        left_title = QLabel("입력 자료")
        left_title.setProperty("role", "title")
        left_layout.addWidget(left_title)

        self.ai_review_input_tabs = QTabWidget()
        source_panel = QWidget()
        source_layout = QVBoxLayout(source_panel); source_layout.setContentsMargins(0, 0, 0, 0)
        source_tools = QHBoxLayout()
        self.lbl_ai_source_store = QLabel()
        self.lbl_ai_source_store.setProperty("role", "muted")
        self.lbl_ai_source_store.setWordWrap(False)
        source_tools.addWidget(self.lbl_ai_source_store, 1)
        btn_source_store_location = QPushButton("위치")
        btn_source_store_location.setToolTip("문항 자료가 저장되는 앱 자료 폴더 위치를 확인합니다.")
        btn_source_store_location.clicked.connect(lambda: self._show_ai_store_location("source"))
        source_tools.addWidget(btn_source_store_location)
        btn_load_saved_source = QPushButton("저장자료 불러오기")
        btn_load_saved_source.setToolTip("앱 자료 폴더에 저장된 문항 자료를 선택해 다시 불러옵니다.")
        btn_load_saved_source.clicked.connect(self._load_saved_ai_source_text)
        source_tools.addWidget(btn_load_saved_source)
        btn_save_source_text = QPushButton("현재 내용 저장")
        btn_save_source_text.setToolTip("현재 문항 자료 칸의 내용을 앱 자료 폴더에 저장합니다.")
        btn_save_source_text.clicked.connect(lambda: self._save_current_ai_text("source"))
        source_tools.addWidget(btn_save_source_text)
        source_layout.addLayout(source_tools)
        self.ai_source_view_tabs = QTabWidget()
        self.txt_ai_review_source = QPlainTextEdit()
        self.txt_ai_review_source.setPlaceholderText(
            "시험 문제 HWPX/PDF에서 추출한 문항, 문항정보표, 수행평가 채점기준표를 붙여 넣거나 '문항 자료'로 불러오세요."
        )
        self.ai_source_view_tabs.addTab(self.txt_ai_review_source, "편집")
        self.browser_ai_review_source = QTextBrowser()
        self.browser_ai_review_source.setReadOnly(True)
        self.browser_ai_review_source.setOpenExternalLinks(False)
        self._style_ai_markdown_browser(self.browser_ai_review_source)
        self.ai_source_view_tabs.addTab(self.browser_ai_review_source, "미리보기")
        self.txt_ai_review_source.textChanged.connect(
            lambda: self._update_ai_markdown_preview("source")
        )
        source_layout.addWidget(self.ai_source_view_tabs, 1)
        self.ai_review_input_tabs.addTab(source_panel, "문항 자료")

        reference_panel = QWidget()
        reference_layout = QVBoxLayout(reference_panel); reference_layout.setContentsMargins(0, 0, 0, 0)
        reference_tools = QHBoxLayout()
        self.lbl_ai_reference_store = QLabel()
        self.lbl_ai_reference_store.setProperty("role", "muted")
        self.lbl_ai_reference_store.setWordWrap(False)
        reference_tools.addWidget(self.lbl_ai_reference_store, 1)
        btn_reference_store_location = QPushButton("위치")
        btn_reference_store_location.setToolTip("성취기준·수준 자료가 저장되는 앱 자료 폴더 위치를 확인합니다.")
        btn_reference_store_location.clicked.connect(lambda: self._show_ai_store_location("reference"))
        reference_tools.addWidget(btn_reference_store_location)
        btn_load_saved_reference = QPushButton("저장자료 불러오기")
        btn_load_saved_reference.setToolTip("앱 자료 폴더에 저장된 성취기준·수준 자료를 선택해 다시 불러옵니다.")
        btn_load_saved_reference.clicked.connect(self._load_saved_ai_reference_text)
        reference_tools.addWidget(btn_load_saved_reference)
        btn_save_reference_text = QPushButton("현재 내용 저장")
        btn_save_reference_text.setToolTip("현재 성취기준·수준 칸의 내용을 앱 자료 폴더에 저장합니다.")
        btn_save_reference_text.clicked.connect(lambda: self._save_current_ai_text("reference"))
        reference_tools.addWidget(btn_save_reference_text)
        reference_layout.addLayout(reference_tools)
        self.txt_ai_review_reference = QPlainTextEdit()
        self.txt_ai_review_reference.setPlaceholderText(
            "성취기준, 성취수준 A~E 설명, 최소능력자 특성, 평가기준 자료를 붙여 넣거나 '성취기준·수준 자료'로 불러오세요."
        )
        self.ai_reference_view_tabs = QTabWidget()
        self.ai_reference_view_tabs.addTab(self.txt_ai_review_reference, "편집")
        self.browser_ai_review_reference = QTextBrowser()
        self.browser_ai_review_reference.setReadOnly(True)
        self.browser_ai_review_reference.setOpenExternalLinks(False)
        self._style_ai_markdown_browser(self.browser_ai_review_reference)
        self.ai_reference_view_tabs.addTab(self.browser_ai_review_reference, "미리보기")
        self.txt_ai_review_reference.textChanged.connect(
            lambda: self._update_ai_markdown_preview("reference")
        )
        reference_layout.addWidget(self.ai_reference_view_tabs, 1)
        self.ai_review_input_tabs.addTab(reference_panel, "성취기준·수준")
        left_layout.addWidget(self.ai_review_input_tabs, 1)
        split.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right); right_layout.setContentsMargins(0, 0, 0, 0); right_layout.setSpacing(6)
        self.ai_review_tabs = QTabWidget()
        self.table_ai_review = QTableWidget(0, len(AI_REVIEW_HEADERS))
        self.table_ai_review.setHorizontalHeaderLabels(AI_REVIEW_HEADERS)
        _setup_table(self.table_ai_review, word_wrap=False, horizontal_scroll=True, row_height=32)
        self.table_ai_review.setEditTriggers(
            QAbstractItemView.DoubleClicked
            | QAbstractItemView.EditKeyPressed
            | QAbstractItemView.AnyKeyPressed
        )
        self.ai_review_tabs.addTab(self.table_ai_review, "검토 초안")
        self.txt_ai_review_prompt = QPlainTextEdit()
        self.txt_ai_review_prompt.setReadOnly(True)
        self.txt_ai_review_prompt.setPlaceholderText("검토 초안을 만들면 AI 연결용 프롬프트가 여기에 생성됩니다.")
        self.ai_review_tabs.addTab(self.txt_ai_review_prompt, "AI 프롬프트")
        self.txt_ai_progress = QPlainTextEdit()
        self.txt_ai_progress.setReadOnly(True)
        self.txt_ai_progress.setPlaceholderText("AI 연결, 서버 탐색, 보강 요청의 진행 상황이 여기에 표시됩니다.")
        self.ai_review_tabs.addTab(self.txt_ai_progress, "진행 로그")
        self.ai_review_tabs.addTab(self._build_ai_usage_panel(), "사용 예시")
        self.ai_review_tabs.addTab(self._build_ai_settings_panel(), "AI 설정")
        right_layout.addWidget(self.ai_review_tabs, 1)
        split.addWidget(right)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 2)
        split.setSizes([420, 780])
        layout.addWidget(split, 1)
        self.lbl_ai_review_footer = QLabel(
            "AI 문항 검토는 교사 검토를 돕는 초안입니다. 자세한 흐름과 예시는 오른쪽 '사용 예시' 탭에서 확인하세요."
        )
        self.lbl_ai_review_footer.setProperty("role", "muted")
        self.lbl_ai_review_footer.setWordWrap(True)
        layout.addWidget(self.lbl_ai_review_footer, 0)
        self._refresh_ai_source_store_label()
        self._refresh_ai_reference_store_label()
        self._set_ai_review_summary(0, 0, 0)

    @staticmethod
    def _style_ai_markdown_browser(browser: QTextBrowser):
        browser.document().setDefaultStyleSheet("""
            body {
                line-height: 1.55;
                font-size: 13px;
            }
            h1 {
                font-size: 20px;
                margin: 8px 0 10px;
            }
            h2 {
                font-size: 16px;
                margin: 14px 0 8px;
            }
            h3 {
                font-size: 14px;
                margin: 12px 0 6px;
            }
            p {
                margin: 5px 0;
            }
            ul, ol {
                margin-top: 4px;
                margin-bottom: 8px;
            }
            li {
                margin: 3px 0;
            }
            code {
                padding: 1px 4px;
            }
            pre {
                padding: 8px;
                white-space: pre-wrap;
            }
            table {
                border-collapse: collapse;
            }
            th, td {
                padding: 4px 6px;
                border: 1px solid #789;
            }
        """)

    def _update_ai_markdown_preview(self, target: str):
        if target == "reference":
            if not hasattr(self, "browser_ai_review_reference"):
                return
            text = self.txt_ai_review_reference.toPlainText()
            browser = self.browser_ai_review_reference
        else:
            if not hasattr(self, "browser_ai_review_source"):
                return
            text = self.txt_ai_review_source.toPlainText()
            browser = self.browser_ai_review_source
        try:
            browser.setMarkdown(text)
        except Exception:
            browser.setPlainText(text)

    def _build_ai_usage_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel); layout.setContentsMargins(10, 10, 10, 10)
        browser = QTextBrowser()
        browser.setReadOnly(True)
        browser.setOpenExternalLinks(False)
        browser.setHtml("""
        <style>
          body { line-height: 1.55; }
          h2 { margin: 0 0 8px; font-size: 18px; }
          h3 { margin: 16px 0 6px; font-size: 15px; }
          p { margin: 5px 0; }
          ol, ul { margin-top: 5px; }
          li { margin: 4px 0; }
          pre { padding: 10px; border: 1px solid #789; border-radius: 6px; white-space: pre-wrap; }
          code { padding: 1px 4px; border-radius: 4px; }
        </style>
        <h2>AI 문항 검토 사용 흐름</h2>
        <p><b>목적</b>: AI가 최종 판단을 대신하는 것이 아니라, 교사가 검토할 표를 먼저 채워 분할점수 산정의 출발점을 빠르게 만드는 것입니다.</p>
        <ol>
          <li><b>문항 자료</b> 칸에 시험 문제 PDF에서 추출한 문항, 문항정보표, 수행평가 채점기준표를 넣습니다.</li>
          <li><b>성취기준·수준</b> 칸에 성취기준, A~E 성취수준 설명, 최소능력자 특성 자료를 넣습니다. 여러 PDF를 한 번에 선택할 수 있고, 불러온 원본은 앱 자료 폴더에 저장됩니다.</li>
          <li>성취기준·수준 PDF는 원문 전체가 아니라 성취기준 코드와 A~E 성취수준 설명 중심으로 정리되어 표시됩니다.</li>
          <li><b>검토 초안 생성</b>을 누르면 앱 내부 규칙으로 문항을 먼저 나누고, 참고자료와 대조해 성취기준, 평가유형, 목표수준, 난이도, A~E 예상값을 만듭니다.</li>
          <li>로컬 AI를 연결했다면 <b>AI로 보강</b>을 눌러 근거와 판단을 더 정교하게 보강합니다.</li>
          <li>지필 문항은 <b>지필→예상정답률</b>, 수행평가는 <b>수행→재산정</b>으로 보냅니다.</li>
          <li>교사가 문항을 직접 보며 A~E 예상값을 수정하고 최종 분할점수를 확인합니다.</li>
        </ol>

        <h3>지필평가 예시 해석</h3>
        <p><code>C 예상 2/3</code>은 C 수준 최소능력자 3명 중 2명 정도가 맞힐 것 같다는 뜻입니다.</p>
        <p><code>A 수준 문항</code>은 A 학생만 맞히는 문항이라는 뜻이 아니라, A 수준 최소능력자 3명 중 약 2명이 해결할 수 있는 문항이라는 뜻으로 봅니다.</p>
        <p>AI 보강은 문항 자료만 보지 않고, 성취기준·수준 자료를 기준표로 삼아 어떤 성취기준과 성취수준에 가까운지 다시 판단합니다.</p>

        <h3>수행평가 예시 해석</h3>
        <p>수행평가는 O/X가 아니라 평가요소별 예상점수로 봅니다. 예를 들어 <code>B 예상 7.5점</code>은 B 수준 최소능력자가 해당 평가요소에서 대략 7.5점을 받을 것으로 본다는 뜻입니다.</p>

        <h3>로컬 AI 연결 예시</h3>
        <pre>ollama pull qwen2.5:7b
ollama serve</pre>
        <p>그 뒤 <b>AI 설정</b>에서 다음처럼 입력합니다.</p>
        <pre>AI 제공자: Ollama 로컬
엔드포인트: http://127.0.0.1:11434/api/chat
모델: qwen2.5:7b
API 키: 비워둠</pre>
        <p>MLX-LM, LM Studio처럼 OpenAI 호환 로컬 서버를 쓰면 제공자를 <b>MLX-LM / LM Studio 로컬</b>로 바꾸고, 서버가 알려주는 <code>/v1/chat/completions</code> 주소를 넣습니다. 앱의 <b>MLX 찾기</b> 또는 <b>MLX 서버 시작</b> 버튼으로 자동 설정할 수 있습니다.</p>
        <p>OpenAI 클라우드는 OAuth 로그인이 아니라 API Key 방식입니다. API Key를 넣고 사용할 수 있는 모델명을 입력해야 합니다.</p>
        """)
        layout.addWidget(browser, 1)
        return panel

    def _build_ai_settings_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel); layout.setContentsMargins(10, 10, 10, 10); layout.setSpacing(10)

        note = QLabel("AI 보강을 누를 때만 선택한 제공자를 호출합니다.")
        note.setProperty("role", "muted")
        note.setWordWrap(True)
        layout.addWidget(note)

        form_card = QFrame()
        form_card.setProperty("role", "card")
        form = QFormLayout(form_card)
        form.setContentsMargins(14, 12, 14, 12)
        form.setSpacing(8)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self.cmb_ai_provider = QComboBox()
        self.cmb_ai_provider.addItem("로컬 초안만 사용", "local_draft")
        self.cmb_ai_provider.addItem("Ollama 로컬", "ollama")
        self.cmb_ai_provider.addItem("MLX / LM Studio", "mlx_compatible")
        self.cmb_ai_provider.addItem("OpenAI 클라우드 API (API Key)", "openai_cloud")
        self.cmb_ai_provider.currentIndexChanged.connect(self._sync_ai_provider_defaults)
        form.addRow("AI 제공자", self.cmb_ai_provider)

        self.edit_ai_endpoint = QLineEdit()
        self.edit_ai_endpoint.setPlaceholderText("예: http://127.0.0.1:11434/api/chat")
        form.addRow("엔드포인트", self.edit_ai_endpoint)

        self.cmb_ai_model = QComboBox()
        self.cmb_ai_model.setEditable(True)
        self.cmb_ai_model.setInsertPolicy(QComboBox.NoInsert)
        self.cmb_ai_model.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.cmb_ai_model.lineEdit().setPlaceholderText("예: qwen2.5:7b, mlx-community/Qwen3.5-9B-OptiQ-4bit")
        self.edit_ai_model = self.cmb_ai_model.lineEdit()
        form.addRow("모델", self.cmb_ai_model)

        self.lbl_ai_model_hint = QLabel("MLX 찾기 또는 모델 새로고침을 누르면 감지된 모델과 추천값이 표시됩니다.")
        self.lbl_ai_model_hint.setProperty("role", "muted")
        self.lbl_ai_model_hint.setWordWrap(True)
        form.addRow("추천", self.lbl_ai_model_hint)

        self.edit_ai_api_key = QLineEdit()
        self.edit_ai_api_key.setEchoMode(QLineEdit.Password)
        self.edit_ai_api_key.setPlaceholderText("클라우드 또는 인증이 필요한 로컬 서버에서만 입력")
        form.addRow("API 키", self.edit_ai_api_key)

        self.spin_ai_timeout = QDoubleSpinBox()
        self.spin_ai_timeout.setRange(5, 600)
        self.spin_ai_timeout.setDecimals(0)
        self.spin_ai_timeout.setSingleStep(15)
        self.spin_ai_timeout.setSuffix(" 초")
        form.addRow("대기 시간", self.spin_ai_timeout)

        self.chk_ai_scrub = QCheckBox("클라우드/외부 서버로 보낼 때 학생 이름·반번호를 가능한 한 제거")
        form.addRow("개인정보", self.chk_ai_scrub)

        layout.addWidget(form_card)

        guide = QLabel("자세한 연결 방법은 '사용 예시' 탭에서 확인하세요.")
        guide.setProperty("role", "muted")
        guide.setWordWrap(True)
        layout.addWidget(guide)

        row = QHBoxLayout()
        btn_save = QPushButton("설정 저장")
        btn_save.setProperty("role", "primary")
        btn_save.clicked.connect(self._save_ai_settings)
        row.addWidget(btn_save)
        self.btn_ai_test = QPushButton("연결 테스트")
        self.btn_ai_test.clicked.connect(self._test_ai_connection)
        row.addWidget(self.btn_ai_test)
        self.btn_refresh_ai_models = QPushButton("모델 새로고침")
        self.btn_refresh_ai_models.setToolTip("현재 AI 제공자의 모델 목록을 다시 읽고 추천 모델을 선택합니다.")
        self.btn_refresh_ai_models.clicked.connect(self._refresh_ai_model_list)
        row.addWidget(self.btn_refresh_ai_models)
        self.btn_find_mlx = QPushButton("MLX 찾기")
        self.btn_find_mlx.setToolTip("실행 중인 MLX-LM/LM Studio 로컬 서버를 자동으로 찾아 설정합니다.")
        self.btn_find_mlx.clicked.connect(self._find_local_mlx_server)
        row.addWidget(self.btn_find_mlx)
        self.btn_start_mlx = QPushButton("MLX 서버 시작")
        self.btn_start_mlx.setToolTip("로컬에 설치된 mlx_lm.server를 실행합니다. 모델이 없으면 다운로드가 필요할 수 있습니다.")
        self.btn_start_mlx.clicked.connect(self._start_local_mlx_server)
        row.addWidget(self.btn_start_mlx)
        row.addStretch(1)
        layout.addLayout(row)

        self.lbl_ai_settings_status = QLabel("AI 설정을 저장하면 다음 실행 때도 유지됩니다.")
        self.lbl_ai_settings_status.setProperty("role", "muted")
        self.lbl_ai_settings_status.setWordWrap(True)
        layout.addWidget(self.lbl_ai_settings_status)
        layout.addStretch(1)
        self._load_ai_settings()
        return panel

    def _provider_from_combo(self) -> str:
        if not hasattr(self, "cmb_ai_provider"):
            return "local_draft"
        data = self.cmb_ai_provider.currentData()
        return str(data or "local_draft")

    def _provider_setting_value(self, provider: str, key: str, default: str = "") -> str:
        provider_key = f"ai/providers/{provider}/{key}"
        value = self.settings.value(provider_key, None)
        if value is None and str(self.settings.value("ai/provider", "")) == provider:
            value = self.settings.value(f"ai/{key}", default)
        if value is None:
            value = default
        return str(value)

    def _store_current_ai_provider_settings(self, provider: str | None = None):
        if not hasattr(self, "cmb_ai_provider"):
            return
        provider = provider or self._provider_from_combo()
        endpoint = normalize_endpoint(provider, self.edit_ai_endpoint.text())
        model = self._ai_model_text() or default_model(provider)
        model = self._sanitize_ai_model_for_provider(provider, model)
        api_key = self.edit_ai_api_key.text().strip()
        self.settings.setValue(f"ai/providers/{provider}/endpoint", endpoint)
        self.settings.setValue(f"ai/providers/{provider}/model", model)
        self.settings.setValue(f"ai/providers/{provider}/api_key", api_key)

    def _provider_model_note(self, provider: str) -> str:
        if provider == "local_draft":
            return "로컬 초안은 모델 선택이 필요하지 않습니다."
        if provider == "ollama":
            return "모델 새로고침을 누르면 설치된 Ollama 모델을 자동 감지하고 추천값을 선택합니다."
        if provider == "mlx_compatible":
            return "MLX 찾기 또는 모델 새로고침을 누르면 감지된 모델과 추천값이 표시됩니다."
        if provider == "openai_cloud":
            return "OpenAI API는 API Key 방식입니다. OAuth 로그인은 이 데스크톱 API 호출에 사용하지 않습니다."
        return "모델 새로고침을 누르면 서버의 모델 목록을 선택할 수 있습니다."

    @staticmethod
    def _is_ai_chat_model_candidate(model: str) -> bool:
        lowered = (model or "").lower()
        return not any(term in lowered for term in ("embed", "embedding", "rerank", "whisper"))

    @staticmethod
    def _sanitize_ai_model_for_provider(provider: str, model: str) -> str:
        model = (model or "").strip()
        lowered = model.lower()
        if not model:
            return default_model(provider)
        if provider == "ollama" and any(term in lowered for term in ("mlx-community/", "lmstudio-community/")):
            return default_model(provider)
        if provider == "mlx_compatible" and model == default_model("ollama"):
            return default_model(provider)
        if provider == "openai_cloud" and (
            any(term in lowered for term in ("mlx-community/", "lmstudio-community/"))
            or lowered in {default_model("ollama").lower(), default_model("openai_compatible").lower()}
        ):
            return default_model(provider)
        return model

    def _update_ai_provider_help(self, provider: str):
        if not hasattr(self, "lbl_ai_settings_status"):
            return
        if provider == "local_draft":
            status = "로컬 초안은 외부 AI를 호출하지 않습니다."
        elif provider == "ollama":
            status = "Ollama가 실행 중이어야 합니다. 모델 새로고침/연결 테스트가 설치된 채팅 모델을 감지합니다."
        elif provider == "mlx_compatible":
            status = "MLX-LM/LM Studio 로컬 서버의 /v1/chat/completions 주소를 사용합니다."
        elif provider == "openai_cloud":
            status = "OpenAI 클라우드는 OAuth가 아니라 API Key 방식입니다. 모델명과 API 키를 입력하세요."
        else:
            status = "OpenAI 호환 서버의 chat completions 엔드포인트를 입력하세요."
        self.lbl_ai_settings_status.setText(status)
        if hasattr(self, "lbl_ai_model_hint"):
            self.lbl_ai_model_hint.setText(self._provider_model_note(provider))

    def _load_ai_settings(self):
        if not hasattr(self, "cmb_ai_provider"):
            return
        provider = str(self.settings.value("ai/provider", "local_draft"))
        idx = self.cmb_ai_provider.findData(provider)
        self._loading_ai_settings = True
        self.cmb_ai_provider.blockSignals(True)
        self.cmb_ai_provider.setCurrentIndex(idx if idx >= 0 else 0)
        self.cmb_ai_provider.blockSignals(False)
        provider = self._provider_from_combo()
        endpoint = self._provider_setting_value(provider, "endpoint", default_endpoint(provider))
        model = self._sanitize_ai_model_for_provider(
            provider,
            self._provider_setting_value(provider, "model", default_model(provider)),
        )
        api_key = self._provider_setting_value(provider, "api_key", "")
        self.edit_ai_endpoint.setText(normalize_endpoint(provider, endpoint))
        self._set_ai_model_choices([], provider, recommended=model, select_recommended=True, note=self._provider_model_note(provider))
        self._set_ai_model_text(model or default_model(provider))
        self.edit_ai_api_key.setText(api_key)
        try:
            self.spin_ai_timeout.setValue(float(self.settings.value("ai/timeout", 120)))
        except Exception:
            self.spin_ai_timeout.setValue(120)
        scrub = self.settings.value("ai/scrub_personal_data", True)
        self.chk_ai_scrub.setChecked(str(scrub).lower() not in {"false", "0", "no"})
        self._ai_active_provider = provider
        self._loading_ai_settings = False
        self._update_ai_provider_help(provider)

    def _ai_model_text(self) -> str:
        if hasattr(self, "cmb_ai_model"):
            return self.cmb_ai_model.currentText().strip() or self.edit_ai_model.text().strip()
        return self.edit_ai_model.text().strip() if hasattr(self, "edit_ai_model") else ""

    def _set_ai_model_text(self, model: str):
        model = (model or "").strip()
        if hasattr(self, "cmb_ai_model"):
            idx = self.cmb_ai_model.findText(model)
            if idx >= 0:
                self.cmb_ai_model.setCurrentIndex(idx)
            else:
                self.cmb_ai_model.setEditText(model)
        elif hasattr(self, "edit_ai_model"):
            self.edit_ai_model.setText(model)

    @staticmethod
    def _model_size_hint(model: str) -> float:
        lowered = model.lower()
        matches = re.findall(r"(\d+(?:\.\d+)?)\s*b", lowered)
        if not matches:
            return 0.0
        try:
            return max(float(value) for value in matches)
        except Exception:
            return 0.0

    @classmethod
    def _recommend_ai_model(cls, models: list[str], provider: str) -> str:
        clean = [model for model in dict.fromkeys(m.strip() for m in models if m and m.strip())]
        if not clean:
            return default_model(provider)

        def score(model: str) -> tuple[float, str]:
            lowered = model.lower()
            value = 0.0
            if any(term in lowered for term in ("embed", "rerank", "vision", "whisper")):
                value -= 200
            if any(term in lowered for term in ("qwen", "gemma", "llama", "mistral")):
                value += 25
            if any(term in lowered for term in ("instruct", "chat", "it")):
                value += 18
            if "coder" in lowered:
                value -= 8
            if any(term in lowered for term in ("optiq", "mlx-community")):
                value += 8
            if "4bit" in lowered or "q4" in lowered:
                value += 5
            size = cls._model_size_hint(model)
            if 7 <= size <= 10:
                value += 70
            elif 11 <= size <= 15:
                value += 62
            elif 20 <= size <= 32:
                value += 48
            elif 3 <= size < 7:
                value += 38
            elif 1 <= size < 3:
                value += 18
            elif 0 < size < 1:
                value -= 25
            if provider == "ollama" and any(term in lowered for term in ("qwen2.5", "gemma", "llama3")):
                value += 10
            return value, model

        return max(clean, key=score)

    def _set_ai_model_choices(
        self,
        models: list[str],
        provider: str,
        recommended: str = "",
        select_recommended: bool = True,
        note: str = "",
    ):
        if not hasattr(self, "cmb_ai_model"):
            return
        raw_clean = [model for model in dict.fromkeys(m.strip() for m in models if m and m.strip())]
        clean = [model for model in raw_clean if self._is_ai_chat_model_candidate(model)]
        removed_count = len(raw_clean) - len(clean)
        if not clean:
            clean = raw_clean
        recommended = recommended or self._recommend_ai_model(clean, provider)
        if recommended and recommended not in clean and clean:
            recommended = self._recommend_ai_model(clean, provider)
        current = self._ai_model_text()
        self.cmb_ai_model.blockSignals(True)
        self.cmb_ai_model.clear()
        for model in clean:
            self.cmb_ai_model.addItem(model)
        target = recommended if select_recommended and recommended else current
        if target and target not in clean:
            self.cmb_ai_model.addItem(target)
        self.cmb_ai_model.blockSignals(False)
        self._set_ai_model_text(target or default_model(provider))
        if clean:
            hint = f"감지 모델 {len(clean)}개"
            if recommended:
                size = self._model_size_hint(recommended)
                size_note = " · 균형 추천" if 7 <= size <= 15 else (" · 고품질/느림" if size >= 20 else " · 빠른 확인용")
                hint += f" · 추천: {recommended}{size_note}"
            if note:
                hint += f" · {note}"
            if removed_count:
                hint += f" · 비채팅 모델 {removed_count}개 숨김"
            self.lbl_ai_model_hint.setText(hint)
        else:
            self.lbl_ai_model_hint.setText(note or "감지된 모델이 없습니다. 모델명을 직접 입력할 수 있습니다.")

    def _save_ai_settings(self):
        if not hasattr(self, "cmb_ai_provider"):
            return
        provider = self._provider_from_combo()
        endpoint = normalize_endpoint(provider, self.edit_ai_endpoint.text())
        self.edit_ai_endpoint.setText(endpoint)
        model = self._ai_model_text() or default_model(provider)
        model = self._sanitize_ai_model_for_provider(provider, model)
        self._set_ai_model_text(model)
        api_key = self.edit_ai_api_key.text().strip()
        self.settings.setValue("ai/provider", provider)
        self.settings.setValue("ai/endpoint", endpoint)
        self.settings.setValue("ai/model", model)
        self.settings.setValue("ai/api_key", api_key)
        self.settings.setValue("ai/timeout", int(self.spin_ai_timeout.value()))
        self.settings.setValue("ai/scrub_personal_data", self.chk_ai_scrub.isChecked())
        self.settings.setValue(f"ai/providers/{provider}/endpoint", endpoint)
        self.settings.setValue(f"ai/providers/{provider}/model", model)
        self.settings.setValue(f"ai/providers/{provider}/api_key", api_key)
        self.settings.sync()
        self._ai_active_provider = provider
        self.lbl_ai_settings_status.setText("AI 설정을 저장했습니다.")
        self.statusBar().showMessage("AI 설정 저장 완료", 3000)

    def _sync_ai_provider_defaults(self, *_args):
        provider = self._provider_from_combo()
        if getattr(self, "_loading_ai_settings", False):
            self._update_ai_provider_help(provider)
            return
        previous = getattr(self, "_ai_active_provider", None)
        if previous and previous != provider:
            self._store_current_ai_provider_settings(previous)
        endpoint = self._provider_setting_value(provider, "endpoint", default_endpoint(provider))
        model = self._sanitize_ai_model_for_provider(
            provider,
            self._provider_setting_value(provider, "model", default_model(provider)),
        )
        api_key = self._provider_setting_value(provider, "api_key", "")
        self.edit_ai_endpoint.setText(normalize_endpoint(provider, endpoint))
        self._set_ai_model_choices([], provider, recommended=model, select_recommended=True, note=self._provider_model_note(provider))
        self._set_ai_model_text(model or default_model(provider))
        self.edit_ai_api_key.setText(api_key)
        self._ai_active_provider = provider
        self.settings.setValue("ai/provider", provider)
        self.settings.sync()
        self._update_ai_provider_help(provider)

    def _ai_provider_config(self) -> AIProviderConfig:
        if not hasattr(self, "cmb_ai_provider"):
            return AIProviderConfig()
        provider = self._provider_from_combo()
        return AIProviderConfig(
            provider=provider,
            endpoint=normalize_endpoint(provider, self.edit_ai_endpoint.text()),
            model=self._sanitize_ai_model_for_provider(provider, self._ai_model_text() or default_model(provider)),
            api_key=self.edit_ai_api_key.text().strip(),
            timeout=int(self.spin_ai_timeout.value()),
        )

    def _append_ai_progress(self, message: str):
        stamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{stamp}] {message}"
        if hasattr(self, "txt_ai_progress"):
            self.txt_ai_progress.appendPlainText(line)
            self.ai_review_tabs.setCurrentWidget(self.txt_ai_progress)
        if hasattr(self, "lbl_ai_settings_status"):
            self.lbl_ai_settings_status.setText(message)
        self.statusBar().showMessage(message, 5000)

    def _set_ai_review_control_state(
        self,
        *,
        running: bool = False,
        can_resume: bool = False,
        stop_requested: bool = False,
    ):
        if hasattr(self, "btn_ai_review_stop"):
            self.btn_ai_review_stop.setEnabled(running and not stop_requested)
            self.btn_ai_review_stop.setText("중지 요청됨" if stop_requested else "보강 중지")
        if hasattr(self, "btn_ai_review_resume"):
            self.btn_ai_review_resume.setEnabled((not running) and can_resume)

    def _request_ai_review_stop(self):
        event = getattr(self, "_ai_review_cancel_event", None)
        if not getattr(self, "_ai_worker_active", False) or event is None:
            QMessageBox.information(self, "AI 문항 검토", "현재 중지할 AI 보강 작업이 없습니다.")
            return
        event.set()
        self._set_ai_review_control_state(running=True, can_resume=False, stop_requested=True)
        self._append_ai_progress("AI 보강 중지 요청 · 현재 응답 중인 묶음이 끝난 뒤 멈춥니다.")

    def _resume_ai_review_completion(self):
        state = getattr(self, "_ai_review_resume_state", None)
        if not state:
            QMessageBox.information(self, "AI 문항 검토", "이어갈 AI 보강 작업이 없습니다.")
            return
        self._run_ai_review_completion(resume_state=state)

    def _set_ai_busy(self, busy: bool, label: str = ""):
        for attr in (
            "btn_ai_enrich",
            "btn_ai_generate",
            "btn_ai_test",
            "btn_find_mlx",
            "btn_start_mlx",
            "btn_refresh_ai_models",
            "btn_ai_load_source",
        ):
            widget = getattr(self, attr, None)
            if widget is not None:
                widget.setEnabled(not busy)
        if busy:
            QApplication.setOverrideCursor(Qt.WaitCursor)
        else:
            while QApplication.overrideCursor() is not None:
                QApplication.restoreOverrideCursor()
        if busy and label:
            self._append_ai_progress(label)

    def _run_ai_background_task(self, title: str, func, on_success):
        if getattr(self, "_ai_worker_active", False):
            QMessageBox.information(self, title, "이미 AI 작업이 진행 중입니다. 진행 로그를 확인해 주세요.")
            return
        self._set_ai_busy(True, f"{title} 시작")
        events: queue.Queue = queue.Queue()
        self._ai_worker_active = True
        self._ai_worker_queue = events

        def progress(message: str):
            events.put(("progress", str(message)))

        def runner():
            try:
                events.put(("success", func(progress)))
            except Exception:
                events.put(("failure", traceback.format_exc()))

        worker = threading.Thread(target=runner, daemon=True, name=f"GoeduSplit-{title}")
        self._ai_worker_thread = worker
        worker.start()

        timer = QTimer(self)
        timer.setInterval(150)
        self._ai_worker_timer = timer

        def cleanup():
            timer.stop()
            timer.deleteLater()
            self._ai_worker_active = False
            self._ai_worker_queue = None
            self._ai_worker_thread = None
            self._ai_worker_timer = None
            self._set_ai_busy(False)

        def handle_success(result):
            try:
                on_success(result)
            except Exception:
                trace = traceback.format_exc()
                short = trace.strip().splitlines()[-1] if trace.strip() else "알 수 없는 오류"
                self._append_ai_progress(f"{title} 결과 반영 실패: {short}")
                if hasattr(self, "txt_ai_progress"):
                    self.txt_ai_progress.appendPlainText(trace)
                QMessageBox.warning(
                    self,
                    title,
                    f"결과를 화면에 반영하는 중 오류가 발생했습니다.\n{short}\n\n자세한 내용은 진행 로그를 확인해 주세요.",
                )
            finally:
                cleanup()

        def handle_failure(trace: str):
            try:
                short = trace.strip().splitlines()[-1] if trace.strip() else "알 수 없는 오류"
                self._append_ai_progress(f"{title} 실패: {short}")
                if hasattr(self, "txt_ai_progress"):
                    self.txt_ai_progress.appendPlainText(trace)
                QMessageBox.warning(
                    self,
                    title,
                    f"작업 중 오류가 발생했습니다.\n{short}\n\n자세한 내용은 진행 로그를 확인해 주세요.",
                )
            finally:
                if title == "AI 문항 검토":
                    self._ai_review_cancel_event = None
                    self._set_ai_review_control_state(
                        running=False,
                        can_resume=bool(getattr(self, "_ai_review_resume_state", None)),
                    )
                cleanup()

        def drain_events():
            while True:
                try:
                    kind, payload = events.get_nowait()
                except queue.Empty:
                    break
                if kind == "progress":
                    self._append_ai_progress(payload)
                elif kind == "success":
                    handle_success(payload)
                    break
                elif kind == "failure":
                    handle_failure(payload)
                    break
            if getattr(self, "_ai_worker_active", False) and not worker.is_alive() and events.empty():
                self._append_ai_progress(f"{title} 종료 상태를 확인하지 못했습니다. 다시 시도해 주세요.")
                cleanup()

        timer.timeout.connect(drain_events)
        timer.start()

    def _candidate_mlx_endpoints(self) -> list[str]:
        current = self.edit_ai_endpoint.text().strip() if hasattr(self, "edit_ai_endpoint") else ""
        raw = [
            "http://127.0.0.1:18080/v1/chat/completions",
            current,
            "http://127.0.0.1:8080/v1/chat/completions",
            "http://127.0.0.1:8000/v1/chat/completions",
            "http://127.0.0.1:1234/v1/chat/completions",
            "http://localhost:18080/v1/chat/completions",
            "http://localhost:8080/v1/chat/completions",
            "http://localhost:8000/v1/chat/completions",
            "http://localhost:1234/v1/chat/completions",
        ]
        endpoints = []
        for endpoint in raw:
            normalized = normalize_endpoint("mlx_compatible", endpoint)
            if normalized and normalized not in endpoints:
                endpoints.append(normalized)
        return endpoints

    def _probe_mlx_models(self) -> tuple[str, list[str], list[str]]:
        errors = []
        timeout = int(self.spin_ai_timeout.value()) if hasattr(self, "spin_ai_timeout") else 20
        for endpoint in self._candidate_mlx_endpoints():
            try:
                models = list_openai_compatible_models(
                    endpoint,
                    "",
                    "mlx_compatible",
                    min(timeout, 15),
                )
            except Exception as exc:
                errors.append(f"{endpoint}: {exc}")
                continue
            if models:
                return endpoint, models, errors
            errors.append(f"{endpoint}: 모델 목록이 비어 있습니다.")
        return "", [], errors

    def _refresh_ai_model_list(self):
        config = self._ai_provider_config()
        self._save_ai_settings()
        provider = config.provider
        if provider == "local_draft":
            self.lbl_ai_model_hint.setText("로컬 초안은 모델 선택이 필요하지 않습니다.")
            return
        endpoints = self._candidate_mlx_endpoints()

        def work(progress):
            progress("모델 목록 새로고침 시작")
            if provider == "ollama":
                progress("Ollama 모델 목록 확인 중")
                models = list_ollama_models(config.endpoint, min(config.timeout, 30))
                return {"provider": provider, "endpoint": config.endpoint, "models": models}
            if provider == "mlx_compatible":
                errors = []
                for endpoint in endpoints:
                    progress(f"MLX 모델 목록 확인 중: {endpoint}")
                    try:
                        models = list_openai_compatible_models(
                            endpoint,
                            "",
                            "mlx_compatible",
                            min(config.timeout, 30),
                        )
                    except Exception as exc:
                        errors.append(f"{endpoint}: {exc}")
                        continue
                    if models:
                        return {
                            "provider": provider,
                            "endpoint": endpoint,
                            "models": models,
                            "errors": errors,
                        }
                    errors.append(f"{endpoint}: 모델 목록이 비어 있습니다.")
                detail = "\n".join(errors[:5])
                raise ValueError(f"MLX/LM Studio 모델 목록을 읽지 못했습니다.\n{detail}")
            progress("OpenAI 호환 모델 목록 확인 중")
            models = list_openai_compatible_models(
                config.endpoint,
                config.api_key,
                provider,
                min(config.timeout, 30),
            )
            return {"provider": provider, "endpoint": config.endpoint, "models": models}

        def success(result):
            models = result.get("models") or []
            result_provider = result.get("provider") or provider
            endpoint = result.get("endpoint") or config.endpoint
            recommended = self._recommend_ai_model(models, result_provider)
            if endpoint:
                self.edit_ai_endpoint.setText(normalize_endpoint(result_provider, endpoint))
            self._set_ai_model_choices(
                models,
                result_provider,
                recommended=recommended,
                select_recommended=True,
                note="직접 다른 모델을 선택할 수 있습니다.",
            )
            self._save_ai_settings()
            message = f"모델 {len(models)}개 감지 · 추천 모델: {recommended}"
            self._append_ai_progress(message)

        self._run_ai_background_task("모델 새로고침", work, success)

    @staticmethod
    def _is_local_port_open(port: int, timeout: float = 0.25) -> bool:
        try:
            with socket.create_connection(("127.0.0.1", int(port)), timeout=timeout):
                return True
        except OSError:
            return False

    def _preferred_mlx_port(self) -> int:
        for port in (18080, 8080, 8000, 1234):
            if not self._is_local_port_open(port):
                return port
        return 18080

    def _find_local_mlx_server(self):
        config = AIProviderConfig(
            provider="mlx_compatible",
            endpoint=normalize_endpoint("mlx_compatible", self.edit_ai_endpoint.text()),
            model="",
            timeout=int(self.spin_ai_timeout.value()),
        )
        endpoints = self._candidate_mlx_endpoints()

        def work(progress):
            progress("MLX/LM Studio 로컬 서버 자동 탐색 시작")
            prepared, note = self._prepare_ai_connection_config_for_worker(config, endpoints, progress)
            models = list_openai_compatible_models(
                prepared.endpoint,
                "",
                "mlx_compatible",
                min(prepared.timeout, 30),
            )
            recommended = self._recommend_ai_model(models, "mlx_compatible")
            return {"config": prepared, "note": note, "models": models, "recommended": recommended}

        def success(result):
            prepared = result["config"]
            note = result.get("note", "")
            models = result.get("models") or []
            self._apply_prepared_ai_config(prepared, note)
            self._set_ai_model_choices(
                models,
                "mlx_compatible",
                recommended=result.get("recommended") or prepared.model,
                select_recommended=True,
                note="AI로 보강 품질을 높이려면 7B~15B급 모델을 권장합니다.",
            )
            message = f"MLX 서버 감지 완료 · {prepared.endpoint} · 모델 {prepared.model}"
            self.lbl_ai_settings_status.setText(message)
            self.statusBar().showMessage(message, 6000)

        self._run_ai_background_task("MLX 서버 찾기", work, success)

    def _start_local_mlx_server(self):
        exe = shutil.which("mlx_lm.server")
        if not exe:
            for version in ("3.14", "3.13", "3.12", "3.11"):
                known = Path(f"/Library/Frameworks/Python.framework/Versions/{version}/bin/mlx_lm.server")
                if known.exists():
                    exe = str(known)
                    break
        if not exe:
            QMessageBox.warning(
                self,
                "MLX 서버 시작",
                "mlx_lm.server 명령을 찾지 못했습니다.\n"
                "터미널에서 `pip install mlx-lm` 설치 후 다시 시도하세요.",
            )
            return
        current_model = self._ai_model_text() if hasattr(self, "edit_ai_model") else ""
        default_model_id = (
            current_model
            if current_model and current_model not in {"local-model", default_model("openai_compatible")}
            else default_model("mlx_compatible")
        )
        model, ok = QInputDialog.getText(
            self,
            "MLX 서버 시작",
            "사용할 MLX 모델 ID를 입력하세요.\n"
            "처음 사용하는 모델은 다운로드가 필요할 수 있습니다.\n"
            "연결 확인이 목적이면 작은 모델(Qwen3-0.6B-4bit)을 권장합니다.",
            text=default_model_id,
        )
        if not ok or not model.strip():
            return
        model = model.strip()
        open_ports = [port for port in (18080, 8080, 8000, 1234) if self._is_local_port_open(port)]
        if open_ports:
            port = open_ports[0]
            endpoint = f"http://127.0.0.1:{port}/v1/chat/completions"
            idx = self.cmb_ai_provider.findData("mlx_compatible")
            if idx >= 0:
                self.cmb_ai_provider.setCurrentIndex(idx)
            self.edit_ai_endpoint.setText(endpoint)
            self._set_ai_model_text(model)
            self._save_ai_settings()
            self._append_ai_progress(
                f"이미 열린 로컬 서버 포트 {port}를 발견했습니다. 새 서버를 띄우지 않고 연결 확인을 진행합니다."
            )
            QTimer.singleShot(300, self._find_local_mlx_server)
            return
        port = self._preferred_mlx_port()
        log_path = self._ai_reference_store_dir().parent / "mlx_server.log"
        try:
            log_file = open(log_path, "a", encoding="utf-8")
            process = subprocess.Popen(
                [exe, "--model", model, "--host", "127.0.0.1", "--port", str(port)],
                stdout=log_file,
                stderr=log_file,
                start_new_session=True,
            )
        except Exception as exc:
            QMessageBox.warning(self, "MLX 서버 시작", f"MLX 서버를 시작하지 못했습니다.\n{exc}")
            return
        self.mlx_server_process = process
        self.mlx_server_log_file = log_file
        idx = self.cmb_ai_provider.findData("mlx_compatible")
        if idx >= 0:
            self.cmb_ai_provider.setCurrentIndex(idx)
        self.edit_ai_endpoint.setText(f"http://127.0.0.1:{port}/v1/chat/completions")
        self._set_ai_model_text(model)
        self._save_ai_settings()
        self.lbl_ai_settings_status.setText(
            f"MLX 서버 시작 요청 완료. 5~20초 뒤 'MLX 찾기' 또는 '연결 테스트'를 누르세요. 로그: {log_path}"
        )
        self._append_ai_progress(f"MLX 서버 시작 요청 완료 · PID {process.pid} · 포트 {port} · 로그 {log_path}")
        QTimer.singleShot(7000, self._find_local_mlx_server)

    @staticmethod
    def _prepare_ai_connection_config_for_worker(
        config: AIProviderConfig,
        mlx_endpoints: list[str] | None = None,
        progress=None,
    ) -> tuple[AIProviderConfig, str]:
        def tell(message: str):
            if progress:
                progress(message)

        note = ""
        if config.provider == "openai_cloud" and not config.api_key:
            raise ValueError("OpenAI 클라우드는 OAuth 로그인이 아니라 API Key가 필요합니다. API 키를 입력해 주세요.")
        if config.provider == "ollama":
            tell("Ollama 서버 모델 목록 확인 중")
            models = list_ollama_models(config.endpoint, min(config.timeout, 20))
            if models:
                recommended = MainWindow._recommend_ai_model(models, "ollama")
                ordered = []
                for name in (config.model, recommended, *models):
                    name = (name or "").strip()
                    lowered = name.lower()
                    if not name or name in ordered:
                        continue
                    if name not in models:
                        continue
                    if any(term in lowered for term in ("embed", "rerank", "whisper")):
                        continue
                    ordered.append(name)
                probe_errors = []
                selected = ""
                for name in ordered[:5]:
                    tell(f"Ollama 짧은 실제 응답 확인 중: {name}")
                    probe_config = AIProviderConfig(
                        provider="ollama",
                        endpoint=config.endpoint,
                        model=name,
                        api_key=config.api_key,
                        timeout=min(max(config.timeout, 45), 120),
                    )
                    try:
                        output = run_completion(
                            '다음 JSON만 반환하세요: {"status":"ok"}',
                            probe_config,
                            max_tokens=96,
                        )
                    except Exception as exc:
                        probe_errors.append(f"{name}: {exc}")
                        continue
                    if output.strip():
                        selected = name
                        break
                    probe_errors.append(f"{name}: 빈 응답")
                if not selected:
                    detail = "\n".join(probe_errors[:5])
                    raise ValueError(
                        "Ollama 서버와 모델 목록은 확인했지만 실제 답변 가능한 채팅 모델을 찾지 못했습니다.\n"
                        "임베딩 모델은 문항 검토에 사용할 수 없습니다. `ollama pull qwen2.5:7b` 또는 "
                        "`ollama pull gemma3:12b` 같은 채팅 모델을 받은 뒤 다시 시도하세요.\n\n"
                        f"점검 내용:\n{detail}"
                    )
                if config.model != selected:
                    note = f"설치된 Ollama 모델을 감지해 모델을 {selected}(으)로 맞췄습니다."
                config.model = selected
            else:
                note = "Ollama 서버는 응답했지만 설치된 모델 목록이 비어 있습니다."
        elif config.provider == "mlx_compatible":
            errors = []
            endpoint = ""
            models = []
            selected_model = ""
            for candidate in mlx_endpoints or []:
                tell(f"MLX 서버 확인 중: {candidate}")
                try:
                    found = list_openai_compatible_models(
                        candidate,
                        "",
                        "mlx_compatible",
                        min(config.timeout, 15),
                    )
                except Exception as exc:
                    errors.append(f"{candidate}: {exc}")
                    continue
                if not found:
                    errors.append(f"{candidate}: 모델 목록이 비어 있습니다.")
                    continue
                models = found
                preferred = (
                    config.model
                    if config.model and config.model in found
                    else MainWindow._recommend_ai_model(found, "mlx_compatible")
                )
                tell(f"모델 목록 확인 성공: {preferred}")
                tell("짧은 실제 응답 확인 중")
                probe_config_timeout = min(max(config.timeout, 45), 120)
                try:
                    probe_openai_compatible_chat(
                        candidate,
                        "",
                        "mlx_compatible",
                        preferred,
                        probe_config_timeout,
                    )
                except Exception as exc:
                    errors.append(f"{candidate}: 모델 목록은 확인됐지만 짧은 응답 실패 - {exc}")
                    tell(f"응답 지연 또는 실패, 다음 서버 후보로 이동: {candidate}")
                    continue
                endpoint = candidate
                selected_model = preferred
                tell(f"실제 응답 확인 완료: {candidate}")
                break
            if not endpoint:
                detail = "\n".join(errors[:4])
                raise ValueError(
                    "MLX-LM/LM Studio 로컬 서버가 실제 응답 가능한 상태인지 확인하지 못했습니다.\n"
                    "서버 주소만 열려 있어도 큰 모델이 로딩 중이면 시간초과가 날 수 있습니다.\n"
                    "작은 모델로 먼저 확인하려면 터미널에서 다음처럼 실행하세요.\n"
                    "mlx_lm.server --model mlx-community/Qwen3-0.6B-4bit --host 127.0.0.1 --port 18080\n\n"
                    f"점검 내용:\n{detail}"
                )
            config.endpoint = endpoint
            if selected_model:
                if config.model != selected_model:
                    note = f"MLX 서버 실제 응답 모델을 감지해 모델을 {selected_model}(으)로 맞췄습니다."
                config.model = selected_model
            elif models and (not config.model or config.model not in models):
                config.model = MainWindow._recommend_ai_model(models, "mlx_compatible")
                note = f"MLX 서버 모델 목록을 감지해 모델을 {config.model}(으)로 맞췄습니다."
        elif config.provider == "openai_compatible":
            tell("OpenAI 호환 서버 모델 목록 확인 중")
            try:
                models = list_openai_compatible_models(
                    config.endpoint,
                    config.api_key,
                    config.provider,
                    min(config.timeout, 20),
                )
            except Exception:
                models = []
            if models and (not config.model or config.model not in models):
                config.model = models[0]
                note = f"서버 모델 목록을 감지해 모델을 {config.model}(으)로 맞췄습니다."
        return config, note

    def _apply_prepared_ai_config(self, config: AIProviderConfig, note: str = ""):
        if not hasattr(self, "cmb_ai_provider"):
            return
        idx = self.cmb_ai_provider.findData(config.provider)
        if idx >= 0:
            self.cmb_ai_provider.setCurrentIndex(idx)
        self.edit_ai_endpoint.setText(config.endpoint)
        self._set_ai_model_text(config.model)
        self.settings.setValue("ai/provider", config.provider)
        self.settings.setValue("ai/endpoint", config.endpoint)
        self.settings.setValue("ai/model", config.model)
        self.settings.setValue(f"ai/providers/{config.provider}/endpoint", config.endpoint)
        self.settings.setValue(f"ai/providers/{config.provider}/model", config.model)
        self.settings.setValue(f"ai/providers/{config.provider}/api_key", config.api_key)
        self.settings.sync()
        self._ai_active_provider = config.provider
        if note:
            self._append_ai_progress(note)

    def _prepare_ai_connection_config(self, config: AIProviderConfig) -> tuple[AIProviderConfig, str]:
        prepared, note = self._prepare_ai_connection_config_for_worker(
            config,
            self._candidate_mlx_endpoints(),
            self._append_ai_progress,
        )
        self._apply_prepared_ai_config(prepared, note)
        return prepared, note

    def _student_names_for_privacy(self) -> list[str]:
        if self.exam is None:
            return []
        return [st.name for st in self.exam.students if getattr(st, "name", "")]

    def _test_ai_connection(self):
        config = self._ai_provider_config()
        self._save_ai_settings()
        if config.provider == "local_draft":
            QMessageBox.information(self, "AI 연결 테스트", "로컬 초안 모드는 외부 연결 없이 바로 사용할 수 있습니다.")
            return
        endpoints = self._candidate_mlx_endpoints()
        prompt = '다음 JSON만 반환하세요: {"status":"ok"}'

        def work(progress):
            prepared, note = self._prepare_ai_connection_config_for_worker(config, endpoints, progress)
            progress(f"{prepared.label}에 최종 짧은 테스트 요청 전송 중")
            output = run_completion(prompt, prepared, max_tokens=96)
            if not output.strip():
                raise ValueError("AI 서버가 빈 응답을 보냈습니다. 모델 새로고침으로 다른 채팅 모델을 선택해 주세요.")
            progress("AI 응답 수신 완료")
            return {"config": prepared, "note": note, "output": output}

        def success(result):
            prepared = result["config"]
            note = result.get("note", "")
            self._apply_prepared_ai_config(prepared, note)
            status = f"{prepared.label} 연결 확인 완료. 모델: {prepared.model}"
            if note:
                status += f" · {note}"
            self.lbl_ai_settings_status.setText(status)
            self._append_ai_progress(status)
            QMessageBox.information(
                self,
                "AI 연결 테스트",
                f"{prepared.label} 응답을 정상적으로 읽었습니다.\n"
                f"모델: {prepared.model}\n"
                f"응답 예시: {(result.get('output') or '').strip()[:120]}\n"
                f"{note}".strip(),
            )

        self._run_ai_background_task("AI 연결 테스트", work, success)

    def _ai_review_example_text(self, kind: str) -> str:
        if kind == "perform":
            return (
                "평가요소: 수학적 모델링\n"
                "만점 10점\n"
                "성취기준 [10공수1-03-01] 함수의 그래프를 해석하고 상황에 맞게 모델링할 수 있다.\n"
                "목표수준 A\n"
                "난이도 어려움\n"
                "A: 주어진 상황을 함수로 일반화하고 그래프의 의미를 정확히 해석한다.\n"
                "B: 상황을 함수로 표현하고 그래프의 주요 특징을 설명한다.\n"
                "C: 기본적인 함수식과 그래프를 연결한다.\n"
                "D: 일부 값의 대응 관계를 찾는다.\n"
                "E: 안내를 받아 함수식의 의미를 확인한다.\n"
                "\n"
                "평가요소: 풀이 과정 설명\n"
                "만점 8점\n"
                "성취기준 [10공수1-02-02] 이차방정식의 실근과 허근을 이해하고 판별식을 활용할 수 있다.\n"
                "목표수준 B\n"
                "난이도 보통\n"
                "A: 판별식의 의미를 근의 개수와 연결해 논리적으로 설명한다.\n"
                "B: 판별식을 계산하고 근의 종류를 정확히 판별한다.\n"
                "C: 판별식 계산 절차를 수행한다.\n"
                "D: 일부 항을 대입해 계산한다.\n"
                "E: 안내를 받아 판별식의 형태를 확인한다."
            )
        return (
            "문항 1 | 유형 선택형 | 난이도 쉬움 | 목표수준 E | 배점 4 | "
            "성취기준 [10공수1-01-01] 다항식의 사칙연산 원리를 설명하고 계산할 수 있다.\n"
            "문항 내용: 두 다항식의 합을 계산하는 기본 문항이다. 보기 5개 중 정답을 고른다.\n"
            "\n"
            "문항 2 | 유형 서답형 | 난이도 보통 | 목표수준 C | 배점 5 | "
            "성취기준 [10공수1-02-03] 이차방정식의 근과 계수의 관계를 설명할 수 있다.\n"
            "문항 내용: 이차방정식 x^2 - 5x + 6 = 0의 두 근을 alpha, beta라 할 때 "
            "alpha+beta와 alpha beta를 구하고 근과 계수의 관계를 설명한다.\n"
            "\n"
            "문항 3 | 유형 서답형 | 난이도 어려움 | 목표수준 A | 배점 6 | "
            "성취기준 [10공수1-03-01] 함수의 그래프를 해석하고 상황에 맞게 모델링할 수 있다.\n"
            "문항 내용: 실생활 자료를 함수식으로 모델링하고 그래프의 변화율을 해석하여 결론을 정당화한다."
        )

    def _ai_review_reference_example_text(self, kind: str) -> str:
        if kind == "perform":
            return (
                "[10공수1-03-01] 함수의 그래프를 해석하고 상황에 맞게 모델링할 수 있다.\n"
                "A 수준: 주어진 상황을 수학적 모델로 일반화하고, 그래프의 의미와 한계를 근거와 함께 설명한다.\n"
                "B 수준: 상황을 함수식이나 그래프로 표현하고 주요 특징을 설명한다.\n"
                "C 수준: 기본적인 함수식과 그래프의 대응 관계를 설명한다.\n"
                "D 수준: 안내된 절차에 따라 일부 값의 대응 관계를 찾는다.\n"
                "E 수준: 도움을 받아 함수식 또는 그래프의 기본 의미를 확인한다.\n"
                "\n"
                "[10공수1-02-02] 이차방정식의 실근과 허근을 이해하고 판별식을 활용할 수 있다.\n"
                "A 수준: 판별식을 근의 구조와 연결하고 이유를 논리적으로 설명한다.\n"
                "B 수준: 판별식을 계산하여 근의 종류를 정확히 판별한다.\n"
                "C 수준: 판별식 계산 절차를 알고 기본 문항에 적용한다.\n"
                "D 수준: 안내에 따라 계수를 대입하고 일부 계산을 수행한다.\n"
                "E 수준: 도움을 받아 판별식의 형태와 의미를 확인한다."
            )
        return (
            "[10공수1-01-01] 다항식의 사칙연산 원리를 설명하고 계산할 수 있다.\n"
            "A 수준: 다항식 연산 원리를 일반화하고 여러 표현을 연결해 설명한다.\n"
            "B 수준: 다항식의 사칙연산 원리를 설명하고 복합 계산을 수행한다.\n"
            "C 수준: 기본적인 다항식 덧셈, 뺄셈, 곱셈을 수행한다.\n"
            "D 수준: 안내된 절차에 따라 간단한 다항식 계산을 수행한다.\n"
            "E 수준: 도움을 받아 동류항과 기본 계산 절차를 확인한다.\n"
            "\n"
            "[10공수1-02-03] 이차방정식의 근과 계수의 관계를 설명할 수 있다.\n"
            "A 수준: 근과 계수의 관계를 여러 상황에 적용하고 식의 의미를 정당화한다.\n"
            "B 수준: 근과 계수의 관계를 설명하고 표준적인 문항에 적용한다.\n"
            "C 수준: 두 근의 합과 곱을 계수와 연결해 구한다.\n"
            "D 수준: 안내에 따라 두 근의 합 또는 곱 일부를 구한다.\n"
            "E 수준: 도움을 받아 근과 계수 관계의 기본 형태를 확인한다.\n"
            "\n"
            "[10공수1-03-01] 함수의 그래프를 해석하고 상황에 맞게 모델링할 수 있다.\n"
            "A 수준: 실생활 자료를 함수식으로 모델링하고 그래프의 변화율을 해석하여 결론을 정당화한다.\n"
            "B 수준: 자료의 관계를 함수식이나 그래프로 표현하고 주요 특징을 설명한다.\n"
            "C 수준: 기본적인 그래프 정보를 읽고 함수식과 연결한다.\n"
            "D 수준: 안내에 따라 그래프의 일부 정보를 찾는다.\n"
            "E 수준: 도움을 받아 좌표, 증가·감소 등 기본 정보를 확인한다."
        )

    def _insert_ai_review_example(self, kind: str):
        if not hasattr(self, "txt_ai_review_source"):
            return
        source_has_text = self.txt_ai_review_source.toPlainText().strip()
        reference_has_text = (
            hasattr(self, "txt_ai_review_reference")
            and self.txt_ai_review_reference.toPlainText().strip()
        )
        if source_has_text or reference_has_text:
            answer = QMessageBox.question(
                self,
                "예시 입력",
                "현재 문항 자료와 성취기준·수준 자료를 예시로 바꿀까요?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
        self.txt_ai_review_source.setPlainText(self._ai_review_example_text(kind))
        if hasattr(self, "txt_ai_review_reference"):
            self.txt_ai_review_reference.setPlainText(self._ai_review_reference_example_text(kind))
        label = "수행평가" if kind == "perform" else "지필평가"
        self.statusBar().showMessage(f"{label} 문항 자료와 성취기준·수준 예시를 입력했습니다. '검토 초안 생성'을 누르세요.", 5000)

    def _extract_text_from_review_file(self, path: str) -> str:
        p = Path(path)
        suffix = p.suffix.lower()
        if suffix in {".txt", ".md", ".csv", ".json"}:
            return self._format_ai_extracted_markdown(p.read_text(encoding="utf-8", errors="replace"))
        if suffix in {".xlsx", ".xlsm"}:
            import openpyxl
            wb = openpyxl.load_workbook(p, read_only=True, data_only=True)
            parts = []
            for ws in wb.worksheets[:8]:
                parts.append(f"## 시트: {ws.title}")
                for r_idx, row in enumerate(ws.iter_rows(values_only=True), start=1):
                    if r_idx > 120:
                        parts.append("...")
                        break
                    values = [str(v).strip() for v in row[:24] if v not in (None, "")]
                    if values:
                        parts.append(" | ".join(values))
            return "\n".join(parts)
        if suffix == ".docx":
            return self._format_ai_extracted_markdown(self._extract_docx_text(p))
        if suffix == ".hwpx":
            return self._format_ai_extracted_markdown(self._extract_hwpx_text(p))
        if suffix == ".hwp":
            return self._format_ai_extracted_markdown(self._extract_hwp_text_with_external_tools(p))
        if suffix == ".pdf":
            try:
                import pypdf
            except Exception as exc:
                raise ValueError("PDF 텍스트 추출을 위해 pypdf가 필요합니다. requirements.txt를 반영해 설치 후 다시 시도하세요.") from exc
            reader = pypdf.PdfReader(str(p))
            pages = []
            for i, page in enumerate(reader.pages[:80], start=1):
                text = self._normalize_pdf_math_text(page.extract_text() or "")
                if text.strip():
                    pages.append(f"## PDF {i}쪽\n\n{self._format_ai_extracted_markdown(text)}")
            return "\n".join(pages)
        raise ValueError("지원 형식: .txt, .md, .csv, .json, .xlsx, .xlsm, .docx, .hwp, .hwpx, .pdf")

    @staticmethod
    def _xml_local_name(tag: str) -> str:
        return tag.rsplit("}", 1)[-1] if "}" in tag else tag

    def _extract_docx_text(self, path: Path) -> str:
        try:
            with zipfile.ZipFile(path) as zf:
                names = [name for name in zf.namelist() if name == "word/document.xml"]
                if not names:
                    raise ValueError("DOCX 본문 XML을 찾지 못했습니다.")
                root = ET.fromstring(zf.read(names[0]))
        except zipfile.BadZipFile as exc:
            raise ValueError("DOCX 파일 구조를 읽지 못했습니다.") from exc
        paragraphs = []
        for para in root.iter():
            if self._xml_local_name(para.tag) != "p":
                continue
            texts = []
            for node in para.iter():
                name = self._xml_local_name(node.tag)
                if name == "t" and node.text:
                    texts.append(node.text)
                elif name in {"tab", "br"}:
                    texts.append("\t" if name == "tab" else "\n")
            joined = "".join(texts).strip()
            if joined:
                paragraphs.append(joined)
        return "\n".join(paragraphs)

    def _extract_hwpx_text(self, path: Path) -> str:
        try:
            with zipfile.ZipFile(path) as zf:
                xml_names = [
                    name for name in zf.namelist()
                    if name.lower().endswith(".xml")
                    and (
                        "/section" in name.lower()
                        or name.lower().startswith("contents/")
                        or name.lower().startswith("bodytext/")
                    )
                ]
                section_names = [
                    name for name in xml_names
                    if "section" in Path(name).name.lower()
                ] or xml_names
                section_names = sorted(section_names)[:120]
                parts = []
                for name in section_names:
                    try:
                        root = ET.fromstring(zf.read(name))
                    except Exception:
                        continue
                    parts.extend(self._extract_text_from_hwpx_xml_root(root))
        except zipfile.BadZipFile as exc:
            raise ValueError("HWPX 파일 구조를 읽지 못했습니다.") from exc
        text = "\n".join(part for part in parts if part.strip())
        if not text.strip():
            raise ValueError("HWPX에서 본문 텍스트를 찾지 못했습니다.")
        return text

    def _extract_text_from_hwpx_xml_root(self, root: ET.Element) -> list[str]:
        paragraphs: list[str] = []
        for elem in root.iter():
            if self._xml_local_name(elem.tag) not in {"p", "para"}:
                continue
            chunks = []
            for node in elem.iter():
                name = self._xml_local_name(node.tag)
                if name in {"t", "text"} and node.text:
                    chunks.append(node.text)
                elif name in {"lineBreak", "br"}:
                    chunks.append("\n")
                elif name in {"tab"}:
                    chunks.append("\t")
            line = re.sub(r"[ \t]+", " ", "".join(chunks)).strip()
            if line:
                paragraphs.append(line)
        return paragraphs

    @staticmethod
    def _is_useful_converter_output(text: str) -> bool:
        stripped = (text or "").strip()
        if len(stripped) < 20:
            return False
        lowered = stripped.lower()
        if "usage:" in lowered and len(stripped) < 800:
            return False
        if "not found" in lowered and len(stripped) < 400:
            return False
        return True

    def _extract_hwp_text_with_external_tools(self, path: Path) -> str:
        attempts: list[tuple[str, list[str]]] = []
        if shutil.which("hwp5txt"):
            attempts.append(("hwp5txt", ["hwp5txt", str(path)]))
        if shutil.which("kordoc"):
            attempts.extend([
                ("kordoc", ["kordoc", str(path)]),
                ("kordoc parse", ["kordoc", "parse", str(path)]),
                ("kordoc parse-document", ["kordoc", "parse-document", str(path)]),
                ("kordoc to-markdown", ["kordoc", "to-markdown", str(path)]),
            ])
        errors = []
        for label, command in attempts:
            try:
                completed = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=45,
                    check=False,
                )
            except Exception as exc:
                errors.append(f"{label}: {exc}")
                continue
            output = (completed.stdout or "").strip()
            if self._is_useful_converter_output(output):
                return output
            err = (completed.stderr or output or f"종료코드 {completed.returncode}").strip()
            errors.append(f"{label}: {err[:180]}")
        detail = "\n".join(errors[:5])
        raise ValueError(
            "HWP 파일은 현재 앱 내장 파서만으로 안정적으로 읽기 어렵습니다. "
            "HWPX로 저장해 불러오거나, 로컬에 kordoc 또는 hwp5txt를 설치한 뒤 다시 시도해 주세요."
            + (f"\n\n시도 결과:\n{detail}" if detail else "")
        )

    @staticmethod
    def _format_ai_material_header(title: str, path: Path | str) -> str:
        return f"# {title}\n\n**저장 위치:** `{path}`"

    @staticmethod
    def _format_ai_extracted_markdown(text: str) -> str:
        if not text:
            return ""
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"(?<!\n)\s+(?=##\s*PDF\s*\d+쪽)", "\n\n", text)
        text = re.sub(r"(?<!^)(?<!\n)\s+(?=(?:[1-9]|[1-9]\d)\.\s)", "\n\n", text)
        text = re.sub(r"(?<!^)(?<!\n)\s+(?=문항\s*\d{1,3}\b)", "\n\n", text)
        text = re.sub(r"\s+(?=(?:①|②|③|④|⑤|⑥|⑦|⑧|⑨|⑩))", " ", text)
        lines = []
        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                lines.append("")
                continue
            if re.match(r"^(?:[1-9]|[1-9]\d)\.\s", line):
                lines.append(f"### {line}")
            elif re.match(r"^문항\s*\d{1,3}\b", line):
                lines.append(f"### {line}")
            elif line.startswith(("과목:", "학기/학년:", "시험일자", "교사")):
                lines.append(f"**{line}**")
            elif line.startswith("※"):
                lines.append(f"> {line}")
            else:
                lines.append(line)
        formatted = "\n".join(lines)
        formatted = re.sub(r"\n{3,}", "\n\n", formatted)
        return formatted.strip()

    @staticmethod
    def _normalize_pdf_math_text(text: str) -> str:
        if not text:
            return ""
        special_replacements = {
            "\ue05c\ue06d\ue046\ue034": r"\sqrt{-1}",
            "\ue06d\ue0fe": r"\overline{z}",
            "\ue06d\ue0fb": r"\overline{w}",
            "\ue06d\ue0fc": r"\overline{x}",
            "\ue06d\ue0e5": r"\overline{a}",
            "\ue06d\ue0e6": r"\overline{b}",
        }
        for old, new in special_replacements.items():
            text = text.replace(old, new)
        glyphs = {
            "\ue034": "1",
            "\ue035": "2",
            "\ue036": "3",
            "\ue037": "4",
            "\ue038": "5",
            "\ue039": "6",
            "\ue03a": "7",
            "\ue03b": "8",
            "\ue03c": "9",
            "\ue03d": "0",
            "\ue000": "A",
            "\ue001": "B",
            "\ue002": "C",
            "\ue003": "D",
            "\ue010": "Q",
            "\ue011": "R",
            "\ue044": "(",
            "\ue045": ")",
            "\ue046": "-",
            "\ue047": "=",
            "\ue048": "+",
            "\ue052": ",",
            "\ue055": r"\le ",
            "\ue05c": r"\sqrt",
            "\ue06d": "",
            "\ue0e5": "a",
            "\ue0e6": "b",
            "\ue0e7": "c",
            "\ue0e8": "d",
            "\ue0ed": "i",
            "\ue0fb": "w",
            "\ue0fc": "x",
            "\ue0fd": "y",
            "\ue0fe": "z",
        }
        text = "".join(glyphs.get(ch, ch) for ch in text)
        text = re.sub(r"([xyzwabcd])([0-9])", r"\1^{\2}", text)
        text = re.sub(r"\\sqrt\s*\{?-1\}?", r"\\sqrt{-1}", text)
        text = re.sub(r"\s+([①②③④⑤])", r" \1", text)
        return text

    def _compact_ai_reference_text(self, text: str) -> str:
        entries = self._ai_reference_entries(text)
        level_parts = []
        standard_parts = []
        seen = set()
        for entry in entries:
            raw = str(entry.get("text", "")).strip()
            code = str(entry.get("code", "")).strip()
            if not raw:
                continue
            if not re.search(r"\[(?:10공수|10기수)[^\]]+\]", raw):
                continue
            if any(token in raw for token in ("예시 답안", "채점 시 고려", "피드백 방안", "문항 개발", "수행 과제")):
                continue
            cleaned = self._clean_ai_reference_standard_text(raw, code)
            if not cleaned:
                continue
            key = cleaned[:120]
            if key in seen:
                continue
            seen.add(key)
            levels = self._extract_ai_reference_levels(raw)
            if levels:
                level_parts.append(cleaned + "\n" + "\n".join(levels))
            else:
                standard_parts.append(cleaned)
        if level_parts:
            return "\n\n".join(level_parts)
        if standard_parts:
            return "\n\n".join(standard_parts)
        relevant = []
        for line in text.splitlines():
            compact = re.sub(r"\s+", " ", line).strip()
            if not compact:
                continue
            if re.search(r"\[(?:10공수|10기수)[^\]]+\]", compact) or any(
                token in compact for token in ("성취기준", "성취수준", "평가기준", "최소능력자")
            ):
                relevant.append(compact)
        return "\n".join(relevant[:500]) if relevant else text[:AI_REFERENCE_TEXT_LIMIT]

    @staticmethod
    def _extract_ai_reference_levels(text: str) -> list[str]:
        compact = re.sub(r"\s+", " ", text or "").strip()
        levels = []
        for lv in LEVELS_AE:
            match = re.search(rf"(?:^|\s){lv}\s+(.+?)(?=\s[ABCDE]\s+|$)", compact)
            if not match:
                continue
            body = match.group(1).strip()
            body = re.sub(r"\s+", " ", body)
            if len(body) < 12 or not re.search(r"[가-힣]", body):
                continue
            body = body[:260].strip()
            levels.append(f"{lv}: {body}")
        return levels

    def _ai_material_root_dir(self) -> Path:
        if sys.platform == "darwin":
            root = Path.home() / "Library" / "Application Support" / "Goedu-Split"
        elif sys.platform.startswith("win"):
            root = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "Goedu-Split"
        else:
            root = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "Goedu-Split"
        try:
            root.mkdir(parents=True, exist_ok=True)
        except OSError:
            root = Path(tempfile.gettempdir()) / "Goedu-Split"
            root.mkdir(parents=True, exist_ok=True)
        return root

    @staticmethod
    def _ensure_writable_dir(path: Path, fallback_name: str) -> Path:
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".__goedusplit_write_test__"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return path
        except OSError:
            fallback = Path(tempfile.gettempdir()) / "Goedu-Split" / fallback_name
            fallback.mkdir(parents=True, exist_ok=True)
            return fallback

    def _ai_source_store_dir(self) -> Path:
        return self._ensure_writable_dir(self._ai_material_root_dir() / "ai_source_files", "ai_source_files")

    def _ai_reference_store_dir(self) -> Path:
        return self._ensure_writable_dir(self._ai_material_root_dir() / "ai_reference_files", "ai_reference_files")

    def _ai_source_cache_path(self) -> Path:
        return self._ai_source_store_dir() / AI_SOURCE_CACHE_NAME

    def _ai_reference_cache_path(self) -> Path:
        return self._ai_reference_store_dir() / AI_REFERENCE_CACHE_NAME

    def _refresh_ai_source_store_label(self):
        if not hasattr(self, "lbl_ai_source_store"):
            return
        store = self._ai_source_store_dir()
        stored_files = [
            path for path in store.iterdir()
            if path.is_file() and path.name != AI_SOURCE_CACHE_NAME
        ]
        self.lbl_ai_source_store.setText(f"저장자료 {len(stored_files)}개")
        self.lbl_ai_source_store.setToolTip(f"저장 위치: {store}")

    def _refresh_ai_reference_store_label(self):
        if not hasattr(self, "lbl_ai_reference_store"):
            return
        store = self._ai_reference_store_dir()
        stored_files = [
            path for path in store.iterdir()
            if path.is_file() and path.name != AI_REFERENCE_CACHE_NAME
        ]
        self.lbl_ai_reference_store.setText(f"저장자료 {len(stored_files)}개")
        self.lbl_ai_reference_store.setToolTip(f"저장 위치: {store}")

    def _show_ai_store_location(self, kind: str):
        if kind == "reference":
            title = "성취기준·수준 자료 저장 위치"
            store = self._ai_reference_store_dir()
        else:
            title = "문항 자료 저장 위치"
            store = self._ai_source_store_dir()
        QMessageBox.information(
            self,
            title,
            f"불러온 자료와 직접 저장한 텍스트는 아래 폴더에 보관됩니다.\n\n{store}",
        )

    @staticmethod
    def _unique_store_path(directory: Path, filename: str) -> Path:
        safe_name = re.sub(r"[\\/:*?\"<>|]+", "_", filename).strip() or "reference"
        target = directory / safe_name
        if not target.exists():
            return target
        stem = target.stem
        suffix = target.suffix
        for i in range(2, 1000):
            candidate = directory / f"{stem}_{i}{suffix}"
            if not candidate.exists():
                return candidate
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return directory / f"{stem}_{stamp}{suffix}"

    def _store_ai_reference_file(self, path: Path) -> Path:
        store = self._ai_reference_store_dir()
        target = self._unique_store_path(store, path.name)
        shutil.copy2(path, target)
        self._refresh_ai_reference_store_label()
        return target

    def _store_ai_source_file(self, path: Path) -> Path:
        store = self._ai_source_store_dir()
        target = self._unique_store_path(store, path.name)
        shutil.copy2(path, target)
        self._refresh_ai_source_store_label()
        return target

    def _save_ai_source_cache(self, text: str):
        cache = self._ai_source_cache_path()
        cache.write_text(text[:AI_SOURCE_TEXT_LIMIT], encoding="utf-8")
        self._refresh_ai_source_store_label()

    def _save_ai_reference_cache(self, text: str):
        cache = self._ai_reference_cache_path()
        cache.write_text(text[:AI_REFERENCE_TEXT_LIMIT], encoding="utf-8")
        self._refresh_ai_reference_store_label()

    def _load_ai_reference_cache_if_empty(self):
        if self._ai_review_reference_text():
            return
        cache = self._ai_reference_cache_path()
        if not cache.exists():
            return
        try:
            text = cache.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return
        if text.strip():
            self._set_ai_review_source_text(text, target="reference")

    def _save_current_ai_text(self, kind: str):
        if kind == "source":
            text = self._ai_review_source_text()
            store = self._ai_source_store_dir()
            label = "문항 자료"
            suffix = "source"
            limit = AI_SOURCE_TEXT_LIMIT
        else:
            text = self._ai_review_reference_text()
            store = self._ai_reference_store_dir()
            label = "성취기준·수준 자료"
            suffix = "reference"
            limit = AI_REFERENCE_TEXT_LIMIT
        if not text:
            QMessageBox.information(self, "현재 내용 저장", f"저장할 {label}가 없습니다.")
            return
        default = store / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{suffix}.txt"
        path, _ = QFileDialog.getSaveFileName(
            self,
            f"{label} 저장",
            str(default),
            "텍스트 파일 (*.txt);;모든 파일 (*.*)",
        )
        if not path:
            return
        try:
            Path(path).write_text(text[:limit], encoding="utf-8")
            if kind == "source":
                self._save_ai_source_cache(text)
            else:
                self._save_ai_reference_cache(text)
        except Exception as exc:
            QMessageBox.warning(self, "현재 내용 저장", f"저장하지 못했습니다.\n{exc}")
            return
        self.statusBar().showMessage(f"{label} 저장 완료 · {path}", 5000)

    def _choose_saved_ai_files(self, kind: str) -> list[str]:
        if kind == "source":
            store = self._ai_source_store_dir()
            title = "저장된 문항 자료 선택"
        else:
            store = self._ai_reference_store_dir()
            title = "저장된 성취기준·수준 자료 선택"
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            title,
            str(store),
            "저장 자료 (*.txt *.md *.csv *.json *.xlsx *.xlsm *.docx *.hwp *.hwpx *.pdf);;모든 파일 (*.*)",
        )
        return paths

    def _load_saved_ai_source_text(self):
        paths = self._choose_saved_ai_files("source")
        if not paths:
            return
        parts = []
        failures = []
        for path_str in paths:
            path = Path(path_str)
            try:
                text = self._extract_text_from_review_file(str(path))
            except Exception as exc:
                failures.append(f"{path.name}: {exc}")
                continue
            parts.append(f"{self._format_ai_material_header(f'문항 자료: {path.name}', path)}\n\n{text}")
        if not parts:
            QMessageBox.warning(self, "저장자료 불러오기", "선택한 문항 자료를 읽지 못했습니다.\n" + "\n".join(failures[:5]))
            return
        text = "\n\n".join(parts)
        self._set_ai_review_source_text(text, target="source")
        self._save_ai_source_cache(text)
        self._refresh_ai_source_store_label()
        self.statusBar().showMessage(f"저장된 문항 자료 {len(parts)}개를 불러왔습니다.", 5000)
        if failures:
            QMessageBox.warning(self, "일부 문항 자료 읽기 실패", "\n".join(failures[:8]))

    def _load_saved_ai_reference_text(self):
        paths = self._choose_saved_ai_files("reference")
        if not paths:
            return
        parts = []
        failures = []
        for path_str in paths:
            path = Path(path_str)
            try:
                text = self._compact_ai_reference_text(self._extract_text_from_review_file(str(path)))
            except Exception as exc:
                failures.append(f"{path.name}: {exc}")
                continue
            parts.append(f"{self._format_ai_material_header(f'성취기준·수준 자료: {path.name}', path)}\n\n{text}")
        if not parts:
            QMessageBox.warning(
                self,
                "저장자료 불러오기",
                "선택한 성취기준·수준 자료를 읽지 못했습니다.\n" + "\n".join(failures[:5]),
            )
            return
        text = "\n\n".join(parts)
        self._set_ai_review_source_text(text, target="reference")
        self._save_ai_reference_cache(text)
        self._refresh_ai_reference_store_label()
        self.statusBar().showMessage(f"저장된 성취기준·수준 자료 {len(parts)}개를 불러왔습니다.", 5000)
        if failures:
            QMessageBox.warning(self, "일부 참고자료 읽기 실패", "\n".join(failures[:8]))

    def _set_ai_review_source_text(self, text: str, *, target: str = "source"):
        if target == "reference" and hasattr(self, "txt_ai_review_reference"):
            self.txt_ai_review_reference.setPlainText(text[:AI_REFERENCE_TEXT_LIMIT])
            self._update_ai_markdown_preview("reference")
            if hasattr(self, "ai_review_input_tabs"):
                self.ai_review_input_tabs.setCurrentIndex(1)
            if hasattr(self, "ai_reference_view_tabs"):
                self.ai_reference_view_tabs.setCurrentIndex(1)
            return
        self.txt_ai_review_source.setPlainText(text[:AI_SOURCE_TEXT_LIMIT])
        self._update_ai_markdown_preview("source")
        if hasattr(self, "ai_review_input_tabs"):
            self.ai_review_input_tabs.setCurrentIndex(0)
        if hasattr(self, "ai_source_view_tabs"):
            self.ai_source_view_tabs.setCurrentIndex(1)

    def _ai_review_source_text(self) -> str:
        if not hasattr(self, "txt_ai_review_source"):
            return ""
        return self.txt_ai_review_source.toPlainText().strip()

    def _ai_review_reference_text(self) -> str:
        if not hasattr(self, "txt_ai_review_reference"):
            return ""
        return self.txt_ai_review_reference.toPlainText().strip()

    def _load_ai_review_file(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "시험 문제 또는 문항 자료 불러오기",
            "",
            "검토 자료 (*.txt *.md *.csv *.json *.xlsx *.xlsm *.docx *.hwp *.hwpx *.pdf);;모든 파일 (*.*)",
        )
        if not paths:
            return
        existing = self._ai_review_source_text().strip()
        append_existing = False
        if existing:
            choice = QMessageBox.question(
                self,
                "문항 자료 추가",
                f"이미 문항 자료가 들어 있습니다.\n선택한 {len(paths)}개 자료를 기존 자료 뒤에 추가할까요?\n\n"
                "예: 추가\n아니오: 기존 자료를 지우고 교체",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                QMessageBox.Yes,
            )
            if choice == QMessageBox.Cancel:
                return
            append_existing = choice == QMessageBox.Yes
        parts = []
        failures = []
        for path_str in paths:
            path = Path(path_str)
            try:
                saved = self._store_ai_source_file(path)
                text = self._extract_text_from_review_file(str(path))
            except Exception as e:
                failures.append(f"{path.name}: {e}")
                continue
            parts.append(
                f"{self._format_ai_material_header(f'문항 자료: {path.name}', saved)}\n\n"
                f"{text}"
            )
        if not parts:
            QMessageBox.warning(
                self,
                "AI 문항 검토",
                "선택한 문항 자료를 읽지 못했습니다.\n" + "\n".join(failures[:5]),
            )
            return
        text = "\n\n".join(parts)
        if append_existing:
            text = f"{existing}\n\n{text}"
        self._set_ai_review_source_text(text, target="source")
        self._save_ai_source_cache(text)
        message = (
            f"문항 자료 {len(parts)}개 불러오기 완료 · "
            f"저장 위치: {self._ai_source_store_dir()}"
        )
        if failures:
            message += f" · 실패 {len(failures)}개"
            QMessageBox.warning(
                self,
                "일부 문항 자료 읽기 실패",
                "다음 자료는 불러오지 못했습니다.\n" + "\n".join(failures[:8]),
            )
        self.statusBar().showMessage(message, 7000)

    def _load_ai_reference_file(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "성취기준·성취수준 참고자료 불러오기",
            "",
            "참고 자료 (*.txt *.md *.csv *.json *.xlsx *.xlsm *.docx *.hwp *.hwpx *.pdf);;모든 파일 (*.*)",
        )
        if not paths:
            return
        existing = self._ai_review_reference_text().strip()
        append_existing = False
        if existing:
            choice = QMessageBox.question(
                self,
                "성취기준·수준 자료 추가",
                f"이미 참고자료가 들어 있습니다.\n선택한 {len(paths)}개 자료를 기존 자료 뒤에 추가할까요?\n\n"
                "예: 추가\n아니오: 기존 자료를 지우고 교체",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                QMessageBox.Yes,
            )
            if choice == QMessageBox.Cancel:
                return
            append_existing = choice == QMessageBox.Yes
        loaded_parts = []
        failures = []
        for path_str in paths:
            path = Path(path_str)
            try:
                saved = self._store_ai_reference_file(path)
                text = self._compact_ai_reference_text(self._extract_text_from_review_file(str(path)))
            except Exception as e:
                failures.append(f"{path.name}: {e}")
                continue
            loaded_parts.append(
                f"{self._format_ai_material_header(f'성취기준·수준 자료: {path.name}', saved)}\n\n"
                f"{text}"
            )
        if not loaded_parts:
            QMessageBox.warning(
                self,
                "AI 문항 검토",
                "선택한 참고자료를 읽지 못했습니다.\n" + "\n".join(failures[:5]),
            )
            return
        text = "\n\n".join(loaded_parts)
        if append_existing:
            text = f"{existing}\n\n{text}"
        self._set_ai_review_source_text(text, target="reference")
        self._save_ai_reference_cache(text)
        message = (
            f"성취기준·수준 자료 {len(loaded_parts)}개 불러오기 완료 · "
            f"저장 위치: {self._ai_reference_store_dir()}"
        )
        if failures:
            message += f" · 실패 {len(failures)}개"
            QMessageBox.warning(
                self,
                "일부 참고자료 읽기 실패",
                "다음 자료는 불러오지 못했습니다.\n" + "\n".join(failures[:8]),
            )
        self.statusBar().showMessage(message, 7000)

    def _load_ai_review_from_exam(self):
        if self.exam is None:
            QMessageBox.warning(self, "AI 문항 검토", "먼저 문항정보표를 불러와 분석을 실행해 주세요.")
            return
        lines = [
            "# 현재 문항정보표",
            "",
            f"**과목:** {self.exam.subject or '(과목 미상)'}",
            f"**학기/학년:** {self.exam.semester} {self.exam.grade}",
            "",
        ]
        type_order = {"선택형": 0, "서답형": 1}
        for item in sorted(self.exam.items, key=lambda it: (it.number, type_order.get(it.item_type, 9))):
            standard = " ".join(part for part in [item.standard_code, item.standard] if part).strip()
            lines.append(
                f"### 문항 {item.number} | 유형 {item.item_type} | 난이도 {item.difficulty or '-'} | "
                f"배점 {item.score:g} | 내용영역 {item.content_area or '-'} | 성취기준 {standard or '-'}"
            )
        self._set_ai_review_source_text("\n".join(lines), target="source")
        self.statusBar().showMessage("현재 문항정보표를 AI 문항 검토 원문으로 가져왔습니다.", 3500)

    def _split_ai_review_blocks(self, text: str) -> list[dict]:
        normalized_lines = []
        for line in text.splitlines():
            line = re.sub(r"^#{1,6}\s*", "", line.strip())
            line = re.sub(r"^\s*[-*]\s+", "", line)
            line = line.replace("**", "").replace("__", "").replace("`", "")
            normalized_lines.append(re.sub(r"\s+", " ", line).strip())
        lines = normalized_lines
        lines = [line for line in lines if line]
        blocks = []
        current = None
        section_type = ""
        item_re = re.compile(r"^(?:문항\s*)?(\d{1,3})\s*(?:번|[.)]|[|])?\s*(.*)$")
        for raw_line in lines:
            line = raw_line
            for marker, marker_type in (
                ("[선택형 문제]", "선택형"),
                ("[선택형]", "선택형"),
                ("[서답형 문제]", "서답형"),
                ("[서답형]", "서답형"),
                ("[논술형 문제]", "서답형"),
                ("[논술형]", "서답형"),
            ):
                if marker in line:
                    section_type = marker_type
                    before, after = line.split(marker, 1)
                    line = after.strip() or before.strip()
                    break
            if not line:
                continue
            m = item_re.match(line)
            looks_like_item = False
            if m:
                no = int(m.group(1))
                looks_like_item = no <= 150 and (
                    "문항" in line
                    or re.match(r"^\d{1,3}\s*(?:번|[.)])", line)
                    or "성취기준" in line
                    or "배점" in line
                    or any(mark in line for mark in ("①", "②", "③", "④", "⑤", "보기"))
                )
            if looks_like_item:
                label = f"{int(m.group(1))}번"
                starts_new_item_record = bool(re.match(r"^문항\s*\d{1,3}\b", line))
                if current and current.get("kind") == "문항" and current.get("label") == label and not starts_new_item_record:
                    current["text"] += "\n" + line
                else:
                    if current:
                        blocks.append(current)
                    current = {"kind": "문항", "label": label, "text": line, "section_type": section_type}
            elif any(key in line for key in ("평가요소", "채점기준", "수행 수준", "수행수준")):
                if current:
                    blocks.append(current)
                current = {"kind": "수행평가", "label": line[:32], "text": line, "section_type": "수행평가"}
            elif current:
                current["text"] += "\n" + line
            elif re.search(r"\[[^\]\n]{4,40}\]", line):
                blocks.append({"kind": "성취기준", "label": "성취기준", "text": line})
        if current:
            blocks.append(current)
        if not blocks and text.strip():
            blocks.append({"kind": "전체 자료", "label": "전체", "text": text.strip()[:4000]})
        return blocks[:120]

    @staticmethod
    def _ai_reference_tokens(text: str) -> set[str]:
        stopwords = {
            "성취기준", "성취수준", "수준", "문항", "자료", "설명", "확인",
            "있다", "한다", "대한", "통해", "기본", "도움", "안내",
            "서로", "다른", "대하여", "다음", "값은", "경우", "단", "각각",
            "옳은", "것은", "실수", "자연수", "만족", "때의",
        }
        tokens = set(re.findall(r"[가-힣A-Za-z0-9]{2,}", text or ""))
        return {token for token in tokens if token not in stopwords}

    def _ai_reference_entries(self, reference_text: str) -> list[dict[str, str | set[str]]]:
        reference_text = re.sub(r"(?=\[(?:10공수|10기수)[^\]\n]{1,40}\])", "\n", reference_text)
        normalized_lines = []
        for line in reference_text.splitlines():
            line = re.sub(r"^#{1,6}\s*", "", line.strip())
            line = re.sub(r"^\s*[-*]\s+", "", line)
            line = line.replace("**", "").replace("__", "").replace("`", "")
            normalized_lines.append(re.sub(r"\s+", " ", line).strip())
        lines = normalized_lines
        lines = [line for line in lines if line]
        entries: list[dict[str, str | set[str]]] = []
        current: list[str] = []
        current_code = ""

        def flush():
            if not current:
                return
            text = " ".join(current).strip()
            if not text:
                return
            entries.append({
                "code": current_code,
                "text": text[:900],
                "tokens": self._ai_reference_tokens(text),
            })

        for line in lines:
            codes = re.findall(r"\[[^\]\n]{4,40}\]", line)
            starts_standard = bool(codes) or line.startswith(("성취기준", "평가기준"))
            if starts_standard and current:
                flush()
                current = []
                current_code = ""
            if codes and not current_code:
                current_code = codes[0]
            current.append(line)
        flush()
        if not entries and reference_text.strip():
            text = reference_text.strip()[:3000]
            entries.append({"code": "", "text": text, "tokens": self._ai_reference_tokens(text)})
        return entries[:120]

    @staticmethod
    def _clean_ai_reference_standard_text(reference_text: str, reference_code: str = "") -> str:
        text = re.sub(r"\s+", " ", reference_text or "").strip()
        if not text:
            return ""
        if reference_code and reference_code in text:
            text = text[text.find(reference_code):]
        cut_positions = []
        for pattern in (
            r"\sA[:\s]",
            r"\sB[:\s]",
            r"\sC[:\s]",
            r"\sD[:\s]",
            r"\sE[:\s]",
            r"\s프로젝트\s",
            r"\s공통수학\d+-\d+",
            r"\s예시문항\s",
            r"\s평가도구\s",
        ):
            match = re.search(pattern, text)
            if match and match.start() > 0:
                cut_positions.append(match.start())
        if cut_positions:
            text = text[:min(cut_positions)].strip()
        if reference_code and reference_code not in text:
            text = f"{reference_code} {text}".strip()
        return text[:240].strip()

    def _match_ai_reference_entry(self, compact_text: str, entries: list[dict[str, str | set[str]]]) -> dict[str, str | set[str]] | None:
        if not entries:
            return None
        codes = re.findall(r"\[[^\]\n]{4,40}\]", compact_text)
        for code in codes:
            for entry in entries:
                if code and code == entry.get("code"):
                    return entry
                if code and code in str(entry.get("text", "")):
                    return entry
        keyword_match = self._match_ai_reference_by_keywords(compact_text, entries)
        if keyword_match:
            return keyword_match
        tokens = self._ai_reference_tokens(compact_text)
        if not tokens:
            return None
        best = None
        best_score = 0
        for entry in entries:
            code = str(entry.get("code", ""))
            text = str(entry.get("text", ""))
            if not code.startswith("[10공수") or "예시 답안" in text:
                continue
            entry_tokens = entry.get("tokens", set())
            if not isinstance(entry_tokens, set):
                continue
            score = len(tokens & entry_tokens)
            if score > best_score:
                best = entry
                best_score = score
        return best if best_score >= 2 else None

    @staticmethod
    def _entry_for_standard_code(entries: list[dict[str, str | set[str]]], code: str) -> dict[str, str | set[str]] | None:
        target = f"[{code}]"
        for entry in entries:
            if entry.get("code") == target or target in str(entry.get("text", "")):
                return entry
        return None

    def _match_ai_reference_by_keywords(self, compact_text: str, entries: list[dict[str, str | set[str]]]) -> dict[str, str | set[str]] | None:
        text = compact_text or ""
        keyword_rules = [
            ("10공수1-04-02", ("행렬", "행과 열", "")),
            ("10공수1-02-01", ("복소수", "허수", "켤레복소수", "")),
            ("10공수1-03-03", ("조합", "C", "nCr")),
            ("10공수1-03-02", ("순열", "일렬", "나열")),
            ("10공수1-03-01", ("경우의 수", "주사위", "메뉴판", "동시에 던져", "선택하는 경우", "자연수의 개수")),
            ("10공수1-01-03", ("인수분해",)),
            ("10공수1-01-02", ("나머지정리", "인수정리", "조립제법", "나누었을 때", "나누어떨어")),
            ("10공수1-01-01", ("다항식", "동류항", "사칙연산")),
            ("10공수1-02-06", ("최대", "최소")),
            ("10공수1-02-05", ("그래프와 직선", "위치 관계")),
            ("10공수1-02-04", ("이차방정식과 이차함수", "판별식", "그래프")),
            ("10공수1-02-03", ("근과 계수",)),
            ("10공수1-02-02", ("실근", "허근", "이차방정식")),
        ]
        for code, keywords in keyword_rules:
            if any(keyword in text for keyword in keywords):
                entry = self._entry_for_standard_code(entries, code)
                if entry:
                    return entry
        return None

    def _infer_ai_review_row(self, block: dict, reference_entries: list[dict[str, str | set[str]]] | None = None) -> dict:
        text = block["text"]
        compact = re.sub(r"\s+", " ", text)
        codes = re.findall(r"\[[^\]\n]{4,40}\]", compact)
        standard = codes[0] if codes else ""
        if standard:
            pos = compact.find(standard)
            standard = compact[pos:pos + 130].strip()
        matched_reference = self._match_ai_reference_entry(compact, reference_entries or [])
        if matched_reference:
            reference_text = str(matched_reference.get("text", "")).strip()
            reference_code = str(matched_reference.get("code", "")).strip()
            cleaned_reference = self._clean_ai_reference_standard_text(reference_text, reference_code)
            if reference_text and (not standard or standard == reference_code or (reference_code and reference_code in standard)):
                standard = cleaned_reference or reference_text[:130].strip()

        explicit_level = ""
        for lv in LEVELS_AE:
            if re.search(rf"(목표|판별|성취수준|수준)\s*[:：]?\s*{lv}\b", compact):
                explicit_level = lv
                break

        high_terms = ["복합", "추론", "증명", "정당화", "일반화", "모델링", "탐구", "분석", "해석", "실생활", "최대", "최소"]
        mid_terms = ["활용", "설명", "해결", "관계", "그래프", "원리", "성질", "이해"]
        low_terms = ["간단", "기본", "안내", "계산", "대입", "구하", "알고", "따라"]
        high = sum(1 for term in high_terms if term in compact)
        mid = sum(1 for term in mid_terms if term in compact)
        low = sum(1 for term in low_terms if term in compact)
        score = high * 2 + mid - low
        point_values = [
            float(match.group(1))
            for match in re.finditer(r"(\d+(?:\.\d+)?)\s*점", compact)
        ]
        inferred_points = max(point_values) if point_values else 0.0

        if "어려" in compact or re.search(r"\b상\b", compact):
            difficulty = "어려움"
        elif "쉬움" in compact or re.search(r"\b하\b", compact):
            difficulty = "쉬움"
        elif "보통" in compact or re.search(r"\b중\b", compact):
            difficulty = "보통"
        elif inferred_points >= 8:
            difficulty = "어려움"
        elif inferred_points >= 7:
            difficulty = "보통"
        elif inferred_points > 0:
            difficulty = "쉬움"
        elif score >= 4:
            difficulty = "어려움"
        elif score <= 0:
            difficulty = "쉬움"
        else:
            difficulty = "보통"

        if explicit_level:
            target = explicit_level
        elif inferred_points >= 8:
            target = "B"
        elif inferred_points >= 7:
            target = "C"
        elif 0 < inferred_points <= 5:
            target = "E"
        elif score >= 5:
            target = "A"
        elif score >= 3:
            target = "B"
        elif score >= 1:
            target = "C"
        elif score <= -2:
            target = "E"
        else:
            target = "D"

        block_section_type = str(block.get("section_type", ""))
        if block_section_type in {"선택형", "서답형"}:
            review_type = block_section_type
        elif any(term in compact for term in ("수행평가", "평가요소", "채점기준", "수행 수준", "수행수준")):
            review_type = "수행평가"
        elif "유형 선택형" in compact:
            review_type = "선택형"
        elif "유형 서답형" in compact:
            review_type = "서답형"
        elif any(term in compact for term in ("서답", "서술", "논술", "풀이과정", "증명하")):
            review_type = "서답형"
        elif any(term in compact for term in ("선택형", "객관식", "보기", "①", "②", "③", "④", "⑤")):
            review_type = "선택형"
        else:
            review_type = "지필 문항"

        evidence_terms = [term for term in high_terms + mid_terms + low_terms if term in compact][:4]
        if inferred_points > 0:
            evidence_terms.insert(0, f"배점 {inferred_points:g}점")
        if matched_reference:
            evidence_terms.append("참고자료 매칭")
        evidence = " · ".join(evidence_terms) if evidence_terms else compact[:90]
        warnings = []
        if not codes and not matched_reference:
            warnings.append("성취기준 코드 확인")
        if reference_entries and not matched_reference:
            warnings.append("성취기준·수준 자료 대조 확인")
        if block["kind"] == "전체 자료":
            warnings.append("문항/평가요소 분리 확인")
        if review_type == "지필 문항" and "배점" not in compact:
            warnings.append("배점 확인")
        next_step = " / ".join(warnings) if warnings else "성취기준 진술과 문항 요구 행동을 비교"
        if review_type == "수행평가":
            expected = self._ai_default_perform_expected_values(target, difficulty)
        else:
            expected = self._ai_default_ox_expected_values(target, difficulty)
        return {
            "kind": block["kind"],
            "label": block["label"],
            "standard": standard or "(후보 없음)",
            "review_type": review_type,
            "target": target,
            "difficulty": difficulty,
            **expected,
            "evidence": evidence,
            "next_step": next_step,
        }

    def _ai_default_ox_expected_values(self, target: str, difficulty: str) -> dict[str, str]:
        target = self._ai_review_level(target, "C")
        difficulty = self._ai_review_difficulty(difficulty)
        base = {
            "A": [2, 1, 0, 0, 0],
            "B": [3, 2, 1, 0, 0],
            "C": [3, 3, 2, 1, 0],
            "D": [3, 3, 3, 2, 1],
            "E": [3, 3, 3, 3, 2],
        }[target]
        if difficulty == "쉬움":
            counts = [min(3, value + 1) for value in base]
        elif difficulty == "어려움":
            target_index = LEVELS_AE.index(target)
            counts = [
                value if idx <= target_index else max(0, value - 1)
                for idx, value in enumerate(base)
            ]
        else:
            counts = base
        prev = 3
        normalized = []
        for value in counts:
            clipped = max(0, min(3, min(prev, int(value))))
            normalized.append(clipped)
            prev = clipped
        return {f"{lv} 예상": f"{count}/3" for lv, count in zip(LEVELS_AE, normalized)}

    def _ai_default_perform_expected_values(self, target: str, difficulty: str) -> dict[str, str]:
        target = self._ai_review_level(target, "C")
        target_index = LEVELS_AE.index(target)
        base_rates = {"A": 90, "B": 80, "C": 70, "D": 60, "E": 40}
        if difficulty == "쉬움":
            delta = 5
        elif difficulty == "어려움":
            delta = -5
        else:
            delta = 0
        values = {}
        prev = 100
        for idx, lv in enumerate(LEVELS_AE):
            level_adjust = 4 if idx < target_index else (-4 if idx > target_index else 0)
            rate = max(0, min(100, base_rates[lv] + delta + level_adjust))
            rate = min(prev, rate)
            values[f"{lv} 예상"] = f"{rate}%"
            prev = rate
        return values

    def _make_ai_review_prompt(self, rows: list[dict], source_text: str, reference_text: str = "") -> str:
        preview = source_text.strip()
        if len(preview) > 12000:
            preview = preview[:12000] + "\n...(이하 생략)"
        reference_preview = reference_text.strip()
        if len(reference_preview) > 10000:
            reference_preview = reference_preview[:10000] + "\n...(이하 생략)"
        row_lines = "\n".join(
            f"- {row['label']}: 유형={row['review_type']}, 목표={row['target']}, 난이도={row['difficulty']}, 성취기준={row['standard']}"
            for row in rows[:60]
        )
        return (
            "너는 고등학교 성취평가 현장지원단의 문항 검토 보조자다.\n"
            "먼저 시험 문제 자료를 문항 단위로 분석한 뒤, 성취기준·성취수준 참고자료와 대조하여 "
            "각 문항 또는 수행평가 평가요소의 성취기준, 목표 성취수준 후보, 난이도 후보를 제안하라.\n"
            "중요 원칙: 자동 확정하지 말고, 교사가 검토할 수 있도록 근거 문장을 함께 제시한다.\n"
            "A 수준 문항은 A 수준 최소능력자 3명 중 약 2명이 해결할 수 있는 문항이라는 기준으로 판단한다.\n"
            "수행평가는 평가요소별로 A~E 최소능력자의 예상점수를 산출할 수 있도록 채점기준표의 행동 표현을 분석한다.\n\n"
            "출력 형식은 표로 한다: 번호/요소 | 성취기준 후보 | 평가유형 | 목표수준 후보 | 난이도 후보 | "
            "A 예상 | B 예상 | C 예상 | D 예상 | E 예상 | 근거 | 추가 확인 질문.\n"
            "지필 문항의 A~E 예상은 3명 기준 O/X 개수처럼 3/3, 2/3, 1/3, 0/3으로 쓰고, "
            "수행평가는 만점 대비 예상점수 또는 90% 같은 비율로 쓴다.\n\n"
            "[로컬 초안]\n"
            f"{row_lines}\n\n"
            "[시험 문제 자료]\n"
            f"{preview}\n\n"
            "[성취기준·성취수준 참고자료]\n"
            f"{reference_preview or '(참고자료 없음)'}"
        )

    def _make_structured_ai_review_prompt(
        self,
        rows: list[dict],
        source_text: str,
        reference_text: str = "",
        *,
        source_limit: int = 18_000,
        reference_limit: int = 16_000,
        row_limit: int = 80,
        scope_note: str = "",
    ) -> str:
        preview = source_text.strip()
        if len(preview) > source_limit:
            preview = preview[:source_limit] + "\n...(이하 생략)"
        reference_preview = reference_text.strip()
        if len(reference_preview) > reference_limit:
            reference_preview = reference_preview[:reference_limit] + "\n...(이하 생략)"
        draft = "\n".join(
            f"- {row.get('label') or row.get('번호/요소')}: 유형={row.get('review_type') or row.get('평가유형')}, "
            f"목표={row.get('target') or row.get('목표수준 후보')}, 난이도={row.get('difficulty') or row.get('난이도 후보')}, "
            f"예상={', '.join(str(row.get(f'{lv} 예상', '')) for lv in LEVELS_AE)}, "
            f"성취기준={row.get('standard') or row.get('성취기준 후보')}"
            for row in rows[:row_limit]
        )
        scope = ""
        if scope_note:
            scope = (
                f"이번 요청 범위: {scope_note}\n"
                "반드시 이번 범위에 있는 항목만 출력하고, 빠진 항목 없이 같은 순서로 JSON 배열을 작성한다.\n\n"
            )
        return (
            "너는 고등학교 성취평가 현장지원단의 문항 검토 보조자다.\n"
            "아래 시험 문제 자료와 로컬 초안, 성취기준·성취수준 참고자료를 바탕으로 문항/수행평가 평가요소를 다시 검토하라.\n"
            f"{scope}"
            "작업 순서는 반드시 1) 시험 문제 자료를 문항 단위로 읽기, 2) 참고자료에서 가장 가까운 성취기준과 성취수준 설명 찾기, "
            "3) 그 기준에 맞춰 목표수준·난이도·A~E 예상값 제안하기 순서로 한다.\n"
            "AI 판정은 최종 확정이 아니라 교사가 검토할 초안이다.\n"
            "A 수준 문항은 A 수준 최소능력자 3명 중 약 2명이 해결할 수 있다는 기준으로 본다.\n"
            "수행평가는 평가요소별로 A~E 최소능력자의 예상점수 산정에 도움이 되도록 근거를 쓴다.\n\n"
            "반드시 JSON 배열만 출력하라. 설명 문장, 마크다운, 코드블록을 붙이지 마라.\n"
            "각 객체의 키는 반드시 다음 13개만 사용한다:\n"
            '["구분","번호/요소","성취기준 후보","평가유형","목표수준 후보","난이도 후보",'
            '"A 예상","B 예상","C 예상","D 예상","E 예상","근거","다음 확인"]\n'
            "평가유형은 선택형, 서답형, 수행평가 중 하나를 우선 사용한다.\n"
            "목표수준 후보는 A/B/C/D/E 중 하나를 사용한다.\n"
            "난이도 후보는 쉬움/보통/어려움 중 하나를 사용한다.\n\n"
            "지필 문항의 A~E 예상은 각 수준 대표학생 3명 중 몇 명이 맞힐지 3/3, 2/3, 1/3, 0/3으로 쓴다.\n"
            "수행평가의 A~E 예상은 만점 대비 점수나 비율로 쓴다. 예: 9점, 80%, 7.5/10.\n"
            "A에서 E로 갈수록 예상값은 같거나 낮아야 한다.\n\n"
            "근거와 다음 확인은 각각 80자 이내로 간결하게 쓴다.\n\n"
            "[로컬 초안]\n"
            f"{draft}\n\n"
            "[시험 문제 자료]\n"
            f"{preview}\n\n"
            "[성취기준·성취수준 참고자료]\n"
            f"{reference_preview or '(참고자료 없음)'}"
        )

    @staticmethod
    def _ai_review_source_for_blocks(blocks: list[dict], limit_per_block: int = 2400) -> str:
        parts = []
        for block in blocks:
            label = str(block.get("label", "")).strip()
            kind = str(block.get("kind", "문항")).strip()
            text = str(block.get("text", "")).strip()
            if len(text) > limit_per_block:
                text = text[:limit_per_block] + "\n...(문항 일부 생략)"
            parts.append(f"### {kind} {label}\n{text}")
        return "\n\n".join(parts)

    def _ai_reference_text_for_review_chunk(
        self,
        rows: list[dict],
        reference_entries: list[dict[str, str | set[str]]],
        fallback_reference_text: str,
    ) -> str:
        if not reference_entries:
            return fallback_reference_text[:AI_REVIEW_CHUNK_REFERENCE_LIMIT]
        row_text = " ".join(
            " ".join(str(row.get(key, "")) for key in ("label", "번호/요소", "standard", "성취기준 후보", "evidence", "근거"))
            for row in rows
        )
        row_tokens = self._ai_reference_tokens(row_text)
        selected = []
        for entry in reference_entries:
            text = str(entry.get("text", ""))
            code = str(entry.get("code", ""))
            tokens = entry.get("tokens", set())
            token_overlap = len(row_tokens & tokens) if isinstance(tokens, set) else 0
            if (code and code in row_text) or token_overlap >= 2:
                selected.append(text)
            if len(selected) >= 8:
                break
        if not selected:
            selected = [str(entry.get("text", "")) for entry in reference_entries[:4]]
        joined = "\n\n".join(part for part in selected if part)
        return joined[:AI_REVIEW_CHUNK_REFERENCE_LIMIT] or fallback_reference_text[:AI_REVIEW_CHUNK_REFERENCE_LIMIT]

    @staticmethod
    def _ai_review_row_key(row: dict, fallback_index: int = 0) -> str:
        label = str(row.get("label") or row.get("번호/요소") or row.get("번호") or "").strip()
        number = re.search(r"\d+", label)
        if number:
            return f"no:{int(number.group(0))}"
        return f"idx:{fallback_index}"

    def _ai_review_merge_chunk_rows(self, local_rows: list[dict], ai_rows: list[dict]) -> list[dict]:
        if len(ai_rows) == len(local_rows):
            return ai_rows
        by_key = {
            self._ai_review_row_key(row, idx): row
            for idx, row in enumerate(ai_rows)
        }
        merged = []
        used_ids = set()
        for idx, local in enumerate(local_rows):
            key = self._ai_review_row_key(local, idx)
            candidate = by_key.get(key)
            if candidate is not None:
                merged.append(candidate)
                used_ids.add(id(candidate))
            else:
                fallback = dict(local)
                next_step = fallback.get("next_step") or fallback.get("다음 확인") or ""
                fallback["next_step"] = (next_step + " / AI 보강 항목 확인").strip(" /")
                merged.append(fallback)
        for row in ai_rows:
            if id(row) not in used_ids:
                merged.append(row)
        return merged

    @staticmethod
    def _ai_review_failed_chunk_rows(local_rows: list[dict], reason: str) -> list[dict]:
        failed = []
        short_reason = str(reason).splitlines()[0][:90]
        for row in local_rows:
            fallback = dict(row)
            next_step = fallback.get("next_step") or fallback.get("다음 확인") or ""
            fallback["next_step"] = (next_step + f" / AI 보강 실패: {short_reason}").strip(" /")
            failed.append(fallback)
        return failed

    @staticmethod
    def _ai_review_signature(source_text: str, reference_text: str) -> str:
        digest = hashlib.sha256()
        digest.update((source_text or "").encode("utf-8", errors="replace"))
        digest.update(b"\0")
        digest.update((reference_text or "").encode("utf-8", errors="replace"))
        return digest.hexdigest()

    def _set_ai_review_summary(self, rows: int, standards: int, warnings: int, mode: str = "로컬 초안"):
        if not hasattr(self, "ai_review_cards"):
            return
        self.ai_review_cards["rows"].value_label.setText(str(rows))
        self.ai_review_cards["standards"].value_label.setText(str(standards))
        self.ai_review_cards["warnings"].value_label.setText(str(warnings))
        self.ai_review_cards["mode"].value_label.setText(mode)

    def _populate_ai_review_table(self, rows: list[dict], *, mode: str = "로컬 초안"):
        table = self.table_ai_review
        table.setSortingEnabled(False)
        table.setRowCount(len(rows))
        warnings = 0
        standards = set()
        for r, row in enumerate(rows):
            standard = row.get("standard") or row.get("성취기준 후보") or "(후보 없음)"
            next_step = row.get("next_step") or row.get("다음 확인") or ""
            if standard != "(후보 없음)":
                standards.add(standard.split("]")[0] + "]" if "]" in standard else standard)
            if "확인" in next_step or "점검" in next_step:
                warnings += 1
            values = [
                row.get("kind") or row.get("구분") or "",
                row.get("label") or row.get("번호/요소") or "",
                standard,
                row.get("review_type") or row.get("평가유형") or "",
                row.get("target") or row.get("목표수준 후보") or "",
                row.get("difficulty") or row.get("난이도 후보") or "",
                *[
                    row.get(f"{lv} 예상") or row.get(lv) or ""
                    for lv in LEVELS_AE
                ],
                row.get("evidence") or row.get("근거") or "",
                next_step,
            ]
            for c, value in enumerate(values):
                bg = None
                if c == len(values) - 1 and ("확인" in value or "점검" in value):
                    bg = QColor("#f8dfa3"); bg.setAlpha(140)
                _set_item(table, r, c, value, align_left=c in (1, 2, 11, 12), bg=bg, tooltip=value)
        table.setSortingEnabled(False)
        for col, width in enumerate([86, 120, 260, 92, 100, 100, 76, 76, 76, 76, 76, 260, 240]):
            self._set_scaled_column_width(table, col, width)
        self._set_ai_review_summary(len(rows), len(standards), warnings, mode)

    def _generate_ai_review_draft(self):
        if not hasattr(self, "txt_ai_review_source"):
            return
        text = self._ai_review_source_text()
        reference_text = self._ai_review_reference_text()
        if not text:
            QMessageBox.information(self, "AI 문항 검토", "먼저 문항 자료를 붙여 넣거나 시험 문제 PDF를 불러와 주세요.")
            return
        reference_entries = self._ai_reference_entries(reference_text)
        blocks = self._split_ai_review_blocks(text)
        rows = [self._infer_ai_review_row(block, reference_entries) for block in blocks]
        self._populate_ai_review_table(rows, mode="로컬 초안")
        self.txt_ai_review_prompt.setPlainText(self._make_ai_review_prompt(rows, text, reference_text))
        self.statusBar().showMessage(f"AI 문항 검토 초안 생성 완료 · {len(rows)}개 항목", 3500)

    def _run_ai_review_completion(self, resume_state: dict | None = None):
        if not hasattr(self, "txt_ai_review_source"):
            return
        text = self._ai_review_source_text()
        reference_text = self._ai_review_reference_text()
        if not text:
            QMessageBox.information(self, "AI 문항 검토", "먼저 문항 자료를 붙여 넣거나 시험 문제 PDF를 불러와 주세요.")
            return
        source_signature = self._ai_review_signature(text, reference_text)
        if resume_state and resume_state.get("signature") != source_signature:
            QMessageBox.warning(
                self,
                "AI 문항 검토",
                "문항 자료나 성취기준·수준 자료가 바뀌어 이어하기를 할 수 없습니다.\n처음부터 다시 AI로 보강해 주세요.",
            )
            self._ai_review_resume_state = None
            self._set_ai_review_control_state(running=False, can_resume=False)
            return
        config = self._ai_provider_config()
        self._save_ai_settings()
        reference_entries = self._ai_reference_entries(reference_text)
        blocks = self._split_ai_review_blocks(text)
        local_rows = [self._infer_ai_review_row(block, reference_entries) for block in blocks]
        resume_state = resume_state or None
        start_index = int(resume_state.get("next_index", 0)) if resume_state else 0
        seeded_rows = list(resume_state.get("merged_rows", [])) if resume_state else []
        seeded_outputs = list(resume_state.get("outputs", [])) if resume_state else []
        seeded_prompts = list(resume_state.get("prompts", [])) if resume_state else []
        seeded_failures = list(resume_state.get("failures", [])) if resume_state else []
        if resume_state:
            display_rows = seeded_rows + local_rows[start_index:]
            self._populate_ai_review_table(display_rows, mode="AI 보강 이어하기 준비")
        else:
            self._populate_ai_review_table(local_rows, mode="로컬 초안")
            self._ai_review_resume_state = None
            self._set_ai_review_control_state(running=False, can_resume=False)
        if config.provider == "local_draft":
            self.txt_ai_review_prompt.setPlainText(self._make_ai_review_prompt(local_rows, text, reference_text))
            self.statusBar().showMessage("로컬 초안으로 검토표를 갱신했습니다.", 3500)
            return

        preview_prompt = self._make_structured_ai_review_prompt(
            local_rows[: min(5, len(local_rows))],
            self._ai_review_source_for_blocks(blocks[: min(5, len(blocks))]),
            reference_text,
            source_limit=AI_REVIEW_CHUNK_SOURCE_LIMIT,
            reference_limit=AI_REVIEW_CHUNK_REFERENCE_LIMIT,
            row_limit=5,
            scope_note="미리보기용 일부 항목",
        )
        if hasattr(self, "chk_ai_scrub") and self.chk_ai_scrub.isChecked():
            preview_prompt = scrub_personal_data(preview_prompt, self._student_names_for_privacy())
        self.txt_ai_review_prompt.setPlainText(
            preview_prompt
            + "\n\n※ 실제 AI 보강은 시간초과를 줄이기 위해 문항을 작은 묶음으로 나누어 전송합니다."
        )
        endpoints = self._candidate_mlx_endpoints()
        scrub_enabled = hasattr(self, "chk_ai_scrub") and self.chk_ai_scrub.isChecked()
        student_names = self._student_names_for_privacy()
        cancel_event = threading.Event()
        self._ai_review_cancel_event = cancel_event
        self._set_ai_review_control_state(running=True, can_resume=False)

        def work(progress):
            prepared, note = self._prepare_ai_connection_config_for_worker(config, endpoints, progress)
            if prepared.provider in {"mlx_compatible", "ollama"} and prepared.timeout < 240:
                prepared.timeout = 240
                progress("문항 검토는 묶음별 요청으로 나누고, 대기 시간을 이번 요청에 한해 240초로 적용합니다.")
            size = self._model_size_hint(prepared.model)
            if 0 < size < 3:
                progress("현재 선택 모델은 빠른 확인용에 가까워 검토 품질이 낮을 수 있습니다. 품질이 중요하면 7B~15B급 모델을 선택해 보세요.")
            elif size >= 20:
                progress("현재 선택 모델은 큰 모델이라 품질은 좋아질 수 있지만 응답이 오래 걸릴 수 있습니다.")
            chunk_size = AI_REVIEW_CLOUD_CHUNK_SIZE
            if prepared.provider in {"mlx_compatible", "ollama"}:
                chunk_size = AI_REVIEW_LOCAL_CHUNK_SIZE
                if size >= 20:
                    chunk_size = 2
            chunks = [
                (idx, local_rows[idx: idx + chunk_size], blocks[idx: idx + chunk_size])
                for idx in range(start_index, len(local_rows), chunk_size)
            ]
            reference_entries_for_chunks = reference_entries
            progress(
                f"{prepared.label}에 문항 검토 요청 전송 중 · "
                f"{len(local_rows)}개 항목 중 {start_index + 1}번째부터 {len(chunks)}개 묶음으로 처리합니다."
            )
            merged_rows = list(seeded_rows)
            outputs = list(seeded_outputs)
            sent_prompts = list(seeded_prompts)
            failures = list(seeded_failures)
            for chunk_no, (start, chunk_rows, chunk_blocks) in enumerate(chunks, start=1):
                if cancel_event.is_set():
                    progress(f"중지 요청 반영 · {start + 1}번째 항목부터 이어하기 가능")
                    return {
                        "config": prepared,
                        "note": note,
                        "output": "\n\n".join(outputs),
                        "prompts": "\n\n".join(sent_prompts),
                        "rows": merged_rows + local_rows[start:],
                        "merged_rows": merged_rows,
                        "failures": failures,
                        "chunk_count": len(chunks),
                        "canceled": True,
                        "next_index": start,
                        "signature": source_signature,
                        "outputs_list": outputs,
                        "prompts_list": sent_prompts,
                    }
                end = start + len(chunk_rows)
                source_chunk = self._ai_review_source_for_blocks(chunk_blocks)
                reference_chunk = self._ai_reference_text_for_review_chunk(
                    chunk_rows,
                    reference_entries_for_chunks,
                    reference_text,
                )
                scope = f"{start + 1}-{end}번째 항목"
                chunk_prompt = self._make_structured_ai_review_prompt(
                    chunk_rows,
                    source_chunk,
                    reference_chunk,
                    source_limit=AI_REVIEW_CHUNK_SOURCE_LIMIT,
                    reference_limit=AI_REVIEW_CHUNK_REFERENCE_LIMIT,
                    row_limit=len(chunk_rows),
                    scope_note=scope,
                )
                if scrub_enabled:
                    chunk_prompt = scrub_personal_data(chunk_prompt, student_names)
                sent_prompts.append(f"===== 묶음 {chunk_no}/{len(chunks)} · {scope} =====\n{chunk_prompt}")
                progress(f"묶음 {chunk_no}/{len(chunks)} 전송 중 · {scope}")
                try:
                    output = run_completion(
                        chunk_prompt,
                        prepared,
                        max_tokens=max(1200, min(2600, len(chunk_rows) * 750)),
                    )
                except Exception as exc:
                    message = f"묶음 {chunk_no}/{len(chunks)} 실패 · 로컬 초안 유지 · {exc}"
                    progress(message)
                    failures.append(message)
                    outputs.append(f"===== 묶음 {chunk_no} 실패 =====\n{exc}")
                    merged_rows.extend(self._ai_review_failed_chunk_rows(chunk_rows, str(exc)))
                    continue
                outputs.append(f"===== 묶음 {chunk_no}/{len(chunks)} 응답 =====\n{output}")
                ai_rows = parse_review_rows(output)
                if not ai_rows:
                    progress(f"묶음 {chunk_no}/{len(chunks)} 응답 해석 실패 · 1문항씩 재시도")
                    single_rows = []
                    single_failures = []
                    for offset, (single_row, single_block) in enumerate(zip(chunk_rows, chunk_blocks), start=0):
                        if cancel_event.is_set():
                            next_index = start + offset
                            progress(f"중지 요청 반영 · {next_index + 1}번째 항목부터 이어하기 가능")
                            merged_rows.extend(single_rows)
                            return {
                                "config": prepared,
                                "note": note,
                                "output": "\n\n".join(outputs),
                                "prompts": "\n\n".join(sent_prompts),
                                "rows": merged_rows + local_rows[next_index:],
                                "merged_rows": merged_rows,
                                "failures": failures + single_failures,
                                "chunk_count": len(chunks),
                                "canceled": True,
                                "next_index": next_index,
                                "signature": source_signature,
                                "outputs_list": outputs,
                                "prompts_list": sent_prompts,
                            }
                        single_scope = f"{start + offset + 1}번째 항목"
                        single_prompt = self._make_structured_ai_review_prompt(
                            [single_row],
                            self._ai_review_source_for_blocks([single_block], limit_per_block=1800),
                            self._ai_reference_text_for_review_chunk([single_row], reference_entries_for_chunks, reference_text),
                            source_limit=3600,
                            reference_limit=5000,
                            row_limit=1,
                            scope_note=single_scope,
                        )
                        if scrub_enabled:
                            single_prompt = scrub_personal_data(single_prompt, student_names)
                        sent_prompts.append(f"===== 재시도 · {single_scope} =====\n{single_prompt}")
                        progress(f"재시도 전송 중 · {single_scope}")
                        try:
                            single_output = run_completion(single_prompt, prepared, max_tokens=1000)
                        except Exception as exc:
                            message = f"재시도 실패 · {single_scope} · {exc}"
                            progress(message)
                            single_failures.append(message)
                            outputs.append(f"===== 재시도 실패 · {single_scope} =====\n{exc}")
                            single_rows.extend(self._ai_review_failed_chunk_rows([single_row], str(exc)))
                            continue
                        outputs.append(f"===== 재시도 응답 · {single_scope} =====\n{single_output}")
                        parsed_single = parse_review_rows(single_output)
                        if parsed_single:
                            single_rows.extend(self._ai_review_merge_chunk_rows([single_row], parsed_single))
                            progress(f"재시도 완료 · {single_scope}")
                        else:
                            message = f"재시도 응답 해석 실패 · {single_scope}"
                            progress(message)
                            single_failures.append(message)
                            single_rows.extend(self._ai_review_failed_chunk_rows([single_row], "응답 해석 실패"))
                    merged_rows.extend(single_rows)
                    failures.extend(single_failures)
                    if single_failures:
                        failures.append(f"묶음 {chunk_no}/{len(chunks)} 일부 재시도 실패")
                    continue
                merged_rows.extend(self._ai_review_merge_chunk_rows(chunk_rows, ai_rows))
                progress(f"묶음 {chunk_no}/{len(chunks)} 완료 · {len(ai_rows)}개 응답")
            progress("AI 응답 수신, 검토표로 변환 중")
            return {
                "config": prepared,
                "note": note,
                "output": "\n\n".join(outputs),
                "prompts": "\n\n".join(sent_prompts),
                "rows": merged_rows,
                "merged_rows": merged_rows,
                "failures": failures,
                "chunk_count": len(chunks),
                "canceled": False,
                "next_index": len(local_rows),
                "signature": source_signature,
                "outputs_list": outputs,
                "prompts_list": sent_prompts,
            }

        def success(result):
            prepared = result["config"]
            note = result.get("note", "")
            output = result.get("output") or ""
            prompts = result.get("prompts") or ""
            ai_rows = result.get("rows") or []
            failures = result.get("failures") or []
            canceled = bool(result.get("canceled"))
            self._apply_prepared_ai_config(prepared, note)
            if not ai_rows:
                self.txt_ai_review_prompt.setPlainText(
                    prompts[:30000] + "\n\n[AI 원문 출력]\n" + (output or "(빈 응답)")[:20000]
                )
                QMessageBox.information(
                    self,
                    "AI 문항 검토",
                    "AI 응답은 받았지만 검토표로 해석하지 못했습니다.\nAI 프롬프트 탭의 원문 출력을 확인해 주세요.",
                )
                return
            if canceled:
                mode = f"{prepared.label} 보강 중지"
            else:
                mode = f"{prepared.label} 보강" if not failures else f"{prepared.label} 일부 보강"
            self._populate_ai_review_table(ai_rows, mode=mode)
            self.txt_ai_review_prompt.setPlainText(
                prompts[:30000] + "\n\n[AI 원문 출력]\n" + output[:30000]
            )
            self.ai_review_tabs.setCurrentWidget(self.table_ai_review)
            if canceled:
                self._ai_review_resume_state = {
                    "signature": result.get("signature"),
                    "next_index": int(result.get("next_index", 0)),
                    "merged_rows": list(result.get("merged_rows") or []),
                    "outputs": list(result.get("outputs_list") or []),
                    "prompts": list(result.get("prompts_list") or []),
                    "failures": list(failures),
                }
                self._set_ai_review_control_state(running=False, can_resume=True)
                done_message = (
                    f"AI 보강 중지 · {result.get('next_index', 0) + 1}번째 항목부터 이어하기 가능"
                )
            else:
                self._ai_review_resume_state = None
                self._set_ai_review_control_state(running=False, can_resume=False)
                done_message = f"AI 보강 완료 · {len(ai_rows)}개 항목 · 묶음 {result.get('chunk_count', 1)}개"
            if failures:
                done_message += f" · 일부 로컬 초안 유지 {len(failures)}개"
            if note:
                done_message += f" · {note}"
            self._append_ai_progress(done_message)
            self.ai_review_tabs.setCurrentWidget(self.table_ai_review)
            self._ai_review_cancel_event = None
            if failures and not canceled:
                QMessageBox.information(
                    self,
                    "AI 문항 검토",
                    "일부 묶음은 시간초과 또는 응답 해석 실패로 로컬 초안을 유지했습니다.\n"
                    "표의 '다음 확인' 열과 진행 로그를 확인해 주세요.",
                )

        self._run_ai_background_task("AI 문항 검토", work, success)

    def _export_ai_review_csv(self):
        if not hasattr(self, "table_ai_review") or self.table_ai_review.rowCount() == 0:
            QMessageBox.information(self, "AI 문항 검토", "먼저 검토 초안을 생성해 주세요.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "AI 문항 검토 CSV 저장", "ai_item_review.csv", "CSV (*.csv)"
        )
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(AI_REVIEW_HEADERS)
                for r in range(self.table_ai_review.rowCount()):
                    writer.writerow([
                        self.table_ai_review.item(r, c).text() if self.table_ai_review.item(r, c) else ""
                        for c in range(self.table_ai_review.columnCount())
                    ])
        except Exception as e:
            QMessageBox.critical(self, "AI 문항 검토", f"CSV 저장 중 오류가 발생했습니다.\n{e}")
            return
        self.statusBar().showMessage(f"AI 문항 검토 CSV 저장 완료 · {path}", 5000)

    def _ai_review_table_rows(self) -> list[dict]:
        if not hasattr(self, "table_ai_review") or self.table_ai_review.rowCount() == 0:
            return []
        rows = []
        for r in range(self.table_ai_review.rowCount()):
            values = [
                self.table_ai_review.item(r, c).text().strip() if self.table_ai_review.item(r, c) else ""
                for c in range(min(self.table_ai_review.columnCount(), len(AI_REVIEW_HEADERS)))
            ]
            if not any(values):
                continue
            rows.append(dict(zip(AI_REVIEW_HEADERS, values)))
        return rows

    @staticmethod
    def _ai_review_number(label: str, fallback: int) -> int:
        m = re.search(r"(\d{1,3})", label or "")
        if not m:
            return fallback
        try:
            return max(1, int(m.group(1)))
        except Exception:
            return fallback

    @staticmethod
    def _ai_review_level(value: str, fallback: str = "C") -> str:
        value = (value or "").strip().upper()
        return value if value in LEVELS_AE else fallback

    @staticmethod
    def _ai_review_difficulty(value: str) -> str:
        text = value or ""
        if "어려" in text:
            return "어려움"
        if "쉬" in text:
            return "쉬움"
        return "보통"

    @staticmethod
    def _ai_review_expected_type(value: str) -> str:
        text = value or ""
        if "서답" in text or "서술" in text or "논술" in text:
            return "서답형"
        return "선택형"

    def _ai_review_points_for_item(self, number: int, item_type: str, fallback: float = 5.0) -> float:
        if self.exam is None:
            return fallback
        candidates = [
            item for item in self.exam.items
            if int(item.number) == int(number) and item.item_type == item_type
        ]
        if not candidates:
            candidates = [item for item in self.exam.items if int(item.number) == int(number)]
        if not candidates:
            return fallback
        try:
            return float(candidates[0].score) or fallback
        except Exception:
            return fallback

    def _ai_review_points_for_row(self, number: int, item_type: str, row: dict, fallback: float = 5.0) -> float:
        exam_point = self._ai_review_points_for_item(number, item_type, fallback)
        if self.exam is not None and abs(exam_point - fallback) > 1e-6:
            return exam_point
        joined = " ".join(
            str(row.get(key, ""))
            for key in ("번호/요소", "근거", "다음 확인", "성취기준 후보")
        )
        patterns = [
            r"배점\s*(\d+(?:\.\d+)?)\s*점",
            r"\[(\d+(?:\.\d+)?)\s*점\]",
            r"(\d+(?:\.\d+)?)\s*점",
        ]
        for pattern in patterns:
            matches = re.findall(pattern, joined)
            if not matches:
                continue
            try:
                value = float(matches[0])
            except Exception:
                continue
            if 0 < value <= 100:
                return value
        return exam_point

    @staticmethod
    def _parse_expected_count(value: str, default_sample: int = 3) -> tuple[int | None, int]:
        text = (value or "").strip()
        if not text:
            return None, default_sample
        ox_text = text.upper().replace("○", "O").replace("×", "X")
        if any(mark in ox_text for mark in ("O", "X")):
            marks = [ch for ch in ox_text if ch in {"O", "X"}]
            if marks:
                return marks.count("O"), max(1, min(10, len(marks)))
        frac = re.search(r"(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)", text)
        if frac:
            numerator = float(frac.group(1))
            denominator = max(1, min(10, round(float(frac.group(2)))))
            return max(0, min(denominator, round(numerator))), denominator
        pct = re.search(r"(-?\d+(?:\.\d+)?)\s*%", text)
        if pct:
            rate = max(0.0, min(100.0, float(pct.group(1))))
            return round((rate / 100.0) * default_sample), default_sample
        number = re.search(r"-?\d+(?:\.\d+)?", text)
        if number:
            value_num = float(number.group(0))
            if 0 <= value_num <= 1:
                return round(value_num * default_sample), default_sample
            if 0 <= value_num <= default_sample:
                return round(value_num), default_sample
            if 0 <= value_num <= 100:
                return round((value_num / 100.0) * default_sample), default_sample
        return None, default_sample

    def _ai_expected_counts_for_row(self, row: dict) -> tuple[dict[str, int], int]:
        parsed: dict[str, int] = {}
        sample_size = 3
        for lv in LEVELS_AE:
            count, denominator = self._parse_expected_count(row.get(f"{lv} 예상", ""), sample_size)
            if count is not None:
                sample_size = denominator
                parsed[lv] = max(0, min(sample_size, count))
        if len(parsed) != len(LEVELS_AE):
            fallback = self._ai_default_ox_expected_values(
                row.get("목표수준 후보", "C"),
                row.get("난이도 후보", "보통"),
            )
            for lv in LEVELS_AE:
                if lv not in parsed:
                    count, denominator = self._parse_expected_count(fallback.get(f"{lv} 예상", ""), sample_size)
                    sample_size = denominator
                    parsed[lv] = 0 if count is None else count
        prev = sample_size
        for lv in LEVELS_AE:
            parsed[lv] = max(0, min(sample_size, min(prev, parsed[lv])))
            prev = parsed[lv]
        return parsed, sample_size

    @staticmethod
    def _judgments_from_expected_counts(counts: dict[str, int], sample_size: int) -> dict:
        judgments = {}
        sample_size = max(1, min(10, int(sample_size)))
        for lv in LEVELS_AE:
            count = max(0, min(sample_size, int(counts.get(lv, 0))))
            rate = round((count / sample_size) * 100, 2)
            judgments[lv] = {
                "correct": [idx < count for idx in range(sample_size)],
                "targetRate": rate,
                "overrideRate": None,
            }
        return judgments

    @staticmethod
    def _parse_expected_score(value: str, max_score: float) -> float | None:
        text = (value or "").strip()
        if not text:
            return None
        frac = re.search(r"(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)", text)
        if frac:
            denominator = float(frac.group(2))
            if denominator > 0:
                return max_score * (float(frac.group(1)) / denominator)
        pct = re.search(r"(-?\d+(?:\.\d+)?)\s*%", text)
        if pct:
            return max_score * (float(pct.group(1)) / 100.0)
        number = re.search(r"-?\d+(?:\.\d+)?", text)
        if not number:
            return None
        value_num = float(number.group(0))
        if 0 <= value_num <= 1:
            return max_score * value_num
        if 0 <= value_num <= max_score:
            return value_num
        if 0 <= value_num <= 100:
            return max_score * (value_num / 100.0)
        return None

    def _ai_review_expected_scores_for_perform_row(self, row: dict, max_score: float) -> dict:
        parsed = {}
        for lv in LEVELS_AE:
            score = self._parse_expected_score(row.get(f"{lv} 예상", ""), max_score)
            if score is not None:
                parsed[lv] = max(0.0, min(float(max_score), score))
        if not parsed:
            return {}
        prev = float(max_score)
        for lv in LEVELS_AE:
            if lv not in parsed:
                parsed[lv] = prev
            parsed[lv] = max(0.0, min(prev, parsed[lv]))
            prev = parsed[lv]
        return parsed

    def _build_ai_review_spliter_project(self) -> dict | None:
        rows = self._ai_review_table_rows()
        items = []
        for idx, row in enumerate(rows, start=1):
            review_type = row.get("평가유형", "")
            if "수행" in review_type:
                continue
            if not any(token in review_type for token in ("선택", "서답", "지필", "문항")):
                continue
            number = self._ai_review_number(row.get("번호/요소", ""), idx)
            item_type = self._ai_review_expected_type(review_type)
            difficulty = self._ai_review_difficulty(row.get("난이도 후보", ""))
            target = self._ai_review_level(row.get("목표수준 후보", ""), "C")
            standard = row.get("성취기준 후보", "")
            evidence = row.get("근거", "")
            next_step = row.get("다음 확인", "")
            counts, sample_size = self._ai_expected_counts_for_row(row)
            judgments = self._judgments_from_expected_counts(counts, sample_size)
            items.append({
                "id": f"ai-review-{idx}-{number}",
                "number": number,
                "title": row.get("번호/요소", "") or f"{number}번",
                "standard": "" if standard == "(후보 없음)" else standard,
                "points": self._ai_review_points_for_row(number, item_type, row, 5.0),
                "sampleSize": sample_size,
                "type": item_type,
                "difficulty": difficulty,
                "targetLevel": target,
                "judgmentsByJudge": {
                    "teacher-1": judgments,
                    "teacher-2": judgments,
                },
                "evidence": ["AI 검토 초안"],
                "note": " · ".join(part for part in [evidence, next_step] if part),
            })
        if not items:
            return None
        project = {
            "version": 1,
            "judges": [
                {"id": "teacher-1", "name": "교사 1"},
                {"id": "teacher-2", "name": "교사 2"},
            ],
            "activeJudgeId": "teacher-1",
            "items": items,
            "evidenceMode": "difficultyAverage",
        }
        if self.exam is not None and self.overall is not None:
            project["evidenceData"] = self._build_spliter_evidence_payload()
        return project

    def _send_ai_review_to_spliter(self):
        project = self._build_ai_review_spliter_project()
        if project is None:
            QMessageBox.information(
                self,
                "AI 문항 검토",
                "예상정답률 계산기로 보낼 지필 문항 초안이 없습니다.\n먼저 검토 초안을 생성하거나 평가유형을 선택형/서답형으로 수정해 주세요.",
            )
            return
        if self.spliter_view is None:
            QMessageBox.information(self, "AI 문항 검토", "이 환경에서는 내장 예상정답률 계산기를 열 수 없습니다.")
            return
        self._spliter_pending_project_payload = project
        if self.exam is not None and self.overall is not None:
            self._spliter_pending_payload = self._build_spliter_evidence_payload()
        self.tabs.setCurrentWidget(self.tab_spliter)
        if self._spliter_loaded:
            self._flush_spliter_project_payload()
            self._flush_spliter_payload()
        else:
            self._load_spliter_web()
        self.statusBar().showMessage(f"AI 검토 지필 초안 {len(project['items'])}개를 예상정답률 계산기로 보냈습니다.", 5000)

    def _extract_perform_max_score_from_review(self, *texts: str) -> float:
        joined = " ".join(texts)
        for area in getattr(self.perform_data, "areas", []) if self.perform_data is not None else []:
            if area.name and area.name in joined:
                return float(area.max_score)
        numbers = re.findall(r"(\d+(?:\.\d+)?)\s*점", joined)
        if numbers:
            try:
                return max(1.0, float(numbers[-1]))
            except Exception:
                pass
        return 10.0

    def _send_ai_review_to_perform_recalc(self):
        rows = [
            row for row in self._ai_review_table_rows()
            if "수행" in row.get("평가유형", "") or "수행" in row.get("구분", "")
        ]
        if not rows:
            QMessageBox.information(
                self,
                "AI 문항 검토",
                "수행평가 재산정으로 보낼 초안이 없습니다.\n수행평가 채점기준표를 불러와 초안을 만들거나 평가유형을 수행평가로 수정해 주세요.",
            )
            return
        self.table_perform_recalc.blockSignals(True)
        self.table_perform_recalc.setRowCount(0)
        self.table_perform_recalc.blockSignals(False)
        self._perform_recalc_dirty = True
        for row in rows:
            name = row.get("번호/요소", "") or f"평가요소 {self.table_perform_recalc.rowCount() + 1}"
            max_score = self._extract_perform_max_score_from_review(
                name, row.get("성취기준 후보", ""), row.get("근거", ""), row.get("다음 확인", "")
            )
            values = {
                "name": name,
                "max_score": max_score,
                "memo": "AI 검토 초안 · " + " · ".join(
                    part for part in [row.get("목표수준 후보", ""), row.get("난이도 후보", ""), row.get("근거", "")]
                    if part
                ),
            }
            values.update(self._ai_review_expected_scores_for_perform_row(row, max_score))
            self._add_perform_recalc_row(values)
        self._render_perform_recalc_results()
        self.tabs.setCurrentWidget(self.tab_perform)
        if hasattr(self, "perform_table_tabs"):
            self.perform_table_tabs.setCurrentIndex(2)
        self.statusBar().showMessage(f"AI 검토 수행 초안 {len(rows)}개를 수행평가 재산정 표로 보냈습니다.", 5000)

    # ---- 도움말 -------------------------------------------------------
    def _init_tab_help(self):
        layout = QVBoxLayout(self.tab_help)
        txt = QTextBrowser(); txt.setReadOnly(True); txt.setOpenExternalLinks(True)
        txt.setHtml(f"""
        <style>
          body {{ line-height: 1.62; }}
          h1 {{ margin: 0 0 4px; font-size: 22px; }}
          h2 {{ margin: 22px 0 8px; font-size: 17px; }}
          p {{ margin: 6px 0; }}
          ul, ol {{ margin-top: 6px; margin-bottom: 10px; }}
          li {{ margin: 5px 0; }}
          code {{ padding: 2px 5px; border-radius: 4px; }}
          .muted {{ opacity: .78; }}
          .card {{ border: 1px solid #8aa; border-radius: 8px; padding: 12px 14px; margin: 10px 0; }}
        </style>
        <h1>성취평가 결과 분석 Goedu-Split</h1>
        <p class="muted">v{APP_VERSION} · 제작자: {APP_AUTHOR} · {APP_COPYRIGHT}</p>

        <div class="card">
          <b>이 앱은 무엇을 하나요?</b>
          <p>정오표와 문항정보표를 불러와 학생 성취수준, 문항 정답률, 변별도, 답지반응,
          성취기준별 정답률을 한 번에 확인하는 로컬 분석 도구입니다. 자료는 사용자의 컴퓨터 안에서만 처리됩니다.</p>
        </div>

        <h2>빠른 시작</h2>
        <ol>
          <li>왼쪽의 <b>폴더에서 한 번에 불러오기</b>를 누르고 성취평가 자료 폴더를 선택합니다.</li>
          <li>정오표, 문항정보표, 추정분할점수, 수행평가 파일이 자동으로 채워졌는지 확인합니다.</li>
          <li>분할점수를 확인한 뒤 <b>분석 실행</b>을 누릅니다.</li>
        </ol>

        <h2>왼쪽 입력 패널</h2>
        <ul>
          <li><b>학생답 정오표</b>: 학생별 답, 선택형/서답형 점수, 과목총점이 들어 있는 파일입니다.</li>
          <li><b>문항정보표</b>: 문항번호, 성취기준, 난이도, 배점, 정답을 읽습니다.</li>
          <li><b>분할점수</b>: 90, 80, 70, 60, 40이면 <b>고정 분할 방식</b>, 그 밖의 값이면 <b>추정 분할 방식</b>으로 표시합니다.</li>
          <li><b>수행평가</b>: 체크하면 지필과 수행 반영비율을 합산해 최종 환산점수를 계산합니다.</li>
        </ul>

        <h2>Data 탭</h2>
        <ul>
          <li><b>환산점수 분포</b>: 학생 점수가 어디에 모여 있는지 성취수준 색으로 보여줍니다.</li>
          <li><b>학생 검색</b>: 이름이나 반/번호를 입력하면 표가 즉시 필터링됩니다. 여러 명은 쉼표로 구분합니다.</li>
          <li>검색된 학생은 그래프 위에 세로선과 이름으로 표시되어, 분포 안 위치를 바로 볼 수 있습니다.</li>
          <li><b>정규분포·점검</b>: 평균, ±1표준편차, ±2표준편차와 정규분포 곡선을 함께 보여줍니다.</li>
          <li><b>모니터링 탭</b>: 성취평가 외부점검 지표를 별도 탭에서 더 자세히 확인합니다.</li>
        </ul>

        <h2>모니터링 탭</h2>
        <ul>
          <li><b>현재 A 비율, 과목 평균, 표준편차, A/B 분할점수</b>는 분석 결과에서 자동으로 들어옵니다.</li>
          <li><b>전국 기준</b>에는 동일 학교유형·교과군의 전국 평균과 표준편차를 입력합니다.</li>
          <li><b>전년도 기준</b>에는 같은 과목의 전년도 A 비율, 과목 평균, A/B 분할점수를 입력합니다.</li>
          <li><b>필수 지표</b>는 A 비율이 전국 평균보다 높은지, 과목 평균이 A/B 분할점수보다 높은지를 봅니다.</li>
          <li><b>특성 지표</b>는 과목 평균, A/B 분할점수, 전년도 대비 변화가 어떤 방향으로 움직였는지 함께 해석합니다.</li>
          <li>Ⅰ/Ⅱ/Ⅲ 판정은 자동 결론이 아니라 “어디부터 질문할지”를 정하는 점검 신호로 사용하세요.</li>
        </ul>

        <h2>전체 성취도 분석</h2>
        <ul>
          <li><b>성취수준 비율</b>: A부터 미도달까지 학생 비율과 인원을 도넛 차트로 보여줍니다.</li>
          <li><b>평균±표준편차</b>: 각 성취수준 안의 점수 평균과 흩어짐을 확인합니다.</li>
          <li><b>학급별 평균</b>: 학급 간 평균 차이를 살펴봅니다.</li>
        </ul>

        <h2>수행평가 분석</h2>
        <ul>
          <li><b>영역별 요약</b>: 수행평가 각 영역의 평균, 표준편차, 평균점수율, 만점자 비율, 50% 미만 비율을 봅니다.</li>
          <li><b>지필총점 × 수행평가 환산</b>: 지필과 수행이 비슷하게 움직이는지, 특정 학생군이 수행에서 강점/보완점을 보이는지 확인합니다.</li>
          <li><b>학생별 차이</b>: 수행환산점수와 지필총점의 차이가 큰 학생을 먼저 보여줍니다. 수행 강점·수행 보완 학생을 빠르게 찾을 수 있습니다.</li>
          <li><b>분할점수 재산정</b>: 평가요소별로 A~E 최소능력자가 받을 것으로 예상되는 점수를 입력하면 A/B, B/C, C/D, D/E, E/미도달 분할점수를 계산합니다.</li>
          <li><b>자료 기준 딸깍 추천</b>: 수행평가 자료가 있으면 각 성취수준에서 경계에 가까운 대표 학생들의 영역별 점수를 바탕으로 초기값을 제안합니다.</li>
          <li>영역별 2/3 기준선은 “해당 수준 학생이 어느 정도 안정적으로 해결 가능한가”를 보는 참고선입니다. 최종 판단은 채점기준표와 문항지를 함께 보며 교사가 조정합니다.</li>
        </ul>

        <h2>문항 분석</h2>
        <ul>
          <li>문항은 기본적으로 오름차순으로 정렬됩니다.</li>
          <li><b>정답률</b>은 전체 학생 중 정답자의 비율입니다.</li>
          <li><b>변별도</b>는 해당 문항을 맞힌 학생과 총점이 높은 학생 사이의 관련성을 봅니다.</li>
          <li>성취수준별 정답률이 낮은 칸은 음영으로 표시되어 재검토할 문항을 찾기 쉽습니다.</li>
        </ul>

        <h2>답지반응분포</h2>
        <p>각 성취수준 학생들이 어느 선택지를 골랐는지 봅니다. 오답 매력도가 높은 선택지나 특정 수준에서 흔한 오개념을 찾을 때 유용합니다.</p>

        <h2>성취기준 분석 결과</h2>
        <p>성취기준별 평균 정답률과 성취수준별 정답률을 함께 보여줍니다. 어느 성취기준에서 어려움이 컸는지 확인할 수 있습니다.</p>

        <h2>예상정답률 입력</h2>
        <p>분석된 실제 학생 자료를 근거로 새 문항의 예상정답률을 O/X 방식으로 조정합니다.
        A, B, C, D, E 수준 최소능력자가 맞힐지 판단하면 분할점수 산정용 예상정답률로 환산됩니다.</p>
        <p>이 앱에서 <b>A 수준 문항</b>이라는 말은 A 수준 학생 대표 3명 중 약 2명, 즉 2/3 정도가 맞힐 수 있는 문항이라는 뜻입니다.
        B, C, D, E 문항도 같은 방식으로 이해하면 됩니다.</p>
        <p>분석자료 없이도 기본 문항으로 바로 사용할 수 있습니다. 분석자료가 전달되면 지난 정기시험의
        난이도·성취수준별 응답 자료를 기준으로 기본 예상정답률을 맞춘 뒤, 교사가 새 시험 설계에 맞게 조정합니다.</p>
        <p><b>문항 추가</b>로 새 문항을 만들고, 표에서 체크한 문항은 <b>선택 제거</b>로 한 번에 삭제할 수 있습니다.
        행 끝의 휴지통 아이콘은 해당 문항 하나만 지울 때 사용합니다.</p>
        <p><b>시험지 자동 반영</b>은 HWPX, PDF, DOCX, 엑셀, 텍스트 자료를 문항 단위로 읽어 예상정답률 계산기에 바로 넣습니다.
        HWP 파일은 로컬에 <code>kordoc</code> 또는 <code>hwp5txt</code> 변환기가 설치된 경우 자동으로 시도하며, 안정성을 위해 HWPX 저장본을 권장합니다.</p>
        <p><b>문항 구성안 제안</b>은 사용자가 입력한 문항 수에 맞춰 성취수준 목표와 배점을 먼저 제시합니다.
        분석자료가 있으면 기존 문항의 정답률·난이도·배점 분포를 참고하고, 없으면 100점 기준 기본 구성안을 만듭니다.</p>
        <p>지필평가는 문항별 예상정답률을 합산해 분할점수를 만들고, 수행평가는 평가요소별 예상점수를 합산해 분할점수를 만듭니다.
        두 기능은 모두 “최소능력자가 어느 정도 수행할 수 있는가”를 숫자로 옮기는 같은 구조입니다.</p>

        <h2>AI 문항 검토 방향</h2>
        <p><b>AI 문항 검토</b> 탭은 시험 문제 자료를 먼저 문항 단위로 읽고, 별도로 넣은 성취기준·성취수준 자료와 대조해 검토 초안을 만드는 작업 공간입니다.</p>
        <ul>
          <li><b>문항 자료</b>: 시험 문제 HWPX/PDF/DOCX, 문항정보표, 수행평가 채점기준표를 문항 자료 칸으로 불러옵니다. PDF는 텍스트 추출 가능한 파일이어야 합니다.</li>
          <li><b>성취기준·수준 자료</b>: 성취기준, 성취수준 A~E 설명, 최소능력자 특성 자료를 참고자료 칸으로 불러옵니다.</li>
          <li><b>현재 문항정보표</b>: 이미 분석한 문항정보표를 검토 원문으로 가져옵니다.</li>
          <li><b>검토 초안 생성</b>: 문항 자료를 먼저 나누고 참고자료와 대조해 성취기준 후보, 평가유형, 목표수준 후보, 난이도 후보, 근거, 추가 확인 질문을 표로 정리합니다.</li>
          <li><b>AI로 보강</b>: AI 설정에 지정한 로컬/클라우드 모델이 문항 자료와 성취기준·수준 자료를 함께 읽고 검토표를 다시 제안합니다. 기본값은 외부 전송이 없는 로컬 초안입니다.</li>
          <li><b>A~E 예상</b>: 지필 문항은 각 수준 대표 3명 중 몇 명이 맞힐지 <code>2/3</code>처럼 표시하고, 수행평가는 <code>80%</code> 또는 <code>8점</code>처럼 예상점수를 표시합니다.</li>
          <li><b>AI 설정</b>: Ollama 로컬, MLX-LM/LM Studio 같은 OpenAI 호환 로컬 서버, 클라우드 API의 엔드포인트와 모델을 저장합니다.</li>
          <li><b>개인정보 제거</b>: 외부 서버로 보낼 때 학생 이름, 반/번호, 전화번호, 이메일을 가능한 한 제거합니다. 그래도 최종 전송 여부는 교사가 확인합니다.</li>
          <li><b>지필→예상정답률</b>: 선택형·서답형 문항 초안과 A~E 예상 O/X 값을 예상정답률 계산기로 보내 문항별 판단을 이어갑니다.</li>
          <li><b>수행→재산정</b>: 수행평가 평가요소 초안과 A~E 예상점수를 수행평가 분할점수 재산정 표로 보내 합산을 이어갑니다.</li>
          <li><b>AI 프롬프트</b>: 향후 AI 연결 또는 별도 AI 검토에 바로 사용할 수 있는 안전한 검토 요청문을 만듭니다.</li>
        </ul>
        <p>AI 판정은 자동 확정이 아니라, 근거 문장과 함께 제안하고 교사가 최종 수정하는 방식으로 사용합니다.</p>

        <h2>단축키와 조작</h2>
        <ul>
          <li><code>Ctrl+R</code>: 분석 실행</li>
          <li><code>Ctrl+E</code>: 결과 CSV 내보내기</li>
          <li><code>Ctrl+1/2/3</code>: 라이트 / 다크 / 자동 테마</li>
          <li><code>Ctrl + + / -</code>: 화면 배율 조절</li>
          <li><code>Ctrl+Z</code>, <code>Ctrl+Shift+Z</code>: 예상정답률 계산기에서 입력 되돌리기 / 다시 실행</li>
          <li>예상정답률 계산기: <b>문항 추가</b>로 새 문항 생성, <b>선택 제거</b>로 체크한 문항 삭제</li>
          <li>그래프 위 마우스 휠: 확대/축소, 더블클릭: 원상복귀</li>
        </ul>

        <h2>계산 기준</h2>
        <ul>
          <li>환산점수 = 지필점수 × 지필반영비율 + 수행환산점수 × 수행반영비율</li>
          <li>성취수준은 환산점수를 반올림한 정수 점수와 분할점수를 비교해 판정합니다.</li>
          <li>Cronbach α는 지필 문항의 내적 일관성을 확인하는 참고 지표입니다.</li>
        </ul>
        """)
        layout.addWidget(txt)

    # --------------------------------------------------------------- 메뉴
    def _build_menu(self):
        m_file = self.menuBar().addMenu("파일")
        a_run = QAction("분석 실행", self); a_run.setShortcut("Ctrl+R")
        a_run.triggered.connect(self.run_analysis); m_file.addAction(a_run)
        a_exp = QAction("결과 CSV 내보내기…", self); a_exp.setShortcut("Ctrl+E")
        a_exp.triggered.connect(self.export_csv); m_file.addAction(a_exp)
        a_spliter = QAction("예상정답률 근거 엑셀 내보내기…", self)
        a_spliter.triggered.connect(self.export_spliter_evidence); m_file.addAction(a_spliter)
        m_file.addSeparator()
        a_quit = QAction("종료", self); a_quit.setShortcut("Ctrl+Q")
        a_quit.triggered.connect(self.close); m_file.addAction(a_quit)

        m_view = self.menuBar().addMenu("보기")
        self._theme_actions = {}
        if self.theme is not None:
            grp = QActionGroup(self); grp.setExclusive(True)
            for key, label, shortcut in (
                ("light", "라이트 모드", "Ctrl+1"),
                ("dark", "다크 모드", "Ctrl+2"),
                ("auto", "자동 (시간대 기반)", "Ctrl+3"),
            ):
                a = QAction(label, self, checkable=True)
                a.setShortcut(shortcut)
                a.triggered.connect(lambda _=False, k=key: self._set_theme(k))
                grp.addAction(a); m_view.addAction(a)
                self._theme_actions[key] = a
            self._theme_actions[self.theme.mode].setChecked(True)
            m_view.addSeparator()
            a_refresh = QAction("차트 다시 그리기", self); a_refresh.setShortcut("F5")
            a_refresh.triggered.connect(self._refresh_all_charts)
            m_view.addAction(a_refresh)

        m_help = self.menuBar().addMenu("도움말")
        a_about = QAction("프로그램 정보", self)
        a_about.triggered.connect(self._show_about); m_help.addAction(a_about)

    def _set_theme(self, key: str):
        if self.theme is None:
            return
        self.theme.set_mode(key)
        # _on_theme_changed가 차트 재렌더 처리

    def _build_statusbar(self):
        sb = self.statusBar()
        right = QLabel(f"{APP_COPYRIGHT}   v{APP_VERSION}")
        right.setProperty("role", "muted")
        sb.addPermanentWidget(right)

    def _on_theme_changed(self, eff: str):
        charts.set_theme(self.theme.colors)
        # 메뉴 체크 상태 + 헤더 버튼 동기화
        if hasattr(self, "_theme_actions") and self.theme.mode in self._theme_actions:
            self._theme_actions[self.theme.mode].setChecked(True)
        if hasattr(self, "btn_theme"):
            self._refresh_header_icons()
        self._send_spliter_theme()
        self._apply_zoom_to_surfaces()
        self._refresh_all_charts()

    def _refresh_all_charts(self):
        if self.exam is None:
            return
        self._render_data_tab()
        self._render_monitor_tab()
        self._render_overview()
        self._render_perform_tab()
        self._render_items()
        self._render_choice()
        self._render_standard()
        self._render_spliter_tab()

    def _show_about(self):
        QMessageBox.information(
            self, "프로그램 정보",
            f"<h3>Goedu-Split – 성취평가 결과 분석 데스크톱</h3>"
            f"<p>v{APP_VERSION} · 2026</p>"
            f"<p><b>제작자:</b> {APP_AUTHOR}</p>"
            f"<p>{APP_COPYRIGHT}</p>"
            "<p>본 데스크톱 버전은 PySide6/Qt와 matplotlib으로 재구성한 로컬 분석 도구이며, "
            "데이터는 본 PC를 떠나지 않습니다.</p>"
        )

    # --------------------------------------------------------- 분석 실행
    def run_analysis(self):
        if not self.fs_response.path() or not self.fs_iteminfo.path():
            QMessageBox.warning(self, "입력 부족",
                                "정오표와 문항정보표 두 파일을 먼저 지정해 주세요.")
            return
        try:
            exam = load_exam(self.fs_iteminfo.path(), self.fs_response.path())
        except Exception as e:
            QMessageBox.critical(self, "파싱 오류",
                                 f"파일을 읽는 중 오류:\n{e}\n\n{traceback.format_exc()}")
            return
        exam.cut_scores = {lv: float(self.spin_cuts[lv].value()) for lv in ["A","B","C","D","E"]}

        # 수행평가 결합
        perform_data = None
        if self.chk_perform.isChecked() and self.fs_perform.path():
            try:
                perform_data = load_perform(self.fs_perform.path())
            except Exception as e:
                QMessageBox.warning(self, "수행평가 파일 오류",
                                    f"수행평가 파일을 읽지 못했습니다. 지필만 분석합니다.\n{e}")
        apply_perform(
            exam, perform_data,
            float(self.spin_pencil_ratio.value()),
            float(self.spin_perform_ratio.value()),
        )

        try:
            score_mat, _, _ = build_score_matrix(exam)
            overall = analyze_overall(exam, score_mat)
            items = analyze_items(exam)[0]
        except Exception as e:
            QMessageBox.critical(self, "분석 오류", f"{e}\n\n{traceback.format_exc()}")
            return

        self.exam, self.overall, self.item_stats, self.perform_data = exam, overall, items, perform_data
        # 마지막 분석 시점 입력 스냅샷 저장 (실수 복원용)
        self._snapshot_inputs()
        if hasattr(self, "btn_revert"):
            self.btn_revert.setEnabled(True)
        self.exam_info_lbl.setText(
            f"<b>{exam.subject or '(과목 미상)'}</b><br>"
            f"{exam.semester} {exam.grade}<br>"
            f"학생 {len(exam.students)}명 · 문항 {len(exam.items)}문항"
        )
        if perform_data is not None and hasattr(self, "table_perform_recalc") and not self._perform_recalc_dirty:
            self._recommend_perform_recalc_rows()
        self._render_data_tab()
        self._render_monitor_tab()
        self._render_overview()
        self._render_perform_tab()
        self._render_items()
        self._render_choice_combo()
        self._render_choice()
        self._render_standard()
        self._render_spliter_tab()
        if self.spliter_view is not None:
            self._spliter_pending_payload = self._build_spliter_evidence_payload()
            self._flush_spliter_payload()
        self.statusBar().showMessage(
            f"분석 완료 · N={overall.n_students} · α={overall.cronbach_alpha:.3f} "
            f"({reliability_label(overall.cronbach_alpha)}) · "
            f"분할점수 A≥{int(exam.cut_scores['A'])} B≥{int(exam.cut_scores['B'])} "
            f"C≥{int(exam.cut_scores['C'])} D≥{int(exam.cut_scores['D'])} E≥{int(exam.cut_scores['E'])}"
        )

    # ------------------------------------------------------------- 렌더링
    def _render_data_tab(self):
        ov = self.overall
        self.kpi_n.value_label.setText(f"{ov.n_students} 명")
        self.kpi_n_items.value_label.setText(f"{len(self.exam.items)} 문항")
        self.kpi_subject.value_label.setText(self.exam.subject or "-")

        totals = [s.final_score for s in self.exam.students]
        search_text = self.le_search.text() if hasattr(self, "le_search") else ""
        self._render_score_histogram_for_search(search_text)
        self.canvas_score_normal.set_figure(
            charts.fig_score_normal_monitoring(totals, self.exam.cut_scores, ov.level_dist_pct)
        )
        if totals:
            mean = sum(totals) / len(totals)
            std = float((sum((x - mean) ** 2 for x in totals) / max(1, len(totals) - 1)) ** 0.5)
            expected_a = (1 - _normal_cdf(float(self.exam.cut_scores["A"]), mean, std)) * 100 if std > 0 else 0.0
            self.lbl_normal_note.setText(
                f"평균 {mean:.2f}점 · 표준편차 {std:.2f}점 · "
                f"실제 A {ov.level_dist_pct.get('A', 0):.1f}% · "
                f"정규분포 기준 기대 A {expected_a:.1f}%"
            )

        # 학생별 응답표 — 학번 제거, 반/번호+이름을 앞쪽 두 컬럼에 고정 폭으로 둬
        # 가로 스크롤해도 항상 식별 가능. 점수 컬럼들도 앞쪽으로 옮겨 핵심을 우선 노출.
        items = sorted([it for it in self.exam.items if it.item_type == "선택형"],
                       key=lambda x: x.number)
        # KICE 원본 웹앱과 동일: 환산점수는 '반올림 정수 원점수'로 표시
        score_headers = ["성취도", "원점수"]
        if self.exam.use_perform:
            score_headers += ["수행환산", "지필총점"]
        else:
            score_headers += ["지필총점"]
        item_headers = [f"문{it.number}" for it in items]
        headers = ["반/번호", "이름"] + score_headers + item_headers
        self.table_data.setColumnCount(len(headers))
        self.table_data.setHorizontalHeaderLabels(headers)
        self.table_data.setRowCount(len(self.exam.students))

        # 컬럼 폭 — 반/번호와 이름이 잘리지 않게 충분히 넓힘 (좌측 고정 효과)
        hh = self.table_data.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.Fixed)
        self._set_scaled_column_width(self.table_data, 0, 95)   # 반/번호
        self._set_scaled_column_width(self.table_data, 1, 110)  # 이름
        score_n = len(score_headers)
        for i in range(2, 2 + score_n):
            self._set_scaled_column_width(self.table_data, i, 92)
        for i in range(2 + score_n, len(headers)):
            self._set_scaled_column_width(self.table_data, i, 56)

        # 정렬을 위해 채우는 동안 sorting OFF
        self.table_data.setSortingEnabled(False)
        # 성취도 정렬을 위해 A~E,미도달을 숫자로 매핑
        level_order = {"A": 6, "B": 5, "C": 4, "D": 3, "E": 2, "미도달": 1}
        for r, s in enumerate(self.exam.students):
            level = ov.levels_arr[r]

            # 반/번호 — 표시는 '1/3' 그대로, 정렬은 (반,번호) 튜플 비교 (NaturalItem)
            cls_text = s.class_no or ""
            sort_value = _class_no_sort_value(cls_text)
            it_cls = NaturalItem(cls_text, sort_value)
            it_cls.setTextAlignment(Qt.AlignCenter)
            it_cls.setData(Qt.UserRole + 101, r)
            self.table_data.setItem(r, 0, it_cls)

            # 이름
            _set_item(self.table_data, r, 1, s.name or "-", align_left=True,
                      tooltip=s.name)

            col = 2
            # 성취도 — 표시는 A/B/.../미도달, 정렬은 1~6 (NaturalItem)
            it_lv = NaturalItem(level, level_order.get(level, 0))
            it_lv.setTextAlignment(Qt.AlignCenter)
            f = it_lv.font(); f.setBold(True); it_lv.setFont(f)
            level_color = charts.COLOR_LEVELS.get(level, "#ffffff")
            it_lv.setBackground(QBrush(QColor(level_color)))
            it_lv.setForeground(QBrush(_contrast_text_for_fill(level_color)))
            self.table_data.setItem(r, col, it_lv); col += 1

            # 원점수 — 표시는 반올림 정수, 정렬은 float
            it_fs = NaturalItem(f"{round(s.final_score)}", float(s.final_score))
            it_fs.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            it_fs.setToolTip(f"환산점수 {s.final_score:.2f} → 반올림 {round(s.final_score)}")
            f = it_fs.font(); f.setBold(True); it_fs.setFont(f)
            self.table_data.setItem(r, col, it_fs); col += 1

            if self.exam.use_perform:
                it_ps = NaturalItem(f"{s.perform_score:.1f}", float(s.perform_score))
                it_ps.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table_data.setItem(r, col, it_ps); col += 1

            it_ts = NaturalItem(f"{s.total:.1f}", float(s.total))
            it_ts.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table_data.setItem(r, col, it_ts); col += 1

            for it in items:
                v = s.answers.get(it.number, "")
                _set_item(self.table_data, r, col, v, align_right=True); col += 1

        self.table_data.setSortingEnabled(True)
        self.table_data.sortByColumn(0, Qt.AscendingOrder)
        # 첫 두 컬럼(반/번호, 이름)을 좌측에 틀고정 — 가로 스크롤해도 항상 보임
        if not hasattr(self.table_data, "frozenView") or self.table_data.frozenView is None:
            install_frozen_columns(self.table_data, frozen_count=2)
        else:
            refresh_frozen_columns(self.table_data)
        # setSortingEnabled 직후 자동 정렬 상태가 남는 경우가 있어 최종 배치에서 한 번 더 고정한다.
        self.table_data.sortByColumn(0, Qt.AscendingOrder)
        self._filter_data_table(search_text)

    def _render_overview(self):
        ov = self.overall
        # 누적 막대 안 ABCDE 라벨이 겹치는 문제 → 도넛 차트로 교체
        self.canvas_level_stack.set_figure(charts.fig_level_donut(ov.level_dist_pct, ov.level_dist))
        self.canvas_level_means.set_figure(charts.fig_level_means_with_error(ov.level_mean, ov.level_std))
        # 표
        rows = []
        for lv in LEVELS:
            rows.append([lv, ov.level_dist[lv], f"{ov.level_dist_pct[lv]:.1f}",
                         f"{ov.level_mean[lv]:.1f}", f"{ov.level_std[lv]:.1f}"])
        rows.append(["전체", ov.n_students, "100.0", f"{ov.mean:.1f}", f"{ov.std:.1f}"])
        self.table_level.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, v in enumerate(row):
                bold = (r == len(rows) - 1)
                _set_item(self.table_level, r, c, v, align_right=(c > 0), bold=bold)
        self.table_level.resizeColumnsToContents()
        self.canvas_class.set_figure(charts.fig_class_means(ov.by_class))

    def _perform_record_for_student(self, student):
        if self.perform_data is None:
            return None
        return (
            self.perform_data.records.get(student.sid)
            or self.perform_data.by_classno.get(student.class_no)
        )

    def _perform_matches(self):
        if self.exam is None or self.overall is None or self.perform_data is None:
            return []
        levels_arr = list(getattr(self.overall, "levels_arr", []) or [])
        matches = []
        for idx, student in enumerate(self.exam.students):
            rec = self._perform_record_for_student(student)
            if rec is None:
                continue
            level = levels_arr[idx] if idx < len(levels_arr) else grade_level(student.final_score, self.exam.cut_scores)
            matches.append((idx, student, level, rec))
        return matches

    @staticmethod
    def _mean_std(values: list[float]) -> tuple[float, float]:
        if not values:
            return 0.0, 0.0
        mean = sum(values) / len(values)
        if len(values) <= 1:
            return mean, 0.0
        var = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
        return mean, math.sqrt(max(0.0, var))

    def _perform_area_rows(self):
        if self.perform_data is None:
            return []
        matches = self._perform_matches()
        rows = []
        for area in self.perform_data.areas:
            scores = []
            rates = []
            by_level = {lv: [] for lv in LEVELS}
            for _, _, level, rec in matches:
                score = float(rec.scores.get(area.name, 0.0))
                rate = (score / area.max_score * 100.0) if area.max_score > 0 else 0.0
                scores.append(score)
                rates.append(rate)
                by_level.setdefault(level, []).append(rate)
            mean_score, std_score = self._mean_std(scores)
            mean_rate, std_rate = self._mean_std(rates)
            n = len(rates) or 1
            rows.append({
                "name": area.name,
                "max_score": float(area.max_score),
                "ratio_pct": float(area.ratio_pct),
                "mean_score": mean_score,
                "std_score": std_score,
                "mean_rate": mean_rate,
                "std_rate": std_rate,
                "full_pct": sum(1 for score in scores if score >= area.max_score - 1e-9) / n * 100.0,
                "low_pct": sum(1 for rate in rates if rate < 50.0) / n * 100.0,
                "by_level": {
                    lv: (sum(vals) / len(vals) if vals else None)
                    for lv, vals in by_level.items()
                },
            })
        return rows

    def _perform_corr(self, matches) -> float | None:
        if len(matches) <= 1:
            return None
        x = [float(student.total) for _, student, _, _ in matches]
        y = [float(student.perform_score) for _, student, _, _ in matches]
        mx, sx = self._mean_std(x)
        my, sy = self._mean_std(y)
        if sx <= 0 or sy <= 0:
            return None
        cov = sum((a - mx) * (b - my) for a, b in zip(x, y)) / (len(x) - 1)
        return cov / (sx * sy)

    def _render_perform_tab(self):
        if not hasattr(self, "table_perform_areas"):
            return

        no_data = (
            self.exam is None
            or self.overall is None
            or self.perform_data is None
            or not self.exam.use_perform
        )
        if no_data:
            for card in getattr(self, "perform_cards", {}).values():
                card.value_label.setText("-")
            self.table_perform_areas.setRowCount(0)
            self.table_perform_students.setRowCount(0)
            self.canvas_perform_area.set_figure(charts.fig_perform_area_rates([]))
            self.canvas_perform_scatter.set_figure(charts.fig_perform_scatter([], [], []))
            if hasattr(self, "lbl_perform_tab_note"):
                self.lbl_perform_tab_note.setText(
                    "수행평가 파일을 지정하고 ‘수행평가도 포함하여 분석합니다’를 체크한 뒤 분석을 실행하면 "
                    "영역별 점수율, 지필-수행 관계, 학생별 차이가 표시됩니다."
                )
            self._render_perform_recalc_results()
            return

        matches = self._perform_matches()
        area_rows = self._perform_area_rows()
        corr = self._perform_corr(matches)
        self.perform_cards["ratio"].value_label.setText(f"{self.exam.weight_perform:.0f}%")
        self.perform_cards["areas"].value_label.setText(f"{len(self.perform_data.areas)}개")
        self.perform_cards["matched"].value_label.setText(f"{len(matches)}/{len(self.exam.students)}명")
        self.perform_cards["corr"].value_label.setText("-" if corr is None else f"{corr:.2f}")
        self.lbl_perform_tab_note.setText(
            f"{self.perform_data.subject or self.exam.subject or '(과목 미상)'} · "
            f"수행 원점수 만점 {self.perform_data.max_total:.1f}점 · "
            f"수행 자체 반영비율 합 {self.perform_data.ratio_total:.0f}% · "
            "2/3 기준선은 해당 영역이 목표 성취수준 학생에게 적절히 해결 가능한지 보는 참고선입니다."
        )

        self.canvas_perform_area.set_figure(charts.fig_perform_area_rates(area_rows))
        self.canvas_perform_scatter.set_figure(
            charts.fig_perform_scatter(
                [student.total for _, student, _, _ in matches],
                [student.perform_score for _, student, _, _ in matches],
                [level for _, _, level, _ in matches],
            )
        )

        c = self.theme.colors if self.theme else {}
        shade = QColor(c.get("shade", "#e1e6ee"))
        warn = QColor("#f8dfa3"); warn.setAlpha(120)
        self.table_perform_areas.setSortingEnabled(False)
        self.table_perform_areas.setRowCount(len(area_rows))
        for r, row in enumerate(area_rows):
            _set_item(self.table_perform_areas, r, 0, row["name"], align_left=True, tooltip=row["name"])
            _set_item(self.table_perform_areas, r, 1, f"{row['max_score']:.1f}", align_right=True)
            _set_item(self.table_perform_areas, r, 2, f"{row['ratio_pct']:.0f}%", align_right=True)
            _set_item(self.table_perform_areas, r, 3, f"{row['mean_score']:.2f}", align_right=True)
            _set_item(self.table_perform_areas, r, 4, f"{row['std_score']:.2f}", align_right=True)
            rate_item = NaturalItem(f"{row['mean_rate']:.1f}", row["mean_rate"])
            rate_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            ItemBarDelegate.set_bar(rate_item, row["mean_rate"], 100, "#2563eb", light=True)
            if row["mean_rate"] < 66.7:
                rate_item.setBackground(QBrush(shade))
            self.table_perform_areas.setItem(r, 5, rate_item)
            _set_item(self.table_perform_areas, r, 6, f"{row['full_pct']:.1f}%", align_right=True)
            _set_item(self.table_perform_areas, r, 7, f"{row['low_pct']:.1f}%", align_right=True,
                      bg=warn if row["low_pct"] >= 20 else None)
            for i, lv in enumerate(LEVELS):
                value = row["by_level"].get(lv)
                if value is None:
                    _set_item(self.table_perform_areas, r, 8 + i, "-", align_right=True)
                else:
                    _set_item(self.table_perform_areas, r, 8 + i, f"{value:.1f}", align_right=True,
                              bg=shade if value < 66.7 else None)
        self.table_perform_areas.setSortingEnabled(True)
        for col, width in enumerate([180, 70, 82, 74, 82, 92, 78, 82, 68, 68, 68, 68, 68, 78]):
            self._set_scaled_column_width(self.table_perform_areas, col, width)

        student_rows = []
        for _, student, level, _ in matches:
            diff = float(student.perform_score) - float(student.total)
            if diff >= 10:
                note = "수행 강점"
            elif diff <= -10:
                note = "수행 보완"
            elif abs(diff) >= 5:
                note = "차이 확인"
            else:
                note = "유사"
            student_rows.append((abs(diff), diff, student, level, note))
        student_rows.sort(key=lambda row: (-row[0], _class_no_sort_value(row[2].class_no)))

        self.table_perform_students.setSortingEnabled(False)
        self.table_perform_students.setRowCount(len(student_rows))
        level_order = {"A": 6, "B": 5, "C": 4, "D": 3, "E": 2, "미도달": 1}
        for r, (_, diff, student, level, note) in enumerate(student_rows):
            cls_item = NaturalItem(student.class_no or "", _class_no_sort_value(student.class_no or ""))
            cls_item.setTextAlignment(Qt.AlignCenter)
            self.table_perform_students.setItem(r, 0, cls_item)
            _set_item(self.table_perform_students, r, 1, student.name or "-", align_left=True)
            lv_item = NaturalItem(level, level_order.get(level, 0))
            lv_item.setTextAlignment(Qt.AlignCenter)
            level_color = charts.COLOR_LEVELS.get(level, "#ffffff")
            lv_item.setBackground(QBrush(QColor(level_color)))
            lv_item.setForeground(QBrush(_contrast_text_for_fill(level_color)))
            f = lv_item.font(); f.setBold(True); lv_item.setFont(f)
            self.table_perform_students.setItem(r, 2, lv_item)
            _set_item(self.table_perform_students, r, 3, f"{student.total:.1f}", align_right=True)
            _set_item(self.table_perform_students, r, 4, f"{student.perform_score:.1f}", align_right=True)
            diff_item = NaturalItem(f"{diff:+.1f}", abs(diff))
            diff_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if abs(diff) >= 10:
                diff_item.setBackground(QBrush(warn))
            self.table_perform_students.setItem(r, 5, diff_item)
            _set_item(self.table_perform_students, r, 6, note, tooltip=note)
        self.table_perform_students.setSortingEnabled(True)
        self.table_perform_students.sortByColumn(5, Qt.DescendingOrder)
        for col, width in enumerate([90, 110, 72, 82, 90, 90, 110]):
            self._set_scaled_column_width(self.table_perform_students, col, width)
        self._render_perform_recalc_results()
        self._apply_zoom_to_surfaces()

    def _render_items(self):
        ov = self.overall
        self.lbl_alpha.setText(f"지필평가 신뢰도 (Cronbach's alpha): {ov.cronbach_alpha:.3f} "
                               f"({reliability_label(ov.cronbach_alpha)})")

        self.canvas_pvalue.set_figure(charts.fig_item_difficulty(self.item_stats))
        self.canvas_discr.set_figure(charts.fig_item_discrimination(self.item_stats))

        c = self.theme.colors if self.theme else {}
        col_p_bar = QColor(c.get("p_bar", "#cfe3fa")); col_p_bar.setAlpha(110)
        col_d_bar = QColor(c.get("d_bar", "#cfe9d6")); col_d_bar.setAlpha(110)
        col_highlight = QColor(c.get("highlight", "#fff5a4"))
        col_shade = QColor(c.get("shade", "#e1e6ee"))

        self.table_items.setRowCount(len(self.item_stats))
        self.table_items.setSortingEnabled(False)
        for r, s in enumerate(self.item_stats):
            # 문항번호 — 표시는 '문1', 정렬은 1 (NaturalItem). 기본은 문1→문18 순.
            it_no = NaturalItem(f"문{s.item.number}", int(s.item.number))
            it_no.setTextAlignment(Qt.AlignCenter)
            f = it_no.font(); f.setBold(True); it_no.setFont(f)
            it_no.setToolTip(f"문항 {s.item.number} · {s.item.content_area}")
            self.table_items.setItem(r, 0, it_no)
            _set_item(self.table_items, r, 1, s.item.difficulty or "-")
            # 정답률 — 표시는 '85.4', 정렬은 float + 막대
            it_p = NaturalItem(f"{s.p_value*100:.1f}", float(s.p_value * 100))
            it_p.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            it_p.setToolTip(f"정답률 {s.p_value*100:.2f}%")
            ItemBarDelegate.set_bar(it_p, s.p_value * 100, 100, "#2563eb", light=True)
            self.table_items.setItem(r, 2, it_p)
            # 변별도 — 표시는 '0.602', 정렬은 float + 막대
            it_d = NaturalItem(f"{s.discrimination:.3f}", float(s.discrimination))
            it_d.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            it_d.setToolTip(f"변별도 {s.discrimination:.3f}")
            ItemBarDelegate.set_bar(it_d, max(0.0, s.discrimination) * 100, 100, "#16a34a", light=True)
            self.table_items.setItem(r, 3, it_d)
            for i, ch in enumerate([1, 2, 3, 4, 5, 0]):
                v = s.choice_dist.get(ch, 0) * 100
                col = 4 + i
                bg = col_highlight if str(ch) == str(s.item.answer) else None
                _set_item(self.table_items, r, col, f"{v:.1f}", align_right=True, bg=bg)
            for i, lv in enumerate(LEVELS):
                col = 10 + i
                p = s.p_by_level.get(lv)
                if p is None:
                    _set_item(self.table_items, r, col, "-", align_right=True)
                else:
                    bg = col_shade if p < 2.0 / 3.0 else None
                    _set_item(self.table_items, r, col, f"{p*100:.1f}", align_right=True, bg=bg)
        self.table_items.setSortingEnabled(True)
        self.table_items.sortByColumn(0, Qt.AscendingOrder)  # 기본 정렬: 문1 → 문18
        # 문항번호 컬럼 틀고정
        if not hasattr(self.table_items, "frozenView") or self.table_items.frozenView is None:
            install_frozen_columns(self.table_items, frozen_count=1)
        else:
            refresh_frozen_columns(self.table_items)

        # ─── 서답형 분석 표 채우기 ─────────────────────────────────────
        sd = analyze_serdap(self.exam, ov.levels_arr)
        self.table_serdap.setRowCount(1 if sd.n_items > 0 else 0)
        if sd.n_items > 0:
            row = 0
            _set_item(self.table_serdap, row, 0, f"서답형 전체 ({sd.n_items}문항·{int(sd.max_total)}점)",
                      align_left=True)
            _set_item(self.table_serdap, row, 1, f"{sd.min_v:.1f}", align_right=True)
            _set_item(self.table_serdap, row, 2, f"{sd.max_v:.1f}", align_right=True)
            _set_item(self.table_serdap, row, 3, f"{sd.mean:.2f}", align_right=True)
            _set_item(self.table_serdap, row, 4, f"{sd.std:.2f}", align_right=True)
            # 정답률 + 막대
            it_p = NaturalItem(f"{sd.correct_rate*100:.1f}", float(sd.correct_rate*100))
            it_p.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            it_p.setToolTip(f"서답형 정답률 {sd.correct_rate*100:.2f}%")
            ItemBarDelegate.set_bar(it_p, sd.correct_rate*100, 100, "#2563eb", light=True)
            self.table_serdap.setItem(row, 5, it_p)
            # 변별도 + 막대
            it_d = NaturalItem(f"{sd.discrimination:.3f}", float(sd.discrimination))
            it_d.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            it_d.setToolTip(f"변별도 {sd.discrimination:.3f}")
            ItemBarDelegate.set_bar(it_d, max(0.0, sd.discrimination)*100, 100, "#16a34a", light=True)
            self.table_serdap.setItem(row, 6, it_d)
            # 성취수준별 정답률
            col_shade = QColor(c.get("shade", "#e1e6ee"))
            for i, lv in enumerate(LEVELS):
                p_lv = sd.by_level.get(lv)
                col = 7 + i
                if p_lv is None:
                    _set_item(self.table_serdap, row, col, "-", align_right=True)
                else:
                    pct = p_lv * 100
                    bg = col_shade if pct < 50 else None
                    _set_item(self.table_serdap, row, col, f"{pct:.1f}",
                              align_right=True, bg=bg)
            self.table_serdap.resizeColumnsToContents()

    def _render_choice_combo(self):
        self.combo_item.blockSignals(True)
        self.combo_item.clear()
        for s in self.item_stats:
            self.combo_item.addItem(f"문{s.item.number} – {s.item.content_area}", s)
        self.combo_item.blockSignals(False)
        if self.item_stats:
            self.combo_item.setCurrentIndex(0)

    def _render_choice(self):
        self._refresh_choice()

    def _refresh_choice(self):
        if self.combo_item.count() == 0:
            return
        s = self.combo_item.currentData()
        if s is None:
            return
        self.lbl_choice_info.setText(
            f"<b>문항 {s.item.number}</b> · {s.item.content_area} · "
            f"예상난이도(NEIS): {s.item.difficulty or '-'} · "
            f"배점 {s.item.score} · 정답: <b>{s.item.answer}</b><br>"
            f"전체 정답률 {s.p_value*100:.1f}% · 변별도 {s.discrimination:.3f} "
            f"({s.diff_label} / {s.discr_label})<br>"
            f"성취기준: {s.item.standard_code} {s.item.standard}"
        )
        # 매트릭스 표
        rows = []
        for lv in LEVELS:
            d = s.choice_dist_by_level.get(lv)
            if d is None:
                rows.append([lv, "-", "-", "-", "-", "-", "-", "-"])
                continue
            p = s.p_by_level.get(lv, 0) * 100
            rows.append([lv, f"{p:.1f}",
                         f"{d.get(1,0)*100:.1f}", f"{d.get(2,0)*100:.1f}",
                         f"{d.get(3,0)*100:.1f}", f"{d.get(4,0)*100:.1f}",
                         f"{d.get(5,0)*100:.1f}", f"{d.get(0,0)*100:.1f}"])
        # 전체 행
        d_all = s.choice_dist
        rows.append(["전체", f"{s.p_value*100:.1f}",
                     f"{d_all.get(1,0)*100:.1f}", f"{d_all.get(2,0)*100:.1f}",
                     f"{d_all.get(3,0)*100:.1f}", f"{d_all.get(4,0)*100:.1f}",
                     f"{d_all.get(5,0)*100:.1f}", f"{d_all.get(0,0)*100:.1f}"])
        self.table_choice.setRowCount(len(rows))
        try:
            correct_idx = int(s.item.answer)
        except (TypeError, ValueError):
            correct_idx = -1
        c_theme = self.theme.colors if self.theme else {}
        col_p_bar = QColor(c_theme.get("p_bar", "#cfe3fa")); col_p_bar.setAlpha(110)
        col_highlight = QColor(c_theme.get("highlight", "#fff5a4"))
        for r, row in enumerate(rows):
            bold = (r == len(rows) - 1)
            for cc, v in enumerate(row):
                bg = None
                if cc >= 2 and cc - 2 < 5 and (cc - 1) == correct_idx:
                    bg = col_highlight
                if cc == 1:  # 정답률 컬럼
                    bg = col_p_bar
                _set_item(self.table_choice, r, cc, v, align_right=(cc > 0), bold=bold, bg=bg)
        self.table_choice.resizeColumnsToContents()
        self.canvas_choice.set_figure(
            charts.fig_choice_dist_by_level(s, title=f"문항 {s.item.number} 답지반응분포 – 정답: {s.item.answer}")
        )

    def _render_standard(self):
        rows = self.overall.by_standard
        c = self.theme.colors if self.theme else {}
        col_shade = QColor(c.get("shade", "#e1e6ee"))
        self.table_std.setSortingEnabled(False)
        self.table_std.setRowCount(len(rows))
        for r, row in enumerate(rows):
            _set_item(self.table_std, r, 0, row["key"], align_left=True, tooltip=row["key"])
            it_n = NaturalItem(str(row["n_items"]), int(row["n_items"]))
            it_n.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table_std.setItem(r, 1, it_n)
            p = row["mean_p"] * 100
            it_p = NaturalItem(f"{p:.1f}", float(p))
            it_p.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            it_p.setToolTip(f"성취율(전체) {p:.2f}%")
            ItemBarDelegate.set_bar(it_p, p, 100, "#2563eb", light=True)
            self.table_std.setItem(r, 2, it_p)
            for i, lv in enumerate(LEVELS):
                p_lv = row["by_level"].get(lv)
                col = 3 + i
                if p_lv is None:
                    _set_item(self.table_std, r, col, "-", align_right=True)
                else:
                    p_pct = p_lv * 100
                    bg = col_shade if p_pct < 50 else None
                    _set_item(self.table_std, r, col, f"{p_pct:.1f}", align_right=True, bg=bg)
        self.table_std.setSortingEnabled(True)
        self.table_std.sortByColumn(2, Qt.DescendingOrder)
        hh = self.table_std.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        for i in range(1, self.table_std.columnCount()):
            hh.setSectionResizeMode(i, QHeaderView.Fixed)
            self._set_scaled_column_width(self.table_std, i, 72)
        self.table_std.verticalHeader().setDefaultSectionSize(self._px(30))
        self.canvas_std.setMinimumHeight(max(340, min(1400, 30 * len(rows) + 70)))
        self.canvas_std.set_figure(charts.fig_standard_attainment(rows))

    # ---------------------------------------------------------- 내보내기
    def _build_spliter_evidence_payload(self):
        select_items = sorted(self.exam.select_items, key=lambda it: it.number)
        serdap_items = sorted(self.exam.serdap_items, key=lambda it: it.number)
        serdap_max_total = sum(float(it.score) for it in serdap_items)
        serdap_stats = analyze_serdap(self.exam, levels_arr=getattr(self.overall, "levels_arr", None)) if serdap_items else None
        serdap_evidence_number = max([it.number for it in self.exam.items] or [0]) + 10000
        serdap_difficulties = {it.difficulty for it in serdap_items if it.difficulty}
        serdap_difficulty = next(iter(serdap_difficulties)) if len(serdap_difficulties) == 1 else ""
        stats_by_number = {s.item.number: s for s in self.item_stats}
        levels_arr = list(getattr(self.overall, "levels_arr", []) or [])

        source_files = dict(getattr(self.exam, "source_files", {}) or {})
        if self.fs_cuts.path():
            source_files["cuts"] = self.fs_cuts.path()

        def item_payload(it):
            stats = stats_by_number.get(it.number)
            return {
                "number": it.number,
                "type": it.item_type,
                "difficulty": it.difficulty,
                "score": round(float(it.score), 2),
                "answer": it.answer,
                "contentArea": it.content_area,
                "standardCode": it.standard_code,
                "standard": it.standard,
                "pValue": round(stats.p_value * 100, 2) if stats else None,
                "discrimination": round(stats.discrimination, 3) if stats else None,
                "pByLevel": {
                    lv: round(stats.p_by_level.get(lv, 0) * 100, 2)
                    for lv in LEVELS
                    if stats and lv in stats.p_by_level
                },
            }

        def serdap_payload():
            if not serdap_items or serdap_max_total <= 0:
                return None
            return {
                "number": serdap_evidence_number,
                "type": "서답형",
                "difficulty": serdap_difficulty,
                "score": round(float(serdap_max_total), 2),
                "answer": "부분점수",
                "contentArea": "서답형 전체",
                "standardCode": "",
                "standard": "서답형 전체 점수율",
                "pValue": round(serdap_stats.correct_rate * 100, 2) if serdap_stats else None,
                "discrimination": round(serdap_stats.discrimination, 3) if serdap_stats else None,
                "pByLevel": {
                    lv: round(serdap_stats.by_level.get(lv, 0) * 100, 2)
                    for lv in LEVELS
                    if serdap_stats and lv in serdap_stats.by_level
                },
                "isAggregate": True,
            }

        evidence_items = [item_payload(it) for it in select_items]
        serdap_evidence_item = serdap_payload()
        if serdap_evidence_item:
            evidence_items.append(serdap_evidence_item)

        students = []
        for idx, st in enumerate(self.exam.students):
            level = levels_arr[idx] if idx < len(levels_arr) else grade_level(st.final_score, self.exam.cut_scores)
            item_results = []
            for it in select_items:
                choice = str(st.answers.get(it.number, "")).strip()
                is_correct = choice == "."
                item_results.append({
                    "number": it.number,
                    "correct": is_correct,
                    "scoreRate": 100.0 if is_correct else 0.0,
                    "choice": choice,
                    "answer": it.answer,
                    "type": it.item_type,
                    "difficulty": it.difficulty,
                    "score": round(float(it.score), 2),
                    "contentArea": it.content_area,
                    "standardCode": it.standard_code,
                    "standard": it.standard,
                })
            if serdap_evidence_item and serdap_max_total > 0:
                serdap_rate = max(0.0, min(1.0, float(st.serdap_score) / serdap_max_total))
                item_results.append({
                    "number": serdap_evidence_number,
                    "correct": serdap_rate >= 0.5,
                    "scoreRate": round(serdap_rate * 100, 2),
                    "choice": f"{round(float(st.serdap_score), 2)}/{round(float(serdap_max_total), 2)}",
                    "answer": "부분점수",
                    "type": "서답형",
                    "difficulty": serdap_difficulty,
                    "score": round(float(serdap_max_total), 2),
                    "contentArea": "서답형 전체",
                    "standardCode": "",
                    "standard": "서답형 전체 점수율",
                    "isAggregate": True,
                })
            students.append({
                "id": st.sid,
                "classNo": st.class_no,
                "gradeClass": st.grade_class,
                "name": st.name,
                "level": level,
                "finalScore": round(float(st.final_score), 2),
                "total": round(float(st.total), 2),
                "pencilScore": round(float(st.total), 2),
                "performScore": round(float(st.perform_score), 2),
                "itemResults": item_results,
            })

        payload = {
            "kind": "goedusplit-spliter-evidence",
            "version": 1,
            "exportedAt": datetime.now().isoformat(timespec="seconds"),
            "subject": self.exam.subject,
            "grade": self.exam.grade,
            "semester": self.exam.semester,
            "cuts": {lv: round(float(self.exam.cut_scores.get(lv, 0)), 2) for lv in ["A", "B", "C", "D", "E"]},
            "weights": {
                "pencil": round(float(self.exam.weight_pencil), 2),
                "perform": round(float(self.exam.weight_perform), 2),
            },
            "sourceFiles": source_files,
            "levelSummary": {lv: int(self.overall.level_dist.get(lv, 0)) for lv in LEVELS},
            "items": evidence_items,
            "students": students,
        }
        return payload

    @staticmethod
    def _excel_cell_value(value):
        if value is None:
            return ""
        if isinstance(value, (str, int, float, bool)):
            return value
        return json.dumps(value, ensure_ascii=False)

    def _write_spliter_evidence_xlsx(self, path: str, payload: dict):
        import openpyxl
        from openpyxl.styles import Alignment, Font, PatternFill

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "요약"
        header_fill = PatternFill("solid", fgColor="DDEDEA")
        title_font = Font(bold=True)

        def append(ws_, row):
            ws_.append([self._excel_cell_value(value) for value in row])

        append(ws, ["항목", "값"])
        append(ws, ["내보낸 시각", payload.get("exportedAt", "")])
        append(ws, ["과목", payload.get("subject", "")])
        append(ws, ["학년", payload.get("grade", "")])
        append(ws, ["학기", payload.get("semester", "")])
        append(ws, ["학생 수", len(payload.get("students", []))])
        append(ws, ["근거 문항 수", len(payload.get("items", []))])
        append(ws, ["지필 반영비율", payload.get("weights", {}).get("pencil", "")])
        append(ws, ["수행 반영비율", payload.get("weights", {}).get("perform", "")])
        for lv, label in [("A", "A/B"), ("B", "B/C"), ("C", "C/D"), ("D", "D/E"), ("E", "E/미도달")]:
            append(ws, [f"{label} 분할점수", payload.get("cuts", {}).get(lv, "")])
        ws.freeze_panes = "A2"

        ws_levels = wb.create_sheet("성취수준 요약")
        append(ws_levels, ["성취수준", "인원"])
        for lv in LEVELS:
            append(ws_levels, [lv, payload.get("levelSummary", {}).get(lv, 0)])
        ws_levels.freeze_panes = "A2"

        ws_items = wb.create_sheet("문항 근거")
        item_headers = [
            "문항", "유형", "난이도", "배점", "정답", "내용영역", "성취기준 코드", "성취기준",
            "전체 정답률(%)", "변별도", "A(%)", "B(%)", "C(%)", "D(%)", "E(%)", "미도달(%)", "서답형 집계",
        ]
        append(ws_items, item_headers)
        for item in payload.get("items", []):
            p_by_level = item.get("pByLevel") or {}
            append(ws_items, [
                item.get("number", ""),
                item.get("type", ""),
                item.get("difficulty", ""),
                item.get("score", ""),
                item.get("answer", ""),
                item.get("contentArea", ""),
                item.get("standardCode", ""),
                item.get("standard", ""),
                item.get("pValue", ""),
                item.get("discrimination", ""),
                p_by_level.get("A", ""),
                p_by_level.get("B", ""),
                p_by_level.get("C", ""),
                p_by_level.get("D", ""),
                p_by_level.get("E", ""),
                p_by_level.get("미도달", ""),
                "예" if item.get("isAggregate") else "",
            ])
        ws_items.freeze_panes = "A2"

        ws_students = wb.create_sheet("학생")
        student_headers = ["학생ID", "반/번호", "학년반", "이름", "성취도", "환산점수", "지필점수", "수행점수"]
        append(ws_students, student_headers)
        for st in payload.get("students", []):
            append(ws_students, [
                st.get("id", ""),
                st.get("classNo", ""),
                st.get("gradeClass", ""),
                st.get("name", ""),
                st.get("level", ""),
                st.get("finalScore", ""),
                st.get("pencilScore", ""),
                st.get("performScore", ""),
            ])
        ws_students.freeze_panes = "A2"

        ws_responses = wb.create_sheet("학생 응답")
        response_headers = [
            "학생ID", "반/번호", "이름", "성취도", "문항", "정오", "점수율(%)", "응답", "정답",
            "유형", "난이도", "배점", "성취기준 코드", "성취기준", "서답형 집계",
        ]
        append(ws_responses, response_headers)
        for st in payload.get("students", []):
            for result in st.get("itemResults", []):
                append(ws_responses, [
                    st.get("id", ""),
                    st.get("classNo", ""),
                    st.get("name", ""),
                    st.get("level", ""),
                    result.get("number", ""),
                    "정답" if result.get("correct") else "오답",
                    result.get("scoreRate", ""),
                    result.get("choice", ""),
                    result.get("answer", ""),
                    result.get("type", ""),
                    result.get("difficulty", ""),
                    result.get("score", ""),
                    result.get("standardCode", ""),
                    result.get("standard", ""),
                    "예" if result.get("isAggregate") else "",
                ])
        ws_responses.freeze_panes = "A2"

        ws_meta = wb.create_sheet("_앱내부데이터")
        append(ws_meta, ["이 시트는 앱 내부 복원용 원본 데이터입니다. 일반 사용자는 요약/문항/학생 시트를 보시면 됩니다."])
        append(ws_meta, [json.dumps(payload, ensure_ascii=False, indent=2)])
        ws_meta.sheet_state = "hidden"

        for sheet in wb.worksheets:
            for cell in sheet[1]:
                cell.font = title_font
                cell.fill = header_fill
                cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            for row in sheet.iter_rows(min_row=2):
                for cell in row:
                    cell.alignment = Alignment(vertical="top", wrap_text=True)
            for col in sheet.columns:
                letter = col[0].column_letter
                max_len = max(len(str(cell.value or "")) for cell in col[:80])
                sheet.column_dimensions[letter].width = min(max(max_len + 2, 10), 42)
        ws_items.column_dimensions["H"].width = 60
        ws_responses.column_dimensions["N"].width = 60
        wb.save(path)

    def export_spliter_evidence(self):
        if self.exam is None or self.overall is None:
            QMessageBox.warning(self, "예상정답률 계산기", "먼저 분석을 실행해 주세요.")
            return

        safe_subject = "".join(
            "_" if ch in "\\/:*?\"<>|" else ch for ch in (self.exam.subject or "goedusplit")
        ).strip() or "goedusplit"
        default_name = f"{safe_subject}_expected_rate_근거.xlsx"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "예상정답률 근거 엑셀 저장",
            str(Path.home() / "Desktop" / default_name),
            "Excel 통합문서 (*.xlsx)",
        )
        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"

        payload = self._build_spliter_evidence_payload()
        students = payload["students"]
        evidence_items = payload["items"]
        select_count = len(self.exam.select_items)
        serdap_count = len(self.exam.serdap_items)
        serdap_text = f" · 서답형 {serdap_count}문항은 전체 점수율로 반영" if serdap_count else ""

        try:
            self._write_spliter_evidence_xlsx(path, payload)
        except Exception as e:
            QMessageBox.critical(self, "예상정답률 계산기", f"근거 엑셀 저장 중 오류가 발생했습니다.\n{e}")
            return

        self.statusBar().showMessage(f"예상정답률 근거 엑셀 저장 완료 · {path}", 8000)
        QMessageBox.information(
            self,
            "예상정답률 계산기",
            f"근거 엑셀을 저장했습니다.\n학생 {len(students)}명 · 근거 문항 {len(evidence_items)}개"
            f" (선택형 {select_count}개{serdap_text})\n\n{path}",
        )

    def export_csv(self):
        if self.exam is None:
            QMessageBox.warning(self, "내보내기", "먼저 분석을 실행해 주세요.")
            return
        directory = QFileDialog.getExistingDirectory(self, "CSV 저장 폴더 선택")
        if not directory:
            return

        # 그래프 PNG도 함께 저장할지 물어보기 (체크박스 있는 다이얼로그)
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Question)
        msg.setWindowTitle("내보내기 옵션")
        msg.setText("결과 CSV 4개를 저장합니다.\n그래프(.png)도 함께 저장하시겠습니까?")
        msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
        msg.setDefaultButton(QMessageBox.Yes)
        msg.button(QMessageBox.Yes).setText("CSV + 그래프 PNG")
        msg.button(QMessageBox.No).setText("CSV만")
        msg.button(QMessageBox.Cancel).setText("취소")
        ans = msg.exec()
        if ans == QMessageBox.Cancel:
            return
        with_graphs = (ans == QMessageBox.Yes)

        out = Path(directory)
        ov = self.overall
        try:
            self._write_csv(out / "학생결과.csv",
                ["학번","반/번호","이름","학급","선택형","서답형","기타","지필총점","수행환산","환산점수","성취도"],
                [[s.sid, s.class_no, s.name, s.grade_class, s.multi_score, s.serdap_score,
                  s.etc_score, round(s.total,2), round(s.perform_score,2),
                  round(s.final_score,2), ov.levels_arr[i]]
                 for i, s in enumerate(self.exam.students)])
            self._write_csv(out / "문항분석.csv",
                ["문항","예상난이도","정답률(%)","변별도",
                 "응답1(%)","응답2(%)","응답3(%)","응답4(%)","응답5(%)","무응답(%)",
                 "A(%)","B(%)","C(%)","D(%)","E(%)","미도달(%)",
                 "내용영역","성취기준코드","성취기준"],
                [[s.item.number, s.item.difficulty,
                  round(s.p_value*100,2), round(s.discrimination,3),
                  *[round(s.choice_dist.get(c,0)*100,2) for c in (1,2,3,4,5,0)],
                  *[round(s.p_by_level.get(lv,0)*100,2) if lv in s.p_by_level else "" for lv in LEVELS],
                  s.item.content_area, s.item.standard_code, s.item.standard]
                 for s in self.item_stats])
            self._write_csv(out / "성취기준별.csv",
                ["성취기준","문항수","성취율(전체,%)","A(%)","B(%)","C(%)","D(%)","E(%)","미도달(%)"],
                [[r["key"], r["n_items"], round(r["mean_p"]*100,2)] +
                 [round(r["by_level"].get(lv,0)*100,2) if r["by_level"].get(lv) is not None else "" for lv in LEVELS]
                 for r in ov.by_standard])
            self._write_csv(out / "성취수준분포.csv",
                ["성취도","인원","비율(%)","평균","표준편차"],
                [[lv, ov.level_dist[lv], round(ov.level_dist_pct[lv],2),
                  round(ov.level_mean[lv],2), round(ov.level_std[lv],2)] for lv in LEVELS])

            saved_pngs = []
            if with_graphs:
                graph_dir = out / "그래프"
                graph_dir.mkdir(exist_ok=True)
                # 도넛
                f = charts.fig_level_donut(ov.level_dist_pct, ov.level_dist)
                f.savefig(graph_dir / "01_성취수준_도넛.png", dpi=150, bbox_inches="tight")
                saved_pngs.append("01_성취수준_도넛.png")
                # 환산점수 히스토그램
                f = charts.fig_score_histogram_colored(
                    [s.final_score for s in self.exam.students], ov.levels_arr)
                f.savefig(graph_dir / "02_환산점수_분포.png", dpi=150, bbox_inches="tight")
                saved_pngs.append("02_환산점수_분포.png")
                # 평균±표준편차
                f = charts.fig_level_means_with_error(ov.level_mean, ov.level_std)
                f.savefig(graph_dir / "03_성취수준별_평균.png", dpi=150, bbox_inches="tight")
                saved_pngs.append("03_성취수준별_평균.png")
                # 학급별 평균
                f = charts.fig_class_means(ov.by_class)
                f.savefig(graph_dir / "04_학급별_평균.png", dpi=150, bbox_inches="tight")
                saved_pngs.append("04_학급별_평균.png")
                # 문항별 정답률/변별도
                f = charts.fig_item_difficulty(self.item_stats)
                f.savefig(graph_dir / "05_문항_정답률.png", dpi=150, bbox_inches="tight")
                saved_pngs.append("05_문항_정답률.png")
                f = charts.fig_item_discrimination(self.item_stats)
                f.savefig(graph_dir / "06_문항_변별도.png", dpi=150, bbox_inches="tight")
                saved_pngs.append("06_문항_변별도.png")
                # 성취기준
                f = charts.fig_standard_attainment(ov.by_standard)
                f.savefig(graph_dir / "07_성취기준별_정답률.png", dpi=150, bbox_inches="tight")
                saved_pngs.append("07_성취기준별_정답률.png")

            extra = f"\n그래프 {len(saved_pngs)}장 → 그래프/ 폴더" if saved_pngs else ""
            QMessageBox.information(self, "완료",
                                    f"CSV 4개{extra}\n저장 위치: {out}")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"{e}")

    @staticmethod
    def _write_csv(path: Path, headers, rows):
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(headers)
            w.writerows(rows)


def run():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    app.setOrganizationName(APP_AUTHOR)
    icon_path = _app_icon_path()
    if icon_path is not None:
        app.setWindowIcon(QIcon(str(icon_path)))
    # 테마 매니저 초기화 (자동 모드)
    tm = ThemeManager(app)
    tm.set_mode("auto")
    win = MainWindow(theme_manager=tm)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run()
