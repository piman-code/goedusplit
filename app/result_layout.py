"""Compact native result layout with the original widgets and behavior intact.

Existing saved fold preferences take precedence over the initial layout defaults.
"""
from PySide6.QtCore import QEvent, QObject, QSignalBlocker
from PySide6.QtWidgets import QBoxLayout, QComboBox, QPushButton, QSizePolicy, QSplitter


def _layout_containing(layout, widget):
    """Find the existing row without depending on its position in a parent."""
    for index in range(layout.count()):
        item = layout.itemAt(index)
        if item.widget() is widget:
            return layout
        child = item.layout()
        if child is not None:
            found = _layout_containing(child, widget)
            if found is not None:
                return found
    return None


def _initial_fold(section, opened):
    # Respect existing preferences; only choose a default for a new setting.
    if section._settings is not None and section._key and section._settings.contains(section._key):
        return
    blocker = QSignalBlocker(section.toggle)
    section.toggle.setChecked(opened)
    section._apply(opened, remember=False)
    del blocker


class _FoldMinimumGuard(QObject):
    """Propagate a visible body's minimum to its splitter item without overrides."""

    def __init__(self, section):
        super().__init__(section)
        self.section = section
        self._updating = False
        section.body.installEventFilter(self)
        section.toggle.installEventFilter(self)
        section.installEventFilter(self)
        section.toggle.toggled.connect(self.sync)
        self.sync()

    def sync(self, *_args):
        if self._updating:
            return
        self._updating = True
        try:
            section = self.section
            layout = section.layout()
            margins = layout.contentsMargins()
            minimum = 0
            if section.is_open():
                minimum = (section.body.minimumHeight() + section.toggle.sizeHint().height()
                           + max(0, layout.spacing()) + margins.top() + margins.bottom())
            if section.minimumHeight() != minimum:
                section.setMinimumHeight(minimum)
        finally:
            self._updating = False

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.LayoutRequest, QEvent.Resize, QEvent.FontChange, QEvent.StyleChange):
            self.sync()
        return False


class _TableViewportGuard(QObject):
    """Reserve readable rows in addition to headers and the horizontal scrollbar."""

    def __init__(self, table, fold_guard):
        super().__init__(table)
        self.table = table
        self.fold_guard = fold_guard
        self._updating = False
        for widget in (table, table.horizontalHeader(), table.horizontalScrollBar(), table.viewport()):
            widget.installEventFilter(self)
        self.sync()

    def sync(self):
        if self._updating:
            return
        self._updating = True
        try:
            table = self.table
            header = table.horizontalHeader()
            scroll = table.horizontalScrollBar()
            # Reserve the scrollbar even before the first populated table layout.
            chrome = (max(header.height(), header.sizeHint().height())
                      + max(scroll.height(), scroll.sizeHint().height())
                      + 2 * table.frameWidth())
            minimum = max(140, 104 + chrome)
            if table.minimumHeight() != minimum:
                table.setMinimumHeight(minimum)
            self.fold_guard.sync()
        finally:
            self._updating = False

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.LayoutRequest, QEvent.Resize, QEvent.FontChange,
                            QEvent.StyleChange, QEvent.Show):
            self.sync()
        return False


class _ChartViewportGuard(QObject):
    """Size the chart from its canvas and visible chrome, not a zoom multiplier."""

    def __init__(self, window, fold_guard):
        super().__init__(window.score_chart_tabs)
        self.window = window
        self.tabs = window.score_chart_tabs
        self.fold_guard = fold_guard
        self._updating = False
        for widget in (self.tabs, self.tabs.tabBar(), window.lbl_normal_note):
            widget.installEventFilter(self)
        self.tabs.currentChanged.connect(self.sync)
        self.sync()

    def sync(self, *_args):
        if self._updating:
            return
        self._updating = True
        try:
            minimum = 176 + self.tabs.tabBar().sizeHint().height() + 4
            if self.tabs.currentIndex() == 1:
                note = self.window.lbl_normal_note
                width = max(1, self.tabs.width() - 8)
                note_height = note.heightForWidth(width)
                if note_height < 0:
                    note_height = note.sizeHint().height()
                layout = self.tabs.currentWidget().layout()
                margins = layout.contentsMargins()
                minimum += note_height + max(0, layout.spacing()) + margins.top() + margins.bottom()
            if self.tabs.minimumHeight() != minimum:
                self.tabs.setMinimumHeight(minimum)
            self.fold_guard.sync()
            self.fold_guard.section.updateGeometry()
            splitter = self.fold_guard.section.parentWidget()
            if isinstance(splitter, QSplitter):
                splitter.refresh()
        finally:
            self._updating = False

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.LayoutRequest, QEvent.Resize, QEvent.FontChange,
                            QEvent.StyleChange, QEvent.Show):
            self.sync()
        return False


