import csv
import json
import random
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from app.analysis import analyze_items, analyze_overall, build_score_matrix
from app.data_loader import ExamData, ItemInfo, StudentResponse
from app.export_privacy import (
    csv_safe_cell, pseudonym_ids, pseudonymize_evidence_payload, sanitize_csv_text, student_hash,
    student_result_table,
)

# 명부 순서(0,1,2번 학생)와 일부러 다르게 둔 가명
SHUFFLED = ["학생 003", "학생 001", "학생 002"]

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
    window._pseudonym_cache = (window.exam, list(SHUFFLED))
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

    def test_pseudonym_ids_are_a_shuffled_permutation(self):
        ids = pseudonym_ids(50, random.Random(7))
        self.assertEqual(sorted(ids), [f"학생 {n:03d}" for n in range(1, 51)])
        self.assertNotEqual(ids, sorted(ids))
        self.assertEqual(ids, pseudonym_ids(50, random.Random(7)))
        self.assertEqual(pseudonym_ids(0), [])

    def test_pseudonym_ids_use_system_random_by_default(self):
        with patch("app.export_privacy.random.SystemRandom") as system_random:
            pseudonym_ids(3)
        system_random.assert_called_once_with()
        system_random.return_value.shuffle.assert_called_once()

    def test_pseudonym_text_order_matches_number_order_past_999(self):
        ids = pseudonym_ids(1200, random.Random(1))
        self.assertEqual(sorted(ids), [f"학생 {n:04d}" for n in range(1, 1201)])

    def test_student_table_is_pseudonymized_and_sorted_by_pseudonym(self):
        exam = _exam()
        levels = ["A", "C", "E"]
        headers, rows = student_result_table(exam.students, levels, include_identity=False, pseudonyms=SHUFFLED)
        self.assertEqual(headers[:2], ["가명 ID", "학급"])
        flat = json.dumps(rows, ensure_ascii=False)
        for student in exam.students:
            for value in (student.sid, student.class_no, student.name):
                self.assertNotIn(value, flat)
        # 행은 가명 순서이고, 가명과 그 학생의 성취도 짝은 유지된다.
        self.assertEqual([(row[0], row[-1]) for row in rows], [("학생 001", "C"), ("학생 002", "E"), ("학생 003", "A")])

        headers, rows = student_result_table(exam.students, levels, include_identity=True)
        self.assertEqual(headers[:3], ["학번", "반/번호", "이름"])
        self.assertEqual(rows[0][:3], ["S900", "1/1", "합성학생가"])

    def test_evidence_payload_pseudonymized_sorted_without_mutating_source(self):
        payload = {
            "students": [
                {"id": "S900", "classNo": "1/1", "gradeClass": "1", "name": "합성학생가", "level": "A"},
                {"id": "S901", "classNo": "1/2", "gradeClass": "1", "name": "합성학생나", "level": "C"},
            ],
            "sourceFiles": {"response": "/Users/someone/Desktop/정오표.xlsx", "cuts": "C:\\t\\컷.xlsx"},
        }
        result = pseudonymize_evidence_payload(payload, ["학생 002", "학생 001"])
        self.assertEqual(result["students"], [
            {"id": "학생 001", "classNo": "", "gradeClass": "1", "name": "학생 001", "level": "C"},
            {"id": "학생 002", "classNo": "", "gradeClass": "1", "name": "학생 002", "level": "A"},
        ])
        self.assertEqual(result["sourceFiles"], {"response": "정오표.xlsx", "cuts": "컷.xlsx"})
        self.assertEqual([s["name"] for s in payload["students"]], ["합성학생가", "합성학생나"])

    def test_sanitize_csv_text_escapes_formulas_but_keeps_numbers_bom_and_newlines(self):
        text = '\ufeff문항,메모,차이\r\n1,"=HYPERLINK(""x"")",-5\r\n2,"+SUM(A1)",3.5\r\n'
        result = sanitize_csv_text(text)
        self.assertTrue(result.startswith("\ufeff"))
        rows = list(csv.reader(result[1:].splitlines()))
        self.assertEqual(rows[1], ["1", "'=HYPERLINK(\"x\")", "-5"])
        self.assertEqual(rows[2], ["2", "'+SUM(A1)", "3.5"])
        self.assertIn("\r\n", result)
        self.assertEqual(sanitize_csv_text("a,b\n1,2\n"), "a,b\n1,2\n")

    def test_student_hash_is_keyed_and_hides_identifiers(self):
        key, other = b"k" * 32, b"o" * 32
        value = student_hash(key, "S900", "1/1", "합성학생가")
        self.assertEqual(value, student_hash(key, " S900 ", "2/9", "다른이름"))  # 학번이 있으면 학번으로 연결
        self.assertNotEqual(value, student_hash(other, "S900"))
        self.assertNotIn("S900", value)
        self.assertEqual(len(value), 24)
        self.assertEqual(student_hash(key, "", "1/1", "가"), student_hash(key, None, "1/1", "가"))
        self.assertNotEqual(student_hash(key, "", "1/1", "가"), student_hash(key, "", "1/2", "가"))


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
            rows = list(csv.reader(text.splitlines()))
            self.assertEqual(rows[0][0], "가명 ID")
            # 행은 가명 순서: 학생 001=명부 2번째(50점), 002=3번째(0점), 003=1번째(100점)
            self.assertEqual([(row[0], float(row[7])) for row in rows[1:]],
                             [("학생 001", 50.0), ("학생 002", 0.0), ("학생 003", 100.0)])

    def test_pseudonyms_stay_fixed_per_analysis_and_renew_for_new_data(self):
        window = _window()
        with patch("app.main_window.pseudonym_ids", return_value=["학생 002", "학생 003", "학생 001"]) as make:
            first = window._student_pseudonyms()
            self.assertEqual(first, SHUFFLED)
            self.assertIs(window._student_pseudonyms(), first)
            make.assert_not_called()
            window.exam = _exam()
            renewed = window._student_pseudonyms()
            self.assertIs(window._student_pseudonyms(), renewed)
        make.assert_called_once_with(3)
        self.assertEqual(renewed, ["학생 002", "학생 003", "학생 001"])
        self.assertIs(window._pseudonym_cache[0], window.exam)

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
        # CSV와 같은 가명, 가명 순서로 정렬, 가명과 점수 짝 유지
        self.assertEqual([(s["name"], s["finalScore"]) for s in payload["students"]],
                         [("학생 001", 50.0), ("학생 002", 0.0), ("학생 003", 100.0)])
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
                header = [cell.value for cell in workbook["학생"][1]]
                self.assertEqual(header[5], "환산점수")
                pairs = [(row[0], row[5]) for row in workbook["학생"].iter_rows(min_row=2, values_only=True)]
                self.assertEqual(pairs, [("학생 001", 50.0), ("학생 002", 0.0), ("학생 003", 100.0)])
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


    def _portfolio_window(self, directory):
        from PySide6.QtCore import QSettings
        window = _window()
        window.settings = QSettings(str(Path(directory) / "settings.ini"), QSettings.IniFormat)
        store = Path(directory) / "snapshots"
        store.mkdir()
        window._portfolio_store_dir = lambda: store
        return window, store

    def test_portfolio_snapshot_stores_only_keyed_hash_and_links_legacy_files(self):
        with TemporaryDirectory() as directory:
            window, store = self._portfolio_window(directory)
            snapshot = window._current_subject_snapshot()
            text = json.dumps(snapshot, ensure_ascii=False)
            for value in ("S900", "1/1", "합성학생가", "HYPERLINK"):
                self.assertNotIn(value, text)
            self.assertEqual(snapshot["version"], 2)
            key_hex = window.settings.value("privacy/portfolio_hash_key")
            self.assertEqual(len(bytes.fromhex(key_hex)), 32)
            self.assertEqual(window._portfolio_hash_key().hex(), key_hex)  # 두 번째 호출은 같은 키

            (store / "new.json").write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
            legacy = {"version": 1, "subject": "예전과목", "students": [
                {"class_no": "1/1", "sid": "S900", "name": "합성학생가", "level": "B", "final_score": 80}]}
            (store / "old.json").write_text(json.dumps(legacy, ensure_ascii=False), encoding="utf-8")

            rows = window._load_portfolio_rows()
            first = [row for row in rows if row["subject"] in ("합성과목", "예전과목") and row["class_no"] == "1/1"]
            self.assertEqual({row["subject"] for row in first}, {"합성과목", "예전과목"})
            self.assertEqual(len({window._portfolio_student_key(row) for row in first}), 1)
            self.assertEqual({row["name"] for row in first}, {"합성학생가"})  # 불러온 분석 자료로 화면에서만 복원

            window.exam = None  # 분석 자료가 없으면 이름을 알 수 없다
            unresolved = [row for row in window._load_portfolio_rows() if row["subject"] == "합성과목"]
            self.assertTrue(all(row["name"].startswith("학생#") and row["class_no"] == "" for row in unresolved))

    def test_pseudonym_mapping_is_shown_on_screen_only(self):
        window = _window()
        with TemporaryDirectory() as directory, \
             patch("app.main_window.QDialog"), patch("app.main_window.QVBoxLayout"), \
             patch("app.main_window.QLabel"), patch("app.main_window.QPushButton"), \
             patch("app.main_window.QTableWidget"), patch("app.main_window._set_item") as set_item, \
             patch("app.main_window.QFileDialog") as files:
            before = set(Path(directory).iterdir())
            window.show_pseudonym_mapping()
            self.assertEqual(set(Path(directory).iterdir()), before)
        files.getSaveFileName.assert_not_called()
        cells = {}
        for call in set_item.call_args_list:
            _, r, c, value = call.args
            cells[(r, c)] = value
        self.assertEqual([cells[(r, 0)] for r in range(3)], ["학생 001", "학생 002", "학생 003"])
        self.assertEqual([cells[(r, 3)] for r in range(3)], ["합성학생나", FORMULA_NAME, "합성학생가"])


if __name__ == "__main__":
    unittest.main()
