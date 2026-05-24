from __future__ import annotations

import math
import re


GRADE5_CUMULATIVE = [("1", 10.0), ("2", 34.0), ("3", 66.0), ("4", 90.0), ("5", 100.0)]


def format_score(value: float) -> str:
    text = f"{float(value):.2f}"
    return text.rstrip("0").rstrip(".")


def _score_or_none(value, max_score: float = 100.0) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        score = float(value)
        if 0 <= score <= max_score + max(1.0, max_score * 0.01):
            return score
    return None


def _detect_max_score(ws) -> float:
    for row in ws.iter_rows(min_row=1, max_row=min(ws.max_row, 12), values_only=True):
        text = " ".join(str(v) for v in row if v not in (None, ""))
        match = re.search(r"만점\s*[:：]\s*([0-9]+(?:\.[0-9]+)?)", text)
        if match:
            try:
                return max(1.0, float(match.group(1)))
            except Exception:
                pass
    return 100.0


def _detect_subject(ws, fallback: str) -> str:
    joined = []
    for row in ws.iter_rows(min_row=1, max_row=min(ws.max_row, 8), values_only=True):
        joined.append(" ".join(str(v) for v in row if v not in (None, "")))
    text = " ".join(joined)
    match = re.search(r"교과목\s*[:：]\s*(.*?)\s+만점", text)
    if match and match.group(1).strip():
        return match.group(1).strip()
    for line in joined:
        if "교과목" in line:
            return line.strip()
    return fallback


def _extract_matrix_scores(ws, max_score: float) -> tuple[list[float], str]:
    header_row = None
    for row_idx in range(1, min(ws.max_row, 30) + 1):
        first = str(ws.cell(row_idx, 1).value or "").replace(" ", "")
        filled_after = [
            col_idx
            for col_idx in range(2, ws.max_column + 1)
            if ws.cell(row_idx, col_idx).value not in (None, "")
        ]
        if ("반번호" in first or first in {"번호", "반/번호"}) and len(filled_after) >= 2:
            header_row = row_idx
            break
    if not header_row:
        return [], ""

    columns = [
        col_idx
        for col_idx in range(2, ws.max_column + 1)
        if ws.cell(header_row, col_idx).value not in (None, "")
    ]
    scores: list[float] = []
    row_count = 0
    for row_idx in range(header_row + 1, ws.max_row + 1):
        first_text = str(ws.cell(row_idx, 1).value or "").replace(" ", "")
        if any(key in first_text for key in ("응시생수", "총점", "평균", "표준편차")):
            break
        row_scores = []
        for col_idx in columns:
            score = _score_or_none(ws.cell(row_idx, col_idx).value, max_score)
            if score is not None:
                row_scores.append(score)
        if row_scores:
            scores.extend(row_scores)
            row_count += 1
    return scores, f"반번호 점수표 · {len(columns)}개 반 열 × {row_count}개 번호 행"


def _extract_column_scores(ws, max_score: float) -> tuple[list[float], str]:
    preferred = [
        ("환산점수", 120), ("환산점", 115), ("과목총점", 105), ("총점", 100),
        ("합계", 90), ("원점수", 85), ("점수", 65),
    ]
    avoid = ("반번호", "번호", "학번", "성명", "이름", "석차", "등급", "성취", "평균", "표준", "응시", "문항", "배점")
    best: tuple[int, int, int, list[float], str] | None = None
    for header_row in range(1, min(ws.max_row, 35) + 1):
        headers = [
            str(ws.cell(header_row, col_idx).value or "").replace(" ", "")
            for col_idx in range(1, ws.max_column + 1)
        ]
        if sum(1 for header in headers if header) < 2:
            continue
        for col_idx, header in enumerate(headers, start=1):
            if not header or any(word in header for word in avoid):
                continue
            priority = 0
            for term, weight in preferred:
                if term in header:
                    priority = max(priority, weight)
            if priority <= 0:
                continue
            values = []
            for row_idx in range(header_row + 1, ws.max_row + 1):
                score = _score_or_none(ws.cell(row_idx, col_idx).value, max_score)
                if score is not None:
                    values.append(score)
            if len(values) < 3:
                continue
            candidate = (priority, len(values), -header_row, values, f"'{header}' 열 · {len(values)}명")
            if best is None or candidate[:3] > best[:3]:
                best = candidate
    if best:
        return best[3], best[4]
    return [], ""


def load_grade5_cut_reports(path: str) -> list[dict]:
    import openpyxl

    workbook = openpyxl.load_workbook(path, data_only=True, read_only=False)
    reports = []
    for sheet in workbook.worksheets:
        max_score = _detect_max_score(sheet)
        subject = _detect_subject(sheet, sheet.title)
        scores, source_note = _extract_matrix_scores(sheet, max_score)
        if len(scores) < 3:
            scores, source_note = _extract_column_scores(sheet, max_score)
        if len(scores) >= 3:
            reports.append({
                "sheet": sheet.title,
                "subject": subject,
                "max_score": max_score,
                "scores": scores,
                "source_note": source_note,
            })
    if not reports:
        raise ValueError("점수표를 찾지 못했습니다. '반번호' 점수표 또는 환산점수/총점/원점수 열이 있는 엑셀인지 확인해 주세요.")
    return reports


