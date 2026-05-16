"""
PySide6 기반 메인 윈도우 (KICE Shiny 웹앱 2.1.2 화면 구조에 맞춰 재구성).

화면 구조:
- 좌측 사이드바: 입력 파일, 분할점수, 옵션, 분석 실행
- 우측 탭: Data | 전체 성취도 | 문항 분석 | 답지반응분포 | 성취기준 분석 | 도움말

데이터는 모두 로컬에서만 처리되며, 외부로 전송되지 않는다.
"""
from __future__ import annotations

import csv
import json
import math
import re
import sys
import traceback
from datetime import datetime
from pathlib import Path

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
    AIProviderConfig, default_endpoint, default_model, parse_review_rows,
    run_completion, scrub_personal_data,
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
AI_REVIEW_HEADERS = ["구분", "번호/요소", "성취기준 후보", "평가유형", "목표수준 후보", "난이도 후보", "근거", "다음 확인"]


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

        spliter_btn = QPushButton("예상정답률 근거 JSON 내보내기…")
        spliter_btn.setToolTip("분석된 학생 성취수준과 선택형 문항 정오 데이터를 예상정답률 계산기 추천 근거로 저장합니다.")
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
        btn_export = QPushButton("예상정답률 근거 JSON 내보내기…")
        btn_export.clicked.connect(self.export_spliter_evidence)
        toolbar_layout.addWidget(btn_export)
        btn_reload = QPushButton("새로고침")
        btn_reload.clicked.connect(self._load_spliter_web)
        toolbar_layout.addWidget(btn_reload)
        layout.addWidget(self.spliter_toolbar, 0)

        if QWebEngineView is None:
            self.lbl_spliter_web = QLabel(
                "이 Python 환경에는 Qt WebEngine이 없어 내장 계산기를 표시할 수 없습니다. "
                "근거 JSON을 내보내 예상정답률 계산기에서 불러와 주세요."
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
        self.lbl_ai_review_note = QLabel(
            "문항지·수행평가 채점기준표·문항정보표를 불러오거나 텍스트를 붙여 넣으면 "
            "성취기준, 평가유형, 목표 성취수준, 난이도 후보를 검토 초안으로 정리합니다. "
            "현재 단계는 로컬 초안 생성이며, AI 최종 판정이 아니라 교사 검토 보조입니다."
        )
        self.lbl_ai_review_note.setProperty("role", "muted")
        self.lbl_ai_review_note.setWordWrap(True)
        head.addWidget(self.lbl_ai_review_note, 1)
        btn_load = QPushButton("파일 불러오기")
        btn_load.clicked.connect(self._load_ai_review_file)
        head.addWidget(btn_load)
        btn_exam = QPushButton("현재 문항정보표")
        btn_exam.clicked.connect(self._load_ai_review_from_exam)
        head.addWidget(btn_exam)
        btn_generate = QPushButton("검토 초안 생성")
        btn_generate.setProperty("role", "primary")
        btn_generate.clicked.connect(self._generate_ai_review_draft)
        head.addWidget(btn_generate)
        btn_ai_enrich = QPushButton("AI로 보강")
        btn_ai_enrich.setToolTip("AI 설정에 지정한 로컬/클라우드 모델로 검토 초안을 보강합니다.")
        btn_ai_enrich.clicked.connect(self._run_ai_review_completion)
        head.addWidget(btn_ai_enrich)
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
        left_title = QLabel("원문 / 붙여넣기")
        left_title.setProperty("role", "title")
        left_layout.addWidget(left_title)
        self.txt_ai_review_source = QPlainTextEdit()
        self.txt_ai_review_source.setPlaceholderText(
            "문항지, 수행평가 채점기준표, 성취기준별 성취수준, 문항정보표 내용을 붙여 넣거나 파일을 불러오세요."
        )
        left_layout.addWidget(self.txt_ai_review_source, 1)
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
        self.ai_review_tabs.addTab(self._build_ai_settings_panel(), "AI 설정")
        right_layout.addWidget(self.ai_review_tabs, 1)
        split.addWidget(right)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 2)
        split.setSizes([420, 780])
        layout.addWidget(split, 1)
        self._set_ai_review_summary(0, 0, 0)

    def _build_ai_settings_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel); layout.setContentsMargins(10, 10, 10, 10); layout.setSpacing(10)

        note = QLabel(
            "기본은 외부 전송이 없는 로컬 초안입니다. Ollama, MLX-LM 서버, LM Studio, OpenAI 호환 API는 "
            "선생님이 AI로 보강을 누를 때만 호출됩니다."
        )
        note.setProperty("role", "muted")
        note.setWordWrap(True)
        layout.addWidget(note)

        form_card = QFrame()
        form_card.setProperty("role", "card")
        form = QFormLayout(form_card)
        form.setContentsMargins(14, 12, 14, 12)
        form.setSpacing(8)

        self.cmb_ai_provider = QComboBox()
        self.cmb_ai_provider.addItem("로컬 초안만 사용", "local_draft")
        self.cmb_ai_provider.addItem("Ollama 로컬", "ollama")
        self.cmb_ai_provider.addItem("OpenAI 호환 API / MLX 서버", "openai_compatible")
        self.cmb_ai_provider.currentIndexChanged.connect(self._sync_ai_provider_defaults)
        form.addRow("AI 제공자", self.cmb_ai_provider)

        self.edit_ai_endpoint = QLineEdit()
        self.edit_ai_endpoint.setPlaceholderText("예: http://127.0.0.1:11434/api/chat")
        form.addRow("엔드포인트", self.edit_ai_endpoint)

        self.edit_ai_model = QLineEdit()
        self.edit_ai_model.setPlaceholderText("예: qwen2.5:7b, mlx-community 모델, gpt-4.1-mini")
        form.addRow("모델", self.edit_ai_model)

        self.edit_ai_api_key = QLineEdit()
        self.edit_ai_api_key.setEchoMode(QLineEdit.Password)
        self.edit_ai_api_key.setPlaceholderText("클라우드 또는 인증이 필요한 로컬 서버에서만 입력")
        form.addRow("API 키", self.edit_ai_api_key)

        self.spin_ai_timeout = QDoubleSpinBox()
        self.spin_ai_timeout.setRange(5, 180)
        self.spin_ai_timeout.setDecimals(0)
        self.spin_ai_timeout.setSingleStep(5)
        self.spin_ai_timeout.setSuffix(" 초")
        form.addRow("대기 시간", self.spin_ai_timeout)

        self.chk_ai_scrub = QCheckBox("클라우드/외부 서버로 보낼 때 학생 이름·반번호를 가능한 한 제거")
        form.addRow("개인정보", self.chk_ai_scrub)

        layout.addWidget(form_card)

        row = QHBoxLayout()
        btn_save = QPushButton("설정 저장")
        btn_save.setProperty("role", "primary")
        btn_save.clicked.connect(self._save_ai_settings)
        row.addWidget(btn_save)
        btn_test = QPushButton("연결 테스트")
        btn_test.clicked.connect(self._test_ai_connection)
        row.addWidget(btn_test)
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

    def _load_ai_settings(self):
        if not hasattr(self, "cmb_ai_provider"):
            return
        provider = str(self.settings.value("ai/provider", "local_draft"))
        idx = self.cmb_ai_provider.findData(provider)
        self.cmb_ai_provider.setCurrentIndex(idx if idx >= 0 else 0)
        self.edit_ai_endpoint.setText(str(self.settings.value("ai/endpoint", default_endpoint(provider))))
        self.edit_ai_model.setText(str(self.settings.value("ai/model", default_model(provider))))
        self.edit_ai_api_key.setText(str(self.settings.value("ai/api_key", "")))
        try:
            self.spin_ai_timeout.setValue(float(self.settings.value("ai/timeout", 60)))
        except Exception:
            self.spin_ai_timeout.setValue(60)
        scrub = self.settings.value("ai/scrub_personal_data", True)
        self.chk_ai_scrub.setChecked(str(scrub).lower() not in {"false", "0", "no"})

    def _save_ai_settings(self):
        if not hasattr(self, "cmb_ai_provider"):
            return
        self.settings.setValue("ai/provider", self._provider_from_combo())
        self.settings.setValue("ai/endpoint", self.edit_ai_endpoint.text().strip())
        self.settings.setValue("ai/model", self.edit_ai_model.text().strip())
        self.settings.setValue("ai/api_key", self.edit_ai_api_key.text().strip())
        self.settings.setValue("ai/timeout", int(self.spin_ai_timeout.value()))
        self.settings.setValue("ai/scrub_personal_data", self.chk_ai_scrub.isChecked())
        self.settings.sync()
        self.lbl_ai_settings_status.setText("AI 설정을 저장했습니다.")
        self.statusBar().showMessage("AI 설정 저장 완료", 3000)

    def _sync_ai_provider_defaults(self, *_args):
        provider = self._provider_from_combo()
        known_endpoints = {default_endpoint("ollama"), default_endpoint("openai_compatible"), ""}
        known_models = {default_model("ollama"), default_model("openai_compatible"), ""}
        if self.edit_ai_endpoint.text().strip() in known_endpoints:
            self.edit_ai_endpoint.setText(default_endpoint(provider))
        if self.edit_ai_model.text().strip() in known_models:
            self.edit_ai_model.setText(default_model(provider))
        if provider == "local_draft":
            self.lbl_ai_settings_status.setText("로컬 초안은 외부 AI를 호출하지 않습니다.")
        elif provider == "ollama":
            self.lbl_ai_settings_status.setText("Ollama가 실행 중이어야 합니다. 기본 주소는 http://127.0.0.1:11434/api/chat 입니다.")
        else:
            self.lbl_ai_settings_status.setText("MLX-LM/LM Studio/OpenAI 호환 서버의 chat completions 엔드포인트를 입력하세요.")

    def _ai_provider_config(self) -> AIProviderConfig:
        if not hasattr(self, "cmb_ai_provider"):
            return AIProviderConfig()
        provider = self._provider_from_combo()
        return AIProviderConfig(
            provider=provider,
            endpoint=self.edit_ai_endpoint.text().strip() or default_endpoint(provider),
            model=self.edit_ai_model.text().strip() or default_model(provider),
            api_key=self.edit_ai_api_key.text().strip(),
            timeout=int(self.spin_ai_timeout.value()),
        )

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
        prompt = (
            "연결 테스트입니다. JSON 배열만 반환하세요.\n"
            "[{\"구분\":\"테스트\",\"번호/요소\":\"1\",\"성취기준 후보\":\"-\","
            "\"평가유형\":\"선택형\",\"목표수준 후보\":\"C\",\"난이도 후보\":\"보통\","
            "\"근거\":\"연결 확인\",\"다음 확인\":\"없음\"}]"
        )
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            output = run_completion(prompt, config)
            parsed = parse_review_rows(output)
        except Exception as exc:
            QMessageBox.warning(self, "AI 연결 테스트", f"연결하지 못했습니다.\n{exc}")
            self.lbl_ai_settings_status.setText(f"연결 실패: {exc}")
            return
        finally:
            QApplication.restoreOverrideCursor()
        if parsed:
            self.lbl_ai_settings_status.setText(f"{config.label} 연결 확인 완료.")
            QMessageBox.information(self, "AI 연결 테스트", f"{config.label} 응답을 정상적으로 읽었습니다.")
        else:
            self.lbl_ai_settings_status.setText("응답은 받았지만 표 형식으로 해석하지 못했습니다.")
            QMessageBox.information(self, "AI 연결 테스트", "응답은 받았지만 표 형식으로 해석하지 못했습니다. 모델 출력 형식을 확인해 주세요.")

    def _extract_text_from_review_file(self, path: str) -> str:
        p = Path(path)
        suffix = p.suffix.lower()
        if suffix in {".txt", ".md", ".csv", ".json"}:
            return p.read_text(encoding="utf-8", errors="replace")
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
        if suffix == ".pdf":
            try:
                import pypdf
            except Exception as exc:
                raise ValueError("PDF 텍스트 추출을 위해 pypdf가 필요합니다. requirements.txt를 반영해 설치 후 다시 시도하세요.") from exc
            reader = pypdf.PdfReader(str(p))
            pages = []
            for i, page in enumerate(reader.pages[:80], start=1):
                text = page.extract_text() or ""
                if text.strip():
                    pages.append(f"## PDF {i}쪽\n{text}")
            return "\n".join(pages)
        raise ValueError("지원 형식: .txt, .md, .csv, .json, .xlsx, .xlsm, .pdf")

    def _load_ai_review_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "문항지 또는 채점기준표 불러오기",
            "",
            "검토 자료 (*.txt *.md *.csv *.json *.xlsx *.xlsm *.pdf);;모든 파일 (*.*)",
        )
        if not path:
            return
        try:
            text = self._extract_text_from_review_file(path)
        except Exception as e:
            QMessageBox.warning(self, "AI 문항 검토", f"파일을 읽지 못했습니다.\n{e}")
            return
        self.txt_ai_review_source.setPlainText(text[:60000])
        self.statusBar().showMessage(f"AI 문항 검토 자료 불러오기 완료 · {Path(path).name}", 4000)

    def _load_ai_review_from_exam(self):
        if self.exam is None:
            QMessageBox.warning(self, "AI 문항 검토", "먼저 문항정보표를 불러와 분석을 실행해 주세요.")
            return
        lines = [
            f"과목: {self.exam.subject or '(과목 미상)'}",
            f"학기/학년: {self.exam.semester} {self.exam.grade}",
            "",
        ]
        type_order = {"선택형": 0, "서답형": 1}
        for item in sorted(self.exam.items, key=lambda it: (it.number, type_order.get(it.item_type, 9))):
            standard = " ".join(part for part in [item.standard_code, item.standard] if part).strip()
            lines.append(
                f"문항 {item.number} | 유형 {item.item_type} | 난이도 {item.difficulty or '-'} | "
                f"배점 {item.score:g} | 내용영역 {item.content_area or '-'} | 성취기준 {standard or '-'}"
            )
        self.txt_ai_review_source.setPlainText("\n".join(lines))
        self.statusBar().showMessage("현재 문항정보표를 AI 문항 검토 원문으로 가져왔습니다.", 3500)

    def _split_ai_review_blocks(self, text: str) -> list[dict]:
        lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
        lines = [line for line in lines if line]
        blocks = []
        current = None
        item_re = re.compile(r"^(?:문항\s*)?(\d{1,3})\s*(?:번|[.)]|[|])?\s*(.*)$")
        for line in lines:
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
                    current = {"kind": "문항", "label": label, "text": line}
            elif any(key in line for key in ("평가요소", "채점기준", "수행 수준", "수행수준")):
                if current:
                    blocks.append(current)
                current = {"kind": "수행평가", "label": line[:32], "text": line}
            elif current:
                current["text"] += "\n" + line
            elif re.search(r"\[[^\]\n]{4,40}\]", line):
                blocks.append({"kind": "성취기준", "label": "성취기준", "text": line})
        if current:
            blocks.append(current)
        if not blocks and text.strip():
            blocks.append({"kind": "전체 자료", "label": "전체", "text": text.strip()[:4000]})
        return blocks[:120]

    def _infer_ai_review_row(self, block: dict) -> dict:
        text = block["text"]
        compact = re.sub(r"\s+", " ", text)
        codes = re.findall(r"\[[^\]\n]{4,40}\]", compact)
        standard = codes[0] if codes else ""
        if standard:
            pos = compact.find(standard)
            standard = compact[pos:pos + 130].strip()

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

        if "어려" in compact or re.search(r"\b상\b", compact):
            difficulty = "어려움"
        elif "쉬움" in compact or re.search(r"\b하\b", compact):
            difficulty = "쉬움"
        elif "보통" in compact or re.search(r"\b중\b", compact):
            difficulty = "보통"
        elif score >= 4:
            difficulty = "어려움"
        elif score <= 0:
            difficulty = "쉬움"
        else:
            difficulty = "보통"

        if explicit_level:
            target = explicit_level
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

        if any(term in compact for term in ("수행평가", "평가요소", "채점기준", "수행 수준", "수행수준")):
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
        evidence = " · ".join(evidence_terms) if evidence_terms else compact[:90]
        warnings = []
        if not codes:
            warnings.append("성취기준 코드 확인")
        if block["kind"] == "전체 자료":
            warnings.append("문항/평가요소 분리 확인")
        if review_type == "지필 문항" and "배점" not in compact:
            warnings.append("배점 확인")
        next_step = " / ".join(warnings) if warnings else "성취기준 진술과 문항 요구 행동을 비교"
        return {
            "kind": block["kind"],
            "label": block["label"],
            "standard": standard or "(후보 없음)",
            "review_type": review_type,
            "target": target,
            "difficulty": difficulty,
            "evidence": evidence,
            "next_step": next_step,
        }

    def _make_ai_review_prompt(self, rows: list[dict], source_text: str) -> str:
        preview = source_text.strip()
        if len(preview) > 12000:
            preview = preview[:12000] + "\n...(이하 생략)"
        row_lines = "\n".join(
            f"- {row['label']}: 유형={row['review_type']}, 목표={row['target']}, 난이도={row['difficulty']}, 성취기준={row['standard']}"
            for row in rows[:60]
        )
        return (
            "너는 고등학교 성취평가 현장지원단의 문항 검토 보조자다.\n"
            "아래 자료를 바탕으로 각 문항 또는 수행평가 평가요소의 성취기준, 목표 성취수준 후보, 난이도 후보를 제안하라.\n"
            "중요 원칙: 자동 확정하지 말고, 교사가 검토할 수 있도록 근거 문장을 함께 제시한다.\n"
            "A 수준 문항은 A 수준 최소능력자 3명 중 약 2명이 해결할 수 있는 문항이라는 기준으로 판단한다.\n"
            "수행평가는 평가요소별로 A~E 최소능력자의 예상점수를 산출할 수 있도록 채점기준표의 행동 표현을 분석한다.\n\n"
            "출력 형식은 표로 한다: 번호/요소 | 성취기준 후보 | 평가유형 | 목표수준 후보 | 난이도 후보 | 근거 | 추가 확인 질문.\n\n"
            "[로컬 초안]\n"
            f"{row_lines}\n\n"
            "[원문]\n"
            f"{preview}"
        )

    def _make_structured_ai_review_prompt(self, rows: list[dict], source_text: str) -> str:
        preview = source_text.strip()
        if len(preview) > 18000:
            preview = preview[:18000] + "\n...(이하 생략)"
        draft = "\n".join(
            f"- {row.get('label') or row.get('번호/요소')}: 유형={row.get('review_type') or row.get('평가유형')}, "
            f"목표={row.get('target') or row.get('목표수준 후보')}, 난이도={row.get('difficulty') or row.get('난이도 후보')}, "
            f"성취기준={row.get('standard') or row.get('성취기준 후보')}"
            for row in rows[:80]
        )
        return (
            "너는 고등학교 성취평가 현장지원단의 문항 검토 보조자다.\n"
            "아래 원문과 로컬 초안을 바탕으로 문항/수행평가 평가요소를 다시 검토하라.\n"
            "AI 판정은 최종 확정이 아니라 교사가 검토할 초안이다.\n"
            "A 수준 문항은 A 수준 최소능력자 3명 중 약 2명이 해결할 수 있다는 기준으로 본다.\n"
            "수행평가는 평가요소별로 A~E 최소능력자의 예상점수 산정에 도움이 되도록 근거를 쓴다.\n\n"
            "반드시 JSON 배열만 출력하라. 설명 문장, 마크다운, 코드블록을 붙이지 마라.\n"
            "각 객체의 키는 반드시 다음 8개만 사용한다:\n"
            '["구분","번호/요소","성취기준 후보","평가유형","목표수준 후보","난이도 후보","근거","다음 확인"]\n'
            "평가유형은 선택형, 서답형, 수행평가 중 하나를 우선 사용한다.\n"
            "목표수준 후보는 A/B/C/D/E 중 하나를 사용한다.\n"
            "난이도 후보는 쉬움/보통/어려움 중 하나를 사용한다.\n\n"
            "[로컬 초안]\n"
            f"{draft}\n\n"
            "[원문]\n"
            f"{preview}"
        )

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
                row.get("evidence") or row.get("근거") or "",
                next_step,
            ]
            for c, value in enumerate(values):
                bg = None
                if c == 7 and ("확인" in value or "점검" in value):
                    bg = QColor("#f8dfa3"); bg.setAlpha(140)
                _set_item(table, r, c, value, align_left=c in (1, 2, 6, 7), bg=bg, tooltip=value)
        table.setSortingEnabled(False)
        for col, width in enumerate([86, 120, 260, 92, 100, 100, 260, 240]):
            self._set_scaled_column_width(table, col, width)
        self._set_ai_review_summary(len(rows), len(standards), warnings, mode)

    def _generate_ai_review_draft(self):
        if not hasattr(self, "txt_ai_review_source"):
            return
        text = self.txt_ai_review_source.toPlainText().strip()
        if not text:
            QMessageBox.information(self, "AI 문항 검토", "먼저 원문을 붙여 넣거나 파일을 불러와 주세요.")
            return
        blocks = self._split_ai_review_blocks(text)
        rows = [self._infer_ai_review_row(block) for block in blocks]
        self._populate_ai_review_table(rows, mode="로컬 초안")
        self.txt_ai_review_prompt.setPlainText(self._make_ai_review_prompt(rows, text))
        self.statusBar().showMessage(f"AI 문항 검토 초안 생성 완료 · {len(rows)}개 항목", 3500)

    def _run_ai_review_completion(self):
        if not hasattr(self, "txt_ai_review_source"):
            return
        text = self.txt_ai_review_source.toPlainText().strip()
        if not text:
            QMessageBox.information(self, "AI 문항 검토", "먼저 원문을 붙여 넣거나 파일을 불러와 주세요.")
            return
        config = self._ai_provider_config()
        self._save_ai_settings()
        blocks = self._split_ai_review_blocks(text)
        local_rows = [self._infer_ai_review_row(block) for block in blocks]
        if config.provider == "local_draft":
            self._populate_ai_review_table(local_rows, mode="로컬 초안")
            self.txt_ai_review_prompt.setPlainText(self._make_ai_review_prompt(local_rows, text))
            self.statusBar().showMessage("로컬 초안으로 검토표를 갱신했습니다.", 3500)
            return

        prompt = self._make_structured_ai_review_prompt(local_rows, text)
        if hasattr(self, "chk_ai_scrub") and self.chk_ai_scrub.isChecked():
            prompt_to_send = scrub_personal_data(prompt, self._student_names_for_privacy())
        else:
            prompt_to_send = prompt
        self.txt_ai_review_prompt.setPlainText(prompt_to_send)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            output = run_completion(prompt_to_send, config)
            ai_rows = parse_review_rows(output)
        except Exception as exc:
            QMessageBox.warning(self, "AI 문항 검토", f"AI 보강 중 오류가 발생했습니다.\n{exc}")
            self.statusBar().showMessage("AI 보강 실패", 5000)
            return
        finally:
            QApplication.restoreOverrideCursor()

        if not ai_rows:
            self.txt_ai_review_prompt.setPlainText(
                prompt_to_send + "\n\n[AI 원문 출력]\n" + (output or "(빈 응답)")[:20000]
            )
            QMessageBox.information(
                self,
                "AI 문항 검토",
                "AI 응답은 받았지만 검토표로 해석하지 못했습니다.\nAI 프롬프트 탭의 원문 출력을 확인해 주세요.",
            )
            return
        self._populate_ai_review_table(ai_rows, mode=f"{config.label} 보강")
        self.txt_ai_review_prompt.setPlainText(
            prompt_to_send + "\n\n[AI 원문 출력]\n" + (output or "")[:20000]
        )
        self.ai_review_tabs.setCurrentWidget(self.table_ai_review)
        self.statusBar().showMessage(f"AI 보강 완료 · {len(ai_rows)}개 항목", 5000)

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
            items.append({
                "id": f"ai-review-{idx}-{number}",
                "number": number,
                "title": row.get("번호/요소", "") or f"{number}번",
                "standard": "" if standard == "(후보 없음)" else standard,
                "points": self._ai_review_points_for_item(number, item_type, 5.0),
                "sampleSize": 3,
                "type": item_type,
                "difficulty": difficulty,
                "targetLevel": target,
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
            self._add_perform_recalc_row({
                "name": name,
                "max_score": max_score,
                "memo": "AI 검토 초안 · " + " · ".join(
                    part for part in [row.get("목표수준 후보", ""), row.get("난이도 후보", ""), row.get("근거", "")]
                    if part
                ),
            })
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
        <p>지필평가는 문항별 예상정답률을 합산해 분할점수를 만들고, 수행평가는 평가요소별 예상점수를 합산해 분할점수를 만듭니다.
        두 기능은 모두 “최소능력자가 어느 정도 수행할 수 있는가”를 숫자로 옮기는 같은 구조입니다.</p>

        <h2>AI 문항 검토 방향</h2>
        <p><b>AI 문항 검토</b> 탭은 문항지, 문항정보표, 수행평가 채점기준표를 읽어 검토 초안을 만드는 작업 공간입니다.</p>
        <ul>
          <li><b>파일 불러오기</b>: txt, csv, xlsx, pdf 자료를 원문으로 불러옵니다. PDF는 텍스트 추출 가능한 파일이어야 합니다.</li>
          <li><b>현재 문항정보표</b>: 이미 분석한 문항정보표를 검토 원문으로 가져옵니다.</li>
          <li><b>검토 초안 생성</b>: 성취기준 후보, 평가유형, 목표수준 후보, 난이도 후보, 근거, 추가 확인 질문을 표로 정리합니다.</li>
          <li><b>AI로 보강</b>: AI 설정에 지정한 로컬/클라우드 모델로 검토표를 다시 제안받습니다. 기본값은 외부 전송이 없는 로컬 초안입니다.</li>
          <li><b>AI 설정</b>: Ollama 로컬, MLX-LM/LM Studio 같은 OpenAI 호환 로컬 서버, 클라우드 API의 엔드포인트와 모델을 저장합니다.</li>
          <li><b>개인정보 제거</b>: 외부 서버로 보낼 때 학생 이름, 반/번호, 전화번호, 이메일을 가능한 한 제거합니다. 그래도 최종 전송 여부는 교사가 확인합니다.</li>
          <li><b>지필→예상정답률</b>: 선택형·서답형 문항 초안을 예상정답률 계산기로 보내 문항별 O/X 판단을 이어갑니다.</li>
          <li><b>수행→재산정</b>: 수행평가 평가요소 초안을 수행평가 분할점수 재산정 표로 보내 예상점수 합산을 이어갑니다.</li>
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
        a_spliter = QAction("예상정답률 근거 JSON 내보내기…", self)
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

    def export_spliter_evidence(self):
        if self.exam is None or self.overall is None:
            QMessageBox.warning(self, "예상정답률 계산기", "먼저 분석을 실행해 주세요.")
            return

        safe_subject = "".join(
            "_" if ch in "\\/:*?\"<>|" else ch for ch in (self.exam.subject or "goedusplit")
        ).strip() or "goedusplit"
        default_name = f"{safe_subject}_expected_rate_근거.json"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "예상정답률 근거 JSON 저장",
            str(Path.home() / "Desktop" / default_name),
            "JSON (*.json)",
        )
        if not path:
            return

        payload = self._build_spliter_evidence_payload()
        students = payload["students"]
        evidence_items = payload["items"]
        select_count = len(self.exam.select_items)
        serdap_count = len(self.exam.serdap_items)
        serdap_text = f" · 서답형 {serdap_count}문항은 전체 점수율로 반영" if serdap_count else ""

        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception as e:
            QMessageBox.critical(self, "예상정답률 계산기", f"근거 JSON 저장 중 오류가 발생했습니다.\n{e}")
            return

        self.statusBar().showMessage(f"예상정답률 근거 JSON 저장 완료 · {path}", 8000)
        QMessageBox.information(
            self,
            "예상정답률 계산기",
            f"근거 JSON을 저장했습니다.\n학생 {len(students)}명 · 근거 문항 {len(evidence_items)}개"
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
