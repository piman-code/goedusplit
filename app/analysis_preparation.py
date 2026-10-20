"""Isolated per-round preparation: inspect real inputs without mutating the work."""
from __future__ import annotations
import copy
from pathlib import Path
from PySide6.QtCore import Qt,QSignalBlocker
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QCheckBox,
    QComboBox,QPushButton,QTabWidget,QWidget,QScrollArea,QDoubleSpinBox,QFileDialog,QGroupBox,QSizePolicy,QFrame,QToolButton,QProgressBar)
from .cuts_loader import load_cut_scores
from .preparation_settings import load_choices,save_choices
from .perform_loader import load_perform_many
from .data_loader import PATH_SEPARATOR
from .grade_cut_calculator import load_grade5_cut_reports,grade5_cut_summary
from .folder_batch import prepare_round_groups,subjects_compatible,_metadata,_evidence_matches


def score_text(values):
    return '   '.join(f'{level} ≥ {float(values[level]):.2f}' for level in 'ABCDE')


class WrappedValueLabel(QLabel):
    """Keep all computed lines visible when a short placeholder becomes results."""
    def __init__(self, text=''):
        super().__init__(text)
        self.setWordWrap(True)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.setSizePolicy(QSizePolicy.Policy.Preferred,QSizePolicy.Policy.Fixed)

    def _fit_height(self):
        if self.width()<=0 or getattr(self,'_fitting_height',False):
            return
        self._fitting_height=True
        try:
            # QLabel's heightForWidth is bounded by its old minimum. Remove
            # that bound before measuring so an initially narrow label shrinks
            # again when its final two-column width is assigned.
            self.setMinimumHeight(0)
            self.setMaximumHeight(16777215)
            height=max(self.fontMetrics().height(),self.heightForWidth(self.width()))
            self.setFixedHeight(height)
        finally:
            self._fitting_height=False

    def setText(self,text):
        super().setText(text)
        self._fit_height()
        self.updateGeometry()

    def resizeEvent(self,event):
        super().resizeEvent(event)
        self._fit_height()

    def changeEvent(self,event):
        super().changeEvent(event)
        self._fit_height()


class SourceCaption(QLabel):
    def __init__(self,text=''):
        super().__init__();self._source='';self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed);self.setText(text)
    def setText(self,text):
        self._source=text;self.setToolTip(text)
        super().setText(self.fontMetrics().elidedText(text,Qt.TextElideMode.ElideMiddle,max(1,self.width())))
    def resizeEvent(self,event):
        super().resizeEvent(event);self.setText(self._source)


