"""Native user-width and frozen-column preservation with synthetic cells."""
from tests.runtime_isolation import ensure_isolated
ensure_isolated()
import unittest
from PySide6.QtCore import Qt,QPoint
from PySide6.QtWidgets import QApplication,QTableWidget,QTableWidgetItem,QHeaderView
from PySide6.QtTest import QTest
from app.table_controls import enable_table_columns
from app.widgets import install_frozen_columns
from app.portfolio_view import PortfolioDetailTable

class TableControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def table(self,kind=QTableWidget):
        table=kind(10,10);self.addCleanup(table.close)
        table.setHorizontalHeaderLabels([str(i) for i in range(10)])
        for r in range(10):
            for c in range(10):table.setItem(r,c,QTableWidgetItem('33.33'))
        table.resize(850,320);table.show();self.app.processEvents()
        return table
    def drag(self,table,column,delta):
        header=table.horizontalHeader();viewport=header.viewport()
        point=QPoint(header.sectionViewportPosition(column)+header.sectionSize(column)-1,header.height()//2)
        QTest.mousePress(viewport,Qt.LeftButton,pos=point)
        QTest.mouseMove(viewport,point+QPoint(delta,0),30)
        QTest.mouseRelease(viewport,Qt.LeftButton,pos=point+QPoint(delta,0))
        self.app.processEvents()
    def test_native_drag_survives_programmatic_render_and_reset(self):
        table=self.table();control=enable_table_columns(table);self.app.processEvents()
        initial=table.columnWidth(0)
        self.drag(table,0,35)
        resized=table.columnWidth(0)
        self.assertGreater(resized,initial)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Fixed)
        table.setColumnWidth(0,47);self.app.processEvents()
        self.assertEqual(resized,table.columnWidth(0))
        self.assertEqual(QHeaderView.Interactive,table.horizontalHeader().sectionResizeMode(0))
        control.reset_action.trigger();self.app.processEvents()
        self.assertEqual(initial,table.columnWidth(0))
        control.fit_action.trigger();self.app.processEvents()
        self.assertLessEqual(sum(table.columnWidth(c) for c in range(10)),table.viewport().width())
    def test_frozen_header_drag_syncs_main_and_other_rows(self):
        table=self.table();frozen=install_frozen_columns(table,2)
        control=enable_table_columns(table);self.app.processEvents()
        initial=table.columnWidth(0)
        self.drag(frozen,0,30)
        self.assertGreater(table.columnWidth(0),initial)
        self.assertEqual(table.columnWidth(0),frozen.columnWidth(0))
        self.assertIn(0,control.manual)
    def test_choice_initial_fit_then_manual_resize_is_preserved(self):
        table=self.table(PortfolioDetailTable)
        table.configure_columns('choice');self.app.processEvents()
        self.assertTrue(all(table.horizontalHeader().sectionResizeMode(c)==QHeaderView.Interactive for c in range(10)))
        self.assertLessEqual(sum(table.columnWidth(c) for c in range(10)),table.viewport().width())
        self.drag(table,4,25);width=table.columnWidth(4)
        table.resize(900,350);table.configure_columns('choice');self.app.processEvents()
        self.assertEqual(width,table.columnWidth(4))
    def test_full_work_restores_drag_width_and_perform_splitter_keeps_graph_open(self):
        from tests.test_portfolio_view import PortfolioViewTests
        from app.work_session_ui import capture_ui_state,apply_python_state
        from app.work_sessions import build_session,prepare_session
        case=PortfolioViewTests();case.setUpClass();case.setUp();self.addCleanup(case.doCleanups)
        w=case.window;w.show();w.resize(1280,800);self.app.processEvents()
        table=w.table_data;control=enable_table_columns(table);self.app.processEvents()
        self.drag(table,2,35);width=table.columnWidth(2)
        saved=prepare_session(build_session(w.exam,w.perform_data,capture_ui_state(w),None))
        self.drag(table,2,30);self.assertNotEqual(width,table.columnWidth(2))
        apply_python_state(w,saved);self.app.processEvents()
        self.assertEqual(width,table.columnWidth(2))
        self.assertEqual(width,control.manual[2])
        w.tabs.setCurrentWidget(w.tab_perform);self.app.processEvents()
        section=next(widget for widget in w.findChildren(__import__('PySide6.QtWidgets',fromlist=['QWidget']).QWidget)
                     if getattr(widget,'_key',None)=='ui/fold/perform.charts')
        section.toggle.setChecked(True);split=section.parentWidget();split.setSizes([1,900]);self.app.processEvents()
        self.assertGreaterEqual(section.body.height(),220)
        section.toggle.setChecked(False);self.app.processEvents()
        self.assertFalse(section.body.isVisible())
        section.toggle.setChecked(True);self.app.processEvents()
        self.assertGreaterEqual(section.body.height(),220)
    def test_bounded_scan_enables_late_modal_table_without_global_event_filter(self):
        from PySide6.QtWidgets import QWidget,QDialog,QVBoxLayout
        from app.table_controls import install_table_controls
        window=QWidget();self.addCleanup(window.close)
        installer=install_table_controls(window)
        dialog=QDialog();self.addCleanup(dialog.close)
        table=QTableWidget(2,2);layout=QVBoxLayout(dialog);layout.addWidget(table)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Fixed)
        dialog.show();QTest.qWait(550)
        self.assertIsNotNone(getattr(table,'_column_controls',None))
        self.assertEqual(QHeaderView.Interactive,table.horizontalHeader().sectionResizeMode(0))
        self.assertEqual(500,installer.scan_timer.interval())
    def test_portfolio_detail_width_survives_fresh_window_and_legacy_missing_keys(self):
        import copy
        from tests.test_portfolio_view import PortfolioViewTests
        from app.main_window import MainWindow
        from app.work_session_ui import capture_ui_state,apply_python_state
        from app.work_sessions import build_session,prepare_session
        case=PortfolioViewTests();case.setUpClass();case.setUp();self.addCleanup(case.doCleanups)
        w=case.window;w.show();w.resize(1280,800)
        w.tabs.setCurrentWidget(w.tab_portfolio)
        w.combo_portfolio_student.setCurrentIndex(1)
        w.portfolio_view.tabs.setCurrentIndex(2)
        self.app.processEvents()
        table=w.portfolio_detail_tables['items'];initial=table.columnWidth(0)
        self.drag(table,0,39)
        width=table.columnWidth(0)
        self.assertGreater(width,initial)
        state=capture_ui_state(w)
        self.assertTrue(all('portfolio_detail:'+key in state['table_headers'] for key in w.portfolio_detail_tables))
        payload=build_session(w.exam,w.perform_data,state,None)
        fresh=MainWindow();self.addCleanup(fresh.close)
        fresh.settings.setValue('privacy/portfolio_hash_key',w.settings.value('privacy/portfolio_hash_key'))
        fresh.show();fresh.resize(1280,800)
        apply_python_state(fresh,prepare_session(payload));self.app.processEvents()
        self.assertEqual(width,fresh.portfolio_detail_tables['items'].columnWidth(0))
        self.assertEqual(width,fresh.portfolio_detail_tables['items']._column_controls.manual[0])
        legacy=copy.deepcopy(payload)
        for key in list(legacy['ui_state']['table_headers']):
            if key.startswith('portfolio_detail:'):legacy['ui_state']['table_headers'].pop(key)
        apply_python_state(fresh,prepare_session(legacy));self.app.processEvents()
        self.assertEqual(w.exam.subject,fresh.exam.subject)
