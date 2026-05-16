"""
성취평가 결과 분석.

PPT(슬라이드 27~52)에 명시된 다음 지표들을 계산한다.

- 성취수준별 학생 분포(고정 분할점수: 90/80/70/60/40, 사용자 변경 가능)
- 학급별 평균/표준편차
- 문항 난이도(정답률 기반): KICE 기준
- 문항 변별도: point-biserial 상관 (item-total)
- 평가도구 신뢰도: Cronbach's α
- 답지반응분포 (전체/성취수준별)
- 성취기준별 평균 정답률
- 내용영역별 평균 정답률

수치는 가급적 NumPy 한 번 통과로 계산해, 표본이 1만 명 수준까지는 즉시 응답 가능.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable

import numpy as np

from .data_loader import ExamData, ItemInfo, StudentResponse


# ---------------------------------------------------------------------------
# 기본 헬퍼
# ---------------------------------------------------------------------------

LEVELS = ["A", "B", "C", "D", "E", "미도달"]
LEVELS_AE = ["A", "B", "C", "D", "E"]   # 미도달 제외 5단계


def grade_level(total: float, cuts: dict) -> str:
    """과목총점 -> A~E + 미도달 성취도.

    원본 KICE Shiny 웹앱 도움말 기준:
      "성취수준 판정은 반올림하여 정수로 변환한 '원점수' 기준으로 실시함."
    이를 반영해 비교 전에 round()로 정수화한다.
    """
    t = round(float(total))
    if t >= cuts["A"]:
        return "A"
    if t >= cuts["B"]:
        return "B"
    if t >= cuts["C"]:
        return "C"
    if t >= cuts["D"]:
        return "D"
    if t >= cuts["E"]:
        return "E"
    return "미도달"


def difficulty_label(p_value: float) -> str:
    """정답률(p) 기준 KICE 난이도 라벨 (PPT 슬라이드 32 참고)."""
    # 0~0.20: 매우 어려움 / 0.20~0.40: 어려움 / 0.40~0.60: 보통 /
    # 0.60~0.80: 쉬움 / 0.80~1.00: 매우 쉬움
    if p_value < 0.20:
        return "매우 어려움"
    if p_value < 0.40:
        return "어려움"
    if p_value < 0.60:
        return "보통"
    if p_value < 0.80:
        return "쉬움"
    return "매우 쉬움"


def discrim_label(d: float) -> str:
    """변별도 라벨 (PPT 슬라이드 34 참고)."""
    if d >= 0.40:
        return "매우 양호"
    if d >= 0.30:
        return "양호"
    if d >= 0.20:
        return "보통"
    if d >= 0.10:
        return "낮음"
    return "매우 낮음 (재검토)"


def reliability_label(alpha: float) -> str:
    """Cronbach α 라벨 (PPT 슬라이드 37 참고)."""
    if alpha >= 0.90:
        return "매우 우수"
    if alpha >= 0.80:
        return "우수"
    if alpha >= 0.70:
        return "양호"
    if alpha >= 0.60:
        return "보통"
    return "재검토 필요"


# ---------------------------------------------------------------------------
# 행렬 만들기
# ---------------------------------------------------------------------------

def build_score_matrix(exam: ExamData) -> tuple[np.ndarray, np.ndarray, list[ItemInfo]]:
    """
    선택형 채점 행렬을 반환.
      - score_matrix[s, i] = 학생 s의 문항 i에 대한 0/1 정오 (정답=1, 오답=0)
      - choice_matrix[s, i] = 학생 s가 고른 답지 번호. 정답이면 정답 번호, 오답이면 학생이 고른 번호.
        값이 비어있으면 0 (미응답).
      - item_list: 행렬 i 인덱스 순서의 선택형 ItemInfo 리스트
    """
    items = exam.select_items
    item_list = sorted(items, key=lambda x: x.number)
    n_students = len(exam.students)
    n_items = len(item_list)

    score = np.zeros((n_students, n_items), dtype=np.float32)
    choice = np.zeros((n_students, n_items), dtype=np.int8)

    for s_idx, st in enumerate(exam.students):
        for i_idx, it in enumerate(item_list):
            v = st.answers.get(it.number, "")
            if v == "" or v is None:
                continue
            if v == ".":
                # 정답
                score[s_idx, i_idx] = 1.0
                try:
                    choice[s_idx, i_idx] = int(it.answer)
                except (TypeError, ValueError):
                    choice[s_idx, i_idx] = 0
            else:
                # 오답: 학생이 고른 번호
                try:
                    choice[s_idx, i_idx] = int(v)
                except (TypeError, ValueError):
                    choice[s_idx, i_idx] = 0
                score[s_idx, i_idx] = 0.0

    return score, choice, item_list


# ---------------------------------------------------------------------------
# 분석 결과 컨테이너
# ---------------------------------------------------------------------------

@dataclass
class ItemStats:
    item: ItemInfo
    p_value: float                  # 정답률 (전체)
    discrimination: float           # point-biserial
    diff_label: str = ""
    discr_label: str = ""
    choice_dist: dict = field(default_factory=dict)  # {1:%, 2:%, 3:%, 4:%, 5:%, 0:'무응답%'}
    choice_dist_by_level: dict = field(default_factory=dict)  # level -> {choice: %}
    p_by_level: dict = field(default_factory=dict)  # level -> 정답률(%)


@dataclass
class SerdapStats:
    """서답형(논술형) 점수 통계 — NEIS 정오표의 '서답형점수' 컬럼을 사용.

    원본 KICE 웹앱 표시 형태와 동일하게 다음을 산출:
      max_total: 서답형 만점 (문항정보표 서답형 배점 합)
      min_v, max_v, mean, std, correct_rate(전체 정답률 = mean/max_total),
      discrimination = corr(서답형점수, 과목총점),
      by_level: 성취수준별 서답형 정답률(%).
    """
    n_items: int = 0
    max_total: float = 0.0
    min_v: float = 0.0
    max_v: float = 0.0
    mean: float = 0.0
    std: float = 0.0
    correct_rate: float = 0.0          # 0~1
    discrimination: float = 0.0
    by_level: dict = field(default_factory=dict)  # level -> 정답률(0~1)


@dataclass
class OverallStats:
    n_students: int = 0
    mean: float = 0.0
    std: float = 0.0
    median: float = 0.0
    cronbach_alpha: float = 0.0
    level_dist: dict = field(default_factory=dict)         # 'A'~'E','미도달' -> 인원수
    level_dist_pct: dict = field(default_factory=dict)     # 'A'~'E','미도달' -> 비율
    level_mean: dict = field(default_factory=dict)         # level -> 평균(원점수)
    level_std: dict = field(default_factory=dict)          # level -> 표준편차(원점수)
    by_class: dict = field(default_factory=dict)           # 학급명 -> {n, mean, std, level_dist}
    by_standard: list = field(default_factory=list)        # 성취기준별 결과 (level별 포함)
    by_content_area: list = field(default_factory=list)    # 내용영역별 결과
    levels_arr: list = field(default_factory=list)         # 학생별 성취수준 리스트 (총점 정렬과 동일)


# ---------------------------------------------------------------------------
# 핵심 분석 함수
# ---------------------------------------------------------------------------

def cronbach_alpha(score_matrix: np.ndarray) -> float:
    """문항-점수 행렬에서 Cronbach's α 계산."""
    if score_matrix.shape[1] < 2 or score_matrix.shape[0] < 2:
        return 0.0
    n = score_matrix.shape[1]
    item_var = np.var(score_matrix, axis=0, ddof=1)
    total_var = np.var(score_matrix.sum(axis=1), ddof=1)
    if total_var <= 0:
        return 0.0
    return (n / (n - 1)) * (1.0 - item_var.sum() / total_var)


