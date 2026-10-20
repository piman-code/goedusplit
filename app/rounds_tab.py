"""회차 비교 탭: 저장된 회차 기록 두 개를 골라 성취수준 분포·지표·학생 이동을 비교한다.

비교 계산은 `rounds.compare`가 하고, 여기서는 화면만 만든다. 위젯과 상태는 기존처럼
window 속성(`cmb_round_base`, `_round_records` 등)에 두어 작업 세션 복원과 QA가 그대로 읽는다.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QPushButton, QSplitter,
                               QTableWidget, QVBoxLayout, QWidget)

from . import lazy_charts as charts
from . import rounds as round_history


def build_rounds_tab(window):
    from .main_window import CanvasHolder, _setup_table
    layout = QVBoxLayout(window.tab_rounds)
    intro = QLabel(
        "분석할 때마다 자동으로 쌓인 회차 기록 가운데 두 개를 골라 비교합니다. 같은 학생은 이름 없이 해시로만 "
        "이어지고, 기록은 이 컴퓨터에만 저장됩니다. 같은 과목·학기·차수를 다시 분석하면 최신 결과로 바뀝니다."
    )
    intro.setProperty("role", "muted"); intro.setWordWrap(True)
    layout.addWidget(intro)
    row = QHBoxLayout()
    window.cmb_round_base = QComboBox(); window.cmb_round_other = QComboBox()
    for box in (window.cmb_round_base, window.cmb_round_other):
        box.setMinimumContentsLength(16)
        box.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
    row.addWidget(QLabel("기준")); row.addWidget(window.cmb_round_base, 1)
    row.addWidget(QLabel("비교")); row.addWidget(window.cmb_round_other, 1)
    btn_refresh = QPushButton("새로고침")
    btn_refresh.clicked.connect(window._refresh_rounds_tab)
    row.addWidget(btn_refresh)
    layout.addLayout(row)
    window.lbl_round_status = QLabel("")
    window.lbl_round_status.setProperty("role", "muted"); window.lbl_round_status.setWordWrap(True)
    layout.addWidget(window.lbl_round_status)

    body = QSplitter(Qt.Vertical)
    window.canvas_round_compare = CanvasHolder()
    window.canvas_round_compare.setMinimumHeight(window._px(170))
    body.addWidget(window._fold("rounds.chart", "성취수준 분포 비교", window.canvas_round_compare))
    tables = QSplitter(Qt.Horizontal)
    window.table_round_metrics = QTableWidget(0, 4)
    window.table_round_metrics.setHorizontalHeaderLabels(["항목", "기준", "비교", "변화"])
    _setup_table(window.table_round_metrics, row_height=30)
    tables.addWidget(window._fold("rounds.metrics", "지표 비교", window.table_round_metrics))
    moves_wrap = QWidget()
    moves_layout = QVBoxLayout(moves_wrap); moves_layout.setContentsMargins(0, 0, 0, 0)
    window.lbl_round_moves = QLabel("")
    window.lbl_round_moves.setProperty("role", "muted"); window.lbl_round_moves.setWordWrap(True)
    moves_layout.addWidget(window.lbl_round_moves)
    window.table_round_moves = QTableWidget(0, 0)
    _setup_table(window.table_round_moves, row_height=30)
    moves_layout.addWidget(window.table_round_moves, 1)
    tables.addWidget(window._fold("rounds.moves", "학생 성취수준 이동 (기준 → 비교)", moves_wrap))
    body.addWidget(tables)
    body.setSizes([260, 320])
    layout.addWidget(body, 1)
    window._round_records: list[dict] = []
    window.cmb_round_base.currentIndexChanged.connect(window._render_rounds_compare)
    window.cmb_round_other.currentIndexChanged.connect(window._render_rounds_compare)
    window._refresh_rounds_tab()


def course_round_records(window) -> list[dict]:
    records = window._round_store().load_all()
    exam = getattr(window, "exam", None)
    if exam is not None:
        return round_history.same_course(records, exam.subject or "(과목 미상)", exam.grade)
    return records


def refresh_rounds_tab(window):
    if not hasattr(window, "cmb_round_base"):
        return
    records = window._course_round_records()
    keep = [window.cmb_round_base.currentData(), window.cmb_round_other.currentData()]
    window._round_records = records
    multi_subject = len({(r.get("subject"), r.get("grade")) for r in records}) > 1
    for box in (window.cmb_round_base, window.cmb_round_other):
        box.blockSignals(True)
        box.clear()
        for index, record in enumerate(records):
            prefix = f"{record.get('subject')} · " if multi_subject else ""
            caution = "" if record.get("round_provenance") == "written-response-v1" and record.get("response_fingerprint") else " · 입력 출처 미확인"
            box.addItem(f"{prefix}{record['label']} ({record['n_students']}명){caution}", index)
        box.blockSignals(False)
    if records:
        def pick(box, wanted, default):
            found = box.findData(wanted) if wanted is not None else -1
            box.setCurrentIndex(found if found >= 0 else default)
        # 새 회차가 쌓였거나 두 칸이 같아지면 가장 최근 두 회차를 고른다. 아니면 고르던 것을 유지한다.
        changed = len(records) != getattr(window, "_round_count_seen", None) or keep[0] == keep[1]
        verified = [i for i,r in enumerate(records) if r.get("round_provenance")=="written-response-v1"
                    and r.get("response_fingerprint") and all(r.get(k) is not None for k in ("year","semester_no","round_no"))]
        unique = {}
        for index in verified:
            unique[records[index]["response_fingerprint"]] = index
        verified = sorted(unique.values())
        # Legacy summaries stay selectable, but never become verified inputs by default.
        defaults = (verified[-2],verified[-1]) if len(verified)>1 else ((verified[0],-1) if verified else (-1,-1))
        pick(window.cmb_round_base, None if changed else keep[0], defaults[0])
        pick(window.cmb_round_other, None if changed else keep[1], defaults[1])
    window._round_count_seen = len(records)
    window._render_rounds_compare()


def render_rounds_compare(window, *_args):
    from .main_window import _set_item
    if not hasattr(window, "table_round_metrics"):
        return
    records = getattr(window, "_round_records", [])
    base_i, other_i = window.cmb_round_base.currentData(), window.cmb_round_other.currentData()
    window.table_round_metrics.setRowCount(0)
    window.table_round_moves.setRowCount(0); window.table_round_moves.setColumnCount(0)
    if len(records) < 2 or base_i is None or other_i is None:
        window.canvas_round_compare.set_placeholder("서로 다른 두 회차를 분석하면 비교 그래프를 표시합니다.")
        window.lbl_round_moves.setText("")
        window.lbl_round_status.setText(
            "저장 기록 %d개 · 입력 출처가 확인된 서로 다른 두 회차를 분석하면 자동 비교합니다. 미확인 옛 기록은 직접 선택할 수 있습니다. "
            "분석 전에 '시험 구분'을 확인하세요." % len(records))
        return
    if base_i == other_i:
        window.canvas_round_compare.set_placeholder("서로 다른 두 회차를 분석하면 비교 그래프를 표시합니다.")
        window.lbl_round_status.setText("기준과 비교에 서로 다른 회차를 골라 주세요.")
        return
    base, other = records[base_i], records[other_i]
    if any(record.get(key) is None for record in (base,other) for key in ("year","semester_no","round_no")):
        window.canvas_round_compare.set_placeholder("회차 미확인 기록은 비교하지 않습니다. 원래 기록은 보존됩니다.")
        window.lbl_round_status.setText("학년도·학기·차수가 확인된 기록을 선택하세요.")
        return
    if base.get("response_fingerprint") and base.get("response_fingerprint")==other.get("response_fingerprint"):
        window.canvas_round_compare.set_placeholder("두 기록의 정오표 입력이 같습니다. 다른 시험 입력을 확인하세요.")
        window.lbl_round_status.setText("동일 입력의 회차 표기만 다른 기록 · 원래 기록 보존")
        return
    result = round_history.compare(base, other)
    warning = " · 입력 출처 미확인 옛 기록 포함" if any(not record.get("response_fingerprint") for record in (base,other)) else ""
    window.lbl_round_status.setText(f"{base['label']} → {other['label']}{warning}")
    if not getattr(window, "_startup_building", False):
        window.canvas_round_compare.set_figure(charts.fig_round_compare(base, other))

    def fmt(value, signed=False):
        if value is None:
            return "-"
        text = f"{value:+.1f}" if signed else f"{value:.1f}"
        return text[:-2] if text.endswith(".0") else text
    table = window.table_round_metrics
    table.setRowCount(len(result["rows"]))
    good, bad = QColor("#cfe8d5"), QColor("#f5c9c9")
    for r, (name, a, b, diff) in enumerate(result["rows"]):
        _set_item(table, r, 0, name, align_left=True)
        _set_item(table, r, 1, fmt(a)); _set_item(table, r, 2, fmt(b))
        tint = None
        if diff and name.startswith("A 비율"):
            tint = good if diff > 0 else bad
        _set_item(table, r, 3, fmt(diff, signed=True), bold=True, bg=tint)
    moves = window.table_round_moves
    levels = [lv for lv in round_history.LEVELS
              if lv != "미도달" or any(result["matrix"][lv][o] or result["matrix"][o][lv] for o in round_history.LEVELS)]
    moves.setColumnCount(len(levels) + 1); moves.setRowCount(len(levels))
    moves.setHorizontalHeaderLabels(["기준＼비교"] + levels)
    up, down = QColor("#cfe8d5"), QColor("#f5c9c9")
    for r, src in enumerate(levels):
        _set_item(moves, r, 0, src, bold=True)
        for c, dst in enumerate(levels, start=1):
            count = result["matrix"][src][dst]
            shade = None
            if count and levels.index(dst) < levels.index(src):
                shade = up
            elif count and levels.index(dst) > levels.index(src):
                shade = down
            _set_item(moves, r, c, count if count else "", bg=shade, bold=(src == dst and count > 0))
    window.lbl_round_moves.setText(
        f"같은 학생 {result['paired']}명: 상승 {result['up']}명 · 유지 {result['same']}명 · 하락 {result['down']}명"
        f" (한쪽 회차에만 있는 학생: 기준 {result['only_base']}명, 비교 {result['only_other']}명). "
        "초록=수준 상승, 빨강=수준 하락.")
