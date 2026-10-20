"""Student-focused portfolio presentation over the existing snapshot controls."""
from __future__ import annotations

import math
from numbers import Real, Integral
from PySide6.QtCore import Qt, QPointF, QRectF, QSignalBlocker, QSize, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPalette
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QSplitter, QScrollArea, QTableWidget, QTableWidgetItem,
    QHeaderView, QStackedWidget, QPushButton, QSizePolicy, QToolTip, QLineEdit, QComboBox, QCheckBox, QTabWidget)
from .portfolio_timeline import build_timeline


def detail_cell_text(value, header):
    """Presentation only: keep identifiers integral and stored measurements exact."""
    if value is None:
        return "자료 없음"
    if isinstance(value, Real) and not isinstance(value, bool):
        if not math.isfinite(value):
            return "자료 없음"
        if '%' in header or '비율' in header or '정답률' in header:
            return f"{value:.2f}"
        if not isinstance(value, Integral):
            return f"{value:.2f}"
    return str(value)


class PortfolioDetailTable(QTableWidget):
    """Fit six response percentages without letting raw float strings set widths."""
    def configure_columns(self, key):
        from .table_controls import enable_table_columns
        control = enable_table_columns(self)
        self._choice_layout = key == 'choice' and self.columnCount() == 10
        header = self.horizontalHeader()
        if self._choice_layout:
            self.setStyleSheet('QTableWidget::item { padding: 4px 2px; } QHeaderView::section { padding: 8px 2px; }')
            header.setStretchLastSection(False)
            header.setMinimumSectionSize(24)
            header.setSectionResizeMode(QHeaderView.Stretch)
            for column in range(self.columnCount()):
                item = self.horizontalHeaderItem(column)
                original = item.text()
                item.setToolTip(original)
                item.setText(original.replace('학생 응답', '학생\n응답').replace('(%)', '\n(%)'))
            self._compact_identity_columns()
        else:
            self.setStyleSheet('')
            header.setMinimumSectionSize(26)
            header.setSectionResizeMode(QHeaderView.ResizeToContents)
            header.setStretchLastSection(True)
        control.apply()

    def _compact_identity_columns(self):
        if not getattr(self, '_choice_layout', False):
            return
        control = getattr(self, '_column_controls', None)
        if control is not None and control.manual:
            control.apply()
            return
        header = self.horizontalHeader()
        metrics = header.fontMetrics()
        for column, label in enumerate(('문항', '정답', '학생', '미도달')):
            header.setSectionResizeMode(column, QHeaderView.Interactive)
            self.setColumnWidth(column, max(32, metrics.horizontalAdvance(label) + 8))
        remaining = max(0, self.viewport().width() - sum(self.columnWidth(c) for c in range(4)))
        for column in range(4, 10):
            header.setSectionResizeMode(column, QHeaderView.Interactive)
            self.setColumnWidth(column, max(metrics.horizontalAdvance('100.00') + 8,
                                           remaining // 6 + (column - 4 < remaining % 6)))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if getattr(self, '_resizing_detail', False):
            return
        self._resizing_detail = True
        self._compact_identity_columns()
        if getattr(self, '_choice_layout', False):
            self.resizeRowsToContents()
        self._resizing_detail = False


class GrowthChart(QWidget):
    """Fixed 0–100 scale; missing historical means remain gaps, never zeroes."""
    roundSelected = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.points = []
        self.selected_subject = ""
        self.selected_index = -1
        self.show_student = True
        self.show_mean = True
        self.setFixedHeight(280)
        self.setFocusPolicy(Qt.StrongFocus)
        self._round_x = []
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)
        self.setAccessibleName("동일 과목 회차별 학생 점수와 학급 평균 그래프, 0부터 100점 고정 축")
        self._hit_points = []

    def set_data(self, points, subject):
        self.points = points
        self.selected_subject = subject or ""
        self.setMinimumWidth(max(380, len(points) * 116 + 65))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        palette = self.palette()
        background = palette.color(QPalette.Base)
        text = palette.color(QPalette.Text)
        dark = background.lightness() < 128
        accent = QColor("#77c9b9" if dark else "#2a7770")
        average = QColor("#b2bec5" if dark else "#687d83")
        painter.fillRect(self.rect(), background)
        painter.setFont(self.font())
        fm = painter.fontMetrics()
        top, bottom, left, right = 34, fm.height() * 2 + 15, 56, 34
        area = QRectF(left, top, max(1, self.width()-left-right), max(1, self.height()-top-bottom))
        grid = QColor(text); grid.setAlpha(35)
        for tick in range(0, 101, 20):
            y = area.bottom() - area.height() * tick / 100
            painter.setPen(QPen(grid, 1))
            painter.drawLine(QPointF(area.left(), y), QPointF(area.right(), y))
            painter.setPen(text)
            painter.drawText(QRectF(0, y-fm.height()/2, left-10, fm.height()), Qt.AlignRight, str(tick))
        painter.setPen(accent)
        painter.drawText(12, 19, "● 학생 환산점수")
        painter.setPen(average)
        painter.drawText(24 + fm.horizontalAdvance("● 학생 환산점수"), 19, "┄ 학급 평균")
        self._hit_points = []
        if not self.points:
            painter.setPen(text)
            painter.drawText(area, Qt.AlignCenter, "학생을 선택하면 같은 과목의 회차별 기록을 표시합니다.")
            return
        n = len(self.points)
        positions = [area.center().x() if n == 1 else area.left()+i*area.width()/(n-1) for i in range(n)]
        self._round_x = positions
        if 0 <= self.selected_index < n:
            painter.setPen(QPen(grid, 2))
            x = positions[self.selected_index]
            painter.drawLine(QPointF(x, area.top()), QPointF(x, area.bottom()))
        for field, color, style in (("score", accent, Qt.SolidLine), ("class_mean", average, Qt.DashLine)):
            if (field == "score" and not self.show_student) or (field == "class_mean" and not self.show_mean):
                continue
            previous = None
            for index, point in enumerate(self.points):
                value = point.get(field)
                if value is None or not math.isfinite(float(value)):
                    previous = None
                    continue
                pos = QPointF(positions[index], area.bottom()-area.height()*float(value)/100)
                painter.setPen(QPen(color, 2.5, style))
                if previous is not None:
                    painter.drawLine(previous, pos)
                painter.setBrush(color)
                painter.drawEllipse(pos, 4, 4)
                previous = pos
                self._hit_points.append((pos, point))
                if field == "score":
                    painter.setPen(color)
                    label_left = pos.x()+8 if index == 0 and n>1 else pos.x()-66 if index == n-1 and n>1 else pos.x()-29
                    label_left = max(area.left()+3, min(label_left, self.width()-62))
                    painter.drawText(QRectF(label_left, max(top, pos.y()-fm.height()-8), 58, fm.height()),
                                     Qt.AlignCenter, f"{float(value):.1f}")
        painter.setPen(text)
        label_width = min(150, area.width()/max(n, 1))
        for x, point in zip(positions, self.points):
            label = str(point.get("label", "회차 미상"))
            rect = QRectF(max(0, min(x-label_width/2, self.width()-label_width)), area.bottom()+9,
                          label_width, bottom-9)
            painter.drawText(rect, Qt.AlignHCenter | Qt.TextWordWrap,
                             fm.elidedText(label, Qt.ElideRight, int(label_width)*2))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._round_x:
            self.roundSelected.emit(min(range(len(self._round_x)), key=lambda i: abs(self._round_x[i]-event.position().x())))
            self.setFocus()
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if self.points and event.key() in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Home, Qt.Key_End):
            if event.key() == Qt.Key_Home: index = 0
            elif event.key() == Qt.Key_End: index = len(self.points)-1
            else: index = max(0, min(len(self.points)-1, self.selected_index + (1 if event.key() == Qt.Key_Right else -1)))
            self.roundSelected.emit(index)
            event.accept()
            return
        super().keyPressEvent(event)

    def mouseMoveEvent(self, event):
        for position, point in self._hit_points:
            if (position-event.position()).manhattanLength() < 15:
                mean = point.get("class_mean")
                score = point.get("score")
                score_text = f"{score:.2f}점" if score is not None else "자료 없음"
                QToolTip.showText(event.globalPosition().toPoint(),
                    f"{point.get('label', '')}\n학생 {score_text}\n학급 평균 " +
                    (f"{mean:.2f}점" if mean is not None else "자료 없음"), self)
                return
        QToolTip.hideText()


