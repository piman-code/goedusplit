from tests.runtime_isolation import ensure_isolated
ensure_isolated()

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, QEvent, QSettings
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QSplitter, QToolButton

from app.perform_tab import PERFORM_DEFAULT_RATES, recalc_summary, recommend_area_scores


def match(level, total, **scores):
    return (None, SimpleNamespace(final_score=total), level, SimpleNamespace(scores=scores))


class RecommendAreaScoresTests(unittest.TestCase):
    def test_uses_the_three_lowest_totals_of_each_level(self):
        area = SimpleNamespace(name="발표", max_score=10)
        matches = [match("A", 99, 발표=10), match("A", 90, 발표=9), match("A", 91, 발표=8),
                   match("A", 92, 발표=7), match("B", 80, 발표=6)]
        (row,) = recommend_area_scores([area], matches)
        self.assertAlmostEqual((9 + 8 + 7) / 3, row["A"])
        self.assertEqual(6.0, row["B"])

    def test_missing_level_falls_back_to_default_rate_and_stays_monotonic(self):
        area = SimpleNamespace(name="보고서", max_score=20)
        (row,) = recommend_area_scores([area], [match("C", 70, 보고서=19)])
        self.assertEqual(20 * PERFORM_DEFAULT_RATES["A"], row["A"])
        self.assertEqual(row["B"], row["C"])  # C's 19 is cut down to B's default 16
        self.assertTrue(all(row[a] >= row[b] for a, b in zip("ABCD", "BCDE")))

    def test_scores_are_clipped_to_the_area_range(self):
        area = SimpleNamespace(name="실험", max_score=10)
        (row,) = recommend_area_scores([area], [match("A", 95, 실험=14), match("E", 30, 실험=-3)])
        self.assertEqual(10.0, row["A"])
        self.assertEqual(0.0, row["E"])


class RecalcSummaryTests(unittest.TestCase):
    def test_totals_and_inversion_warning(self):
        rows = [{"name": "1", "max_score": 10, "scores": {"A": 9, "B": 8, "C": 7, "D": 6, "E": 4}},
                {"name": "2", "max_score": 10, "scores": {"A": 5, "B": 8, "C": 7, "D": 6, "E": 4}}]
        given = ["1: 만점 숫자 확인"]
        max_total, totals, warnings = recalc_summary(rows, given)
        self.assertEqual(20, max_total)
        self.assertEqual({"A": 14, "B": 16, "C": 14, "D": 12, "E": 8}, totals)
        self.assertEqual(["1: 만점 숫자 확인", "A/B 역전"], warnings)
        self.assertEqual(["1: 만점 숫자 확인"], given)  # the caller's list is not changed


class PerformLayoutTests(unittest.TestCase):
    """On a laptop-height window the graph and table areas must not be drawn under each other."""

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
        self.window.tabs.setCurrentWidget(self.window.tab_perform)

    def close_window(self):
        self.app.processEvents()  # let queued relayouts run while the window still exists
        self.window.close()
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.app.processEvents()

    def settle(self, width, height):
        self.window.resize(width, height)
        self.app.processEvents(); QTest.qWait(600)  # table_controls scans tables every 500 ms

    def test_laptop_height_keeps_every_area_at_its_minimum(self):
        for size in ((1312, 810), (1100, 700), (1600, 1200)):
            self.settle(*size)
            for splitter in self.window.tab_perform.findChildren(QSplitter):
                if splitter.orientation().name != "Vertical":
                    continue
                sizes = splitter.sizes()
                for index in range(splitter.count()):
                    area = splitter.widget(index)
                    with self.subTest(size=size, area=index):
                        self.assertGreaterEqual(sizes[index], area.minimumSizeHint().height())
                        self.assertLessEqual(area.height(), sizes[index])

    def test_recalc_input_table_shows_several_elements(self):
        self.settle(1312, 810)
        self.window.perform_table_tabs.setCurrentIndex(2)
        self.settle(1312, 810)
        table = self.window.table_perform_recalc
        visible_rows = (table.viewport().height()) // table.verticalHeader().defaultSectionSize()
        self.assertGreaterEqual(visible_rows, 5)

    def test_column_width_button_shows_its_whole_label(self):
        self.settle(1312, 810)
        button = self.window.perform_table_tabs.cornerWidget()
        self.assertIsInstance(button, QToolButton)
        self.assertEqual("열 너비 ▾", button.text())
        self.assertIn("image: none", button.styleSheet())  # no second arrow over the label
        self.assertGreaterEqual(button.width(), button.fontMetrics().horizontalAdvance(button.text()) + 8)


if __name__ == "__main__":
    unittest.main()
