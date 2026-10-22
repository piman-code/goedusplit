"""Opt-in screen audit: open every result tab under several window sizes, themes and zooms with
synthetic data, and measure what tests do not see - areas drawn over each other, clipped table
cells, headers and buttons, tables that do not fill their width, chart labels drawn over each
other or cut at the figure edge, and widths frozen by a restore.

Run: .venv/bin/python -B tests/manual_screen_audit.py --run --output <new folder>
Output: SCREEN_AUDIT.json, ISSUES.md and captures/. Exit code 1 when an issue is found.
No student input, normal settings, installed app or network is used (offscreen, isolated).

The measuring functions (``splitter_issues``, ``table_issues``, ``button_issues``,
``chart_issues``) only take Qt widgets, so other PySide projects can reuse them.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from unittest.mock import patch

try:
    from tests.runtime_isolation import ensure_isolated
except ModuleNotFoundError:
    from runtime_isolation import ensure_isolated

SIZES = ((1312, 810), (1100, 700), (1700, 1300))
THEMES = ("light", "dark")
ZOOMS = (100, 120)
CAPTURE_SIZE = (1312, 810)   # every tab is captured at this size; other conditions only when an issue appears
OVERLAP_SHARE = 0.25         # chart texts overlap when they share this much of the smaller box


def _issue(kind, where, detail):
    return {"kind": kind, "where": where, "detail": detail}


def splitter_issues(root, name_of=lambda w: type(w).__name__):
    """Areas a splitter gives less room than their minimum: Qt then paints them over each other
    and under the handle (the monitoring/performance tab bug)."""
    from PySide6.QtWidgets import QSplitter
    issues = []
    for splitter in root.findChildren(QSplitter):
        if not splitter.isVisible():
            continue
        vertical = splitter.orientation().name == "Vertical"
        sizes = splitter.sizes()
        for index in range(splitter.count()):
            area = splitter.widget(index)
            if area is None or not area.isVisible():
                continue
            # Like Qt layouts: an explicit minimum wins over the widget's own hint.
            explicit = area.minimumHeight() if vertical else area.minimumWidth()
            hint = area.minimumSizeHint().height() if vertical else area.minimumSizeHint().width()
            need = explicit if explicit > 0 else max(0, hint)
            if sizes[index] + 1 < need:
                issues.append(_issue("칸 겹침", name_of(splitter),
                                     f"{index + 1}번째 칸 {sizes[index]}px < 최소 {need}px"))
    return issues


def table_issues(table, name, max_rows=60):
    """Cells and headers narrower than their text, and fitted tables that leave the right side empty."""
    issues = []
    if not table.isVisible() or table.columnCount() == 0:
        return issues
    header = table.horizontalHeader()
    model = table.model()
    clipped = []
    for c in range(table.columnCount()):
        if table.isColumnHidden(c):
            continue
        width = table.columnWidth(c)
        title = table.horizontalHeaderItem(c).text().replace("\n", " ") if table.horizontalHeaderItem(c) else str(c)
        # The header's own size hint reserves room for a sort arrow; measure the text itself.
        need = header.fontMetrics().horizontalAdvance(title) + 8
        if header.isVisible() and need > width + 1:
            issues.append(_issue("머리글 잘림", name, f"'{title}' 열 {width}px < 글자 {need}px"))
        if table.wordWrap():
            continue  # wrapped text grows downwards; widths alone do not say it is cut
        worst = 0
        for r in range(min(table.rowCount(), max_rows)):
            if table.isRowHidden(r):
                continue
            index = model.index(r, c)
            if not str(model.data(index) or "").strip():
                continue
            worst = max(worst, table.sizeHintForIndex(index).width())
        if worst > width + 1:
            clipped.append(f"'{title}' {width}px < {worst}px")
    if clipped:
        issues.append(_issue("표 글자 잘림", name, ", ".join(clipped)))
    control = getattr(table, "_column_controls", None)
    if control is not None and control.fills() and not control.user_sized:
        total = sum(table.columnWidth(c) for c in range(table.columnCount()) if not table.isColumnHidden(c))
        spare = table.viewport().width() - total
        if spare > 4:
            issues.append(_issue("표 쏠림", name, f"오른쪽 {spare}px 빈칸 (열 합 {total}px)"))
    return issues


def button_issues(root, name_of=lambda w: type(w).__name__):
    """Buttons narrower than their own label and icon."""
    from PySide6.QtWidgets import QAbstractButton, QTableView
    issues = []
    for button in root.findChildren(QAbstractButton):
        if not button.isVisible() or not button.text().strip():
            continue
        parent = button.parentWidget()
        while parent is not None and not isinstance(parent, QTableView):
            parent = parent.parentWidget()
        if parent is not None:
            continue  # header and corner buttons of tables are not labels
        need = button.sizeHint().width()
        if button.width() + 4 < need:  # a few pixels of style padding do not cut the label
            issues.append(_issue("버튼 글자 잘림", name_of(button),
                                 f"'{button.text()}' {button.width()}px < {need}px"))
    return issues


def _chart_texts(figure):
    texts = []
    for ax in figure.axes:
        if not ax.get_visible():
            continue
        texts += [("값", t) for t in ax.texts]
        texts += [("제목", ax.title), ("축 이름", ax.xaxis.label), ("축 이름", ax.yaxis.label)]
        for axis, (low, high) in ((ax.xaxis, sorted(ax.get_xlim())), (ax.yaxis, sorted(ax.get_ylim()))):
            # Labels of ticks outside the view are returned but never drawn.
            texts += [("눈금", label) for loc, label in zip(axis.get_ticklocs(), axis.get_ticklabels())
                      if low - 1e-9 <= loc <= high + 1e-9]
        legend = ax.get_legend()
        if legend is not None and legend.get_visible():
            texts += [("범례", t) for t in legend.get_texts()]
    texts += [("제목", t) for t in figure.texts]
    if getattr(figure, "_suptitle", None) is not None:
        texts.append(("제목", figure._suptitle))
    unique, seen = [], set()
    for kind, t in texts:
        if id(t) not in seen and t.get_visible() and t.get_text().strip():
            seen.add(id(t)); unique.append((kind, t))
    return unique


def chart_issues(holder, name):
    """Chart texts drawn over each other or cut at the figure edge."""
    canvas = getattr(holder, "_canvas", None)
    if canvas is None or not holder.isVisible():
        return []
    figure = canvas.figure
    canvas.draw()
    renderer = canvas.get_renderer()
    boxes = [(kind, t.get_text().replace("\n", " "), t.get_window_extent(renderer)) for kind, t in _chart_texts(figure)]
    width, height = figure.bbox.width, figure.bbox.height
    issues = []
    for kind, text, box in boxes:
        if box.x0 < -1 or box.y0 < -1 or box.x1 > width + 1 or box.y1 > height + 1:
            issues.append(_issue("그래프 글자 잘림", name, f"{kind} '{text}'가 그림 밖으로 나감"))
    seen, pairs = set(), []
    for i, (kind_a, text_a, a) in enumerate(boxes):
        for kind_b, text_b, b in boxes[i + 1:]:
            w = min(a.x1, b.x1) - max(a.x0, b.x0)
            h = min(a.y1, b.y1) - max(a.y0, b.y0)
            if w <= 0 or h <= 0:
                continue
            smaller = min(a.width * a.height, b.width * b.height) or 1
            if w * h / smaller >= OVERLAP_SHARE:
                key = tuple(sorted((text_a, text_b)))
                if key not in seen:
                    seen.add(key)
                    pairs.append(f"{kind_a} '{text_a}' ↔ {kind_b} '{text_b}'")
    if pairs:
        more = f" 외 {len(pairs) - 4}쌍" if len(pairs) > 4 else ""
        issues.append(_issue("그래프 글자 겹침", name, f"{len(pairs)}쌍: " + "; ".join(pairs[:4]) + more))
    return issues


def run(output):
    ensure_isolated()
    from PySide6.QtCore import QCoreApplication, QEvent, QSettings
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QMessageBox, QTableWidget
    import app.main_window as ui
    from app.synthetic_qa import analysis_fixtures
    from app.theme import ThemeManager
    from app.work_session_ui import apply_python_state, capture_ui_state
    from app.work_sessions import build_session, prepare_session

    output = Path(output).absolute()
    if output.exists():
        raise SystemExit("Output folder already exists; pass a new path.")
    output.mkdir(parents=True)
    captures = output / "captures"
    captures.mkdir()
    inputs = output / "inputs"
    inputs.mkdir()
    item, responses, perform = analysis_fixtures(inputs)
    application = QApplication.instance() or QApplication([])
    settings = QSettings(str(output / "settings.ini"), QSettings.IniFormat)
    settings.setFallbacksEnabled(False)
    report = {"status": "incomplete", "input": "synthetic only", "conditions": [], "issues": []}

    with patch.object(ui, "QSettings", return_value=settings), \
         patch.object(ui, "QWebEngineView", None), \
         patch.object(ui.MainWindow, "_ai_material_root_dir", lambda _self: output / "appdata"), \
         patch.object(QMessageBox, "information"), patch.object(QMessageBox, "warning"), \
         patch.object(QMessageBox, "critical"):
        theme = ThemeManager(application)
        theme.set_mode("light")
        window = ui.MainWindow(theme_manager=theme)
        names = {id(value): key for key, value in vars(window).items() if hasattr(value, "metaObject")}
        name_of = lambda widget: names.get(id(widget), type(widget).__name__)
        try:
            window.resize(*CAPTURE_SIZE)
            window.show()
            QTest.qWait(300)
            window.fs_iteminfo.path_edit.setText(str(item))
            window.fs_response.path_edit.setText(ui.PATH_SEPARATOR.join(map(str, responses[1])))
            window.fs_perform.path_edit.setText(ui.PATH_SEPARATOR.join(map(str, perform)))
            window.chk_perform.setChecked(True)
            window.run_analysis()
            QTest.qWait(300)
            window.fs_response.path_edit.setText(ui.PATH_SEPARATOR.join(map(str, responses[2])))
            window.run_analysis()
            QTest.qWait(300)
            # Folder batch analysis and saved work go through capture -> apply; widths the teacher
            # never set must not come back as fixed widths.
            window.tabs.setCurrentWidget(window.tab_data)
            state = capture_ui_state(window)
            apply_python_state(window, prepare_session(build_session(window.exam, window.perform_data, state, None)))
            QTest.qWait(300)
            for table in window.findChildren(QTableWidget):
                control = getattr(table, "_column_controls", None)
                if control is not None and control.fills() and control.manual:
                    report["issues"].append({"condition": "작업 다시 적용 직후", "tab": "-",
                                             **_issue("너비 고정", name_of(table), "직접 조절하지 않은 표가 고정 너비가 됨")})
            tabs = [(window.tabs.tabText(i), window.tabs.widget(i)) for i in range(window.tabs.count())
                    if window.tabs.widget(i) is not getattr(window, "tab_spliter", None)]
            for size in SIZES:
                for mode in THEMES:
                    for zoom in ZOOMS:
                        condition = f"{size[0]}x{size[1]} {'밝은' if mode == 'light' else '어두운'} {zoom}%"
                        report["conditions"].append(condition)
                        theme.set_mode(mode)
                        window._set_zoom(zoom)
                        window.resize(*size)
                        QTest.qWait(150)
                        for label, tab in tabs:
                            window.tabs.setCurrentWidget(tab)
                            QTest.qWait(250)
                            found = splitter_issues(tab, name_of) + button_issues(tab, name_of)
                            for table in tab.findChildren(QTableWidget):
                                found += table_issues(table, name_of(table))
                            for holder in tab.findChildren(ui.CanvasHolder):
                                found += chart_issues(holder, name_of(holder))
                            for issue in found:
                                report["issues"].append({"condition": condition, "tab": label, **issue})
                            if size == CAPTURE_SIZE and zoom == 100 or found:
                                safe = "".join(ch if ch.isalnum() else "_" for ch in f"{condition}_{label}")
                                window.grab().save(str(captures / f"{safe}.png"))
            report["status"] = "issues-found" if report["issues"] else "passed"
        finally:
            window.close()
            window.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
            application.processEvents()

    (output / "SCREEN_AUDIT.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "ISSUES.md").write_text(_summary(report), encoding="utf-8")
    counts = defaultdict(int)
    for issue in report["issues"]:
        counts[issue["kind"]] += 1
    print(json.dumps({"status": report["status"], "conditions": len(report["conditions"]),
                      "issues": len(report["issues"]), "by_kind": counts}, ensure_ascii=False), flush=True)
    return 0 if report["status"] == "passed" else 1


def _summary(report):
    """One line per distinct problem with the conditions it appeared in."""
    grouped = defaultdict(list)
    for issue in report["issues"]:
        grouped[(issue["kind"], issue["tab"], issue["where"], issue["detail"])].append(issue["condition"])
    lines = ["# 화면 점검 결과", "", f"- 상태: {report['status']}",
             f"- 조건 {len(report['conditions'])}개: " + ", ".join(report["conditions"]),
             f"- 문제 {len(grouped)}종 (조건별 {len(report['issues'])}건)", ""]
    for kind in sorted({key[0] for key in grouped}):
        lines += [f"## {kind}", ""]
        for (k, tab, where, detail), conditions in sorted(grouped.items()):
            if k == kind:
                lines.append(f"- [{tab}] `{where}` — {detail} ({len(conditions)}개 조건: {', '.join(conditions[:3])}{' …' if len(conditions) > 3 else ''})")
        lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.run:
        parser.error("--run is required")
    return run(args.output)


if __name__ == "__main__":
    raise SystemExit(main())
