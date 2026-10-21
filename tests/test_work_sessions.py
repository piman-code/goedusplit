"""Synthetic full-work persistence contracts; no user files or settings."""
from tests.runtime_isolation import ensure_isolated
ensure_isolated()

import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from dataclasses import asdict

from app.data_loader import ExamData, ItemInfo, StudentResponse
from app.perform_loader import PerformArea, PerformData, PerformRecord
from app.synthetic_qa import project_fixture
from app.work_sessions import WorkSessionStore, build_session, prepare_session, validate_session


def synthetic_domain():
    records = {str(n): PerformRecord(str(n), f'1/{n}', f'합성 {n}', {'탐구': score}, score, score * 2.5)
               for n, score in ((1, 33.125), (2, 0))}
    perform = PerformData('합성수학', [PerformArea('탐구', 40, 40)], 40, 40,
                          records, {r.class_no: r for r in records.values()})
    exam = ExamData(subject='합성수학', grade='1', semester='1학기 1차',
                    items=[ItemInfo(1, '선택형', '연산', '합성 기준', '[합성-01]', '보통', 50, '1'),
                           ItemInfo(2, '선택형', '추론', '합성 기준2', '[합성-02]', '어려움', 50, '3')],
                    students=[StudentResponse('1', '1/1', '1', '합성 1', {1:'.', 2:'2'},
                                              multi_score=50, total=50, perform_score=82.8125, final_score=63.125),
                              StudentResponse('2', '1/2', '1', '합성 2', {1:'2', 2:'1'},
                                              total=0, perform_score=0, final_score=0)],
                    source_files={'responses':'/synthetic-only/missing.xlsx'},
                    weight_pencil=60, weight_perform=40, use_perform=True)
    return exam, perform


class WorkSessionCodecTests(unittest.TestCase):
    def payload(self):
        exam, perform = synthetic_domain()
        return build_session(exam, perform, {'perform_recalc_rows': [['탐구','40','오류 원문','30','20','10','0','메모']],
                                              'perform_recalc_dirty': True}, project_fixture(), {'round':'1차'})

    def test_json_roundtrip_preserves_identity_answers_zero_and_precision(self):
        prepared = prepare_session(json.loads(json.dumps(self.payload())))
        exam, perform = synthetic_domain()
        self.assertEqual(asdict(exam), asdict(prepared['exam']))
        self.assertEqual(asdict(perform), asdict(prepared['perform_data']))
        self.assertEqual({1:'.', 2:'2'}, prepared['exam'].students[0].answers)
        self.assertEqual(0, prepared['exam'].students[1].final_score)
        self.assertEqual(63.125, prepared['exam'].students[0].final_score)
        self.assertEqual('오류 원문', prepared['ui_state']['perform_recalc_rows'][0][2])
        self.assertEqual(project_fixture(), prepared['calculator_project'])

    def test_missing_original_inputs_do_not_prevent_saved_results_restore(self):
        prepared = prepare_session(self.payload())
        self.assertEqual(2, len(prepared['exam'].students))
        self.assertIsNotNone(prepared['overall'])
        self.assertEqual(2, len(prepared['item_stats']))

    def test_prepare_does_not_mutate_snapshot_or_share_domain(self):
        payload = self.payload()
        before = copy.deepcopy(payload)
        prepared = prepare_session(payload)
        prepared['exam'].students[0].answers[1] = '5'
        self.assertEqual(before, payload)
        self.assertEqual('.', prepare_session(payload)['exam'].students[0].answers[1])

    def test_summary_and_future_version_are_explicitly_rejected(self):
        with self.assertRaisesRegex(ValueError, '요약'):
            prepare_session({'subject':'합성수학', 'students':[], 'version':2})
        payload = self.payload()
        payload['version'] = 999
        with self.assertRaisesRegex(ValueError, '버전'):
            prepare_session(payload)

    def test_malformed_domain_rejected_without_mutating_original(self):
        payload = self.payload()
        payload['domain']['exam']['fields']['students'] = []
        before = copy.deepcopy(payload)
        with self.assertRaises(ValueError):
            prepare_session(payload)
        self.assertEqual(before, payload)

    def test_nonfinite_values_rejected(self):
        payload = self.payload()
        payload['ui_state']['invalid'] = float('nan')
        with self.assertRaises(ValueError):
            validate_session(payload)

    def test_append_preserves_prior_bytes_and_uses_private_permissions(self):
        root = Path(tempfile.mkdtemp(prefix='goedusplit-work-store-'))
        store = WorkSessionStore(root)
        payload = self.payload()
        first = store.save(payload)
        before = first.read_bytes()
        second = store.save(payload)
        self.assertNotEqual(first, second)
        self.assertEqual(before, first.read_bytes())
        if os.name != 'nt':  # Windows has no POSIX permission bits; os.open's mode is ignored there
            self.assertEqual(0o600, first.stat().st_mode & 0o777)
        self.assertEqual(2, len(store.list_sessions()))
        self.assertEqual(payload, store.read(second))

    def test_failed_publish_preserves_previous_work_and_reports_failure(self):
        root = Path(tempfile.mkdtemp(prefix='goedusplit-work-failure-'))
        store = WorkSessionStore(root)
        first = store.save(self.payload())
        before = first.read_bytes()
        with patch('app.work_sessions.os.link', side_effect=OSError('synthetic disk failure')):
            with self.assertRaises(OSError):
                store.save(self.payload())
        self.assertEqual(before, first.read_bytes())
        self.assertEqual([first], [entry['path'] for entry in store.list_sessions()])


class WorkSessionPythonUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from app.main_window import MainWindow
        from app.work_session_ui import capture_ui_state, apply_python_state
        self.capture = capture_ui_state
        self.apply = apply_python_state
        self.no_web = patch('app.main_window.QWebEngineView', None)
        self.no_web.start()
        self.addCleanup(self.no_web.stop)
        self.window = MainWindow()
        self.addCleanup(self.window.close)
        exam, perform = synthetic_domain()
        prepared = prepare_session(build_session(exam, perform, self.capture(self.window), None))
        self.apply(self.window, prepared)

    def test_all_tab_edits_A_to_B_to_A(self):
        from PySide6.QtWidgets import QTableWidgetItem
        w = self.window
        w.fs_grade5_report.path_edit.setText('/synthetic-only/grade5-A.xlsx')
        w.le_search.setText('합성 1')
        w.chk_chart_student_labels.setChecked(True)
        w.monitor_spins['ref_a_mean'].setValue(21.5)
        w.monitor_spins['prev_mean'].setValue(0)
        w.table_perform_recalc.setRowCount(1)
        raw = ['탐구 A','40','잘못된 원문','30','20','10','0','메모 A']
        for col, text in enumerate(raw):
            w.table_perform_recalc.setItem(0, col, QTableWidgetItem(text))
        w._perform_recalc_dirty = True
        state_a = self.capture(w)
        payload = build_session(w.exam, w.perform_data, state_a, project_fixture())
        w.le_search.setText('B')
        w.fs_grade5_report.path_edit.setText('/synthetic-only/B.xlsx')
        w.monitor_spins['ref_a_mean'].setValue(99)
        w.table_perform_recalc.item(0, 7).setText('B')
        w.exam.students[0].final_score = 99
        self.apply(w, prepare_session(payload))
        self.assertEqual('합성 1', w.le_search.text())
        self.assertEqual('/synthetic-only/grade5-A.xlsx', w.fs_grade5_report.path())
        self.assertEqual(21.5, w.monitor_spins['ref_a_mean'].value())
        self.assertEqual(raw, [w.table_perform_recalc.item(0, c).text() for c in range(8)])
        self.assertTrue(w._perform_recalc_dirty)
        self.assertEqual(63.125, w.exam.students[0].final_score)
        self.assertTrue(w.chk_chart_student_labels.isChecked())

    def test_invalid_ui_keeps_current_work(self):
        w = self.window
        w.le_search.setText('현재 B')
        state = self.capture(w)
        payload = build_session(w.exam, w.perform_data, state, None)
        prepared = prepare_session(payload)
        prepared['ui_state']['edit_tables']['table_perform_recalc'] = [['bad shape']]
        original_exam = w.exam
        with self.assertRaises(ValueError):
            self.apply(w, prepared)
        self.assertIs(original_exam, w.exam)
        self.assertEqual('현재 B', w.le_search.text())
        self.assertEqual(state, self.capture(w))

    def test_renderer_failure_rolls_back_existing_domain_and_edits(self):
        w = self.window
        w.le_search.setText('기존 B')
        state = self.capture(w)
        original_exam = w.exam
        exam_a, perform_a = synthetic_domain()
        exam_a.subject = '복원 A'
        prepared = prepare_session(build_session(exam_a, perform_a, state, None))
        real_renderer = w._refresh_all_charts
        calls = []
        def fail_once():
            calls.append(True)
            if len(calls) == 1:
                raise RuntimeError('synthetic renderer failure')
            return real_renderer()
        with patch.object(w, '_refresh_all_charts', side_effect=fail_once):
            with self.assertRaisesRegex(RuntimeError, 'synthetic renderer failure'):
                self.apply(w, prepared)
        self.assertIs(original_exam, w.exam)
        self.assertEqual('기존 B', w.le_search.text())
        self.assertEqual(state, self.capture(w))

    def test_empty_window_corrupt_header_restore_preserves_every_ui_field(self):
        from app.main_window import MainWindow
        empty = MainWindow()
        self.addCleanup(empty.close)
        empty.le_search.setText('분석 전 입력 보존')
        before = self.capture(empty)
        exam, perform = synthetic_domain()
        prepared = prepare_session(build_session(exam, perform, before, None))
        first_header = next(iter(prepared['ui_state']['table_headers'].values()))
        first_header['state'] = 123
        with self.assertRaises((ValueError, TypeError, AttributeError)):
            self.apply(empty, prepared)
        self.assertIsNone(empty.exam)
        self.assertEqual(before, self.capture(empty))

    def test_active_tab_identity_survives_user_reordering(self):
        w = self.window
        selected = w.tab_perform
        w.tabs.setCurrentWidget(selected)
        state = self.capture(w)
        payload = build_session(w.exam, w.perform_data, state, None)
        index = w.tabs.indexOf(selected)
        destination = 0 if index != 0 else w.tabs.count() - 1
        w.tabs.tabBar().moveTab(index, destination)
        w.tabs.setCurrentWidget(w.tab_data)
        self.apply(w, prepare_session(payload))
        self.assertIs(selected, w.tabs.currentWidget())

    def test_result_only_recommend_add_delete_buttons_cannot_edit_table(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QPushButton
        w = self.window
        w.tabs.setCurrentWidget(w.tab_perform)
        w.perform_table_tabs.setCurrentIndex(2)
        w.table_perform_recalc.selectRow(0)
        w.show()
        self.app.processEvents()
        before = self.capture(w)['edit_tables']['table_perform_recalc']
        w.work_sessions._set_result_only(True)
        for label in ('자료 기준 딸깍 추천', '기본안', '평가요소 추가', '선택 삭제'):
            with self.subTest(button=label):
                buttons = [button for button in w.tab_perform.findChildren(QPushButton)
                           if button.text() == label]
                self.assertEqual(1, len(buttons))
                QTest.mouseClick(buttons[0], Qt.LeftButton)
                self.app.processEvents()
                self.assertEqual(before, self.capture(w)['edit_tables']['table_perform_recalc'])

    def test_empty_window_renderer_failure_restores_full_checkpoint(self):
        from app.main_window import MainWindow
        empty = MainWindow()
        self.addCleanup(empty.close)
        empty.le_search.setText('빈 창 보존')
        before = self.capture(empty)
        info_before = empty.exam_info_lbl.text()
        exam, perform = synthetic_domain()
        state_a = self.capture(self.window)
        prepared = prepare_session(build_session(exam, perform, state_a, None))
        with patch.object(empty, '_refresh_all_charts', side_effect=RuntimeError('empty renderer failure')):
            with self.assertRaisesRegex(RuntimeError, 'empty renderer failure'):
                self.apply(empty, prepared)
        self.assertIsNone(empty.exam)
        self.assertIsNone(empty.overall)
        self.assertEqual(info_before, empty.exam_info_lbl.text())
        self.assertEqual(before, self.capture(empty))

    def test_result_only_blocks_menu_monitor_and_restores_original_enabled_flags(self):
        from PySide6.QtGui import QAction
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QWidget
        w = self.window
        actions = [a for a in w.findChildren(QAction) if a.text() == '분석 실행']
        self.assertTrue(actions)
        guarded = [w.btn_run_analysis, w.input_panel, w.tab_perform,
                   w.tab_monitor, w.btn_portfolio_save, *actions]
        if w.tab_ai_review is not None:
            guarded.append(w.tab_ai_review)
        # An originally disabled child must stay disabled after reconnecting,
        # while enabled children disabled only by their parent must recover.
        w.btn_portfolio_save.setEnabled(False)
        def own_enabled(widget):
            return not widget.testAttribute(Qt.WA_ForceDisabled) if isinstance(widget, QWidget) else widget.isEnabled()
        original = [own_enabled(widget) for widget in guarded]
        w.work_sessions._set_result_only(True)
        self.assertTrue(all(not widget.isEnabled() for widget in guarded))
        w.work_sessions._set_result_only(False)
        self.assertEqual(original, [own_enabled(widget) for widget in guarded])
        self.assertTrue(w.tab_monitor.isEnabled())
        self.assertTrue(all(action.isEnabled() for action in actions))
