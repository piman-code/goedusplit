from tests.runtime_isolation import ensure_isolated
ensure_isolated()

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, QEvent, QSettings, Qt
from PySide6.QtGui import QResizeEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.main_window import MainWindow


class LaptopLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.resources = ExitStack()
        self.addCleanup(self.resources.close)
        tmp = self.resources.enter_context(tempfile.TemporaryDirectory())
        settings = QSettings(str(Path(tmp) / "settings.ini"), QSettings.IniFormat)
        settings.setFallbacksEnabled(False)
        self.resources.enter_context(patch("app.main_window.QSettings", return_value=settings))
        self.resources.enter_context(patch("app.main_window.QWebEngineView", None))
        self.window = MainWindow()
        self.addCleanup(self.close_window)
        self.assertIs(self.window.settings, settings)
        self.window.tabs.setCurrentWidget(self.window.tab_data)
        self.window.show()
        self.resize_window(1600, 900)
        self.assertEqual(0,self.window.splitter.sizes()[0])

    def close_window(self):
        self.window.close()
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.app.processEvents()

    def settle(self):
        self.app.processEvents()
        QTest.qWait(1)

    def resize_window(self, width, height=800):
        self.window.resize(width, height)
        self.settle()
        self.assertEqual((self.window.width(), self.window.height()), (width, height))

    def set_tab(self, tab):
        self.window.tabs.setCurrentWidget(tab)
        self.settle()

    def test_results_keep_full_width_at_laptop_and_monitor_boundaries(self):
        for width in (1080,1179,1180,1280,1439,1440,1600):
            self.resize_window(width)
            for tab in (self.window.tab_data,self.window.tab_spliter):
                self.set_tab(tab)
                self.assertEqual(0,self.window.splitter.sizes()[0])
                self.assertGreater(self.window.tabs.width(),width-50)

    def test_settings_open_does_not_shrink_results_or_change_tabs(self):
        self.resize_window(1280)
        labels=[self.window.tabs.tabText(i) for i in range(self.window.tabs.count())]
        width=self.window.tabs.width()
        QTest.mouseClick(self.window.btn_sidebar,Qt.LeftButton);self.settle()
        self.assertTrue(self.window.input_workspace.dialog.isVisible())
        self.assertEqual(width,self.window.tabs.width())
        self.assertEqual(labels,[self.window.tabs.tabText(i) for i in range(self.window.tabs.count())])
        self.window.input_workspace.dialog.close();self.settle()
        self.assertEqual(width,self.window.tabs.width())

    def test_existing_show_input_action_opens_integrated_settings(self):
        self.window._show_sidebar();self.settle()
        self.assertTrue(self.window.input_workspace.dialog.isVisible())
        self.assertEqual(0,self.window.splitter.sizes()[0])
        self.resize_window(1080,801)
        self.assertTrue(self.window.input_workspace.dialog.isVisible())

    def test_individual_controls_keep_identity_and_typed_values_on_close(self):
        selectors=[self.window.fs_response,self.window.fs_iteminfo,self.window.fs_cuts,
                   self.window.fs_grade5_report,self.window.fs_perform]
        self.window.input_workspace.open('individual');self.settle()
        self.window.cmb_round.setCurrentText('2학기 2차')
        self.window.spin_cuts['A'].setValue(87.25)
        self.window.input_workspace.dialog.close();self.settle()
        self.window.input_workspace.open('individual');self.settle()
        self.assertEqual('2학기 2차',self.window.cmb_round.currentText())
        self.assertEqual(87.25,self.window.spin_cuts['A'].value())
        for control in selectors:
            self.assertIn(control,self.window.findChildren(type(control)))
            self.assertTrue(self.window.input_workspace.dialog.isAncestorOf(control))
        self.assertTrue(self.window.btn_run_analysis.isVisible())

    def test_both_layout_modes_preserve_full_results_and_dialog_access(self):
        mode=self.window._result_layout_refs['mode']
        for index in (1,0):
            mode.setCurrentIndex(index);self.settle()
            self.assertEqual(0,self.window.splitter.sizes()[0])
            self.window.input_workspace.open();self.settle()
            self.assertTrue(self.window.input_workspace.dialog.isVisible())
            self.window.input_workspace.dialog.close()

    def test_full_width_main_tabs_keep_labels_and_tooltips(self):
        for width in (1280,1600):
            self.resize_window(width)
            before=[self.window.tabs.tabText(i) for i in range(self.window.tabs.count())]
            self.set_tab(self.window.tab_spliter)
            self.assertEqual(before,[self.window.tabs.tabText(i) for i in range(self.window.tabs.count())])
            for widget,full,_compact,_tiny in self.window._tab_label_sets:
                self.assertEqual(full,self.window.tabs.tabToolTip(self.window.tabs.indexOf(widget)))

if __name__=='__main__':unittest.main()
