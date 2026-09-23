import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.calibration import borderline_indices, build_calibration, summary_lines, write_calibration_workbook
from app.data_loader import ExamData, ItemInfo, StudentResponse

try:
    from app.main_window import MainWindow
except ModuleNotFoundError:
    MainWindow = None


def _exam():
    """6 synthetic students: A has 3 (scores 95, 90, 85), C has 3 (70, 65, 60)."""
    exam = ExamData(subject="합성")
    exam.items = [
        ItemInfo(number=1, item_type="선택형", difficulty="쉬움", score=40.0, answer="1"),
        ItemInfo(number=2, item_type="선택형", difficulty="어려움", score=40.0, answer="2"),
        ItemInfo(number=1, item_type="서답형", difficulty="보통", score=20.0),
    ]
    data = [  # (final score, item1, item2, serdap score)
        (95, ".", ".", 20), (90, ".", ".", 16), (85, ".", "3", 10),
        (70, ".", "3", 10), (65, "2", "3", 8), (60, "2", "3", 0),
    ]
    for i, (score, a1, a2, serdap) in enumerate(data):
        exam.students.append(StudentResponse(
            sid=f"S{i}", class_no=f"합성반{i}", name=f"합성{i}", answers={1: a1, 2: a2},
            serdap_score=serdap, total=score, final_score=score,
        ))
    return exam, ["A", "A", "A", "C", "C", "C"]


def _design(kind, number, difficulty, points, rates, item):
    return {"type": kind, "number": number, "difficulty": difficulty, "target": "C", "points": points,
            "rates": dict(zip("ABCDE", rates)), "source_item": item}


class CalibrationTests(unittest.TestCase):
    def test_borderline_is_lowest_third_of_each_level(self):
        scores = [95, 90, 85, 70, 65, 60, 50]
        levels = ["A", "A", "A", "C", "C", "C", "C"]
        self.assertEqual(borderline_indices(scores, levels), {"A": [2], "C": [6, 5]})

    def test_item_rates_diffs_bias_and_cuts(self):
        exam, levels = _exam()
        item1, item2, serdap = exam.items
        designs = [
            _design("선택형", 1, "쉬움", 40.0, (90, 80, 70, 60, 50), item1),
            _design("선택형", 2, "어려움", 40.0, (80, 60, 40, 20, 10), item2),
            _design("서답형", 1, "보통", 20.0, (70, 60, 50, 40, 30), serdap),
        ]
        report = build_calibration(designs, exam, levels)
        rows = {(r["type"], r["number"]): r for r in report["rows"]}
        one, two, group = rows[("선택형", "1")], rows[("선택형", "2")], rows[("서답형 묶음", "1")]
        # A 경계 = 85점 학생(1번 정답, 2번 오답, 서답 10/20), C 경계 = 60점 학생(모두 오답, 서답 0)
        self.assertEqual((one["border"]["A"], one["border"]["C"]), (100.0, 0.0))
        self.assertEqual((two["border"]["A"], two["border"]["C"]), (0.0, 0.0))
        self.assertEqual((group["border"]["A"], group["border"]["C"]), (50.0, 0.0))
        self.assertAlmostEqual(one["all"]["C"], 100 / 3)
        self.assertIsNone(one["border"]["B"])
        self.assertEqual((one["diff"]["A"], two["diff"]["A"], group["diff"]["A"]), (10.0, -80.0, -20.0))
        self.assertAlmostEqual(report["bias"]["A"], (10 - 80 - 20) / 3)
        self.assertIsNone(report["bias"]["B"])
        self.assertEqual(report["large_gaps"], 5)  # A: 2번·서답, C: 1번·2번·서답
        cuts = {c["level"]: c for c in report["cuts"]}
        self.assertAlmostEqual(cuts["A"]["predicted_scaled"], (40 * 90 + 40 * 80 + 20 * 70) / 100)
        self.assertAlmostEqual(cuts["A"]["actual_scaled"], (40 * 100 + 40 * 0 + 20 * 50) / 100)
        self.assertIsNone(cuts["B"]["actual_scaled"])
        self.assertEqual(report["counts"], {"A": 3, "B": 0, "C": 3, "D": 0, "E": 0})

    def test_unmatched_and_undesigned_items_are_listed(self):
        exam, levels = _exam()
        designs = [_design("선택형", 1, "쉬움", 40.0, (90, 80, 70, 60, 50), exam.items[0]),
                   _design("선택형", 9, "보통", 10.0, (90, 80, 70, 60, 50), None)]
        report = build_calibration(designs, exam, levels)
        self.assertEqual(report["unmatched"], ["선택형 9번"])
        self.assertEqual(report["not_designed"], ["선택형 2번", "서답형 1번"])
        self.assertEqual(len(report["rows"]), 1)

    def test_summary_wording_follows_sign(self):
        exam, levels = _exam()
        designs = [_design("선택형", 1, "쉬움", 40.0, (50, 50, 90, 50, 50), exam.items[0])]
        lines = summary_lines(build_calibration(designs, exam, levels))
        self.assertIn("50.0%p 낮게", lines[0])   # A 실측 100 vs 예측 50
        self.assertIn("90.0%p 높게", lines[2])   # C 실측 0 vs 예측 90
        self.assertIn("학생 수가 적어", lines[0])
        self.assertIn("비교할 수 없습니다", lines[1])

    def test_workbook_has_no_student_identity(self):
        import openpyxl
        exam, levels = _exam()
        designs = [_design("선택형", 1, "쉬움", 40.0, (90, 80, 70, 60, 50), exam.items[0])]
        with TemporaryDirectory() as directory:
            path = Path(directory) / "보정.xlsx"
            write_calibration_workbook(path, build_calibration(designs, exam, levels))
            book = openpyxl.load_workbook(path)
            try:
                text = " ".join(str(c.value) for sheet in book for row in sheet.iter_rows() for c in row if c.value is not None)
                self.assertEqual(book.sheetnames, ["요약", "문항별"])
            finally:
                book.close()
        for student in exam.students:
            self.assertNotIn(student.name, text)
            self.assertNotIn(student.class_no, text)


