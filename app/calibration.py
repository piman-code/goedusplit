"""Compare teacher estimates with how students actually did (예측-실측 보정 리포트).

Teachers estimate the correct rate of the *minimally competent* student of each
level. The closest observable group is the lowest third of the students placed
in that level, the same idea the calculator uses for its evidence mode. The
level-wide mean is kept as a reference because it always runs higher.

Actual levels come from the cut scores applied in this analysis, so the
comparison is a reference for the next estimate, not a check of this one.
"""

from __future__ import annotations

import math
from pathlib import Path

LEVELS = ("A", "B", "C", "D", "E")
BOUNDARIES = ("A/B", "B/C", "C/D", "D/E", "E/미도달")
BORDERLINE_SHARE = 1 / 3
LARGE_GAP = 15.0          # %p
FEW_STUDENTS = 5


def borderline_indices(scores: list[float], levels: list[str]) -> dict[str, list[int]]:
    """Lowest third (at least one student) of each level by final score."""
    result = {}
    for level in LEVELS:
        members = sorted((i for i, lv in enumerate(levels) if lv == level), key=lambda i: (scores[i], i))
        if members:
            result[level] = members[:max(1, math.ceil(len(members) * BORDERLINE_SHARE))]
    return result


def _mean_pct(values: list[float]) -> float | None:
    return math.fsum(values) / len(values) * 100 if values else None


def _level_rates(per_student: list[float], levels: list[str], border: dict[str, list[int]]) -> dict:
    """per_student: 0~1 score rate of one item (or item group) for every student."""
    return {
        "all": {lv: _mean_pct([per_student[i] for i, x in enumerate(levels) if x == lv]) for lv in LEVELS},
        "border": {lv: _mean_pct([per_student[i] for i in border.get(lv, [])]) for lv in LEVELS},
    }


def _diffs(predicted: dict, actual: dict) -> dict:
    return {lv: None if actual[lv] is None else actual[lv] - predicted[lv] for lv in LEVELS}


def _mean(values) -> float | None:
    values = [v for v in values if v is not None]
    return math.fsum(values) / len(values) if values else None


def build_calibration(designs: list[dict], exam, levels: list[str]) -> dict:
    """designs: calculator items with type, number, difficulty, target, points, rates and source_item."""
    students = exam.students
    scores = [float(st.final_score) for st in students]
    border = borderline_indices(scores, levels)
    rows, unmatched = [], []
    select = [d for d in designs if d["type"] == "선택형"]
    serdap = [d for d in designs if d["type"] == "서답형"]

    for design in select:
        item = design.get("source_item")
        if item is None:
            unmatched.append(f"선택형 {int(design['number'])}번")
            continue
        per_student = [1.0 if str(st.answers.get(item.number, "")).strip() == "." else 0.0 for st in students]
        rows.append(_row(design["type"], str(int(design["number"])), design["difficulty"], design.get("target", ""),
                         float(design["points"]), design["rates"], _level_rates(per_student, levels, border)))

    serdap_max = math.fsum(float(it.score) for it in exam.items if it.item_type == "서답형")
    if serdap and serdap_max > 0:
        points = math.fsum(float(d["points"]) for d in serdap)
        predicted = {lv: math.fsum(float(d["points"]) * float(d["rates"][lv]) for d in serdap) / points for lv in LEVELS}
        per_student = [min(1.0, max(0.0, float(st.serdap_score) / serdap_max)) for st in students]
        numbers = ", ".join(str(int(d["number"])) for d in sorted(serdap, key=lambda d: int(d["number"])))
        rows.append(_row("서답형 묶음", numbers, "", "", points, predicted, _level_rates(per_student, levels, border)))
    elif serdap:
        unmatched.extend(f"서답형 {int(d['number'])}번" for d in serdap)

    designed = {(d["type"], int(d["number"])) for d in designs}
    not_designed = [f"{it.item_type} {it.number}번" for it in exam.items if (it.item_type, int(it.number)) not in designed]

    total = math.fsum(row["points"] for row in rows)
    cuts = []
    for level, boundary in zip(LEVELS, BOUNDARIES):
        predicted = math.fsum(row["points"] * row["predicted"][level] / 100 for row in rows)
        usable = all(row["border"][level] is not None for row in rows) and bool(rows)
        actual = math.fsum(row["points"] * row["border"][level] / 100 for row in rows) if usable else None
        cuts.append({
            "boundary": boundary, "level": level,
            "predicted_scaled": predicted / total * 100 if total else None,
            "actual_scaled": actual / total * 100 if (usable and total) else None,
        })
    counts = {lv: sum(1 for x in levels if x == lv) for lv in LEVELS}
    return {
        "rows": rows,
        "unmatched": unmatched,
        "not_designed": not_designed,
        "counts": counts,
        "border_counts": {lv: len(border.get(lv, [])) for lv in LEVELS},
        "bias": {lv: _mean(row["diff"][lv] for row in rows) for lv in LEVELS},
        "bias_by_difficulty": {
            diff: {lv: _mean(row["diff"][lv] for row in rows if row["difficulty"] == diff) for lv in LEVELS}
            for diff in ("쉬움", "보통", "어려움") if any(row["difficulty"] == diff for row in rows)
        },
        "large_gaps": sum(1 for row in rows for lv in LEVELS if row["diff"][lv] is not None and abs(row["diff"][lv]) >= LARGE_GAP),
        "cuts": cuts,
        "total_points": total,
    }


