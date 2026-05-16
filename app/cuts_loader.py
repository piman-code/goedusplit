"""
예상추정분할점수 조회 엑셀 파서.

샘플 형식 (시트 1장):
    1행: '구분', '성취수준', None, None, None, None
    2행:  None,  'A/B',     'B/C', 'C/D', 'D/E', 'E/미도달'
    3행: '평균',  78.69,     69.52, 58.21, 47.89, 36.57   ← 분할점수로 사용
    4행: '표준편차', 3.44, 4.10, 3.18, 2.91, 1.75
    5행: '최솟값', ...
    6행: '최댓값', ...

위치가 미세하게 달라져도 동작하도록 키워드 기반으로 행/열을 탐색한다.

반환:
    cuts = {'A': 78.69, 'B': 69.52, 'C': 58.21, 'D': 47.89, 'E': 36.57}
    extra = {'std': {...}, 'min': {...}, 'max': {...}}  (있을 때만)
"""

from __future__ import annotations

import openpyxl


_HEADER_TO_LEVEL = {
    "A/B": "A",
    "B/C": "B",
    "C/D": "C",
    "D/E": "D",
    "E/미도달": "E",
    # 옛 표기 호환
    "E/I": "E",
    "E/미이수": "E",
}


def _grid(ws):
    return [list(r) for r in ws.iter_rows(values_only=True)]


def _find_header_row(grid):
    """A/B, B/C, C/D, D/E, E/미도달 5종이 모두 들어있는 행을 찾는다."""
    for r, row in enumerate(grid):
        s = {str(v).strip() for v in row if v is not None}
        if {"A/B", "B/C", "C/D", "D/E"}.issubset(s) and any(
            v in s for v in ("E/미도달", "E/I", "E/미이수")
        ):
            return r
    return None


def _find_row_with_label(grid, label, start_row):
    for r in range(start_row, len(grid)):
        for v in grid[r]:
            if v is None:
                continue
            if str(v).strip() == label:
                return r
    return None


def load_cut_scores(path) -> tuple[dict, dict]:
    """엑셀 -> (cuts, extra). 실패 시 ValueError."""
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.active
    grid = _grid(ws)

    hr = _find_header_row(grid)
    if hr is None:
        raise ValueError(
            "예상추정분할점수 조회 파일에서 머리글 행(A/B, B/C, ...)을 찾지 못했습니다."
        )

    header = grid[hr]
    col_for_level: dict[str, int] = {}
    for c, v in enumerate(header):
        if v is None:
            continue
        key = _HEADER_TO_LEVEL.get(str(v).strip())
        if key:
            col_for_level[key] = c

    if set(col_for_level.keys()) != {"A", "B", "C", "D", "E"}:
        raise ValueError(
            f"머리글 5종(A/B…E/미도달)을 모두 찾지 못했습니다: {col_for_level}"
        )

    def _row_dict(label):
        rr = _find_row_with_label(grid, label, hr + 1)
        if rr is None:
            return None
        out = {}
        for lv, c in col_for_level.items():
            v = grid[rr][c] if c < len(grid[rr]) else None
            try:
                out[lv] = float(v) if v not in (None, "") else None
            except (TypeError, ValueError):
                out[lv] = None
        return out

    cuts = _row_dict("평균")
    if cuts is None or any(v is None for v in cuts.values()):
        raise ValueError("'평균' 행을 찾지 못했거나 값이 비어 있습니다.")

    extra = {}
    for label, key in (("표준편차", "std"), ("최솟값", "min"), ("최댓값", "max")):
        d = _row_dict(label)
        if d is not None:
            extra[key] = d
    return cuts, extra


if __name__ == "__main__":
    import sys, json
    cuts, extra = load_cut_scores(sys.argv[1])
    print("cuts:", cuts)
    print("extra:", json.dumps(extra, ensure_ascii=False, indent=2))
