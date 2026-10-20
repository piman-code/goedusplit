from tests.runtime_isolation import ensure_isolated
ensure_isolated()
import copy
import unittest
from pathlib import Path
import openpyxl
from PySide6.QtWidgets import QApplication,QDialog
from tests import test_folder_round_batch as batch_fixtures
from app.folder_batch import discover_round_groups
from app.analysis_preparation import AnalysisPreparationDialog
from app.work_session_ui import capture_ui_state

class AnalysisPreparationTests(unittest.TestCase):
    setUpClass=classmethod(batch_fixtures.FolderRoundBatchTests.setUpClass.__func__)
    setUp=batch_fixtures.FolderRoundBatchTests.setUp

    def inputs(self):
        for number in (1,2):
            book=openpyxl.Workbook();ws=book.active
            ws.append(['구분','A/B','B/C','C/D','D/E','E/미도달'])
            ws.append(['평균',90-number,80-number,70-number,60-number,40-number])
            book.save(self.folder/f'2026학년도 1학기 {number}차 분할점수.xlsx')
            book=openpyxl.Workbook();ws=book.active
            ws.append([f'2026학년도 1학기 {number}차 교과목 : 합성수학 만점 : 100.00'])
            ws.append(['반번호',1,2])
            for i in range(10):ws.append([i+1,99-i*2-number,98-i*2-number])
            ws.append(['응시생수'])
            book.save(self.folder/f'2026학년도 1학기 {number}차 교과목별일람표.xlsx')
        return discover_round_groups(self.folder,'1학기 1차')[:2]

    def test_actual_cuts_grades_and_independent_round_ratios(self):
        groups=self.inputs();before=capture_ui_state(self.w)
        dialog=AnalysisPreparationDialog(self.w,groups);self.addCleanup(dialog.close)
        first,second=dialog.pages
        self.assertIn('A ≥ 89.00',first.cuts_label.text());self.assertIn('A ≥ 88.00',second.cuts_label.text())
        self.assertIn('미계산',first.grade_label.text())
        first.calculate.click();second.calculate.click()
        self.assertIsNotNone(first.reports);self.assertIsNotNone(second.reports)
        self.assertNotEqual(first.grade_label.text(),second.grade_label.text())
        first.file_weights.setChecked(False);second.file_weights.setChecked(False)
        first.pencil.setValue(60);second.pencil.setValue(70)
        dialog.tabs.setCurrentIndex(1);dialog.tabs.setCurrentIndex(0)
        self.assertEqual(60,first.pencil.value());self.assertEqual(70,second.pencil.value())
        self.assertEqual(before,capture_ui_state(self.w))
        dialog.accept()
        self.assertEqual(QDialog.DialogCode.Accepted,dialog.result())
        self.assertEqual([60,70],[g['pencil_weight'] for g in dialog.result_groups])
        self.assertTrue(self.w._analyze_folder_groups(dialog.result_groups))
        self.assertEqual((60,40),(self.w.exam.weight_pencil,self.w.exam.weight_perform))
        self.assertEqual(89,self.w.exam.cut_scores['A'])
        self.assertEqual(first.reports,self.w._last_grade5_cut_reports)
        from app.work_sessions import WorkSessionStore,build_session
        store=WorkSessionStore(self.root/'prepared-work')
        saved=store.read(store.save(build_session(self.w.exam,self.w.perform_data,capture_ui_state(self.w),None)))
        cached=list(saved['ui_state']['portfolio_analysis_sessions'].values())
        self.assertEqual([first.reports,second.reports],[p['metadata']['analysis_preparation']['grade5_reports'] for p in cached])

    def test_changed_report_invalidates_calculation_and_cancel_preserves_everything(self):
        groups=self.inputs();before=capture_ui_state(self.w)
        dialog=AnalysisPreparationDialog(self.w,groups);self.addCleanup(dialog.close)
        page=dialog.pages[0];page.calculate.click();self.assertIsNotNone(page.reports)
        page.combos['grade5_report'].setCurrentIndex(0)
        self.assertIsNone(page.reports);self.assertIn('미계산',page.grade_label.text())
        page.pencil.setValue(75);dialog.reject()
        self.assertEqual(before,capture_ui_state(self.w))

    def test_bad_round_is_reported_while_valid_round_proceeds(self):
        groups=self.inputs();before=capture_ui_state(self.w)
        dialog=AnalysisPreparationDialog(self.w,groups);self.addCleanup(dialog.close)
        page=dialog.pages[0];combo=page.combos['cuts'];combo.addItem('손상 파일',str(self.root/'missing.xlsx'));combo.setCurrentIndex(combo.count()-1)
        self.assertIn('파일 읽기 실패',page.cuts_label.text())
        dialog.accept();self.assertEqual(QDialog.DialogCode.Accepted,dialog.result())
        self.assertEqual([groups[1]['key']],[g['key'] for g in dialog.result_groups])
        self.assertEqual(1,len(dialog.skipped_groups));self.assertIn('분할점수',dialog.skipped_groups[0]['reason'])
        self.assertTrue(dialog.status.text());self.assertEqual(before,capture_ui_state(self.w))

    def test_missing_optional_files_use_only_actual_written_scores(self):
        groups=self.inputs();dialog=AnalysisPreparationDialog(self.w,groups[:1]);self.addCleanup(dialog.close)
        page=dialog.pages[0];page.combos['iteminfo'].setCurrentIndex(0)
        page.file_weights.setChecked(False);page.pencil.setValue(60)
        for _,check in page.perform_checks:check.setChecked(False)
        self.assertFalse(page.error);self.assertIn('학기 총점이 아닙니다',page.validation.text())
        dialog.accept();self.assertEqual(QDialog.DialogCode.Accepted,dialog.result())
        entry=dialog.result_groups[0];self.assertEqual((100,0),(entry['pencil_weight'],entry['perform_weight']))
        self.assertTrue(entry['warnings']);self.assertFalse(entry['iteminfo'])

    def test_all_invalid_rounds_stay_open_with_reasons(self):
        dialog=AnalysisPreparationDialog(self.w,self.inputs()[:1]);self.addCleanup(dialog.close)
        combo=dialog.pages[0].combos['cuts'];combo.addItem('손상',str(self.root/'missing.xlsx'));combo.setCurrentIndex(combo.count()-1)
        dialog.accept();self.assertEqual(QDialog.DialogCode.Rejected,dialog.result())
        self.assertFalse(dialog.result_groups);self.assertEqual(1,len(dialog.skipped_groups))

    def test_explicit_report_round_conflict_never_shows_calculated_values(self):
        groups=self.inputs();dialog=AnalysisPreparationDialog(self.w,groups);self.addCleanup(dialog.close)
        page=dialog.pages[0];page.calculate.click();self.assertIsNotNone(page.reports)
        wrong=groups[1]['grade5_report'];combo=page.combos['grade5_report']
        combo.addItem('다른 회차',wrong);combo.setCurrentIndex(combo.count()-1);page.calculate.click()
        self.assertIsNone(page.reports)
        self.assertIn('미계산',page.grade_label.text())
        self.assertIn('시험 정보',page.validation.text())

    def test_900_width_has_no_horizontal_scroll_and_actual_file_ratio_is_visible(self):
        from PySide6.QtTest import QTest
        dialog=AnalysisPreparationDialog(self.w,self.inputs());self.addCleanup(dialog.close)
        dialog.resize(900,700);dialog.show();QTest.qWait(80)
        page=dialog.pages[0];page.file_weights.setChecked(True);QTest.qWait(30)
        scroll=dialog.tabs.widget(0)
        self.assertEqual(0,scroll.horizontalScrollBar().maximum())
        self.assertLessEqual(page.width(),scroll.viewport().width())
        self.assertEqual(60,page.pencil.value())
        self.assertFalse(page.pencil.isEnabled())
        self.assertIn('지필 60%',page.perform_label.text())
        for widget in (page.pencil,page.perform_label,page.file_weights,page.calculate,page.cut_source):
            point=widget.mapTo(page,widget.rect().bottomRight())
            self.assertLess(point.x(),page.width())

    def test_computed_grade_lines_receive_full_height_after_click(self):
        from PySide6.QtTest import QTest
        dialog=AnalysisPreparationDialog(self.w,self.inputs());self.addCleanup(dialog.close)
        dialog.resize(900,700);dialog.show();QTest.qWait(50)
        page=dialog.pages[0];page.calculate.click();QTest.qWait(50)
        self.assertIsNotNone(page.reports)
        self.assertIn('5등급',page.grade_label.text())
        for label in (page.grade_label,page.cuts_label):
            self.assertTrue(label.isHidden())
        self.assertTrue(page.grade_source.isVisible())
        self.assertTrue(page.cut_source.isVisible())
        self.assertEqual(5,len(page.grade_cards))
        self.assertTrue(all(cell.text()!='—' and cell.isVisible() for cell in page.grade_cards.values()))
        self.assertEqual(0,dialog.tabs.widget(0).horizontalScrollBar().maximum())
        page.combos['grade5_report'].setCurrentIndex(0);QTest.qWait(30)
        self.assertIn('미계산',page.grade_label.text())
        self.assertTrue(all(cell.text()=='—' for cell in page.grade_cards.values()))

    def test_wrapped_value_height_shrinks_after_narrow_initial_layout(self):
        from app.analysis_preparation import WrappedValueLabel
        from PySide6.QtTest import QTest
        label=WrappedValueLabel();self.addCleanup(label.close)
        label.resize(60,20);label.setText('성취도 분할점수 · 현재 화면 설정\nA ≥ 90.00   B ≥ 80.00   C ≥ 70.00   D ≥ 60.00   E ≥ 40.00')
        label.show();QTest.qWait(30);narrow=label.height()
        label.resize(360,label.height());QTest.qWait(30)
        self.assertLess(label.height(),narrow)
        self.assertLessEqual(label.height(),4*label.fontMetrics().height()+16)
        label.setText('미계산');QTest.qWait(30)
        self.assertLessEqual(label.height(),2*label.fontMetrics().height())
