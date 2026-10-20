"""Full-work capture and restore using the existing analysis widgets and renderer."""
from __future__ import annotations

import copy
import html
import json
import math
from pathlib import Path

from PySide6.QtCore import QObject, QSignalBlocker, Qt, QTimer
from PySide6.QtGui import QAction, QShortcut
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFileDialog, QHBoxLayout,
                              QInputDialog, QLabel, QLineEdit, QListWidget, QMessageBox,
                              QPlainTextEdit, QPushButton, QTabWidget, QTableWidget,
                              QTableWidgetItem, QVBoxLayout, QSplitter, QWidget, QAbstractButton,
                              QSpinBox, QDoubleSpinBox, QGroupBox, QHeaderView)

from . import rounds
from .work_sessions import MAX_BYTES, WorkSessionStore, build_session, encode_domain, prepare_session, signature
from .data_loader import split_paths, PATH_SEPARATOR

SELECTORS = ("fs_response", "fs_iteminfo", "fs_cuts", "fs_perform", "fs_grade5_report")
CONTROLS = ("cmb_round", "chk_perform", "le_search", "combo_filter_level", "combo_filter_grade9",
            "combo_filter_grade5", "chk_counsel_only_target", "chk_chart_achievement_cuts",
            "chk_chart_grade9", "chk_chart_grade5", "chk_chart_student_markers", "chk_chart_student_labels",
            "le_portfolio_search", "combo_portfolio_student", "combo_portfolio_subject", "combo_item",
            "btn_counsel_mode", "portfolio_history_toggle", "portfolio_round_combo", "portfolio_version_combo", "portfolio_show_student", "portfolio_show_mean", "txt_ai_review_source", "txt_ai_review_reference", "txt_ai_review_prompt")
EDIT_TABLES = ("table_perform_recalc", "table_ai_review")
MAX_ANALYSIS_SESSIONS = 1024


def _tab_identity(window, widget):
    names = [name for name, value in vars(window).items() if value is widget]
    if names:
        return names[0]
    return widget.objectName()


def _initialize_tab_ids(window):
    for index, tabs in enumerate(window.findChildren(QTabWidget)):
        if not _tab_identity(window, tabs):
            tabs.setObjectName(f"work-tabs-{index}")
        for page_index in range(tabs.count()):
            page = tabs.widget(page_index)
            if not _tab_identity(window, page):
                page.setObjectName(f"{_tab_identity(window, tabs)}-page-{page_index}")


def _round_key(record):
    return rounds.record_key(record.get("subject"), record.get("grade"), record.get("year"),
                             record.get("semester_no"), record.get("round_no"))


def _state_tables(window):
    """Stable optional keys include nested portfolio tables in newer snapshots."""
    tables = {name: value for name, value in vars(window).items()
              if isinstance(value, QTableWidget) and name not in EDIT_TABLES}
    for key, table in getattr(window, "portfolio_detail_tables", {}).items():
        if key in {"data", "perform", "items", "choice", "standards"} and isinstance(table, QTableWidget):
            tables["portfolio_detail:" + key] = table
    return tables


def capture_ui_state(window):
    _initialize_tab_ids(window)
    # Ask Qt to settle initial/stale splitter sizes with the active style's
    # handle widths and minimum hints. This is idempotent on laid-out splitters.
    for splitter in window.findChildren(QSplitter):
        splitter.setSizes(splitter.sizes())
    state = {"inputs": {name: getattr(window, name).path() for name in SELECTORS if hasattr(window, name)},
             "widgets": {}, "cuts": window._current_cut_scores_from_inputs(),
             "weights": [window.spin_pencil_ratio.value(), window.spin_perform_ratio.value()],
             "monitor": {key: spin.value() for key, spin in getattr(window, "monitor_spins", {}).items()},
             "perform_recalc_dirty": window._perform_recalc_dirty,
             "edit_tables": {}, "tabs": [], "folds": {}, "round_selection": [], "table_headers": {},
             "splitters": [widget.sizes() for widget in window.findChildren(QSplitter)],
             "portfolio_analysis_sessions": copy.deepcopy(getattr(window, "_portfolio_analysis_sessions", {})),
             "grade5_reports": copy.deepcopy(getattr(window, "_last_grade5_cut_reports", None)),
             "grade5_info": window.lbl_grade5_cut_info.text() if hasattr(window, "lbl_grade5_cut_info") else ""}
    for name in CONTROLS:
        widget = getattr(window, name, None)
        if widget is None:
            continue
        if isinstance(widget, QComboBox):
            data = widget.currentData()
            # Choice-combo userData is a derived ItemStats object; its stable
            # displayed item number selects the reconstructed object after render.
            if name == "combo_item":
                data = None
            state["widgets"][name] = {"text": widget.currentText(), "data": data}
        elif isinstance(widget, QLineEdit):
            state["widgets"][name] = widget.text()
        elif isinstance(widget, QPlainTextEdit):
            state["widgets"][name] = widget.toPlainText()
        elif hasattr(widget, "isChecked"):
            state["widgets"][name] = widget.isChecked()
    for name in EDIT_TABLES:
        table = getattr(window, name, None)
        if table is not None:
            state["edit_tables"][name] = [
                [table.item(r, c).text() if table.item(r, c) else None for c in range(table.columnCount())]
                for r in range(table.rowCount())]
    for widget in window.findChildren(QTabWidget):
        state["tabs"].append({"widget": _tab_identity(window, widget),
                              "selected": _tab_identity(window, widget.currentWidget()) if widget.currentWidget() else None,
                              "order": [_tab_identity(window, widget.widget(i)) for i in range(widget.count())]})
    for widget in window.findChildren(QObject):
        if isinstance(getattr(widget, "_key", None), str) and widget._key.startswith("ui/fold/"):
            state["folds"][widget._key] = widget.is_open()
    for box in (window.cmb_round_base, window.cmb_round_other):
        index = box.currentData()
        state["round_selection"].append(_round_key(window._round_records[index])
            if isinstance(index, int) and 0 <= index < len(window._round_records) else None)
    for name, table in _state_tables(window).items():
        if isinstance(table, QTableWidget):
            control = getattr(table, "_column_controls", None)
            if control is not None:
                # Rendering can leave the automatic sizing mode in place until
                # its queued column-control update. Snapshot the settled UI,
                # just as it appears after the next event-loop iteration.
                control.apply()
            header = table.horizontalHeader()
            state["table_headers"][name] = {"state": [{"visual": header.visualIndex(c), "mode": header.sectionResizeMode(c).value,
                    "width": header.sectionSize(c) if header.sectionResizeMode(c).value in (0, 2) else None,
                    "hidden": header.isSectionHidden(c)} for c in range(table.columnCount())],
                "sort": header.sortIndicatorSection(), "order": header.sortIndicatorOrder().value,
                "row": table.currentRow(), "column": table.currentColumn()}
    return state