def _rounded_cumulative_limits(total: int, cumulative: list[tuple[str, float]]) -> list[tuple[str, int, float]]:
    limits = []
    for grade, boundary in cumulative:
        limit = max(1, min(total, int(math.floor(total * boundary / 100.0 + 0.5))))
        limits.append((grade, limit, boundary))
    if limits:
        last_grade, _, last_boundary = limits[-1]
        limits[-1] = (last_grade, total, last_boundary)
    return limits


def _grade_for_rank(rank: float, limits: list[tuple[str, int, float]]) -> str:
    for grade, limit, _ in limits:
        if rank <= limit + 1e-9:
            return grade
    return limits[-1][0]


def _grade_for_middle_percent(mid_rank: float, total: int, cumulative: list[tuple[str, float]]) -> str:
    pct = mid_rank / total * 100.0
    for grade, boundary in cumulative:
        if pct <= boundary + 1e-9:
            return grade
    return cumulative[-1][0]


def official_grade_groups(scores: list[float], cumulative: list[tuple[str, float]]) -> list[dict]:
    """Return score groups graded by school-record rules.

    Normal boundaries use rounded cumulative student counts. If a same-score
    group crosses a boundary, that group uses middle-rank percentage.
    """
    values = [float(score) for score in scores]
    total = len(values)
    if total == 0:
        return []
    counts = {value: values.count(value) for value in set(values)}
    limits = _rounded_cumulative_limits(total, cumulative)
    groups = []
    greater = 0
    for score in sorted(counts, reverse=True):
        count = counts[score]
        start = greater + 1
        end = greater + count
        mid = start + (count - 1) / 2.0
        crosses_boundary = any(start <= limit < end for _, limit, _ in limits[:-1])
        if crosses_boundary:
            grade = _grade_for_middle_percent(mid, total, cumulative)
        else:
            grade = _grade_for_rank(start, limits)
        groups.append({
            "score": score,
            "count": count,
            "start": start,
            "end": end,
            "middle": mid,
            "middle_pct": mid / total * 100.0,
            "grade": grade,
            "crosses_boundary": crosses_boundary,
        })
        greater += count
    return groups


def relative_grade_labels(scores: list[float], cumulative: list[tuple[str, float]]) -> list[str]:
    groups = official_grade_groups(scores, cumulative)
    grade_by_score = {group["score"]: group["grade"] for group in groups}
    return [grade_by_score.get(float(score), cumulative[-1][0]) for score in scores]


def relative_grade_cut_points(scores: list[float], cumulative: list[tuple[str, float]], prefix: str) -> list[dict]:
    groups = official_grade_groups(scores, cumulative)
    cut_points = []
    for grade, _ in cumulative[:-1]:
        grade_scores = [group["score"] for group in groups if group["grade"] == grade]
        if not grade_scores:
            continue
        cut_points.append({
            "score": min(grade_scores),
            "label": f"{prefix} {grade}/{int(grade) + 1 if str(grade).isdigit() else ''}".rstrip("/"),
            "kind": prefix,
        })
    return cut_points


def grade5_cut_summary(scores: list[float]) -> dict:
    sorted_scores = sorted([float(value) for value in scores], reverse=True)
    total = len(sorted_scores)
    groups = official_grade_groups(sorted_scores, GRADE5_CUMULATIVE)
    cut_rows = []
    for grade, boundary in GRADE5_CUMULATIVE[:-1]:
        rank = max(1, min(total, int(math.floor(total * boundary / 100.0 + 0.5))))
        grade_groups = [group for group in groups if group["grade"] == grade]
        if grade_groups:
            score = min(group["score"] for group in grade_groups)
            included = sum(group["count"] for group in grade_groups)
            boundary_tie = any(group["crosses_boundary"] and group["score"] == score for group in grade_groups)
        else:
            score = sorted_scores[rank - 1]
            included = 0
            boundary_tie = False
        cut_rows.append({
            "grade": grade,
            "boundary": boundary,
            "rank": rank,
            "score": score,
            "included": included,
            "included_pct": included / total * 100.0,
            "boundary_tie": boundary_tie,
        })
    labels = relative_grade_labels(sorted_scores, GRADE5_CUMULATIVE)
    counts = {grade: labels.count(grade) for grade, _ in GRADE5_CUMULATIVE}
    return {
        "n": total,
        "min": min(sorted_scores),
        "max": max(sorted_scores),
        "mean": sum(sorted_scores) / total,
        "cut_rows": cut_rows,
        "counts": counts,
    }
