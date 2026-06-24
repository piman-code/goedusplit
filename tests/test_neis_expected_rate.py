import unittest

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


class _Settings:
    def __init__(self, raw=""):
        self.raw = raw

    def value(self, _key, default=""):
        return self.raw or default

    def setValue(self, _key, value):
        self.raw = value


@unittest.skipIf(MainWindow is None, f"app.main_window unavailable: {MAIN_WINDOW_IMPORT_ERROR}")
class NEISExpectedRateTests(unittest.TestCase):
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
        self.assertEqual({level: choice[level] for level in ["A", "B", "C", "D", "E"]}, {"A": 85.0, "B": 70.0, "C": 70.0, "D": 25.0, "E": 5.0})
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
                            "B": {"targetRate": 63, "correct": [True, True, True, False, False]},
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
        self.assertEqual(item["rates"]["A"], 85.0)
        self.assertEqual(item["rates"]["B"], 80.0)
        self.assertEqual(item["rates"]["C"], 40.0)
        self.assertEqual(item["rates"]["D"], 20.0)
        self.assertEqual(item["rates"]["E"], 0.0)


if __name__ == "__main__":
    unittest.main()