def _row(kind, number, difficulty, target, points, predicted, actual) -> dict:
    predicted = {lv: float(predicted[lv]) for lv in LEVELS}
    return {
        "type": kind, "number": number, "difficulty": difficulty, "target": target, "points": points,
        "predicted": predicted, "border": actual["border"], "all": actual["all"],
        "diff": _diffs(predicted, actual["border"]),
    }


def summary_lines(report: dict) -> list[str]:
    lines = []
    for level in LEVELS:
        bias = report["bias"][level]
        n = report["counts"][level]
        if bias is None:
            lines.append(f"{level}: 이 수준 학생이 없어 비교할 수 없습니다.")
            continue
        direction = "높게" if bias < 0 else "낮게"
        caution = " (학생 수가 적어 참고만)" if n < FEW_STUDENTS else ""
        if abs(bias) < 2.5:
            lines.append(f"{level}: 예측과 실측이 평균 {abs(bias):.1f}%p 안쪽으로 가깝습니다{caution}.")
        else:
            lines.append(f"{level}: 경계 학생의 실제 정답률을 평균 {abs(bias):.1f}%p {direction} 예측했습니다{caution}.")
    return lines


def write_calibration_workbook(path: str | Path, report: dict) -> None:
    import openpyxl
    from openpyxl.styles import Font, PatternFill

    workbook = openpyxl.Workbook()
    summary = workbook.active
    summary.title = "요약"
    summary.append(["예측-실측 보정 리포트. 실측 = 각 성취수준 하위 1/3(경계 학생) 정답률. 학생 개인정보는 들어가지 않습니다."])
    summary.append(["실제 성취수준은 이번 분석의 분할점수로 나눈 결과라, 다음 예측을 위한 참고 자료입니다."])
    summary.append([])
    summary.append(["수준", "학생 수", "경계 학생 수", "평균 차이(실측-예측, %p)"])
    for level in LEVELS:
        summary.append([level, report["counts"][level], report["border_counts"][level], report["bias"][level]])
    summary.append([])
    summary.append(["경계", "예측 100점 환산", "실측 100점 환산", "차이"])
    for cut in report["cuts"]:
        diff = None if cut["actual_scaled"] is None else cut["actual_scaled"] - cut["predicted_scaled"]
        summary.append([cut["boundary"], cut["predicted_scaled"], cut["actual_scaled"], diff])
    summary.append([])
    for line in summary_lines(report):
        summary.append([line])
    if report["unmatched"]:
        summary.append(["분석 자료에서 찾지 못한 예측 문항: " + ", ".join(report["unmatched"])])
    if report["not_designed"]:
        summary.append(["예측값이 없는 시험 문항: " + ", ".join(report["not_designed"])])

    items = workbook.create_sheet("문항별")
    headers = ["구분", "번호", "난이도", "목표수준", "배점"]
    for level in LEVELS:
        headers += [f"{level} 예측", f"{level} 실측(경계)", f"{level} 차이", f"{level} 수준 평균"]
    items.append(headers)
    for row in report["rows"]:
        values = [row["type"], row["number"], row["difficulty"], row["target"], row["points"]]
        for level in LEVELS:
            values += [row["predicted"][level], row["border"][level], row["diff"][level], row["all"][level]]
        items.append(values)
    for sheet in workbook:
        for cells in sheet.iter_rows():
            for cell in cells:
                if isinstance(cell.value, str):
                    cell.data_type = "s"
                elif isinstance(cell.value, float):
                    cell.number_format = "0.0"
    for cell in items[1]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="DDEDEA")
    items.freeze_panes = "F2"
    workbook.save(path)
