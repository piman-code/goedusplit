import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, QEvent, QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QScrollArea, QTableWidget

from app import charts
from app.calibration import headline_lines
from app.main_window import FoldSection, MainWindow, _MarginKeepingCanvas, build_data_empty_state_html
from app.widgets import NaturalItem, install_frozen_columns
try:
    from test_calibration import _exam
except ModuleNotFoundError:  # run as tests.test_beginner_ux
    from tests.test_calibration import _exam


class BeginnerTextTests(unittest.TestCase):
    def test_start_guide_numbers_once_and_separates_title_from_text(self):
        html = build_data_empty_state_html()
        self.assertNotIn("1. 입력 데이터", html)          # <ol> numbers the steps
        self.assertIn("<b>입력 데이터</b> — 왼쪽에서", html)
        self.assertIn("시험지에서 문항 가져오기", html)   # no longer says paper import is a later version

    def test_comparison_headline_names_the_largest_misses_in_plain_words(self):
        def row(number, relative):
            return {"type": "선택형", "number": str(number), "predicted": dict.fromkeys("ABCDE", 70.0),
                    "border": dict.fromkeys("ABCDE", 50.0), "relative": dict(dict.fromkeys("ABCDE"), C=relative)}
        lines = headline_lines({"rows": [row(1, 5.0), row(2, -29.0), row(3, 20.0), row(4, -16.0), row(5, 18.0)]})
        self.assertTrue(lines[0].startswith("선택형 2번 · C/D 경계: 예측 70% → 실제 50%"))
        self.assertIn("29%p 높게 예측", lines[0])
        self.assertEqual(len(lines), 4)
        self.assertIn("그 밖에 1칸", lines[-1])
        self.assertIn("크게 빗나간 칸이 없습니다", headline_lines({"rows": [row(1, 5.0)]})[0])


class FrozenColumnSortTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_freezing_a_column_keeps_the_ascending_order(self):
        table = QTableWidget(18, 2)
        for r, number in enumerate(range(18, 0, -1)):
            table.setItem(r, 0, NaturalItem(f"문{number}", number))
        table.setSortingEnabled(True)
        table.sortByColumn(0, Qt.AscendingOrder)
        install_frozen_columns(table, frozen_count=1)   # used to re-sort by Qt's default, descending
        self.assertEqual([table.item(r, 0).text() for r in range(3)], ["문1", "문2", "문3"])


class ChartMarginTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_axis_title_stays_inside_a_shorter_chart(self):
        scores = [50.0 + i % 40 for i in range(120)]
        fig = charts.fig_score_histogram_colored(scores, ["C"] * len(scores))
        design = dict(vars(fig.subplotpars))
        canvas = _MarginKeepingCanvas(fig)
        canvas.show()

        def resize(width, height):
            canvas.resize(width, height)
            QTest.qWait(50)
            canvas.draw()

        # Small, then large, then smaller: the first fit must not freeze the margins.
        resize(800, 300)
        resize(1400, 700)                                # larger than designed: designed margins again
        for key in ("left", "right", "bottom", "top"):
            self.assertAlmostEqual(getattr(fig.subplotpars, key), design[key], places=3, msg=key)
        resize(900, 150)
        label = fig.axes[0].xaxis.label.get_window_extent(canvas.get_renderer())
        self.assertGreaterEqual(label.y0, 0)             # was below the figure's edge
        canvas.close()


class WindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.resources = ExitStack()
        self.addCleanup(self.resources.close)
        tmp = Path(self.resources.enter_context(tempfile.TemporaryDirectory()))
        settings = QSettings(str(tmp / "settings.ini"), QSettings.IniFormat)
        self.resources.enter_context(patch("app.main_window.QSettings", return_value=settings))
        self.resources.enter_context(patch("app.main_window.QWebEngineView", None))
        self.resources.enter_context(patch.object(MainWindow, "_ai_material_root_dir", lambda _self: tmp / "appdata"))
        exam, _levels = _exam()
        self.resources.enter_context(patch("app.main_window.load_exam", return_value=exam))
        self.window = MainWindow()
        self.addCleanup(self.close_window)
        self.window.show()
        self.window.resize(1320, 860)
        self.settle()

    def close_window(self):
        self.window.close()
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.app.processEvents()

    def settle(self):
        for _ in range(3):
            self.app.processEvents()
            QTest.qWait(5)

    def analyze(self):
        self.window.fs_response.path_edit.setText("/합성/정오표.xlsx")
        self.window.fs_iteminfo.path_edit.setText("/합성/문항정보표.xlsx")
        self.window.run_analysis()
        self.settle()

    def test_first_launch_uses_the_readable_tab_names(self):
        self.assertEqual(self.window.tabs.tabText(1), "포트폴리오")   # not the tiny "학생"

    def test_run_button_is_outside_the_scrolling_panel(self):
        button = self.window.btn_run_analysis
        parent = button.parentWidget()
        while parent is not None:
            self.assertNotIsInstance(parent, QScrollArea)
            parent = parent.parentWidget()
        self.assertTrue(button.isVisible())

    def test_empty_charts_and_filters_appear_only_after_analysis(self):
        self.assertFalse(self.window.data_results.isVisible())
        self.analyze()
        self.assertTrue(self.window.data_results.isVisible())
        self.assertFalse(self.window.data_empty_state.isVisible())

    def test_header_buttons_say_what_they_do_after_a_theme_change(self):
        self.window._refresh_header_icons()
        self.assertEqual(self.window.btn_counsel_mode.text(), "상담 모드")
        self.assertEqual(self.window.btn_zoom_reset.text(), "기본")
        self.assertEqual(self.window.btn_sidebar.text(), "입력 패널")

    def test_answer_marks_are_explained(self):
        self.analyze()
        table = self.window.table_data
        headers = [table.horizontalHeaderItem(c) for c in range(table.columnCount())]
        item_header = next(h for h in headers if h.text() == "문1")
        self.assertIn(". = 정답", item_header.toolTip())
        self.assertIn(". = 정답", self.window.lbl_data_note.text())

    def test_item_analysis_starts_at_the_first_item_and_explains_terms(self):
        self.analyze()
        self.assertEqual(self.window.table_items.item(0, 0).text(), "문1")
        self.assertIn("점수가 높은 학생", self.window.table_items.horizontalHeaderItem(3).toolTip())
        self.assertIn("일관되게", self.window.lbl_alpha.toolTip())

    def test_blank_monitoring_inputs_read_not_entered(self):
        spins = self.window.monitor_spins
        self.assertEqual(spins["ref_a_mean"].spin.text(), "미입력")
        self.assertEqual(spins["prev_mean"].spin.text(), "미입력")
        self.assertNotEqual(spins["th_a_delta"].spin.text(), "미입력")   # thresholds keep their values
        # a blank ('미입력') national mean with a filled SD is still "not entered", not a comparison with 0
        status = self.window._monitor_z_status(30.0, 0.0, 5.0)
        self.assertEqual(status[0], "기준 입력 필요")
        self.assertEqual(self.window._monitor_z_status(27.0, 20.0, 5.0)[0], "Ⅱ 주의")

    def test_portfolio_note_leaves_the_folder_path_to_its_button(self):
        self.window.refresh_portfolio_tab()
        note = self.window.lbl_portfolio_note
        self.assertNotIn("appdata", note.text())
        self.assertIn("appdata", note.toolTip())

    def test_large_areas_fold_give_their_room_away_and_remember_it(self):
        self.analyze()
        self.window.tabs.setCurrentWidget(self.window.tab_data)
        self.settle()
        folds = {fold._key.split("/")[-1]: fold for fold in self.window.findChildren(FoldSection)}
        for key in ("data.chart", "items.charts", "overview.levels", "monitor.inputs", "standard.chart", "choice.chart"):
            self.assertTrue(folds[key].is_open(), key)                 # open by default
        chart, table = folds["data.chart"], folds["data.table"]
        before = table.height()
        chart.toggle.click()
        self.settle()
        self.assertFalse(chart.body.isVisible())
        self.assertLessEqual(chart.height(), chart.toggle.sizeHint().height() + 4)
        self.assertGreater(table.height(), before + 50)                # the table got the chart's room
        self.assertEqual(self.window.settings.value("ui/fold/data.chart"), "0")
        chart.toggle.click()
        self.settle()
        self.assertTrue(chart.body.isVisible())
        self.assertGreaterEqual(chart.height(), 150)                   # room taken back on unfolding
        chart.toggle.click()
        self.settle()
        again = MainWindow()                                           # the next launch keeps it folded
        self.addCleanup(again.close)
        folded = next(f for f in again.findChildren(FoldSection) if f._key.endswith("data.chart"))
        self.assertFalse(folded.is_open())


if __name__ == "__main__":
    unittest.main()