def _validate_ui(window, state):
    _initialize_tab_ids(window)
    required = {"inputs", "widgets", "cuts", "weights", "monitor", "perform_recalc_dirty",
                "edit_tables", "tabs", "folds", "round_selection", "table_headers", "splitters",
                "grade5_reports", "grade5_info"}
    optional = {"portfolio_analysis_sessions"}
    if not isinstance(state, dict) or not required.issubset(state) or set(state) - required - optional:
        raise ValueError("화면 편집 상태가 누락되었습니다.")
    sessions = state.get("portfolio_analysis_sessions", {})
    if not isinstance(sessions, dict):
        raise ValueError("회차 분석 자료가 올바르지 않습니다.")
    if len(sessions) > MAX_ANALYSIS_SESSIONS:
        raise ValueError("회차 분석 자료 수가 제한을 넘었습니다.")
    try:
        cache_bytes = json.dumps(sessions, ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:
        raise ValueError("회차 분석 자료에 유효하지 않은 값이 있습니다.") from exc
    if len(cache_bytes) > MAX_BYTES:
        raise ValueError("회차 분석 자료 크기가 제한을 넘었습니다.")
    for session_id, payload in sessions.items():
        if not isinstance(session_id, str) or not session_id or len(session_id)>128:
            raise ValueError("회차 분석 식별자가 올바르지 않습니다.")
        if not isinstance(payload, dict) or not isinstance(payload.get("ui_state"), dict):
            raise ValueError("회차 분석 자료가 올바르지 않습니다.")
        cached_ui = payload["ui_state"]
        # Analysis cache entries are minimal snapshots, never nested full works.
        if set(cached_ui) != {"inputs", "widgets"}:
            raise ValueError("회차 분석 자료의 중첩 저장은 허용하지 않습니다.")
        inputs, widgets = cached_ui["inputs"], cached_ui["widgets"]
        if not isinstance(inputs,dict) or set(inputs)-set(SELECTORS) or any(not isinstance(v,str) for v in inputs.values()):
            raise ValueError("회차 분석 입력 경로가 올바르지 않습니다.")
        if not isinstance(widgets,dict) or set(widgets)!={"cmb_round"} or not isinstance(widgets["cmb_round"],dict) or set(widgets["cmb_round"])!={"text"} or not isinstance(widgets["cmb_round"]["text"],str):
            raise ValueError("회차 분석 구분이 올바르지 않습니다.")
        prepare_session(payload)

    if set(state["inputs"]) - set(SELECTORS) or set(state["widgets"]) - set(CONTROLS):
        raise ValueError("지원하지 않는 입력 상태입니다.")
    if set(state["edit_tables"]) - set(EDIT_TABLES):
        raise ValueError("지원하지 않는 표 편집 상태입니다.")
    if set(state["cuts"]) != set("ABCDE") or len(state["weights"]) != 2:
        raise ValueError("입력 분할점수·가중치 상태가 누락되었습니다.")
    if any(not isinstance(value, str) for value in state["inputs"].values()):
        raise ValueError("원본 경로는 문자열이어야 합니다.")
    for name, value in state["widgets"].items():
        widget = getattr(window, name, None)
        if isinstance(widget, QComboBox):
            if not isinstance(value, dict) or set(value) != {"text", "data"} or not isinstance(value["text"], str):
                raise ValueError("선택 상태가 올바르지 않습니다.")
        elif isinstance(widget, (QLineEdit, QPlainTextEdit)):
            if not isinstance(value, str):
                raise ValueError("입력 문구가 올바르지 않습니다.")
        elif hasattr(widget, "setChecked") and not isinstance(value, bool):
            raise ValueError("체크 상태가 올바르지 않습니다.")
    def finite(value):
        return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)
    if any(not finite(v) or not 0 <= v <= 100 for v in [*state["cuts"].values(), *state["weights"]]):
        raise ValueError("분할점수·가중치 범위가 올바르지 않습니다.")
    for name, value in state["monitor"].items():
        if name not in window.monitor_spins or not finite(value):
            raise ValueError("모니터링 값이 올바르지 않습니다.")
        spin = window.monitor_spins[name].spin
        if not spin.minimum() <= value <= spin.maximum():
            raise ValueError("모니터링 입력 범위를 벗어났습니다.")
    if not isinstance(state["perform_recalc_dirty"], bool) or any(not isinstance(v, bool) for v in state["folds"].values()):
        raise ValueError("화면 상태가 올바르지 않습니다.")
    tabs_by_id = {_tab_identity(window, tabs): tabs for tabs in window.findChildren(QTabWidget)}
    for data in state["tabs"]:
        if not isinstance(data, dict) or set(data) != {"widget", "selected", "order"} or data["widget"] not in tabs_by_id:
            raise ValueError("탭 선택 상태가 올바르지 않습니다.")
        tabs = tabs_by_id[data["widget"]]
        expected = {_tab_identity(window, tabs.widget(i)) for i in range(tabs.count())}
        if not isinstance(data["order"], list) or set(data["order"]) != expected or len(data["order"]) != len(expected):
            raise ValueError("탭 순서가 올바르지 않습니다.")
        if data["selected"] not in expected and expected:
            raise ValueError("선택한 탭이 존재하지 않습니다.")
    for name, data in state["table_headers"].items():
        table = _state_tables(window).get(name)
        if not isinstance(table, QTableWidget) or not isinstance(data, dict) or set(data) != {"state", "sort", "order", "row", "column"}:
            raise ValueError("표 머리글 상태가 올바르지 않습니다.")
        if any(not isinstance(data[key], int) or isinstance(data[key], bool) for key in ("sort", "order", "row", "column")) or data["order"] not in (0, 1):
            raise ValueError("표 정렬 상태가 올바르지 않습니다.")
        columns = data["state"]
        if not isinstance(columns, list) or len(columns) > 10000:
            raise ValueError("표 너비 상태가 올바르지 않습니다.")
        for column in columns:
            if not isinstance(column, dict) or set(column) != {"visual", "mode", "width", "hidden"}:
                raise ValueError("표 열 상태가 올바르지 않습니다.")
            if type(column["visual"]) is not int or type(column["mode"]) is not int or column["mode"] not in (0, 1, 2, 3) or type(column["hidden"]) is not bool:
                raise ValueError("표 열 상태가 올바르지 않습니다.")
            if column["width"] is not None and (type(column["width"]) is not int or not 0 <= column["width"] <= 100000):
                raise ValueError("표 열 너비가 올바르지 않습니다.")
        if sorted(column["visual"] for column in columns) != list(range(len(columns))):
            raise ValueError("표 열 순서가 올바르지 않습니다.")
    if not isinstance(state["splitters"], list) or any(not isinstance(row, list) or any(
            not isinstance(v, int) or isinstance(v, bool) or v < 0 for v in row) for row in state["splitters"]):
        raise ValueError("화면 배치 상태가 올바르지 않습니다.")
    for name, rows in state["edit_tables"].items():
        table = getattr(window, name, None)
        if table is None:
            if rows:
                raise ValueError("이 앱에서 지원하지 않는 편집 표가 있습니다.")
            continue
        if not isinstance(rows, list) or any(not isinstance(row, list) or len(row) != table.columnCount()
                                             or any(v is not None and not isinstance(v, str) for v in row) for row in rows):
            raise ValueError("편집 표 구조가 올바르지 않습니다.")


