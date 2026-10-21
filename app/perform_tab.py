"""수행평가 분석 탭: 영역별 요약·학생별 차이·분할점수 재산정 화면.

재산정 계산(`recommend_area_scores`, `recalc_summary`)은 Qt 없이 쓸 수 있는 순수 함수이고,
나머지는 화면이다. 위젯은 기존처럼 window 속성(`table_perform_recalc` 등)에 둔다.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QPushButton, QScrollArea, QSplitter, QTabWidget, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from .analysis import LEVELS_AE
from .widgets import ItemBarDelegate

# 자료가 없을 때 A~E 최소능력자 예상점수 = 만점 × 이 비율
PERFORM_DEFAULT_RATES = {"A": 0.90, "B": 0.80, "C": 0.70, "D": 0.60, "E": 0.40}


def build_perform_tab(window):
    from .main_window import CanvasHolder, _setup_table
    layout = QVBoxLayout(window.tab_perform)

    head_row = QHBoxLayout()
    window.lbl_perform_tab_note = QLabel(
        "수행평가 영역별 점수율, 정기시험 총점과의 관계, 학생별 차이를 함께 봅니다. "
        "왼쪽 입력 패널에서 수행평가 파일을 지정하고 체크한 뒤 분석을 실행하세요."
    )
    window.lbl_perform_tab_note.setProperty("role", "muted")
    window.lbl_perform_tab_note.setWordWrap(True)
    head_row.addWidget(window.lbl_perform_tab_note, 1)
    btn_refresh = QPushButton("새로고침")
    btn_refresh.clicked.connect(window._refresh_perform_tab)
    head_row.addWidget(btn_refresh)
    layout.addLayout(head_row)

    grid = QGridLayout(); grid.setSpacing(8)
    window.perform_cards = {
        "ratio": window._kpi_card("수행 반영비율", "-"),
        "areas": window._kpi_card("수행 영역", "-"),
        "matched": window._kpi_card("매칭 학생", "-"),
        "corr": window._kpi_card("정기시험-수행 상관", "-"),
    }
    for i, card in enumerate(window.perform_cards.values()):
        grid.addWidget(card, 0, i)
    perform_cards_box = QWidget()
    perform_cards_box.setLayout(grid)
    # Summary, graphs and tables are taller together than a laptop-height tab; a splitter then
    # gives the graph and table areas less than their minimum and the handle is painted over the
    # graph. Scroll them as one page instead, as in the monitoring tab.
    page_body = QWidget()
    page_layout = QVBoxLayout(page_body); page_layout.setContentsMargins(0, 0, 0, 0)
    page_layout.addWidget(window._fold("perform.summary", "요약", perform_cards_box))

    split = QSplitter(Qt.Vertical)

    chart_row = QWidget()
    chart_layout = QHBoxLayout(chart_row); chart_layout.setContentsMargins(0, 0, 0, 0)
    window.canvas_perform_area = CanvasHolder()
    window.canvas_perform_scatter = CanvasHolder()
    chart_layout.addWidget(window.canvas_perform_area, 1)
    chart_layout.addWidget(window.canvas_perform_scatter, 1)
    split.addWidget(window._fold("perform.charts", "영역별·정기시험-수행 그래프", chart_row))

    table_tabs = QTabWidget()
    window.perform_table_tabs = table_tabs
    window.table_perform_areas = QTableWidget(0, 14)
    window.table_perform_areas.setHorizontalHeaderLabels([
        "영역", "만점", "반영비율", "평균", "표준편차", "평균점수율",
        "만점자", "50% 미만", "A", "B", "C", "D", "E", "미도달",
    ])
    _setup_table(window.table_perform_areas, word_wrap=False, horizontal_scroll=True, row_height=30)
    window.table_perform_areas.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
    window._perform_area_bar_delegate = ItemBarDelegate(window.table_perform_areas)
    window.table_perform_areas.setItemDelegateForColumn(5, window._perform_area_bar_delegate)
    table_tabs.addTab(window.table_perform_areas, "영역별 요약")

    window.table_perform_students = QTableWidget(0, 7)
    window.table_perform_students.setHorizontalHeaderLabels([
        "반/번호", "이름", "성취도", "정기시험 총점", "수행환산", "수행-정기시험", "해석",
    ])
    _setup_table(window.table_perform_students, word_wrap=False, horizontal_scroll=True, row_height=30)
    window.table_perform_students.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
    table_tabs.addTab(window.table_perform_students, "학생별 차이")

    recalc_page = QWidget()
    recalc_layout = QVBoxLayout(recalc_page)
    recalc_layout.setContentsMargins(8, 8, 8, 8)
    recalc_layout.setSpacing(8)

    recalc_head = QHBoxLayout()
    window.lbl_perform_recalc_note = QLabel(
        "평가요소별로 A~E 최소능력자가 받을 것으로 예상되는 점수를 넣으면 "
        "수행평가 분할점수가 자동 계산됩니다."
    )
    window.lbl_perform_recalc_note.setProperty("role", "muted")
    window.lbl_perform_recalc_note.setWordWrap(True)
    recalc_head.addWidget(window.lbl_perform_recalc_note, 1)
    btn_perf_recommend = QPushButton("자료 기준 딸깍 추천")
    btn_perf_recommend.clicked.connect(window._recommend_perform_recalc_rows)
    recalc_head.addWidget(btn_perf_recommend)
    btn_perf_default = QPushButton("기본안")
    btn_perf_default.clicked.connect(window._reset_perform_recalc_rows)
    recalc_head.addWidget(btn_perf_default)
    btn_perf_add = QPushButton("평가요소 추가")
    btn_perf_add.clicked.connect(window._add_perform_recalc_row)
    recalc_head.addWidget(btn_perf_add)
    btn_perf_del = QPushButton("선택 삭제")
    btn_perf_del.clicked.connect(window._delete_selected_perform_recalc_rows)
    recalc_head.addWidget(btn_perf_del)
    recalc_layout.addLayout(recalc_head)

    cut_grid = QGridLayout(); cut_grid.setSpacing(8)
    window.perform_recalc_cards = {
        "max": window._kpi_card("수행 만점", "-"),
        "A": window._kpi_card("A/B", "-"),
        "B": window._kpi_card("B/C", "-"),
        "C": window._kpi_card("C/D", "-"),
        "D": window._kpi_card("D/E", "-"),
        "E": window._kpi_card("E/미도달", "-"),
        "check": window._kpi_card("점검", "-"),
    }
    for i, card in enumerate(window.perform_recalc_cards.values()):
        cut_grid.addWidget(card, i // 4, i % 4)
    recalc_layout.addLayout(cut_grid)

    recalc_split = QSplitter(Qt.Vertical)
    window.table_perform_recalc = QTableWidget(0, 8)
    window.table_perform_recalc.setHorizontalHeaderLabels([
        "평가요소", "만점", "A 예상", "B 예상", "C 예상", "D 예상", "E 예상", "근거/메모",
    ])
    _setup_table(window.table_perform_recalc, word_wrap=False, horizontal_scroll=True, row_height=32)
    # Five evaluation elements (32 px each) plus header and scrollbar; the page scrolls, so
    # without this the table got its bare minimum and showed one row at a time.
    window.table_perform_recalc.setMinimumHeight(window._px(5 * 32 + 64))
    window.table_perform_recalc.setEditTriggers(
        QAbstractItemView.DoubleClicked
        | QAbstractItemView.EditKeyPressed
        | QAbstractItemView.AnyKeyPressed
    )
    window.table_perform_recalc.itemChanged.connect(window._render_perform_recalc_results)
    recalc_split.addWidget(window.table_perform_recalc)

    window.table_perform_recalc_results = QTableWidget(0, 4)
    window.table_perform_recalc_results.setHorizontalHeaderLabels(["경계", "원점수", "100점 환산", "의미"])
    _setup_table(window.table_perform_recalc_results, word_wrap=False, horizontal_scroll=True, row_height=30)
    # Five boundaries and the check row (30 px each) plus header and scrollbar.
    window.table_perform_recalc_results.setMinimumHeight(window._px(6 * 30 + 64))
    recalc_split.addWidget(window.table_perform_recalc_results)
    recalc_split.setStretchFactor(0, 3)
    recalc_split.setStretchFactor(1, 1)
    recalc_split.setSizes([330, 170])
    recalc_layout.addWidget(recalc_split, 1)
    table_tabs.addTab(recalc_page, "분할점수 재산정")

    split.addWidget(window._fold("perform.tables", "수행평가 표", table_tabs))
    split.setStretchFactor(0, 1)
    split.setStretchFactor(1, 2)
    split.setSizes([300, 430])
    page_layout.addWidget(split, 1)
    page = QScrollArea()
    page.setWidgetResizable(True)
    page.setFrameShape(QFrame.NoFrame)
    page.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    page.setWidget(page_body)
    layout.addWidget(page, 1)
    window._reset_perform_recalc_rows()
    window._render_perform_tab()


def refresh_perform_tab(window):
    window._render_perform_tab()
    window.statusBar().showMessage("수행평가 분석 탭을 새로고침했습니다.", 2500)


def set_recalc_item(window, row: int, col: int, value, *, align_right=False):
    item = QTableWidgetItem("" if value is None else str(value))
    item.setTextAlignment((Qt.AlignRight if align_right else Qt.AlignLeft) | Qt.AlignVCenter)
    window.table_perform_recalc.setItem(row, col, item)
    return item


def add_recalc_row(window, values: dict | None = None):
    if not hasattr(window, "table_perform_recalc"):
        return
    user_added = values is None
    values = values or {}
    if user_added:
        window._perform_recalc_dirty = True
    table = window.table_perform_recalc
    table.blockSignals(True)
    row = table.rowCount()
    table.insertRow(row)
    max_score = float(values.get("max_score", 10.0))
    name = values.get("name", f"평가요소 {row + 1}")
    window._set_perform_recalc_item(row, 0, name)
    window._set_perform_recalc_item(row, 1, f"{max_score:.1f}", align_right=True)
    for idx, lv in enumerate(LEVELS_AE, start=2):
        default = max_score * PERFORM_DEFAULT_RATES[lv]
        score = float(values.get(lv, default))
        window._set_perform_recalc_item(row, idx, f"{score:.1f}", align_right=True)
    window._set_perform_recalc_item(row, 7, values.get("memo", ""))
    table.blockSignals(False)
    window._render_perform_recalc_results()


def reset_recalc_rows(window):
    if not hasattr(window, "table_perform_recalc"):
        return
    window._perform_recalc_dirty = False
    window.table_perform_recalc.blockSignals(True)
    window.table_perform_recalc.setRowCount(0)
    window.table_perform_recalc.blockSignals(False)
    if window.perform_data is not None and getattr(window.perform_data, "areas", None):
        window._recommend_perform_recalc_rows()
        return
    window._add_perform_recalc_row({"name": "평가요소 1", "max_score": 10.0, "memo": "성취율 기준 기본안"})
    window._add_perform_recalc_row({"name": "평가요소 2", "max_score": 10.0, "memo": "성취율 기준 기본안"})
    window._add_perform_recalc_row({"name": "평가요소 3", "max_score": 10.0, "memo": "성취율 기준 기본안"})


def delete_selected_recalc_rows(window):
    if not hasattr(window, "table_perform_recalc"):
        return
    rows = sorted({idx.row() for idx in window.table_perform_recalc.selectedIndexes()}, reverse=True)
    if not rows:
        return
    window._perform_recalc_dirty = True
    window.table_perform_recalc.blockSignals(True)
    for row in rows:
        window.table_perform_recalc.removeRow(row)
    window.table_perform_recalc.blockSignals(False)
    window._render_perform_recalc_results()


def recommended_scores_by_area(window):
    if window.perform_data is None or not getattr(window.perform_data, "areas", None):
        return []
    return recommend_area_scores(window.perform_data.areas, window._perform_matches())


def recommend_area_scores(areas, matches) -> list[dict]:
    """영역마다 A~E 예상점수: 그 수준 학생 가운데 총점이 낮은 대표 3명의 영역 점수 평균.

    matches는 (_, student, level, record) 묶음이다. 그 수준 학생이 없으면 만점 × 기본 비율을 쓰고,
    A ≥ B ≥ … ≥ E가 되도록 위 수준 값으로 자른다.
    """
    recommendations = []
    for area in areas:
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


def recommend_recalc_rows(window):
    if not hasattr(window, "table_perform_recalc"):
        return
    rows = window._recommended_perform_scores_by_area()
    if not rows:
        rows = [
            {"name": "평가요소 1", "max_score": 10.0, "memo": "자료 없음 · 성취율 기준"},
            {"name": "평가요소 2", "max_score": 10.0, "memo": "자료 없음 · 성취율 기준"},
            {"name": "평가요소 3", "max_score": 10.0, "memo": "자료 없음 · 성취율 기준"},
        ]
    window._perform_recalc_dirty = False
    table = window.table_perform_recalc
    table.blockSignals(True)
    table.setRowCount(0)
    table.blockSignals(False)
    for row in rows:
        window._add_perform_recalc_row(row)
    window.statusBar().showMessage("수행평가 분할점수 재산정 기본값을 적용했습니다.", 3000)


def read_recalc_rows(window):
    if not hasattr(window, "table_perform_recalc"):
        return [], []
    rows = []
    warnings = []
    table = window.table_perform_recalc
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


def recalc_summary(rows: list[dict], warnings: list[str]):
    """평가요소 행들 → (수행 만점, 수준별 예상점수 합, 점검 목록). 합이 역전되면 점검에 더한다."""
    warnings = list(warnings)
    max_total = sum(row["max_score"] for row in rows)
    totals = {
        lv: sum(row["scores"].get(lv, 0.0) for row in rows)
        for lv in LEVELS_AE
    }
    for left, right in zip(LEVELS_AE, LEVELS_AE[1:]):
        if totals[left] + 1e-9 < totals[right]:
            warnings.append(f"{left}/{right} 역전")
    return max_total, totals, warnings


def render_recalc_results(window, *changed_items):
    from .main_window import _set_item
    if not hasattr(window, "table_perform_recalc_results"):
        return
    if changed_items:
        window._perform_recalc_dirty = True
    rows, warnings = window._perform_recalc_rows()
    max_total, totals, warnings = recalc_summary(rows, warnings)

    if hasattr(window, "perform_recalc_cards"):
        window.perform_recalc_cards["max"].value_label.setText(f"{max_total:.1f}")
        for lv in LEVELS_AE:
            window.perform_recalc_cards[lv].value_label.setText(f"{totals[lv]:.1f}")
        window.perform_recalc_cards["check"].value_label.setText(str(len(warnings)))

    result_rows = [
        ("A/B", totals["A"], "A 최소능력자 예상점수 합"),
        ("B/C", totals["B"], "B 최소능력자 예상점수 합"),
        ("C/D", totals["C"], "C 최소능력자 예상점수 합"),
        ("D/E", totals["D"], "D 최소능력자 예상점수 합"),
        ("E/미도달", totals["E"], "E 최소능력자 예상점수 합"),
    ]
    table = window.table_perform_recalc_results
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
        window._set_scaled_column_width(table, col, width)
    for col, width in enumerate([210, 76, 82, 82, 82, 82, 82, 260]):
        window._set_scaled_column_width(window.table_perform_recalc, col, width)
