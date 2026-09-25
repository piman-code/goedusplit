import copy
import json
import math
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from app.expected_rates import (
    LEVELS, build_neis_rows, normalize_rates, round_neis_rate,
    summarize_designs, validate_design_items, write_estimation_workbook,
)


def design(number=1, points=4, rates=(100, 80, 60, 40, 20), item_type="선택형"):
    return {"number": number, "points": points, "type": item_type, "difficulty": "보통", "target": "C", "rates": dict(zip(LEVELS, rates))}


class ExpectedRateContractTests(unittest.TestCase):
    def test_weighting_before_rounding_and_non_100_point_scale(self):
        items = [design(points=1), design(2, 3, (80, 60, 40, 20, 0))]
        original = copy.deepcopy(items)
        result = summarize_designs(items)
        self.assertEqual(result["total_points"], 4)
        self.assertAlmostEqual(result["raw_cuts"]["B"], 2.6)
        self.assertAlmostEqual(result["scaled_cuts"]["B"], 65)
        self.assertEqual(build_neis_rows(items)[0]["C"], 45)
        self.assertEqual(items, original)

    def test_teacher_values_are_preserved_and_neis_difference_is_visible(self):
        item = design(rates=(100, 82.5, 63.25, 40, 12.5))
        result = summarize_designs([item])
        self.assertEqual(normalize_rates(item["rates"])["C"], 63.25)
        self.assertAlmostEqual(result["scaled_cuts"]["C"], 63.25, places=12)
        self.assertEqual(result["neis_scaled_cuts"]["C"], 65)
        self.assertEqual(build_neis_rows([item])[0]["A"], 100)
        self.assertEqual(build_neis_rows([item])[0]["E"], 15)

    def test_fraction_is_not_rounded_per_item(self):
        result = summarize_designs([design(points=90, rates=(100, 200 / 3, 50, 25, 0))])
        self.assertAlmostEqual(result["raw_cuts"]["B"], 60, places=12)

    def test_halfway_rounds_up_including_e(self):
        for value, expected in [(0, 0), (2.5, 5), (12.5, 15), (82.5, 85), (97.5, 100), (100, 100)]:
            self.assertEqual(round_neis_rate(value), expected)

    def test_bad_values_rejected_without_clamping_or_defaulting(self):
        for value in [None, "", True, math.nan, math.inf, -1, 101]:
            item = design()
            item["rates"]["C"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                summarize_designs([item])
        for points in [0, -1, math.inf]:
            with self.assertRaises(ValueError):
                summarize_designs([design(points=points)])
        with self.assertRaisesRegex(ValueError, "역전"):
            summarize_designs([design(rates=(80, 90, 60, 40, 0))])

    def test_duplicate_number_is_scoped_to_item_type(self):
        with self.assertRaisesRegex(ValueError, "중복"):
            validate_design_items([design(), design()])
        rows = build_neis_rows([design(), design(item_type="서답형")])
        self.assertEqual(len(rows), 2)

    def test_workbook_contains_originals_comparison_and_real_neis_cells(self):
        import openpyxl
        item = design(rates=(100, 82.5, 63.25, 40, 12.5))
        item["standard"] = "=1+1"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "review.xlsx"
            write_estimation_workbook(path, [item])
            book = openpyxl.load_workbook(path, data_only=False)
            self.assertEqual(book.sheetnames, ["분할점수 비교", "문항별 입력값", "NEIS 입력표"])
            self.assertEqual(book["문항별 입력값"]["H2"].value, 63.25)
            self.assertEqual(book["NEIS 입력표"]["H2"].value, 65)
            self.assertEqual(book["문항별 입력값"]["K2"].data_type, "s")
            self.assertAlmostEqual(book["분할점수 비교"]["F5"].value, 1.75)
            book.close()

    @unittest.skipUnless(shutil.which("node"), "Node is needed for Python/JavaScript parity")
    def test_browser_and_python_calculations_agree(self):
        items = [design(1, 1, (100, 82.5, 63.25, 40, 12.5)), design(2, 3, (90, 80, 200 / 3, 45, 20)), design(1, 4, (80, 60, 40, 20, 0), "서답형")]
        module = Path(__file__).resolve().parents[1] / "app/spliter_ox_web/expected-rates.js"
        script = "const fs=require('fs'), api=require(process.argv[1]), items=JSON.parse(fs.readFileSync(0,'utf8')); console.log(JSON.stringify({rows:api.rowsFromDesigns(items),summary:api.summarizeDesigns(items)}));"
        output = subprocess.check_output([shutil.which("node"), "-e", script, str(module)], input=json.dumps(items), text=True, encoding="utf-8")
        actual = json.loads(output)
        self.assertEqual(actual["rows"], build_neis_rows(items))
        expected = summarize_designs(items)
        for key in ("raw_cuts", "scaled_cuts", "neis_raw_cuts", "neis_scaled_cuts"):
            for level in LEVELS:
                self.assertAlmostEqual(actual["summary"][key][level], expected[key][level], places=10)

    @unittest.skipUnless(shutil.which("node"), "Node is needed for the calculator's live preview")
    def test_live_preview_keeps_cut_scores_while_rates_are_inverted(self):
        items = [design(1, 1, (60, 80, 50, 40, 10)), design(2, 3, (90, 80, 70, 45, 20))]
        module = Path(__file__).resolve().parents[1] / "app/spliter_ox_web/expected-rates.js"
        script = ("const fs=require('fs'), api=require(process.argv[1]), items=JSON.parse(fs.readFileSync(0,'utf8')); let strict;"
                  "try { api.summarizeDesigns(items); strict = 'no error'; } catch (error) { strict = error.message; }"
                  "console.log(JSON.stringify({strict, live: api.summarizeDesigns(items, {allowInversions: true})}));")
        output = subprocess.check_output([shutil.which("node"), "-e", script, str(module)], input=json.dumps(items), text=True, encoding="utf-8")
        actual = json.loads(output)
        self.assertIn("역전", actual["strict"])  # NEIS 표와 저장 검사는 그대로 막는다
        self.assertAlmostEqual(actual["live"]["raw_cuts"]["A"], (1 * 60 + 3 * 90) / 100)
        self.assertEqual(actual["live"]["inversions"], [{"type": "선택형", "number": 1, "pairs": [["A", "B"]]}])


if __name__ == "__main__":
    unittest.main()
