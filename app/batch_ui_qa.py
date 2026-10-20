"""Opt-in native QA for compact numeric portfolio details and batch rounds."""
from __future__ import annotations

REQUIRED_CHECKS = (
    'portfolio five answer choices fit laptop at 100 and 120 percent',
    'portfolio percentage text rounds to two places without changing source values',
)


def verify(window, output, check, wait, report):
    import copy
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from .work_sessions import build_session
    from .portfolio_details import resolve_details

    controller=window.work_sessions
    def capture():
        result=[]
        controller.capture(lambda payload,error:result.append((payload,error)))
        wait(lambda:bool(result))
        assert result[0][1] is None, 'batch QA capture failed'
        return result[0][0]
    def restore(payload):
        result=[]
        controller.restore(payload,lambda ok,error:result.append((ok,error)))
        wait(lambda:bool(result))
        assert result[0][0] and result[0][1] is None, 'batch QA restore failed'
    original=capture()
    old_zoom=window._zoom_percent();old_theme=window.theme.mode
    old_size=window.size()
    try:
        exam=copy.deepcopy(window.exam)
        template=exam.students[0]
        exam.students=[];exam.use_perform=False
        exam.weight_pencil=100;exam.weight_perform=0
        for index,answer in enumerate(('.',2,3,4,5,'')):
            student=copy.deepcopy(template)
            student.sid=f'five-choice-synthetic-{index}'
            student.name=f'선택지합성{index}'
            student.class_no=f'1/{index+1}';student.grade_class='1'
            student.answers={item.number:answer for item in exam.select_items}
            student.total=sum(item.score for item in exam.select_items if answer=='.' or str(answer)==str(item.answer))
            student.final_score=student.total;student.perform_score=0
            exam.students.append(student)
        payload=build_session(exam,None,copy.deepcopy(original['ui_state']),copy.deepcopy(original['calculator_project']))
        restore(payload)
        window.btn_counsel_mode.setChecked(False)
        window.theme.set_mode('light');window.resize(1280,800)
        window.tabs.setCurrentWidget(window.tab_portfolio)
        window.le_portfolio_search.clear();window.refresh_portfolio_tab()
        key=next(iter(window._current_identity_by_hash()))
        selector=window.combo_portfolio_student
        selector.setCurrentIndex(selector.findData('hash:'+key))
        subject=window.combo_portfolio_subject
        subject.setCurrentIndex(subject.findData(exam.subject))
        view=window.portfolio_view
        view.history_toggle.setChecked(False)
        view.sync()
        assert view.selected_point and view.selected_point.get('source_kind')=='current', 'five-choice QA needs live fixture'
        source_before=copy.deepcopy(resolve_details(window,view.selected_point))
        raw_percentages=[value for row in source_before['tabs']['standards']['rows'] for value in row[2:] if isinstance(value,(int,float))]
        assert any(abs(value-round(value,2))>1e-8 for value in raw_percentages), 'fixture must include long fractional percentages'
        captures=[]
        for width,zoom in ((1280,100),(1280,120),(1148,100),(1148,120),(1055,100),(1055,120)):
            window.resize(width,800)
            window._set_zoom(zoom)
            view.tabs.setCurrentIndex(3)
            view.report_scroll.ensureWidgetVisible(view.tabs)
            QTest.qWait(180)
            table=view.tables['choice']
            table.horizontalScrollBar().setValue(0)
            name=f'portfolio-five-choice-{width}-{zoom}.png'
            assert window.grab().save(str(output/name));captures.append(name)
            fifth=next(c for c in range(table.columnCount()) if table.horizontalHeaderItem(c).text().replace('\n','')=='5번(%)')
            assert table.columnViewportPosition(fifth)+table.columnWidth(fifth)<=table.viewport().width(), f'5th choice clipped at width {width}, actual {window.width()}, zoom {zoom}: viewport {table.viewport().width()}, edge {table.columnViewportPosition(fifth)+table.columnWidth(fifth)}'
            minimum=table.fontMetrics().horizontalAdvance('100.00')+8
            assert all(table.columnWidth(c)>=minimum for c in range(4,10)), f'choice percentage columns too narrow at width {width}, zoom {zoom}'
            for r,row in enumerate(source_before['tabs']['choice']['rows']):
                for c,value in enumerate(row[4:],4):
                    expected='자료 없음' if value is None else f'{value:.2f}'
                    assert table.item(r,c).text()==expected and table.item(r,c).data(Qt.UserRole)==value, f'choice cell {r},{c} lost precision contract'
        check(REQUIRED_CHECKS[0],True)
        view.tabs.setCurrentIndex(4);QTest.qWait(100)
        table=view.tables['standards']
        for r,row in enumerate(source_before['tabs']['standards']['rows']):
            for c,value in enumerate(row[2:],2):
                expected='자료 없음' if value is None else f'{value:.2f}'
                assert table.item(r,c).data(Qt.UserRole)==value, f'raw percentage cell {r},{c} changed'
                assert table.item(r,c).text()==expected, f'standard percentage cell {r},{c} not two decimals'
        check(REQUIRED_CHECKS[1],resolve_details(window,view.selected_point)==source_before)
        assert window.grab().save(str(output/'portfolio-standard-precision.png'))
        report['portfolio_precision']={'captures':captures,'five_choices':True,'source_unchanged':True}
        restore(original)
        verify_batch(window,output,check,wait,report,capture,restore)
    finally:
        window._set_zoom(old_zoom);window.theme.set_mode(old_theme);window.resize(old_size)
        restore(original)
        after=capture()
        assert after['domain']==original['domain'] and after['calculator_project']==original['calculator_project'], 'precision QA changed original work'


