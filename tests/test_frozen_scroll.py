"""Synthetic wheel and viewport regression for shared frozen table rows."""
from tests.runtime_isolation import ensure_isolated
ensure_isolated()
import unittest
from PySide6.QtCore import Qt, QPoint, QPointF
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QTableWidget, QTableWidgetItem, QAbstractItemView
from app.widgets import install_frozen_columns, refresh_frozen_columns

class FrozenScrollTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
    def setUp(self):
        self.table = QTableWidget(60, 8)
        self.addCleanup(self.table.close)
        self.table.resize(580, 340)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        for r in range(60):
            for c in range(8):
                self.table.setItem(r,c,QTableWidgetItem(f'{60-r:03}-{c}'))
            self.table.setRowHeight(r, 28 + r % 3 * 7)
        self.table.setSortingEnabled(True)
        self.table.show()
        self.app.processEvents()
        self.frozen = install_frozen_columns(self.table, 2)
        self.app.processEvents()
    def assert_aligned(self):
        a,b = self.table,self.frozen
        origin_a=a.viewport().mapToGlobal(QPoint(0,0)).y()
        origin_b=b.viewport().mapToGlobal(QPoint(0,0)).y()
        for r in range(60):
            self.assertEqual(origin_a+a.rowViewportPosition(r),origin_b+b.rowViewportPosition(r),f'row {r} viewport y')
    def wheel(self, view):
        pos=QPointF(30,70)
        event=QWheelEvent(pos,QPointF(view.viewport().mapToGlobal(pos.toPoint())),QPoint(),QPoint(0,-120),Qt.NoButton,Qt.NoModifier,Qt.ScrollUpdate,False)
        QApplication.sendEvent(view.viewport(),event)
        self.app.processEvents()
    def test_wheel_over_frozen_and_body_keeps_rows_aligned(self):
        self.wheel(self.frozen)
        self.assertGreater(self.table.verticalScrollBar().value(),0)
        self.assert_aligned()
        self.wheel(self.table)
        self.assert_aligned()
    def test_scrollbar_middle_end_sort_resize_remain_aligned(self):
        bar=self.table.verticalScrollBar()
        for value in [bar.maximum()//2,bar.maximum(),0]:
            bar.setValue(value);self.app.processEvents();self.assert_aligned()
        self.frozen.horizontalHeader().setSortIndicator(0,Qt.AscendingOrder)
        self.app.processEvents();self.assert_aligned()
        self.table.resize(650,410)
        self.app.processEvents();refresh_frozen_columns(self.table)
        bar.setValue(bar.maximum());self.app.processEvents();self.assert_aligned()

    def test_filter_row_height_horizontal_end_and_keyboard_end(self):
        for r in range(0,60,4):
            self.table.setRowHidden(r,True)
        self.table.setRowHeight(5,79)
        refresh_frozen_columns(self.table)
        self.table.horizontalScrollBar().setValue(self.table.horizontalScrollBar().maximum())
        self.table.setFocus()
        QTest.keyClick(self.table,Qt.Key_End,Qt.ControlModifier)
        self.app.processEvents();self.assert_aligned()
        self.frozen.verticalScrollBar().setValue(self.frozen.verticalScrollBar().maximum())
        self.app.processEvents();self.assert_aligned()
        self.assertEqual(self.table.viewport().height(),self.frozen.viewport().height())
    def test_item_scroll_mode_and_single_frozen_column(self):
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollPerItem)
        self.table.frozenCount=1
        refresh_frozen_columns(self.table)
        self.wheel(self.frozen);self.assert_aligned()
        self.table.verticalScrollBar().setValue(self.table.verticalScrollBar().maximum())
        self.app.processEvents();self.assert_aligned()
    def test_real_light_dark_styles_at_100_and_120_percent(self):
        from app.theme import _build_qss
        from app.palettes import LIGHT, DARK
        original=self.app.styleSheet()
        self.addCleanup(self.app.setStyleSheet,original)
        for palette in [LIGHT,DARK]:
            for font_size in [13,16]:
                self.app.setStyleSheet(_build_qss(palette,font_size))
                self.app.processEvents()
                refresh_frozen_columns(self.table)
                self.app.processEvents()
                self.table.verticalScrollBar().setValue(self.table.verticalScrollBar().maximum())
                self.app.processEvents();self.assert_aligned()
                self.table.verticalScrollBar().setValue(0)
                self.wheel(self.frozen);self.assert_aligned()
