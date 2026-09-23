import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QPushButton
from app.main_window import MainWindow, SpliterWebBridge


class CoreReleaseScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_core_window_does_not_initialize_deferred_ai(self):
        def unexpected_ai(_window):
            raise AssertionError("deferred AI initialized")

        with tempfile.TemporaryDirectory() as tmp:
            settings = QSettings(str(Path(tmp) / "settings.ini"), QSettings.IniFormat)
            with patch("app.main_window.QSettings", return_value=settings), \
                 patch("app.main_window.QWebEngineView", None), \
                 patch.object(MainWindow, "_init_tab_ai_review", new=unexpected_ai):
                window = MainWindow()
                try:
                    labels = [window.tabs.tabText(i) for i in range(window.tabs.count())]
                    self.assertNotIn("AI 문항 검토", labels)
                    self.assertIsNone(window.tab_ai_review)
                    self.assertFalse(hasattr(window, "txt_ai_source"))
                    buttons = [b.text() for b in window.tab_spliter.findChildren(QPushButton)]
                    self.assertFalse(any("시험지" in text for text in buttons))
                    self.assertIn("NEIS 입력표", buttons)
                    project = window._project_from_neis_targets([{
                        "number": 1, "points": 7.125, "type": "선택형", "difficulty": "보통", "target": "C",
                        "rates": dict(zip("ABCDE", (100, 82.5, 63.25, 40, 12.5))),
                    }])
                    bridge = SpliterWebBridge(window)
                    with patch("app.main_window.QFileDialog.getSaveFileName", return_value=("", "")):
                        self.assertFalse(bridge.saveNeisProjectJson(json.dumps(project)))
                    self.assertFalse(list(Path(tmp).glob("*.xlsx")))
                    with patch("app.main_window.QFileDialog.getSaveFileName", return_value=(str(Path(tmp) / "review"), "")):
                        self.assertTrue(bridge.saveNeisProjectJson(json.dumps(project)))
                    self.assertTrue((Path(tmp) / "review.xlsx").is_file())
                finally:
                    window.close()
                    window.deleteLater()


if __name__ == "__main__":
    unittest.main()
