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
    def double_click_handle(self,table,column):
        header=table.horizontalHeader();viewport=header.viewport()
        point=QPoint(header.sectionViewportPosition(column)+header.sectionSize(column)-1,header.height()//2)
        QTest.mouseDClick(viewport,Qt.LeftButton,pos=point)
        self.app.processEvents()
    def test_double_click_handle_fits_column_to_contents_and_keeps_it(self):
        table=self.table();control=enable_table_columns(table)
        table.setItem(0,3,QTableWidgetItem('성취수준 A 비율이 전국 평균보다 높음'));self.app.processEvents()
        table.setColumnWidth(3,40);self.app.processEvents()
        self.double_click_handle(table,3)
        fitted=table.columnWidth(3)
        self.assertGreaterEqual(fitted,min(table.sizeHintForColumn(3),int(table.viewport().width()*0.6)))
        self.assertEqual(fitted,control.manual[3])
        table.setColumnWidth(3,47);self.app.processEvents()
        self.assertEqual(fitted,table.columnWidth(3))
        self.assertIn('더블클릭',table.horizontalHeader().toolTip())
    def test_fit_all_to_contents_caps_long_text(self):
        table=self.table();control=enable_table_columns(table)
        table.setItem(0,9,QTableWidgetItem('긴 설명 '*80));self.app.processEvents()
        control.contents_action.trigger();self.app.processEvents()
        self.assertLessEqual(table.columnWidth(9),int(table.viewport().width()*0.6))
        self.assertEqual(10,len(control.manual))
    def test_fill_table_spreads_columns_over_width_until_user_sizes_one(self):
        table=self.table();table.setColumnCount(5);table.setProperty('fillColumns',True)
        for c,width in enumerate((250,180,260,120,520)):table.setColumnWidth(c,width)
        control=enable_table_columns(table);self.app.processEvents()
        def total():return sum(table.columnWidth(c) for c in range(5))
        self.assertLessEqual(abs(total()-table.viewport().width()),5)
        self.assertGreater(table.columnWidth(4),table.columnWidth(3))
        table.resize(1200,320);self.app.processEvents()
        self.assertLessEqual(abs(total()-table.viewport().width()),5)
        self.drag(table,0,30);dragged=table.columnWidth(0)
        table.resize(1000,320);self.app.processEvents()
        self.assertEqual(dragged,table.columnWidth(0))
        control.reset_action.trigger();self.app.processEvents()
        self.assertEqual({},control.manual)
        self.assertLessEqual(abs(total()-table.viewport().width()),5)
    def test_every_table_fills_the_width_by_default(self):
        table=self.table();table.setColumnCount(4)
        for c in range(4):table.setColumnWidth(c,90)
        enable_table_columns(table);self.app.processEvents()
        self.assertLessEqual(abs(sum(table.columnWidth(c) for c in range(4))-table.viewport().width()),4)
    def test_filling_never_leaves_a_narrow_column_cut(self):
        table=self.table();table.setColumnCount(6)
        for r in range(10):table.setItem(r,2,QTableWidgetItem('100.0'))
        for c,width in enumerate((200,200,20,200,200,20)):table.setColumnWidth(c,width)
        enable_table_columns(table);self.app.processEvents()
        self.assertGreaterEqual(table.columnWidth(2),table.sizeHintForColumn(2))
        self.assertLessEqual(abs(sum(table.columnWidth(c) for c in range(6))-table.viewport().width()),6)
    def test_table_too_wide_to_read_keeps_its_widths_and_scrolls(self):
        table=self.table()
        table.setHorizontalHeaderLabels(['정기시험 총점과 수행평가 환산 '+str(c) for c in range(10)])
        for c in range(10):table.setColumnWidth(c,240)
        enable_table_columns(table);self.app.processEvents()
        self.assertEqual([240]*10,[table.columnWidth(c) for c in range(10)])
    def test_opted_out_table_is_not_filled_and_frozen_table_stays_in_sync(self):
        opted_out=self.table();opted_out.setProperty('fillColumns',False)
        for c in range(10):opted_out.setColumnWidth(c,50)
        enable_table_columns(opted_out);self.app.processEvents()
        self.assertEqual(500,sum(opted_out.columnWidth(c) for c in range(10)))
        frozen_table=self.table();frozen=install_frozen_columns(frozen_table,2)
        for c in range(10):frozen_table.setColumnWidth(c,50)
        enable_table_columns(frozen_table);self.app.processEvents()
        self.assertLessEqual(abs(sum(frozen_table.columnWidth(c) for c in range(10))-frozen_table.viewport().width()),10)
        self.assertEqual(frozen_table.columnWidth(0),frozen.columnWidth(0))
    def test_user_sizing_is_remembered_and_fit_returns_to_filling(self):
        table=self.table();control=enable_table_columns(table);self.app.processEvents()
        self.assertFalse(control.user_sized)
        self.drag(table,0,30)
        self.assertTrue(control.user_sized)
        control.fit_action.trigger();self.app.processEvents()
        self.assertFalse(control.user_sized);self.assertEqual({},control.manual)
        self.double_click_handle(table,1)
        self.assertTrue(control.user_sized)
        control.reset_action.trigger();self.app.processEvents()
        self.assertFalse(control.user_sized)
    def test_wide_table_still_gives_each_column_room_to_read(self):
        table=self.table();table.setColumnCount(30)
        table.setHorizontalHeaderLabels([str(c) for c in range(30)])
        for r in range(10):
            for c in range(30):table.setItem(r,c,QTableWidgetItem('100.0'))
        for c in range(30):table.setColumnWidth(c,20)
        enable_table_columns(table);self.app.processEvents()
        self.assertTrue(all(table.columnWidth(c)>=table.sizeHintForColumn(c) for c in range(30)))
    def small_table(self,headers):
        table=QTableWidget(2,len(headers));self.addCleanup(table.close)
        table.setHorizontalHeaderLabels(headers)
        for r in range(2):
            for c in range(len(headers)):table.setItem(r,c,QTableWidgetItem(f'{r}{c}'))
        table.resize(500,200);table.show();self.app.processEvents()
        return table
    def test_copy_selection_as_tab_separated_text_with_headers(self):
        # 제안 6: results could not be moved to Excel or Hangul.
        from PySide6.QtWidgets import QTableWidgetSelectionRange
        table=self.small_table(['문항','정답률','변별도']);control=enable_table_columns(table)
        table.setRangeSelected(QTableWidgetSelectionRange(0,0,1,1),True)
        control.copy_selection()
        self.assertEqual('문항\t정답률\n00\t01\n10\t11',QApplication.clipboard().text())
    def test_ctrl_c_copies_the_selection(self):
        from PySide6.QtGui import QKeySequence
        table=self.small_table(['문항','정답률']);enable_table_columns(table)
        table.selectRow(1);QApplication.clipboard().clear()
        QTest.keySequence(table.viewport(),QKeySequence.Copy);self.app.processEvents()
        self.assertEqual('문항\t정답률\n10\t11',QApplication.clipboard().text())
    def test_student_table_copies_only_after_the_real_identity_warning(self):
        from unittest.mock import patch
        from PySide6.QtWidgets import QMessageBox
        table=self.small_table(['반/번호','이름','성취도']);control=enable_table_columns(table)
        table.selectAll();QApplication.clipboard().setText('before')
        with patch.object(QMessageBox,'warning',return_value=QMessageBox.No) as warning:
            control.copy_selection()
        warning.assert_called_once()
        self.assertEqual('before',QApplication.clipboard().text())
        with patch.object(QMessageBox,'warning',return_value=QMessageBox.Yes):
            control.copy_selection()
        self.assertTrue(QApplication.clipboard().text().startswith('반/번호\t이름\t성취도'))
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
        dialog.show()
        # The scan runs every 500 ms; wait for its result rather than a fixed time (CI runners are slow).
        ready=lambda:(getattr(table,'_column_controls',None) is not None
                      and table.horizontalHeader().sectionResizeMode(0)==QHeaderView.Interactive)
        for _ in range(60):
            if ready():break
            QTest.qWait(50)
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
