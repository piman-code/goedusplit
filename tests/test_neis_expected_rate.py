import unittest
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from app.expected_rates import build_neis_rows, summarize_designs

try:
    from app.main_window import MainWindow
except ModuleNotFoundError as exc:
    MainWindow = None
    MAIN_WINDOW_IMPORT_ERROR = exc
else:
    MAIN_WINDOW_IMPORT_ERROR = None


def _window():
    window = MainWindow.__new__(MainWindow)
    window.exam = None
    window.overall = None
    window.item_stats = []
    return window


def _design(**changes):
    design = {
        "number": 1, "type": "선택형", "difficulty": "보통", "target": "B",
        "points": 4.0, "sampleSize": 5,
        "rates": {"A": 86.0, "B": 63.0, "C": 40.0, "D": 20.0, "E": 12.5},
    }
    design.update(changes)
    return design


class _Settings:
    def __init__(self, raw=""):
        self.raw = raw

    def value(self, _key, default=""):
        return self.raw or default

    def setValue(self, _key, value):
        self.raw = value


@unittest.skipIf(MainWindow is None, f"app.main_window unavailable: {MAIN_WINDOW_IMPORT_ERROR}")
class NEISExpectedRateTests(unittest.TestCase):
    def test_project_flush_embeds_evidence_without_replacing_teacher_judgments(self):
        import json
        window = _window()
        window.spliter_view = Mock()
        window._spliter_loaded = True
        original = {"items": [{"points": 7.125, "manual": 63.25}]}
        window._spliter_pending_project_payload = original
        window._spliter_pending_payload = {"synthetic": True}
        window._flush_spliter_project_payload()
        window._flush_spliter_payload()
        page = window.spliter_view.page.return_value
        page.runJavaScript.assert_called_once()
        script = page.runJavaScript.call_args.args[0]
        payload = json.loads(script.split(" = ", 1)[1].split(";window.postMessage", 1)[0])
        self.assertEqual(payload["items"], original["items"])
        self.assertEqual(payload["evidenceData"], {"synthetic": True})
        self.assertNotIn("evidenceData", original)
        self.assertNotIn("type: 'goedusplit-evidence'", script)
        self.assertIsNone(window._spliter_pending_payload)

    def test_enforce_neis_rate_order_rounds_and_keeps_monotone(self):
        window = _window()

        rates = window._enforce_neis_rate_order(
            {"A": 88.0, "B": 83.0, "C": 71.0, "D": 47.0, "E": 12.4}
        )

        self.assertEqual(rates, {"A": 90.0, "B": 85.0, "C": 70.0, "D": 45.0, "E": 12.0})
        ordered = [rates[level] for level in ["A", "B", "C", "D", "E"]]
        self.assertEqual(ordered, sorted(ordered, reverse=True))

    def test_custom_target_rate_presets_drive_target_defaults(self):
        window = _window()
        window.settings = _Settings()
        window._save_target_rate_presets(
            {
                "C": {"A": 77, "B": 71, "C": 66, "D": 33, "E": 11},
            }
        )

        rates = window._target_level_rates("C", "보통")

        self.assertEqual(rates, {"A": 75, "B": 70, "C": 70, "D": 35, "E": 11})
        self.assertIn('"C"', window.settings.raw)

    def test_custom_target_rate_presets_respect_difficulty_adjustment(self):
        window = _window()
        window.settings = _Settings()
        window._save_target_rate_presets(
            {
                "B": {"A": 80, "B": 65, "C": 40, "D": 20, "E": 5},
            }
        )

        rates = window._target_level_rates("B", "어려움")

        self.assertEqual(rates, {"A": 70, "B": 70, "C": 30, "D": 10, "E": 0})

    def test_target_rate_rules_use_two_thirds_actual_student_count(self):
        window = _window()

        small = window._enforce_target_rate_rules(
            {"A": 65, "B": 60, "C": 55, "D": 40, "E": 20},
            "B",
            sample_size=3,
        )
        large = window._enforce_target_rate_rules(
            {"A": 65, "B": 60, "C": 55, "D": 40, "E": 20},
            "B",
            sample_size=20,
        )
        judgments = window._judgments_from_rates(large, 20, [{"id": "teacher-1"}], "B")

        self.assertEqual(small["B"], 67)
        self.assertEqual(large["B"], 70)
        self.assertEqual(sum(judgments["teacher-1"]["B"]["correct"]), 14)
        self.assertGreaterEqual(large["A"], large["B"])
        self.assertGreaterEqual(large["B"], large["C"])

    def test_build_neis_expected_rows_groups_and_weights_points(self):
        window = _window()
        design_items = [
            {
                "number": 1,
                "type": "선택형",
                "difficulty": "보통",
                "target": "C",
                "points": 1,
                "rates": {"A": 100, "B": 80, "C": 60, "D": 40, "E": 20},
            },
            {
                "number": 2,
                "type": "선택형",
                "difficulty": "보통",
                "target": "C",
                "points": 3,
                "rates": {"A": 80, "B": 60, "C": 40, "D": 20, "E": 0},
            },
            {
                "number": 1,
                "type": "서답형",
                "difficulty": "어려움",
                "target": "B",
                "points": 4,
                "rates": {"A": 70, "B": 60, "C": 40, "D": 20, "E": 0},
            },
        ]

        rows = window._build_neis_expected_rows(design_items)

        self.assertEqual(len(rows), 2)
        choice = rows[0]
        self.assertEqual(choice["문항구분"], "선택형")
        self.assertEqual(choice["난이도"], "보통")
        self.assertEqual(choice["해당문항번호"], "1, 2")
        self.assertEqual(choice["문항수"], 2)
        self.assertEqual(choice["배점합"], 4.0)
        self.assertEqual({level: choice[level] for level in ["A", "B", "C", "D", "E"]}, {"A": 85.0, "B": 65.0, "C": 45.0, "D": 25.0, "E": 5.0})
        written = rows[1]
        self.assertEqual(written["문항구분"], "서답형")
        self.assertEqual(written["난이도"], "어려움")
        self.assertEqual(written["해당문항번호"], "1")

    def test_project_from_neis_targets_uses_rates_as_judgment_counts(self):
        window = _window()

        project = window._project_from_neis_targets(
            [
                {
                    "number": 3,
                    "type": "선택형",
                    "difficulty": "보통",
                    "target": "C",
                    "points": 5,
                    "standard": "[10공수1-01-01] 다항식",
                    "rates": {"A": 90, "B": 80, "C": 70, "D": 40, "E": 10},
                }
            ],
            sample_size=10,
        )

        item = project["items"][0]
        self.assertEqual(item["sampleSize"], 10)
        self.assertEqual(item["targetLevel"], "C")
        self.assertEqual(item["type"], "선택형")
        counts = [
            sum(item["judgmentsByJudge"]["teacher-1"][level]["correct"])
            for level in ["A", "B", "C", "D", "E"]
        ]
        self.assertEqual(counts, [9, 8, 7, 4, 1])
        self.assertIn("NEIS 설계표", item["evidence"])
        self.assertIn("계산기 현재값", item["evidence"])

    def test_neis_design_items_from_spliter_project_reads_override_rates(self):
        window = _window()
        project = {
            "judges": [{"id": "teacher-1", "name": "교사"}],
            "items": [
                {
                    "id": "item-1",
                    "number": 4,
                    "type": "논술형",
                    "difficulty": "어려움",
                    "targetLevel": "B",
                    "points": 6,
                    "standard": "[10공수1-01-02] 식",
                    "sampleSize": 5,
                    "judgmentsByJudge": {
                        "teacher-1": {
                            "A": {"overrideRate": 86, "correct": [True, True, True, True, False]},
                            "B": {"overrideRate": 63, "correct": [True, True, True, False, False]},
                            "C": {"correct": [True, True, False, False, False]},
                            "D": {"correct": [True, False, False, False, False]},
                            "E": {"correct": [False, False, False, False, False]},
                        }
                    },
                }
            ],
        }

        items = window._neis_design_items_from_spliter_project(project)

        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item["type"], "서답형")
        self.assertEqual(item["target"], "B")
        self.assertEqual(item["points"], 6.0)
        self.assertEqual(item["rates"]["A"], 86.0)
        self.assertEqual(item["rates"]["B"], 63.0)
        self.assertEqual(item["rates"]["C"], 40.0)
        self.assertEqual(item["rates"]["D"], 20.0)
        self.assertEqual(item["rates"]["E"], 0.0)

    def test_explicit_rates_survive_sample_sizes_and_neis_roundtrip(self):
        window = _window()
        for sample in (1, 3, 5, 10, 20):
            with self.subTest(sample=sample):
                design = _design(sampleSize=sample)
                before = deepcopy(design)
                project = window._project_from_neis_targets([design])
                judgment = project["items"][0]["judgmentsByJudge"]["teacher-1"]
                self.assertEqual(judgment["B"]["overrideRate"], 63.0)
                self.assertEqual(judgment["E"]["overrideRate"], 12.5)
                self.assertEqual(sum(judgment["B"]["correct"]), round(0.63 * sample))
                restored = window._neis_design_items_from_spliter_project(project)
                self.assertEqual(restored[0]["rates"], design["rates"])
                row = window._build_neis_expected_rows(restored, sample_size=20)[0]
                self.assertEqual((row["B"], row["E"]), (65, 15))
                self.assertEqual(design, before)

    def test_roundtrip_preserves_judges_active_state_and_item_details(self):
        window = _window()
        project = window._project_from_neis_targets([_design()])
        project["judges"] = [{"id": "one", "name": "검토안 가"}, {"id": "two", "name": "검토안 나"}]
        project["activeJudgeId"] = "two"
        project["customSetting"] = "keep"
        item = project["items"][0]
        item["title"] = "문항 제목"
        item["note"] = "교과 협의 메모"
        item["judgmentsByJudge"] = {
            judge: {level: {"overrideRate": value} for level, value in _design(rates={"A": a, "B": b, "C": 40, "D": 20, "E": 10})["rates"].items()}
            for judge, a, b in (("one", 90, 66), ("two", 75, 60))
        }
        original = deepcopy(project)
        designs = window._neis_design_items_from_spliter_project(project)
        self.assertEqual(designs[0]["rates"]["A"], 82.5)
        self.assertEqual(designs[0]["rates"]["B"], 63.0)
        designs[0]["points"] = 7.125
        result = window._project_from_neis_targets(designs)
        expected = deepcopy(original)
        expected["items"][0]["points"] = 7.125
        self.assertEqual(result, expected)
        self.assertEqual(project, original)

    def test_group_weighting_precedes_half_up_rounding_and_preserves_100(self):
        window = _window()
        first = _design(points=1, rates={"A": 90, "B": 63, "C": 40, "D": 20, "E": 12.5})
        second = _design(number=2, points=3, rates={"A": 80, "B": 63, "C": 40, "D": 20, "E": 12.5})
        rows = window._build_neis_expected_rows([first, second])
        self.assertEqual((rows[0]["A"], rows[0]["B"], rows[0]["E"]), (85, 65, 15))
        summary = summarize_designs([first, second])
        self.assertAlmostEqual(summary["raw_cuts"]["A"], 3.3)
        self.assertEqual(summary["scaled_cuts"]["A"], 82.5)
        full = _design(rates={level: 100 for level in "ABCDE"})
        self.assertEqual(window._build_neis_expected_rows([full])[0]["A"], 100)

    def test_invalid_inputs_fail_before_defaults_or_export(self):
        window = _window()
        invalid = [
            _design(points=value) for value in (0, -1, float("nan"), float("inf"), True)
        ] + [_design(number=value) for value in (0, -1, 1.5, True)]
        invalid += [_design(rates={**_design()["rates"], "B": value}) for value in (float("nan"), float("inf"), -1, 101, True)]
        invalid += [_design(rates={"A": 90}), _design(rates={**_design()["rates"], "B": 99})]
        for design in invalid:
            with self.subTest(design=design):
                with self.assertRaises(ValueError):
                    window._build_neis_expected_rows([design])
                with self.assertRaises(ValueError):
                    window._project_from_neis_targets([design])
        with self.assertRaises(ValueError):
            window._build_neis_expected_rows([_design(), _design()])
        self.assertEqual(len(window._build_neis_expected_rows([_design(), _design(type="서답형")])), 2)

    def test_judgment_precedence_and_invalid_values(self):
        window = _window()
        judgment = {"targetRate": 63, "correct": [True, True, True, False, False]}
        self.assertEqual(window._rate_from_spliter_judgment(judgment), 60)
        self.assertEqual(window._rate_from_spliter_judgment({**judgment, "overrideRate": 63}), 63)
        for invalid in ({"overrideRate": "nan"}, {"correct": ["false", "0"]}):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                window._rate_from_spliter_judgment(invalid)
        with self.assertRaises(ValueError):
            window._rates_from_spliter_item({"number": 1, "judgmentsByJudge": {}}, [{"id": "one"}])

    def test_cell_parsers_reject_invalid_numbers(self):
        window = _window()
        for value in ("", "x", "nan", "inf", "-1", "0", "1.5", True):
            with self.subTest(number=value), self.assertRaises(ValueError):
                window._parse_neis_int(value)
        for value in ("", "x", "nan", "inf", "-1", "0", True):
            with self.subTest(points=value), self.assertRaises(ValueError):
                window._parse_neis_float(value)

    def test_invalid_clipboard_save_and_send_leave_state_untouched(self):
        window = _window()
        window.spliter_view = object()
        window._spliter_pending_project_payload = {"unchanged": True}
        window._collect_neis_design_items = Mock(return_value=[_design(points=0)])
        sample, mode = Mock(), Mock()
        sample.currentText.return_value = "20"
        mode.currentData.return_value = "target"
        with patch("app.main_window.QMessageBox") as messages, patch("app.main_window.QApplication") as application, patch("app.main_window.QFileDialog") as files:
            window._copy_neis_expected_rows(None, sample, mode)
            window._save_neis_expected_rows_xlsx(None, sample, mode)
            window._send_neis_targets_to_spliter(None, sample, mode)
        self.assertEqual(messages.warning.call_count, 3)
        application.clipboard.assert_not_called()
        files.getSaveFileName.assert_not_called()
        self.assertEqual(window._spliter_pending_project_payload, {"unchanged": True})

    def test_workbook_uses_same_rows_and_preserves_source_values(self):
        import openpyxl

        window = _window()
        designs = [_design()]
        rows = window._build_neis_expected_rows(designs)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "estimates.xlsx"
            with patch("app.main_window.QMessageBox"), patch("app.main_window.QFileDialog.getSaveFileName", return_value=(str(path), "")):
                window._save_neis_rows_xlsx(rows, designs=designs)
            workbook = openpyxl.load_workbook(path, data_only=True)
            try:
                self.assertEqual(workbook.sheetnames, ["분할점수 비교", "문항별 입력값", "NEIS 입력표"])
                self.assertEqual(workbook["문항별 입력값"]["G2"].value, 63)
                self.assertAlmostEqual(workbook["분할점수 비교"]["B4"].value, 2.52)
                self.assertEqual(workbook["분할점수 비교"]["C4"].value, 63)
                self.assertEqual(workbook["분할점수 비교"]["E4"].value, 65)
                self.assertEqual(workbook["분할점수 비교"]["F4"].value, 2)
                headers = window._neis_row_headers()
                exported = list(workbook["NEIS 입력표"].values)[1]
                self.assertEqual(list(exported), [rows[0][header] for header in headers])
                self.assertEqual(rows, build_neis_rows(designs))
            finally:
                workbook.close()

    def test_native_dialog_without_analysis_loads_exact_rates_and_summary(self):
        from PySide6.QtWidgets import QApplication, QDialog, QLabel, QMainWindow, QPushButton, QTableWidget

        self.__class__._qt_app = QApplication.instance() or QApplication([])
        application = self.__class__._qt_app
        window = _window()
        QMainWindow.__init__(window)
        window.settings = _Settings()
        window.spliter_view = object()
        window._spliter_loaded = True
        window._px = lambda value: value
        project = window._project_from_neis_targets([_design()])
        window._fetch_spliter_project = Mock(side_effect=lambda callback, **_kwargs: callback(project))
        self.assertEqual(window._default_neis_design_items(), [])

        def inspect(dialog):
            dialog.show()
            application.processEvents()
            table = dialog.findChild(QTableWidget)
            summary = dialog.findChild(QLabel, "neisEstimationSummary")
            self.assertEqual(table.rowCount(), 1)
            self.assertIn("B63", table.item(0, 5).text())
            self.assertIn("B/C 2.52", summary.text())
            self.assertIn("B/C 63.00", summary.text())
            self.assertIn("B/C 65.00", summary.text())
            self.assertIn("B/C +2.00", summary.text())
            table.cellWidget(0, 4).setCurrentText("E")
            self.assertIn("B63", table.item(0, 5).text())
            table.item(0, 3).setText("0")
            self.assertIn("입력 오류", summary.text())
            copy_button = next(button for button in dialog.findChildren(QPushButton) if button.text() == "엑셀용 복사")
            copy_button.click()
            table.item(0, 3).setText("7.125")
            restored = window._project_from_neis_targets(window._collect_neis_design_items(table))
            self.assertEqual(restored["items"][0]["points"], 7.125)
            self.assertEqual(restored["items"][0]["judgmentsByJudge"], project["items"][0]["judgmentsByJudge"])
            dialog.reject()
            return 0

        with patch.object(QDialog, "exec", new=inspect), patch("app.main_window.QMessageBox") as messages:
            window.open_neis_expected_rate_dialog()
        window._fetch_spliter_project.assert_called_once()
        self.assertEqual(messages.warning.call_count, 1)
        window.deleteLater()


if __name__ == "__main__":
    unittest.main()
