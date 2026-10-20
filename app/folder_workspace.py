"""Document folder registration, local-only drop, and five pinned folder paths.

Settings are additive and never included in a saved analysis transaction.
"""
from pathlib import Path
from shiboken6 import isValid
import os
from PySide6.QtCore import QObject, QEvent, Qt, QTimer
from PySide6.QtWidgets import (QApplication, QFrame, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QFileDialog, QWidget)

KEY = 'workspace/favoriteFoldersV1'
SELECTED = 'workspace/selectedFolderV1'


def canonical_folder(value):
    return os.path.normcase(str(Path(value).expanduser().resolve()))


def folder_from_mime(mime):
    if not mime.hasUrls() or len(mime.urls()) != 1:
        return None
    url = mime.urls()[0]
    if not url.isLocalFile():
        return None
    path = Path(url.toLocalFile())
    return canonical_folder(path) if path.is_dir() else None


class FolderWorkspace(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.settings = window.settings
        raw = self.settings.value(KEY, [])
        if isinstance(raw, str):
            raw = [raw]
        self.favorites = []
        for value in raw or []:
            if isinstance(value, str) and value:
                path = canonical_folder(value)
                if path not in self.favorites:
                    self.favorites.append(path)
        self.favorites = self.favorites[:5]
        self.selected = str(self.settings.value(SELECTED, '') or '')
        self.had_analysis = False
        self._analysis_ui_shown = False
        self.sync_timer = QTimer(self)
        self.sync_timer.setSingleShot(True)
        self.sync_timer.timeout.connect(self.sync_location)
        self.card = QFrame()
        self.card.setProperty('role', 'card')
        self.card.setObjectName('documentFolderCard')
        layout = QVBoxLayout(self.card)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)
        title = QLabel('문서 폴더')
        title.setProperty('role', 'title')
        layout.addWidget(title)
        self.drop_hint = QLabel('폴더를 여기에 끌어놓거나 아래에서 선택하세요.')
        self.drop_hint.setWordWrap(True)
        self.drop_hint.setMinimumHeight(50)
        self.drop_hint.setStyleSheet('QLabel { border: 1px dashed #699d96; border-radius: 6px; padding: 12px; }')
        layout.addWidget(self.drop_hint)
        self.path_label = QLabel()
        self.path_label.setWordWrap(True)
        self.path_label.setTextFormat(Qt.PlainText)
        self.path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.path_label)
        self.pick = QPushButton('폴더 선택')
        self.pick.clicked.connect(self.choose)
        layout.addWidget(self.pick)
        self.favorite_combo = QComboBox()
        self.favorite_combo.setAccessibleName('자주 쓰는 문서 폴더')
        self.favorite_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.favorite_combo.setMinimumContentsLength(12)
        self.favorite_combo.activated.connect(self.activate_favorite)
        layout.addWidget(self.favorite_combo)
        row = QHBoxLayout(); row.setSpacing(8)
        self.add = QPushButton('즐겨찾기 추가')
        self.remove = QPushButton('등록 해제')
        self.add.clicked.connect(self.add_favorite)
        self.remove.clicked.connect(self.remove_favorite)
        row.addWidget(self.add); row.addWidget(self.remove); layout.addLayout(row)
        self.analyze = QPushButton('이 폴더로 분석 준비')
        self.analyze.setProperty('role', 'primary')
        self.analyze.clicked.connect(self.prepare)
        layout.addWidget(self.analyze)
        self.note = QLabel('자주 쓰는 폴더는 최대 5개까지 저장합니다.')
        self.note.setWordWrap(True)
        self.note.setProperty('role', 'muted')
        layout.addWidget(self.note)
        self.start_layout = window.data_empty_state.layout()
        self.sidebar_layout = window.folder_sidebar_layout
        self.start_layout.insertWidget(0, self.card)
        # Keep the existing file selectors; replace only their old folder shortcut.
        if hasattr(window, 'btn_folder_batch'):
            window.btn_folder_batch.hide()
        self.overlay = QLabel('문서 폴더를 놓아 등록하세요', window.centralWidget())
        self.overlay.setAlignment(Qt.AlignCenter)
        self.overlay.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.overlay.setStyleSheet('background: #eaf5f1; color: #205f59; border: 3px dashed #287f79; border-radius: 12px; font-size: 20px;')
        self.overlay.hide()
        window.setAcceptDrops(True)
        window.data_empty_state.installEventFilter(self)
        # Do not attach Python filters to QApplication: QtWebEngine's internal
        # objects can re-enter Shiboken wrapper creation during native events.
        window.installEventFilter(self)
        for widget in window.findChildren(QWidget):
            widget.installEventFilter(self)
        self.refresh()
        self.sync_location()
        if window.exam is None and window._sidebar_user_choice is None:
            window._sidebar_user_choice = False
            window.splitter.setSizes([0, max(1, sum(window.splitter.sizes()))])

    def refresh(self):
        self.path_label.setText(self.selected or '선택된 폴더 없음')
        self.path_label.setToolTip(self.selected)
        self.favorite_combo.blockSignals(True)
        self.favorite_combo.clear()
        self.favorite_combo.addItem(f'자주 쓰는 폴더 ({len(self.favorites)}/5)', '')
        for path in self.favorites:
            # Include parent path to distinguish equally named document folders.
            label = f'{Path(path).name} — {Path(path).parent}'
            self.favorite_combo.addItem(label, path)
            self.favorite_combo.setItemData(self.favorite_combo.count()-1, path, Qt.ToolTipRole)
        index = self.favorite_combo.findData(self.selected)
        self.favorite_combo.setCurrentIndex(max(0, index))
        self.favorite_combo.blockSignals(False)
        self.remove.setEnabled(self.selected in self.favorites)
        self.add.setEnabled(bool(self.selected))
        self.analyze.setEnabled(bool(self.selected))

    def register(self, value):
        path = canonical_folder(value)
        if not Path(path).is_dir():
            self.note.setText('폴더를 찾을 수 없습니다. 이동했거나 연결이 끊겼다면 다시 선택하세요.')
            return False
        self.selected = path
        self.settings.setValue(SELECTED, path)
        self.settings.sync()
        self.refresh()
        self.note.setText('폴더가 등록되었습니다. 분석 준비에서 연결 자료를 확인하세요.')
        return True

    def choose(self):
        path = QFileDialog.getExistingDirectory(self.window, '문서 폴더 등록', self.selected if Path(self.selected).is_dir() else '')
        if path:
            self.register(path)

    def activate_favorite(self, index):
        path = self.favorite_combo.itemData(index)
        if path:
            if not self.register(path):
                # Retain missing saved path so it can be explicitly removed.
                self.selected = path
                self.refresh()

    def add_favorite(self):
        if not self.selected or not Path(self.selected).is_dir():
            self.note.setText('먼저 접근 가능한 폴더를 선택하세요.')
            return False
        if self.selected in self.favorites:
            self.note.setText('이미 등록된 폴더입니다.')
            return False
        if len(self.favorites) >= 5:
            self.note.setText('최대 5개까지 등록할 수 있습니다. 기존 항목을 해제한 뒤 추가하세요.')
            return False
        self.favorites.append(self.selected)
        self.persist()
        return True

    def remove_favorite(self):
        if self.selected in self.favorites:
            self.favorites.remove(self.selected)
            self.persist()
            self.note.setText('즐겨찾기 등록만 해제했습니다. 폴더와 파일은 변경하지 않았습니다.')

    def persist(self):
        self.settings.setValue(KEY, self.favorites)
        self.settings.sync()
        self.refresh()
        self.note.setText(f'자주 쓰는 폴더 {len(self.favorites)}개를 저장했습니다.')

    def prepare(self):
        controller = getattr(self.window, 'work_sessions', None)
        if controller is not None and (controller.busy or controller.result_only):
            self.note.setText('작업 복원 중이거나 결과 열람 상태입니다. 원본을 연결한 뒤 분석해 주세요.')
            return
        if not self.selected or not Path(self.selected).is_dir():
            self.note.setText('폴더를 찾을 수 없습니다. 다시 선택하세요.')
            return
        before = self.window.exam
        self.window._pick_folder_batch(self.selected)
        if self.window.exam is not before:
            self.after_analysis()
        self.sync_location()

    def sync_location(self):
        if not all(isValid(obj) for obj in (self.window, self.card, self.start_layout, self.sidebar_layout)):
            return
        analyzed = self.window.exam is not None and self.window.overall is not None
        workspace = getattr(self.window, "input_workspace", None)
        target = (workspace.folder_layout if workspace is not None and (analyzed or workspace.dialog.isVisible())
                  else self.sidebar_layout if analyzed else self.start_layout)
        if target.indexOf(self.card) < 0:
            self.start_layout.removeWidget(self.card)
            self.sidebar_layout.removeWidget(self.card)
            if workspace is not None:workspace.folder_layout.removeWidget(self.card)
            target.insertWidget(0 if workspace is not None else (1 if analyzed else 0), self.card)
            self.card.show()
        self.drop_hint.setVisible(not analyzed)
        self.had_analysis = analyzed

    def after_analysis(self):
        self.sync_location()
        if not self._analysis_ui_shown:
            self.window._sidebar_user_choice = False
            sizes = self.window.splitter.sizes()
            self.window.splitter.setSizes([0, max(1, sum(sizes))])
        self._analysis_ui_shown = True

    def eventFilter(self, watched, event):
        if watched is self.window.data_empty_state and event.type() in (QEvent.Show, QEvent.Hide):
            self.sync_timer.start(0)
        if event.type() not in (QEvent.DragEnter, QEvent.DragMove, QEvent.DragLeave, QEvent.Drop):
            return False
        workspace = getattr(self.window, 'input_workspace', None)
        hosts = (self.window, workspace.dialog) if workspace is not None else (self.window,)
        if not hasattr(watched, 'window') or watched.window() not in hosts:
            return False
        if event.type() == QEvent.DragLeave:
            self.overlay.hide()
            return False
        path = folder_from_mime(event.mimeData())
        if path is None:
            self.overlay.hide()
            return False  # Existing file drop handlers retain their behavior.
        event.acceptProposedAction()
        if event.type() == QEvent.Drop:
            self.overlay.hide()
            self.register(path)
            if self.window.exam is not None:
                if workspace is not None:workspace.open('folder')
                else:self.window._show_sidebar()
        elif watched.window() is self.window:
            self.overlay.setGeometry(self.window.centralWidget().rect().adjusted(12, 12, -12, -12))
            self.overlay.show(); self.overlay.raise_()
        return True


def install_folder_workspace(window):
    window.folder_workspace = FolderWorkspace(window)
