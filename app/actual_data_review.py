"""Read-only real-input review with isolated Qt UI and explicit executable identity.

No screenshots or raw diagnostic output. New work copies stay in a private
0700 temporary root. Default is discovery/dialog review only; --analyze enables
validated groups. Missing or ambiguous item files are never auto-connected.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import sys
import tempfile
import unicodedata
from contextlib import ExitStack
from unittest.mock import patch


def resolve_folder(value):
    requested=Path(value).expanduser().absolute()
    if requested.is_dir():return requested.resolve()
    cursor=Path(requested.anchor)
    for part in requested.parts[1:]:
        matches=[p for p in cursor.iterdir() if unicodedata.normalize('NFC',p.name)==unicodedata.normalize('NFC',part)]
        if len(matches)!=1:raise ValueError('folder resolution failed')
        cursor=matches[0]
    if not cursor.is_dir():raise ValueError('not a directory')
    return cursor.resolve()


def fingerprint(folder):
    result={}
    for path in sorted(folder.rglob('*')):
        if path.is_symlink():raise ValueError('linked input excluded')
        if path.is_file():
            with path.open('rb') as stream:result[str(path.relative_to(folder))]=hashlib.file_digest(stream,'sha256').hexdigest()
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-folder',required=True)
    parser.add_argument('--analyze',action='store_true')
    parser.add_argument('--first-only',action='store_true')
    parser.add_argument('--native',action='store_true')
    parser.add_argument('--item-round',choices=['1학기 1차','1학기 2차'])
    args=parser.parse_args()
    root=Path(tempfile.mkdtemp(prefix='goedusplit-private-review-',dir='/private/tmp'));root.chmod(0o700)
    result={'checks':{'source_qt_isolated':not bool(getattr(sys,'frozen',False)),'installed_app_test':bool(getattr(sys,'frozen',False)) and str(Path(sys.executable).resolve()).startswith('/Applications/Goedu-Split.app/'),'screenshots_created':False},'counts':{},'rounds':[]}
    report=root/'RESULT.json'
    # Suppress Python and native-library diagnostics: exception text can contain
    # input cell values or sensitive paths. Only the aggregate JSON is retained.
    stdout=os.dup(1);stderr=os.dup(2)
    null=os.open(os.devnull,os.O_WRONLY);os.dup2(null,1);os.dup2(null,2);os.close(null)
    original=None;folder=None;window=None;application=None
    try:
        folder=resolve_folder(args.input_folder);original=fingerprint(folder)
        result['counts']['input_files']=len(original)
        for name in ('appdata','cache','matplotlib','codex','tmp','profile'):(root/name).mkdir(mode=0o700)
        os.environ.update(MPLCONFIGDIR=str(root/'matplotlib'),XDG_CACHE_HOME=str(root/'cache'),GOEDUSPLIT_CODEX_WORKDIR=str(root/'codex'),TMPDIR=str(root/'tmp'))
        if not args.native:os.environ['QT_QPA_PLATFORM']='offscreen'
        from PySide6.QtCore import Qt,QSettings,QPoint,QTimer
        from PySide6.QtWidgets import QApplication,QPushButton
        from PySide6.QtTest import QTest
        from PySide6.QtWebEngineCore import QWebEngineProfile,QWebEnginePage,QWebEngineUrlRequestInterceptor
        import app.main_window as ui
        from app.theme import ThemeManager
        from app.folder_batch import discover_round_groups
        from app.analysis_preparation import AnalysisPreparationDialog,score_text
        from app.perform_loader import load_perform_many
        from app.data_loader import PATH_SEPARATOR
        from app.cuts_loader import load_cut_scores
        from app.folder_batch import _metadata,_evidence_matches,subjects_compatible
        from app.grade_cut_calculator import load_grade5_cut_reports
        from app.work_session_ui import capture_ui_state,apply_python_state
        from app.work_sessions import build_session,prepare_session,WorkSessionStore,encode_domain
        application=QApplication([])
        profile=QWebEngineProfile(application)
        profile.setPersistentCookiesPolicy(QWebEngineProfile.NoPersistentCookies)
        profile.setCachePath(str(root/'profile'))
        class LocalOnly(QWebEngineUrlRequestInterceptor):
            def interceptRequest(self,info):
                if info.requestUrl().scheme() not in ('file','qrc','data','blob','about'):info.block(True)
        interceptor=LocalOnly(profile);profile.setUrlRequestInterceptor(interceptor)
        def settings_factory(*_a,**_k):
            settings=QSettings(str(root/'settings.ini'),QSettings.IniFormat);settings.setFallbacksEnabled(False);return settings
        warning_count=[0]
        def silent_warning(*_a,**_k):warning_count[0]+=1;return 0
        with ExitStack() as scope:
            scope.enter_context(patch.object(ui,'QSettings',side_effect=settings_factory))
            scope.enter_context(patch.object(ui.MainWindow,'_ai_material_root_dir',lambda _w:root/'appdata'))
            scope.enter_context(patch.object(ui,'QWebEnginePage',side_effect=lambda parent:QWebEnginePage(profile,parent)))
            scope.enter_context(patch.object(tempfile,'tempdir',str(root/'tmp')))
            scope.enter_context(patch('app.ai_client._codex_cli_path_from_config',return_value=''))
            import socket
            scope.enter_context(patch.object(socket.socket,'connect',side_effect=PermissionError('network disabled')))
            scope.enter_context(patch.object(socket.socket,'connect_ex',side_effect=PermissionError('network disabled')))
            scope.enter_context(patch.object(ui.QMessageBox,'warning',side_effect=silent_warning))
            scope.enter_context(patch.object(ui.QMessageBox,'critical',side_effect=silent_warning))
            theme=ThemeManager(application);theme.set_mode('light')
            window=ui.MainWindow(theme_manager=theme);window.resize(1280,900);window.show()
            window.btn_counsel_mode.setChecked(True)
            input_folder=folder
            if args.first_only:
                candidates=discover_round_groups(folder,'1학기 1차')
                chosen=[g for g in candidates if g['key'][1:3]==(1,1)]
                assert len(chosen)==1
                g=chosen[0]; selected=set(g['response']+g['perform'])
                selected.update(g[k] for k in ('iteminfo','cuts','grade5_report') if g[k])
                if not g['iteminfo'] and args.item_round=='1학기 1차':
                    assert len(g['item_candidates'])==1
                    selected.add(g['item_candidates'][0])
                input_folder=root/'first-only-input';input_folder.mkdir(mode=0o700)
                for source in selected:
                    source=Path(source);target=input_folder/source.name
                    target.write_bytes(source.read_bytes());target.chmod(0o600)
                result['counts']['first_only_input_files']=len(selected)
                verified=discover_round_groups(input_folder,'1학기 1차')
                result['checks']['only_first_round_in_input']=len(verified)==1 and verified[0]['key'][1:3]==(1,1)
                assert result['checks']['only_first_round_in_input']
            workspace=window.folder_workspace;workspace.register(input_folder);workspace.add_favorite();window.settings.sync()
            fresh=ui.MainWindow(theme_manager=theme)
            result['checks']['favorite_reopened_from_disk']=str(input_folder) in fresh.folder_workspace.favorites
            fresh.close();fresh.deleteLater()
            groups=discover_round_groups(input_folder,window.cmb_round.currentText())
            result['counts']['discovered_groups']=len(groups)
            dialog=AnalysisPreparationDialog(window,groups)
            baseline=capture_ui_state(window)
            eligible=[]
            def inspect_dialog():
                try:
                    for index,(group,page) in enumerate(zip(groups,dialog.pages)):
                        dialog.tabs.setCurrentIndex(index)
                        sem,number=group['key'][1:3]
                        label=f'{sem}학기 {number}차' if sem in (1,2) and number in (1,2) else '회차 미확인'
                        combo=page.combos['iteminfo']
                        if args.item_round==label and not combo.currentData():
                            assert combo.count()==2
                            combo.setCurrentIndex(1)
                        page.refresh()
                        complete=not page.error
                        checks={'item_assigned':bool(combo.currentData()),'ready':complete,
                                'partial_without_items':not bool(combo.currentData())}
                        cuts=load_cut_scores(group['cuts'])[0] if group['cuts'] else page.current_cuts
                        checks['cut_values_displayed']=score_text(cuts) in page.cuts_label.text()
                        if page.calculate.isEnabled():
                            QTest.mouseClick(page.calculate,Qt.LeftButton)
                            checks['grade_cuts_calculated']=bool(page.reports)
                            if not page.reports:
                                page.calculate.click()
                                checks['grade_cuts_via_signal']=bool(page.reports)
                                path=page.combos['grade5_report'].currentData()
                                evidence=_metadata(Path(path))
                                expected=dict(zip(('학년도','학기','차수','학년','과목'),group['key']))
                                checks['grade_metadata_matches']=all(len(evidence[field])<=1 and _evidence_matches(field,value,evidence[field]) for field,value in expected.items())
                                try:
                                    reports=load_grade5_cut_reports(path)
                                    checks['grade_report_readable']=True
                                    checks['grade_unique_subject']=sum(not group['key'][4] or subjects_compatible(group['key'][4],r['subject']) for r in reports)==1
                                except Exception as exc:
                                    checks['grade_report_readable']=False
                                    result['grade_error_type']=type(exc).__name__
                        if group['perform']:
                            ratio=float(load_perform_many(PATH_SEPARATOR.join(group['perform'])).ratio_total)
                            checks['file_perform_ratio_applied']=page.file_weights.isChecked() and abs(page.pencil.value()-(100-ratio))<0.01
                        result['rounds'].append({'label':label,'checks':checks,'counts':{'response_files':len(group['response']),'perform_files':len(group['perform'])}})
                        if complete:eligible.append(page.selected())
                    result['checks']['dialog_inspected']=True
                    cancel=next(b for b in dialog.findChildren(QPushButton) if b.text()=='취소')
                    QTest.mouseClick(cancel,Qt.LeftButton)
                except Exception as exc:
                    result['checks']['dialog_inspected']=False
                    result['error_type']=type(exc).__name__
                finally:
                    dialog.reject()
            QTimer.singleShot(100,inspect_dialog);dialog.exec()
            result['checks']['popup_cancel_preserved_inputs']=capture_ui_state(window)==baseline
            dialog.deleteLater()
            result['counts']['ready_groups']=len(eligible)
            result['counts']['withheld_groups']=len(groups)-len(eligible)
            result['counts']['analyzed_groups']=0
            if args.analyze and eligible:
                def accept_actual_dialog():
                    actual=application.activeModalWidget()
                    try:
                        assert isinstance(actual,AnalysisPreparationDialog)
                        if args.first_only:assert len(actual.pages)==1
                        for page in actual.pages:
                            combo=page.combos['iteminfo']
                            label=f"{page.group['key'][1]}학기 {page.group['key'][2]}차"
                            if args.item_round==label and not combo.currentData() and combo.count()==2:
                                combo.setCurrentIndex(1)
                            page.refresh()
                            assert not page.error
                        button=next(b for b in actual.findChildren(QPushButton) if '선택' in b.text() and '분석' in b.text())
                        QTest.mouseClick(button,Qt.LeftButton)
                        result['checks']['analysis_button_accepted']=actual.result()==1
                    except Exception as exc:
                        result['button_error_type']=type(exc).__name__
                        result['checks']['analysis_button_accepted']=False
                        if actual:actual.reject()
                QTimer.singleShot(150,accept_actual_dialog)
                QTest.mouseClick(workspace.analyze,Qt.LeftButton);QTest.qWait(150)
                ok=window.exam is not None and result['checks'].get('analysis_button_accepted',False)
                result['checks']['valid_groups_analysis']=bool(ok)
                if ok:
                    result['counts']['analyzed_groups']=len(eligible)
                    result['counts']['students']=len(window.exam.students)
                    result['checks']['all_result_tabs_open']=True
                    for index in range(window.tabs.count()):
                        window.tabs.setCurrentIndex(index);QTest.qWait(40)
                    result['checks']['data_rows_present']=window.table_data.rowCount()>0
                    if window.exam.items:
                        result['checks']['item_response_standard_rows_present']=all(t.rowCount()>0 for t in (window.table_items,window.table_choice,window.table_std))
                    else:
                        result['checks']['missing_item_tables_empty']=all(t.rowCount()==0 for t in (window.table_items,window.table_choice,window.table_std))
                    result['checks']['analyzed_round_is_first']=not args.first_only or window.exam.source_files.get('responses','') and all('1차' in unicodedata.normalize('NFC',Path(p).name) for p in window.exam.source_files['responses'].split(PATH_SEPARATOR))
                    window.tabs.setCurrentWidget(window.tab_data);QTest.qWait(150)
                    table=window.table_data;header=table.horizontalHeader();viewport=header.viewport();column=2
                    point=QPoint(header.sectionViewportPosition(column)+header.sectionSize(column)-1,header.height()//2)
                    width=table.columnWidth(column)
                    QTest.mousePress(viewport,Qt.LeftButton,pos=point);QTest.mouseMove(viewport,point+QPoint(35,0),40);QTest.mouseRelease(viewport,Qt.LeftButton,pos=point+QPoint(35,0));QTest.qWait(100)
                    dragged=table.columnWidth(column);result['checks']['data_header_drag']=dragged>width
                    domain=encode_domain(window.exam,window.perform_data)
                    store=WorkSessionStore(root/'saved-work');saved=store.save(build_session(window.exam,window.perform_data,capture_ui_state(window),None))
                    saved.chmod(0o600)
                    fresh=ui.MainWindow(theme_manager=theme);fresh.btn_counsel_mode.setChecked(True)
                    apply_python_state(fresh,prepare_session(store.read(saved)));QTest.qWait(150)
                    result['checks']['fresh_restore_domain']=encode_domain(fresh.exam,fresh.perform_data)==domain
                    result['checks']['fresh_restore_width']=fresh.table_data.columnWidth(column)==dragged
                    reopened=AnalysisPreparationDialog(fresh,discover_round_groups(input_folder,'1학기 1차'))
                    restored=reopened.pages[0].selected()
                    result['checks']['preparation_saved_item_restored']=restored['iteminfo']==window.exam.source_files.get('item_info','') and bool(restored['iteminfo'])
                    result['checks']['preparation_saved_weights_restored']=abs(restored['pencil_weight']-window.exam.weight_pencil)<0.01
                    reopened.reject();reopened.deleteLater()
                    fresh.close();fresh.deleteLater()
            result['counts']['application_warnings']=warning_count[0]
            result['checks']['runner_completed']=True
            window.close();window.deleteLater();window=None
            application.processEvents()
    except Exception as exc:
        result['error_type']=type(exc).__name__
        result['checks']['runner_completed']=False
    finally:
        if folder is not None and original is not None:
            try:result['checks']['input_files_unchanged']=fingerprint(folder)==original
            except Exception:result['checks']['input_files_unchanged']=False
        if window is not None:window.close()
        report.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');report.chmod(0o600)
        os.dup2(stdout,1);os.dup2(stderr,2);os.close(stdout);os.close(stderr)
    required=['runner_completed','input_files_unchanged','favorite_reopened_from_disk','popup_cancel_preserved_inputs','dialog_inspected']
    if args.analyze and result['counts'].get('ready_groups'):
        required+=['analysis_button_accepted','all_result_tabs_open','data_rows_present','analyzed_round_is_first','valid_groups_analysis','data_header_drag','fresh_restore_domain','fresh_restore_width','preparation_saved_item_restored','preparation_saved_weights_restored']
    if args.first_only:required+=['only_first_round_in_input']
    if 'item_response_standard_rows_present' in result['checks']:required+=['item_response_standard_rows_present']
    if 'missing_item_tables_empty' in result['checks']:required+=['missing_item_tables_empty']
    passed=all(result['checks'].get(key) is True for key in required)
    from app import __version__
    result['version']=__version__
    result['executable']=str(Path(sys.executable).resolve())
    result['executable_sha256']=hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest()
    passed=passed and all(row['checks'].get(key,True) for row in result['rounds'] for key in ('cut_values_displayed','grade_cuts_calculated','file_perform_ratio_applied'))
    result['checks']['requested_checks_passed']=passed
    report.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');report.chmod(0o600)
    print(str(report))
    print(json.dumps(result,ensure_ascii=False))
    return 0 if passed else 1

if __name__=='__main__':raise SystemExit(main())