def apply_layout(window):
    """Rearrange existing widgets once; return references for behavioral QA."""
    if getattr(window, "_result_layout_refs", None) is not None:
        return window._result_layout_refs

    chart_fold = window.score_chart_tabs.parentWidget()
    table_fold = window.table_data.parentWidget()
    note_fold = window.lbl_data_note.parentWidget()
    data_splitter = chart_fold.parentWidget()
    if not isinstance(data_splitter, QSplitter) or table_fold.parentWidget() is not data_splitter:
        raise ValueError("Expected the original chart/table splitter")

    # Use the existing title/value labels and the same grid/card objects.
    for card in window._kpis:
        box = card.layout()
        box.setDirection(QBoxLayout.LeftToRight)
        box.setContentsMargins(10, 4, 10, 4)
        box.setSpacing(8)
        box.setStretch(0, 1)
        card.value_label.setStyleSheet("font-size: 16px; font-weight: 700;")
        card.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
    window.kpi_grid.setSpacing(6)
    summary_fold = window.kpi_n.parentWidget().parentWidget()
    summary_fold.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)

    search_row = _layout_containing(window.data_results.layout(), window.le_search)
    filter_row = _layout_containing(window.data_results.layout(), window.combo_filter_level)
    if search_row is None or filter_row is None:
        raise ValueError("Expected the original search/filter rows")
    moved = []
    for index in range(filter_row.count()):
        widget = filter_row.itemAt(index).widget()
        if isinstance(widget, QPushButton) and (
                widget is window.btn_clear_search or widget.text() in {"포트폴리오 저장", "모니터링 탭"}):
            moved.append(widget)
    if len(moved) != 3:
        raise ValueError("Expected three original search actions")
    for widget in moved:
        filter_row.removeWidget(widget)
        search_row.addWidget(widget)
    filter_row.setSpacing(6)
    window.lbl_search_status.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)

    # At 1280x800/120%, the original standalone collapsed note header consumes
    # the 32px needed by the two splitter minima. Keep its original toggle and
    # signal, but put that control in the chart-options row's trailing space.
    chart_options = _layout_containing(window.data_results.layout(), window.chk_chart_student_labels)
    if chart_options is None:
        raise ValueError("Expected the original chart-options row")
    note_fold.layout().removeWidget(note_fold.toggle)
    chart_options.addWidget(note_fold.toggle)

    # Keep the chart's native plotting space: shortening its canvas clips axes.
    # Summary remains available through the original fold rather than consuming
    # the graph/table workspace at startup.
    window.score_chart_tabs.setMinimumHeight(220)
    window.table_data.setMinimumHeight(140)
    window.tab_data.layout().setContentsMargins(4, 4, 4, 4)
    window.tab_data.layout().setSpacing(1)
    window.data_results.layout().setSpacing(1)
    data_splitter.setChildrenCollapsible(False)
    data_splitter.setStretchFactor(0, 2)
    data_splitter.setStretchFactor(1, 3)
    _initial_fold(note_fold, False)
    _initial_fold(summary_fold, False)
    _initial_fold(chart_fold, True)
    _initial_fold(table_fold, True)
    fold_guards = tuple(_FoldMinimumGuard(section) for section in (chart_fold, table_fold))
    table_viewport_guard = _TableViewportGuard(window.table_data, fold_guards[1])
    chart_viewport_guard = _ChartViewportGuard(window, fold_guards[0])
    data_splitter.setSizes([260, 260])

    # Older versions did not persist sidebar visibility. Preserve any explicit
    # runtime choice and use an open input panel only as the new default.
    if window._sidebar_user_choice is None:
        window._sidebar_user_choice = True
    window._sidebar_hidden_for_calculator = False
    window.input_panel.setMinimumWidth(280)
    sizes = window.splitter.sizes()
    total = max(sum(sizes), window.width() - 28)
    if window._sidebar_user_choice:
        window.splitter.setSizes([300, max(1, total - 300)])
    else:
        window.splitter.setSizes([0, total])

    mode = QComboBox(window.header_bar)
    mode.setObjectName("resultDisplayMode")
    mode.setAccessibleName("화면 배치")
    mode.addItem("노트북", "laptop")
    mode.addItem("모니터", "monitor")
    saved_mode = str(window.settings.value("ui/result_layout_mode", "laptop"))
    mode.setCurrentIndex(max(0, mode.findData(saved_mode)))
    mode.setToolTip("기능과 창 크기는 유지하고 입력 패널 너비를 조절합니다.")
    header = window.header_bar.layout()
    header.insertWidget(3, mode)

    def set_mode(_index):
        # No resize(), fold toggling, table rebuilding, or filter reset here.
        current = window.splitter.sizes()
        if current and current[0] > 4:
            width = 320 if mode.currentData() == "monitor" else 300
            window.splitter.setSizes([width, max(1, sum(current) - width)])
        window._apply_responsive_tab_labels()
        window._apply_header_compactness()

    set_mode(mode.currentIndex())
    mode.currentIndexChanged.connect(set_mode)
    mode.currentIndexChanged.connect(
        lambda _index: window.settings.setValue("ui/result_layout_mode", mode.currentData()))
    refs = {
        "mode": mode,
        "set_mode": set_mode,
        "data_splitter": data_splitter,
        "chart_fold": chart_fold,
        "table_fold": table_fold,
        "note_fold": note_fold,
        "summary_fold": summary_fold,
        "search_row": search_row,
        "filter_row": filter_row,
        "chart_options": chart_options,
        "moved_buttons": tuple(moved),
        "table": window.table_data,
        "chart_tabs": window.score_chart_tabs,
        "input_panel": window.input_panel,
        "kpis": tuple(window._kpis),
        "fold_guards": fold_guards,
        "table_viewport_guard": table_viewport_guard,
        "chart_viewport_guard": chart_viewport_guard,
    }
    window._result_layout_refs = refs
    return refs

