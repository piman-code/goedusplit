"""Read-only discovery and preflight of distinct exam bundles."""
from pathlib import Path
import re
import unicodedata
import openpyxl
from .rounds import parse_round, parse_year, round_name
from .data_loader import _response_exam_evidence, load_exam, apply_perform, PATH_SEPARATOR
from .perform_loader import load_perform_many
from .cuts_loader import load_cut_scores

RULES = {
    'response': ('정오표', '학생답안', '응답', 'answer'),
    'iteminfo': ('문항정보', 'iteminfo'),
    'cuts': ('분할점수', 'cutscore'),
    'perform': ('수행평가', '수행결과', 'performance'),
    'grade5_report': ('교과목별일람표', '일람표'),
}

def _norm(value):
    return re.sub(r'\s+', '', unicodedata.normalize('NFC', str(value or '')))

def subjects_compatible(left, right):
    """Compare optional numeric annotations without rewriting saved subject identity."""
    left, right = (_norm(value).replace('（', '(').replace('）', ')') for value in (left, right))
    if left == right:
        return True
    pattern = r'^(.*)[(（]([0-9]+)[)）]$'
    a, b = re.fullmatch(pattern, left), re.fullmatch(pattern, right)
    # Two explicit, different annotations remain distinct. This is deliberately
    # not a general removal of parentheses, course numbers, or name suffixes.
    if a and not b:
        return a.group(1) == right
    if b and not a:
        return b.group(1) == left
    return False


def _evidence_matches(field, expected, values):
    if not values or expected is None:
        return True
    if field == '과목':
        return all(subjects_compatible(expected, value) for value in values)
    return expected in values


def _metadata(path):
    # Only labelled header text is used; student rows are neither logged nor retained.
    book = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        texts = [unicodedata.normalize('NFC', path.stem)]
        for row in book.active.iter_rows(min_row=1, max_row=12, values_only=True):
            for value in row:
                if isinstance(value, str) and re.search(r'학년도|학기|과목\s*[:：]|수학\s*[:：]|\)\s*과목', value):
                    texts.append(unicodedata.normalize('NFC', value))
    finally:
        book.close()
    found = {key:set() for key in ('학년도','학기','차수','학년','과목')}
    for text in texts:
        for key, values in _response_exam_evidence(text).items():
            if key == '과목':
                # NEIS report headers place an explicitly labelled max-score
                # field after the subject on the same line.
                values = {re.split(r'만점[:：]', value, maxsplit=1)[0] for value in values}
            found[key].update(values)
        for subject in re.findall(r'\(\s*((?:[^()]|\([0-9]+\))+?)\s*\)\s*과목', text):
            found['과목'].add(_norm(subject))
    # Subject parentheses in filenames, never class labels.
    for label in re.findall(r'[（(]((?:[^()（）]|[(（][0-9]+[)）])+)[)）]', texts[0]):
        if re.search(r'[가-힣A-Za-z]', label) and not re.search(r'학년|학기|반|학급|차|샘플|공통자료', label):
            found['과목'].add(_norm(label))
    subjects = found['과목']
    if len(subjects) > 1 and all(subjects_compatible(a, b) for a in subjects for b in subjects):
        found['과목'] = {max(subjects, key=lambda value: (bool(re.search(r'[(（][0-9]+[)）]$', value)), len(value)))}
    return found

