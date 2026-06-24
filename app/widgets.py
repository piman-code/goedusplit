"""
공통 커스텀 위젯들.

- StepperSpinBox: 좌/우에 큰 - / + 버튼이 붙은 더블 스핀 위젯.
  QSS의 ::up-button/::down-button 표시가 일부 환경에서 안 먹는 문제를 회피하고,
  손가락(터치)으로도 클릭 쉬운 큰 버튼을 제공한다.

- ItemBarDelegate: 표 셀 안에 '수치 뒤로 가로 막대'를 그리는 delegate.
  KICE 웹앱처럼 정답률·변별도가 한눈에 들어오게 한다.

- ZoomableCanvas: 마우스 휠로 자체 확대/축소 가능한 matplotlib 캔버스.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QObject, QRect, QSize, QPointF
from PySide6.QtGui import QColor, QPainter, QBrush, QPen, QPainterPath
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QPushButton, QDoubleSpinBox, QSizePolicy,
    QStyledItemDelegate, QStyle, QTableWidgetItem, QTableView, QHeaderView,
    QAbstractItemView, QTableWidget
)


class StepperSpinBox(QWidget):
    """[ - ][   값   ][ + ] 형태의 더블 스핀 위젯."""
    valueChanged = Signal(float)
    BASE_HEIGHT = 48
    BUTTON_BASE_HEIGHT = 44
    BUTTON_BASE_WIDTH = 38
    VALUE_MIN_BASE_WIDTH = 118
    SIDEBAR_BASE_HEIGHT = 40
    SIDEBAR_BUTTON_BASE_HEIGHT = 36
    SIDEBAR_BUTTON_BASE_WIDTH = 32
    SIDEBAR_VALUE_MIN_BASE_WIDTH = 96
    SIDEBAR_ROW_BASE_HEIGHT = 82

    def __init__(self, *, value: float = 0.0, minimum: float = 0.0,
                 maximum: float = 100.0, step: float = 1.0, decimals: int = 2,
                 suffix: str = "", parent=None):
        super().__init__(parent)
        self.setFixedHeight(self.BASE_HEIGHT)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        h = QHBoxLayout(self); h.setContentsMargins(0, 0, 0, 0); h.setSpacing(4)

        self.btn_minus = QPushButton("−")
        self.btn_minus.setProperty("role", "stepper")
        self.btn_minus.setFixedWidth(self.BUTTON_BASE_WIDTH)
        self.btn_minus.setFixedHeight(self.BUTTON_BASE_HEIGHT)
        self.btn_minus.setAutoRepeat(True)
        self.btn_minus.setAutoRepeatInterval(80)
        self.btn_minus.setAutoRepeatDelay(350)
        self.btn_minus.setFocusPolicy(Qt.NoFocus)

        self.spin = QDoubleSpinBox()
        self.spin.setProperty("role", "stepper-spin")
        self.spin.setRange(minimum, maximum)
        self.spin.setValue(value)
        self.spin.setDecimals(decimals)
        self.spin.setSingleStep(step)
        if suffix:
            self.spin.setSuffix(suffix)
        self.spin.setButtonSymbols(QDoubleSpinBox.NoButtons)  # 내장 화살표 제거
        self.spin.setAlignment(Qt.AlignCenter)
        self.spin.setFixedHeight(self.BUTTON_BASE_HEIGHT)
        self.spin.setMinimumWidth(self.VALUE_MIN_BASE_WIDTH)
        self.spin.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.btn_plus = QPushButton("+")
        self.btn_plus.setProperty("role", "stepper")
        self.btn_plus.setFixedWidth(self.BUTTON_BASE_WIDTH)
        self.btn_plus.setFixedHeight(self.BUTTON_BASE_HEIGHT)
        self.btn_plus.setAutoRepeat(True)
        self.btn_plus.setAutoRepeatInterval(80)
        self.btn_plus.setAutoRepeatDelay(350)
        self.btn_plus.setFocusPolicy(Qt.NoFocus)

        h.addWidget(self.btn_minus)
        h.addWidget(self.spin, 1)
        h.addWidget(self.btn_plus)

        self.btn_minus.clicked.connect(self._step_down)
        self.btn_plus.clicked.connect(self._step_up)
        self.spin.valueChanged.connect(self.valueChanged.emit)

    def _step_up(self):
        self.spin.setValue(min(self.spin.maximum(), self.spin.value() + self.spin.singleStep()))

    def _step_down(self):
        self.spin.setValue(max(self.spin.minimum(), self.spin.value() - self.spin.singleStep()))

    # 외부에서 QDoubleSpinBox 인터페이스처럼 쓰기 위한 패스스루
    def value(self) -> float: return self.spin.value()
    def setValue(self, v: float):
        self.spin.blockSignals(True)
        self.spin.setValue(v)
        self.spin.blockSignals(False)
    def setRange(self, lo: float, hi: float): self.spin.setRange(lo, hi)
    def setDecimals(self, d: int): self.spin.setDecimals(d)
    def setSingleStep(self, s: float): self.spin.setSingleStep(s)
    def setSuffix(self, s: str): self.spin.setSuffix(s)
    def setEnabled(self, on: bool):
        super().setEnabled(on)
        self.spin.setEnabled(on)
        self.btn_minus.setEnabled(on)
        self.btn_plus.setEnabled(on)
    def blockSignals(self, b: bool):
        return self.spin.blockSignals(b)


# ---------------------------------------------------------------------------
# 표 셀 안 가로 막대 delegate (수치 뒤에 진척도 막대)
# ---------------------------------------------------------------------------

class ItemBarDelegate(QStyledItemDelegate):
    """셀 텍스트 뒤에 '값/최댓값' 비율만큼 가로 막대를 그린다.

    동작 방식:
      1) super().paint() 로 표준 셀 그리기(배경·alternation·선택색·텍스트)를 끝낸 뒤
      2) 그 위에 알파 값이 매우 낮은 막대를 덮어 둔다.
      → 텍스트가 막대에 가려질 일이 없고, 라이트/다크 모두에서 가독성 보장.

    셀의 Qt.UserRole 에 (value, max_value, color_hex, light_bool) 튜플을 두면 자동 적용.
    """

    @staticmethod
    def set_bar(item, value: float, max_value: float = 100.0,
                color: str = "#2563eb", light: bool = True):
        from PySide6.QtCore import Qt as _Qt
        item.setData(_Qt.UserRole, (float(value), float(max_value), str(color), bool(light)))

    def paint(self, painter: QPainter, option, index):
        # 1) 표준 셀 먼저 그리기 (텍스트 + 배경 + alt + 선택)
        super().paint(painter, option, index)

        # 2) 막대 메타가 있으면 덧칠
        meta = index.data(Qt.UserRole)
        if not meta:
            return
        try:
            value, max_value, color, light = meta
        except Exception:
            return
        if not max_value or float(max_value) <= 0:
            return

        ratio = max(0.0, min(1.0, float(value) / float(max_value)))
        if ratio <= 0:
            return

        rect: QRect = option.rect
        # 셀 위/아래 약간 여백, 좌/우 작은 여백
        inner = rect.adjusted(3, 4, -3, -4)
        bar_w = int(inner.width() * ratio)
        if bar_w <= 0:
            return
        bar_rect = QRect(inner.left(), inner.top(), bar_w, inner.height())

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        col = QColor(color)
        # 알파를 낮게 둬서 텍스트가 비치도록
        col.setAlpha(58 if light else 100)
        path = QPainterPath()
        path.addRoundedRect(bar_rect.x(), bar_rect.y(),
                            bar_rect.width(), bar_rect.height(), 3, 3)
        painter.fillPath(path, col)
        painter.restore()


# ---------------------------------------------------------------------------
# 휠 줌 가능한 matplotlib 캔버스
# ---------------------------------------------------------------------------

# 별도 모듈에 있는 기존 FigureCanvas를 그대로 쓰되, 휠 이벤트로 xlim/ylim를 조절.
# main_window.CanvasHolder 안에서 사용된다.

def install_frozen_columns(table, frozen_count: int):
    """QTableWidget의 첫 N개 컬럼을 좌측에 '진짜' 틀 고정한다.

    구현 핵심:
      1) 같은 model을 공유하는 QTableView를 좌측 위에 덮어 첫 N 컬럼만 보여준다.
         → 본문과 헤더는 원래 위치를 유지해 컬럼명이 어긋나지 않는다.
      2) 본문 세로 스크롤과 frozen 뷰 세로 스크롤을 동기화한다.
      3) frozen 헤더 클릭은 메인 표의 sortByColumn으로 전달 → 반/번호·이름도 정렬 가능.
    """
    if frozen_count <= 0:
        return None

    frozen_widths = [table.columnWidth(c) for c in range(min(frozen_count, table.columnCount()))]

    frozen = QTableView(table)
    frozen.setObjectName("frozen")
    frozen.setModel(table.model())
    frozen.setSelectionModel(table.selectionModel())
    frozen.setFocusPolicy(Qt.NoFocus)
    frozen.verticalHeader().hide()
    frozen.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    frozen.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    frozen.setEditTriggers(QAbstractItemView.NoEditTriggers)
    frozen.setSelectionBehavior(QAbstractItemView.SelectRows)
    frozen.setShowGrid(True)
    frozen.setItemDelegate(table.itemDelegate())
    for c in range(table.columnCount()):
        d = table.itemDelegateForColumn(c)
        if d is not None:
            frozen.setItemDelegateForColumn(c, d)

    # 첫 N개 컬럼만 보이게 (나머지는 hide)
    for c in range(table.columnCount()):
        frozen.setColumnHidden(c, c >= frozen_count)
        if c < frozen_count:
            frozen.setColumnWidth(c, frozen_widths[c])

    # 헤더 sorting 표시 동기화
    frozen.setSortingEnabled(table.isSortingEnabled())
    frozen.horizontalHeader().setSortIndicatorShown(True)

    # 헤더 sort 동작: frozen 헤더 클릭 → 메인 표를 정렬
    def _on_frozen_sort(idx, order):
        if not table.isSortingEnabled():
            return
        table.sortByColumn(idx, order)
        # 메인 헤더 indicator도 동기화
        table.horizontalHeader().setSortIndicator(idx, order)
    frozen.horizontalHeader().sortIndicatorChanged.connect(_on_frozen_sort)

    # 메인 표 스크롤 동기화 (vertical만)
    table.verticalScrollBar().valueChanged.connect(frozen.verticalScrollBar().setValue)

    def _sync_geometry():
        # frozen 폭 = 고정 컬럼들의 합 + verticalHeader 폭 (선택적)
        vh_w = table.verticalHeader().width() if table.verticalHeader().isVisible() else 0
        cols_w = sum(getattr(table, "frozenWidths", frozen_widths))
        total_w = vh_w + cols_w
        # frozen 위치: 표 frame 안쪽, 헤더 + 본문 높이 모두 포함
        header_h = table.horizontalHeader().height()
        frozen.setGeometry(table.frameWidth(), table.frameWidth(),
                           total_w, table.viewport().height() + header_h)

    def _on_main_resize(event):
        QTableWidget.resizeEvent(table, event)
        _sync_geometry()

    table.resizeEvent = _on_main_resize
    table.frozenView = frozen
    table.frozenCount = frozen_count
    table.frozenWidths = frozen_widths
    refresh_frozen_columns(table)
    frozen.show()
    return frozen


def refresh_frozen_columns(table):
    """행 추가/삭제, 컬럼 폭 변경, 모델 갱신 후 호출."""
    if not hasattr(table, "frozenView") or table.frozenView is None:
        return
    fv = table.frozenView
    fc = getattr(table, "frozenCount", 0)
    widths = []
    for c in range(min(fc, table.columnCount())):
        w = table.columnWidth(c)
        if w <= 0 and hasattr(table, "frozenWidths") and c < len(table.frozenWidths):
            w = table.frozenWidths[c]
        if w <= 0:
            w = fv.columnWidth(c)
        widths.append(max(1, w))
    table.frozenWidths = widths
    for c in range(table.columnCount()):
        fv.setColumnHidden(c, c >= fc)
        if c < fc:
            table.setColumnHidden(c, False)
            fv.setColumnWidth(c, widths[c])
        else:
            table.setColumnHidden(c, False)
    for r in range(table.rowCount()):
        fv.setRowHeight(r, table.rowHeight(r))
    # 메인 viewport 좌측 마진과 frozen 위치 재계산
    cols_w = sum(widths)
    vh_w = table.verticalHeader().width() if table.verticalHeader().isVisible() else 0
    header_h = table.horizontalHeader().height()
    fv.setGeometry(table.frameWidth(), table.frameWidth(),
                   vh_w + cols_w, table.viewport().height() + header_h)
    fv.show()
    fv.raise_()


class NaturalItem(QTableWidgetItem):
    """표시 텍스트는 그대로 두고 정렬만 sort_value 기반으로 하는 셀.

    예: 반/번호 '1/3' → 표시는 '1/3' 그대로, 정렬은 (1, 3) 튜플로.
    """
    def __init__(self, text: str, sort_value):
        super().__init__(text)
        self._sort_value = sort_value
    def __lt__(self, other):
        try:
            ov = other._sort_value  # type: ignore[attr-defined]
        except AttributeError:
            return super().__lt__(other)
        try:
            return self._sort_value < ov
        except Exception:
            return super().__lt__(other)


def attach_wheel_zoom(canvas):
    """주어진 FigureCanvasQTAgg 에 마우스 휠로 확대/축소되는 동작을 붙인다.

    - 휠 위 = 확대 (마우스 위치 중심), 휠 아래 = 축소
    - 셋째 클릭 또는 더블클릭 = 원상복귀 (autoscale)
    초기 xlim/ylim 을 저장해 두고 더블클릭 시 그 값으로 복원.
    """
    # figure의 모든 axes의 초기 limit을 캡처 (한 번)
    initial = []
    for ax in canvas.figure.axes:
        initial.append((ax, ax.get_xlim(), ax.get_ylim()))

    def on_scroll(event):
        ax = event.inaxes
        if ax is None:
            return
        scale = 0.85 if event.button == "up" else (1.18 if event.button == "down" else 1.0)
        x0, x1 = ax.get_xlim(); y0, y1 = ax.get_ylim()
        xc = event.xdata if event.xdata is not None else (x0 + x1) / 2
        yc = event.ydata if event.ydata is not None else (y0 + y1) / 2
        ax.set_xlim(xc - (xc - x0) * scale, xc + (x1 - xc) * scale)
        ax.set_ylim(yc - (yc - y0) * scale, yc + (y1 - yc) * scale)
        canvas.draw_idle()

    def on_press(event):
        # dblclick=True 또는 가운데 버튼 클릭 → 원상복귀
        if event.dblclick or event.button == 2:
            for ax, x_lim, y_lim in initial:
                try:
                    ax.set_xlim(x_lim); ax.set_ylim(y_lim)
                except Exception:
                    pass
            canvas.draw_idle()

    canvas.mpl_connect("scroll_event", on_scroll)
    canvas.mpl_connect("button_press_event", on_press)