class RoundPreparation(QWidget):
    def __init__(self,window,group):
        super().__init__()
        self.window=window;self.group=copy.deepcopy(group);self.reports=None;self.report_path='';self.error=''
        self.current_cuts=window._current_cut_scores_from_inputs()
        self.restore_notice=''
        layout=QVBoxLayout(self);layout.setContentsMargins(16,16,16,16);layout.setSpacing(12)
        self.include=QCheckBox(group['label']);self.include.setChecked(True);layout.addWidget(self.include)
        columns=QHBoxLayout();columns.setSpacing(16);layout.addLayout(columns)
        connection=QGroupBox('연결 자료');connection.setObjectName('prepare_connections');values=QGroupBox('이 회차에 적용할 값');values.setObjectName('prepare_values')
        for panel in (connection,values):
            panel.setMinimumWidth(0);panel.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Expanding)
        columns.addWidget(connection,1);columns.addWidget(values,1)
        left=QVBoxLayout(connection);right=QVBoxLayout(values)
        left.setSpacing(12);right.setSpacing(12)
        def file_section(title, paths, editable=False):
            toggle=QToolButton();toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            toggle.setCheckable(True);toggle.setArrowType(Qt.ArrowType.RightArrow)
            toggle.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed)
            panel=QWidget();body=QVBoxLayout(panel);body.setContentsMargins(8,4,8,4);body.setSpacing(8)
            toggle.setText(f'{title} · {len(paths)}개 파일 · 펼쳐 보기')
            for path in paths:
                if editable:
                    choice=QCheckBox(Path(path).name);choice.setChecked(path in group['perform'])
                    choice.setToolTip(str(path));self.perform_checks.append((path,choice))
                else:
                    choice=QLabel(Path(path).name);choice.setWordWrap(True);choice.setToolTip(str(path))
                body.addWidget(choice)
            panel.setVisible(False)
            def expand(checked):
                panel.setVisible(checked);toggle.setArrowType(Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow)
            toggle.toggled.connect(expand)
            return toggle,panel
        self.perform_checks=[]
        form=QFormLayout();form.setVerticalSpacing(14);form.setHorizontalSpacing(12)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows);left.addLayout(form);self.combos={}
        response_toggle,response_panel=file_section('정오표',group['response'])
        self.response_toggle=response_toggle;form.addRow('학생 정오표',response_toggle);form.addRow('',response_panel)
        for category,title,key in [('iteminfo','문항정보표','item_candidates'),('cuts','성취도 분할점수','cuts_candidates'),('grade5_report','지필 등급 컷 자료','grade5_report_candidates')]:
            row=QWidget();h=QHBoxLayout(row);h.setContentsMargins(0,0,0,0);h.setSpacing(8)
            combo=QComboBox();combo.setObjectName('prepare_'+category)
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon);combo.setMinimumContentsLength(8)
            combo.addItem('현재 화면 설정 사용' if category=='cuts' else '미지정','')
            for path in dict.fromkeys([group[category]]+group[key]):
                if path:combo.addItem(Path(path).name,path)
            if group[category]:combo.setCurrentIndex(combo.findData(group[category]))
            browse=QPushButton('찾기');h.addWidget(combo,1);h.addWidget(browse);form.addRow(title,row);self.combos[category]=combo
            browse.clicked.connect(lambda checked=False,c=category:self.browse(c))
        self.perform_toggle,perform_panel=file_section('수행평가',list(dict.fromkeys(group['perform']+group['perform_candidates'])),True)
        form.addRow('수행평가',self.perform_toggle);form.addRow('',perform_panel)
        def score_cards(labels):
            strip=QWidget();grid=QHBoxLayout(strip);grid.setContentsMargins(0,0,0,0);grid.setSpacing(8);cells={}
            for label in labels:
                card=QFrame();card.setProperty('role','card');column=QVBoxLayout(card);column.setContentsMargins(6,8,6,8);column.setSpacing(4)
                title=QLabel(label+'등급' if label.isdigit() else label);title.setAlignment(Qt.AlignmentFlag.AlignCenter)
                value=QLabel('—');value.setProperty('role','prepare_score');value.setAlignment(Qt.AlignmentFlag.AlignCenter)
                font=value.font();font.setBold(True);font.setPointSizeF(font.pointSizeF()+1);value.setFont(font)
                column.addWidget(title);column.addWidget(value);grid.addWidget(card,1);cells[label]=value
            return strip,cells
        self.cuts_label=WrappedValueLabel();self.cuts_label.setObjectName('prepare_cut_values');self.cuts_label.setWordWrap(True);right.addWidget(self.cuts_label);self.cuts_label.hide()
        right.addWidget(QLabel('성취도 분할점수'));self.cut_source=SourceCaption();right.addWidget(self.cut_source)
        strip,self.cut_cards=score_cards(list('ABCDE'));right.addWidget(strip)
        self.grade_label=WrappedValueLabel('지필평가 1~5등급 컷 · 미계산');self.grade_label.setObjectName('prepare_grade_values');self.grade_label.setWordWrap(True)
        right.addWidget(self.grade_label);self.grade_label.hide()
        right.addWidget(QLabel('지필평가 1~5등급 컷'));self.grade_source=SourceCaption('아직 계산하지 않음');right.addWidget(self.grade_source)
        strip,self.grade_cards=score_cards([str(n) for n in range(1,6)]);right.addWidget(strip)
        self.calculate=QPushButton('선택 일람표로 1~5등급 컷 계산');self.calculate.setObjectName('prepare_grade_calculate');right.addWidget(self.calculate)
        weights=QHBoxLayout();right.addLayout(weights)
        weights.addWidget(QLabel('지필 반영비율'))
        self.pencil=QDoubleSpinBox();self.pencil.setObjectName('prepare_pencil_weight');self.pencil.setRange(0,100);self.pencil.setDecimals(2);self.pencil.setSuffix(' %')
        total=window.spin_pencil_ratio.value()+window.spin_perform_ratio.value()
        self.pencil.setValue(window.spin_pencil_ratio.value()*100/total if total>0 and group['perform'] else 100)
        weights.addWidget(self.pencil);weights.addStretch()
        self.perform_label=QLabel();self.perform_label.setWordWrap(True);right.addWidget(self.perform_label)
        self.weight_bar=QProgressBar();self.weight_bar.setRange(0,10000);self.weight_bar.setTextVisible(False);self.weight_bar.setFixedHeight(14);right.addWidget(self.weight_bar)
        self.file_weights=QCheckBox('수행 파일의 반영비율 사용')
        self.file_weights.setToolTip('이 회차는 선택한 수행평가 파일에 기록된 반영비율을 사용합니다.')
        self.file_weights.setChecked(bool(group['perform']) and window.spin_perform_ratio.value()==0);right.addWidget(self.file_weights)
        self.validation=QLabel();self.validation.setObjectName('prepare_validation');self.validation.setWordWrap(True);left.addWidget(self.validation);left.addStretch();right.addStretch()
        for category,combo in self.combos.items():combo.currentIndexChanged.connect(lambda _,c=category:self.changed(c))
        for _,choice in self.perform_checks:choice.toggled.connect(self.refresh)
        self.pencil.valueChanged.connect(self.refresh);self.file_weights.toggled.connect(self.refresh)
        self.calculate.clicked.connect(self.calculate_grades);self.refresh()

    def restore_choices(self,saved):
        if saved.get('manual_cut_scores') is not None:self.current_cuts=dict(saved['manual_cut_scores'])
        widgets=[*self.combos.values(),self.pencil,self.file_weights,self.include,*[c for _,c in self.perform_checks]]
        blockers=[QSignalBlocker(widget) for widget in widgets]
        for category,path in saved['files'].items():
            combo=self.combos[category]
            if path and combo.findData(path)<0:combo.addItem(Path(path).name,path)
            combo.setCurrentIndex(max(0,combo.findData(path)))
        for path,choice in self.perform_checks:choice.setChecked(path in saved['perform'])
        self.pencil.setValue(saved['pencil_weight']);self.file_weights.setChecked(saved['file_weights']);self.include.setChecked(saved['include'])
        del blockers
        names={'iteminfo':'문항정보표','cuts':'분할점수','grade5_report':'등급 컷 자료','perform':'수행평가'}
        if saved['missing']:self.restore_notice='저장한 파일이 없습니다. 다시 선택해 주세요: '+', '.join(dict.fromkeys(names[k] for k in saved['missing']))
        self.refresh()

    def save_choices(self):
        values={category:combo.currentData() or '' for category,combo in self.combos.items()}
        values.update(perform=[p for p,c in self.perform_checks if c.isChecked()],pencil_weight=self.pencil.value(),file_weights=self.file_weights.isChecked(),include=self.include.isChecked(),manual_cut_scores=dict(self.current_cuts))
        return save_choices(self.window.settings,self.group,values)

    def browse(self,category):
        path,_=QFileDialog.getOpenFileName(self,'회차 자료 선택','','Excel (*.xlsx)')
        if path:
            combo=self.combos[category];index=combo.findData(path)
            if index<0:combo.addItem(Path(path).name,path);index=combo.count()-1
            combo.setCurrentIndex(index)

    def changed(self,category):
        if category=='grade5_report':
            self.reports=None;self.report_path='';self.grade_label.setText('지필평가 1~5등급 컷 · 미계산 (자료 변경)')
            self.grade_source.setText('아직 계산하지 않음')
            for cell in self.grade_cards.values():cell.setText('—')
        self.refresh()

    def selected(self):
        entry=copy.deepcopy(self.group)
        entry['manual_cut_scores']=dict(self.current_cuts)
        for category,combo in self.combos.items():
            entry[category]=combo.currentData() or ''
            if category!='iteminfo' or entry[category]:entry['problems']=[p for p in entry['problems'] if not p.startswith(category+':')]
        entry['problems']=[p for p in entry['problems'] if p!='같은 회차 문항정보표 또는 명시적 공통자료 필요']
        entry['perform']=[p for p,c in self.perform_checks if c.isChecked()]
        entry['use_file_perform_ratio']=self.file_weights.isChecked()
        entry['pencil_weight']=self.pencil.value();entry['perform_weight']=100-self.pencil.value()
        entry['warnings']=[w for w in entry.get('warnings',[]) if not w.startswith(('문항정보표 없음:', '수행 자료 없음:'))]
        if not entry['iteminfo']:
            message='문항정보표 없음: 학생 점수만 분석하며 문항별 결과는 표시하지 않습니다.'
            if message not in entry['warnings']:entry['warnings'].append(message)
        if not entry['perform']:
            entry['pencil_weight']=100;entry['perform_weight']=0;entry['use_file_perform_ratio']=False
            message='수행 자료 없음: 지필 원점수만 표시합니다. 학기 총점이 아닙니다.'
            if message not in entry['warnings']:entry['warnings'].append(message)
        entry['prepared_grade5_reports']=copy.deepcopy(self.reports)
        entry['prepared_grade5_info']=self.grade_label.text() if self.reports else '지필평가 1~5등급 컷 · 미계산'
        return entry

    def refresh(self,*_):
        self.error='';entry=self.selected()
        for combo in self.combos.values():combo.setToolTip(str(combo.currentData() or combo.currentText()))
        try:
            cuts=load_cut_scores(entry['cuts'])[0] if entry['cuts'] else self.current_cuts
            self.cut_source.setText(Path(entry['cuts']).name if entry['cuts'] else '현재 화면 설정')
            for key,cell in self.cut_cards.items():cell.setText(f'{float(cuts[key]):.2f}')
            self.cuts_label.setText('성취도 분할점수 · '+(Path(entry['cuts']).name if entry['cuts'] else '현재 화면 설정')+'\n'+score_text(cuts))
        except Exception:
            self.cut_source.setText('파일 읽기 실패')
            for cell in self.cut_cards.values():cell.setText('—')
            self.cuts_label.setText('성취도 분할점수 · 파일 읽기 실패');self.error='분할점수 파일을 확인해 주세요.'
        self.pencil.setEnabled(bool(entry['perform']) and not self.file_weights.isChecked())
        pw,sw=entry['pencil_weight'],entry['perform_weight']
        if entry['use_file_perform_ratio']:
            try:
                if not entry['perform']:raise ValueError('missing performance')
                sw=float(load_perform_many(PATH_SEPARATOR.join(entry['perform'])).ratio_total)
                if not 0<sw<=100:raise ValueError('invalid ratio')
                pw=100-sw
                blocker=QSignalBlocker(self.pencil);self.pencil.setValue(pw);del blocker
            except Exception:self.error='수행 파일과 반영비율을 확인해 주세요.'
        self.perform_label.setText(f'적용: 지필 {pw:g}% · 수행 {sw:g}%')
        self.weight_bar.setValue(round(pw*100))
        self.perform_toggle.setText(f'수행평가 · {len(entry["perform"])}개 선택 · 펼쳐 보기')
        if not entry['perform']:self.perform_label.setText('지필 원점수만 표시 · 수행 자료 없음 · 학기 총점 아님')
        if entry['problems']:self.error=' / '.join(entry['problems'])
        self.validation.setText('\n'.join(filter(None,[self.error,self.restore_notice,*entry['warnings']])) or '선택한 자료는 분석 전에 다시 검사합니다.')
        self.calculate.setEnabled(bool(entry['grade5_report']))

    def calculate_grades(self):
        path=self.combos['grade5_report'].currentData()
        try:
            evidence=_metadata(Path(path))
            expected=dict(zip(('학년도','학기','차수','학년','과목'),self.group['key']))
            if any(len(evidence[field])>1 or not _evidence_matches(field,value,evidence[field]) for field,value in expected.items()):
                raise ValueError('선택 회차와 일람표의 시험 정보가 다릅니다.')
            reports=load_grade5_cut_reports(path)
            subject=self.group['key'][4]
            matching=[r for r in reports if not subject or subjects_compatible(subject,r['subject'])]
            if len(matching)!=1:raise ValueError('선택 회차의 과목을 한 개로 확인하지 못했습니다.')
            report=matching[0];summary=grade5_cut_summary(report['scores'])
            self.grade_source.setText(f"{Path(path).name} · {summary['n']}명")
            for row in summary['cut_rows']:self.grade_cards[str(row['grade'])].setText(f"{float(row['score']):.2f}")
            values='   '.join(f"{row['grade']}등급 {float(row['score']):.2f}" for row in summary['cut_rows'])
            self.grade_label.setText(f"지필평가 1~5등급 컷 · {Path(path).name} · {summary['n']}명\n{values}")
            self.reports=copy.deepcopy(matching);self.report_path=path
        except Exception as exc:
            self.grade_source.setText('아직 계산하지 않음')
            for cell in self.grade_cards.values():cell.setText('—')
            self.reports=None;self.report_path='';self.grade_label.setText('지필평가 1~5등급 컷 · 미계산 (읽기 또는 과목 확인 실패)')
            self.validation.setText(str(exc))


