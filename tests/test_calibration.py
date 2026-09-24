import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.calibration import (
    borderline_indices, build_calibration, cut_lines, suggest_presets, summary_lines, write_calibration_workbook,
)
from app.data_loader import ExamData, ItemInfo, StudentResponse

try:
    from app.main_window import MainWindow
except ModuleNotFoundError:
    MainWindow = None

CUTS = {"A": 80, "B": 60, "C": 50, "D": 20, "E": 10}


def _exam():
    """6 synthetic students. With 6 students, 2 are taken from each side of a cut.

    A cut 80: below [78, 70], above [82, 90]. B cut 60: below [52], above [70].
    C cut 50: below [48], above [52]. D and E: nobody within 10 points.
    """
    exam = ExamData(subject="합성")
    exam.cut_scores = dict(CUTS)
    exam.items = [
        ItemInfo(number=1, item_type="선택형", difficulty="쉬움", score=40.0, answer="1"),
        ItemInfo(number=2, item_type="선택형", difficulty="어려움", score=40.0, answer="2"),
        ItemInfo(number=1, item_type="서답형", difficulty="보통", score=20.0),
    ]
    data = [  # (final score, item1, item2, serdap score out of 20)
        (90, ".", ".", 20), (82, ".", "3", 16), (78, ".", "3", 12),
        (70, "2", ".", 10), (52, "2", "3", 4), (48, "2", "3", 0),
    ]
    for i, (score, a1, a2, serdap) in enumerate(data):
        exam.students.append(StudentResponse(
            sid=f"S{i}", class_no=f"합성반{i}", name=f"합성{i}", answers={1: a1, 2: a2},
            serdap_score=serdap, total=score, final_score=score,
        ))
    return exam, ["A", "A", "B", "B", "C", "미도달"]


def _design(kind, number, difficulty, points, rates, item):
    return {"type": kind, "number": number, "difficulty": difficulty, "target": "C", "points": points,
            "rates": dict(zip("ABCDE", rates)), "source_item": item}


def _standard_designs(exam):
    item1, item2, serdap = exam.items
    return [
        _design("선택형", 1, "쉬움", 40.0, (90, 80, 70, 60, 50), item1),
        _design("선택형", 2, "어려움", 40.0, (80, 60, 40, 20, 10), item2),
        _design("서답형", 1, "보통", 20.0, (70, 60, 50, 40, 30), serdap),
    ]