def batch_fixtures(output):
    """Four rounds made only from the existing synthetic workbook generator."""
    from zipfile import ZipFile, ZIP_DEFLATED
    from .synthetic_qa import analysis_fixtures
    base=output/'batch-fixture-base';base.mkdir()
    item,responses,performance=analysis_fixtures(base)
    target=output/'four-round-input';target.mkdir()
    def copied(source,name,semester,annotated_subject=False):
        destination=target/name
        with ZipFile(source) as incoming, ZipFile(destination,'x',compression=ZIP_DEFLATED) as outgoing:
            for entry in incoming.infolist():
                data=incoming.read(entry.filename)
                if entry.filename.endswith('.xml'):
                    data=data.replace('1학기'.encode(),f'{semester}학기'.encode())
                    if annotated_subject:
                        data=data.replace('합성수학'.encode(),'합성수학(4)'.encode())
                outgoing.writestr(entry,data)
    for semester in (1,2):
        for number in (1,2):
            prefix=f'2026_{semester}학기_{number}차_1학년_(합성수학)'
            copied(item,prefix+'_문항정보표.xlsx',semester)
            for klass,source in enumerate(responses[number],1):
                copied(source,prefix.replace('(합성수학)','(합성수학(4))')+f'_정오표(1-{klass}).xlsx',semester,True)
        for klass,source in enumerate(performance,1):
            copied(source,f'2026_{semester}학기_1학년_(합성수학(4))_수행평가(1-{klass}).xlsx',semester,True)
    return target


def verify_batch(window,output,check,wait,report,capture,restore):
    import hashlib
    from PySide6.QtTest import QTest
    from .folder_batch import discover_round_groups
    from .work_sessions import WorkSessionStore
    folder=batch_fixtures(output)
    before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.iterdir()}
    groups=discover_round_groups(folder,window.cmb_round.currentText())
    assert len(groups)==4 and all(not group['problems'] for group in groups), 'four-round synthetic discovery failed'
    # Independent reference: the existing single-round Analyze action, not batch internals.
    from .data_loader import PATH_SEPARATOR
    baseline=capture()
    expected_scores=[]
    expected_subjects=[]
    baseline_weights=(window.spin_pencil_ratio.value(),window.spin_perform_ratio.value())
    try:
        for group in groups:
            window.fs_iteminfo.path_edit.setText(group['iteminfo'])
            window.fs_response.path_edit.setText(PATH_SEPARATOR.join(group['response']))
            window.fs_perform.path_edit.setText(PATH_SEPARATOR.join(group['perform']))
            window.fs_cuts.path_edit.setText(group['cuts'])
            window.cmb_round.setCurrentText(f"{group['key'][1]}학기 {group['key'][2]}차")
            window.chk_perform.setChecked(True)
            window.spin_pencil_ratio.setValue(baseline_weights[0])
            window.spin_perform_ratio.setValue(baseline_weights[1])
            window.run_analysis()
            assert window._detect_exam_round()==group['key'][:3], 'single-round reference used wrong exam'
            expected_scores.append(window.exam.students[0].final_score)
            expected_subjects.append(window.exam.subject)
    finally:
        restore(baseline)
    window.chk_perform.setChecked(True)
    assert window._analyze_folder_groups(groups), 'four-round native analysis failed'
    window.tabs.setCurrentWidget(window.tab_portfolio)
    window.le_portfolio_search.clear();window.refresh_portfolio_tab()
    student_key=next(iter(window._current_identity_by_hash()))
    window.combo_portfolio_student.setCurrentIndex(window.combo_portfolio_student.findData('hash:'+student_key))
    window.combo_portfolio_subject.setCurrentIndex(window.combo_portfolio_subject.findData(window.exam.subject))
    window.portfolio_view.sync();QTest.qWait(160)
    points=window.portfolio_growth_chart.points
    assert [(p['semester_no'],p['round_no']) for p in points]==[(1,1),(1,2),(2,1),(2,2)], 'batch timeline did not contain ordered four rounds'
    assert [p['score'] for p in points]==expected_scores, 'batch round scores differ from existing single-round analysis'
    assert [p['subject'] for p in points]==expected_subjects, 'batch rewrote loaded subject names'
    assert (window.exam.weight_pencil,window.exam.weight_perform)==baseline_weights, 'batch changed current weighting'
    check(BATCH_CHECKS[0],True)
    view=window.portfolio_view
    for index in range(4):
        view.round_combo.setCurrentIndex(index);QTest.qWait(60)
        from .portfolio_details import resolve_details
        details=resolve_details(window,view.selected_point)
        assert all(details['tabs'][key]['available'] for key in ('data','perform','items','choice','standards')), 'batch round missing exact details'
    assert window.grab().save(str(output/'portfolio-four-rounds.png'))
    payload=capture()
    store=WorkSessionStore(output/'batch-saved-work')
    path=store.save(payload);saved=path.read_bytes()
    window.le_portfolio_search.setText('different synthetic selection')
    restore(store.read(path))
    after=capture()
    check(BATCH_CHECKS[1],after['domain']==payload['domain']
          and after['ui_state']['portfolio_analysis_sessions']==payload['ui_state']['portfolio_analysis_sessions']
          and len(window.portfolio_growth_chart.points)==4 and path.read_bytes()==saved
          and before=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.iterdir()})
    report['four_round_batch']={'groups':4,'rounds':[(p['semester_no'],p['round_no']) for p in points],
                               'input_files_preserved':True,'reference_scores':expected_scores,'numeric_subject_annotation_fixture':True,'subjects_preserved':True,'weights':baseline_weights,'saved_work':str(path.relative_to(output))}


BATCH_CHECKS=(
    'folder batch analyzes four explicit rounds with exact scores and order',
    'four round detail data survives full work save and restore without changing inputs',
)
REQUIRED_CHECKS += BATCH_CHECKS