def _set_control(widget, value):
    if widget is None:
        return
    blocker = QSignalBlocker(widget)
    if isinstance(widget, QComboBox):
        index = widget.findData(value["data"]) if value.get("data") is not None else -1
        if index < 0:
            index = widget.findText(value["text"])
        if index >= 0:
            widget.setCurrentIndex(index)
        elif widget.isEditable():
            widget.setEditText(value["text"])
    elif isinstance(widget, QLineEdit):
        widget.setText(value)
    elif isinstance(widget, QPlainTextEdit):
        widget.setPlainText(value)
    elif hasattr(widget, "setChecked"):
        widget.setChecked(value)
    del blocker


def _apply_python(window, prepared):
    from PySide6.QtCore import QByteArray
    state = prepared["ui_state"]
    # Missing optional data in older works means no historical cache, never B's.
    window._portfolio_analysis_sessions = copy.deepcopy(state.get("portfolio_analysis_sessions", {}))
    window.exam, window.perform_data = prepared["exam"], prepared["perform_data"]
    window.overall, window.item_stats = prepared["overall"], prepared["item_stats"]
    for name, path in state["inputs"].items():
        _set_control(getattr(window, name).path_edit, path)
    for group, values in ((window.spin_cuts, state["cuts"]),
                          (window.monitor_spins, state["monitor"])):
        for name, value in values.items():
            if name in group:
                spin = group[name]
                blocker = QSignalBlocker(spin.spin)
                spin.setValue(value)
                del blocker
    for spin, value in zip((window.spin_pencil_ratio, window.spin_perform_ratio), state["weights"]):
        blocker = QSignalBlocker(spin.spin)
        spin.setValue(value)
        del blocker
    for name, value in state["widgets"].items():
        _set_control(getattr(window, name, None), value)
    # Set availability without resetting a captured draft's numeric values.
    window.fs_perform.setEnabled(window.chk_perform.isChecked())
    window.spin_perform_ratio.setEnabled(window.chk_perform.isChecked())
    window._update_cut_box_title()
    window._update_round_hint()
    window._last_grade5_cut_reports = copy.deepcopy(state["grade5_reports"])
    if hasattr(window, "lbl_grade5_cut_info"):
        window.lbl_grade5_cut_info.setText(state["grade5_info"])
    for name, rows in state["edit_tables"].items():
        table = getattr(window, name, None)
        if table is None:
            continue
        blocker = QSignalBlocker(table)
        table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, text in enumerate(row):
                table.setItem(r, c, QTableWidgetItem(text) if text is not None else None)
        del blocker
    window._perform_recalc_dirty = state["perform_recalc_dirty"]
    window._render_perform_recalc_results()
    window._perform_recalc_dirty = state["perform_recalc_dirty"]
    window._render_choice_combo()
    window._refresh_all_charts()
    window.refresh_portfolio_tab()
    window._refresh_rounds_tab()
    # Rendering rebuilds combos/tables. Restore selection identities afterwards.
    for name, value in state["widgets"].items():
        _set_control(getattr(window, name, None), value)
    for box, key in zip((window.cmb_round_base, window.cmb_round_other), state["round_selection"]):
        for index, record in enumerate(window._round_records):
            if _round_key(record) == key:
                _set_control(box, {"data": index, "text": box.itemText(index)})
                break
    window._filter_data_table(window.le_search.text())
    window._filter_portfolio_table()
    window._render_choice()
    window._render_rounds_compare()
    window._on_counseling_mode_changed(window.btn_counsel_mode.isChecked())
    for widget in window.findChildren(QObject):
        key = getattr(widget, "_key", None)
        if key in state["folds"]:
            blocker = QSignalBlocker(widget.toggle)
            widget.toggle.setChecked(state["folds"][key])
            widget._apply(state["folds"][key], remember=False)
            del blocker
    for data in state["tabs"]:
        widget = next(w for w in window.findChildren(QTabWidget) if _tab_identity(window, w) == data["widget"])
        blocker = QSignalBlocker(widget)
        for position, page_id in enumerate(data["order"]):
            index = next(i for i in range(widget.count()) if _tab_identity(window, widget.widget(i)) == page_id)
            if position != index:
                widget.tabBar().moveTab(index, position)
        if data["selected"] is not None:
            widget.setCurrentIndex(next(i for i in range(widget.count()) if _tab_identity(window, widget.widget(i)) == data["selected"]))
        del blocker
    for widget, sizes in zip(window.findChildren(QSplitter), state["splitters"]):
        if len(sizes) == widget.count():
            widget.setSizes(sizes)
    for name, data in state["table_headers"].items():
        table = _state_tables(window).get(name)
        if isinstance(table, QTableWidget):
            header = table.horizontalHeader()
            if len(data["state"]) == table.columnCount():
                for logical, column in sorted(enumerate(data["state"]), key=lambda pair: pair[1]["visual"]):
                    header.moveSection(header.visualIndex(logical), column["visual"])
                    header.setSectionResizeMode(logical, QHeaderView.ResizeMode(column["mode"]))
                    if column["width"] is not None:
                        header.resizeSection(logical, column["width"])
                    header.setSectionHidden(logical, column["hidden"])
                control = getattr(table, "_column_controls", None)
                if control is not None:
                    # The restored snapshot, rather than a previous work's
                    # drag widths, becomes the current width preference.
                    control.adopt_current_widths()
            if table.isSortingEnabled() and 0 <= data["sort"] < table.columnCount():
                table.sortItems(data["sort"], Qt.SortOrder(data["order"]))
            if 0 <= data["row"] < table.rowCount() and 0 <= data["column"] < table.columnCount():
                table.setCurrentCell(data["row"], data["column"])
    window._snapshot_inputs()
    window.btn_revert.setEnabled(True)
    exam = window.exam
    window.exam_info_lbl.setText(f"<b>{html.escape(exam.subject)}</b><br>{html.escape(exam.semester)} "
                                f"{html.escape(exam.grade)}<br>학생 {len(exam.students)}명 · 문항 {len(exam.items)}문항")


