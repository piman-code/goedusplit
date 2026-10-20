from tests.runtime_isolation import ensure_isolated
ensure_isolated()
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QSplitter, QTabWidget, QPushButton
from app.main_window import MainWindow
from app.input_workspace import install_input_workspace
from app.work_session_ui import capture_ui_state, apply_python_state
from app.work_sessions import build_session, prepare_session
from tests.test_work_sessions import synthetic_domain


class InputWorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='input-workspace-'))
        self.settings = QSettings(str(self.root/'settings.ini'), QSettings.IniFormat)
        for p in [patch('app.main_window.QWebEngineView', None),
                  patch('app.main_window.QSettings', return_value=self.settings),
                  patch.object(MainWindow, '_ai_material_root_dir', lambda w:self.root/'state')]:
            p.start(); self.addCleanup(p.stop)
        with patch('app.input_workspace.install_input_workspace'):
            self.w=MainWindow()
        self.w.resize(1280,800);self.w.show();self.app.processEvents()
        self.before=capture_ui_state(self.w)
        self.controls={name:getattr(self.w,name) for name in ('input_panel','fs_response','fs_iteminfo','fs_cuts','fs_perform','fs_grade5_report','btn_run_analysis','btn_revert','cmb_round','spin_pencil_ratio','spin_perform_ratio')}
        self.tabs=self.w.findChildren(QTabWidget);self.splitters=self.w.findChildren(QSplitter)
        install_input_workspace(self.w)
        self.addCleanup(self.w.close);self.addCleanup(self.w.input_workspace.dialog.close)

    def test_same_controls_and_snapshot_structure_survive_reparenting(self):
        w=self.w;ws=w.input_workspace
        for name,control in self.controls.items():self.assertIs(control,getattr(w,name))
        self.assertEqual(self.tabs,w.findChildren(QTabWidget))
        self.assertEqual(self.splitters,w.findChildren(QSplitter))
        self.assertEqual(2,w.splitter.count());self.assertEqual(0,w.splitter.sizes()[0])
        self.assertTrue(ws.dialog.isAncestorOf(w.input_panel))
        self.assertEqual(5,len(ws.original_panels))
        after=capture_ui_state(w)
        for key in ('inputs','weights','cuts','folds','tabs'):
            self.assertEqual(self.before[key],after[key],key)
        self.assertTrue(w.fs_response.multiple);self.assertTrue(w.fs_perform.multiple)
        texts=[b.text() for b in w.input_panel.findChildren(QPushButton)]
        self.assertTrue(any('CSV' in text for text in texts));self.assertTrue(any('근거' in text for text in texts))
        self.assertIn('1-5등급 컷 계산',texts)

    def test_real_picker_callbacks_and_close_keep_inputs(self):
        w=self.w;ws=w.input_workspace;ws.open('individual');self.app.processEvents()
        with patch('app.main_window.QFileDialog.getOpenFileNames',return_value=([str(self.root/'1학기 1차 합성.xlsx')],'')):
            QTest.mouseClick(w.fs_response.btn,Qt.LeftButton)
        self.assertIn('1학기 1차',w.fs_response.path())
        w.chk_perform.setChecked(True);self.assertTrue(w.fs_perform.isEnabled())
        w.spin_pencil_ratio.spin.setValue(60);self.assertEqual(40,w.spin_perform_ratio.value())
        w.spin_cuts['A'].setValue(87.5)
        state=capture_ui_state(w);ws.dialog.close();self.app.processEvents()
        after=capture_ui_state(w)
        for key in ('inputs','weights','cuts'):self.assertEqual(state[key],after[key])
        w._show_sidebar();self.assertTrue(ws.dialog.isVisible());self.assertIs(ws.pages.currentWidget(),ws.individual_page)
        self.assertEqual(0,w.splitter.sizes()[0])

    def test_single_folder_card_moves_and_readonly_cannot_prepare(self):
        w=self.w;ws=w.input_workspace;c=w.folder_workspace
        self.assertGreaterEqual(c.start_layout.indexOf(c.card),0)
        ws.open();self.assertGreaterEqual(ws.folder_layout.indexOf(c.card),0)
        ws.dialog.close();self.app.processEvents();self.assertGreaterEqual(c.start_layout.indexOf(c.card),0)
        c.register(self.root)
        w.work_sessions._set_result_only(True)
        with patch.object(w,'_pick_folder_batch') as prepare:
            c.prepare();prepare.assert_not_called()
        self.assertFalse(w.input_panel.isEnabled())
        w.work_sessions._set_result_only(False);self.assertTrue(w.input_panel.isEnabled())

    def test_legacy_work_state_restores_with_two_slot_splitter(self):
        exam,perform=synthetic_domain()
        payload=build_session(exam,perform,self.before,None)
        apply_python_state(self.w,prepare_session(payload))
        self.assertEqual(exam.subject,self.w.exam.subject)
        self.assertEqual(len(exam.students),len(self.w.exam.students))
        after=capture_ui_state(self.w)
        for key in ('inputs','weights','cuts','tabs','folds'):self.assertEqual(self.before[key],after[key],key)
        self.assertEqual(2,self.w.splitter.count());self.assertEqual(0,self.w.splitter.sizes()[0])
        self.w.input_workspace.open('folder')
        self.assertGreaterEqual(self.w.input_workspace.folder_layout.indexOf(self.w.folder_workspace.card),0)

if __name__=='__main__':unittest.main()
