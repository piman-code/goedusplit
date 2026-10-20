from tests.runtime_isolation import ensure_isolated
ensure_isolated()
import copy
import json
import unittest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QDialog
from tests import test_analysis_preparation as fixtures
from app.analysis_preparation import AnalysisPreparationDialog
from app.preparation_settings import load_choices,settings_key


class PreparationSettingsTests(unittest.TestCase):
    setUpClass=classmethod(fixtures.AnalysisPreparationTests.setUpClass.__func__)
    setUp=fixtures.AnalysisPreparationTests.setUp
    inputs=fixtures.AnalysisPreparationTests.inputs

    def dialog(self,groups):
        dialog=AnalysisPreparationDialog(self.w,groups);self.addCleanup(dialog.close);return dialog

    def test_explicit_save_reopens_from_disk_and_cancel_does_not_overwrite(self):
        groups=self.inputs();d=self.dialog(groups);p=d.pages[0]
        p.file_weights.setChecked(False);p.pencil.setValue(63);p.include.setChecked(False)
        p.current_cuts={'A':91,'B':81,'C':71,'D':61,'E':41}
        p.combos['iteminfo'].setCurrentIndex(0)
        self.assertTrue(d.save_settings());p.pencil.setValue(12);d.reject()
        fresh=QSettings(self.w.settings.fileName(),self.w.settings.format());fresh.setFallbacksEnabled(False)
        data=load_choices(fresh,groups[0]);self.assertEqual(63,data['pencil_weight']);self.assertFalse(data['include'])
        reopened=self.dialog(groups);r=reopened.pages[0]
        self.assertEqual(63,r.pencil.value());self.assertFalse(r.include.isChecked());self.assertFalse(r.combos['iteminfo'].currentData())
        self.assertIsNone(r.reports)
        self.assertEqual(91,r.current_cuts['A']);self.assertEqual(91,r.selected()['manual_cut_scores']['A'])
        payload=json.loads(fresh.value(settings_key(groups[0])))
        self.assertEqual({'identity','files','perform','pencil_weight','file_weights','include','manual_cut_scores'},set(payload))

    def test_cancel_without_save_keeps_settings_empty(self):
        groups=self.inputs();d=self.dialog(groups);d.pages[0].pencil.setValue(13);d.reject()
        self.assertIsNone(load_choices(self.w.settings,groups[0]))

    def test_identity_scope_and_missing_path_never_substitute(self):
        groups=self.inputs();d=self.dialog(groups);p=d.pages[0]
        missing=str(self.root/'not-present.xlsx');p.combos['iteminfo'].addItem('누락',missing);p.combos['iteminfo'].setCurrentIndex(p.combos['iteminfo'].count()-1)
        self.assertTrue(d.save_settings());reopened=self.dialog(groups)
        self.assertFalse(reopened.pages[0].combos['iteminfo'].currentData());self.assertIn('문항정보표',reopened.pages[0].restore_notice)
        other=copy.deepcopy(groups[0]);other['key']=tuple(list(other['key'][:2])+[2]+list(other['key'][3:]))
        # It must read only that exact round's independent choices.
        self.assertNotEqual(settings_key(groups[0]),settings_key(other))
        other=copy.deepcopy(groups[0]);other['response']=[str(self.root/'different-folder'/'response.xlsx')]
        self.assertIsNone(load_choices(self.w.settings,other))

    def test_analysis_accept_saves_and_prefers_current_valid_round(self):
        groups=self.inputs();d=self.dialog(groups);d.tabs.setCurrentIndex(0);d.accept()
        self.assertEqual(QDialog.DialogCode.Accepted,d.result())
        self.assertEqual(1,sum(bool(g.get('preferred_display')) for g in d.result_groups))
        self.assertTrue(d.result_groups[0]['preferred_display'])
        self.assertIsNotNone(load_choices(self.w.settings,groups[0]))

    def test_failed_settings_write_does_not_claim_success(self):
        from unittest.mock import patch
        d=self.dialog(self.inputs())
        with patch.object(d.pages[0],'save_choices',return_value=False):
            self.assertFalse(d.save_settings());self.assertIn('실패',d.status.text())
