"""Pure portfolio presentation model. Never changes or writes snapshot history.

A graph contains one student and one subject. Missing historical class means
remain unknown; present-day identity mappings are never used to infer them.
"""
from __future__ import annotations

import copy
from datetime import datetime
import math
import re


def _number(value):
    if isinstance(value, bool) or value is None or value == '':
        return None
    try:
        result = float(value)
    except (ValueError, TypeError):
        return None
    return result if math.isfinite(result) else None


def _integer(value):
    number = _number(value)
    return int(number) if number is not None and number == int(number) else None


def _exam_identity(row):
    text = str(row.get('semester') or row.get('term') or '')
    year = _integer(row.get('year'))
    semester = _integer(row.get('semester_no'))
    round_no = _integer(row.get('round_no', row.get('round')))
    for pattern, field in ((r'(?<!\d)(20\d{2})\s*학년도', 'year'),
                           (r'([12])\s*학기', 'semester'),
                           (r'(\d+)\s*차', 'round')):
        match = re.search(pattern, text)
        if match:
            if field == 'year' and year is None: year = int(match[1])
            if field == 'semester' and semester is None: semester = int(match[1])
            if field == 'round' and round_no is None: round_no = int(match[1])
    return year, semester, round_no


def _saved_order(row):
    try:
        stamp = datetime.fromisoformat(str(row.get('saved_at', '')).replace('Z', '+00:00'))
        # Timestamp offsets are respected; naive local dates remain deterministic.
        value = stamp.timestamp() if stamp.tzinfo else (stamp - datetime(1970, 1, 1)).total_seconds()
    except (ValueError, TypeError, OverflowError):
        value = float('-inf')
    # Legacy timestamps have only seconds; filesystem nanoseconds disambiguate
    # their save order before the random UUID filename fallback.
    mtime = row.get('snapshot_mtime_ns', 0)
    if not isinstance(mtime, int) or isinstance(mtime, bool):
        mtime = 0
    return bool(row.get('is_current_analysis') or row.get('is_current_preview')), value, mtime, str(row.get('snapshot_path', ''))


def build_timeline(rows, student_key, subject=None):
    """Return detached points and complete history for an already-hashed identity.

    Required row identity is student_hash. Optional exam fields are year,
    semester_no, round_no, grade; class_mean must be snapshot-time evidence.
    Unknown exam identities are kept separate instead of guessing equivalence.
    A missing subject selects the current-preview subject, then a stable subject.
    """
    hashed = str(student_key or '').removeprefix('hash:')
    history = [copy.deepcopy(row) for row in rows
               if hashed and str(row.get('student_hash', '')) == hashed]
    subjects = sorted({str(row.get('subject', '')) for row in history if row.get('subject')})
    if subject is None or subject == '':
        current = [row for row in history if (row.get('is_current_analysis') or row.get('is_current_preview')) and row.get('subject')]
        subject = str(max(current, key=_saved_order)['subject']) if current else (subjects[0] if subjects else '')
    selected = str(subject)
    grouped = {}
    for index, row in enumerate(history):
        if str(row.get('subject', '')) != selected:
            continue
        identity = _exam_identity(row)
        key = ('exam', *identity, str(row.get('grade', ''))) if all(v is not None for v in identity) else ('unknown', index)
        grouped.setdefault(key, []).append(row)
    points = []
    for revisions in grouped.values():
        row = copy.deepcopy(max(revisions, key=_saved_order))
        year, semester, round_no = _exam_identity(row)
        label = ' '.join(part for part in (
            f'{year}학년도' if year is not None else '',
            f'{semester}학기' if semester is not None else '',
            f'{round_no}차' if round_no is not None else '') if part)
        row.update(year=year, semester_no=semester, round_no=round_no,
                   label=label or str(row.get('term') or '회차 미확인'),
                   score=_number(row.get('score')), class_mean=_number(row.get('class_mean')),
                   is_current_preview=bool(row.get('is_current_preview')),
                   revision_count=len(revisions))
        points.append(row)
    points.sort(key=lambda row: (row['year'] if row['year'] is not None else 9999,
                                  row['semester_no'] if row['semester_no'] is not None else 99,
                                  row['round_no'] if row['round_no'] is not None else 999,
                                  _saved_order(row)))
    unknown_points=[point for point in points if any(point[key] is None for key in ('year','semester_no','round_no'))]
    known_points=[point for point in points if all(point[key] is not None for key in ('year','semester_no','round_no'))]
    return {'student_key': student_key, 'subjects': subjects,
            'selected_subject': selected, 'points': known_points, 'unknown_points': unknown_points, 'history': history,
            'selection_policy': '같은 회차는 현재 분석 우선, 그 외에는 최근 저장 표시 · 상세 이력은 모두 보존'}
