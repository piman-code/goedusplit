"""User-sized native table columns, with explicit fit/reset actions.

Double-clicking a column boundary fits that column to its contents. Until the user sizes a
column, a table spreads its columns over the visible width ("화면에 맞춤"), unless shrinking
would cut a header or short cell; then it keeps its own widths and scrolls. The ``fillColumns``
property forces this on (True: always fill, for wrapped text) or off (False: the per-student
results table).
"""
from PySide6.QtCore import QObject, QEvent, QTimer, Qt, Slot, QPoint
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QTableWidget, QHeaderView, QMenu, QToolButton, QTabWidget, QHBoxLayout, QSplitter


def _menu_button_label(button):
    # The style's own menu arrow was painted over the last letter; draw the arrow as text instead.
    button.setText("열 너비 ▾");button.setPopupMode(QToolButton.InstantPopup)
    button.setStyleSheet("QToolButton::menu-indicator { image: none; width: 0px; }")
    button.setToolTip("열 너비: 화면에 맞춤 · 모든 열 내용에 맞춤 · 초기 너비로 되돌리기")


class TableColumnControls(QObject):
    def __init__(self, table):
        super().__init__(table)
        self.table=table; self.schema=None; self.defaults=[]; self.manual={}; self.base=[]
        # True only after the teacher sized a column (drag, double-click, content fit, saved work).
        self.user_sized=False
        self.busy=False; self.pending=False; self.dragging=False
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.timeout.connect(self.apply)
        header=table.horizontalHeader()
        header.installEventFilter(self); header.viewport().installEventFilter(self)
        table.installEventFilter(self)
        header.sectionResized.connect(self.resized)
        # QTableView already connects this to resizeColumnToContents; ours runs after it, caps
        # wrapped text and keeps the result as the user's width.
        header.sectionHandleDoubleClicked.connect(self.fit_column)
        for signal in (table.model().modelReset,table.model().columnsInserted,table.model().columnsRemoved):
            signal.connect(self.schedule)
        header.setToolTip('열 경계를 끌어 너비 조절 · 경계 더블클릭: 내용에 맞춤 · 우클릭: 화면에 맞춤 / 내용에 맞춤 / 초기 너비')
        header.setContextMenuPolicy(Qt.CustomContextMenu)
        header.customContextMenuRequested.connect(self.menu)
        self.fit_action=QAction('화면에 맞춤',header);self.fit_action.triggered.connect(self.fit)
        self.contents_action=QAction('모든 열 내용에 맞춤',header);self.contents_action.triggered.connect(self.fit_contents)
        self.reset_action=QAction('초기 너비로 되돌리기',header);self.reset_action.triggered.connect(self.reset)
        self.add_visible_menu()
        self.schedule()

    def add_visible_menu(self):
        table=self.table;parent=table.parentWidget()
        tabs=parent.parentWidget() if parent is not None else None
        if isinstance(tabs,QTabWidget):
            if getattr(tabs,"_column_menu_button",None) is not None:return
            button=QToolButton(tabs);_menu_button_label(button)
            menu=QMenu(button);button.setMenu(menu)
            def populate():
                menu.clear();current=tabs.currentWidget()
                if isinstance(current,QTableWidget):
                    control=enable_table_columns(current)
                    menu.addAction(control.fit_action);menu.addAction(control.contents_action);menu.addAction(control.reset_action)
            menu.aboutToShow.connect(populate)
            tabs.setCornerWidget(button,Qt.TopRightCorner);tabs._column_menu_button=button
        elif parent is not None and getattr(parent,"body",None) is table and hasattr(parent,"toggle"):
            button=QToolButton(parent);_menu_button_label(button)
            menu=QMenu(button);menu.addAction(self.fit_action);menu.addAction(self.contents_action);menu.addAction(self.reset_action);button.setMenu(menu)
            layout=parent.layout();layout.removeWidget(parent.toggle)
            row=QHBoxLayout();row.setContentsMargins(0,0,0,0);row.addWidget(parent.toggle);row.addStretch();row.addWidget(button)
            layout.insertLayout(0,row);self.menu_button=button

    @Slot()
    def schedule(self,*_):
        if not hasattr(self,'pending'):return
        if not self.pending:
            self.pending=True;self.timer.start(0)

    @Slot()
    def apply(self):
        self.pending=False
        if self.busy or self.table.columnCount()==0:return
        table=self.table;header=table.horizontalHeader()
        schema=tuple(table.horizontalHeaderItem(c).text() if table.horizontalHeaderItem(c) else str(c)
                     for c in range(table.columnCount()))
        self.busy=True
        try:
            if schema!=self.schema:
                self.schema=schema;self.defaults=[table.columnWidth(c) for c in range(table.columnCount())];self.manual={}
                self.user_sized=False
                # The widths the app chose; filling scales these, never its own earlier result.
                self.base=list(self.defaults)
            if not self.manual:
                self.defaults=[table.columnWidth(c) for c in range(table.columnCount())]
            header.setStretchLastSection(False)
            header.setSectionResizeMode(QHeaderView.Interactive)
            if self.manual:
                for c,width in self.manual.items():
                    if c<table.columnCount():table.setColumnWidth(c,width)
            elif self.fills():self.fill_width()
            else:self.keep_headers_readable()
            self.sync_frozen()
        finally:self.busy=False

    def fills(self):
        forced=self.table.property('fillColumns')
        return True if forced is None else bool(forced)

    def keep_headers_readable(self):
        """Tables that keep their own widths still show every header in full (zoom changes fonts)."""
        table=self.table;metrics=table.horizontalHeader().fontMetrics()
        for c in range(table.columnCount()):
            item=table.horizontalHeaderItem(c)
            need=metrics.horizontalAdvance(item.text().replace('\n',' ') if item else str(c))+12
            if table.columnWidth(c)<need:table.setColumnWidth(c,need)

    def readable_width(self,column):
        table=self.table
        return max(table.horizontalHeader().sectionSizeHint(column),min(table.sizeHintForColumn(column),160))

    def fill_width(self):
        table=self.table;count=table.columnCount()
        base=[max(1,w) for w in self.base[:count]]+[max(1,table.columnWidth(c)) for c in range(len(self.base),count)]
        available=table.viewport().width();total=sum(base)
        if total<=0:return
        # Every column first gets room for its header and short cells; the rest is shared by the
        # app's own proportions, so widening never leaves a narrow column showing "10…".
        need=[max(28,self.readable_width(c)) for c in range(count)]
        if available<=count*28 and not self.table.property('fillColumns'):
            widths=[max(base[c],need[c]) for c in range(count)]  # no room to fit at all: scroll
        elif sum(need)<=available:
            spare=available-sum(need)
            widths=[need[c]+int(spare*base[c]/total) for c in range(count)]
            widths[-1]+=available-sum(widths)
        elif self.table.property('fillColumns'):
            widths=[max(28,int(available*width/total)) for width in base]  # wrapped text: always fit
            widths[-1]+=available-sum(widths)
        else:
            # Too many columns to fit: scroll, but never narrower than the text ("…" or blank cells).
            widths=[max(base[c],need[c]) for c in range(count)]
        for c,width in enumerate(widths):table.setColumnWidth(c,max(28,width))

    def content_width(self,column):
        table=self.table
        width=max(table.sizeHintForColumn(column),table.horizontalHeader().sectionSizeHint(column))+12
        return max(40,min(width,int(table.viewport().width()*0.6)))

    @Slot(int)
    def fit_column(self,column):
        if 0<=column<self.table.columnCount():self.remember_width(column,self.content_width(column))

    @Slot()
    def fit_contents(self):
        self.apply()
        self.manual={c:self.content_width(c) for c in range(self.table.columnCount())};self.user_sized=True
        self.apply()

    def sync_frozen(self):
        table=self.table;frozen=getattr(table,'frozenView',None)
        if frozen is None:return
        count=min(table.frozenCount,table.columnCount())
        table.frozenWidths=[table.columnWidth(c) for c in range(count)]
        frozen.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        for c,width in enumerate(table.frozenWidths):frozen.setColumnWidth(c,width)
        table._sync_frozen_geometry()

    @Slot(int,int,int)
    def resized(self,column,_old,width):
        if self.busy:return
        if self.dragging:
            self.manual[column]=width;self.user_sized=True
            self.busy=True
            try:self.sync_frozen()
            finally:self.busy=False
        else:
            # A width the app set (render, zoom) becomes the new base for filling.
            if not self.manual and column<len(self.base):self.base[column]=width
            self.schedule()

    def adopt_current_widths(self):
        """Widths restored from saved work that the teacher had sized."""
        table=self.table;self.user_sized=True
        self.schema=tuple(table.horizontalHeaderItem(c).text() if table.horizontalHeaderItem(c) else str(c)
                          for c in range(table.columnCount()))
        self.manual={c:table.columnWidth(c) for c in range(table.columnCount())}
        self.apply()

    def refit(self):
        """Back to the app's widths (fitted to the screen where the table fills), as if never sized."""
        self.manual={};self.user_sized=False
        table=self.table
        if not self.fills() and table.property("baseColumnWidths"):
            window=table.window()
            px=getattr(window,"_px",None)
            for c,width in dict(table.property("baseColumnWidths")).items():
                if int(c)<table.columnCount():table.setColumnWidth(int(c),px(float(width)) if px else int(width))
        self.apply()

    def remember_width(self,column,width):
        self.manual[column]=width;self.user_sized=True
        self.table.setColumnWidth(column,width)
        self.schedule()

    @Slot()
    def fit(self):
        if self.fills():return self.refit()
        self.apply();table=self.table
        widths=[max(1,table.columnWidth(c)) for c in range(table.columnCount())]
        available=max(1,table.viewport().width());total=max(1,sum(widths))
        self.manual={c:max(28,int(available*width/total)) for c,width in enumerate(widths)}
        self.apply()

    @Slot()
    def reset(self):
        # A filling table's initial width is "fill the table", not the widths at fill time.
        if self.fills():return self.refit()
        self.manual={c:width for c,width in enumerate(self.defaults)};self.user_sized=False
        self.apply()

    @Slot(QPoint)
    def menu(self,pos):
        menu=QMenu(self.table);menu.addAction(self.fit_action);menu.addAction(self.contents_action);menu.addAction(self.reset_action)
        menu.exec(self.table.horizontalHeader().mapToGlobal(pos))

    def eventFilter(self,obj,event):
        if not hasattr(self,'table'):return False
        if event.type()==QEvent.MouseButtonPress and event.button()==Qt.LeftButton:self.dragging=True
        elif event.type()==QEvent.MouseButtonRelease:self.dragging=False
        elif obj is self.table and event.type() in (QEvent.Show,QEvent.Resize,QEvent.LayoutRequest):self.schedule()
        return False


