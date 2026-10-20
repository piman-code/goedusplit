"""Synthetic native-widget boundaries for the portfolio presentation."""
from tests.runtime_isolation import ensure_isolated
ensure_isolated()

import copy
from pathlib import Path
import tempfile
from dataclasses import replace
import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLineEdit, QSplitter
from app.main_window import MainWindow
from app.work_session_ui import capture_ui_state, apply_python_state
from app.work_sessions import build_session, prepare_session
from app.portfolio import write_snapshot
from tests.test_work_sessions import synthetic_domain


class PortfolioViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        # Full-work rows are rehashed against the current window's identity key.
        # A shared process store would therefore leak earlier cases' synthetic
        # work records into later cases even though their QSettings are isolated.
        self.store_directory = tempfile.TemporaryDirectory(prefix="portfolio-view-case-")
        self.addCleanup(self.store_directory.cleanup)
        case_root = Path(self.store_directory.name)
        self.store_patch = patch.object(MainWindow, "_ai_material_root_dir", lambda _window: case_root)
        self.store_patch.start()
        self.addCleanup(self.store_patch.stop)
        self.web_patch = patch('app.main_window.QWebEngineView', None)
        self.web_patch.start()
        self.addCleanup(self.web_patch.stop)
        self.window = MainWindow()
        self.addCleanup(self.window.close)
        exam, _ = synthetic_domain()
        template = exam.students[0]
        exam.students = [replace(template, sid=f'synthetic-{i}', name=f'합성학생{i}',
                                 class_no=f'{klass}/{number}', grade_class=str(klass),
                                 total=score, final_score=score)
                         for i, (klass,number,score) in enumerate(
                             [(1,1,100),(1,2,50),(2,1,40),(2,2,90),(2,3,0)],1)]
        exam.use_perform = False
        exam.weight_pencil, exam.weight_perform = 100, 0
        prepared = prepare_session(build_session(exam, None, capture_ui_state(self.window), None))
        apply_python_state(self.window, prepared)
        self.window.refresh_portfolio_tab()

    def test_snapshot_class_means_use_each_current_class_population(self):
        w = self.window
        snapshot = w._current_subject_snapshot()
        identity = w._current_identity_by_hash()
        expected = {'1':75.0, '2':43.33}
        self.assertEqual(5,len(snapshot['students']))
        for student in snapshot['students']:
            class_no, _ = identity[student['student_hash']]
            self.assertAlmostEqual(expected[class_no.split('/')[0]],student['class_mean'],places=2)
        self.assertEqual({75.0,43.33},{round(s['class_mean'],2) for s in snapshot['students']})

    def test_legacy_snapshot_mean_remains_unknown_in_chart_and_detail(self):
        w = self.window
        legacy = copy.deepcopy(w._current_subject_snapshot())
        legacy['subject'] = '과거 합성과목'
        for student in legacy['students']:
            student.pop('class_mean',None)
        path = write_snapshot(w._portfolio_store_dir(),legacy)
        before = path.read_bytes()
        w.refresh_portfolio_tab()
        w.combo_portfolio_student.setCurrentIndex(1)
        w.combo_portfolio_subject.setCurrentIndex(w.combo_portfolio_subject.findData('과거 합성과목'))
        w.portfolio_view.sync()
        self.assertEqual(0,len(w.portfolio_growth_chart.points))
        self.assertEqual(1,len(w.portfolio_view.model['unknown_points']))
        self.assertIsNone(w.portfolio_view.selected_point['class_mean'])
        self.assertIn('회차 미확인',w.portfolio_view.round_combo.currentText())
        self.assertEqual(before,path.read_bytes())

    def test_counseling_masks_new_student_list_header_and_combo(self):
        w = self.window
        w.combo_portfolio_student.setCurrentIndex(1)
        w.portfolio_view.sync()
        real_names = [student.name for student in w.exam.students]
        real_classes = [student.class_no for student in w.exam.students]
        w.btn_counsel_mode.setChecked(True)
        w.portfolio_view.sync()
        labels = [w.portfolio_student_list.item(i).text() for i in range(w.portfolio_student_list.count())]
        labels += [w.lbl_portfolio_summary.text(),w.portfolio_view.heading.text()]
        labels += [w.combo_portfolio_student.itemText(i) for i in range(1,w.combo_portfolio_student.count())]
        self.assertTrue(labels)
        self.assertFalse(any(identity in text for identity in real_names+real_classes for text in labels))
        self.assertEqual(QLineEdit.Password,w.le_portfolio_search.echoMode())
        w.btn_counsel_mode.setChecked(False)
        w.portfolio_view.sync()
        self.assertTrue(any(name in w.portfolio_student_list.item(0).text() for name in real_names))

    def test_108_work_without_new_portfolio_widgets_still_restores(self):
        w = self.window
        w.le_search.setText('합성학생1')
        state = capture_ui_state(w)
        # Reconstruct the 1.0.8 UI schema before the new table and splitter existed.
        state['table_headers'].pop('portfolio_timeline_table',None)
        state['widgets'].pop('portfolio_history_toggle',None)
        # The new view deliberately adds no splitter, preserving positional
        # layout compatibility with existing 1.0.8 snapshots.
        self.assertFalse(hasattr(w, 'portfolio_content_splitter'))
        payload = build_session(w.exam,w.perform_data,state,None)
        w.le_search.setText('B')
        w.exam.subject = 'B 과목'
        apply_python_state(w,prepare_session(payload))
        self.assertEqual('합성학생1',w.le_search.text())
        self.assertEqual(payload['metadata']['subject'],w.exam.subject)
        self.assertEqual(5,len(w.exam.students))
        self.assertTrue(hasattr(w,'portfolio_timeline_table'))

    def test_full_work_restores_history_toggle_and_original_history_table(self):
        w = self.window
        w.portfolio_history_toggle.setChecked(True)
        payload = build_session(w.exam,w.perform_data,capture_ui_state(w),None)
        w.portfolio_history_toggle.setChecked(False)
        self.assertIsNot(w.table_portfolio,w.portfolio_view.stack.currentWidget())
        apply_python_state(w,prepare_session(payload))
        self.assertTrue(w.portfolio_history_toggle.isChecked())
        self.assertIs(w.table_portfolio,w.portfolio_view.stack.currentWidget())

    def _select_two_rounds(self):
        w = self.window
        w.exam.semester = '2026학년도 1학기 2차'
        old = copy.deepcopy(w._current_subject_snapshot())
        old.update(semester='2026학년도 1학기 1차', year=2026, semester_no=1, round_no=1, round=1)
        for student in old['students']:
            student['final_score'] = 20.0
        write_snapshot(w._portfolio_store_dir(), old)
        w.refresh_portfolio_tab()
        w.combo_portfolio_student.setCurrentIndex(1)
        return w.portfolio_view

    def test_v4_selector_replaces_side_rail_and_details_are_real(self):
        view = self._select_two_rounds()
        self.window.tabs.setCurrentWidget(self.window.tab_portfolio)
        self.window.show(); self.app.processEvents()
        self.assertFalse(self.window.portfolio_student_list.isVisible())
        self.assertTrue(self.window.combo_portfolio_student.isVisible())
        self.assertEqual(280, view.chart.height())
        self.assertEqual(['Data','수행평가','문항','답지반응','성취기준'],
                         [view.tabs.tabText(i) for i in range(view.tabs.count())])
        self.assertTrue(view.details['tabs']['data']['available'])
        self.assertTrue(view.details['tabs']['items']['available'])
        self.assertGreater(view.tables['data'].rowCount(), 0)
        self.assertEqual('100.0점', view.summary_values[0].text())
        self.assertEqual('+80.0점', view.summary_values[1].text())
        self.assertEqual('+25.0점', view.summary_values[2].text())

    def test_v4_graph_keyboard_and_round_buttons_select_exact_details(self):
        from PySide6.QtTest import QTest
        view = self._select_two_rounds()
        self.window.tabs.setCurrentWidget(self.window.tab_portfolio)
        self.window.show(); self.app.processEvents()
        self.assertEqual(2, len(view.chart.points))
        QTest.keyClick(view.chart, Qt.Key_Home)
        self.assertEqual(0, view.round_combo.currentIndex())
        self.assertIs(view.selected_round_point, view.chart.points[0])
        self.assertFalse(view.details['tabs']['items']['available'])
        view.next.click()
        self.assertEqual(1, view.round_combo.currentIndex())
        self.assertTrue(view.details['tabs']['items']['available'])
        view.previous.click()
        self.assertEqual(0, view.round_combo.currentIndex())

    def test_v4_full_work_restores_round_detail_tab_and_visibility(self):
        view = self._select_two_rounds()
        view.round_combo.setCurrentIndex(0)
        view.tabs.setCurrentIndex(3)
        view.show_mean.setChecked(False)
        payload = build_session(self.window.exam, self.window.perform_data, capture_ui_state(self.window), None)
        selected_round = view.round_combo.currentData()
        view.round_combo.setCurrentIndex(1); view.tabs.setCurrentIndex(0); view.show_mean.setChecked(True)
        apply_python_state(self.window, prepare_session(payload))
        self.assertEqual(selected_round, view.round_combo.currentData())
        self.assertEqual(3, view.tabs.currentIndex())
        self.assertFalse(view.show_mean.isChecked())
        self.assertFalse(view.chart.show_mean)
        self.assertIs(view.selected_round_point, view.chart.points[0])

    def test_v4_legacy_work_without_new_detail_tabs_and_controls_restores(self):
        view = self._select_two_rounds()
        state = capture_ui_state(self.window)
        state['tabs'] = [tab for tab in state['tabs'] if tab['widget'] != 'portfolio_detail_tabs']
        for key in ('portfolio_round_combo','portfolio_version_combo','portfolio_show_student','portfolio_show_mean'):
            state['widgets'].pop(key,None)
        payload = build_session(self.window.exam,self.window.perform_data,state,None)
        self.window.le_search.setText('temporary')
        apply_python_state(self.window, prepare_session(payload))
        self.assertEqual(state['widgets']['le_search'], self.window.le_search.text())
        self.assertEqual(5, view.tabs.count())

    def test_v4_saved_full_work_remains_accessible_beside_latest_summary(self):
        w = self.window
        w.exam.semester = '2026학년도 1학기 2차'
        w.work_sessions.store().save(build_session(w.exam, w.perform_data, capture_ui_state(w), None))
        write_snapshot(w._portfolio_store_dir(), w._current_subject_snapshot())
        w.refresh_portfolio_tab(); w.combo_portfolio_student.setCurrentIndex(1)
        view = w.portfolio_view
        kinds = [point.get('source_kind') for point in view._versions]
        self.assertIn('work-session', kinds)
        self.assertIn('current', kinds)
        full_index = kinds.index('work-session')
        view.version_combo.setCurrentIndex(full_index)
        self.assertTrue(view.details['tabs']['items']['available'])
        self.assertEqual('저장된 전체 작업', view.badge.text())
        saved_version = view.version_combo.currentData()
        payload = build_session(w.exam, w.perform_data, capture_ui_state(w), None)
        view.version_combo.setCurrentIndex(kinds.index('current'))
        apply_python_state(w, prepare_session(payload))
        self.assertEqual(saved_version, view.version_combo.currentData())
        self.assertEqual('work-session', view.selected_point['source_kind'])

    def test_v4_search_filters_dropdown_without_losing_selection(self):
        w = self.window
        w.combo_portfolio_student.setCurrentIndex(1)
        selected = w.combo_portfolio_student.currentData()
        w.le_portfolio_search.setText('합성학생2')
        popup = w.combo_portfolio_student.view()
        self.assertEqual(selected, w.combo_portfolio_student.currentData())
        self.assertFalse(popup.isRowHidden(1))
        self.assertFalse(popup.isRowHidden(2))
        self.assertTrue(popup.isRowHidden(3))

    def test_v4_unknown_exam_order_does_not_infer_previous_delta(self):
        view = self._select_two_rounds()
        self.window.exam.semester = '회차 미확인'
        self.window.refresh_portfolio_tab()
        self.assertEqual('비교 자료 없음', view.summary_values[1].text())
        self.assertEqual('20.0점', view.summary_values[0].text())
        self.assertEqual('2026학년도 1학기 1차', view.summary_captions[0].text())

    def test_student_identity_stays_visible_while_report_scrolls(self):
        view = self._select_two_rounds()
        w = self.window
        w.resize(1280, 800)
        w.tabs.setCurrentWidget(w.tab_portfolio)
        w.show(); self.app.processEvents()
        selector = w.combo_portfolio_student
        from PySide6.QtCore import QPoint
        before = selector.mapTo(w, QPoint(0, 0)).y()
        bar = view.report_scroll.verticalScrollBar()
        self.assertGreater(bar.maximum(), 0)
        bar.setValue(bar.maximum()); self.app.processEvents()
        self.assertEqual(before, selector.mapTo(w, QPoint(0, 0)).y())
        self.assertFalse(view.report_scroll.widget().isAncestorOf(selector))
        self.assertTrue(selector.isVisible())
        self.assertFalse(view.report_scroll.widget().isAncestorOf(w.lbl_portfolio_summary))

    def test_unknown_history_remains_selectable_but_not_graphed(self):
        view = self._select_two_rounds()
        w = self.window
        legacy = copy.deepcopy(w._current_subject_snapshot())
        legacy.update(semester='2026학년도 1학기', round_no=None, round=None)
        write_snapshot(w._portfolio_store_dir(), legacy)
        w.refresh_portfolio_tab()
        self.assertEqual(2, len(view.chart.points))
        self.assertEqual(3, view.round_combo.count())
        self.assertEqual(2, view.selected_round_point['round_no'])
        view.round_combo.setCurrentIndex(2)
        self.assertIn('회차 미확인', view.round_combo.currentText())
        self.assertEqual(-1, view.chart.selected_index)
        self.assertIsNone(view.selected_round_point['round_no'])
        self.assertGreater(view.tables['data'].rowCount(), 0)
        view.previous.click()
        self.assertEqual(1, view.chart.selected_index)

    def test_detail_numbers_format_without_changing_raw_values(self):
        from app.portfolio_view import detail_cell_text
        self.assertEqual('8.33', detail_cell_text(100 / 12, '1번(%)'))
        self.assertEqual('0.00', detail_cell_text(0, '전체 정답률(%)'))
        self.assertEqual('자료 없음', detail_cell_text(None, '전체 정답률(%)'))
        self.assertEqual('5', detail_cell_text(5, '문항'))
        self.assertEqual('.', detail_cell_text('.', '학생 응답'))
        view = self._select_two_rounds()
        tab = {'headers': ['전체 정답률(%)', '문항 수'], 'rows': [[100 / 12, 5]], 'available': True}
        before = copy.deepcopy(tab)
        with patch('app.portfolio_details.resolve_details', return_value={'tabs': {'standards': tab}}):
            view._render_version_details()
        table = view.tables['standards']
        self.assertEqual('8.33', table.item(0, 0).text())
        self.assertEqual(100 / 12, table.item(0, 0).data(Qt.UserRole))
        self.assertEqual(before, tab)

    def test_all_five_choices_fit_laptop_viewport(self):
        view = self._select_two_rounds()
        w = self.window
        w.resize(1280, 800); w.tabs.setCurrentWidget(w.tab_portfolio)
        tab = {'headers': ['문항', '정답', '학생 응답', '집단', '무응답(%)'] + [f'{i}번(%)' for i in range(1,6)],
               'rows': [[8, 4, '.', '미도달', 0, 100/13, 100/3, 25, 100/6, 100/7]], 'available': True}
        with patch('app.portfolio_details.resolve_details', return_value={'tabs': {'choice': tab}}):
            view._render_version_details()
        view.tabs.setCurrentIndex(3)
        w.show(); self.app.processEvents()
        table = view.tables['choice']
        self.assertEqual('14.29', table.item(0, 9).text())
        self.assertLessEqual(table.columnViewportPosition(9) + table.columnWidth(9), table.viewport().width())
        self.assertEqual(0, table.horizontalScrollBar().maximum())
