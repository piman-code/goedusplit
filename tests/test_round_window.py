from tests.runtime_isolation import ensure_isolated
ensure_isolated()

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import json
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from app import rounds
from app.main_window import MainWindow

try:
    from test_calibration import _exam
except ModuleNotFoundError:  # run as tests.test_round_window
    from tests.test_calibration import _exam


class RoundWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.resources = ExitStack()
        self.addCleanup(self.resources.close)
        self.tmp = Path(self.resources.enter_context(tempfile.TemporaryDirectory()))
        settings = QSettings(str(self.tmp / "settings.ini"), QSettings.IniFormat)
        self.resources.enter_context(patch("app.main_window.QSettings", return_value=settings))
        self.resources.enter_context(patch("app.main_window.QWebEngineView", None))
        self.resources.enter_context(patch.object(MainWindow, "_ai_material_root_dir", lambda _self: self.tmp / "appdata"))
        self.resources.enter_context(patch.object(QMessageBox, "information"))
        self.resources.enter_context(patch.object(QMessageBox, "warning"))
        self.window = MainWindow()
        self.addCleanup(self.window.close)

    def analyze(self, response="1학기 1차 정오표(1-1).xlsx", mean_shift=0.0, cuts=""):
        exam, _levels = _exam()
        for student in exam.students:
            student.final_score = student.total = student.final_score + mean_shift
        with patch("app.main_window.load_exam", return_value=exam):
            self.window.fs_response.path_edit.setText("/합성/" + response)
            self.window.fs_iteminfo.path_edit.setText("/합성/문항정보표.xlsx")
            self.window.fs_cuts.path_edit.setText(("/합성/" + cuts) if cuts else "")
            self.window.run_analysis()
        self.app.processEvents()

    def records(self):
        return rounds.RoundStore(self.tmp / "appdata" / "round_history").load_all()

    def test_every_analysis_leaves_one_record_per_round_without_names(self):
        self.analyze("1학기 1차 정오표(1-1).xlsx")
        self.analyze("1학기 1차 정오표(1-1).xlsx", mean_shift=1.0)     # same round again: replaced, not added
        self.analyze("1학기 2차 정오표(1-1).xlsx", mean_shift=-3.0)
        records = self.records()
        self.assertEqual(["1학기 1차", "1학기 2차"], [rounds.round_name(r["semester_no"], r["round_no"]) for r in records])
        text = json.dumps(records, ensure_ascii=False)
        for forbidden in ("합성0", "합성반0", '"S0"'):
            self.assertNotIn(forbidden, text)                          # hashes only, never names or ids
        self.assertEqual(6, len(records[0]["students"]))
        self.assertGreater(records[0]["mean"], records[1]["mean"] - 3.5)   # the latest 1차 analysis is the one kept
        self.assertTrue((self.tmp / "appdata" / "round_history").is_dir())
        self.assertEqual([], list((self.tmp / "appdata" / "subject_snapshots").glob("*.json")))   # the portfolio is untouched

    def test_manual_round_overrides_the_file_name(self):
        self.window.cmb_round.setEditText("2학기 2차")
        self.analyze("1학기 1차 정오표(1-1).xlsx")
        self.assertEqual([(2, 2)], [(r["semester_no"], r["round_no"]) for r in self.records()])

    def test_hint_warns_when_files_belong_to_different_exams(self):
        self.analyze("1차 정오표(1-1).xlsx", cuts="예상추정분할점수조회 2차.xlsx")
        hint = self.window.lbl_round_hint.text()
        self.assertIn("기록 이름: 1차", hint)
        self.assertIn("분할점수 파일은 2차용", hint)
        self.analyze("1차 정오표(1-1).xlsx", cuts="예상추정분할점수조회 1차.xlsx")
        self.assertNotIn("⚠", self.window.lbl_round_hint.text())

    def test_folder_batch_matches_the_exam_round_of_the_answer_sheet(self):
        folder = self.tmp / "자료"
        folder.mkdir()
        names = {"1차 정기시험 교과목별 학생답 정오표(1-1).xlsx": 3000, "2차 정기시험 교과목별 학생답 정오표(1-1).xlsx": 1000,
                 "1차 정기시험 교과목별 일람표(공통수학1).xlsx": 1500, "2차 정기시험 교과목별 일람표(공통수학1).xlsx": 2500,
                 "예상추정분할점수조회(공통수학1)1학기 1차.xlsx": 1200, "예상추정분할점수조회(공통수학1)1학기 2차.xlsx": 2200,
                 "문항정보표(공통수학1) 샘플.xlsx": 100}
        for name, mtime in names.items():
            (folder / name).write_bytes(b"")
            os.utime(folder / name, (mtime, mtime))
        with patch.object(QFileDialog, "getExistingDirectory", return_value=str(folder)):
            self.window._pick_folder_batch()
        self.assertIn("1차 정기시험 교과목별 학생답 정오표", self.window.fs_response.path())
        self.assertIn("1차 정기시험 교과목별 일람표", self.window.fs_grade5_report.path())    # not the newer 2차 file
        self.assertIn("1학기 1차", self.window.fs_cuts.path())
        self.assertNotIn("⚠", self.window.lbl_round_hint.text())

    def test_compare_tab_and_monitor_trend_use_the_saved_rounds(self):
        self.analyze("1학기 1차 정오표(1-1).xlsx")
        self.assertIn("아직 1개", self.window.lbl_round_status.text())                       # one round: nothing to compare
        self.analyze("1학기 2차 정오표(1-1).xlsx", mean_shift=5.0)
        window = self.window
        self.assertEqual(2, window.cmb_round_base.count())
        self.assertEqual("1학기 1차", window.cmb_round_base.currentText().split(" (")[0])
        self.assertEqual("1학기 2차", window.cmb_round_other.currentText().split(" (")[0])
        metrics = {window.table_round_metrics.item(r, 0).text(): window.table_round_metrics.item(r, 3).text()
                   for r in range(window.table_round_metrics.rowCount())}
        self.assertEqual("+5", metrics["평균(점)"])
        self.assertIn("같은 학생 6명", window.lbl_round_moves.text())
        self.assertGreaterEqual(window.table_round_moves.rowCount(), 5)
        self.assertIsNotNone(window.canvas_monitor_trend._canvas)
        window.cmb_round_other.setCurrentIndex(0)                                          # same round on both sides
        self.assertIn("서로 다른 회차", window.lbl_round_status.text())

    def test_previous_year_values_fill_the_monitor_inputs(self):
        store = rounds.RoundStore(self.tmp / "appdata" / "round_history")
        old = rounds.build_record(subject="합성", grade="", year=2025, semester=1, round_no=1, n_students=6, mean=61.5,
                                  std=9.0, level_pct={"A": 18.5, "B": 20.0}, level_n={}, cuts={"A": 83.0}, students={})
        store.save(old)
        self.analyze("1학기 1차 정오표(1-1).xlsx")
        self.window.exam.semester = "2026학년도 1학기"
        self.window._fill_monitor_prev_year()
        self.assertEqual(18.5, self.window._monitor_value("prev_a_pct"))
        self.assertEqual(61.5, self.window._monitor_value("prev_mean"))
        self.assertEqual(83.0, self.window._monitor_value("prev_cut_a"))


if __name__ == "__main__":
    unittest.main()
