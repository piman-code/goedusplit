"""Synthetic regression checks for on-demand Windows startup."""
from tests.runtime_isolation import ensure_isolated
ensure_isolated()
import unittest
import os
import subprocess
import sys
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
import app.main_window as ui
from app import fonts, lazy_charts
from app.theme import ThemeManager


class DeferredStartupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    @unittest.skipUnless(sys.platform == "win32", "Windows deferred imports")
    def test_fresh_import_does_not_load_chart_or_webengine_modules(self):
        code = "import sys; import app.main_window; assert not any(n in sys.modules for n in ('matplotlib', 'matplotlib.font_manager', 'PySide6.QtWebEngineWidgets', 'PySide6.QtQuickWidgets'))"
        result = subprocess.run([sys.executable, "-B", "-c", code], capture_output=True, text=True, timeout=30, env=dict(os.environ))
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_empty_windows_do_not_create_figures_or_web_views(self):
        with patch.object(ui.sys, "platform", "win32"), \
             patch.object(ui, "QWebEngineView") as web_view, \
             patch.object(ui, "_load_webengine") as web_import, \
             patch.object(lazy_charts, "__getattr__", side_effect=AssertionError("empty startup requested a chart")):
            theme = ThemeManager(self.app)
            theme.set_mode("dark")
            window = ui.MainWindow(theme_manager=theme)
            self.assertIsNone(window.spliter_view)
            self.assertIsNone(window.canvas_round_compare._canvas)
            self.assertIsNone(window.canvas_monitor._canvas)
            self.assertIsNone(window.canvas_monitor_trend._canvas)
            web_view.assert_not_called()
            web_import.assert_not_called()
            self.assertFalse(hasattr(window, "_gpu_surface_anchor"))
            window.close()

    def test_first_calculator_use_creates_once_and_keeps_the_page(self):
        with patch.object(ui.sys, "platform", "win32"):
            window = ui.MainWindow()
            self.assertIsNone(window.spliter_view)
            self.assertTrue(window._create_spliter_view())
            view, page = window.spliter_view, window.spliter_view.page()
            self.assertTrue(page.profile().isOffTheRecord())
            self.assertTrue(window._create_spliter_view())
            self.assertIs(window.spliter_view, view)
            self.assertIs(window.spliter_view.page(), page)
            window.close()

    def test_fonts_registered_once_per_backend(self):
        from matplotlib import font_manager
        from PySide6.QtGui import QFontDatabase
        with patch.object(fonts, "_qt_registered", set()), \
             patch.object(fonts, "_mpl_registered", set()), \
             patch.object(QFontDatabase, "addApplicationFont", return_value=0) as qt, \
             patch.object(font_manager.fontManager, "addfont") as mpl:
            files = [p for p in fonts.font_dir().iterdir() if p.suffix.lower() in (".ttf", ".otf")]
            self.assertGreater(len(files), 0)
            fonts.register_fonts(matplotlib_fonts=False)
            fonts.register_fonts(matplotlib_fonts=False)
            mpl.assert_not_called()
            self.assertEqual(qt.call_count, len(files))
            fonts.register_fonts()
            fonts.register_fonts()
            self.assertEqual(qt.call_count, len(files))
            self.assertEqual(mpl.call_count, len(files))

    def test_deferred_chart_uses_the_selected_theme_and_font_size(self):
        theme = ThemeManager(self.app)
        theme.set_mode("dark")
        theme.set_base_font_pt(16)
        with patch.object(lazy_charts, "_module", None), patch.object(lazy_charts, "_colors", None):
            lazy_charts.set_theme(theme.colors)
            figure = lazy_charts.fig_round_compare(None, None)
            from matplotlib import rcParams
            self.assertEqual(rcParams["axes.facecolor"], theme.colors["chart_bg"])
            self.assertAlmostEqual(rcParams["font.size"], 10 * 16 / 13)
            self.assertEqual(lazy_charts.THEME_COLORS["chart_bg"], theme.colors["chart_bg"])
            self.assertIsNotNone(figure)
