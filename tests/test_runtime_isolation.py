from tests.runtime_isolation import ensure_isolated
ensure_isolated()

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
from app.main_window import MainWindow


class RuntimeIsolationTests(unittest.TestCase):
    def test_window_ignores_a_decoy_user_portfolio_and_writes_only_scratch(self):
        app = QApplication.instance() or QApplication([])
        root = ensure_isolated()
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            real = home / "Library" / "Application Support" / "Goedu-Split" / "subject_snapshots"
            real.mkdir(parents=True)
            decoy = real / "user-snapshot.json"
            decoy.write_text(json.dumps({"version": 2, "subject": "USER_DECOY", "students": []}))
            original = decoy.read_bytes()
            # Removing appdata isolation would make a macOS window discover this decoy.
            with patch("app.main_window.Path.home", return_value=home), patch("app.main_window.QWebEngineView", None):
                window = MainWindow()
                try:
                    self.assertEqual(window._portfolio_store_dir(), root / "appdata" / "subject_snapshots")
                    self.assertEqual(window.settings.format(), QSettings.IniFormat)
                    self.assertFalse(window.settings.fallbacksEnabled())
                    self.assertTrue(Path(window.settings.fileName()).is_relative_to(root))
                    window.settings.setValue("isolation/probe", "synthetic")
                    window.settings.sync()
                    self.assertTrue(Path(window.settings.fileName()).exists())
                    self.assertEqual(list(real.iterdir()), [decoy])
                    self.assertEqual(decoy.read_bytes(), original)
                finally:
                    window.close()
                    window.deleteLater()
                    app.processEvents()

    def test_ai_and_temp_writes_stay_inside_the_same_runtime(self):
        from app.ai_client import CODEX_CLI_WORKDIR, _codex_review_rows_schema_path
        root = ensure_isolated()
        self.assertTrue(CODEX_CLI_WORKDIR.is_relative_to(root))
        self.assertTrue(_codex_review_rows_schema_path().is_relative_to(root))
        with tempfile.TemporaryDirectory() as directory:
            self.assertTrue(Path(directory).is_relative_to(root))

    def test_unmocked_network_access_fails_before_transfer(self):
        import urllib.request
        with self.assertRaisesRegex(AssertionError, "Network access is forbidden"):
            urllib.request.urlopen("https://example.invalid/never-contacted")
