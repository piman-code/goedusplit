"""모니터링 탭: 현재 과목의 A 비율·평균·A/B 분할점수를 전국 기준과 전년도 값에 비교한다.

판정 계산(`z_status`, `monitor_rows_and_benchmarks`)은 Qt 없이 쓸 수 있는 순수 함수이고,
나머지는 화면이다. 위젯은 기존처럼 window 속성(`monitor_spins`, `table_monitor` 등)에 둔다.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QFormLayout, QFrame, QGridLayout, QHBoxLayout,
                               QLabel, QMessageBox, QPushButton, QScrollArea, QSplitter,
                               QTableWidget, QVBoxLayout, QWidget)

from . import lazy_charts as charts
from . import rounds as round_history
from .widgets import StepperSpinBox


def build_monitor_tab(window):
    from .main_window import CanvasHolder, _setup_table
    layout = QVBoxLayout(window.tab_monitor)
    head_row = QHBoxLayout()
    intro = QLabel(
        "현재 과목의 A 비율, 과목 평균, A/B 분할점수를 "
        "동일 학교유형·교과군의 전국 평균±표준편차 및 전년도 값과 비교합니다. "
        "위쪽 카드(현재 값)는 분석 결과에서 자동으로 들어옵니다. 아래 칸은 직접 넣는 값입니다: "
        "전국 기준은 교육청 등에서 받은 성취평가 모니터링 자료에 있을 때만, 전년도 값은 작년 같은 과목 결과로 넣으세요. "
        "모르는 칸은 '미입력'으로 두면 되고, 그 항목은 판정 대신 '기준 입력 필요'로 표시됩니다."
    )
    intro.setProperty("role", "muted")
    intro.setWordWrap(True)
    head_row.addWidget(intro, 1)
    btn_prev_year = QPushButton("전년도 기록으로 채우기")
    btn_prev_year.setToolTip("같은 과목·학기·차수의 전년도 분석 기록이 있으면 아래 전년도 값을 자동으로 넣습니다.")
    btn_prev_year.clicked.connect(window._fill_monitor_prev_year)
    head_row.addWidget(btn_prev_year)
    btn_refresh = QPushButton("새로고침")
    btn_refresh.clicked.connect(window._refresh_monitoring_tab)
    head_row.addWidget(btn_refresh)
    layout.addLayout(head_row)

    top_area = QWidget()
    top_layout = QVBoxLayout(top_area)
    top_layout.setContentsMargins(0, 0, 0, 0)
    top_layout.setSpacing(8)
    current_grid = QGridLayout(); current_grid.setSpacing(8)
    window.monitor_current_cards = {
        "a_pct": window._kpi_card("현재 A 비율", "-"),
        "mean": window._kpi_card("현재 과목 평균", "-"),
        "std": window._kpi_card("현재 표준편차", "-"),
        "cut_a": window._kpi_card("현재 A/B 분할점수", "-"),
    }
    for i, card in enumerate(window.monitor_current_cards.values()):
        current_grid.addWidget(card, 0, i)
    top_layout.addLayout(current_grid)

    window.monitor_spins: dict[str, StepperSpinBox] = {}
    input_row = QSplitter(Qt.Horizontal)
    national_body = QWidget()
    national_form = QFormLayout(national_body); national_form.setLabelAlignment(Qt.AlignRight)
    window._add_monitor_spin(national_form, "ref_a_mean", "A 비율 평균", 0.0, suffix=" %", tip="같은 학교유형·교과군 학교들의 A 비율 평균(모니터링 자료)")
    window._add_monitor_spin(national_form, "ref_a_sd", "A 비율 표준편차", 0.0, suffix=" %p", tip="같은 자료의 A 비율 표준편차. 평균과 함께 있어야 Ⅰ/Ⅱ/Ⅲ 수준을 판정합니다")
    window._add_monitor_spin(national_form, "ref_mean_mean", "과목 평균", 0.0, suffix=" 점")
    window._add_monitor_spin(national_form, "ref_mean_sd", "과목 평균 표준편차", 0.0, suffix=" 점")
    window._add_monitor_spin(national_form, "ref_cut_mean", "A/B 분할점수 평균", 0.0, suffix=" 점")
    window._add_monitor_spin(national_form, "ref_cut_sd", "A/B 분할점수 표준편차", 0.0, suffix=" 점")
    national_box = window._make_collapsible_panel("동일 학교유형·교과군 전국 기준", national_body)
    input_row.addWidget(national_box)

    history_body = QWidget()
    history_form = QFormLayout(history_body); history_form.setLabelAlignment(Qt.AlignRight)
    window._add_monitor_spin(history_form, "prev_a_pct", "전년도 A 비율", 0.0, suffix=" %", tip="작년 같은 과목·같은 학기의 A 비율")
    window._add_monitor_spin(history_form, "prev_mean", "전년도 과목 평균", 0.0, suffix=" 점", tip="작년 같은 과목·같은 학기의 과목 평균")
    window._add_monitor_spin(history_form, "prev_cut_a", "전년도 A/B 분할점수", 0.0, suffix=" 점", tip="작년 같은 과목·같은 학기의 A/B 분할점수")
    window._add_monitor_spin(history_form, "th_a_delta", "A 비율 증가 기준", 10.0, suffix=" %p")
    window._add_monitor_spin(history_form, "th_mean_stable", "평균 큰 변동 아님", 5.0, suffix=" 점")
    window._add_monitor_spin(history_form, "th_cut_delta", "분할점수 감소 기준", 10.0, suffix=" 점")
    history_box = window._make_collapsible_panel("전년도·판정 기준", history_body)
    input_row.addWidget(history_box)
    input_row.setStretchFactor(0, 1); input_row.setStretchFactor(1, 1)
    # Twelve input rows are taller than their share of the tab and squeezed the chart below to
    # a line; let them scroll instead.
    input_scroll = QScrollArea()
    input_scroll.setWidgetResizable(True)
    input_scroll.setFrameShape(QFrame.NoFrame)
    input_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    input_scroll.setWidget(input_row)
    # The page scrolls now, so keep about three input rows readable instead of one cut-off row.
    input_scroll.setMinimumHeight(window._px(220))
    top_layout.addWidget(input_scroll, 1)

    body = QSplitter(Qt.Vertical)
    window.canvas_monitor = CanvasHolder()
    window.canvas_monitor.setMinimumHeight(window._px(170))
    body.addWidget(window._fold("monitor.chart", "기준 비교 그래프", window.canvas_monitor))
    window.canvas_monitor_trend = CanvasHolder()
    window.canvas_monitor_trend.setMinimumHeight(window._px(150))
    body.addWidget(window._fold("monitor.trend", "회차별 추이 (분석할 때마다 자동으로 쌓임)", window.canvas_monitor_trend))

    flow_note = QLabel(
        "점검 흐름: 1단계 A 비율 변화 확인 → 2단계 대상교·학생 특성 확인 → "
        "3단계 정기시험 특성 확인 → 4단계 분할점수 재산출 → 5단계 A 비율 재산정"
    )
    flow_note.setProperty("role", "muted")
    flow_note.setWordWrap(True)

    table_wrap = QWidget()
    table_layout = QVBoxLayout(table_wrap); table_layout.setContentsMargins(0, 0, 0, 0)
    note_row = QHBoxLayout()
    note_row.addWidget(flow_note, 1)
    btn_copy = QPushButton("표 복사")
    btn_copy.setToolTip("점검 표를 엑셀·한글에 붙여 넣을 수 있게 복사합니다. 학생 정보는 들어 있지 않습니다.")
    btn_copy.clicked.connect(lambda: copy_monitor_table(window))
    note_row.addWidget(btn_copy)
    table_layout.addLayout(note_row)
    window.table_monitor = QTableWidget(0, 5)
    window.table_monitor.setHorizontalHeaderLabels(["지표", "현재/변화", "기준", "판정", "해석·질문"])
    _setup_table(window.table_monitor, word_wrap=True, horizontal_scroll=True, row_height=42)
    window.table_monitor.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
    # Spread the columns over the table width (table_controls) until the teacher sizes one.
    window.table_monitor.setProperty("fillColumns", True)
    # All six check rows (42 px each) plus header and scrollbar, so no verdict is hidden below.
    window.table_monitor.setMinimumHeight(window._px(6 * 42 + 70))
    table_layout.addWidget(window.table_monitor, 1)
    body.addWidget(window._fold("monitor.table", "점검 표", table_wrap))
    body.setStretchFactor(0, 1); body.setStretchFactor(1, 1); body.setStretchFactor(2, 2)
    body.setSizes([240, 220, 360])
    monitor_split = QSplitter(Qt.Vertical)
    monitor_split.addWidget(window._fold("monitor.inputs", "현재 값과 비교 기준 입력", top_area))
    monitor_split.addWidget(body)
    monitor_split.setStretchFactor(0, 0)
    monitor_split.setStretchFactor(1, 1)
    monitor_split.setSizes([250, 620])
    # A laptop-height tab is shorter than the areas' minimums together; a splitter then hands out
    # less than each minimum and the chart, trend and table are painted over each other and under
    # the handles. Scroll the page instead so every area keeps its minimum height.
    page = QScrollArea()
    page.setWidgetResizable(True)
    page.setFrameShape(QFrame.NoFrame)
    page.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    page.setWidget(monitor_split)
    layout.addWidget(page, 1)
    window._render_monitor_tab()


def refresh_monitoring_tab(window):
    window._render_monitor_tab()
    window.statusBar().showMessage("모니터링 탭을 새로고침했습니다.", 2500)


def fill_monitor_prev_year(window):
    if window.exam is None or window.overall is None:
        QMessageBox.information(window, "전년도 기록", "먼저 분석을 실행해 주세요.")
        return
    year, semester, round_no = window._detect_exam_round()
    previous = round_history.previous_year(
        window._round_store().load_all(), window.exam.subject or "(과목 미상)", window.exam.grade, year, semester, round_no)
    if previous is None:
        QMessageBox.information(
            window, "전년도 기록",
            f"저장된 {round_history.round_label((year - 1) if year else None, semester, round_no)} 분석 기록이 없습니다.\n"
            "작년 같은 시험을 이 앱으로 분석한 적이 있어야 자동으로 채울 수 있습니다. "
            "없으면 아래 칸에 직접 입력하세요.")
        return
    for key, value in (("prev_a_pct", previous["level_pct"].get("A", 0.0)), ("prev_mean", previous["mean"]),
                       ("prev_cut_a", previous["cuts"].get("A", 0.0))):
        window.monitor_spins[key].setValue(float(value))
    window.statusBar().showMessage(f"전년도 값을 {previous['label']} 기록으로 채웠습니다.", 5000)


def add_monitor_spin(window, form: QFormLayout, key: str, label: str, value: float,
                     *, suffix: str = "", tip: str = ""):
    spin = StepperSpinBox(value=value, minimum=-100.0, maximum=200.0,
                          step=1.0, decimals=1, suffix=suffix)
    if key.startswith(("ref_", "prev_")):
        # 0 already means "not entered" in the checks below; show it as such instead of "0.0 %".
        spin.spin.setMinimum(0.0)
        spin.spin.setSpecialValueText("미입력")
    if tip:
        spin.setToolTip(tip)
    spin.valueChanged.connect(lambda *_: window._render_monitor_tab())
    window.monitor_spins[key] = spin
    form.addRow(label, spin)
    return spin


def monitor_value(window, key: str) -> float:
    spin = getattr(window, "monitor_spins", {}).get(key)
    return float(spin.value()) if spin is not None else 0.0


def z_status(value: float, ref: float, sd: float, *, low_is_risk: bool = False):
    """전국 평균·표준편차 기준 판정: (판정, 설명, 심각도 0~3)."""
    if sd <= 0 or ref <= 0:  # 0 is shown as '미입력': a missing mean must not be compared as 0
        return "기준 입력 필요", "전국 평균과 표준편차를 입력하면 Ⅰ/Ⅱ/Ⅲ 수준을 자동 판정합니다.", 0
    z = (ref - value) / sd if low_is_risk else (value - ref) / sd
    if z >= 2:
        return "Ⅲ 점검", f"전국 평균에서 {'아래로' if low_is_risk else '위로'} 표준편차의 {z:.2f}배 벗어났습니다.", 3
    if z >= 1:
        return "Ⅱ 주의", f"전국 평균에서 {'아래로' if low_is_risk else '위로'} 표준편차의 {z:.2f}배 벗어났습니다.", 2
    return "참고 범위", f"전국 평균±1SD(표준편차) 안쪽 또는 위험 방향이 아닙니다. z={z:.2f}", 1


def rows_and_benchmarks(window):
    if window.exam is None or window.overall is None:
        return [], []
    return monitor_rows_and_benchmarks(
        float(window.overall.level_dist_pct.get("A", 0.0)), float(window.overall.mean),
        float(window.exam.cut_scores.get("A", 0.0)), window._monitor_value)


def monitor_rows_and_benchmarks(a_pct: float, mean: float, cut_a: float, value):
    """점검 표 행과 기준 비교 그래프 자료. value(key)는 입력칸 값이며 0은 '미입력'이다."""
    prev_a = value("prev_a_pct")
    prev_mean = value("prev_mean")
    prev_cut = value("prev_cut_a")
    th_a = value("th_a_delta")
    th_mean = value("th_mean_stable")
    th_cut = value("th_cut_delta")

    rows = []
    status, detail, sev = z_status(
        a_pct, value("ref_a_mean"), value("ref_a_sd")
    )
    rows.append((
        "필수 1 · 성취수준 A 비율이 높음",
        f"{a_pct:.1f}%",
        "전국 평균+1SD 이상: Ⅱ · +2SD 이상: Ⅲ",
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

    status, detail, sev = z_status(
        mean, value("ref_mean_mean"), value("ref_mean_sd")
    )
    rows.append((
        "특성 3 · 과목 평균이 높음",
        f"{mean:.1f}점",
        "전국 평균+1SD 이상: 주의 · +2SD 이상: 점검",
        status,
        f"{detail} 평가도구가 쉬웠는지, 학생 특성이 높은지 함께 봅니다.",
        sev,
    ))

    status, detail, sev = z_status(
        cut_a, value("ref_cut_mean"), value("ref_cut_sd"),
        low_is_risk=True,
    )
    rows.append((
        "특성 4 · A/B 분할점수가 낮음",
        f"{cut_a:.1f}점",
        "전국 평균-1SD 이하: 주의 · -2SD 이하: 점검",
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
            "ref": value("ref_a_mean") if value("ref_a_mean") > 0 and value("ref_a_sd") > 0 else None,
            "sd": value("ref_a_sd") if value("ref_a_mean") > 0 and value("ref_a_sd") > 0 else None,
            "color": "#ef4444",
        },
        {
            "label": "과목 평균",
            "value": mean,
            "ref": value("ref_mean_mean") if value("ref_mean_mean") > 0 and value("ref_mean_sd") > 0 else None,
            "sd": value("ref_mean_sd") if value("ref_mean_mean") > 0 and value("ref_mean_sd") > 0 else None,
            "color": "#f59e0b",
        },
        {
            "label": "A/B 분할점수",
            "value": cut_a,
            "ref": value("ref_cut_mean") if value("ref_cut_mean") > 0 and value("ref_cut_sd") > 0 else None,
            "sd": value("ref_cut_sd") if value("ref_cut_mean") > 0 and value("ref_cut_sd") > 0 else None,
            "color": "#2a7770",
        },
    ]
    return rows, benchmarks


def monitor_table_text(table) -> str:
    """Tab-separated header and rows, as Excel and Hangul paste a table."""
    def clean(text):
        return " ".join(str(text).split())
    lines = ["\t".join(clean(table.horizontalHeaderItem(c).text()) for c in range(table.columnCount()))]
    for r in range(table.rowCount()):
        lines.append("\t".join(clean(table.item(r, c).text() if table.item(r, c) else "")
                               for c in range(table.columnCount())))
    return "\n".join(lines)


def copy_monitor_table(window):
    if window.table_monitor.rowCount() == 0:
        window.statusBar().showMessage("분석을 실행하면 점검 표를 복사할 수 있습니다.", 4000)
        return
    QApplication.clipboard().setText(monitor_table_text(window.table_monitor))
    window.statusBar().showMessage(
        f"점검 표 {window.table_monitor.rowCount()}줄을 복사했습니다. 엑셀이나 한글에 붙여 넣으세요.", 4000)


def render_monitor_tab(window):
    from .main_window import _set_item
    if not hasattr(window, "table_monitor"):
        return
    if window.exam is None or window.overall is None:
        for card in getattr(window, "monitor_current_cards", {}).values():
            card.value_label.setText("-")
        window.table_monitor.setRowCount(0)
        if hasattr(window, "canvas_monitor"):
            window.canvas_monitor.set_placeholder("분석자료를 불러오면 기준 비교 그래프를 표시합니다.")
        if hasattr(window, "canvas_monitor_trend"):
            window.canvas_monitor_trend.set_placeholder("분석한 회차의 추이를 표시합니다.")
        return

    a_pct = float(window.overall.level_dist_pct.get("A", 0.0))
    window.monitor_current_cards["a_pct"].value_label.setText(f"{a_pct:.1f}%")
    window.monitor_current_cards["mean"].value_label.setText(f"{window.overall.mean:.1f}점")
    window.monitor_current_cards["std"].value_label.setText(f"{window.overall.std:.1f}점")
    window.monitor_current_cards["cut_a"].value_label.setText(f"{window.exam.cut_scores.get('A', 0):.1f}점")

    rows, benchmarks = window._monitor_rows_and_benchmarks()
    window.canvas_monitor.set_figure(charts.fig_monitoring_benchmarks(benchmarks))
    if hasattr(window, "canvas_monitor_trend"):
        try:
            course = window._course_round_records()
        except Exception:
            course = []
        window.canvas_monitor_trend.set_figure(charts.fig_round_trend(round_history.trend(course) if course else None))

    window.table_monitor.setSortingEnabled(False)
    window.table_monitor.setRowCount(len(rows))
    colors = window.theme.colors if window.theme else {}
    shade = QColor(colors.get("shade", "#e1e6ee"))
    warn = QColor("#f8dfa3"); warn.setAlpha(150)
    danger = QColor("#f5b5b5"); danger.setAlpha(165)
    ok = QColor(colors.get("card", "#f4f7f8"))
    for r, row in enumerate(rows):
        bg = danger if row[5] >= 3 else warn if row[5] == 2 else shade if row[5] == 0 else ok
        for c, value in enumerate(row[:5]):
            _set_item(
                window.table_monitor,
                r,
                c,
                value,
                align_left=(c in (0, 4)),
                bg=bg if c == 3 else None,
                bold=(c == 3),
                tooltip=str(value),
            )
    window.table_monitor.setSortingEnabled(False)
    for col, width in enumerate([250, 180, 260, 120, 520]):
        window._set_scaled_column_width(window.table_monitor, col, width)
    window._apply_zoom_to_surfaces()
