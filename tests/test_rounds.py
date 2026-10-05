from tests.runtime_isolation import ensure_isolated
ensure_isolated()

import tempfile
import unittest
from pathlib import Path

from app import rounds


def _record(year, semester, round_no, students, mean=60.0, std=10.0, a=10.0, subject="공통수학1", grade="1학년"):
    pct = {"A": a, "B": 20.0, "C": 30.0, "D": 25.0, "E": 15.0 - a + 10.0, "미도달": 0.0}
    return rounds.build_record(
        subject=subject, grade=grade, year=year, semester=semester, round_no=round_no,
        n_students=len(students), mean=mean, std=std, level_pct=pct, level_n={}, cuts={"A": 80, "B": 70, "C": 60, "D": 50, "E": 40},
        students={h: {"level": lv, "score": 50.0} for h, lv in students.items()})


class RoundNameTests(unittest.TestCase):
    def test_semester_and_round_come_from_file_names(self):
        self.assertEqual((1, 1), rounds.parse_round("예상추정분할점수조회(공통수학1)1학기 1차.xlsx"))
        self.assertEqual((None, 2), rounds.parse_round("2차 정기시험 교과목별 일람표(공통수학1).xlsx"))
        self.assertEqual((2, None), rounds.parse_round("2학기 분할점수.xlsx"))
        self.assertEqual((None, None), rounds.parse_round("수행평가 조회(3-5, 확통).xlsx", "문항정보표(공통수학1) 샘플.xlsx"))
        self.assertEqual((1, 2), rounds.parse_round("정오표.xlsx", "2026학년도 1학기 2차"))   # first text without a tag is skipped

    def test_labels_and_conflicts(self):
        self.assertEqual("2026학년도 1학기 1차", rounds.round_label(2026, 1, 1))
        self.assertEqual("1차", rounds.round_name(None, 1))
        self.assertEqual("회차 미지정", rounds.round_name(None, None))
        self.assertEqual(2026, rounds.parse_year("2026학년도"))
        self.assertTrue(rounds.tags_conflict((1, 1), (1, 2)))
        self.assertFalse(rounds.tags_conflict((None, 1), (1, 1)))       # an unknown side never conflicts
        self.assertFalse(rounds.tags_conflict((None, None), (2, 2)))


class RoundStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = rounds.RoundStore(Path(self.tmp.name) / "round_history")

    def test_same_round_overwrites_and_others_accumulate(self):
        first = self.store.save(_record(2026, 1, 1, {"h1": "A"}, mean=60))
        again = self.store.save(_record(2026, 1, 1, {"h1": "B"}, mean=65))
        self.store.save(_record(2026, 1, 2, {"h1": "C"}))
        self.assertEqual(first, again)
        loaded = self.store.load_all()
        self.assertEqual([(1, 1), (1, 2)], [(r["semester_no"], r["round_no"]) for r in loaded])
        self.assertEqual(65.0, loaded[0]["mean"])                    # the latest analysis of 1학기 1차 wins

    def test_unreadable_or_foreign_files_are_skipped(self):
        self.store.save(_record(2026, 1, 1, {"h1": "A"}))
        (self.store.directory / "round_broken.json").write_text("{not json", encoding="utf-8")
        (self.store.directory / "round_other.json").write_text('{"kind": "snapshot"}', encoding="utf-8")
        self.assertEqual(1, len(self.store.load_all()))
        self.assertEqual([], rounds.RoundStore(Path(self.tmp.name) / "missing").load_all())

    def test_previous_year_and_same_course(self):
        for year in (2025, 2026):
            self.store.save(_record(year, 1, 1, {"h1": "A"}, mean=50 + year - 2025))
        self.store.save(_record(2026, 1, 1, {"h1": "A"}, subject="확률과 통계"))
        records = self.store.load_all()
        self.assertEqual(2, len(rounds.same_course(records, "공통수학1", "1학년")))
        previous = rounds.previous_year(records, "공통수학1", "1학년", 2026, 1, 1)
        self.assertEqual(50.0, previous["mean"])
        self.assertIsNone(rounds.previous_year(records, "공통수학1", "1학년", 2026, 1, 2))
        self.assertIsNone(rounds.previous_year(records, "공통수학1", "1학년", None, 1, 1))


class CompareTests(unittest.TestCase):
    def test_metrics_and_student_movement(self):
        base = _record(2026, 1, 1, {"a": "A", "b": "B", "c": "C", "d": "D", "gone": "E"}, mean=60, std=10, a=10)
        other = _record(2026, 1, 2, {"a": "B", "b": "B", "c": "A", "d": "E", "new": "C"}, mean=64.5, std=9, a=14)
        result = rounds.compare(base, other)
        rows = {name: (a, b, diff) for name, a, b, diff in result["rows"]}
        self.assertEqual((60.0, 64.5, 4.5), rows["평균(점)"])
        self.assertEqual((10.0, 9.0, -1.0), rows["표준편차(점)"])
        self.assertEqual(4.0, rows["A 비율(%)"][2])
        self.assertNotIn("미도달 비율(%)", rows)                        # nobody there in either round
        self.assertEqual({"paired": 4, "up": 1, "same": 1, "down": 2},
                         {key: result[key] for key in ("paired", "up", "same", "down")})   # c rose; a and d fell
        self.assertEqual(1, result["matrix"]["A"]["B"])                # a: A -> B
        self.assertEqual(1, result["matrix"]["C"]["A"])                # c: C -> A
        self.assertEqual((1, 1), (result["only_base"], result["only_other"]))

    def test_trend_labels_add_the_year_only_when_years_differ(self):
        one_year = [_record(2026, 1, 1, {}), _record(2026, 1, 2, {})]
        self.assertEqual(["1학기 1차", "1학기 2차"], rounds.trend(one_year)["labels"])
        two_years = [_record(2025, 1, 1, {}), _record(2026, 1, 1, {})]
        self.assertEqual(["2025학년도 1학기 1차", "2026학년도 1학기 1차"], rounds.trend(two_years)["labels"])
        self.assertEqual([10.0, 10.0], rounds.trend(one_year)["a_pct"])


if __name__ == "__main__":
    unittest.main()
