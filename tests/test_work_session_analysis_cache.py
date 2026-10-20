"""Synthetic save/reopen of earlier analyzed rounds bundled in a full work."""
from tests.runtime_isolation import ensure_isolated
ensure_isolated()
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from app.main_window import MainWindow
from app.portfolio_details import remember_analysis,load_work_session_rows,resolve_details
from app.work_session_ui import capture_ui_state,apply_python_state
from app.work_sessions import build_session,prepare_session,WorkSessionStore
from tests.test_work_sessions import synthetic_domain

class AnalysisCacheWorkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.patch=patch('app.main_window.QWebEngineView',None);self.patch.start();self.addCleanup(self.patch.stop)
        self.w=MainWindow();self.addCleanup(self.w.close)
        exam,perform=synthetic_domain();exam.semester='2026학년도 1학기 1차'
        apply_python_state(self.w,prepare_session(build_session(exam,perform,capture_ui_state(self.w),None)))
        remember_analysis(self.w)
    def test_earlier_round_and_performance_reopen_in_fresh_window(self):
        w=self.w
        second=copy.deepcopy(w.exam);second.semester='2026학년도 1학기 2차';second.students[0].final_score=10
        apply_python_state(w,prepare_session(build_session(second,w.perform_data,capture_ui_state(w),None)))
        remember_analysis(w)
        payload=build_session(w.exam,w.perform_data,capture_ui_state(w),None)
        self.assertEqual(2,len(payload['ui_state']['portfolio_analysis_sessions']))
        store=WorkSessionStore(Path(tempfile.mkdtemp(prefix='analysis-cache-work-')))
        path=store.save(payload)
        fresh=MainWindow();self.addCleanup(fresh.close)
        # Student identities use the same application-local privacy key in real reopen.
        fresh.settings.setValue('privacy/portfolio_hash_key',w.settings.value('privacy/portfolio_hash_key'))
        apply_python_state(fresh,prepare_session(store.read(path)))
        earlier=next(r for r in load_work_session_rows(fresh) if r['source_kind']=='analysis-session' and r['round_no']==1 and r['class_no']=='1/1')
        result=resolve_details(fresh,earlier)
        self.assertTrue(all(tab['available'] for tab in result['tabs'].values()))
        self.assertEqual(63.125,earlier['score'])
        self.assertEqual(33.125,result['tabs']['perform']['rows'][0][3])
        self.assertNotIn('미저장',result['provenance'])
        self.assertEqual('2026학년도 1학기 2차',fresh.exam.semester)
    def test_old_work_without_cache_clears_unrelated_live_cache(self):
        payload=build_session(self.w.exam,self.w.perform_data,capture_ui_state(self.w),None)
        payload['ui_state'].pop('portfolio_analysis_sessions',None)
        apply_python_state(self.w,prepare_session(payload))
        self.assertEqual({},self.w._portfolio_analysis_sessions)
    def test_nested_cache_refused_before_mutation(self):
        w=self.w;before=capture_ui_state(w);exam=w.exam
        payload=build_session(w.exam,w.perform_data,before,None)
        cached=copy.deepcopy(next(iter(w._portfolio_analysis_sessions.values())))
        cached['ui_state']['portfolio_analysis_sessions']={}
        payload['ui_state']['portfolio_analysis_sessions']={'bad':cached}
        with self.assertRaises(ValueError):apply_python_state(w,prepare_session(payload))
        self.assertIs(exam,w.exam);self.assertEqual(before,capture_ui_state(w))
    def test_renderer_failure_preserves_previous_cache(self):
        w=self.w;before=copy.deepcopy(w._portfolio_analysis_sessions)
        payload=build_session(w.exam,w.perform_data,capture_ui_state(w),None)
        payload['ui_state']['portfolio_analysis_sessions']={}
        original=w._refresh_all_charts;calls=[]
        def fail_once():
            calls.append(True)
            if len(calls)==1:raise RuntimeError('synthetic renderer')
            return original()
        with patch.object(w,'_refresh_all_charts',side_effect=fail_once):
            with self.assertRaises(RuntimeError):apply_python_state(w,prepare_session(payload))
        self.assertEqual(before,w._portfolio_analysis_sessions)

    def test_empty_window_renderer_failure_preserves_cache(self):
        empty=MainWindow();self.addCleanup(empty.close)
        empty._portfolio_analysis_sessions=copy.deepcopy(self.w._portfolio_analysis_sessions)
        before=capture_ui_state(empty)
        payload=build_session(self.w.exam,self.w.perform_data,capture_ui_state(self.w),None)
        payload['ui_state']['portfolio_analysis_sessions']={}
        with patch.object(empty,'_refresh_all_charts',side_effect=RuntimeError('synthetic empty renderer')):
            with self.assertRaises(RuntimeError):apply_python_state(empty,prepare_session(payload))
        self.assertIsNone(empty.exam)
        self.assertEqual(before,capture_ui_state(empty))

    def test_cache_count_and_size_limits_preserve_previous_state(self):
        w=self.w;before=capture_ui_state(w)
        prepared=prepare_session(build_session(w.exam,w.perform_data,before,None))
        with patch('app.work_session_ui.MAX_ANALYSIS_SESSIONS',0):
            with self.assertRaisesRegex(ValueError,'자료 수'):apply_python_state(w,prepared)
        self.assertEqual(before,capture_ui_state(w))
        with patch('app.work_session_ui.MAX_BYTES',1):
            with self.assertRaisesRegex(ValueError,'자료 크기'):apply_python_state(w,prepared)
        self.assertEqual(before,capture_ui_state(w))