def point_biserial(item_col: np.ndarray, total: np.ndarray) -> float:
    """item-total 상관(=피어슨 r).

    KICE 원본 웹앱과 동일하게:
      item_col = 0/1 정답 여부
      total    = 학생 과목총점 (선택형 가중합 + 서답형 점수)
    즉, 호출 측에서 total로 과목총점을 넘겨야 한다. (자기 제외 corrected 아님)
    """
    if item_col.std(ddof=0) == 0 or total.std(ddof=0) == 0:
        return 0.0
    return float(np.corrcoef(item_col, total)[0, 1])


def analyze_items(exam: ExamData) -> tuple[list[ItemStats], np.ndarray, list[ItemInfo]]:
    """문항별 통계를 일괄 계산. (KICE 원본 웹앱과 동일한 산식)

      정답률 p = 정답 학생 수 / 전체 학생 수
      변별도 r = corr( 0/1 정답여부 , 과목총점 )
        ※ 과목총점은 선택형 가중합 + 서답형 점수의 합 (NEIS 정오표의 '과목총점' 컬럼)
    """
    score, choice, item_list = build_score_matrix(exam)
    if score.size == 0:
        return [], score, item_list

    # 변별도용 total = NEIS의 과목총점 (선택형 가중합 + 서답형 합)
    exam_total = np.array([st.total for st in exam.students], dtype=float)
    p_values = score.mean(axis=0)

    # 학생별 성취수준 (환산점수 final_score 기준)
    cuts = exam.cut_scores
    levels_arr = np.array([grade_level(st.final_score, cuts) for st in exam.students])

    stats: list[ItemStats] = []
    for i, it in enumerate(item_list):
        p = float(p_values[i])
        d = point_biserial(score[:, i], exam_total)

        # 답지 반응 분포 (전체)
        col = choice[:, i]
        dist_total = {}
        for v in (1, 2, 3, 4, 5):
            dist_total[v] = float(np.mean(col == v))
        dist_total[0] = float(np.mean(col == 0))  # 무응답
        # 답지 반응 분포 (성취수준별) + 성취수준별 정답률
        dist_by_lvl = {}
        p_by_lvl = {}
        for lv in LEVELS:
            mask = levels_arr == lv
            if mask.sum() == 0:
                continue
            sub_choice = col[mask]
            sub_score = score[mask, i]
            d_lv = {v: float(np.mean(sub_choice == v)) for v in (1, 2, 3, 4, 5)}
            d_lv[0] = float(np.mean(sub_choice == 0))
            dist_by_lvl[lv] = d_lv
            p_by_lvl[lv] = float(np.mean(sub_score))

        stats.append(ItemStats(
            item=it, p_value=p, discrimination=d,
            diff_label=difficulty_label(p),
            discr_label=discrim_label(d),
            choice_dist=dist_total,
            choice_dist_by_level=dist_by_lvl,
            p_by_level=p_by_lvl,
        ))
    return stats, score, item_list