def discover_round_groups(directory, current_round_text=''):
    records=[]
    for path in sorted(Path(directory).glob('*.xlsx')):
        if path.name.startswith('~'):continue
        name=_norm(path.stem).lower()
        category=next((key for key, words in RULES.items() if any(word in name for word in words)),None)
        if not category:continue
        try: evidence=_metadata(path)
        except Exception:continue  # Invalid workbooks still use the existing individual-file flow.
        records.append(dict(path=str(path),category=category,evidence=evidence,
                            common=('공통자료' in name or '전회차' in name)))
    groups={}
    current_sem=parse_round(current_round_text)[0]
    for record in records:
        if record['category']!='response':continue
        ev=record['evidence']
        values=[next(iter(ev[k])) if len(ev[k])==1 else None for k in ('학년도','학기','차수','학년','과목')]
        if not ev['학기']:values[1]=current_sem
        key=tuple(values)
        group=groups.setdefault(key,dict(key=key,label=f"{values[0] or '학년도 미상'} {round_name(values[1],values[2])} · {values[4] or '과목 미상'}",response=[],perform=[],perform_candidates=[],item_candidates=[],cuts_candidates=[],grade5_report_candidates=[],iteminfo='',cuts='',grade5_report='',problems=[]))
        group['response'].append(record['path'])
        if any(len(v)>1 for v in ev.values()):group['problems'].append('정오표 안 시험 정보 충돌')
        if values[1] is None or values[2] is None:group['problems'].append('학기·차수 확인 필요')
        elif values[2] not in (1,2):group['problems'].append('지원 회차 확인 필요: 1차·2차 외 자료')
    for key,group in groups.items():
        if group['problems']:
            continue
        for category in ('iteminfo','cuts','perform','grade5_report'):
            matches=[]
            for record in records:
                if record['category']!=category:continue
                ev=record['evidence']
                if any(len(v)>1 for v in ev.values()):continue
                # Performing task numbers are not written-exam numbers.
                relevant=('학년도','학기','학년','과목') if category=='perform' else ('학년도','학기','차수','학년','과목')
                mapping=dict(zip(('학년도','학기','차수','학년','과목'),key))
                if any(not _evidence_matches(k, mapping[k], ev[k]) for k in relevant):continue
                compatible_subjects = {g[4] for g in groups if g[4] is not None
                                       and _evidence_matches('과목', g[4], ev['과목'])}
                if ev['과목'] and any(not subjects_compatible(a,b) for a in compatible_subjects for b in compatible_subjects):
                    candidate_key = 'item_candidates' if category=='iteminfo' else category+'_candidates'
                    group[candidate_key].append(record['path'])
                    continue
                if category=='perform':
                    if not ev['학기'] or (key[4] is not None and not ev['과목']):
                        group['perform_candidates'].append(record['path'])
                        continue
                elif not record['common'] and (not ev['차수'] or not ev['학기']):
                    if category=='iteminfo':group['item_candidates'].append(record['path'])
                    continue
                # Unknown subject/year/grade cannot silently span distinct cohorts.
                if any(not ev[field] and len({k[index] for k in groups if k[index] is not None})>1
                       for field,index in (('학년도',0),('학년',3),('과목',4))):continue
                matches.append(record['path'])
            if category=='perform':
                group[category]=matches
            elif len(matches)==1:group[category]=matches[0]
            elif len(matches)>1:
                group['problems'].append(f'{category}: 중복 후보 선택 필요')
                candidate_key = 'item_candidates' if category=='iteminfo' else category+'_candidates'
                group[candidate_key].extend(matches)
        if not group['iteminfo']:
            group.setdefault('warnings', []).append('문항정보표 없음: 학생 점수만 분석하며 문항별 결과는 표시하지 않습니다.')
    return sorted(groups.values(),key=lambda g:tuple(str(v or '') for v in g['key']))

def prepare_round_groups(groups, cut_scores, pencil_weight, perform_weight):
    prepared=[]
    for group in groups:
        if group['problems']:raise ValueError(group['label']+' : '+' / '.join(group['problems']))
        expected=dict(zip(('학년도','학기','차수','학년','과목'),group['key']))
        for category in ('response','iteminfo','cuts','perform','grade5_report'):
            paths=group[category] if isinstance(group[category],list) else [group[category]]
            for path in filter(None,paths):
                evidence=_metadata(Path(path))
                fields=('학년도','학기','학년','과목') if category=='perform' else tuple(expected)
                if any(len(evidence[field])>1 or not _evidence_matches(field, expected[field], evidence[field]) for field in fields):
                    raise ValueError(group['label']+' : 선택 자료의 학년도·학기·회차·학년·과목이 다릅니다.')
        exam=load_exam(group['iteminfo'],PATH_SEPARATOR.join(group['response']))
        year,sem,number,grade,subject=group['key']
        if subject and exam.subject and not subjects_compatible(subject,exam.subject):raise ValueError('정오표와 문항정보의 과목이 다릅니다.')
        exam.semester=f"{str(year)+'학년도 ' if year else ''}{sem}학기 {number}차"
        if subject and not exam.subject:exam.subject=subject
        exam.cut_scores=load_cut_scores(group['cuts'])[0] if group['cuts'] else dict(cut_scores)
        perform=load_perform_many(PATH_SEPARATOR.join(group['perform'])) if group['perform'] else None
        pw,sw=pencil_weight,perform_weight
        if perform is None:
            pw,sw=100,0
            message='지필 원점수만 표시 · 수행자료 없음(학기총점 아님)'
            if message not in group.setdefault('warnings', []):group['warnings'].append(message)
        if perform is not None and group.get('use_file_perform_ratio',False):
            sw=float(perform.ratio_total)
            if not 0 < sw <= 100:raise ValueError('수행평가 파일 반영비율을 확인해 주세요.')
            pw=100-sw
        apply_perform(exam,perform,pw,sw)
        prepared.append((group,exam,perform))
    return prepared
