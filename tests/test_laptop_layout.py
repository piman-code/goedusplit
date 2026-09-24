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
        self.assert_sidebar_open()

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

    def toggle_sidebar(self):
        QTest.mouseClick(self.window.btn_sidebar, Qt.LeftButton)
        self.settle()

    def assert_sidebar_open(self):
        self.assertGreater(self.window.splitter.sizes()[0], 4)

    def assert_sidebar_closed(self):
        self.assertLessEqual(self.window.splitter.sizes()[0], 4)

    def assert_reopen_survives_height_changes(self):
        self.toggle_sidebar()
        self.assert_sidebar_open()
        # A same-size event can arrive while Qt settles a layout or theme update.
        size = self.window.size()
        QApplication.sendEvent(self.window, QResizeEvent(size, size))
        self.settle()
        self.assert_sidebar_open()
        for height in (801, 840, 800):
            with self.subTest(height=height):
                self.resize_window(self.window.width(), height)
                self.assert_sidebar_open()

    def test_manual_collapse_survives_laptop_and_wide_resizes(self):
        self.resize_window(1280)
        self.toggle_sidebar()
        self.assert_sidebar_closed()
        for width in (1281, 1440, 1600):
            with self.subTest(width=width):
                self.resize_window(width)
                self.assert_sidebar_closed()
                self.resize_window(width, 801)
                self.assert_sidebar_closed()

    def test_manual_collapse_is_not_reopened_by_resize_or_tab_changes(self):
        self.toggle_sidebar()
        for width in (1080, 1179, 1180, 1439, 1440, 1600):
            with self.subTest(width=width):
                self.resize_window(width)
                self.assert_sidebar_closed()
                self.set_tab(self.window.tab_spliter)
                self.assert_sidebar_closed()
                self.set_tab(self.window.tab_data)
                self.assert_sidebar_closed()

    def test_automatic_collapse_and_restore_have_distinct_width_boundaries(self):
        self.resize_window(1180)
        self.assert_sidebar_open()
        self.resize_window(1179)
        self.assert_sidebar_closed()
        for width in (1180, 1281, 1439):
            with self.subTest(width=width):
                self.resize_window(width)
                self.assert_sidebar_closed()
        self.resize_window(1440)
        self.assert_sidebar_open()
        self.resize_window(1600)
        self.assert_sidebar_open()
        self.resize_window(1080)
        self.assert_sidebar_closed()
        self.resize_window(1440)
        self.assert_sidebar_open()

    def test_entering_calculator_below_1440_collapses_sidebar_by_default(self):
        for width in (1180, 1280, 1439):
            with self.subTest(width=width):
                self.set_tab(self.window.tab_data)
                self.resize_window(1600)
                self.resize_window(width)
                self.assert_sidebar_open()
                self.set_tab(self.window.tab_spliter)
                self.assert_sidebar_closed()

    def test_calculator_restores_automatic_sidebar_at_1440(self):
        self.resize_window(1440)
        self.set_tab(self.window.tab_spliter)
        self.assert_sidebar_open()
        self.resize_window(1439)
        self.assert_sidebar_closed()
        self.resize_window(1440)
        self.assert_sidebar_open()

    def test_calculator_keeps_tab_names_and_gives_the_input_panel_back(self):
        def labels():
            return [self.window.tabs.tabText(i) for i in range(self.window.tabs.count())]

        # 1435: the tab bar is wide enough for the long names only once the panel is hidden.
        for width in (1280, 1435):
            with self.subTest(width=width):
                self.set_tab(self.window.tab_data)
                self.resize_window(1600)
                self.resize_window(width)
                self.assert_sidebar_open()
                before = labels()
                self.set_tab(self.window.tab_spliter)
                self.assert_sidebar_closed()
                self.assertEqual(labels(), before)
                self.set_tab(self.window.tab_data)
                self.assert_sidebar_open()
                self.assertEqual(labels(), before)

    def test_narrow_window_or_manual_toggle_ends_the_calculator_collapse(self):
        def labels():
            return [self.window.tabs.tabText(i) for i in range(self.window.tabs.count())]

        def calculator_hides_panel_at_1300():
            self.set_tab(self.window.tab_data)
            self.resize_window(1600)
            self.resize_window(1300)
            self.assert_sidebar_open()
            self.set_tab(self.window.tab_spliter)
            self.assert_sidebar_closed()
            self.assertTrue(self.window._sidebar_hidden_for_calculator)

        self.resize_window(1100)
        narrow = labels()
        calculator_hides_panel_at_1300()
        self.resize_window(1100)
        self.set_tab(self.window.tab_data)
        self.assertEqual(labels(), narrow)     # hidden for the window size now, not for the calculator
        self.assert_sidebar_closed()
        calculator_hides_panel_at_1300()
        self.toggle_sidebar()                  # opened by hand on the calculator
        self.toggle_sidebar()                  # and closed again by hand
        self.assertFalse(self.window._sidebar_hidden_for_calculator)
        self.set_tab(self.window.tab_data)
        self.assert_sidebar_closed()           # the teacher's choice stays

    def test_manual_reopen_on_narrow_main_tab_survives_layout_events(self):
        self.resize_window(1080)
        self.assert_sidebar_closed()
        self.assert_reopen_survives_height_changes()

    def test_manual_reopen_on_calculator_survives_layout_events(self):
        self.resize_window(1280)
        self.set_tab(self.window.tab_spliter)
        self.assert_sidebar_closed()
        self.assert_reopen_survives_height_changes()

    def test_show_input_action_keeps_narrow_sidebar_open(self):
        self.resize_window(1080)
        self.assert_sidebar_closed()
        self.window._show_sidebar()
        self.settle()
        self.assert_sidebar_open()
        self.resize_window(1080, 801)
        self.assert_sidebar_open()

    def test_main_tab_labels_follow_available_pane_width(self):
        def labels():
            return [self.window.tabs.tabText(i) for i in range(self.window.tabs.count())]

        outer_width = self.window.width()
        narrow_width = self.window.tabs.width()
        narrow_labels = labels()
        self.toggle_sidebar()
        wide_labels = labels()
        self.assertEqual(self.window.width(), outer_width)
        self.assertGreater(self.window.tabs.width(), narrow_width)
        self.assertGreater(sum(map(len, wide_labels)), sum(map(len, narrow_labels)))
        for widget, full, _compact, _tiny in self.window._tab_label_sets:
            index = self.window.tabs.indexOf(widget)
            self.assertEqual(self.window.tabs.tabText(index), full)
            self.assertEqual(self.window.tabs.tabToolTip(index), full)
        self.toggle_sidebar()
        self.assertEqual(labels(), narrow_labels)


if __name__ == "__main__":
    unittest.main()