class AnalysisPreparationDialog(QDialog):
    def __init__(self,window,groups):
        # A preparation draft must not become part of MainWindow's descendant
        # widget snapshot (especially its round-navigation tabs).
        super().__init__(None);self.setPalette(window.palette());self.setFont(window.font())
        self.setStyleSheet(window.styleSheet());self.setWindowTitle('회차별 분석 준비');self.resize(1000,740)
        from .palettes import LIGHT,DARK
        colors=getattr(getattr(window,'theme',None),'colors',None) or (DARK if window.palette().window().color().lightness()<128 else LIGHT)
        self.setStyleSheet(self.styleSheet()+f'''\nQGroupBox#prepare_connections {{ background: {colors['panel']}; }}\nQGroupBox#prepare_values {{ background: {colors['card']}; }}\nQGroupBox::title {{ font-weight: 700; font-size: 15px; }}\nQLabel#prepare_heading {{ font-size: 18px; font-weight: 700; }}\nQLabel, QComboBox, QCheckBox, QDoubleSpinBox {{ font-weight: 400; }}\nQLabel[role="prepare_score"] {{ font-weight: 700; }}\nQLabel, QCheckBox {{ background: transparent; color: {colors['text']}; }}\nQCheckBox::indicator:unchecked {{ border: 1px solid {colors['border']}; background: {colors['panel']}; border-radius: 3px; }}\nQProgressBar {{ background: {colors['border']}; border: none; border-radius: 7px; }}\nQProgressBar::chunk {{ background: {colors['accent']}; border-radius: 7px; }}\nQToolButton {{ background: {colors['card']}; color: {colors['text']}; border: 1px solid {colors['border']}; border-radius: 6px; padding: 8px; }}''')
        self.window=window;self.result_groups=[];self.skipped_groups=[];layout=QVBoxLayout(self);layout.setContentsMargins(16,16,16,16);layout.setSpacing(12)
        heading=QLabel('회차별 분석 준비');heading.setObjectName('prepare_heading');layout.addWidget(heading)
        intro=QLabel('자료 연결 → 점수·비율 확인 → 분석 · 취소하면 기존 작업을 유지합니다.');intro.setWordWrap(True);layout.addWidget(intro)
        self.tabs=QTabWidget();self.tabs.tabBar().setExpanding(True);self.tabs.setStyleSheet('QTabWidget::pane { margin-top: 8px; }');layout.addWidget(self.tabs);self.pages=[]
        for group in groups:
            saved=load_choices(window.settings,group)
            group=copy.deepcopy(group)
            if saved:group['perform_candidates']=list(dict.fromkeys(group['perform_candidates']+saved['perform']))
            page=RoundPreparation(window,group)
            if saved:page.restore_choices(saved)
            scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QFrame.Shape.NoFrame);scroll.setWidget(page)
            self.tabs.addTab(scroll,group['label']);self.pages.append(page)
        self.status=QLabel();self.status.setWordWrap(True);layout.addWidget(self.status)
        row=QHBoxLayout();layout.addLayout(row);run=QPushButton('선택 회차 분석');run.setObjectName('prepare_analyze');run.setProperty('role','primary');cancel=QPushButton('취소')
        self.save_button=QPushButton('설정 저장');self.save_button.setObjectName('prepare_save_settings');self.save_button.clicked.connect(self.save_settings)
        row.addWidget(self.save_button);row.addStretch();row.addWidget(cancel);row.addWidget(run);run.clicked.connect(self.accept);cancel.clicked.connect(self.reject)

    def save_settings(self):
        outcomes=[page.save_choices() for page in self.pages]
        ok=all(outcomes)
        self.status.setText('설정을 저장했습니다. 이 폴더의 같은 회차를 다시 열면 복원됩니다.' if ok else '설정 저장에 실패했습니다. 현재 선택은 유지됩니다.')
        return ok

    def accept(self):
        selected=[];skipped=[]
        for index,page in enumerate(self.pages):
            if not page.include.isChecked():continue
            page.refresh();entry=page.selected();reason=page.error
            if not reason:
                try:prepare_round_groups([entry],page.current_cuts,entry['pencil_weight'],entry['perform_weight'])
                except Exception as exc:reason=str(exc)
            if reason:
                skipped.append({'label':page.group['label'],'reason':reason,'index':index})
            else:selected.append(entry)
        self.skipped_groups=skipped
        if skipped:
            self.status.setText('분석 제외 · '+'\n'.join(f"{item['label']}: {item['reason']}" for item in skipped))
        if not selected:
            if skipped:self.tabs.setCurrentIndex(skipped[0]['index'])
            else:self.status.setText('분석할 회차를 선택해 주세요.')
            return
        current_key=self.pages[self.tabs.currentIndex()].group['key']
        preferred=next((entry for entry in selected if entry['key']==current_key),selected[0])
        preferred['preferred_display']=True
        if not self.save_settings():return
        self.result_groups=selected;super().accept()
