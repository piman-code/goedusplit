"""The screen audit's measuring functions find the problem classes they are named after."""
from tests.runtime_isolation import ensure_isolated
ensure_isolated()

import unittest

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (QApplication, QLayout, QPushButton, QSplitter, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from tests.manual_screen_audit import button_issues, chart_issues, splitter_issues, table_issues


class ScreenAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def window(self):
        root = QWidget(); self.addCleanup(root.close)
        QVBoxLayout(root)
        root.resize(600, 400)
        return root

    def settle(self, root):
        root.show(); self.app.processEvents(); QTest.qWait(1)

    def test_squeezed_splitter_area_is_reported(self):
        root = self.window()
        splitter = QSplitter(Qt.Vertical); root.layout().addWidget(splitter)
        tall = QWidget(); tall.setMinimumHeight(300)
        splitter.addWidget(tall); splitter.addWidget(QWidget())
        # A window shorter than the area's minimum, as on a laptop-height tab.
        root.layout().setSizeConstraint(QLayout.SetNoConstraint)
        root.resize(600, 150)
        self.settle(root)
        self.assertEqual(["칸 겹침"], [i["kind"] for i in splitter_issues(root)])

    def test_clipped_cell_and_header_are_reported(self):
        root = self.window()
        table = QTableWidget(1, 2); root.layout().addWidget(table)
        table.setWordWrap(False)  # app tables set this explicitly; wrapped ones are not width-checked
        table.setHorizontalHeaderLabels(["정기시험 총점과 수행평가", "b"])
        table.setItem(0, 0, QTableWidgetItem("100.0 100.0 100.0"))
        table.setColumnWidth(0, 30)
        self.settle(root)
        kinds = sorted(i["kind"] for i in table_issues(table, "t"))
        self.assertEqual(["머리글 잘림", "표 글자 잘림"], kinds)

    def test_narrow_button_is_reported(self):
        root = self.window()
        button = QPushButton("아주 긴 버튼 이름입니다"); root.layout().addWidget(button)
        button.setFixedWidth(40)
        self.settle(root)
        self.assertEqual(["버튼 글자 잘림"], [i["kind"] for i in button_issues(root)])

    def test_overlapping_chart_texts_are_reported_and_hidden_ticks_ignored(self):
        from app.chart_canvas import _MarginKeepingCanvas  # noqa: F401  (Qt matplotlib backend)
        from app.main_window import CanvasHolder
        from matplotlib.figure import Figure
        root = self.window()
        holder = CanvasHolder(); root.layout().addWidget(holder)
        figure = Figure(figsize=(4, 3))
        ax = figure.add_subplot(111)
        ax.bar([1, 2], [10, 20]); ax.set_xlim(0, 3)
        ax.text(1, 10, "같은 자리 글자"); ax.text(1, 10, "같은 자리 글자 2")
        holder.set_figure(figure)
        self.settle(root)
        issues = chart_issues(holder, "c")
        self.assertEqual(["그래프 글자 겹침"], [i["kind"] for i in issues])
        self.assertNotIn("그래프 글자 잘림", [i["kind"] for i in issues])  # ticks beyond xlim are not drawn


if __name__ == "__main__":
    unittest.main()
