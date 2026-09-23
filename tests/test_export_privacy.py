import csv
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from app.analysis import analyze_items, analyze_overall, build_score_matrix
from app.data_loader import ExamData, ItemInfo, StudentResponse
from app.export_privacy import (
    csv_safe_cell, pseudonym_id, pseudonymize_evidence_payload, student_result_table,
)

try:
    from app.main_window import MainWindow
except ModuleNotFoundError as exc:
    MainWindow = None
    MAIN_WINDOW_IMPORT_ERROR = exc
else:
    MAIN_WINDOW_IMPORT_ERROR = None

FORMULA_NAME = '=HYPERLINK("https://example.invalid","x")'
REAL_NAMES = ["합성학생가", "합성학생나", FORMULA_NAME]


def _exam():
    exam = ExamData(subject="합성과목", grade="1", semester="1학기")
    exam.items = [
        ItemInfo(number=1, item_type="선택형", difficulty="쉬움", score=50.0, answer="3"),
        ItemInfo(number=2, item_type="선택형", difficulty="보통", score=50.0, answer="2"),
    ]
    answers = [{1: ".", 2: "."}, {1: ".", 2: "4"}, {1: "1", 2: "4"}]
    for index, (name, answer) in enumerate(zip(REAL_NAMES, answers)):
        total = 50.0 * sum(1 for value in answer.values() if value == ".")
        exam.students.append(StudentResponse(
            sid=f"S90{index}", class_no=f"1/{index + 1}", grade_class="1", name=name,
            answers=answer, multi_score=total, total=total, final_score=total,
        ))
    exam.source_files = {"response": "/Users/someone/Desktop/정오표.xlsx", "iteminfo": "C:\\Users\\t\\문항정보표.xlsx"}
    return exam


def _window():
    window = MainWindow.__new__(MainWindow)
    window.exam = _exam()
    score, _, _ = build_score_matrix(window.exam)
    window.overall = analyze_overall(window.exam, score)
    window.item_stats = analyze_items(window.exam)[0]
    window.fs_cuts = Mock(path=Mock(return_value=""))
    window.statusBar = Mock()
    return window


def _all_xlsx_text(path):
    import openpyxl
    workbook = openpyxl.load_workbook(path)
    try:
        return workbook, [cell for sheet in workbook for row in sheet.iter_rows() for cell in row]
    except Exception:
        workbook.close()
        raise


class ExportPrivacyHelperTests(unittest.TestCase):
    def test_csv_safe_cell_escapes_formula_prefixes_only_for_text(self):
        for text in ("=1+1", "+1", "-1", "@SUM(A1)", "\tx", "\rx"):
            self.assertEqual(csv_safe_cell(text), "'" + text)
        for value in ("학생 001", "A/B", "", -3.5, 0, None):
            self.assertEqual(csv_safe_cell(value), value)

    def test_student_table_is_pseudonymized_by_default(self):
        exam = _exam()
        levels = ["A", "C", "E"]
        headers, rows = student_result_table(exam.students, levels, include_identity=False)
        self.assertEqual(headers[:2], ["가명 ID", "학급"])
        flat = json.dumps(rows, ensure_ascii=False)
        for student in exam.students:
            for value in (student.sid, student.class_no, student.name):
                self.assertNotIn(value, flat)
        self.assertEqual([row[0] for row in rows], [pseudonym_id(i) for i in range(3)])
        self.assertEqual([row[-1] for row in rows], levels)

        headers, rows = student_result_table(exam.students, levels, include_identity=True)
        self.assertEqual(headers[:3], ["학번", "반/번호", "이름"])
        self.assertEqual(rows[0][:3], ["S900", "1/1", "합성학생가"])

    def test_evidence_payload_pseudonymized_without_mutating_source(self):
        payload = {
            "students": [{"id": "S900", "classNo": "1/1", "gradeClass": "1", "name": "합성학생가", "level": "A"}],
            "sourceFiles": {"response": "/Users/someone/Desktop/정오표.xlsx", "cuts": "C:\\t\\컷.xlsx"},
        }
        result = pseudonymize_evidence_payload(payload)
        self.assertEqual(result["students"][0], {
            "id": "학생 001", "classNo": "", "gradeClass": "1", "name": "학생 001", "level": "A",
        })
        self.assertEqual(result["sourceFiles"], {"response": "정오표.xlsx", "cuts": "컷.xlsx"})
        self.assertEqual(payload["students"][0]["name"], "합성학생가")


