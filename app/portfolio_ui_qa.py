"""Opt-in synthetic interaction checks for the approved portfolio report layout."""
from __future__ import annotations

REQUIRED_CHECKS = (
    'portfolio student selector updates timeline and details',
    'portfolio graph compares same subject rounds with actual class means',
    'portfolio changing student updates graph scores',
    'portfolio history toggle preserves existing table and actions',
    'portfolio counseling masks new student surfaces',
    'portfolio laptop and monitor show report graph without student side rail',
    'portfolio full work restores student round detail tab and chart toggles',
    'portfolio graph click keyboard and round buttons synchronize five detail tabs',
)


def verify(window, output, check, wait, report):
    from PySide6.QtCore import Qt, QPoint
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QLabel
    window.tabs.setCurrentWidget(window.tab_portfolio)
    window.le_portfolio_search.clear()
    window.combo_portfolio_subject.setCurrentIndex(window.combo_portfolio_subject.findData(window.exam.subject))
    window.refresh_portfolio_tab()
    selector = window.combo_portfolio_student
    assert selector.count() >= 3
    def choose_student(index):
        selector.setFocus(); QTest.keyClick(selector, Qt.Key_Home)
        for _ in range(index): QTest.keyClick(selector, Qt.Key_Down)
        QTest.qWait(100)
        return selector.currentData()
    first_key = choose_student(1)
    view = window.portfolio_view
    chart = window.portfolio_growth_chart
    points = chart.points
    check(REQUIRED_CHECKS[0], first_key and len(points)==2 and view.selected_point is not None
          and not window.portfolio_student_list.isVisible() and view.tabs.count()==5)
    check(REQUIRED_CHECKS[1], [p['round_no'] for p in points]==[1,2]
          and len({p['subject'] for p in points})==1 and all(p['class_mean']==75.0 for p in points))
    scores = [p['score'] for p in points]
    second_key = choose_student(2)
    check(REQUIRED_CHECKS[2], second_key!=first_key and [p['score'] for p in chart.points]!=scores)
    toggle = window.portfolio_history_toggle
    toggle.click(); QTest.qWait(80)
    history_visible = view.stack.currentWidget() is window.table_portfolio
    toggle.click(); QTest.qWait(80)
    check(REQUIRED_CHECKS[3], history_visible and view.stack.currentWidget() is view.tabs
          and window.table_portfolio.columnCount()==9 and window.btn_portfolio_save.isEnabled())
    window.btn_counsel_mode.setChecked(True); QTest.qWait(100)
    names = [student.name for student in window.exam.students]
    text = ' '.join(selector.itemText(i) for i in range(selector.count()))
    text += ' '.join(label.text() for label in window.portfolio_content_panel.findChildren(QLabel))
    text += ' '.join(table.item(r,c).text() for table in view.tables.values()
                     for r in range(table.rowCount()) for c in range(table.columnCount()) if table.item(r,c))
    check(REQUIRED_CHECKS[4], not any(name and name in text for name in names))
    window.grab().save(str(output/'portfolio-counseling.png'))
    window.btn_counsel_mode.setChecked(False); choose_student(1)
    captures = []
    for mode,width,height,theme in [('laptop',1280,800,'light'),('monitor',1600,1000,'light'),('laptop',1280,800,'dark')]:
        window.theme.set_mode(theme)
        combo = window._result_layout_refs['mode']; combo.setCurrentIndex(combo.findData(mode))
        window.resize(width,height); view.report_scroll.verticalScrollBar().setValue(0); QTest.qWait(250)
        top = chart.mapTo(window,QPoint(0,0))
        assert chart.isVisible() and chart.height()==280 and selector.isVisible()
        assert not window.portfolio_student_list.isVisible()
        assert top.x()>=0 and top.x()+chart.width()<=window.width() and top.y()+chart.height()<=window.height()
        name=f'portfolio-{mode}-{theme}.png'
        assert window.grab().save(str(output/name)); captures.append(name)
    check(REQUIRED_CHECKS[5], len(captures)==3)
    window.theme.set_mode('light')
    view.report_scroll.ensureWidgetVisible(chart); QTest.qWait(80)
    QTest.mouseClick(chart,Qt.LeftButton,pos=QPoint(round(chart._round_x[0]),chart.height()//2))
    assert view.round_combo.currentIndex()==0 and view.selected_round_point is chart.points[0], f"graph click round mismatch: index={view.round_combo.currentIndex()}, selected={view.selected_round_point}, expected={chart.points[0]}"
    QTest.keyClick(chart,Qt.Key_Right)
    assert view.round_combo.currentIndex()==1, f"graph keyboard selection mismatch: {view.round_combo.currentIndex()}"
    view.previous.click(); assert view.round_combo.currentIndex()==0, "previous round button did not select first round"
    view.next.click(); assert view.round_combo.currentIndex()==1, "next round button did not select second round"
    for index in range(5):
        view.report_scroll.ensureWidgetVisible(view.tabs); QTest.qWait(40)
        QTest.mouseClick(view.tabs.tabBar(),Qt.LeftButton,pos=view.tabs.tabBar().tabRect(index).center())
        table = view.tabs.currentWidget()
        assert view.tabs.currentIndex()==index and table.rowCount()>0, f"detail tab click mismatch: expected={index}, actual={view.tabs.currentIndex()}, rows={table.rowCount()}"
    assert window.grab().save(str(output/'portfolio-details-light.png')), 'detail screenshot save failed'
    check(REQUIRED_CHECKS[7],True)
    view.round_combo.setCurrentIndex(0); view.tabs.setCurrentIndex(3)
    view.show_mean.setChecked(False); toggle.setChecked(True)
    captured=[]; window.work_sessions.capture(lambda payload,error:captured.append((payload,error)))
    wait(lambda:bool(captured)); assert captured[0][1] is None, f"portfolio full-work capture failed: {captured[0][1]}"
    choose_student(2); toggle.setChecked(False); view.round_combo.setCurrentIndex(1)
    view.tabs.setCurrentIndex(0); view.show_mean.setChecked(True)
    restored=[]; window.work_sessions.restore(captured[0][0],lambda ok,error:restored.append((ok,error)))
    wait(lambda:bool(restored))
    check(REQUIRED_CHECKS[6],restored[0][0] and selector.currentData()==first_key
          and [p['score'] for p in chart.points]==scores and toggle.isChecked()
          and view.round_combo.currentIndex()==0 and view.tabs.currentIndex()==3 and not view.show_mean.isChecked())
    toggle.setChecked(False); view.show_mean.setChecked(True)
    report['portfolio_ui']={'captures':captures,'synthetic_only':True,'rounds':len(chart.points),
                            'student_scores':scores,'class_means':[p['class_mean'] for p in chart.points]}
