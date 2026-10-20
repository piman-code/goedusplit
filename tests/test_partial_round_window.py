from tests.runtime_isolation import ensure_isolated
ensure_isolated()
import unittest
from unittest.mock import patch
from tests import test_folder_round_batch as fixtures
from app.folder_batch import discover_round_groups
from app.work_sessions import build_session,prepare_session
from app.work_session_ui import capture_ui_state,apply_python_state

class PartialRoundWindowTests(unittest.TestCase):
    setUpClass=classmethod(fixtures.FolderRoundBatchTests.setUpClass.__func__)
    setUp=fixtures.FolderRoundBatchTests.setUp

    def test_complete_then_first_response_only_clears_old_item_results_and_restores(self):
        groups=discover_round_groups(self.folder,'1학기 1차')
        self.assertTrue(self.w._analyze_folder_groups(groups[:1]))
        self.assertGreater(self.w.table_choice.rowCount(),0)
        only=self.root/'only-first';only.mkdir()
        for source in self.folder.glob('1학기 1차 정오표*.xlsx'):
            (only/source.name).write_bytes(source.read_bytes())
        first=discover_round_groups(only,'1학기 1차')
        self.assertEqual(1,len(first))
        with patch('app.main_window.QMessageBox.warning') as warning:
            self.assertTrue(self.w._analyze_folder_groups(first),warning.call_args)
        self.assertEqual([],self.w.exam.items)
        self.assertEqual(0,self.w.table_items.rowCount())
        self.assertEqual(0,self.w.table_choice.rowCount())
        self.assertEqual(0,self.w.table_std.rowCount())
        self.assertGreater(self.w.table_data.rowCount(),0)
        self.assertTrue(all(st.final_score==st.total for st in self.w.exam.students))
        self.assertIn('자료 없음',self.w.lbl_alpha.text())
        payload=build_session(self.w.exam,self.w.perform_data,capture_ui_state(self.w),None)
        apply_python_state(self.w,prepare_session(payload))
        self.assertEqual(0,self.w.table_choice.rowCount())
        self.assertEqual([],self.w.exam.items)

    def test_individual_input_accepts_missing_items_and_performance_without_zero_scores(self):
        self.w.fs_response.path_edit.setText(str(next(self.folder.glob('1학기 1차 정오표*.xlsx'))))
        self.w.fs_iteminfo.path_edit.clear()
        self.w.chk_perform.setChecked(True)
        self.w.fs_perform.path_edit.clear()
        with patch('app.main_window.QMessageBox.warning') as warn,patch('app.main_window.QMessageBox.critical') as critical:
            self.w.run_analysis()
        warn.assert_not_called();critical.assert_not_called()
        self.assertIsNotNone(self.w.exam)
        self.assertFalse(self.w.exam.use_perform)
        self.assertEqual([],self.w.exam.items)
        self.assertTrue(all(st.final_score==st.total for st in self.w.exam.students))
        self.assertIn('학기 총점 아님',self.w.statusBar().currentMessage())

    def test_preferred_first_round_stays_visible_and_second_is_preserved(self):
        groups=discover_round_groups(self.folder,'1학기 1차')[:2]
        groups[0]['preferred_display']=True
        groups[1]['iteminfo']=''
        self.assertTrue(self.w._analyze_folder_groups(groups))
        self.assertEqual(2,len(self.w._portfolio_analysis_sessions))
        self.assertEqual(2,len(self.w._round_store().load_all()))
        self.assertEqual(groups[0]['iteminfo'],self.w.fs_iteminfo.path_edit.text())
        self.assertIn('1학기 1차',self.w.cmb_round.currentText())
        self.assertGreater(self.w.table_items.rowCount(),0)
        self.assertGreater(self.w.table_choice.rowCount(),0)
        self.assertGreater(self.w.table_std.rowCount(),0)
        self.assertIn('현재 표시: 1학기 1차',self.w.statusBar().currentMessage())
        payload=build_session(self.w.exam,self.w.perform_data,capture_ui_state(self.w),None)
        apply_python_state(self.w,prepare_session(payload))
        self.assertGreater(self.w.table_choice.rowCount(),0)
        self.assertEqual(2,len(self.w._portfolio_analysis_sessions))
