"""Explicit synthetic QA only: native frozen rows and persistent student selector."""
from __future__ import annotations

REQUIRED_CHECKS = (
    'Data frozen and main wheel keep 103 synthetic rows aligned',
    'Data frozen rows align at scrollbar end after sort filter and zoom',
    'portfolio student selector remains fixed while report scrolls',
    'scroll QA restores original analysis calculator and selections',
)


def verify(window, output, check, wait, report):
    import copy
    from PySide6.QtCore import Qt, QPoint, QPointF
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtTest import QTest
    from .analysis import analyze_overall, build_score_matrix
    from .widgets import refresh_frozen_columns

    controller = window.work_sessions
    captured = []
    controller.capture(lambda value, error: captured.append((value,error)))
    wait(lambda: bool(captured))
    assert captured[0][1] is None, 'scroll QA capture failed'
    original = captured[0][0]
    old_zoom = window._zoom_percent()
    old_theme = window.theme.mode
    original_student_count = len(window.exam.students)
    measurements = []

    def aligned(table, label):
        frozen = table.frozenView
        deltas = []
        for row in range(table.rowCount()):
            if table.isRowHidden(row):
                continue
            left = frozen.visualRect(table.model().index(row,0))
            right = table.visualRect(table.model().index(row,2))
            deltas.append(frozen.viewport().mapToGlobal(left.topLeft()).y()
                          - table.viewport().mapToGlobal(right.topLeft()).y())
        measurements.append({'case':label, 'maximum_row_offset':max(map(abs,deltas),default=0),
                             'main_viewport_height':table.viewport().height(),
                             'frozen_viewport_height':frozen.viewport().height()})
        assert deltas and not any(deltas), f'{label}: frozen row y offset {max(map(abs,deltas),default=0)}'

    def wheel(view):
        pos = QPointF(35,55)
        QApplication = __import__('PySide6.QtWidgets',fromlist=['QApplication']).QApplication
        QApplication.sendEvent(view.viewport(),QWheelEvent(pos,QPointF(view.viewport().mapToGlobal(pos.toPoint())),
            QPoint(),QPoint(0,-120),Qt.NoButton,Qt.NoModifier,Qt.ScrollUpdate,False))
        QTest.qWait(80)

    try:
        exam = copy.deepcopy(window.exam)
        originals = exam.students
        exam.students = []
        for index in range(103):
            student = copy.deepcopy(originals[index % len(originals)])
            student.sid = f'scroll-synthetic-{index:03}'
            student.name = f'스크롤합성{index:03}'
            student.class_no = f'{index // 35 + 1}/{index % 35 + 1}'
            student.grade_class = str(index // 35 + 1)
            exam.students.append(student)
        window.exam = exam
        matrix, _, _ = build_score_matrix(exam)
        window.overall = analyze_overall(exam,matrix)
        window.le_search.clear()
        window.btn_counsel_mode.setChecked(False)
        window.theme.set_mode('light')
        window.tabs.setCurrentWidget(window.tab_data)
        window._render_data_tab()
        window.resize(1280,800)
        QTest.qWait(250)
        table = window.table_data
        assert table.rowCount()==103
        bar = table.verticalScrollBar()
        bar.setValue(0)
        wheel(table.frozenView)
        assert bar.value()>0, 'wheel on frozen columns did not move main rows'
        aligned(table,'frozen wheel')
        wheel(table); aligned(table,'main wheel')
        check(REQUIRED_CHECKS[0],True)
        for zoom in (100,120):
            window._set_zoom(zoom); QTest.qWait(150)
            refresh_frozen_columns(table)
            table.sortByColumn(2,Qt.DescendingOrder)
            bar.setValue(bar.maximum()//2); QTest.qWait(80); aligned(table,f'{zoom} middle')
            bar.setValue(bar.maximum()); QTest.qWait(80); aligned(table,f'{zoom} end')
            table.horizontalScrollBar().setValue(table.horizontalScrollBar().maximum())
            aligned(table,f'{zoom} horizontal end')
            window.le_search.setText('스크롤합성00'); QTest.qWait(80)
            bar.setValue(bar.maximum()); QTest.qWait(80); aligned(table,f'{zoom} filter')
            window.le_search.clear(); QTest.qWait(80)
        check(REQUIRED_CHECKS[1],True)
        window._set_zoom(100); QTest.qWait(150)
        assert window.grab().save(str(output/'data-frozen-scroll-light.png'))
    finally:
        window._set_zoom(old_zoom)
        restored = []
        controller.restore(original,lambda ok,error:restored.append((ok,error)))
        wait(lambda: bool(restored))
        window.theme.set_mode(old_theme)
        assert restored[0][0] and restored[0][1] is None, 'scroll QA original state restore failed'
        assert len(window.exam.students)==original_student_count and window.table_data.rowCount()==original_student_count, 'scroll QA did not restore original student rows'

    selected = window.combo_portfolio_student.currentData()
    try:
        window.theme.set_mode('light')
        window.tabs.setCurrentWidget(window.tab_portfolio)
        scroll = window.portfolio_view.report_scroll.verticalScrollBar()
        selector = window.combo_portfolio_student
        before = selector.mapToGlobal(QPoint(0,0))
        scroll.setValue(scroll.maximum()); QTest.qWait(100)
        check(REQUIRED_CHECKS[2], scroll.maximum()>0 and selector.isVisible()
              and selector.mapToGlobal(QPoint(0,0))==before and selector.currentData()==selected
              and not window.portfolio_view.report_scroll.isAncestorOf(selector))
        assert window.grab().save(str(output/'portfolio-sticky-selector-light.png'))
    finally:
        restored = []
        controller.restore(original,lambda ok,error:restored.append((ok,error)))
        wait(lambda: bool(restored))
        window.theme.set_mode(old_theme)
        assert restored[0][0] and restored[0][1] is None, 'sticky QA original state restore failed'
    recaptured = []
    controller.capture(lambda value,error:recaptured.append((value,error)))
    wait(lambda: bool(recaptured))
    after = recaptured[0][0]
    check(REQUIRED_CHECKS[3],restored[0][0] and restored[0][1] is None and recaptured[0][1] is None
          and after['domain']==original['domain'] and after['calculator_project']==original['calculator_project']
          and window.combo_portfolio_student.currentData()==selected
          and len(window.exam.students)==original_student_count and window.table_data.rowCount()==original_student_count)
    report['scroll_alignment'] = {'synthetic_students':103,'measurements':measurements,
                                  'original_domain_and_calculator_restored':True}
