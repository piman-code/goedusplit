"""
수행평가 강의실별 일람표(NEIS 다운로드) 파서.

샘플 형식:
    2025학년도   1학기 ... 일반계   3학년      5
    교과목 : 수학:확률과 통계(3)
    ...
    7행 헤더: '반/번호', None, '성명',
              '문제해결능력평가(만점 15.00,15.00%)',
              '통계카드뉴스제작(만점 15.00,15.00%)',
              '수학독서논술(만점 10.00,10.00%)',
              '합 계', '비고', ...
    8행~: ('1/4', 2023000234.0, '김경은', 13.0, 15.0, 10.0, 38.0, ...)

반환:
    PerformData(
        areas=[(이름, 만점, 반영비율%)...],
        max_total=15+15+10=40, ratio_total=40.0(%),
        records: dict 학번 -> (반/번호, 이름, 영역점수list, 합계, 100점환산)
    )

100점 환산 = (합계 / 만점합계) * 100
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import openpyxl


_AREA_RE = re.compile(r"\(만점\s*([0-9.]+)\s*,\s*([0-9.]+)%\)")


@dataclass
class PerformArea:
    name: str
    max_score: float
    ratio_pct: float


@dataclass
class PerformRecord:
    sid: str           # 학번 (가능하면 정수 문자열)
    class_no: str      # '1/4'
    name: str          # 성명
    scores: dict       # 영역명 -> 점수
    total: float       # 합계 (원점수)
    pct100: float      # 100점 환산 (총합 / 만점합 * 100)


@dataclass
class PerformData:
    subject: str = ""
    areas: list = field(default_factory=list)
    max_total: float = 0.0
    ratio_total: float = 0.0   # 영역 반영비율 합 (%)
    records: dict = field(default_factory=dict)   # sid -> PerformRecord
    by_classno: dict = field(default_factory=dict)  # '1/4' -> PerformRecord


def _grid(ws):
    return [list(r) for r in ws.iter_rows(values_only=True)]


def _find_header_row(grid):
    for r, row in enumerate(grid):
        s = {str(v).strip() for v in row if v is not None}
        if "반/번호" in s and "성명" in s and ("합 계" in s or "합계" in s):
            return r
    return None


def load_perform(path) -> PerformData:
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.active
    grid = _grid(ws)

    hr = _find_header_row(grid)
    if hr is None:
        raise ValueError("수행평가 파일에서 머리글 행(반/번호·성명·합 계)을 찾지 못했습니다.")
    header = grid[hr]

    # 컬럼 위치 잡기
    col_classno = col_sid = col_name = col_total = None
    area_cols = []  # (col_idx, name, max, ratio)
    for c, v in enumerate(header):
        if v is None:
            continue
        s = str(v).strip()
        if s == "반/번호":
            col_classno = c
        elif s == "성명":
            col_name = c
        elif s in ("합 계", "합계"):
            col_total = c
        elif "(만점" in s and "%)" in s:
            m = _AREA_RE.search(s)
            if m:
                # 헤더에서 '(만점 X, Y%)' 부분 제거 → 영역명
                name = _AREA_RE.sub("", s).strip()
                area_cols.append((c, name, float(m.group(1)), float(m.group(2))))

    # '반/번호' 다음 셀이 학번 (정수)
    if col_classno is None or col_total is None or not area_cols:
        raise ValueError(f"필수 컬럼 인식 실패: classno={col_classno} total={col_total} areas={len(area_cols)}")
    col_sid = col_classno + 1   # 양식상 학번은 반/번호 우측에 위치

    pd_obj = PerformData()
    pd_obj.areas = [PerformArea(name=n, max_score=mx, ratio_pct=rt) for _, n, mx, rt in area_cols]
    pd_obj.max_total = sum(a.max_score for a in pd_obj.areas)
    pd_obj.ratio_total = sum(a.ratio_pct for a in pd_obj.areas)

    # 과목명 추출
    for r in range(hr):
        for v in grid[r]:
            if v is None:
                continue
            s = str(v)
            if "교과목" in s:
                m = re.search(r"교과목\s*[:：]\s*([^\n,]+)", s)
                if m:
                    pd_obj.subject = m.group(1).strip()

    # 학생 데이터
    for r in range(hr + 1, len(grid)):
        row = grid[r]
        cls_v = row[col_classno] if col_classno < len(row) else None
        if cls_v is None or "/" not in str(cls_v):
            continue
        sid_v = row[col_sid] if col_sid < len(row) else None
        try:
            sid = str(int(float(sid_v))) if sid_v not in (None, "") else ""
        except (TypeError, ValueError):
            sid = str(sid_v).strip()
        name = str(row[col_name]).strip() if col_name is not None and row[col_name] else ""
        scores = {}
        for c, n, _, _ in area_cols:
            v = row[c] if c < len(row) else None
            try:
                scores[n] = float(v) if v not in (None, "") else 0.0
            except (TypeError, ValueError):
                scores[n] = 0.0
        try:
            total = float(row[col_total]) if row[col_total] not in (None, "") else sum(scores.values())
        except (TypeError, ValueError):
            total = sum(scores.values())
        pct = (total / pd_obj.max_total * 100.0) if pd_obj.max_total > 0 else 0.0
        rec = PerformRecord(sid=sid, class_no=str(cls_v).strip(), name=name,
                            scores=scores, total=total, pct100=pct)
        if sid:
            pd_obj.records[sid] = rec
        pd_obj.by_classno[str(cls_v).strip()] = rec
    return pd_obj


if __name__ == "__main__":
    import sys
    p = load_perform(sys.argv[1])
    print(f"과목={p.subject}  영역수={len(p.areas)}  만점합={p.max_total}  비율합={p.ratio_total}%")
    for a in p.areas:
        print(f"  - {a.name}: 만점{a.max_score} 반영{a.ratio_pct}%")
    for k, r in list(p.records.items())[:5]:
        print(f"  학번 {k} ({r.class_no} {r.name}) 합={r.total}  100환산={r.pct100:.2f}")