def _empty_view_checkpoint(window):
    """Keep the empty view independently of analysis renderers for rollback."""
    from .main_window import CanvasHolder
    tables, values, charts, flags = [], [], [], []
    tab_order = [(tabs, [tabs.widget(i) for i in range(tabs.count())], tabs.currentWidget())
                 for tabs in window.findChildren(QTabWidget)]
    splitter_sizes = [(splitter, splitter.sizes(), splitter.geometry()) for splitter in window.findChildren(QSplitter)]
    for widget in window.findChildren(QWidget):
        # Cell widgets may be destroyed by table rendering; their items are cloned below.
        parent = widget.parentWidget()
        in_table = False
        while parent is not None:
            if isinstance(parent, QTableWidget):
                in_table = True
                break
            parent = parent.parentWidget()
        if in_table:
            continue
        flags.append((widget, widget.isHidden(), not widget.testAttribute(Qt.WA_ForceDisabled),
                      widget.minimumSize(), widget.maximumSize(), widget.geometry()))
        if isinstance(widget, QTableWidget):
            clone = lambda item: item.clone() if item is not None else None
            tables.append((widget, widget.rowCount(), widget.columnCount(),
                           [[clone(widget.item(r, c)) for c in range(widget.columnCount())]
                            for r in range(widget.rowCount())],
                           [clone(widget.horizontalHeaderItem(c)) for c in range(widget.columnCount())],
                           [clone(widget.verticalHeaderItem(r)) for r in range(widget.rowCount())],
                           widget.horizontalHeader().saveState(), widget.isSortingEnabled()))
        elif isinstance(widget, CanvasHolder):
            charts.append((widget, widget._canvas.figure if widget._canvas is not None else None,
                           widget._placeholder.text()))
        elif isinstance(widget, QComboBox):
            values.append((widget, "combo", ([(widget.itemText(i), widget.itemData(i))
                                               for i in range(widget.count())], widget.currentIndex(), widget.currentText())))
        elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
            values.append((widget, "value", widget.value()))
        elif isinstance(widget, (QLineEdit, QLabel)):
            values.append((widget, "text", widget.text()))
        elif isinstance(widget, QPlainTextEdit):
            values.append((widget, "plain", widget.toPlainText()))
        elif isinstance(widget, QAbstractButton):
            values.append((widget, "checked", widget.isChecked()))
        elif isinstance(widget, QGroupBox):
            values.append((widget, "title", widget.title()))
    # Rendering replaces these Python caches; retain their pre-restore identities.
    attrs = {name: value for name, value in vars(window).items()
             if name.startswith("_") and not isinstance(value, QObject)}

    def restore():
        for name, value in attrs.items():
            setattr(window, name, value)
        blockers = [QSignalBlocker(widget) for widget, _, _ in values]
        blockers += [QSignalBlocker(table) for table, *_ in tables]
        for table, rows, columns, items, horizontal, vertical, header, sorting in tables:
            table.setSortingEnabled(False)
            table.clear()
            table.setColumnCount(columns)
            table.setRowCount(rows)
            for c, item in enumerate(horizontal):
                if item is not None:
                    table.setHorizontalHeaderItem(c, item)
            for r, item in enumerate(vertical):
                if item is not None:
                    table.setVerticalHeaderItem(r, item)
            for r, row in enumerate(items):
                for c, item in enumerate(row):
                    if item is not None:
                        table.setItem(r, c, item)
            table.horizontalHeader().restoreState(header)
            table.setSortingEnabled(sorting)
        for widget, kind, value in values:
            if kind == "combo":
                items, index, text = value
                widget.clear()
                for label, data in items:
                    widget.addItem(label, data)
                widget.setCurrentIndex(index)
                if widget.isEditable():
                    widget.setEditText(text)
            elif kind == "value": widget.setValue(value)
            elif kind == "text": widget.setText(value)
            elif kind == "plain": widget.setPlainText(value)
            elif kind == "checked": widget.setChecked(value)
            elif kind == "title": widget.setTitle(value)
        for holder, figure, text in charts:
            if figure is None: holder.set_placeholder(text)
            else: holder.set_figure(figure)
        for tabs, pages, selected in tab_order:
            blocker = QSignalBlocker(tabs)
            for position, page in enumerate(pages):
                tabs.tabBar().moveTab(tabs.indexOf(page), position)
            if selected is not None:
                tabs.setCurrentWidget(selected)
            del blocker
        for widget, hidden, enabled, minimum, maximum, geometry in flags:
            widget.setMinimumSize(minimum)
            widget.setMaximumSize(maximum)
            widget.setEnabled(enabled)
            widget.setVisible(not hidden)
            widget.setGeometry(geometry)
        for splitter, sizes, geometry in splitter_sizes:
            splitter.setGeometry(geometry)
            splitter.setSizes(sizes)
        del blockers
    return restore