class PortfolioView:
    def __init__(self, window):
        self.window = window
        self.syncing = False
        self.model = {}
        root = window.tab_portfolio.layout()
        items = [root.takeAt(0) for _ in range(root.count())]
        self._retained_layout_items = items
        # Full-work actions were inserted first; existing portfolio actions follow title.
        work_actions, old_top, actions = items[0].layout(), items[1].layout(), items[2].layout()
        while old_top.count():
            old_item = old_top.takeAt(0)
            if isinstance(old_item.widget(), QLabel):
                old_item.widget().hide()
        root.addLayout(work_actions)
        root.addLayout(actions)
        root.setSpacing(5)
        report = QWidget()
        content = QVBoxLayout(report); content.setContentsMargins(5, 3, 5, 5); content.setSpacing(7)
        window.portfolio_content_panel = report
        selector = QHBoxLayout()
        selector.addWidget(QLabel("학생"))
        window.combo_portfolio_student.setMinimumWidth(190)
        window.combo_portfolio_student.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        selector.addWidget(window.combo_portfolio_student, 2)
        selector.addWidget(QLabel("검색")); selector.addWidget(window.le_portfolio_search, 1)
        selector.addWidget(QLabel("과목")); selector.addWidget(window.combo_portfolio_subject, 1)
        root.addLayout(selector)
        window.lbl_portfolio_summary.setProperty("role", "muted")
        root.addWidget(window.lbl_portfolio_summary)
        # Retain identity-based compatibility for saved selections, without a side rail.
        self.students = QListWidget(window.tab_portfolio)
        self.students.hide()
        self.students.currentItemChanged.connect(self._select_student)
        self.privacy_note = QLabel(report); self.privacy_note.hide()
        summary = QHBoxLayout()
        self.summary_values = []
        self.summary_captions = []
        for title in ("최근 확인 회차 점수", "직전 확인 회차 대비", "같은 회차 학급 평균과 차이"):
            box = QWidget(); column = QVBoxLayout(box); column.setContentsMargins(8, 2, 8, 3); column.setSpacing(1)
            label = QLabel(title); label.setProperty("role", "muted")
            value = QLabel("자료 없음"); value.setStyleSheet("font-size: 22px; font-weight: 650;")
            caption = QLabel(""); caption.setProperty("role", "muted")
            column.addWidget(label); column.addWidget(value); column.addWidget(caption)
            summary.addWidget(box, 1); self.summary_values.append(value); self.summary_captions.append(caption)
        content.addLayout(summary)
        chart_top = QHBoxLayout()
        self.heading = QLabel("회차별 변화"); self.heading.setProperty("role", "title")
        chart_top.addWidget(self.heading, 1)
        self.show_student = QCheckBox("학생 점수"); self.show_student.setChecked(True)
        self.show_mean = QCheckBox("학급 평균"); self.show_mean.setChecked(True)
        for checkbox in (self.show_student, self.show_mean):
            chart_top.addWidget(checkbox); checkbox.toggled.connect(self._update_chart_options)
        self.history_toggle = QPushButton("전체 저장 이력"); self.history_toggle.setCheckable(True)
        self.history_toggle.toggled.connect(self._toggle_history); chart_top.addWidget(self.history_toggle)
        content.addLayout(chart_top)
        self.chart = GrowthChart()
        chart_scroll = QScrollArea(); chart_scroll.setWidgetResizable(True); chart_scroll.setWidget(self.chart)
        chart_scroll.setFixedHeight(300); chart_scroll.setFrameShape(QScrollArea.NoFrame)
        content.addWidget(chart_scroll)
        round_row = QHBoxLayout(); round_row.addStretch(1)
        self.previous = QPushButton("이전 회차"); self.next = QPushButton("다음 회차")
        self.round_combo = QComboBox(); self.round_combo.setMinimumWidth(230)
        self.round_combo.setAccessibleName("포트폴리오 상세 회차 선택")
        self.previous.clicked.connect(lambda: self._choose_round(self.round_combo.currentIndex()-1))
        self.next.clicked.connect(lambda: self._choose_round(self.round_combo.currentIndex()+1))
        self.round_combo.currentIndexChanged.connect(self._render_selected_details)
        self.chart.roundSelected.connect(self._choose_round)
        round_row.addWidget(self.previous); round_row.addWidget(self.round_combo); round_row.addWidget(self.next); round_row.addStretch(1)
        content.addLayout(round_row)
        version_row = QHBoxLayout(); version_row.addWidget(QLabel("기록 버전"))
        self.version_combo = QComboBox(); self.version_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.version_combo.setAccessibleName("선택 회차의 저장 버전 선택")
        self.version_combo.currentIndexChanged.connect(self._render_version_details)
        version_row.addWidget(self.version_combo, 1); content.addLayout(version_row)
        self._versions = []
        self.badge = QLabel(); self.badge.setProperty("role", "muted")
        self.policy = QLabel("0–100점 고정 축 · 같은 과목만 연결 · 동일 회차는 현재 분석 우선 · 회차 미상 기록은 그래프 제외")
        self.policy.setProperty("role", "muted"); self.policy.setWordWrap(True)
        note_row = QHBoxLayout(); note_row.addWidget(self.policy, 1); note_row.addWidget(self.badge)
        content.addLayout(note_row)
        self.selected_heading = QLabel("회차별 학생 자료"); self.selected_heading.setProperty("role", "title")
        content.addWidget(self.selected_heading)
        self.provenance = QLabel(); self.provenance.setWordWrap(True); self.provenance.setProperty("role", "muted")
        content.addWidget(self.provenance)
        self.tabs = QTabWidget(); self.tabs.setObjectName("portfolio-detail-tabs")
        self.tables = {}
        for key, title in (("data", "Data"), ("perform", "수행평가"), ("items", "문항"), ("choice", "답지반응"), ("standards", "성취기준")):
            table = PortfolioDetailTable(0, 0); table.setObjectName("portfolio-detail-"+key)
            table.setEditTriggers(QTableWidget.NoEditTriggers); table.verticalHeader().setVisible(False)
            table.setAlternatingRowColors(True); table.setWordWrap(True)
            table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
            table.horizontalHeader().setStretchLastSection(True)
            self.tables[key] = table; self.tabs.addTab(table, title)
        self.stack = QStackedWidget(); self.stack.addWidget(self.tabs); self.stack.addWidget(window.table_portfolio)
        self.stack.setMinimumHeight(195); content.addWidget(self.stack, 1)
        # The old four-column summary remains available to state/compatibility checks.
        self.detail = QTableWidget(0, 4, window.tab_portfolio); self.detail.hide()
        self.detail.setHorizontalHeaderLabels(["학년도 · 회차", "학생 환산점수", "학급 평균", "기록 상태"])
        window.lbl_portfolio_note.hide()
        self.history_note = QLabel(); self.history_note.setWordWrap(True); self.history_note.setProperty("role", "muted")
        content.addWidget(self.history_note)
        report_scroll = QScrollArea(); report_scroll.setWidgetResizable(True); report_scroll.setWidget(report)
        report_scroll.setFrameShape(QScrollArea.NoFrame)
        root.addWidget(report_scroll, 1)
        self.report_scroll = report_scroll
        window.portfolio_student_list = self.students
        window.portfolio_growth_chart = self.chart
        window.portfolio_timeline_table = self.detail
        window.portfolio_history_toggle = self.history_toggle
        window.portfolio_version_combo = self.version_combo
        window.portfolio_round_combo = self.round_combo
        window.portfolio_show_student = self.show_student
        window.portfolio_show_mean = self.show_mean
        window.portfolio_detail_tabs = self.tabs
        window.portfolio_detail_tables = self.tables
        window.le_portfolio_search.textChanged.connect(lambda _: self.sync())

    def _toggle_history(self, checked):
        self.stack.setCurrentIndex(1 if checked else 0)
        self.history_toggle.setText("회차별 학생 자료로 돌아가기" if checked else "전체 저장 이력")

    @staticmethod
    def _point_key(point):
        import json
        return json.dumps([point.get(k) for k in ("student_hash", "subject", "year", "semester_no", "round_no", "grade")]
                          + ([point.get("snapshot_path")] if point.get("round_no") is None else []), ensure_ascii=False)

    @staticmethod
    def _score(value):
        return f"{float(value):.1f}점" if value is not None else "자료 없음"

    def _update_chart_options(self):
        self.chart.show_student = self.show_student.isChecked()
        self.chart.show_mean = self.show_mean.isChecked()
        self.chart.update()

    def _choose_round(self, index):
        if 0 <= index < self.round_combo.count():
            self.round_combo.setCurrentIndex(index)

    def _render_selected_details(self, *_):
        points = self.model.get("points", []) + self.model.get("unknown_points", [])
        index = self.round_combo.currentIndex()
        self.chart.selected_index = index if index < len(self.model.get("points", [])) else -1
        self._update_chart_options()
        self.previous.setEnabled(index > 0)
        self.next.setEnabled(0 <= index < len(points)-1)
        point = points[index] if 0 <= index < len(points) else None
        self.selected_round_point = point
        previous_version = self.version_combo.currentData()
        versions = []
        if point:
            for row in self.model.get("history", []):
                version_model = build_timeline([row], self.window.combo_portfolio_student.currentData(), point.get("subject"))
                normalized = version_model["points"] + version_model.get("unknown_points", [])
                if normalized and self._point_key(normalized[0]) == self._point_key(point):
                    versions.append(normalized[0])
            if not versions:
                versions = [point]
            versions.sort(key=lambda row: (self._revision_key(row) == self._revision_key(point), str(row.get("saved_at", ""))), reverse=True)
        self._versions = list({self._revision_key(row): row for row in versions}.values())
        blocker = QSignalBlocker(self.version_combo)
        self.version_combo.clear()
        for row in self._versions:
            source = "현재 분석" if row.get("source_kind") == "current" else "전체 작업" if row.get("source_kind") == "work-session" else "작업 내 분석" if row.get("source_kind") == "analysis-session" else "요약 저장"
            stamp = "미저장" if row.get("is_current_preview") else str(row.get("saved_at", ""))
            self.version_combo.addItem(f"{source} · {stamp}", self._revision_key(row))
        index = self.version_combo.findData(previous_version)
        self.version_combo.setCurrentIndex(index if index >= 0 else 0)
        del blocker
        self._render_version_details()

    @staticmethod
    def _revision_key(point):
        import json
        return json.dumps([point.get(k) for k in ("source_kind", "work_session_path", "snapshot_path", "detail_revision", "saved_at")], ensure_ascii=False)

    def _render_version_details(self, *_):
        index = self.version_combo.currentIndex()
        point = self._versions[index] if 0 <= index < len(self._versions) else None
        self.selected_point = point
        self.badge.setText("현재 분석 · 미저장" if point and point.get("is_current_preview") else "현재 분석" if point and point.get("source_kind") == "current" else "저장된 전체 작업" if point and point.get("source_kind") == "work-session" else "작업 내 분석 자료" if point and point.get("source_kind") == "analysis-session" else "저장된 요약" if point else "")
        self.selected_heading.setText((str(point.get("label", ""))+" · 학생 자료") if point else "회차별 학생 자료")
        if point:
            from .portfolio_details import resolve_details
            details = resolve_details(self.window, point)
        else:
            details = {"tabs": {}, "provenance": "상단에서 학생과 회차를 선택하세요."}
        self.details = details
        self.provenance.setText(str(details.get("provenance", "")))
        for key, table in self.tables.items():
            tab = details.get("tabs", {}).get(key, {})
            headers = tab.get("headers", [])
            rows = tab.get("rows", [])
            if not tab.get("available", False):
                headers, rows = ["자료 안내"], [[tab.get("message") or "이 회차에는 해당 상세 자료가 없습니다. 요약 점수로 상세 값을 추정하지 않습니다."]]
            table.setSortingEnabled(False); table.clear(); table.setColumnCount(len(headers)); table.setRowCount(len(rows))
            table.setHorizontalHeaderLabels([str(value) for value in headers])
            for r, row in enumerate(rows):
                for c, value in enumerate(row):
                    text = detail_cell_text(value, str(headers[c]))
                    item = QTableWidgetItem(text); item.setToolTip(text)
                    item.setData(Qt.UserRole, value)
                    if isinstance(value, Real) and not isinstance(value, bool):
                        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    table.setItem(r, c, item)
            table.configure_columns(key)
            table.resizeRowsToContents()

    def _select_student(self, item, previous=None):
        if self.syncing or item is None:
            return
        w = self.window
        index = w.combo_portfolio_student.findData(item.data(Qt.UserRole))
        if index >= 0:
            w.combo_portfolio_student.setCurrentIndex(index)
            # Selection itself filters by identity; leave search available for the next student.
            blocker = QSignalBlocker(w.le_portfolio_search)
            w.le_portfolio_search.clear()
            del blocker
            w._filter_portfolio_table("")

    def sync(self):
        if self.syncing:
            return
        self.syncing = True
        try:
            self._toggle_history(self.history_toggle.isChecked())
            w = self.window
            from .portfolio_details import presentation_rows
            rows = presentation_rows(w, getattr(w, "_portfolio_rows_cache", []))
            selected = str(w.combo_portfolio_student.currentData() or "")
            privacy = w._counseling_mode_enabled()
            terms = w._search_terms(w.le_portfolio_search.text())
            grouped = {}
            for row in rows:
                grouped.setdefault(w._portfolio_student_key(row), row)
            if selected and w.le_portfolio_search.text() == str(grouped.get(selected, {}).get("name", "")):
                terms = []
            self.students.clear()
            for index in range(1, w.combo_portfolio_student.count()):
                key = str(w.combo_portfolio_student.itemData(index) or "")
                row = grouped.get(key, {})
                name, class_no = str(row.get("name", "")), str(row.get("class_no", ""))
                label = f"익명 학생 {index:03d}" if privacy else f"{name or '미연결 학생'}  {class_no}"
                w.combo_portfolio_student.setItemText(index, label if privacy else w._portfolio_student_label(row))
                automatic_search = selected == key and w.le_portfolio_search.text() == name
                matches = not terms or automatic_search or any(term in (name+" "+class_no).lower() for term in terms)
                w.combo_portfolio_student.view().setRowHidden(index, not matches and key != selected)
                if not matches:
                    continue
                item = QListWidgetItem(label); item.setData(Qt.UserRole, key)
                item.setSizeHint(QSize(160, 40)); self.students.addItem(item)
                if key == selected:
                    self.students.setCurrentItem(item)
            # Never expose an automatically filled name in the search field during counseling.
            w.le_portfolio_search.setEchoMode(QLineEdit.EchoMode.Password if privacy else QLineEdit.EchoMode.Normal)
            self.privacy_note.setText("상담 모드 · 목록과 그래프의 이름·반번호 비공개" if privacy else "미연결 학생은 이름을 추정해 합치지 않습니다.")
            subject = w.combo_portfolio_subject.currentData() or None
            self.model = build_timeline(rows, selected, subject) if selected else {"points": [], "history": [], "selected_subject": subject}
            points = self.model["points"]
            chosen = self.model.get("selected_subject") or ""
            row = grouped.get(selected, {})
            identity = "상담 학생" if privacy else " ".join(filter(None, [row.get("name"), row.get("class_no")]))
            w.lbl_portfolio_summary.setText(identity or "상단에서 학생을 선택하세요")
            self.heading.setText(f"{chosen} · 회차별 변화" if chosen else "회차별 변화")
            self.chart.set_data(points, chosen)
            prior_round = self.round_combo.currentData()
            blocker = QSignalBlocker(self.round_combo)
            self.round_combo.clear()
            selectable = points + self.model.get("unknown_points", [])
            for point in selectable:
                suffix = " · 회차 미확인 (그래프 제외)" if point in self.model.get("unknown_points", []) else ""
                self.round_combo.addItem(str(point.get("label", "회차 미확인")) + suffix, self._point_key(point))
            index = self.round_combo.findData(prior_round)
            default = next((i for i, p in enumerate(selectable) if p.get("is_current_analysis") or p.get("is_current_preview")), max(0, len(points)-1))
            self.round_combo.setCurrentIndex(index if index >= 0 else default)
            del blocker
            dated_points = [point for point in points if all(point.get(field) is not None
                            for field in ("year", "semester_no", "round_no"))]
            latest = dated_points[-1] if dated_points else {}
            previous = dated_points[-2] if len(dated_points)>1 else {}
            value, prior, mean = latest.get("score"), previous.get("score"), latest.get("class_mean")
            ordered_pair = all(point.get(field) is not None for point in (latest, previous) for field in ("year", "semester_no", "round_no"))
            if not ordered_pair:
                prior = None
            difference = lambda a, b: f"{float(a)-float(b):+.1f}점" if a is not None and b is not None else "비교 자료 없음"
            for label, text in zip(self.summary_values, (self._score(value), difference(value, prior), difference(value, mean))):
                label.setText(text)
            for label, text in zip(self.summary_captions, (str(latest.get("label", "")), "같은 과목 직전 회차 기준", "최근 학급 평균 "+self._score(mean))):
                label.setText(text)
            self._render_selected_details()
            self.detail.setRowCount(len(points))
            for r, point in enumerate(points):
                mean = point.get("class_mean")
                status = "현재 · 미저장" if point.get("is_current_preview") else "저장됨"
                if point.get("revision_count", 1) > 1:
                    status += f" · 이력 {point['revision_count']}개"
                values = [str(point.get("label", "")), f"{point['score']:.2f}점" if point.get("score") is not None else "자료 없음",
                          f"{mean:.2f}점" if mean is not None else "자료 없음", status]
                for c, value in enumerate(values):
                    item = QTableWidgetItem(value); item.setToolTip(value)
                    if c in (1, 2): item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    self.detail.setItem(r, c, item)
            count = sum(row.get("source_kind") not in ("current", "analysis-session") for row in self.model.get("history", []))
            self.history_note.setText(f"전체 저장 이력 {count}개 보존 · 과거 평균이 없으면 자료 없음으로 표시합니다.")
            errors = len(getattr(w, "_portfolio_load_errors", []))
            if errors:
                self.history_note.setText(self.history_note.text() + f" · 읽지 못한 저장 파일 {errors}개 (원본 보존)")
            self.history_note.setToolTip(w.lbl_portfolio_note.text())
            if w.exam is not None:
                w.btn_portfolio_save.setText(f"현재 과목 저장 · {w.exam.subject}")
            else:
                w.btn_portfolio_save.setText("현재 과목 저장")
        finally:
            self.syncing = False


def install_portfolio_view(window):
    window.portfolio_view = PortfolioView(window)
    window.portfolio_view.sync()
    return window.portfolio_view
