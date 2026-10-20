"""Reuse every original input control in a dedicated, nonmodal workspace."""
from PySide6.QtCore import QObject, Qt
from PySide6.QtWidgets import (QDialog,QWidget,QVBoxLayout,QHBoxLayout,QStackedWidget,
    QPushButton,QLabel,QFrame,QSizePolicy)


class InputWorkspace(QObject):
    def __init__(self,window):
        super().__init__(window);self.window=window
        self.dialog=QDialog(window);self.dialog.setWindowTitle('자료·분석 설정');self.dialog.resize(1000,760)
        self.dialog.setModal(False)
        self.dialog.setObjectName('inputWorkspaceDialog')
        self.dialog.setStyleSheet('QDialog#inputWorkspaceDialog QWidget[workspaceContainer="true"] { background: transparent; } QDialog#inputWorkspaceDialog QLabel { background: transparent; font-weight: 400; } QDialog#inputWorkspaceDialog QLabel[role="title"] { font-weight: 600; }')
        layout=QVBoxLayout(self.dialog);layout.setContentsMargins(18,18,18,18);layout.setSpacing(12)
        title=QLabel('자료·분석 설정');title.setProperty('role','title');layout.addWidget(title)
        note=QLabel('폴더에서 회차별 분석을 준비하거나, 개별 파일과 세부 설정을 직접 지정하세요.');note.setWordWrap(True);layout.addWidget(note)
        nav=QHBoxLayout();layout.addLayout(nav)
        self.folder_button=QPushButton('폴더·회차별 분석 준비');self.individual_button=QPushButton('개별 파일·세부 설정')
        nav.addWidget(self.folder_button);nav.addWidget(self.individual_button);nav.addStretch()
        self.pages=QStackedWidget();layout.addWidget(self.pages,1)
        self.folder_page=QWidget();self.folder_layout=QVBoxLayout(self.folder_page);self.folder_layout.setContentsMargins(0,0,0,0)
        self.folder_layout.addStretch();self.pages.addWidget(self.folder_page)
        self.individual_page=QWidget();individual=QVBoxLayout(self.individual_page);individual.setContentsMargins(0,0,0,0)
        description=QLabel('<p style="line-height:145%">입력 변경은 바로 유지됩니다. 닫아도 입력은 남으며, 분석 결과는 분석 실행 후 갱신됩니다.<br>CSV·추천 근거 Excel 내보내기는 현재 분석 결과를 사용합니다.</p>');description.setWordWrap(True);individual.addWidget(description)
        self.placeholder=QWidget();self.placeholder.setObjectName('inputCompatibilitySlot');self.placeholder.setFixedWidth(0)
        original=window.splitter.replaceWidget(0,self.placeholder)
        if original is not window.input_panel:raise RuntimeError('Input panel location changed')
        self.placeholder.hide()
        individual.addWidget(original,1);original.show();self.pages.addWidget(self.individual_page)
        self._arrange_original_panels()
        # Remove only structural widget fills; themed cards and actual inputs keep
        # their existing backgrounds in both light and dark themes.
        for widget in [original, *original.findChildren(QWidget)]:
            if type(widget) is QWidget or type(widget).__name__ in ('FileSelector', 'StepperSpinBox') or widget.property('role') == 'inputrow':
                widget.setProperty('workspaceContainer', True)
                widget.style().unpolish(widget)
                widget.style().polish(widget)
        close=QPushButton('닫기 · 입력 유지');close.clicked.connect(self.dialog.close)
        footer=QHBoxLayout();footer.addStretch();footer.addWidget(close);layout.addLayout(footer)
        self.folder_button.clicked.connect(lambda:self.open('folder'))
        self.individual_button.clicked.connect(lambda:self.open('individual'))
        self.dialog.finished.connect(lambda *_:window.folder_workspace.sync_location())
        window.btn_sidebar.setText('자료·분석 설정');window.btn_sidebar.setProperty('iconLabel','자료·분석 설정')
        window.btn_sidebar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        window.btn_sidebar.setToolTip('폴더·회차 준비와 모든 개별 입력 설정 열기')
        window.splitter.setSizes([0,max(1,window.width())])
        self.dialog.setAcceptDrops(True);self.dialog.installEventFilter(window.folder_workspace)

    def _arrange_original_panels(self):
        root=self.window.folder_sidebar_layout
        panels=[root.itemAt(i).widget() for i in range(root.count())
                if root.itemAt(i).widget() is not None and hasattr(root.itemAt(i).widget(),'body_widget')]
        columns=QWidget();columns.setObjectName('individualInputColumns');horizontal=QHBoxLayout(columns)
        horizontal.setContentsMargins(0,0,0,0);horizontal.setSpacing(16)
        left=QVBoxLayout();right=QVBoxLayout();left.setSpacing(12);right.setSpacing(12)
        horizontal.addLayout(left,1);horizontal.addLayout(right,1)
        # Input files, performance and report on the left; weights/cuts on the right.
        for panel in panels:
            root.removeWidget(panel)
            name=panel.toggle_button.text()
            target=right if name.startswith(('반영비율','분할점수')) else left
            target.addWidget(panel)
        left.addStretch();right.addStretch();root.insertWidget(1,columns)
        self.original_panels=panels;self.columns=columns

    def open(self,section='folder'):
        self.pages.setCurrentWidget(self.individual_page if section=='individual' else self.folder_page)
        self.dialog.show();self.dialog.raise_();self.dialog.activateWindow()
        self.window.folder_workspace.sync_location()


def install_input_workspace(window):
    window.input_workspace=InputWorkspace(window)
