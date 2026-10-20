"""Interactive native workspace preview with isolated synthetic input and settings."""
import argparse
from contextlib import ExitStack
import hashlib
import json
import os
import sys
from pathlib import Path
import tempfile
from unittest.mock import patch


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--capture-only',action='store_true');parser.add_argument('--theme',choices=['light','dark'],default='light');parser.add_argument('--show-preparation',action='store_true');args=parser.parse_args()
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    for name in ('state','tmp','cache','matplotlib','codex'):(out/name).mkdir()
    os.environ.update(MPLCONFIGDIR=str(out/'matplotlib'),XDG_CACHE_HOME=str(out/'cache'),GOEDUSPLIT_CODEX_WORKDIR=str(out/'codex'))
    from PySide6.QtCore import QSettings,QTimer,Qt,QMimeData,QUrl,QPoint,QPointF
    from PySide6.QtGui import QDragEnterEvent,QDropEvent
    from PySide6.QtWidgets import QApplication
    from PySide6.QtWebEngineCore import QWebEngineProfile,QWebEnginePage,QWebEngineUrlRequestInterceptor
    from PySide6.QtTest import QTest
    from . import __version__
    from . import main_window as ui
    from .theme import ThemeManager
    from .batch_ui_qa import batch_fixtures
    from .work_session_ui import capture_ui_state,apply_python_state
    from .work_sessions import build_session,prepare_session,WorkSessionStore,encode_domain
    application=QApplication([])
    settings=QSettings(str(out/'settings.ini'),QSettings.IniFormat);settings.setFallbacksEnabled(False)
    profile=QWebEngineProfile(application);profile.setPersistentCookiesPolicy(QWebEngineProfile.NoPersistentCookies)
    class LocalOnly(QWebEngineUrlRequestInterceptor):
        def interceptRequest(self,info):
            if info.requestUrl().scheme() not in ('file','qrc','data','blob','about'):info.block(True)
    interceptor=LocalOnly(profile);profile.setUrlRequestInterceptor(interceptor)
    checks={};errors=[]
    def check(key,ok):
        checks[key]=bool(ok)
        if not ok:raise AssertionError(key)
    with ExitStack() as scope:
        scope.enter_context(patch.object(ui,'QSettings',return_value=settings))
        scope.enter_context(patch.object(ui.MainWindow,'_ai_material_root_dir',lambda w:out/'state'))
        scope.enter_context(patch.object(ui,'QWebEnginePage',side_effect=lambda parent:QWebEnginePage(profile,parent)))
        scope.enter_context(patch.object(tempfile,'tempdir',str(out/'tmp')))
        scope.enter_context(patch('app.ai_client._codex_cli_path_from_config',return_value=''))
        warning_patch=patch.object(ui.QMessageBox,'warning',side_effect=lambda *a:errors.append(str(a[2])))
        scope.enter_context(warning_patch)
        theme=ThemeManager(application);theme.set_mode(args.theme)
        w=ui.MainWindow(theme_manager=theme);w.resize(1280,900)
        w.setWindowTitle(f'Goedu-Split {__version__} · 설치 전 검토본 · 합성 자료 / 격리 설정')
        w.show();QTest.qWait(400)
        c=w.folder_workspace
        folder=batch_fixtures(out)
        import openpyxl
        for semester in (1,2):
            for number in (1,2):
                book=openpyxl.Workbook();sheet=book.active
                sheet.append(['구분','A/B','B/C','C/D','D/E','E/미도달'])
                sheet.append(['평균',90-number,80-number,70-number,60-number,40-number])
                book.save(folder/f'2026학년도 {semester}학기 {number}차 분할점수.xlsx')
                book=openpyxl.Workbook();sheet=book.active
                sheet.append([f'2026학년도 {semester}학기 {number}차 교과목 : 수학:합성수학(4) 만점 : 100.00'])
                sheet.append(['반번호',1,2])
                for i in range(10):sheet.append([i+1,99-i*2-number,98-i*2-number])
                sheet.append(['응시생수'])
                book.save(folder/f'2026학년도 {semester}학기 {number}차 교과목별일람표.xlsx')
        mime=QMimeData();mime.setUrls([QUrl.fromLocalFile(str(folder))])
        enter=QDragEnterEvent(QPoint(200,200),Qt.CopyAction,mime,Qt.LeftButton,Qt.NoModifier)
        drop=QDropEvent(QPointF(200,200),Qt.CopyAction,mime,Qt.LeftButton,Qt.NoModifier)
        application.sendEvent(w,enter);application.sendEvent(w,drop)
        check('native directory drop registers only',drop.isAccepted() and c.selected==str(folder.resolve()) and w.exam is None)
        QTest.mouseClick(c.add,Qt.LeftButton)
        for i in range(4):
            p=out/f'favorite-{i}';p.mkdir();c.register(p);QTest.mouseClick(c.add,Qt.LeftButton)
        p=out/'sixth';p.mkdir();c.register(p);QTest.mouseClick(c.add,Qt.LeftButton)
        check('sixth favorite blocked',len(c.favorites)==5 and '최대' in c.note.text())
        c.activate_favorite(1)
        check('favorite dropdown restores selected folder',c.selected==str(folder.resolve()))
        w._sidebar_user_choice=False;w.splitter.setSizes([0,1280]);QTest.qWait(200)
        w.grab().save(str(out/'start.png'))
        settings.sync()
        reopened=QSettings(settings.fileName(),QSettings.IniFormat)
        check('five favorites durable on disk',reopened.value('workspace/favoriteFoldersV1')==c.favorites)
        inputs={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.glob('*.xlsx')}
        # Drive the actual folder action and its modal, rather than calling analysis directly.
        def accept_preparation():
            dialog=application.activeModalWidget()
            try:
                check('real preparation dialog opens',dialog is not None)
                for index, page in enumerate(dialog.pages):
                    QTest.mouseClick(page.calculate, Qt.LeftButton)
                    check(f'prefixed subject grade cut round {index+1}', page.reports is not None)
                QTest.qWait(120)
                check('actual grade cut calculation available', dialog.pages[0].reports is not None)
                check('actual file cut values shown', '89.00' in dialog.pages[0].cuts_label.text())
                dialog.grab().save(str(out/'preparation.png'))
                # Accept through the public primary button (helper owns validation).
                buttons=[b for b in dialog.findChildren(ui.QPushButton) if '분석' in b.text() and '선택' in b.text()]
                check('preparation primary button available',bool(buttons) and buttons[-1].isEnabled())
                QTest.mouseClick(buttons[-1],Qt.LeftButton)
            except Exception as exc:
                errors.append(str(exc));dialog.reject()
        QTimer.singleShot(500,accept_preparation)
        QTest.mouseClick(c.analyze,Qt.LeftButton);QTest.qWait(500)
        check('folder action analyzes four rounds',w.exam is not None and len(w._portfolio_analysis_sessions)>=4)
        check('registration card moved to settings',w.input_workspace.folder_layout.indexOf(c.card)>=0)
        check('result sidebar defaults collapsed',w.splitter.sizes()[0]==0)
        w.grab().save(str(out/'results.png'))
        QTest.mouseClick(w.btn_sidebar,Qt.LeftButton);QTest.qWait(150)
        check('settings opens without losing folder',w.input_workspace.dialog.isVisible() and c.selected==str(folder.resolve()))
        w.input_workspace.dialog.grab().save(str(out/'input-panel.png'))
        w.input_workspace.open('individual');QTest.qWait(150)
        w.input_workspace.dialog.grab().save(str(out/'individual-inputs.png'))
        check('individual input controls preserved',w.fs_response.isVisible() and w.btn_run_analysis.isVisible())
        w.input_workspace.dialog.close()
        # Cancel a real edited preparation dialog; no live work may change.
        domain_before_cancel=encode_domain(w.exam,w.perform_data)
        ui_before_cancel=capture_ui_state(w)
        cancel_seen=[]
        def cancel_preparation():
            dialog=application.activeModalWidget()
            try:
                check('preparation cancellation dialog opens',dialog is not None)
                page=dialog.pages[0]
                page.pencil.setValue(37)
                page.include.setChecked(False)
                buttons=[b for b in dialog.findChildren(ui.QPushButton) if '취소' in b.text()]
                check('preparation cancel button available',bool(buttons))
                QTest.mouseClick(buttons[-1],Qt.LeftButton)
                cancel_seen.append(True)
            except Exception as exc:
                errors.append(str(exc))
                if dialog:dialog.reject()
        QTimer.singleShot(350,cancel_preparation)
        QTest.mouseClick(c.analyze,Qt.LeftButton);QTest.qWait(200)
        check('preparation cancel preserves current domain and edits',cancel_seen==[True]
              and encode_domain(w.exam,w.perform_data)==domain_before_cancel
              and capture_ui_state(w)==ui_before_cancel)

        def drag_column(table,column,delta):
            header=table.horizontalHeader();viewport=header.viewport()
            point=QPoint(header.sectionViewportPosition(column)+header.sectionSize(column)-1,header.height()//2)
            initial=table.columnWidth(column)
            QTest.mousePress(viewport,Qt.LeftButton,pos=point)
            QTest.mouseMove(viewport,point+QPoint(delta,0),40)
            QTest.mouseRelease(viewport,Qt.LeftButton,pos=point+QPoint(delta,0))
            QTest.qWait(100)
            return initial,table.columnWidth(column)
        w.tabs.setCurrentWidget(w.tab_data);QTest.qWait(120)
        data_initial,data_width=drag_column(w.table_data,2,35)
        check('actual Data header drag changes width',data_width>data_initial)
        w.grab().save(str(out/'data-column-drag.png'))
        w.tabs.setCurrentWidget(w.tab_portfolio)
        w.le_portfolio_search.clear();w.refresh_portfolio_tab()
        w.combo_portfolio_student.setCurrentIndex(1)
        w.portfolio_view.tabs.setCurrentIndex(2)
        w.portfolio_view.report_scroll.ensureWidgetVisible(w.portfolio_view.tabs)
        QTest.qWait(150)
        detail=w.portfolio_detail_tables['items']
        detail_initial,detail_width=drag_column(detail,0,35)
        check('actual portfolio detail header drag changes width',detail_width>detail_initial)
        w.grab().save(str(out/'portfolio-column-drag.png'))
        before=encode_domain(w.exam,w.perform_data)
        store=WorkSessionStore(out/'saved-work');saved=store.save(build_session(w.exam,w.perform_data,capture_ui_state(w),None))
        fresh=ui.MainWindow(theme_manager=theme)
        apply_python_state(fresh,prepare_session(store.read(saved)));QTest.qWait(500)
        check('fresh window keeps full result area', fresh.splitter.sizes()[0] == 0)
        check('fresh window restores full work',encode_domain(fresh.exam,fresh.perform_data)==before)
        check('fresh window retains favorites',fresh.folder_workspace.favorites==c.favorites)
        check('fresh window restores dragged Data width',fresh.table_data.columnWidth(2)==data_width)
        check('fresh window restores dragged portfolio detail width',fresh.portfolio_detail_tables['items'].columnWidth(0)==detail_width)
        fresh.close();fresh.deleteLater()
        check('input files unchanged',inputs=={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.glob('*.xlsx')})
        check('no application warnings',not errors)
        # Verify actual popup geometry at laptop zoom, keeping the work untouched.
        from .folder_batch import discover_round_groups
        from .analysis_preparation import AnalysisPreparationDialog
        w._set_zoom(120)
        zoom_dialog=AnalysisPreparationDialog(w,discover_round_groups(folder,w.cmb_round.currentText()))
        zoom_dialog.resize(1000,740);zoom_dialog.show();QTest.qWait(200)
        zoom_page=zoom_dialog.pages[0];zoom_page.calculate.click();QTest.qWait(100)
        zoom_dialog.grab().save(str(out/'preparation-120.png'))
        check('120 percent popup has no horizontal scroll',zoom_dialog.tabs.widget(0).horizontalScrollBar().maximum()==0)
        check('120 percent all grade cards populated',all(card.text() not in ('','—') for card in zoom_page.grade_cards.values()))
        zoom_dialog.reject();zoom_dialog.deleteLater();w._set_zoom(100)
        # Exercise incomplete input through the same visible preparation action.
        # Only first-round response files exist in this folder: no second round,
        # item information or performance input can be silently reused.
        first_only=out/'first-response-only';first_only.mkdir()
        first_group=discover_round_groups(folder,w.cmb_round.currentText())[0]
        for source in first_group['response']:
            source=Path(source)
            (first_only/source.name).write_bytes(source.read_bytes())
        c.register(first_only)
        def accept_partial():
            dialog=application.activeModalWidget()
            try:
                check('first-only preparation has one round',len(dialog.pages)==1)
                dialog.grab().save(str(out/'first-only-preparation.png'))
                buttons=[b for b in dialog.findChildren(ui.QPushButton) if '분석' in b.text() and '선택' in b.text()]
                QTest.mouseClick(buttons[-1],Qt.LeftButton)
            except Exception as exc:
                errors.append(str(exc))
                if dialog:dialog.reject()
        QTimer.singleShot(350,accept_partial)
        QTest.mouseClick(c.analyze,Qt.LeftButton);QTest.qWait(400)
        check('first-only actual students displayed',w.exam is not None and bool(w.exam.students) and w.table_data.rowCount()>0)
        check('first-only missing item data empty',not w.exam.items and w.table_items.rowCount()==0 and w.table_choice.rowCount()==0 and w.table_std.rowCount()==0)
        check('first-only pencil scores preserved',not w.exam.use_perform and all(s.final_score==s.total for s in w.exam.students))
        check('first-only has no application warnings',not errors)
        w.tabs.setCurrentWidget(w.tab_data);QTest.qWait(150)
        w.grab().save(str(out/'first-only-result.png'))
        report={'status':'passed','checks':checks,'errors':errors,'input':'isolated synthetic only','source_preview':not bool(getattr(sys,'frozen',False)),
                'version':__version__,'frozen':bool(getattr(sys,'frozen',False)),
                'executable':str(Path(sys.executable).resolve()),
                'executable_sha256':hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest()}
        (out/'REVIEW.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
        print(json.dumps(report,ensure_ascii=False),flush=True)
        if args.capture_only:
            w.close();return 0
        warning_patch.stop()
        w.showNormal(); w.raise_(); w.activateWindow()
        if args.show_preparation:
            from .folder_batch import discover_round_groups
            from .analysis_preparation import AnalysisPreparationDialog
            dialog=AnalysisPreparationDialog(w,discover_round_groups(folder,w.cmb_round.currentText()))
            for page in dialog.pages:page.calculate.click()
            dialog.accepted.connect(lambda:w._analyze_folder_groups(dialog.result_groups))
            dialog.setWindowTitle('Goedu-Split · 설치 전 실제 검토본 · 분석 준비')
            w._review_dialog=dialog
            def bring_review_forward():
                # Restore this review's own Qt windows, including macOS minimized
                # windows. This does not use desktop accessibility automation.
                w.showNormal()
                dialog.setWindowFlag(Qt.WindowStaysOnTopHint, True)
                dialog.showNormal();dialog.raise_();dialog.activateWindow()
                if dialog.windowHandle():dialog.windowHandle().requestActivate()
                if sys.platform == 'darwin':
                    import ctypes
                    objc=ctypes.CDLL('/usr/lib/libobjc.A.dylib')
                    objc.objc_getClass.restype=ctypes.c_void_p
                    objc.sel_registerName.restype=ctypes.c_void_p
                    objc.objc_getClass.argtypes=[ctypes.c_char_p]
                    objc.sel_registerName.argtypes=[ctypes.c_char_p]
                    def send(receiver, selector, arg=None):
                        types=[ctypes.c_void_p,ctypes.c_void_p]+([ctypes.c_long] if arg is not None else [])
                        fn=ctypes.CFUNCTYPE(ctypes.c_void_p,*types)(('objc_msgSend',objc))
                        return fn(receiver,objc.sel_registerName(selector.encode()),*([arg] if arg is not None else []))
                    nsapp=send(objc.objc_getClass(b'NSApplication'),'sharedApplication')
                    send(nsapp,'setActivationPolicy:',0)
                    native=send(int(dialog.winId()),'window')
                    if native:
                        send(native,'setCollectionBehavior:',2|256)
                        send(native,'deminiaturize:',0)
                        send(native,'makeKeyAndOrderFront:',0)
                        send(native,'orderFrontRegardless')
                    send(nsapp,'activateIgnoringOtherApps:',1)
            QTimer.singleShot(300,bring_review_forward)
        return application.exec()

if __name__=='__main__':raise SystemExit(main())