def apply_python_state(window, prepared):
    _validate_ui(window, prepared["ui_state"])
    previous = {"exam": window.exam, "perform_data": window.perform_data, "overall": window.overall,
                "item_stats": window.item_stats, "ui_state": capture_ui_state(window)}
    previous_cache = copy.deepcopy(getattr(window,"_portfolio_analysis_sessions",{}))
    rollback_empty = _empty_view_checkpoint(window) if previous["exam"] is None else None
    try:
        _apply_python(window, prepared)
    except Exception:
        try:
            if previous["exam"] is not None:
                _apply_python(window, previous)
            else:
                window.exam, window.perform_data = previous["exam"], previous["perform_data"]
                window.overall, window.item_stats = previous["overall"], previous["item_stats"]
                rollback_empty()
        finally:
            window._portfolio_analysis_sessions = previous_cache
        raise


class WorkSessionController(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.busy = False
        self.last_saved_signature = None
        self._cached_project = None
        self._token = 0
        self.result_only = False
        self._read_only_enabled = {}
        self.reconnect_buttons = []
        self._action_states = None

    def _lock(self, locked):
        if locked:
            self._action_states = [(action, action.isEnabled()) for action in
                                   [*self.window.findChildren(QAction), *self.window.findChildren(QShortcut)]]
            for action, _ in self._action_states:
                action.setEnabled(False)
            self.window.setEnabled(False)
        else:
            self.window.setEnabled(True)
            for action, enabled in self._action_states or []:
                action.setEnabled(enabled)
            self._action_states = None

    def _set_result_only(self, enabled):
        self.result_only = enabled
        widgets = [self.window.btn_run_analysis, self.window.tab_perform, self.window.input_panel,
                   self.window.tab_monitor, self.window.btn_portfolio_save]
        if self.window.spliter_view is not None:
            widgets.append(self.window.spliter_view)
        if self.window.tab_ai_review is not None:
            widgets.append(self.window.tab_ai_review)
        widgets.extend(action for action in self.window.findChildren(QAction)
                       if action.text() == "분석 실행")
        if enabled:
            # Capture each widget's own flag before disabling ancestors; inherited
            # disabled state must not leave children disabled after reconnecting.
            for widget in widgets:
                own_enabled = (not widget.testAttribute(Qt.WA_ForceDisabled)
                               if isinstance(widget, QWidget) else widget.isEnabled())
                self._read_only_enabled.setdefault(widget, own_enabled)
            for widget in widgets:
                widget.setEnabled(False)
        else:
            for widget, was_enabled in list(self._read_only_enabled.items()):
                widget.setEnabled(was_enabled)
            self._read_only_enabled.clear()
        for button in self.reconnect_buttons:
            button.setEnabled(enabled)

    @staticmethod
    def missing_inputs(payload):
        return {name: path for name, path in payload["ui_state"]["inputs"].items()
                if path and any(not Path(p).is_file() for p in split_paths(path))}

    def reconnect_dialog(self):
        if not self.result_only:
            return
        def captured(payload, error):
            if error:
                QMessageBox.warning(self.window, "원본 재연결", str(error)); return
            self._reconnect(payload, lambda updated: self._restore_dialog(updated, False))
        self.capture(captured)

    def _reconnect(self, payload, after):
        updated = copy.deepcopy(payload)
        missing = self.missing_inputs(updated)
        for name in missing:
            paths, _ = QFileDialog.getOpenFileNames(self.window,
                "원본 재연결 · " + getattr(self.window, name).label.text(), "", "Excel (*.xlsx)")
            if not paths:
                return  # No state has been changed.
            if name != "fs_response" and name != "fs_perform" and len(paths) != 1:
                QMessageBox.warning(self.window, "원본 재연결", "이 항목에는 파일 하나를 선택하세요."); return
            updated["ui_state"]["inputs"][name] = PATH_SEPARATOR.join(paths)
        if self.missing_inputs(updated):
            QMessageBox.warning(self.window, "원본 재연결", "아직 찾지 못한 원본 경로가 있습니다."); return
        prepared = prepare_session(updated)
        prepared["exam"].source_files.update({"responses": updated["ui_state"]["inputs"].get("fs_response", ""),
                                              "item_info": updated["ui_state"]["inputs"].get("fs_iteminfo", "")})
        updated["domain"] = encode_domain(prepared["exam"], prepared["perform_data"])
        after(updated)

    def _restore_dialog(self, payload, result_only):
        def done(ok, error):
            if ok:
                self._set_result_only(result_only)
                self.window.statusBar().showMessage(
                    "저장 결과 보기 · 원본 재연결 전에는 재분석·편집을 할 수 없습니다." if result_only else
                    "모든 탭의 저장 작업을 복원했습니다. 원본 재분석은 분석 실행에서 검증합니다.", 12000)
            else:
                QMessageBox.warning(self.window, "복원 실패", str(error))
        self.restore(payload, done)

    def store(self):
        return WorkSessionStore(self.window._ai_material_root_dir() / "work_sessions")

    def _idle(self):
        if self.busy or getattr(self.window, "_ai_worker_active", False):
            raise ValueError("진행 중인 작업이 끝난 뒤 저장·불러오기를 실행하세요.")

    def _get_project(self, callback):
        w = self.window
        if w.spliter_view is None or not w._spliter_loaded:
            if not w._create_spliter_view():
                callback(copy.deepcopy(w._spliter_pending_project_payload or self._cached_project), None)
                return
            w._ensure_spliter_tab_loaded()
            attempts = [0]
            def ready():
                if w._spliter_loaded:
                    self._get_project(callback)
                elif attempts[0] < 100:
                    attempts[0] += 1
                    QTimer.singleShot(100, ready)
                else:
                    callback(None, ValueError("계산기 준비가 끝나지 않아 작업을 변경하지 않았습니다."))
            QTimer.singleShot(100, ready)
            return
        done = [False]
        def finish(raw):
            if done[0]:
                return
            done[0] = True
            try:
                if not isinstance(raw, str):
                    raise ValueError("계산기 편집 상태를 읽지 못했습니다.")
                project = json.loads(raw)
            except (ValueError, TypeError) as exc:
                callback(None, exc)
                return
            callback(project, None)
        w.spliter_view.page().runJavaScript(
            "typeof window.__GOEDUSPLIT_GET_PROJECT__ === 'function' ? JSON.stringify(window.__GOEDUSPLIT_GET_PROJECT__()) : null", finish)
        QTimer.singleShot(5000, lambda: finish(None) if not done[0] else None)

    def capture(self, callback):
        try:
            self._idle()
            if self.window.exam is None:
                raise ValueError("먼저 분석을 실행하세요.")
            self.busy = True
            state = capture_ui_state(self.window)
            # Domain/UI are captured together; disable interaction until JS answers.
            self._lock(True)
            exam, perform = copy.deepcopy(self.window.exam), copy.deepcopy(self.window.perform_data)
        except Exception as exc:
            callback(None, exc)
            return
        def finish(project, error):
            self.busy = False
            self._lock(False)
            if error:
                callback(None, error)
                return
            try:
                _validate_ui(self.window, state)
                payload = build_session(exam, perform, state, project,
                                        {"subject": exam.subject, "round": self.window.cmb_round.currentText()})
            except Exception as exc:
                callback(None, exc)
                return
            callback(payload, None)
        self._get_project(finish)

    def restore(self, payload, callback):
        try:
            self._idle()
            prepared = prepare_session(payload)
            _validate_ui(self.window, prepared["ui_state"])
        except Exception as exc:
            callback(False, exc)
            return
        self.busy = True
        self._lock(True)
        def old_ready(old_project, error):
            if error:
                finish(False, error)
                return
            def commit():
                try:
                    apply_python_state(self.window, prepared)
                    self._cached_project = copy.deepcopy(prepared["calculator_project"])
                    self.window._spliter_pending_payload = None
                    if not self.window._spliter_loaded:
                        self.window._spliter_pending_project_payload = copy.deepcopy(prepared["calculator_project"])
                    self.last_saved_signature = signature(payload)
                    finish(True, None)
                except Exception as exc:
                    if old_project is not None and self.window._spliter_loaded:
                        self._post_project(old_project)
                    finish(False, exc)
            project = prepared["calculator_project"]
            if self.window._spliter_loaded:
                if project is None:
                    project = {"judges": [{"id": "teacher-1", "name": "검토안 1"},
                                          {"id": "teacher-2", "name": "검토안 2"}],
                               "activeJudgeId": "teacher-1", "items": [], "selectedId": "", "selectedIds": [],
                               "evidenceData": None, "evidenceMode": "difficultyAverage"}
                self._post_project(project)
                attempts = [0]
                def verify():
                    self._get_project(checked)
                def checked(actual, error):
                    if not error and actual == project:
                        commit()
                    elif attempts[0] < 12:
                        attempts[0] += 1
                        QTimer.singleShot(100, verify)
                    else:
                        if old_project is not None:
                            self._post_project(old_project)
                        finish(False, ValueError("계산기 편집 상태 복원을 확인하지 못해 기존 작업을 유지했습니다."))
                QTimer.singleShot(80, verify)
            else:
                commit()
        def finish(ok, error):
            self.busy = False
            self._lock(False)
            callback(ok, error)
        self._get_project(old_ready)

    def _post_project(self, project):
        raw = json.dumps(project, ensure_ascii=False)
        self.window.spliter_view.page().runJavaScript(
            f"window.__GOEDUSPLIT_PROJECT__={raw};window.postMessage({{type:'goedusplit-project',payload:window.__GOEDUSPLIT_PROJECT__}}, '*');")

    def save_dialog(self, after=None):
        if self.result_only:
            QMessageBox.information(self.window, "결과 보기 전용", "원본을 재연결한 다음 전체 작업을 저장하세요.")
            return
        def captured(payload, error):
            if error:
                QMessageBox.warning(self.window, "작업 저장", str(error)); return
            name, ok = QInputDialog.getText(self.window, "전체 작업 저장 · 이 PC에만 저장",
                "학생 이름·학번·응답과 모든 탭 편집 상태를 포함합니다.\n원본 파일은 복제하지 않습니다.\n기록 이름:",
                text=f"{self.window.exam.subject} {self.window.cmb_round.currentText()}".strip())
            if not ok:
                return
            payload["metadata"]["name"] = name.strip() or "전체 작업"
            def save():
                try:
                    path = self.store().save(payload)
                    self.last_saved_signature = signature(payload)
                    self.window.statusBar().showMessage(f"전체 작업 저장 완료 · {path.name} · 이전 저장 보존", 8000)
                    if after:
                        after()
                except Exception:
                    result = QMessageBox.warning(self.window, "저장 실패", "저장하지 못했습니다. 현재 분석과 기존 기록은 유지됩니다.",
                                                 QMessageBox.Retry | QMessageBox.Cancel)
                    if result == QMessageBox.Retry:
                        save()
            save()
        self.capture(captured)

    def open_dialog(self):
        try:
            self._idle()
            entries = self.store().list_sessions()
        except Exception as exc:
            QMessageBox.warning(self.window, "작업 불러오기", str(exc)); return
        dialog = QDialog(self.window); dialog.setWindowTitle("저장한 회차 작업 불러오기"); dialog.resize(640, 400)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("전체 작업은 모든 탭을 복원합니다. 기존 자동 회차 기록은 요약 보기만 가능합니다."))
        listing = QListWidget(); layout.addWidget(listing, 1)
        for entry in entries:
            meta = entry["metadata"]
            listing.addItem(f"전체 작업 · {meta.get('name', meta.get('subject', ''))} · {entry['saved_at']}")
        legacy = self.window._round_store().load_all()
        for record in legacy:
            listing.addItem(f"요약 전용 · {record.get('subject', '')} · {record.get('label', '')}")
        row = QHBoxLayout(); button = QPushButton("선택 기록 열기"); cancel = QPushButton("취소")
        row.addWidget(button); row.addWidget(cancel); layout.addLayout(row); cancel.clicked.connect(dialog.reject)
        def chosen():
            index = listing.currentRow()
            if index < 0:
                return
            if index >= len(entries):
                record = legacy[index - len(entries)]
                QMessageBox.information(dialog, "요약 전용 기록", f"{record.get('label', '')}\n"
                    f"학생 수 {record.get('n_students', '')} · 평균 {record.get('mean', '')}\n"
                    "원본 응답·편집 상태가 없어 전체 작업을 복원하지 않습니다. 현재 작업은 그대로입니다.")
                return
            try:
                payload = self.store().read(entries[index]["path"])
                prepare_session(payload)
            except Exception as exc:
                QMessageBox.warning(dialog, "불러오기 실패", str(exc)); return
            dialog.accept()
            def load():
                missing = self.missing_inputs(payload)
                if not missing:
                    self._restore_dialog(payload, False); return
                box = QMessageBox(self.window); box.setWindowTitle("원본 파일 경로 누락")
                box.setText("저장한 작업의 원본 경로를 찾지 못했습니다.\n저장 결과는 원본 없이 볼 수 있습니다.\n"
                            "원본 파일은 복제하지 않았습니다.")
                results = box.addButton("저장 결과만 보기", QMessageBox.AcceptRole)
                reconnect = box.addButton("원본 재연결", QMessageBox.ActionRole)
                box.addButton("취소", QMessageBox.RejectRole); box.exec()
                if box.clickedButton() is results:
                    self._restore_dialog(payload, True)
                elif box.clickedButton() is reconnect:
                    self._reconnect(payload, lambda updated: self._restore_dialog(updated, False))
            if self.window.exam is None:
                load(); return
            def inspected(current, error):
                if error:
                    QMessageBox.warning(self.window, "작업 확인", str(error)); return
                if signature(current) == self.last_saved_signature:
                    load(); return
                box = QMessageBox(self.window); box.setWindowTitle("현재 작업 보존")
                box.setText("저장하지 않은 변경이 있을 수 있습니다. 현재 작업을 저장한 뒤 불러올까요?")
                save = box.addButton("저장 후 불러오기", QMessageBox.AcceptRole)
                discard = box.addButton("저장하지 않고 불러오기", QMessageBox.DestructiveRole)
                box.addButton("취소", QMessageBox.RejectRole); box.exec()
                if box.clickedButton() is save:
                    self.save_dialog(load)
                elif box.clickedButton() is discard:
                    load()
            self.capture(inspected)
        button.clicked.connect(chosen); dialog.exec()


def install_work_sessions(window):
    controller = WorkSessionController(window)
    window.work_sessions = controller
    for tab in (window.tab_rounds, window.tab_portfolio):
        row = QHBoxLayout()
        save = QPushButton("전체 작업 저장")
        load = QPushButton("저장한 회차 불러오기")
        reconnect = QPushButton("원본 재연결")
        reconnect.setEnabled(False)
        reconnect.clicked.connect(controller.reconnect_dialog)
        controller.reconnect_buttons.append(reconnect)
        save.clicked.connect(lambda _checked=False: controller.save_dialog())
        load.clicked.connect(controller.open_dialog)
        row.addWidget(save); row.addWidget(load); row.addWidget(reconnect); row.addStretch(1)
        tab.layout().insertLayout(0, row)
    return controller
