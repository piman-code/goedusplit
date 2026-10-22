from tests.runtime_isolation import ensure_isolated
ensure_isolated()

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, QEvent, QSettings
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QSplitter, QTableWidgetItem

from app.monitor_tab import monitor_rows_and_benchmarks, z_status


THRESHOLDS = {"th_a_delta": 10.0, "th_mean_stable": 5.0, "th_cut_delta": 10.0}


def inputs(**values):
    """Same as an input box: anything not entered reads as 0."""
    merged = dict(THRESHOLDS, **values)
    return lambda key: merged.get(key, 0.0)


class ZStatusTests(unittest.TestCase):
    def test_missing_reference_is_not_compared_as_zero(self):
        self.assertEqual(z_status(30.0, 0.0, 5.0)[0], "기준 입력 필요")
        self.assertEqual(z_status(30.0, 20.0, 0.0)[2], 0)

    def test_levels_follow_standard_deviations(self):
        self.assertEqual(z_status(24.0, 20.0, 5.0)[0], "참고 범위")
        self.assertEqual(z_status(27.0, 20.0, 5.0)[0], "Ⅱ 주의")
        self.assertEqual(z_status(30.0, 20.0, 5.0)[0], "Ⅲ 점검")

    def test_low_is_risk_flips_direction(self):
        self.assertEqual(z_status(60.0, 80.0, 5.0, low_is_risk=True)[0], "Ⅲ 점검")
        self.assertEqual(z_status(90.0, 80.0, 5.0, low_is_risk=True)[0], "참고 범위")


class MonitorRowsTests(unittest.TestCase):
    def test_no_inputs_gives_six_rows_and_empty_benchmarks(self):
        rows, benchmarks = monitor_rows_and_benchmarks(25.0, 70.0, 80.0, inputs())
        self.assertEqual(6, len(rows))
        self.assertEqual("참고 범위", rows[1][3])  # mean below A/B cut
        self.assertEqual(["기준 입력 필요"] * 2, [rows[4][3], rows[5][3]])
        self.assertTrue(all(b["ref"] is None and b["sd"] is None for b in benchmarks))

    def test_mean_at_or_above_cut_is_flagged(self):
        rows, _ = monitor_rows_and_benchmarks(25.0, 81.0, 80.0, inputs())
        self.assertEqual(("Ⅲ 점검", 3), (rows[1][3], rows[1][5]))

    def test_a_rise_without_mean_change_is_a_feature(self):
        rows, _ = monitor_rows_and_benchmarks(
            30.0, 72.0, 80.0, inputs(prev_a_pct=15.0, prev_mean=70.0, prev_cut_a=92.0))
        self.assertEqual("특성 발생", rows[4][3])
        self.assertEqual("특성 발생", rows[5][3])


