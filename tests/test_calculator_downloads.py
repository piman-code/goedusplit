import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

try:
    from app.main_window import MainWindow, QWebEngineDownloadRequest
except ModuleNotFoundError as exc:
    MainWindow = None
    IMPORT_ERROR = exc
else:
    IMPORT_ERROR = None


class _Request:
    """Stand-in for QWebEngineDownloadRequest with the calls the handler uses."""

    def __init__(self, page, name):
        self._page, self._name, self._dir = page, name, ""
        self.accepted = self.cancelled = False
        self.isFinishedChanged = Mock()
        self.finished, self.status = False, None

    def page(self): return self._page
    def downloadFileName(self): return self._name
    def downloadDirectory(self): return self._dir
    def setDownloadDirectory(self, value): self._dir = value
    def setDownloadFileName(self, value): self._name = value
    def accept(self): self.accepted = True
    def cancel(self): self.cancelled = True
    def isFinished(self): return self.finished
    def state(self): return self.status
    def interruptReasonString(self): return "synthetic"


@unittest.skipIf(MainWindow is None or QWebEngineDownloadRequest is None, f"WebEngine unavailable: {IMPORT_ERROR}")
class CalculatorDownloadTests(unittest.TestCase):
    def _window(self):
        window = MainWindow.__new__(MainWindow)
        window.spliter_view = Mock()
        window.statusBar = Mock()
        return window

    def test_accepts_calculator_download_into_chosen_path(self):
        window = self._window()
        request = _Request(window.spliter_view.page(), "expected-rate-project.json")
        with TemporaryDirectory() as directory, \
             patch("app.main_window.QFileDialog.getSaveFileName", return_value=(str(Path(directory) / "내작업"), "")):
            window._on_spliter_download_requested(request)
        self.assertTrue(request.accepted)
        self.assertFalse(request.cancelled)
        self.assertEqual((Path(request.downloadDirectory()), request.downloadFileName()), (Path(directory), "내작업.json"))
        request.isFinishedChanged.connect.assert_called_once()

    def test_cancelled_dialog_and_foreign_page_do_not_download(self):
        window = self._window()
        request = _Request(window.spliter_view.page(), "expected-rate-results.csv")
        with patch("app.main_window.QFileDialog.getSaveFileName", return_value=("", "")):
            window._on_spliter_download_requested(request)
        self.assertTrue(request.cancelled)
        self.assertFalse(request.accepted)

        foreign = _Request(object(), "x.csv")
        with patch("app.main_window.QFileDialog.getSaveFileName") as dialog:
            window._on_spliter_download_requested(foreign)
        dialog.assert_not_called()
        self.assertTrue(foreign.cancelled)

    def test_finished_csv_is_checked_for_formulas_and_reported(self):
        window = self._window()
        with TemporaryDirectory() as directory:
            target = Path(directory) / "결과.csv"
            target.write_bytes('\ufeff문항,메모\r\n1,=HYPERLINK("x")\r\n2,-5\r\n'.encode("utf-8"))
            request = _Request(window.spliter_view.page(), target.name)
            request.setDownloadDirectory(directory)
            request.finished = True
            request.status = QWebEngineDownloadRequest.DownloadState.DownloadCompleted
            window._on_spliter_download_finished(request)
            data = target.read_bytes().decode("utf-8")
        self.assertEqual(data, '\ufeff문항,메모\r\n1,"\'=HYPERLINK(""x"")"\r\n2,-5\r\n')
        window.statusBar().showMessage.assert_called_once()

    def test_csv_gets_bom_and_is_checked_even_if_renamed(self):
        window = self._window()
        with TemporaryDirectory() as directory:
            target = Path(directory) / "결과.txt"   # 저장 창에서 확장자를 바꾼 경우
            target.write_bytes('문항,메모\n1,@SUM(A1)\n'.encode("utf-8"))
            request = _Request(window.spliter_view.page(), target.name)
            request.setDownloadDirectory(directory)
            request.finished = True
            request.status = QWebEngineDownloadRequest.DownloadState.DownloadCompleted
            window._on_spliter_download_finished(request, csv_file=True)
            data = target.read_bytes().decode("utf-8")
            leftovers = [p.name for p in Path(directory).iterdir() if p.name != target.name]
        self.assertEqual(data, "\ufeff문항,메모\n1,'@SUM(A1)\n")
        self.assertEqual(leftovers, [])  # 임시 파일이 남지 않는다

    def test_download_handler_is_connected_once_per_profile(self):
        window = self._window()
        profile = window.spliter_view.page().profile()
        store = {}
        profile.property.side_effect = store.get
        profile.setProperty.side_effect = store.__setitem__
        window._connect_spliter_downloads()
        window._connect_spliter_downloads()
        profile.downloadRequested.connect.assert_called_once()

    def test_failed_download_warns(self):
        window = self._window()
        request = _Request(window.spliter_view.page(), "x.json")
        request.finished = True
        request.status = QWebEngineDownloadRequest.DownloadState.DownloadInterrupted
        with patch("app.main_window.QMessageBox") as messages:
            window._on_spliter_download_finished(request)
        messages.warning.assert_called_once()
        window.statusBar().showMessage.assert_not_called()


if __name__ == "__main__":
    unittest.main()