def _judgment(rate):
    return {"correct": [], "targetRate": rate, "overrideRate": None}


@unittest.skipIf(MainWindow is None, "main window unavailable")
class CalibrationWindowTests(unittest.TestCase):
    def test_calculator_project_is_compared_with_judge_average(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        window = MainWindow.__new__(MainWindow)
        window.exam, levels = _exam()
        window.overall = SimpleNamespace(levels_arr=levels)
        judges = [{"id": "j1", "name": "검토안 1"}, {"id": "j2", "name": "검토안 2"}]
        project = {"judges": judges, "items": [{
            "id": "i1", "number": 1, "type": "선택형", "difficulty": "쉬움", "targetLevel": "C", "points": 40,
            "judgmentsByJudge": {
                "j1": {lv: _judgment(r) for lv, r in zip("ABCDE", (90, 80, 70, 60, 50))},
                "j2": {lv: _judgment(r) for lv, r in zip("ABCDE", (70, 60, 50, 40, 30))},
            },
        }]}
        with patch.object(MainWindow, "_show_calibration_dialog") as show:
            window._on_calibration_project(project)
        report = show.call_args.args[0]
        self.assertEqual(report["rows"][0]["predicted"]["A"], 80.0)  # 두 검토안 평균
        self.assertEqual(report["rows"][0]["border"]["A"], 100.0)
        self.assertEqual(report["not_designed"], ["선택형 2번", "서답형 1번"])

    def test_empty_calculator_and_missing_analysis_explain_next_step(self):
        from unittest.mock import patch
        window = MainWindow.__new__(MainWindow)
        window.exam, window.overall = None, None
        with patch("app.main_window.QMessageBox") as messages:
            window.show_calibration_report()
            window.exam, _ = _exam()
            window._on_calibration_project({"items": []})
        texts = [call.args[2] for call in messages.information.call_args_list]
        self.assertIn("분석을 실행", texts[0])
        self.assertIn("작업 불러오기", texts[1])


if __name__ == "__main__":
    unittest.main()
