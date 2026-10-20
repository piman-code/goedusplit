"""Explicit native review entry. Real application, isolated synthetic saved work.

Run: .venv/bin/python -m app.portfolio_review --output <new directory>
No installed settings or user data are read or changed by initialization.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import json
import os
from pathlib import Path
import tempfile
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--capture-only', action='store_true')
    parser.add_argument('--four-rounds', action='store_true', help='Review the four-round folder import with synthetic files')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    for name in ('appdata', 'cache', 'matplotlib', 'tmp', 'inputs', 'codex'):
        (output / name).mkdir()
    os.environ.update(MPLCONFIGDIR=str(output/'matplotlib'), XDG_CACHE_HOME=str(output/'cache'),
                      GOEDUSPLIT_CODEX_WORKDIR=str(output/'codex'))
    from PySide6.QtCore import QSettings, QTimer, Qt
    from PySide6.QtWidgets import QApplication
    from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage, QWebEngineUrlRequestInterceptor
    from PySide6.QtTest import QTest
    from . import main_window as ui
    from .theme import ThemeManager
    from .synthetic_qa import analysis_fixtures
    from .work_session_ui import capture_ui_state
    from .work_sessions import WorkSessionStore, build_session, encode_domain

    application = QApplication([])
    application.setApplicationName('Goedu-Split 포트폴리오 검토본')
    settings = QSettings(str(output/'settings.ini'), QSettings.IniFormat)
    settings.setFallbacksEnabled(False)
    profile = QWebEngineProfile(application)
    profile.setHttpCacheType(QWebEngineProfile.MemoryHttpCache)
    profile.setPersistentCookiesPolicy(QWebEngineProfile.NoPersistentCookies)

    class LocalOnly(QWebEngineUrlRequestInterceptor):
        def interceptRequest(self, info):
            if info.requestUrl().scheme().lower() not in ('file', 'qrc', 'data', 'blob', 'about'):
                info.block(True)

    interceptor = LocalOnly(profile)
    profile.setUrlRequestInterceptor(interceptor)
    with ExitStack() as scope:
        scope.enter_context(patch.object(ui, 'QSettings', return_value=settings))
        scope.enter_context(patch.object(ui.MainWindow, '_ai_material_root_dir', lambda self: output/'appdata'))
        scope.enter_context(patch.object(ui, 'QWebEnginePage', side_effect=lambda parent: QWebEnginePage(profile, parent)))
        scope.enter_context(patch.object(tempfile, 'tempdir', str(output/'tmp')))
        scope.enter_context(patch('app.ai_client._codex_cli_path_from_config', return_value=''))
        theme = ThemeManager(application)
        theme.set_mode('light')
        window = ui.MainWindow(theme_manager=theme)
        window.setWindowTitle('Goedu-Split · 포트폴리오 검토본 · 격리된 합성 저장자료')
        window.resize(1280, 800)
        window.show()
        item, responses, performance = analysis_fixtures(output/'inputs')
        window.fs_iteminfo.path_edit.setText(str(item))
        window.fs_perform.path_edit.setText(ui.PATH_SEPARATOR.join(map(str, performance)))
        window.chk_perform.setChecked(True)
        window.spin_pencil_ratio.setValue(60)
        window.spin_perform_ratio.setValue(40)
        store = WorkSessionStore(output/'appdata'/'work_sessions')
        paths = []
        if args.four_rounds:
            from .batch_ui_qa import batch_fixtures
            from .folder_batch import discover_round_groups
            batch_folder = batch_fixtures(output)
            groups = discover_round_groups(batch_folder, '1학기 1차')
            if not window._analyze_folder_groups(groups):
                raise AssertionError('Four-round review import failed')
            paths.append(str(store.save(build_session(window.exam, window.perform_data, capture_ui_state(window), None)).relative_to(output)))
        for round_no in (() if args.four_rounds else (1, 2)):
            window.fs_response.path_edit.setText(ui.PATH_SEPARATOR.join(map(str, responses[round_no])))
            window.run_analysis()
            QTest.qWait(200)
            year, semester, number = window._detect_exam_round()
            payload = build_session(window.exam, window.perform_data, capture_ui_state(window), None,
                                    {'subject': window.exam.subject, 'grade': window.exam.grade,
                                     'year': year, 'semester_no': semester, 'round_no': number,
                                     'round': window.cmb_round.currentText(), 'name': f'합성 검토 {round_no}차'})
            paths.append(str(store.save(payload).relative_to(output)))
        window.refresh_portfolio_tab()
        window.combo_portfolio_student.setCurrentIndex(1)
        window.tabs.setCurrentWidget(window.tab_portfolio)
        if window.input_panel.isVisible():
            QTest.mouseClick(window.btn_sidebar, Qt.LeftButton)
        view = window.portfolio_view
        before_domain = encode_domain(window.exam, window.perform_data)
        checks = {}
        initial_key = window.combo_portfolio_student.currentData()
        window.combo_portfolio_student.setFocus()
        QTest.keyClick(window.combo_portfolio_student, Qt.Key_Down)
        QTest.qWait(100)
        checks['dropdown changes student'] = window.combo_portfolio_student.currentData() != initial_key
        QTest.keyClick(window.combo_portfolio_student, Qt.Key_Up)
        view.round_combo.setFocus()
        QTest.keyClick(view.round_combo, Qt.Key_Home)
        QTest.qWait(150)
        checks['older round reads full detail'] = view.selected_point.get('source_kind') in ('work-session', 'analysis-session')
        if args.four_rounds:
            checks['all four round labels visible'] = [(p['semester_no'], p['round_no']) for p in view.chart.points] == [(1,1),(1,2),(2,1),(2,2)]
        checks['saved work has all five detail sources'] = all(
            tab.get('available') for tab in view.details['tabs'].values())
        for index, key in enumerate(('data', 'perform', 'items', 'choice', 'standards')):
            view.report_scroll.ensureWidgetVisible(view.tabs)
            QTest.mouseClick(view.tabs.tabBar(), Qt.LeftButton, pos=view.tabs.tabBar().tabRect(index).center())
            QTest.qWait(80)
            checks['detail tab '+key] = view.tabs.currentIndex() == index and view.tables[key].rowCount() > 0
            window.grab().save(str(output/f'native-{key}.png'))
        checks['reading history leaves current analysis unchanged'] = before_domain == encode_domain(window.exam, window.perform_data)
        view.tabs.setCurrentIndex(0)
        view.round_combo.setCurrentIndex(view.round_combo.count()-1)
        window.save_current_subject_snapshot()
        QTest.qWait(100)
        checks['saving summary keeps live detailed data available'] = all(
            tab.get('available') for tab in view.details['tabs'].values())
        checks['saved revisions are explicitly selectable'] = view.version_combo.count() >= 2
        window.btn_counsel_mode.setChecked(True)
        QTest.qWait(80)
        visible_cells = ' '.join(
            table.item(r, c).text() for table in view.tables.values()
            for r in range(table.rowCount()) for c in range(table.columnCount()) if table.item(r, c))
        checks['counseling hides names in every detail table'] = not any(
            student.name and student.name in visible_cells for student in window.exam.students)
        window.btn_counsel_mode.setChecked(False)
        QTest.qWait(80)
        view.report_scroll.verticalScrollBar().setValue(0)
        window.statusBar().showMessage('검토본: 실제 앱 기능 / 격리된 합성 저장자료 / 설치본 및 기존 설정 변경 없음')
        window.raise_()
        window.activateWindow()
        QTest.qWait(400)
        window.grab().save(str(output/'native-review.png'))
        (output/'REVIEW.json').write_text(json.dumps({'pid': os.getpid(), 'saved_work': paths, 'checks': checks,
            'installed_changed': False, 'data': 'synthetic persisted through WorkSessionStore'}, indent=2))
        if not all(checks.values()):
            window.close()
            raise AssertionError('Native review checks failed; see REVIEW.json')
        if args.capture_only:
            window.close()
            return 0
        return application.exec()


if __name__ == '__main__':
    raise SystemExit(main())