class MonitorLayoutTests(unittest.TestCase):
    """On a laptop-height window the chart, trend and table areas must not be drawn over each other."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from app.main_window import MainWindow
        resources = ExitStack()
        self.addCleanup(resources.close)
        tmp = resources.enter_context(tempfile.TemporaryDirectory())
        settings = QSettings(str(Path(tmp) / "settings.ini"), QSettings.IniFormat)
        settings.setFallbacksEnabled(False)
        resources.enter_context(patch("app.main_window.QSettings", return_value=settings))
        resources.enter_context(patch("app.main_window.QWebEngineView", None))
        self.window = MainWindow()
        self.addCleanup(self.close_window)
        self.window.show()
        self.window.tabs.setCurrentWidget(self.window.tab_monitor)

    def close_window(self):
        self.app.processEvents()  # let queued relayouts run while the window still exists
        self.window.close()
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.app.processEvents()

    def assert_areas_do_not_overlap(self, width, height):
        self.window.resize(width, height)
        self.app.processEvents(); QTest.qWait(1)
        for splitter in self.window.tab_monitor.findChildren(QSplitter):
            if splitter.orientation().name != "Vertical":
                continue
            sizes = splitter.sizes()
            for index in range(splitter.count()):
                area = splitter.widget(index)
                with self.subTest(size=(width, height), area=index):
                    self.assertGreaterEqual(sizes[index], area.minimumSizeHint().height())
                    self.assertLessEqual(area.height(), sizes[index])

    def test_laptop_height_keeps_every_area_at_its_minimum(self):
        self.assert_areas_do_not_overlap(1312, 810)
        self.assert_areas_do_not_overlap(1100, 700)

    def test_check_table_fills_width_and_copies_as_tab_separated_text(self):
        from app.monitor_tab import copy_monitor_table
        window = self.window
        window.resize(1312, 810); self.app.processEvents()
        table = window.table_monitor
        table.setRowCount(1)
        for c, text in enumerate(["필수 1", "20.0%", "기준\n두 줄", "참고 범위", "설명"]):
            table.setItem(0, c, QTableWidgetItem(text))
        for c, width in enumerate([250, 180, 260, 120, 520]):
            window._set_scaled_column_width(table, c, width)
        self.app.processEvents(); QTest.qWait(1)
        self.assertLessEqual(abs(sum(table.columnWidth(c) for c in range(5)) - table.viewport().width()), 5)
        copy_monitor_table(window)
        self.assertEqual("지표\t현재/변화\t기준\t판정\t해석·질문\n필수 1\t20.0%\t기준 두 줄\t참고 범위\t설명",
                         QApplication.clipboard().text())

    def test_check_table_has_column_width_menu(self):
        from PySide6.QtWidgets import QToolButton
        buttons = [b for b in self.window.tab_monitor.findChildren(QToolButton) if b.text() == "열 너비 ▾"]
        self.assertEqual(1, len(buttons))
        labels = [a.text() for a in buttons[0].menu().actions()]
        self.assertEqual(["화면에 맞춤", "모든 열 내용에 맞춤", "초기 너비로 되돌리기"], labels)

    def test_restoring_work_refits_tables_the_teacher_did_not_size(self):
        # Folder batch analysis captures and re-applies the whole UI; widths of never-shown tables
        # must not come back as the teacher's own choice.
        from app.work_session_ui import apply_python_state, capture_ui_state
        from app.work_sessions import build_session, prepare_session
        from tests.test_work_sessions import synthetic_domain
        window = self.window
        window.resize(1312, 810); self.app.processEvents(); QTest.qWait(1)
        state = capture_ui_state(window)
        self.assertTrue(all(c["mode"] == 1 and c["width"] is None for c in state["table_headers"]["table_monitor"]["state"]))
        self.assertTrue(all(c["mode"] == 0 for c in state["table_headers"]["table_data"]["state"]))
        exam, perform = synthetic_domain()
        apply_python_state(window, prepare_session(build_session(exam, perform, state, None)))
        self.app.processEvents(); QTest.qWait(1)
        table = window.table_monitor
        self.assertEqual({}, table._column_controls.manual)
        self.assertLessEqual(abs(sum(table.columnWidth(c) for c in range(5)) - table.viewport().width()), 5)
        # Splitters of tabs never shown before the capture must not come back collapsed to 0
        # (the monitoring "전년도·판정 기준" box and the rounds "학생 이동" table disappeared).
        for tab in (window.tab_monitor, window.tab_rounds):
            window.tabs.setCurrentWidget(tab); self.app.processEvents(); QTest.qWait(1)
            for splitter in tab.findChildren(QSplitter):
                if splitter.isVisible():
                    with self.subTest(tab=window.tabs.tabText(window.tabs.indexOf(tab)), sizes=splitter.sizes()):
                        self.assertTrue(all(size > 0 for i, size in enumerate(splitter.sizes())
                                            if not splitter.widget(i).isHidden()))

    def test_tall_window_still_fills_without_scrolling(self):
        self.assert_areas_do_not_overlap(1600, 1200)


if __name__ == "__main__":
    unittest.main()