def analyze_overall(exam: ExamData, score_matrix: np.ndarray | None = None) -> OverallStats:
    """전체 성취도 통계 (환산점수 final_score 기준).

    final_score는 data_loader.apply_perform()에서 계산된 100점 만점 환산점수.
    수행평가가 적용되지 않은 경우 final_score == total(지필 점수)와 같다.
    """
    out = OverallStats()
    students = exam.students
    out.n_students = len(students)
    if not students:
        return out

    # 성취수준 판정·기술통계는 모두 환산점수(final_score) 기준
    totals = np.array([st.final_score for st in students], dtype=float)
    out.mean = float(totals.mean())
    out.std = float(totals.std(ddof=1)) if len(totals) > 1 else 0.0
    out.median = float(np.median(totals))

    if score_matrix is None:
        score_matrix, _, _ = build_score_matrix(exam)
    if score_matrix.size:
        out.cronbach_alpha = float(cronbach_alpha(score_matrix))

    # 성취수준 분포 (반올림 정수 원점수 기준)
    levels = [grade_level(t, exam.cut_scores) for t in totals]
    out.levels_arr = levels
    out.level_dist = {lv: levels.count(lv) for lv in LEVELS}
    n = len(levels) or 1
    out.level_dist_pct = {lv: out.level_dist[lv] / n * 100 for lv in LEVELS}
    # level별 평균/표준편차
    for lv in LEVELS:
        sub = totals[np.array(levels) == lv]
        if len(sub) > 0:
            out.level_mean[lv] = float(sub.mean())
            out.level_std[lv] = float(sub.std(ddof=1)) if len(sub) > 1 else 0.0
        else:
            out.level_mean[lv] = 0.0
            out.level_std[lv] = 0.0

    # 학급별 (환산점수 기준)
    by_class = {}
    for st in students:
        key = st.class_no.split("/")[0] if st.class_no else "(미상)"
        by_class.setdefault(key, []).append(st)
    out.by_class = {}
    for cls, ss in sorted(by_class.items(), key=lambda x: (len(x[0]), x[0])):
        ts = np.array([s.final_score for s in ss], dtype=float)
        ld = {lv: 0 for lv in LEVELS}
        for s in ss:
            ld[grade_level(s.final_score, exam.cut_scores)] += 1
        out.by_class[cls] = {
            "n": len(ss),
            "mean": float(ts.mean()),
            "std": float(ts.std(ddof=1)) if len(ts) > 1 else 0.0,
            "level_dist": ld,
        }

    # 성취기준별, 내용영역별 평균 정답률 + 성취수준별 정답률
    # 같은 성취기준이 띄어쓰기·문장부호·앞뒤 공백 차이로 다른 키로 분리되는 것을 막기 위해
    # 비교용으로는 정규화 키를 쓰되, 표시는 가장 긴(완전한) 원문을 보존한다.
    import re as _re
    def _normalize(s: str) -> str:
        return _re.sub(r"\s+", " ", s.strip()).rstrip(".,;:· ").lower()

    def _standard_key(item: ItemInfo) -> str:
        # 같은 성취기준 코드는 문장 일부가 잘려 들어와도 반드시 하나로 묶는다.
        if item.standard_code:
            return f"code:{_normalize(item.standard_code)}"
        full_text = f"{item.standard_code} {item.standard}".strip()
        return f"text:{_normalize(full_text) or '(미상)'}"

    item_stats, _, item_list = analyze_items(exam)
    by_std_raw: dict = {}    # norm_key -> {"display": str, "p":..., "p_lv":...}
    by_area_raw: dict = {}
    for s in item_stats:
        full = f"{s.item.standard_code} {s.item.standard}".strip()
        if not full:
            full = "(미상)"
        norm = _standard_key(s.item)
        entry = by_std_raw.setdefault(norm, {
            "display": full,
            "p": [], "p_lv": {lv: [] for lv in LEVELS},
        })
        # 더 긴 표시 텍스트를 우선 (잘린 버전이 들어와도 가장 완전한 것 채택)
        if len(full) > len(entry["display"]):
            entry["display"] = full
        entry["p"].append(s.p_value)
        for lv in LEVELS:
            if lv in s.p_by_level:
                entry["p_lv"][lv].append(s.p_by_level[lv])

        area_full = s.item.content_area.strip() or "(미상)"
        area_norm = _normalize(area_full) or "(미상)"
        entry2 = by_area_raw.setdefault(area_norm, {
            "display": area_full,
            "p": [], "p_lv": {lv: [] for lv in LEVELS},
        })
        if len(area_full) > len(entry2["display"]):
            entry2["display"] = area_full
        entry2["p"].append(s.p_value)
        for lv in LEVELS:
            if lv in s.p_by_level:
                entry2["p_lv"][lv].append(s.p_by_level[lv])

    # 호출자 호환: by_std[k]는 {p, p_lv} 형태로 그대로 유지하고 'display'를 별도 키로
    by_std = {v["display"]: {"p": v["p"], "p_lv": v["p_lv"]} for v in by_std_raw.values()}
    by_area = {v["display"]: {"p": v["p"], "p_lv": v["p_lv"]} for v in by_area_raw.values()}

    def _summarize(d):
        out_list = []
        for k, v in d.items():
            row = {"key": k, "n_items": len(v["p"]),
                   "mean_p": float(np.mean(v["p"])) if v["p"] else 0.0,
                   "by_level": {}}
            for lv in LEVELS:
                vals = v["p_lv"].get(lv, [])
                row["by_level"][lv] = float(np.mean(vals)) if vals else None
            out_list.append(row)
        return sorted(out_list, key=lambda x: -x["mean_p"])

    out.by_standard = _summarize(by_std)
    out.by_content_area = _summarize(by_area)
    return out