@unittest.skipIf(MainWindow is None, f"app.main_window unavailable: {MAIN_WINDOW_IMPORT_ERROR}")
class ExportPrivacyWindowTests(unittest.TestCase):
    def _export_csv(self, directory, *, check_real: bool, confirm: bool):
        window = _window()
        with patch("app.main_window.QMessageBox") as messages, \
             patch("app.main_window.QCheckBox") as checkbox, \
             patch("app.main_window.QFileDialog.getExistingDirectory", return_value=directory):
            messages.return_value.exec.return_value = messages.No  # CSV만
            messages.warning.return_value = messages.Yes if confirm else messages.No
            checkbox.return_value.isChecked.return_value = check_real
            window.export_csv()
        return messages

    def test_csv_export_defaults_to_pseudonyms(self):
        with TemporaryDirectory() as directory:
            messages = self._export_csv(directory, check_real=False, confirm=False)
            messages.warning.assert_not_called()
            text = (Path(directory) / "학생결과.csv").read_text(encoding="utf-8-sig")
            for value in ("S900", "1/1", "합성학생가", "합성학생나", "HYPERLINK"):
                self.assertNotIn(value, text)
            self.assertIn("가명 ID", text)
            self.assertIn("학생 003", text)

    def test_real_name_csv_needs_warning_confirmation(self):
        with TemporaryDirectory() as directory:
            messages = self._export_csv(directory, check_real=True, confirm=False)
            messages.warning.assert_called_once()
            self.assertEqual(list(Path(directory).iterdir()), [])

        with TemporaryDirectory() as directory:
            self._export_csv(directory, check_real=True, confirm=True)
            with open(Path(directory) / "학생결과.csv", encoding="utf-8-sig", newline="") as f:
                rows = list(csv.reader(f))
            self.assertEqual(rows[0][:3], ["학번", "반/번호", "이름"])
            self.assertEqual(rows[1][2], "합성학생가")
            self.assertEqual(rows[3][2], "'" + FORMULA_NAME)

    def test_web_calculator_payload_has_no_identity_or_folders(self):
        window = _window()
        payload = window._build_spliter_evidence_payload()
        text = json.dumps(payload, ensure_ascii=False)
        for value in ("S900", "합성학생가", "HYPERLINK", "/Users/", "C:\\\\Users"):
            self.assertNotIn(value, text)
        self.assertEqual(payload["students"][0]["name"], "학생 001")
        self.assertEqual(payload["sourceFiles"]["response"], "정오표.xlsx")
        self.assertEqual(window._build_spliter_evidence_payload(include_identity=True)["students"][0]["name"], "합성학생가")

    def _export_evidence(self, path, *, check_real: bool, confirm: bool, save: bool = True):
        window = _window()
        with patch("app.main_window.QMessageBox") as messages, \
             patch("app.main_window.QCheckBox") as checkbox, \
             patch("app.main_window.QFileDialog.getSaveFileName", return_value=(str(path), "")) as dialog:
            messages.return_value.exec.return_value = messages.Save if save else messages.Cancel
            messages.warning.return_value = messages.Yes if confirm else messages.No
            checkbox.return_value.isChecked.return_value = check_real
            window.export_spliter_evidence()
        return messages, dialog

    def test_evidence_xlsx_defaults_to_pseudonyms(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "근거.xlsx"
            messages, _ = self._export_evidence(path, check_real=False, confirm=False)
            messages.warning.assert_not_called()
            workbook, cells = _all_xlsx_text(path)
            try:
                values = [str(cell.value) for cell in cells if cell.value is not None]
                for value in ("S900", "합성학생가", "HYPERLINK"):
                    self.assertFalse(any(value in text for text in values), value)
                self.assertIn("학생 001", values)
            finally:
                workbook.close()

    def test_evidence_real_names_need_confirmation_and_stay_text(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "근거.xlsx"
            _, dialog = self._export_evidence(path, check_real=True, confirm=False)
            dialog.assert_not_called()
            self.assertFalse(path.exists())
            _, dialog = self._export_evidence(path, check_real=False, confirm=False, save=False)
            dialog.assert_not_called()

            self._export_evidence(path, check_real=True, confirm=True)
            workbook, cells = _all_xlsx_text(path)
            try:
                formula_cells = [cell for cell in cells if cell.value == FORMULA_NAME]
                self.assertTrue(formula_cells)
                self.assertTrue(all(cell.data_type == "s" for cell in formula_cells))
                self.assertTrue(any(cell.value == "합성학생가" for cell in cells))
            finally:
                workbook.close()


if __name__ == "__main__":
    unittest.main()
