"""Opt-in check on the real macOS window system: opening the 예상정답률 tab must not recreate the window.

Run from the repository (a window appears for a few seconds, synthetic data only):
    .venv/bin/python tests/manual_native_window.py --run

The calculator's web view draws through the GPU. Without a GPU widget present from the start, Qt
destroyed and recreated the main window's native surface the first time the tab was shown, which
looked like the app closing and starting again. The offscreen platform used by the unit tests has
no such surfaces, so this is checked here instead.
"""

import argparse
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch


def run() -> int:
    with tempfile.TemporaryDirectory(prefix="goedusplit-native-window-", ignore_cleanup_errors=True) as folder:
        return _run(Path(folder))


def _run(scratch: Path) -> int:
    os.environ["MPLCONFIGDIR"] = str(scratch / "matplotlib")
    sys.path[:0] = [str(Path(__file__).resolve().parents[1]), str(Path(__file__).resolve().parent)]
    from PySide6.QtCore import QEvent, QObject, QSettings
    from PySide6.QtTest import QTest
    from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
    from PySide6.QtWidgets import QApplication
    from app.analysis import analyze_items, analyze_overall, build_score_matrix
    from app.main_window import MainWindow
    from test_calibration import _exam

    app = QApplication([])
    profile = QWebEngineProfile(app)
    destroyed = []

    class Watch(QObject):
        def eventFilter(self, obj, event):
            if event.type() == QEvent.PlatformSurface and event.surfaceEventType().name == "SurfaceAboutToBeDestroyed":
                destroyed.append(obj.surfaceType().name)
            return False

    with patch("app.main_window.QSettings", return_value=QSettings(str(scratch / "settings.ini"), QSettings.IniFormat)), \
         patch("app.main_window.QWebEnginePage", side_effect=lambda parent: QWebEnginePage(profile, parent)), \
         patch.object(MainWindow, "_ai_material_root_dir", lambda _self: scratch / "appdata"):
        window = MainWindow()
        window.exam, levels = _exam()
        score, _, _ = build_score_matrix(window.exam)
        window.overall = analyze_overall(window.exam, score)
        window.overall.levels_arr = levels
        window.item_stats = analyze_items(window.exam)[0]
        window.show()
        window.resize(1440, 900)
        QTest.qWait(800)
        watch = Watch()
        window.windowHandle().installEventFilter(watch)
        first_id = int(window.winId())
        first_surface = window.windowHandle().surfaceType().name
        window.tabs.setCurrentWidget(window.tab_spliter)
        QTest.qWait(3000)
        window.tabs.setCurrentWidget(window.tab_data)
        QTest.qWait(500)
        window.tabs.setCurrentWidget(window.tab_spliter)
        QTest.qWait(1500)
        results = {
            "window starts with GPU drawing": first_surface != "RasterSurface",
            "opening the calculator tab does not recreate the window": not destroyed and int(window.winId()) == first_id,
        }
        window.close()
        QTest.qWait(800)
    for name, ok in results.items():
        print(("passed  " if ok else "FAILED  ") + name, flush=True)
    return 0 if all(results.values()) else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", action="store_true", help="Show a window on this screen and run the check")
    if not parser.parse_args().run:
        parser.error("--run is required; it opens a real window for a few seconds")
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
