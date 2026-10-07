"""Explicit candidate-only synthetic QA. Normal launch never imports this module.

Use --synthetic-qa <new output directory>. No user settings, input or AI service
is used; native UI, WebEngine and real project downloads run in an isolated root.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import tempfile
import time
from unittest.mock import patch

REQUIRED_CHECKS = (
    'settings are explicit isolated INI', 'portfolio is isolated',
    'WebEngine is off the record', 'bundled calculator renders',
    'synthetic file loads and preserves fractional business values',
    'real JSON download preserves business values', 'downloaded work reopens',
    'cancelled save creates no extra JSON', 'tab switch retains loaded work',
    'first calculator activation preserves the native window',
    'tab switches preserve the native window',
    'analysis tables contain both synthetic classes',
    'performance scores preserve expected combined values',
    'analysis and performance charts render',
    'semester and round are recognized from synthetic filenames',
    'second round analysis and comparison render',
    'synthetic analysis window capture exists',
    'no JavaScript or application dialog errors', 'core flow attempted no network',
    'native window capture exists',
    'analysis creates no unexpected chart windows',
    'portfolio current analysis preview is visible without automatic saving',
    'portfolio score column preserves combined scores and round labels',
    'portfolio explicit save removes preview and masks stored identities',
    'portfolio repeated save preserves every existing file',
    'portfolio links two subjects and filters selected student',
    'portfolio consultation report opens and captures',
    'portfolio records reload with isolated settings and recover names',
    'portfolio malformed file is preserved and diagnosed',
)


def project_fixture():
    rates = [(100,82.5,63.25,40,0),(100,80,60,40,20)]
    return {'version':1,'judges':[{'id':'j1','name':'합성 검토안 1'},{'id':'j2','name':'합성 검토안 2'}],
            'activeJudgeId':'j2','evidenceMode':'difficultyAverage','evidenceData':None,
            'items':[{'id':f'i{n}','number':n,'title':f'합성 선택형 {n}번','type':'선택형',
                      'difficulty':'보통','targetLevel':'C','points':points,'sampleSize':3,
                      'standard':'합성 성취기준','note':'합성 QA 전용','evidence':[],
                      'judgmentsByJudge':{judge:{lv:{'correct':[True,True,False],'targetRate':rate,'overrideRate':rate}
                                               for lv,rate in zip('ABCDE',values)} for judge in ('j1','j2')}}
                     for n,points,values in [(1,1.5,rates[0]),(2,3.25,rates[1])]]}


def business_values(project):
    keys=('id','number','type','points','targetLevel','judgmentsByJudge','standard','note')
    return {'judges':project['judges'],'activeJudgeId':project['activeJudgeId'],
            'items':[{k:item.get(k) for k in keys} for item in project['items']]}


def analysis_fixtures(inputs):
    """Write new, synthetic-only NEIS-style workbooks; never open user inputs."""
    from xml.etree.ElementTree import Element, SubElement, tostring
    from zipfile import ZipFile, ZIP_DEFLATED
    def write(name, rows):
        path = inputs / name
        if path.exists():
            raise FileExistsError(path)
        # Write a minimal workbook directly: no temporary-file cleanup/deletion.
        namespace = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
        sheet = Element('worksheet', xmlns=namespace)
        data = SubElement(sheet, 'sheetData')
        for row_number, values in enumerate(rows, 1):
            row = SubElement(data, 'row', r=str(row_number))
            for column, value in enumerate(values, 1):
                if value is None:
                    continue
                address = chr(64 + column) + str(row_number)
                cell = SubElement(row, 'c', r=address)
                if isinstance(value, (int, float)):
                    SubElement(cell, 'v').text = str(value)
                else:
                    cell.set('t', 'inlineStr')
                    SubElement(SubElement(cell, 'is'), 't').text = str(value)
        with ZipFile(path, 'x', compression=ZIP_DEFLATED) as archive:
            archive.writestr('[Content_Types].xml',
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                '<Default Extension="xml" ContentType="application/xml"/>'
                '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
            archive.writestr('_rels/.rels',
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
            archive.writestr('xl/workbook.xml',
                '<workbook xmlns="'+namespace+'" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                '<sheets><sheet name="합성" sheetId="1" r:id="rId1"/></sheets></workbook>')
            archive.writestr('xl/_rels/workbook.xml.rels',
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
            archive.writestr('xl/worksheets/sheet1.xml', tostring(sheet, encoding='utf-8', xml_declaration=True))
        return path
    item = write('합성_문항정보표.xlsx', [
        ['합성 검증 전용 (합성수학) 과목'], ['선택형 문항'],
        ['문항번호','내용영역','성취기준','난이도',None,None,'배점','정답'],
        [None,None,None,'어려움','보통','쉬움'],
        [1,'합성 연산','[합성-01] 합성 기준',None,None,'○',50,1],
        [2,'합성 연산','[합성-02] 합성 기준',None,'○',None,50,3]])
    responses, performance = {}, []
    for round_no in (1, 2):
        responses[round_no] = []
        for klass, students in ((1, [(1,'.','.',100),(2,'.','2',50)]),
                                (2, [(1,'4','.',50),(2,'.','.',100),(3,'4','2',0)])):
            if round_no == 2 and klass == 1:
                students = [(1,'.','2',50),(2,'.','.',100)]
            rows = [['합성 검증 전용'], [],
                    [f'2026학년도 1학기 {round_no}차 1학년 수학:합성수학'],
                    ['반/번호',None,'성명',1,2,'선택형점수','서답형점수','기타점수','과목총점'],
                    [None,None,'정답',1,3],[None,None,'배점',50,50]]
            for number, answer1, answer2, total in students:
                rows.append([f'2026{klass}{number:03d}',f'{klass}/{number}',f'합성{klass}{number}',
                             answer1,answer2,total,0,0,total])
            rows.append(['※ . : 맞음 , 번호 : 틀림 , 알파벳 : 복수답안코드 (합성 범례)'])
            responses[round_no].append(write(f'합성_2026_1학기_{round_no}차_정오표(1-{klass}).xlsx',rows))
    for klass, scores in ((1, [(1,40),(2,20)]), (2, [(1,10),(2,30),(3,0)])):
        rows = [['합성 검증 전용'],['교과목 : 합성수학'],
                ['반/번호','합성 학번','성명','합성 영역(만점 40.00,40.00%)','합 계']]
        for number, score in scores:
            rows.append([f'{klass}/{number}',f'2026{klass}{number:03d}',f'합성{klass}{number}',score,score])
        performance.append(write(f'합성_수행평가(1-{klass}).xlsx',rows))
    return item, responses, performance


def run(output):
    # This is the first application import, after isolated paths have been selected.
    state=output/'state';state.mkdir()
    for name in ('appdata','matplotlib','cache','tmp','codex'): (state/name).mkdir()
    os.environ.update(MPLCONFIGDIR=str(state/'matplotlib'),XDG_CACHE_HOME=str(state/'cache'),
                      GOEDUSPLIT_CODEX_WORKDIR=str(state/'codex'))
    from PySide6.QtCore import QPoint, QSettings, Qt, QCoreApplication, QEvent, QObject, QTimer
    from PySide6.QtTest import QTest
    from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineUrlRequestInterceptor
    from PySide6.QtWidgets import QApplication, QTextBrowser
    import app.main_window as ui
    from app import __version__
    report={'version':__version__,'frozen':bool(getattr(sys,'frozen',False)),
            'os':platform.system(),'architecture':platform.machine(),'input':'synthetic only',
            'checks':{},'errors':[],'status':'incomplete'}
    if report['frozen']:
        with Path(sys.executable).open('rb') as binary:
            report['executable_sha256']=hashlib.file_digest(binary,'sha256').hexdigest()
    inputs=output/'inputs';inputs.mkdir()
    work=inputs/'합성 작업.json';work.write_text(json.dumps(project_fixture(),ensure_ascii=False),encoding='utf-8')
    saved=output/'합성 저장.json'
    analysis_item, analysis_responses, analysis_performance = analysis_fixtures(inputs)
    chosen=[str(work)]
    save_dest=[str(saved)]
    blocked=[]
    application=QApplication.instance() or QApplication([])
    profile=QWebEngineProfile(application)
    profile.setHttpCacheType(QWebEngineProfile.MemoryHttpCache)
    profile.setPersistentCookiesPolicy(QWebEngineProfile.NoPersistentCookies)
    profile.setCachePath(str(state/'cache'))
    profile.setPersistentStoragePath(str(state/'cache'))

    class LocalOnly(QWebEngineUrlRequestInterceptor):
        def interceptRequest(self, info):
            if info.requestUrl().scheme().lower() not in {'file','qrc','data','blob','about'}:
                blocked.append(info.requestUrl().scheme())
                info.block(True)
    interceptor=LocalOnly(profile);profile.setUrlRequestInterceptor(interceptor)

    class Page(QWebEnginePage):
        def chooseFiles(self, mode, old, accepted): return chosen
        def javaScriptAlert(self, origin, message): report['errors'].append('JavaScript alert: '+message)
        def javaScriptConsoleMessage(self, level, message, line, source):
            if 'rror' in message: report['errors'].append('JavaScript: '+message)

    settings=QSettings(str(state/'settings.ini'),QSettings.IniFormat);settings.setFallbacksEnabled(False)
    def wait(predicate, seconds=20):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            if predicate(): return
            QTest.qWait(50)
        raise TimeoutError('Synthetic candidate operation timed out')
    def js(window, expression):
        replies=[]
        window.spliter_view.page().runJavaScript('JSON.stringify('+expression+')',replies.append)
        wait(lambda:bool(replies),10)
        return json.loads(replies[0]) if replies[0] else None
    def click(window, title):
        point=js(window,'(() => { const el=document.querySelector('+json.dumps('button.goedu-file-action[title="'+title+'"]')+'); if(!el)return null; const r=el.getBoundingClientRect();return [r.x+r.width/2,r.y+r.height/2];})()')
        if not point: raise AssertionError('Missing calculator button: '+title)
        target=window.spliter_view.focusProxy() or window.spliter_view;target.setFocus()
        QTest.mouseClick(target,Qt.LeftButton,pos=QPoint(round(point[0]),round(point[1])))
    def check(name, condition):
        report['checks'][name]=bool(condition)
        if not condition: raise AssertionError(name)
    window=None
    destroyed_surfaces=[]
    unexpected_chart_windows=[]
    class ChartWindowWatch(QObject):
        def eventFilter(self, obj, event):
            if event.type()==QEvent.Show and type(obj).__name__=="_MarginKeepingCanvas" and obj.isWindow():
                unexpected_chart_windows.append({"width":obj.width(),"height":obj.height()})
            return False
    chart_watcher=ChartWindowWatch();application.installEventFilter(chart_watcher)
    class SurfaceWatch(QObject):
        def eventFilter(self, obj, event):
            if event.type() == QEvent.PlatformSurface and event.surfaceEventType().name == 'SurfaceAboutToBeDestroyed':
                destroyed_surfaces.append(obj.surfaceType().name)
            return False
    with patch.object(tempfile,'tempdir',str(state/'tmp')), \
         patch.object(ui,'QSettings',return_value=settings), \
         patch.object(ui.MainWindow,'_ai_material_root_dir',lambda _self:state/'appdata'), \
         patch.object(ui,'QWebEnginePage',side_effect=lambda parent:Page(profile,parent)), \
         patch.object(ui.QFileDialog,'getSaveFileName',side_effect=lambda *a,**k:(save_dest[0],'')), \
         patch('app.ai_client._codex_cli_path_from_config',return_value=''), \
         patch('urllib.request.urlopen',side_effect=AssertionError('Network forbidden during candidate QA')), \
         patch.object(ui.QMessageBox,'warning',side_effect=lambda *a,**k:report['errors'].append('warning: '+str(a[2]))), \
         patch.object(ui.QMessageBox,'critical',side_effect=lambda *a,**k:report['errors'].append('critical: '+str(a[2]))):
        try:
            window=ui.MainWindow();window.resize(1280,800);window.show()
            QTest.qWait(500)
            initial_window_id=int(window.winId())
            watcher=SurfaceWatch()
            window.windowHandle().installEventFilter(watcher)
            report['native_window']={'platform':application.platformName(),'initial_id':initial_window_id,
                                     'initial_surface':window.windowHandle().surfaceType().name}
            check('settings are explicit isolated INI',window.settings is settings and not settings.fallbacksEnabled())
            check('portfolio is isolated',window._portfolio_store_dir().is_relative_to(state/'appdata'))
            check('WebEngine is off the record',profile.isOffTheRecord())
            window.tabs.setCurrentWidget(window.tab_spliter)
            wait(lambda:window._spliter_loaded,30);QTest.qWait(1500)
            check('first calculator activation preserves the native window',
                  not destroyed_surfaces and int(window.winId())==initial_window_id)
            check('bundled calculator renders',js(window,'Boolean(document.querySelector(".item-table"))'))
            click(window,'작업 불러오기');QTest.qWait(1800)
            loaded=js(window,'window.__GOEDUSPLIT_GET_PROJECT__()')
            check('synthetic file loads and preserves fractional business values',business_values(loaded)==business_values(project_fixture()))
            click(window,'작업 저장');wait(lambda:saved.is_file());QTest.qWait(600)
            persisted=json.loads(saved.read_text(encoding='utf-8'))
            check('real JSON download preserves business values',business_values(persisted)==business_values(project_fixture()))
            different=copy.deepcopy(project_fixture())
            different['items'][0]['points']=6.25
            different_work=inputs/'별도 합성 작업.json'
            different_work.write_text(json.dumps(different,ensure_ascii=False),encoding='utf-8')
            chosen[:]=[str(different_work)];click(window,'작업 불러오기');QTest.qWait(1600)
            was_different=business_values(js(window,'window.__GOEDUSPLIT_GET_PROJECT__()'))==business_values(different)
            chosen[:]=[str(saved)];click(window,'작업 불러오기');QTest.qWait(1600)
            reloaded=js(window,'window.__GOEDUSPLIT_GET_PROJECT__()')
            check('downloaded work reopens',was_different and business_values(reloaded)==business_values(persisted))
            saved_before_cancel=saved.read_bytes();input_before_cancel=work.read_bytes()
            save_dest[0]='';click(window,'작업 저장');QTest.qWait(700)
            check('cancelled save creates no extra JSON',sorted(p.name for p in output.glob('*.json'))==[saved.name]
                  and saved.read_bytes()==saved_before_cancel and work.read_bytes()==input_before_cancel)
            window.tabs.setCurrentWidget(window.tab_data);QTest.qWait(500)
            window.tabs.setCurrentWidget(window.tab_spliter);QTest.qWait(500)
            check('tab switch retains loaded work',business_values(js(window,'window.__GOEDUSPLIT_GET_PROJECT__()'))==business_values(persisted))
            check('tab switches preserve the native window',not destroyed_surfaces and int(window.winId())==initial_window_id)
            window.tabs.setCurrentWidget(window.tab_data)
            window.fs_iteminfo.path_edit.setText(str(analysis_item))
            window.fs_response.path_edit.setText(ui.PATH_SEPARATOR.join(map(str,analysis_responses[1])))
            window.fs_perform.path_edit.setText(ui.PATH_SEPARATOR.join(map(str,analysis_performance)))
            window.chk_perform.setChecked(True)
            window.spin_pencil_ratio.setValue(60)
            window.spin_perform_ratio.setValue(40)
            window.run_analysis();QTest.qWait(500)
            check('analysis tables contain both synthetic classes',window.table_data.rowCount()==5
                  and window.table_items.rowCount()==2 and set(window.overall.by_class)=={'1','2'})
            combined=[float(student.final_score) for student in window.exam.students]
            check('performance scores preserve expected combined values',combined==[100.0,50.0,40.0,90.0,0.0]
                  and window.table_perform_students.rowCount()==5 and window.table_perform_areas.rowCount()==1)
            # Exercise the actual portfolio UI and file roundtrip, not just its directory.
            store = window._portfolio_store_dir()
            window.tabs.setCurrentWidget(window.tab_portfolio);QTest.qWait(150)
            check('portfolio current analysis preview is visible without automatic saving',
                  window.table_portfolio.rowCount()==5 and window.btn_portfolio_save.isEnabled()
                  and window._portfolio_has_preview and not list(store.glob('*.json')))
            check('portfolio score column preserves combined scores and round labels',
                  window.table_portfolio.horizontalHeaderItem(8).text()=='환산점수'
                  and sorted(float(window.table_portfolio.item(r,8).text()) for r in range(5))==sorted(combined)
                  and all('1차' in row['term'] for row in window._portfolio_rows_cache))
            window.btn_portfolio_save.click();QTest.qWait(100)
            first_files={path.name:path.read_bytes() for path in store.glob('*.json')}
            stored_text=next(iter(first_files.values())).decode('utf-8')
            check('portfolio explicit save removes preview and masks stored identities',
                  len(first_files)==1 and window.table_portfolio.rowCount()==5
                  and not window._portfolio_has_preview
                  and all(student.name not in stored_text and student.sid not in stored_text
                          for student in window.exam.students))
            window.btn_portfolio_save.click();QTest.qWait(100)
            check('portfolio repeated save preserves every existing file',
                  len(list(store.glob('*.json')))==2 and window.table_portfolio.rowCount()==10
                  and all((store/name).read_bytes()==data for name,data in first_files.items()))
            original_subject=window.exam.subject
            window.exam.subject='합성영어';window.refresh_portfolio_tab()
            window.btn_portfolio_save.click();QTest.qWait(100)
            window.combo_portfolio_student.setCurrentIndex(1)
            selected_key=window.combo_portfolio_student.currentData()
            selected=window._portfolio_rows_for_key(selected_key)
            visible=sum(not window.table_portfolio.isRowHidden(r) for r in range(window.table_portfolio.rowCount()))
            check('portfolio links two subjects and filters selected student',
                  len(selected)==3 and visible==3 and {row['subject'] for row in selected}=={original_subject,'합성영어'})
            captured=[]
            def capture_report():
                dialog=application.activeModalWidget()
                if dialog and dialog.windowTitle()=='학생 포트폴리오 상담 리포트':
                    browsers=dialog.findChildren(QTextBrowser)
                    text=browsers[0].toPlainText() if browsers else ''
                    captured.append(original_subject in text and '합성영어' in text
                                    and dialog.grab().save(str(output/'portfolio-report.png')))
                    dialog.accept()
            QTimer.singleShot(250,capture_report)
            window.show_selected_student_portfolio()
            check('portfolio consultation report opens and captures',captured==[True])
            retained={path.name:path.read_bytes() for path in store.glob('*.json')}
            current_exam,current_overall=window.exam,window.overall
            settings.sync()
            reloaded_settings=QSettings(settings.fileName(),QSettings.IniFormat)
            reloaded_settings.setFallbacksEnabled(False)
            original_hash=settings.value('privacy/portfolio_hash_key')
            window.settings=reloaded_settings;window.exam=None;window.overall=None
            window.refresh_portfolio_tab()
            anonymous=window.table_portfolio.rowCount()==15 and all(
                row['name'].startswith('학생#') for row in window._portfolio_rows_cache)
            window.exam,window.overall=current_exam,current_overall
            window.refresh_portfolio_tab()
            restored=window._portfolio_rows_for_key(selected_key)
            check('portfolio records reload with isolated settings and recover names',
                  anonymous and reloaded_settings.value('privacy/portfolio_hash_key')==original_hash
                  and len(restored)==3 and visible==sum(not window.table_portfolio.isRowHidden(r)
                      for r in range(window.table_portfolio.rowCount()))
                  and all(not row['name'].startswith('학생#') for row in restored)
                  and all((store/name).read_bytes()==data for name,data in retained.items()))
            malformed=store/'synthetic-malformed.json';malformed.write_text('{}',encoding='utf-8')
            window.refresh_portfolio_tab()
            check('portfolio malformed file is preserved and diagnosed',
                  window.table_portfolio.rowCount()==15 and len(window._portfolio_load_errors)==1
                  and '읽지 못한 저장 파일 1개' in window.lbl_portfolio_note.text()
                  and malformed.read_text(encoding='utf-8')=='{}'
                  and window.grab().save(str(output/'portfolio-window.png')))
            report['portfolio']={'saved_files':len(retained),'records':15,'selected_student_records':3,
                                 'subjects':2,'stored_identity':'keyed hashes only','malformed_files_preserved':1}
            window.exam.subject=original_subject
            window.combo_portfolio_student.setCurrentIndex(0)
            window.refresh_portfolio_tab()
            window.tabs.setCurrentWidget(window.tab_data)
            chart_names=('canvas_score_hist','canvas_score_normal','canvas_level_stack','canvas_level_means',
                         'canvas_class','canvas_pvalue','canvas_discr','canvas_monitor','canvas_monitor_trend',
                         'canvas_perform_area','canvas_perform_scatter')
            charts_dir=output/'charts';charts_dir.mkdir()
            chart_files=[]
            for name in chart_names:
                canvas=getattr(window,name)._canvas
                if canvas is None or not canvas.figure.axes:
                    raise AssertionError('Missing rendered analysis chart: '+name)
                canvas.draw()
                path=charts_dir/(name+'.png');canvas.figure.savefig(path)
                if not path.is_file() or path.stat().st_size<1000:
                    raise AssertionError('Empty chart image: '+name)
                chart_files.append(path.name)
            check('analysis and performance charts render',len(chart_files)==len(chart_names))
            check('semester and round are recognized from synthetic filenames',window._detect_exam_round()==(2026,1,1))
            check('synthetic analysis window capture exists',window.grab().save(str(output/'analysis-window.png')))
            window.fs_response.path_edit.setText(ui.PATH_SEPARATOR.join(map(str,analysis_responses[2])))
            window.run_analysis();QTest.qWait(500)
            check('second round analysis and comparison render',window._detect_exam_round()==(2026,1,2)
                  and len(window._round_records)==2 and window.table_round_metrics.rowCount()>0
                  and window.canvas_round_compare._canvas is not None)
            window.canvas_round_compare._canvas.figure.savefig(charts_dir/'round-comparison.png')
            report['analysis']={'students':5,'classes':2,'items':2,'combined_scores_first_round':combined,
                                'chart_files':chart_files+['round-comparison.png'],'rounds':len(window._round_records)}
            report['unexpected_chart_windows']=unexpected_chart_windows
            check('analysis creates no unexpected chart windows',not unexpected_chart_windows)
            report['native_window'].update(final_id=int(window.winId()),destroyed_before_close=list(destroyed_surfaces))
            check('no JavaScript or application dialog errors',not report['errors'])
            check('core flow attempted no network',not blocked)
            check('native window capture exists',window.grab().save(str(output/'candidate-window.png')))
            report['status']='passed'
        except Exception as error:
            report['errors'].append(type(error).__name__+': '+str(error));report['status']='failed'
            if window: window.grab().save(str(output/'candidate-failure.png'))
        finally:
            application.removeEventFilter(chart_watcher)
            if window:
                window.close();QTest.qWait(1300);window.deleteLater()
                QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete);application.processEvents()
            profile.deleteLater()
            QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete);application.processEvents()
            settings.sync()
            # Complete report is durable; this explicit QA root is never user appdata.
            (output/'QA_REPORT.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    for name, passed in report['checks'].items(): print(('passed: ' if passed else 'FAILED: ')+name,flush=True)
    print('Synthetic candidate QA: '+report['status'],flush=True)
    return 0 if report['status']=='passed' else 1


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--synthetic-qa',type=Path,required=True,help='New directory for synthetic QA only')
    args=parser.parse_args()
    output=args.synthetic_qa.expanduser().resolve()
    output.mkdir(parents=True,exist_ok=False)
    return run(output)