class CalibrationTests(unittest.TestCase):
    def test_borderline_takes_both_sides_of_each_cut(self):
        exam, _ = _exam()
        border = borderline_indices([st.final_score for st in exam.students], CUTS)
        self.assertEqual(border["A"], [[2, 3], [1, 0]])
        self.assertEqual(border["B"], [[4], [3]])
        self.assertEqual(border["C"], [[5], [4]])
        self.assertNotIn("D", border)
        # 한쪽에만 학생이 있으면 그쪽만, 동점은 함께 포함
        self.assertEqual(borderline_indices([55, 52, 52, 30], {"A": 60}), {"A": [[0, 1, 2]]})

    def test_rates_average_both_sides_and_relative_misses(self):
        exam, levels = _exam()
        report = build_calibration(_standard_designs(exam), exam, levels)
        rows = {(r["type"], r["number"]): r for r in report["rows"]}
        one, two, group = rows[("선택형", "1")], rows[("선택형", "2")], rows[("서답형 묶음", "1")]
        self.assertEqual([one["border"][lv] for lv in "ABC"], [75.0, 0.0, 0.0])      # A: 아래 50, 위 100
        self.assertEqual([two["border"][lv] for lv in "ABC"], [50.0, 50.0, 0.0])
        self.assertAlmostEqual(group["border"]["A"], 72.5)                             # 아래 55, 위 90
        self.assertAlmostEqual(group["border"]["B"], 35.0)
        self.assertIsNone(one["border"]["D"])
        self.assertEqual(one["all"]["A"], 100.0)
        self.assertEqual((one["diff"]["A"], two["diff"]["A"], group["diff"]["A"]), (-15.0, -30.0, 2.5))
        self.assertAlmostEqual(report["offset"]["A"], (40 * -15 + 40 * -30 + 20 * 2.5) / 100)
        self.assertAlmostEqual(report["offset"]["B"], -41.0)
        self.assertIsNone(report["offset"]["D"])
        # 상대차 = 차이 - 그 경계의 배점 가중 평균 차이
        self.assertEqual([one["relative"]["A"], two["relative"]["A"], group["relative"]["A"]], [2.5, -12.5, 20.0])
        self.assertEqual([one["relative"]["B"], two["relative"]["B"], group["relative"]["B"]], [-39.0, 31.0, 16.0])
        self.assertIsNone(one["relative"]["D"])
        self.assertEqual(report["large_gaps"], 5)  # A: 서답, B: 1·2번·서답, C: 1번
        easy, hard = report["relative_by_difficulty"]["쉬움"], report["relative_by_difficulty"]["어려움"]
        self.assertEqual((easy["items"], easy["levels"]["A"], easy["levels"]["C"]), (1, 2.5, -18.0))
        self.assertEqual(hard["levels"]["B"], 31.0)
        self.assertNotIn("", report["relative_by_difficulty"])  # 서답형 묶음은 난이도 없음
        cuts = {c["level"]: c for c in report["cuts"]}
        self.assertAlmostEqual(cuts["A"]["predicted_scaled"], 82.0)
        self.assertAlmostEqual(cuts["A"]["actual_scaled"], 64.5)
        # 배점 가중 평균 차이 = 분할점수 차이 (모든 문항에 실측이 있을 때)
        self.assertAlmostEqual(cuts["A"]["actual_scaled"] - cuts["A"]["predicted_scaled"], report["offset"]["A"])
        self.assertEqual(cuts["A"]["applied"], 80.0)
        self.assertIsNone(cuts["D"]["actual_scaled"])
        self.assertEqual(report["counts"], {"A": 2, "B": 2, "C": 1, "D": 0, "E": 0})
        self.assertEqual(report["border_counts"], {"A": 4, "B": 2, "C": 2, "D": 0, "E": 0})

    def test_serdap_group_is_point_weighted_and_needs_every_serdap_item(self):
        exam, levels = _exam()
        exam.items.append(ItemInfo(number=2, item_type="서답형", difficulty="보통", score=30.0))
        s1, s2 = exam.items[2], exam.items[3]
        both = [_design("서답형", 1, "보통", 10.0, (80, 70, 60, 50, 40), s1),
                _design("서답형", 2, "보통", 30.0, (40, 30, 20, 10, 0), s2)]
        report = build_calibration(both, exam, levels)
        self.assertEqual(report["rows"][0]["number"], "1, 2")
        self.assertAlmostEqual(report["rows"][0]["predicted"]["A"], (10 * 80 + 30 * 40) / 40)
        self.assertEqual(report["notes"], [])

        partial = build_calibration(both[:1] + [_design("서답형", 9, "보통", 5.0, (1, 1, 1, 1, 1), None)], exam, levels)
        self.assertEqual(partial["rows"], [])
        self.assertEqual(partial["unmatched"], ["서답형 9번"])
        self.assertIn("모든 서답형 문항", partial["notes"][0])

    def test_unmatched_undesigned_and_perform_notes(self):
        exam, levels = _exam()
        exam.use_perform, exam.weight_perform = True, 30.0
        designs = [_design("선택형", 1, "쉬움", 40.0, (90, 80, 70, 60, 50), exam.items[0]),
                   _design("선택형", 9, "보통", 10.0, (90, 80, 70, 60, 50), None)]
        report = build_calibration(designs, exam, levels)
        self.assertEqual(report["unmatched"], ["선택형 9번"])
        self.assertEqual(report["not_designed"], ["선택형 2번", "서답형 1번"])
        self.assertTrue(any("수행평가" in note for note in report["notes"]))

    def test_summary_reads_relative_misses_then_cautions(self):
        exam, levels = _exam()
        lines = summary_lines(build_calibration(_standard_designs(exam), exam, levels))
        self.assertIn("쉬움 문항(1개): 다른 문항보다 경계 학생 정답률을 평균 18.2%p 높게", lines[0])
        self.assertIn("어려움 문항(1개): 다른 문항보다 경계 학생 정답률을 평균 10.2%p 낮게", lines[1])
        self.assertIn("15%p 이상 빗나간 칸이 5개", lines[2])
        self.assertTrue(any(line.startswith("A/B: 경계 학생이 적음") for line in lines))
        self.assertTrue(any(line.startswith("D/E: 분할점수 가까이에 학생이 없어") for line in lines))
        report = build_calibration(_standard_designs(exam), exam, levels)
        report["border_one_sided"] = ["A"]
        self.assertTrue(any("한쪽에만" in line for line in summary_lines(report)))

    def test_cut_lines_compare_estimated_and_applied_cuts(self):
        exam, levels = _exam()
        lines = cut_lines(build_calibration(_standard_designs(exam), exam, levels))
        self.assertEqual(lines[0], "A/B: 검토안으로 계산한 분할점수 82.0점, 이번에 적용한 분할점수 80.0점.")
        self.assertEqual(len(lines), 5)

    def test_preset_suggestion_uses_target_groups_and_keeps_missing_cells(self):
        exam, levels = _exam()
        report = build_calibration(_standard_designs(exam), exam, levels)
        current = {t: {lv: 10 * (i + 1) for i, lv in enumerate("ABCDE")} for t in "ABCDE"}
        suggestion = suggest_presets(report, current)
        # 선택형 1·2번 모두 목표 C: A (75+50)/2=62.5→63, B 25, C 0, D·E는 경계 학생이 없어 현재값 유지
        self.assertEqual(suggestion["C"]["suggested"], {"A": 63, "B": 25, "C": 0, "D": 40, "E": 50})
        self.assertEqual(suggestion["C"]["items"], 2)
        self.assertIsNone(suggestion["B"]["suggested"])
        self.assertIsNone(suggest_presets(report, current, min_items=3)["C"]["suggested"])

    def test_workbook_has_no_student_identity(self):
        import openpyxl
        exam, levels = _exam()
        with TemporaryDirectory() as directory:
            path = Path(directory) / "보정.xlsx"
            write_calibration_workbook(path, build_calibration(_standard_designs(exam), exam, levels))
            book = openpyxl.load_workbook(path)
            try:
                text = " ".join(str(c.value) for sheet in book for row in sheet.iter_rows() for c in row if c.value is not None)
                self.assertEqual(book.sheetnames, ["요약", "문항별"])
            finally:
                book.close()
        for student in exam.students:
            self.assertNotIn(student.name, text)
            self.assertNotIn(student.class_no, text)
            self.assertNotIn(student.sid, text)


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
        self.assertEqual(report["rows"][0]["border"]["A"], 75.0)
        self.assertEqual(report["not_designed"], ["선택형 2번", "서답형 1번"])

    def test_applying_suggestion_changes_only_chosen_rows_and_keeps_rules(self):
        import json
        from unittest.mock import Mock
        from app.main_window import DEFAULT_TARGET_RATE_PRESETS
        window = MainWindow.__new__(MainWindow)
        saved = {}
        window.settings = Mock(setValue=lambda key, value: saved.__setitem__(key, value))
        window._send_spliter_teacher_presets = Mock()
        window.statusBar = Mock()
        current = {t: dict(DEFAULT_TARGET_RATE_PRESETS[t]) for t in "ABCDE"}
        suggestion = {t: {"items": 0, "current": current[t], "suggested": None} for t in "ABCDE"}
        suggestion["C"]["suggested"] = {"A": 63, "B": 25, "C": 40, "D": 20, "E": 5}   # C < 2/3 → 규칙으로 보정
        suggestion["B"]["suggested"] = {"A": 90, "B": 80, "C": 50, "D": 30, "E": 10}  # 고르지 않은 행
        window._apply_preset_suggestion(suggestion, ["C"])
        stored = json.loads(saved["spliter/target_rate_presets"])
        self.assertEqual(stored["B"], current["B"])
        self.assertNotEqual(stored["C"], current["C"])
        self.assertGreaterEqual(stored["C"]["C"], 66)                 # 목표수준 학생 2/3 이상
        rates = [stored["C"][lv] for lv in "ABCDE"]
        self.assertEqual(rates, sorted(rates, reverse=True))         # A ≥ B ≥ … ≥ E
        window._send_spliter_teacher_presets.assert_called_once_with(apply_current=False)

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