def column_menu_button(table,parent):
    """A '열 너비 ▾' menu for a table placed where add_visible_menu cannot find a header row."""
    control=enable_table_columns(table)
    button=QToolButton(parent);_menu_button_label(button)
    menu=QMenu(button);menu.addAction(control.fit_action);menu.addAction(control.contents_action)
    menu.addAction(control.reset_action);button.setMenu(menu)
    return button


def enable_table_columns(table):
    control=getattr(table,'_column_controls',None)
    if control is None:
        control=TableColumnControls(table);table._column_controls=control
    control.schedule()
    return control


class _TableControlsInstaller(QObject):
    def __init__(self,window):
        super().__init__(window);self.window=window
        # Never filter all QApplication events: WebEngine owns non-widget Qt
        # objects whose wrapper creation can re-enter an application filter.
        window.installEventFilter(self)
        self.scan_timer=QTimer(self)
        self.scan_timer.setInterval(500)
        self.scan_timer.timeout.connect(self.scan_tables)
        self.scan_timer.start()
        self.scan_tables()
        from .result_layout import _FoldMinimumGuard
        self.chart_guards=[]
        for split in window.findChildren(QSplitter):
            if split.orientation()!=Qt.Vertical:continue
            split.setChildrenCollapsible(False);split.setHandleWidth(8)
            for index in range(1,split.count()):split.handle(index).setToolTip('끌어서 그래프와 표 높이를 조절합니다.')
            for index in range(split.count()):
                section=split.widget(index);body=getattr(section,'body',None)
                if body is None or not hasattr(section,'toggle'):continue
                if str(getattr(section,'_key','')).startswith('ui/fold/data.'):continue
                charts=[child for child in [body]+body.findChildren(QObject) if type(child).__name__=='CanvasHolder']
                if charts:
                    minimum=220 if str(getattr(section,'_key',''))=='ui/fold/perform.charts' else 160
                    body.setMinimumHeight(max(body.minimumHeight(),minimum))
                    self.chart_guards.append(_FoldMinimumGuard(section))
        refs=getattr(window,'_result_layout_refs',{})
        splitter=refs.get('data_splitter')
        if splitter is not None:
            splitter.setChildrenCollapsible(False);splitter.setHandleWidth(8)
            splitter.handle(1).setToolTip('끌어서 그래프와 표 높이를 조절합니다. 제목 버튼으로 접고 펼칠 수 있습니다.')
            splitter.splitterMoved.connect(lambda *_: [guard.sync() for guard in refs.get('fold_guards',())])

    @Slot()
    def scan_tables(self):
        if not hasattr(self,'window'):return
        # topLevelWidgets returns QWidget wrappers only. This also covers
        # modal editors created after startup without watching Qt internals.
        roots=[self.window]+QApplication.topLevelWidgets()
        seen=set()
        for root in roots:
            for table in root.findChildren(QTableWidget):
                if id(table) not in seen:
                    seen.add(id(table))
                    if getattr(table,'_column_controls',None) is None:
                        enable_table_columns(table)

    def eventFilter(self,obj,event):
        if event.type()==QEvent.Show and hasattr(self,'scan_timer'):
            self.scan_timer.start()
        elif event.type()==QEvent.Close and hasattr(self,'scan_timer'):
            self.scan_timer.stop()
        return False


def install_table_controls(window):
    if not hasattr(window,'_table_controls_installer'):
        window._table_controls_installer=_TableControlsInstaller(window)
    return window._table_controls_installer
