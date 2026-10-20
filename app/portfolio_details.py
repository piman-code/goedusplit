"""Read-only, revision-bound portfolio details from explicitly saved full work.

Summary records never borrow responses from a similar exam. No identity guessing,
source-file reopening, state restoration, persistence, or network is performed.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

from .analysis import analyze_items, analyze_overall, grade_level, LEVELS
from .export_privacy import student_hash
from .grade_cut_calculator import GRADE5_CUMULATIVE, relative_grade_labels
from .rounds import parse_round, parse_year
from .work_sessions import WorkSessionStore, encode_domain, prepare_session, build_session

GRADE9 = [('1',4),('2',11),('3',23),('4',40),('5',60),('6',77),('7',89),('8',96),('9',100)]
TAB_KEYS = ('data','perform','items','choice','standards')


def _revision(exam, perform):
    return hashlib.sha256(json.dumps(encode_domain(exam,perform),sort_keys=True,
                                    ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def _payload_revision(payload):
    return hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def current_revision(window):
    return _revision(window.exam,window.perform_data) if window.exam is not None else ''


def _term(exam, ui):
    from .rounds import identify_exam_round
    manual = ui.get('widgets',{}).get('cmb_round',{}).get('text','')
    response = exam.source_files.get('responses') or ui.get('inputs',{}).get('fs_response','')
    return identify_exam_round(exam.semester,response,manual)


def _class(student):
    return str(student.grade_class or (student.class_no.split('/')[0] if '/' in student.class_no else ''))


def _grades(exam):
    scores = [s.final_score for s in exam.students]
    return relative_grade_labels(scores,GRADE9), relative_grade_labels(scores,GRADE5_CUMULATIVE)


def remember_analysis(window):
    """Retain successful analyses in memory only; explicit full save is durable."""
    import uuid
    if window.exam is None: return
    state={'widgets':{'cmb_round':{'text':window.cmb_round.currentText()}},
           'inputs':{'fs_response':window.exam.source_files.get('responses','')}}
    payload=build_session(window.exam,window.perform_data,state,None)
    sessions=getattr(window,'_portfolio_analysis_sessions',{})
    # Same loaded analysis is already represented; do not multiply identical runs.
    if any(entry['domain']==payload['domain'] and entry['ui_state']==payload['ui_state'] for entry in sessions.values()):
        return
    sessions=dict(sessions)
    sessions[uuid.uuid4().hex]=payload
    window._portfolio_analysis_sessions=sessions


def load_work_session_rows(window):
    """List saved-work students without changing original records or live analysis."""
    store = WorkSessionStore(window._ai_material_root_dir()/'work_sessions')
    key = window._portfolio_hash_key()
    rows = []
    sources=[(entry['path'],None,None) for entry in store.list_sessions()]
    sources += [(None,session_id,payload) for session_id,payload in getattr(window,'_portfolio_analysis_sessions',{}).items()]
    for path,session_id,cached in sources:
        try:
            payload = cached if cached is not None else store.read(path)
            prepared = prepare_session(payload)
            exam = prepared['exam']
            year, semester, number = _term(exam,prepared['ui_state'])
            if session_id and window.exam is not None and _revision(exam,prepared['perform_data'])==current_revision(window) and (year,semester,number)==window._detect_exam_round():
                continue
            grade9,grade5 = _grades(exam)
            revision = _payload_revision(payload)
            groups = {}
            for student in exam.students:
                if _class(student): groups.setdefault(_class(student),[]).append(student.final_score)
            for index, student in enumerate(exam.students):
                group = groups.get(_class(student),[])
                rows.append(dict(student_hash=student_hash(key,student.sid,student.class_no,student.name),
                    class_no=student.class_no,name=student.name,subject=exam.subject,grade=exam.grade,
                    year=year,semester_no=semester,round_no=number,
                    term=f'{exam.semester} {exam.grade}'.strip(),saved_at=payload['saved_at'],
                    score=student.final_score,level=grade_level(student.final_score,exam.cut_scores),
                    grade9=grade9[index],grade5=grade5[index],pencil_total=student.total,
                    perform_score=student.perform_score,rounded_score=round(student.final_score),
                    class_mean=sum(group)/len(group) if group else None,
                    snapshot_path=str(path) if path else 'session:'+session_id,snapshot_mtime_ns=path.stat().st_mtime_ns if path else 0,
                    is_current_preview=False,source_kind='analysis-session' if session_id else 'work-session',work_session_path=str(path) if path else '',
                    analysis_session_id=session_id,
                    detail_revision=revision))
        except (OSError,ValueError,TypeError,KeyError,AttributeError,OverflowError):
            # Other valid records remain readable; never emit identities in logs.
            continue
    return rows


def presentation_rows(window, rows):
    """Add explicit live analysis for presentation; never relabel saved summaries."""
    result=list(rows)
    if window.exam is None or any(row.get('source_kind')=='current' for row in result):
        return result
    snapshot=window._current_subject_snapshot()
    if not snapshot:
        return result
    identities=window._current_identity_by_hash()
    revision=current_revision(window)
    for student in snapshot['students']:
        hashed=student['student_hash']
        class_no,name=identities.get(hashed,('',f'학생#{hashed[:6]}'))
        result.append(dict(student_hash=hashed,class_no=class_no,name=name,
            subject=snapshot['subject'],grade=snapshot['grade'],year=snapshot.get('year'),
            semester_no=snapshot.get('semester_no'),round_no=snapshot.get('round_no'),
            term=f"{snapshot.get('semester','')} {snapshot['grade']}".strip(),
            saved_at='현재 분석',snapshot_path='',snapshot_mtime_ns=0,
            score=student['final_score'],rounded_score=student.get('rounded_score'),
            pencil_total=student.get('pencil_total'),perform_score=student.get('perform_score'),
            level=student.get('level',''),grade9=student.get('grade9',''),grade5=student.get('grade5',''),
            class_mean=student.get('class_mean'),is_current_preview=bool(getattr(window,"_portfolio_has_preview",False)),is_current_analysis=True,
            source_kind='current',detail_revision=revision))
    return result


def _table(headers,rows,available=True):
    return dict(headers=headers,rows=rows,available=available)


def _summary(point,message,window=None):
    tabs = {key:_table([],[],False) for key in TAB_KEYS}
    point = dict(point)
    if window is not None and getattr(window,'_counseling_mode_enabled',lambda:False)():
        point.update(class_no='',name='상담 학생')
    fields = [('반/번호','class_no'),('이름','name'),('성취도','level'),('9등급','grade9'),('5등급','grade5'),('원점수','rounded_score'),
              ('수행환산','perform_score'),('정기시험 총점','pencil_total')]
    present = [(label,point[key]) for label,key in fields if key in point and point[key] is not None]
    tabs['data'] = _table([v[0] for v in present],[[v[1] for v in present]] if present else [],bool(present))
    return dict(tabs=tabs,provenance=message)


def resolve_details(window,point):
    """Resolve the exact full-work revision, or return explicit summary-only data."""
    if not isinstance(point,dict):
        return _summary({},'선택한 회차가 없습니다.')
    try:
        if point.get('source_kind') == 'work-session':
            root = (window._ai_material_root_dir()/'work_sessions').resolve()
            path = Path(point['work_session_path']).resolve()
            if path.parent != root or path.suffix != '.json':
                raise ValueError('outside work store')
            payload = WorkSessionStore(root).read(path)
            prepared = prepare_session(payload)
            exam,perform = prepared['exam'],prepared['perform_data']
            term = _term(exam,prepared['ui_state'])
            revision = _payload_revision(payload)
        elif point.get('source_kind')=='analysis-session':
            payload=getattr(window,'_portfolio_analysis_sessions',{})[point['analysis_session_id']]
            prepared=prepare_session(payload)
            exam,perform=prepared['exam'],prepared['perform_data']
            term=_term(exam,prepared['ui_state'])
            revision=_payload_revision(payload)
        elif point.get('source_kind')=='current' and point.get('detail_revision'):
            exam,perform = window.exam,window.perform_data
            if exam is None: raise ValueError('no live exam')
            prepared = dict(item_stats=analyze_items(exam)[0],overall=analyze_overall(exam))
            term = window._detect_exam_round()
            revision = _revision(exam,perform)
        else:
            return _summary(point,'요약 저장 기록 · 응답·문항·수행 상세가 저장되지 않았습니다.',window)
        if (revision != point.get('detail_revision') or exam.subject != point.get('subject')
            or str(exam.grade) != str(point.get('grade',''))
            or term != (point.get('year'),point.get('semester_no'),point.get('round_no'))):
            raise ValueError('revision or exam mismatch')
        key = window._portfolio_hash_key()
        matches = [(i,s) for i,s in enumerate(exam.students)
                   if student_hash(key,s.sid,s.class_no,s.name)==point.get('student_hash')]
        if len(matches)!=1: raise ValueError('ambiguous identity')
        index,student = matches[0]
        grade9,grade5 = _grades(exam)
        tabs={}
        selected=sorted(exam.select_items,key=lambda item:item.number)
        answers=[student.answers.get(item.number,'') for item in selected]
        privacy=getattr(window,'_counseling_mode_enabled',lambda:False)()
        headers=['반/번호','이름','성취도','9등급','5등급','원점수']
        values=['' if privacy else student.class_no,'상담 학생' if privacy else student.name,
                grade_level(student.final_score,exam.cut_scores),grade9[index],grade5[index],round(student.final_score)]
        if exam.use_perform:
            headers.append('수행환산');values.append(student.perform_score)
        headers+=['정기시험 총점']+[f'문{item.number}' for item in selected]
        values+=[student.total]+answers
        tabs['data']=_table(headers,[values])
        record = (perform.records.get(student.sid) or perform.by_classno.get(student.class_no)) if perform is not None else None
        # A class/number fallback still requires the same saved name and class.
        if record and (record.class_no!=student.class_no or record.name!=student.name): record=None
        tabs['perform']=_table(['평가요소','만점','반영비율','학생 점수'],
            [[area.name,area.max_score,area.ratio_pct,record.scores.get(area.name)] for area in perform.areas]
            if record else [],bool(record))
        stats_by_number={s.item.number:s for s in prepared['item_stats']}
        item_rows=[]
        for item in exam.items:
            stats=stats_by_number.get(item.number) if item.item_type=='선택형' else None
            item_rows.append([item.number,item.item_type,item.score,item.answer,
                student.answers.get(item.number,'') if item.item_type=='선택형' else None,
                item.content_area,f'{item.standard_code} {item.standard}'.strip(),
                stats.p_value*100 if stats else None,stats.discrimination if stats else None])
        tabs['items']=_table(['문항','유형','배점','정답','학생 응답','내용영역','성취기준','전체 정답률(%)','변별도'],item_rows,bool(item_rows))
        choice_rows=[]
        for stats in prepared['item_stats']:
            groups=[('전체',stats.choice_dist)]+[(level,stats.choice_dist_by_level.get(level)) for level in LEVELS]
            for label,dist in groups:
                choice_rows.append([stats.item.number,stats.item.answer,student.answers.get(stats.item.number,''),label,
                                    *[dist.get(choice,0)*100 if dist is not None else None for choice in range(6)]])
        tabs['choice']=_table(['문항','정답','학생 응답','집단','무응답(%)','1번(%)','2번(%)','3번(%)','4번(%)','5번(%)'],choice_rows,bool(choice_rows))
        tabs['standards']=_table(['성취기준','문항 수','전체 정답률(%)']+[f'{level} 정답률(%)' for level in LEVELS],
            [[r['key'],r['n_items'],r['mean_p']*100,
              *[r['by_level'].get(level)*100 if r['by_level'].get(level) is not None else None for level in LEVELS]]
             for r in prepared['overall'].by_standard],bool(prepared['overall'].by_standard))
        origin='현재 분석의 실제 자료 (저장 요약과 별도)' if point.get('source_kind')=='current' else '선택한 회차·학생·저장 버전의 실제 자료'
        if point.get('source_kind')=='analysis-session':
            origin='작업에 포함된 회차 분석 자료 · 전체 작업 저장 시 함께 보존'
        return dict(tabs=tabs,provenance=origin+' · 응답 . = 정답, 숫자 = 선택 답지, 빈칸 = 무응답')
    except (OSError,ValueError,TypeError,KeyError,AttributeError,OverflowError):
        return _summary(point,'저장 버전·학생·회차를 확인하지 못해 상세 연결을 중단했습니다. 요약만 표시합니다.',window)