def analyze_serdap(exam: ExamData, levels_arr: list | None = None) -> SerdapStats:
    """서답형(논술형) 점수 분석.

    NEIS 정오표의 '서답형점수' 컬럼이 학생별 서답형 총점을 담는다.
    문항정보표의 서답형 문항들의 배점 합을 서답형 만점으로 사용.
    """
    st = SerdapStats()
    serdap_items = [it for it in exam.items if it.item_type == "서답형"]
    st.n_items = len(serdap_items)
    st.max_total = sum(it.score for it in serdap_items)
    if not exam.students or st.max_total <= 0:
        return st
    arr = np.array([s.serdap_score for s in exam.students], dtype=float)
    st.min_v = float(arr.min())
    st.max_v = float(arr.max())
    st.mean = float(arr.mean())
    st.std = float(arr.std(ddof=1)) if len(arr) > 1 else 0.0
    st.correct_rate = st.mean / st.max_total if st.max_total else 0.0
    exam_total = np.array([s.total for s in exam.students], dtype=float)
    if arr.std(ddof=0) > 0 and exam_total.std(ddof=0) > 0:
        st.discrimination = float(np.corrcoef(arr, exam_total)[0, 1])
    # 성취수준별 정답률
    if levels_arr is None:
        cuts = exam.cut_scores
        levels_arr = [grade_level(s.final_score, cuts) for s in exam.students]
    levels_np = np.array(levels_arr)
    for lv in LEVELS:
        mask = levels_np == lv
        if mask.sum() == 0:
            continue
        st.by_level[lv] = float(arr[mask].mean()) / st.max_total
    return st


if __name__ == "__main__":
    import sys
    from .data_loader import load_exam
    e = load_exam(sys.argv[1], sys.argv[2])
    o = analyze_overall(e)
    print("N:", o.n_students, "mean:", round(o.mean, 2), "std:", round(o.std, 2),
          "alpha:", round(o.cronbach_alpha, 3))
    print("level_dist:", o.level_dist)
    print("level_pct:", {k: round(v, 1) for k, v in o.level_dist_pct.items()})
    print("classes:", list(o.by_class.keys()))
    items, _, _ = analyze_items(e)
    for s in items[:5]:
        print(f"  문항{s.item.number} p={s.p_value:.2f} d={s.discrimination:.2f} {s.diff_label}/{s.discr_label}")
