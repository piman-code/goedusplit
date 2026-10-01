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
    'no JavaScript or native warnings', 'core flow attempted no network',
    'native window capture exists',
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


def run(output):
    # This is the first application import, after isolated paths have been selected.
    state=output/'state';state.mkdir()
    for name in ('appdata','matplotlib','cache','tmp','codex'): (state/name).mkdir()
    os.environ.update(MPLCONFIGDIR=str(state/'matplotlib'),XDG_CACHE_HOME=str(state/'cache'),
                      GOEDUSPLIT_CODEX_WORKDIR=str(state/'codex'))
    from PySide6.QtCore import QPoint, QSettings, Qt, QCoreApplication, QEvent
    from PySide6.QtTest import QTest
    from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineUrlRequestInterceptor
    from PySide6.QtWidgets import QApplication
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
            check('settings are explicit isolated INI',window.settings is settings and not settings.fallbacksEnabled())
            check('portfolio is isolated',window._portfolio_store_dir().is_relative_to(state/'appdata'))
            check('WebEngine is off the record',profile.isOffTheRecord())
            window.tabs.setCurrentWidget(window.tab_spliter)
            wait(lambda:window._spliter_loaded,30);QTest.qWait(1500)
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
            check('no JavaScript or native warnings',not report['errors'])
            check('core flow attempted no network',not blocked)
            check('native window capture exists',window.grab().save(str(output/'candidate-window.png')))
            report['status']='passed'
        except Exception as error:
            report['errors'].append(type(error).__name__+': '+str(error));report['status']='failed'
            if window: window.grab().save(str(output/'candidate-failure.png'))
        finally:
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
