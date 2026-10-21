from tests.runtime_isolation import ensure_isolated
ensure_isolated()
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import QSettings, Qt, QMimeData, QUrl, QPoint, QPointF
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QApplication
from app.main_window import MainWindow
from app.folder_workspace import KEY, SELECTED, canonical_folder, folder_from_mime


class FolderWorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='folder-workspace-')).resolve()
        self.settings = QSettings(str(self.root/'settings.ini'), QSettings.IniFormat)
        self.settings.setValue('existing/keep', 'untouched')
        self.patches = [patch('app.main_window.QSettings', return_value=self.settings),
                        patch('app.main_window.QWebEngineView', None),
                        patch.object(MainWindow, '_ai_material_root_dir', lambda w: self.root/'state')]
        for p in self.patches:
            p.start(); self.addCleanup(p.stop)
        self.w = MainWindow(); self.w.resize(1280,800); self.w.show()
        self.addCleanup(self.w.close)
        self.c = self.w.folder_workspace

    def directory(self, name):
        p=self.root/name;p.mkdir(parents=True,exist_ok=True);return p

    def test_five_distinct_paths_dedupe_missing_and_restart(self):
        folders=[self.directory(f'{i}/same') for i in range(6)]
        for p in folders[:5]:
            self.assertTrue(self.c.register(p));self.assertTrue(self.c.add_favorite())
        self.assertFalse(self.c.add_favorite())
        self.c.register(folders[5]);self.assertFalse(self.c.add_favorite())
        self.c.register(folders[1]);self.c.remove_favorite()
        self.c.register(folders[5]);self.assertTrue(self.c.add_favorite())
        self.assertEqual('untouched',self.settings.value('existing/keep'))
        fresh=MainWindow();self.addCleanup(fresh.close)
        self.assertEqual(self.c.favorites,fresh.folder_workspace.favorites)
        self.assertEqual(canonical_folder(folders[5]),fresh.folder_workspace.selected)
        self.assertEqual(6,fresh.folder_workspace.favorite_combo.count())
        self.assertFalse(self.c.register(self.root/'absent'))

    def test_real_qt_drop_registers_without_analysis_and_rejects_files(self):
        folder=self.directory('drop');mime=QMimeData();mime.setUrls([QUrl.fromLocalFile(str(folder))])
        enter=QDragEnterEvent(QPoint(100,100),Qt.CopyAction,mime,Qt.LeftButton,Qt.NoModifier)
        drop=QDropEvent(QPointF(100,100),Qt.CopyAction,mime,Qt.LeftButton,Qt.NoModifier)
        with patch.object(self.w,'_pick_folder_batch') as analyze:
            self.app.sendEvent(self.w,enter);self.app.sendEvent(self.w,drop)
            self.assertTrue(enter.isAccepted());self.assertTrue(drop.isAccepted())
            self.assertEqual(canonical_folder(folder),self.c.selected);analyze.assert_not_called()
            self.c.prepare();analyze.assert_called_once_with(canonical_folder(folder))
        file=self.root/'file.txt';file.write_text('synthetic')
        mime.setUrls([QUrl.fromLocalFile(str(file))]);self.assertIsNone(folder_from_mime(mime))
        mime.setUrls([QUrl('https://example.invalid/folder')]);self.assertIsNone(folder_from_mime(mime))
        mime.setUrls([QUrl.fromLocalFile(str(folder)),QUrl.fromLocalFile(str(folder))]);self.assertIsNone(folder_from_mime(mime))

    def test_same_card_moves_to_settings_once_without_losing_selection(self):
        folder=self.directory('registered');self.c.register(folder);self.c.add_favorite()
        card=self.c.card
        self.assertGreaterEqual(self.c.start_layout.indexOf(card),0)
        self.w.exam=object();self.w.overall=object();self.c.after_analysis()
        self.assertGreaterEqual(self.w.input_workspace.folder_layout.indexOf(card),0)
        self.assertEqual(0,self.w.splitter.sizes()[0])
        self.w._show_sidebar();self.c.sync_location()
        self.assertEqual(self.w.splitter.sizes()[0],0)
        self.assertTrue(self.w.input_workspace.dialog.isVisible())
        self.assertEqual(canonical_folder(folder),self.c.selected)
        self.w.exam=None;self.w.overall=None;self.w.input_workspace.dialog.close();self.c.sync_location()
        self.assertGreaterEqual(self.c.start_layout.indexOf(card),0)
        self.assertEqual([canonical_folder(folder)],self.c.favorites)

if __name__=='__main__': unittest.main()
