from tests.runtime_isolation import ensure_isolated
ensure_isolated()

import contextlib
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from build_scripts import generate_synthetic_validation_kit as kit


class SyntheticValidationKitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.output = cls.root / "synthetic-kit"
        with patch("urllib.request.urlopen", side_effect=AssertionError("no network")), \
                patch("app.exam_structure.find_kordoc", side_effect=AssertionError("no converter or personal-path probing")):
            kit.generate(cls.output)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_manifest_covers_every_generated_file_and_matches_bytes(self):
        manifest = json.loads((self.output / "manifest.json").read_text(encoding="utf-8"))
        self.assertTrue(manifest["synthetic_only"])
        names = {path.name for path in self.output.iterdir()}
        self.assertEqual(names - {"manifest.json"}, set(manifest["file_sha256"]))
        for name, value in manifest["file_sha256"].items():
            self.assertEqual(hashlib.sha256((self.output / name).read_bytes()).hexdigest(), value)
        self.assertEqual("passed", json.loads((self.output / "validation.json").read_text())["status"])
        self.assertFalse(any(path.is_dir() for path in self.output.iterdir()))

    def test_independent_constants_and_reading_formats_remain_stable(self):
        expected = json.loads((self.output / "expected.json").read_text(encoding="utf-8"))
        self.assertEqual([100, 50, 37.5, 0], expected["exam"]["written_scores"])
        self.assertEqual([100, 50, 32.5, 0], expected["exam"]["combined_scores"])
        self.assertEqual({"A": 4.75, "B": 3.6375, "C": 2.73625, "D": 1.6625, "E": 0.4875}, expected["calculator"]["raw_cuts"])
        self.assertEqual({"A": 100, "B": 75, "C": 60, "D": 35, "E": 10}, expected["calculator"]["neis_rates"])
        report = kit.verify_created(self.output)
        self.assertEqual(6, len(report["checks"]))
        self.assertIn("Synthetic Korean PDF parsed through PDF 내장 읽기", report["checks"])
        self.assertIn("HWP binary not generated or validated", report["limits"])

    def test_every_student_identity_is_explicitly_synthetic(self):
        from app.data_loader import load_exam
        from app.perform_loader import load_perform
        exam = load_exam(self.output / "합성_문항정보표.xlsx", self.output / "합성_정오표.xlsx")
        performance = load_perform(self.output / "합성_수행평가.xlsx")
        for student in exam.students:
            self.assertTrue(all(value.startswith("합성") for value in (student.sid, student.class_no, student.name)))
        for record in performance.records.values():
            self.assertTrue(all(value.startswith("합성") for value in (record.sid, record.class_no, record.name)))

    def test_actual_product_judge_conversion_preserves_decimal_rates_and_review_average(self):
        from app.main_window import MainWindow
        project = json.loads((self.output / "합성_계산기_검토안.json").read_text(encoding="utf-8"))
        before = deepcopy(project)
        window = MainWindow.__new__(MainWindow)
        window.exam = None
        designs = window._neis_design_items_from_spliter_project(project)
        self.assertEqual(kit.EXPECTED["calculator"]["mean_rates"], [item["rates"] for item in designs])
        self.assertEqual([1.5, 3.25], [item["points"] for item in designs])
        self.assertEqual(63.25, project["items"][0]["judgmentsByJudge"]["synthetic-judge-2"]["C"]["overrideRate"])
        self.assertEqual(before, project)

    def test_product_arithmetic_regression_cannot_rewrite_the_expected_or_pass(self):
        from app.expected_rates import summarize_designs
        before = deepcopy(kit.EXPECTED)
        def wrong(designs):
            values = summarize_designs(designs)
            values["raw_cuts"]["C"] = 0
            return values
        with patch("app.expected_rates.summarize_designs", side_effect=wrong):
            with self.assertRaisesRegex(ValueError, "calculator.summary.raw_cuts.C"):
                kit.verify_created(self.output)
        self.assertEqual(before, kit.EXPECTED)

    def test_verification_opens_only_the_newly_generated_loader_and_parser_inputs(self):
        import app.data_loader
        import app.exam_structure
        original_xlsx = app.data_loader.openpyxl.load_workbook
        original_paper = app.exam_structure.extract_exam_text
        def xlsx(path, *args, **kwargs):
            self.assertEqual(self.output, Path(path).parent)
            return original_xlsx(path, *args, **kwargs)
        def paper(path):
            self.assertEqual(self.output, Path(path).parent)
            return original_paper(path)
        with patch("app.data_loader.openpyxl.load_workbook", side_effect=xlsx), \
                patch("app.exam_structure.extract_exam_text", side_effect=paper):
            self.assertEqual("passed", kit.verify_created(self.output)["status"])

    def test_existing_output_is_refused_without_changing_any_file(self):
        before = {path.name: path.read_bytes() for path in self.output.iterdir()}
        with self.assertRaises(FileExistsError):
            kit.generate(self.output)
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.output.iterdir()})
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(1, kit.main(["--output", str(self.output)]))

    def test_failed_generation_records_failure_and_restores_process_environment(self):
        with tempfile.TemporaryDirectory() as scratch:
            output = Path(scratch) / "failed-kit"
            before = {key: os.environ.get(key) for key in ("MPLCONFIGDIR", "XDG_CACHE_HOME")}
            with patch.object(kit, "_workbooks"), patch.object(kit, "_papers"), \
                    patch.object(kit, "verify_created", side_effect=ValueError("synthetic verification failed")):
                with contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(1, kit.main(["--output", str(output)]))
            self.assertEqual(before, {key: os.environ.get(key) for key in before})
            self.assertEqual("failed", json.loads((output / "validation.json").read_text())["status"])
            self.assertFalse((output / "manifest.json").exists())

    def test_symlink_and_mock_junction_output_ancestors_are_refused(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            real = root / "real"
            real.mkdir()
            link = root / "linked"
            try:
                link.symlink_to(real, target_is_directory=True)
            except OSError:
                link = None
            if link is not None:
                with self.assertRaisesRegex(ValueError, "symlink/junction"):
                    kit.generate(link / "must-not-create")
                self.assertFalse((real / "must-not-create").exists())
            with patch.object(Path, "is_junction", lambda path: path == real, create=True):
                with self.assertRaisesRegex(ValueError, "symlink/junction"):
                    kit.generate(real / "must-not-create")
            self.assertFalse((real / "must-not-create").exists())

    @unittest.skipUnless(os.name == "nt" and hasattr(Path, "is_junction"), "requires actual Windows junction support")
    def test_real_windows_junction_output_is_refused(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            real = root / "real"
            real.mkdir()
            link = root / "linked"
            result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(real)], capture_output=True)
            if result.returncode:
                self.skipTest("Windows junction creation unavailable")
            with self.assertRaisesRegex(ValueError, "symlink/junction"):
                kit.generate(link / "must-not-create")
            self.assertFalse((real / "must-not-create").exists())


if __name__ == "__main__":
    unittest.main()
