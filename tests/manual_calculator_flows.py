"""Opt-in, synthetic-only QtWebEngine checks for calculator flows that unit tests cannot reach.

Run from the repository with its existing Qt environment:
    .venv/bin/python tests/manual_calculator_flows.py --run

Checks, on the real embedded calculator:
1. The calculator's untouched example items are recognised as such.
2. With an analysis done before the calculator tab opens (the usual order), loading a
   saved work file without evidence by a real mouse click keeps the calculator alive
   (no React "removeChild" crash) and the prediction-vs-actual comparison opens.
It never attaches to a running app and uses an off-the-record browser profile.
"""

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch


def _judgments(rates):
    return {"j1": {lv: {"correct": [True, True, False], "targetRate": r, "overrideRate": r} for lv, r in zip("ABCDE", rates)}}


def saved_work_file(folder: Path) -> Path:
    project = {
        "version": 1, "judges": [{"id": "j1", "name": "검토안 1"}], "activeJudgeId": "j1",
        "evidenceMode": "difficultyAverage", "evidenceData": None,
        "items": [
            {"id": f"i{n}", "number": n, "title": f"선택형 {n}번", "type": "선택형", "difficulty": d, "targetLevel": "C",
             "points": 40, "sampleSize": 3, "standard": "", "note": "", "evidence": [], "judgmentsByJudge": _judgments(r)}
            for n, d, r in ((1, "쉬움", (90, 80, 70, 60, 50)), (2, "어려움", (80, 60, 40, 20, 10)))
        ],
    }
    path = folder / "시험전작업.json"
    path.write_text(json.dumps(project, ensure_ascii=False), encoding="utf-8")
    return path


def run() -> int:
    scratch = Path(tempfile.mkdtemp(prefix="goedusplit-calculator-flows-"))
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-gpu --disable-gpu-compositing"
    os.environ["MPLCONFIGDIR"] = str(scratch / "matplotlib")
    sys.path[:0] = [str(Path(__file__).resolve().parents[1]), str(Path(__file__).resolve().parent)]
    from PySide6.QtCore import QPoint, QSettings, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
    from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QTableWidget
    from app.analysis import analyze_items, analyze_overall, build_score_matrix
    from app.main_window import MainWindow
    from test_calibration import _exam

    app = QApplication([])
    profile = QWebEngineProfile(app)
    chosen, problems, dialogs = [str(saved_work_file(scratch))], [], []

    class Page(QWebEnginePage):
        def chooseFiles(self, mode, old, accepted):
            return chosen

        def javaScriptAlert(self, origin, message):
            problems.append("alert: " + message)

        def javaScriptConsoleMessage(self, level, message, line, source):
            if "rror" in message:
                problems.append(message)

    def fake_exec(dialog):
        tables = dialog.findChildren(QTableWidget)
        dialogs.append((dialog.windowTitle(), max((t.rowCount() for t in tables), default=0)))
        return 0

    def wait(condition, seconds):
        end = time.monotonic() + seconds
        while not condition() and time.monotonic() < end:
            QTest.qWait(50)

    def js(window, expression):
        out = []
        window.spliter_view.page().runJavaScript(f"JSON.stringify({expression})", out.append)
        wait(lambda: out, 5)
        return json.loads(out[0]) if out and out[0] else None

    results = {}
    with patch("app.main_window.QSettings", return_value=QSettings(str(scratch / "settings.ini"), QSettings.IniFormat)), \
         patch("app.main_window.QWebEnginePage", side_effect=lambda parent: Page(profile, parent)), \
         patch.object(QDialog, "exec", fake_exec), \
         patch.object(QMessageBox, "information", side_effect=lambda *a, **k: problems.append("info: " + a[2])), \
         patch.object(QMessageBox, "question", side_effect=lambda *a, **k: problems.append("question: " + a[2]) or QMessageBox.No):
        probe = MainWindow()
        probe.show()
        probe.tabs.setCurrentWidget(probe.tab_spliter)
        wait(lambda: probe._spliter_loaded, 30)
        QTest.qWait(1500)
        fetched = []
        probe._fetch_spliter_project(fetched.append)
        wait(lambda: fetched, 10)
        results["untouched calculator is recognised as example"] = MainWindow._is_sample_calculator_project(fetched[0])
        probe.close()
        QTest.qWait(1300)

        window = MainWindow()
        window.exam, levels = _exam()  # analysis first, as in run_analysis before opening the tab
        score, _, _ = build_score_matrix(window.exam)
        window.overall = analyze_overall(window.exam, score)
        window.overall.levels_arr = levels
        window.item_stats = analyze_items(window.exam)[0]
        window._spliter_pending_payload = window._build_spliter_evidence_payload()
        window.show()
        window.resize(1440, 900)
        window.tabs.setCurrentWidget(window.tab_spliter)
        wait(lambda: window._spliter_loaded, 30)
        QTest.qWait(1500)
        window.send_spliter_evidence_to_web()
        QTest.qWait(2000)
        center = js(window, "(() => { const r = document.querySelector('button.goedu-file-action[title=\"작업 불러오기\"]').getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; })()")
        target = window.spliter_view.focusProxy() or window.spliter_view
        target.setFocus()
        QTest.mouseClick(target, Qt.LeftButton, pos=QPoint(round(center[0]), round(center[1])))
        QTest.qWait(2500)
        fetched.clear()
        window._fetch_spliter_project(fetched.append)
        wait(lambda: fetched, 10)
        titles = [item.get("title") for item in (fetched[0] or {}).get("items", [])]
        results["saved work loads after evidence was shown"] = titles == ["선택형 1번", "선택형 2번"]
        window.show_calibration_report()
        QTest.qWait(1500)
        results["comparison opens with loaded items"] = ("예측-실측 비교", 3) in dialogs
        results["no calculator errors or alerts"] = not problems
        window.close()
        QTest.qWait(1300)

    for name, ok in results.items():
        print(("passed  " if ok else "FAILED  ") + name, flush=True)
    for problem in problems:
        print("  " + problem[:200], flush=True)
    return 0 if all(results.values()) else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", action="store_true", help="Run the isolated native WebEngine checks")
    if not parser.parse_args().run:
        parser.error("--run is required; no Qt instance has been started")
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
