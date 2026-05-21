"""
Matplotlib 기반 차트 헬퍼.

- macOS/Windows에서 한글 글꼴이 누락된 경우를 대비해, 시스템에 흔히 있는 글꼴을
  순차 탐색해 한글이 깨지지 않도록 한다.
- 차트는 Figure 객체를 반환하므로 Qt 위젯과 자유롭게 결합할 수 있다.
"""
from __future__ import annotations

import math
from typing import Iterable

import matplotlib
matplotlib.use("Agg")  # GUI에서 FigureCanvasQTAgg가 다시 백엔드를 잡아준다.
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib import font_manager as fm

import numpy as np


# ---------------------------------------------------------------------------
# 한글 글꼴 설정
# ---------------------------------------------------------------------------

try:
    from .fonts import register_fonts, pick_korean_font
    register_fonts()
    _FONT = pick_korean_font()
except Exception:
    _FONT = matplotlib.rcParams.get("font.family", ["DejaVu Sans"])[0]

matplotlib.rcParams["font.family"] = _FONT
matplotlib.rcParams["axes.unicode_minus"] = False
matplotlib.rcParams["font.size"] = 10
matplotlib.rcParams["axes.titlesize"] = 12
matplotlib.rcParams["axes.titleweight"] = "bold"
matplotlib.rcParams["axes.labelsize"] = 10


COLOR_LEVELS = {
    "A": "#205b7a",
    "B": "#2a7770",
    "C": "#69a68f",
    "D": "#c4d8a7",
    "E": "#f0d998",
    "미도달": "#9aa3a1",
}

# 테마에서 주입받는 보조 색상 (set_theme로 교체됨)
THEME_COLORS = {
    "p_bar": "#b8d8cf",
    "d_bar": "#d7c88f",
    "highlight": "#fff5a4",
    "shade": "#e1e6ee",
    "chart_bg": "#ffffff",
    "chart_grid": "#dfe5ee",
    "chart_text": "#222",
}


def set_theme(colors: dict):
    """ThemeManager가 호출. 차트 색을 테마 팔레트로 갱신."""
    global COLOR_LEVELS, THEME_COLORS
    COLOR_LEVELS = {
        "A": colors["level_A"], "B": colors["level_B"], "C": colors["level_C"],
        "D": colors["level_D"], "E": colors["level_E"], "미도달": colors["level_미도달"],
    }
    THEME_COLORS = {
        "p_bar": colors["p_bar"], "d_bar": colors["d_bar"],
        "highlight": colors["highlight"], "shade": colors["shade"],
        "chart_bg": colors["chart_bg"], "chart_grid": colors["chart_grid"],
        "chart_text": colors["chart_text"],
    }


# ---------------------------------------------------------------------------
# 차트 함수들
# ---------------------------------------------------------------------------

def fig_level_distribution(level_pct: dict, level_n: dict, title: str = "성취수준별 분포") -> Figure:
    fig = Figure(figsize=(6.2, 3.8), dpi=110)
    ax = fig.add_subplot(111)
    levels = ["A", "B", "C", "D", "E", "미도달"]
    pcts = [level_pct.get(lv, 0) for lv in levels]
    counts = [level_n.get(lv, 0) for lv in levels]
    colors = [COLOR_LEVELS[l] for l in levels]
    bars = ax.bar(levels, pcts, color=colors, edgecolor="white")
    top = max(pcts + [10]) * 1.35 + 8
    for b, p, n in zip(bars, pcts, counts):
        ax.text(b.get_x() + b.get_width() / 2, b.get_height() + top * 0.02,
                f"{p:.1f}%\n({n}명)", ha="center", va="bottom", fontsize=9,
                color=THEME_COLORS["chart_text"])
    ax.set_ylabel("학생 비율 (%)")
    ax.set_ylim(0, top)
    ax.set_title(title)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", linestyle=":", alpha=0.4)
    fig.subplots_adjust(left=0.10, right=0.98, top=0.88, bottom=0.12)
    return fig


def _luminance(hex_color: str) -> float:
    """웹용 명도 계산 (0~1). 0.5 미만이면 어두운 색."""
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c*2 for c in h)
    r, g, b = (int(h[i:i+2], 16) / 255 for i in (0, 2, 4))
    # WCAG luminance
    def _lin(v): return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def fig_level_donut(level_pct: dict, level_n: dict, title: str = "성취수준 비율") -> Figure:
    """도넛(파이) 차트로 성취수준 비율을 표시.

    안쪽: 알파벳만 (배경 명도에 따라 흰/검 자동 → 어떤 테마에서도 또렷)
    바깥: 'A 40.8% (42명)' 한 줄에 알파벳·비율·인원 모두
    중복 % 표기 없음. 도넛 + 좌우 여백 + 제목 영역을 충분히 확보해 잘림 방지.
    """
    fig = Figure(figsize=(6.8, 4.0), dpi=110)
    ax = fig.add_subplot(111)
    ax.set_facecolor(THEME_COLORS["chart_bg"])

    levels = ["A", "B", "C", "D", "E", "미도달"]
    sizes = [level_pct.get(lv, 0) for lv in levels]
    counts = [level_n.get(lv, 0) for lv in levels]
    colors = [COLOR_LEVELS[lv] for lv in levels]
    pairs = [(lv, s, n, c) for lv, s, n, c in zip(levels, sizes, counts, colors) if s > 0]
    if not pairs:
        ax.text(0.5, 0.5, "데이터 없음", ha="center", va="center",
                color=THEME_COLORS["chart_text"])
        return fig
    levels = [p[0] for p in pairs]; sizes = [p[1] for p in pairs]
    counts = [p[2] for p in pairs]; colors = [p[3] for p in pairs]

    edge = THEME_COLORS.get("chart_bg", "#ffffff")
    text_color = THEME_COLORS["chart_text"]

    wedges, _ = ax.pie(
        sizes, colors=colors, startangle=90, counterclock=False,
        wedgeprops=dict(width=0.42, edgecolor=edge, linewidth=2),
    )
    # 안쪽: 알파벳만 (단순·또렷)
    for idx, (w, lv, sz) in enumerate(zip(wedges, levels, sizes)):
        if sz < 3.0:  # 너무 작은 조각만 안쪽 라벨 생략
            continue
        if lv == "미도달":
            continue
        ang = (w.theta2 + w.theta1) / 2.0
        x = 0.79 * np.cos(np.deg2rad(ang))
        y = 0.79 * np.sin(np.deg2rad(ang))
        lum = _luminance(colors[idx])
        inner_text_color = "#ffffff" if lum < 0.5 else "#1f2933"
        inner_font = 14 if sz >= 8 else 11
        ax.text(x, y, lv, ha="center", va="center",
                fontsize=inner_font, color=inner_text_color, fontweight="bold")
    # 바깥 라벨은 좌/우 컬럼에 정렬해 좁은 패널에서도 잘리지 않게 배치한다.
    label_points = {"left": [], "right": []}
    for idx, w in enumerate(wedges):
        ang = (w.theta2 + w.theta1) / 2.0
        c = np.cos(np.deg2rad(ang))
        side = "right" if c >= 0 else "left"
        label_points[side].append((idx, 1.12 * np.sin(np.deg2rad(ang)), ang))

    def _spread(items, *, low=-1.08, high=1.08, gap=0.27):
        items = sorted(items, key=lambda t: -t[1])
        out = []
        prev = high + gap
        for idx, y, ang in items:
            y = min(high, max(low, y))
            if y > prev - gap:
                y = prev - gap
            out.append([idx, y, ang])
            prev = y
        if out and out[-1][1] < low:
            shift = low - out[-1][1]
            for item in out:
                item[1] += shift
        return out

    for side, items in label_points.items():
        x_text = 1.22 if side == "right" else -1.22
        ha = "left" if side == "right" else "right"
        x_elbow = 1.08 if side == "right" else -1.08
        x_end = x_text - 0.06 if side == "right" else x_text + 0.06
        for idx, y, ang in _spread(items):
            lv, n, sz = levels[idx], counts[idx], sizes[idx]
            x0 = 0.99 * np.cos(np.deg2rad(ang))
            y0 = 0.99 * np.sin(np.deg2rad(ang))
            ax.plot([x0, x_elbow, x_end], [y0, y, y],
                    color=text_color, alpha=0.55, linewidth=0.8, clip_on=False)
            label = f"{lv} {sz:.1f}% ({n}명)"
            outer_font = 8.5
            if len(pairs) >= 6:
                outer_font = 7.6
            if len(label) >= 15:
                outer_font = min(outer_font, 7.2)
            ax.text(x_text, y, label, ha=ha, va="center", fontsize=outer_font,
                    color=text_color, fontweight="bold", clip_on=False)

    # 가운데 총원
    total = sum(counts)
    total_font = 22 if total < 1000 else 18
    ax.text(0, 0.08, f"{total}", ha="center", va="center", fontsize=total_font,
            fontweight="bold", color=text_color)
    ax.text(0, -0.13, "명", ha="center", va="center", fontsize=max(9, total_font - 11),
            color=text_color)
    title_font = 13 if len(pairs) >= 6 else 14
    ax.set_title(title, pad=18, color=text_color, fontsize=title_font, fontweight="bold")
    ax.set_aspect("equal")
    ax.set_axis_off()
    ax.set_xlim(-3.70, 3.70); ax.set_ylim(-1.35, 1.35)
    fig.subplots_adjust(left=0.04, right=0.96, top=0.82, bottom=0.08)
    return fig


def fig_level_stack(level_pct: dict, title: str = "성취수준 비율") -> Figure:
    """원본 화면 좌측의 단일 세로 누적 막대 (A→미도달)."""
    fig = Figure(figsize=(2.6, 4.2), dpi=110)
    ax = fig.add_subplot(111)
    bottom = 0
    for lv in ["A", "B", "C", "D", "E", "미도달"]:
        v = level_pct.get(lv, 0)
        if v <= 0:
            continue
        ax.bar(["전체"], [v], bottom=[bottom], color=COLOR_LEVELS[lv], edgecolor="white")
        if v >= 4:
            ax.text(0, bottom + v / 2, lv, ha="center", va="center",
                    fontsize=11, color="white" if lv in ("A", "B", "미도달") else "#222",
                    fontweight="bold")
        bottom += v
    ax.set_ylim(0, 100)
    ax.set_ylabel("비율 (%)")
    ax.set_title(title)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    return fig


def fig_score_histogram_colored(
    totals,
    levels_arr,
    title: str = "환산점수 분포",
    *,
    achievement_cuts: dict | None = None,
    grade_cut_points: list[dict] | None = None,
    highlight_scores: list[float] | None = None,
    highlight_labels: list[str] | None = None,
) -> Figure:
    """원본 Data 탭처럼 점수 1점 빈으로 쪼개고 학생별 성취수준 색상으로 막대를 표시."""
    fig = Figure(figsize=(8.2, 3.8), dpi=110)
    ax = fig.add_subplot(111)
    arr = np.array(totals, dtype=float)
    if arr.size == 0:
        ax.text(0.5, 0.5, "데이터 없음", ha="center", va="center")
        return fig
    rounded = np.round(arr).astype(int)
    levels = np.array(levels_arr)
    bins = np.arange(0, 102, 1)
    bottom = np.zeros(len(bins) - 1, dtype=int)
    bar_handles = {}
    for lv in ["미도달", "E", "D", "C", "B", "A"]:
        mask = levels == lv
        if mask.sum() == 0:
            continue
        cnt, _ = np.histogram(rounded[mask], bins=bins)
        bars = ax.bar(bins[:-1], cnt, width=1.0, bottom=bottom, color=COLOR_LEVELS[lv],
                      edgecolor="white", linewidth=0.2, label=lv)
        bar_handles[lv] = bars[0]
        bottom += cnt
    ymax = max(1, int(bottom.max()) if bottom.size else 1)
    headroom = 1.3
    if achievement_cuts:
        for i, lv in enumerate(["A", "B", "C", "D", "E"]):
            if lv not in achievement_cuts:
                continue
            x = float(achievement_cuts[lv])
            ax.axvline(x, color=COLOR_LEVELS.get(lv, "#555"), linestyle="--", linewidth=1.0, alpha=0.72)
            ax.text(
                x, ymax + 0.22 + (i % 2) * 0.20, lv,
                ha="center", va="bottom", fontsize=8.2, fontweight="bold",
                color=COLOR_LEVELS.get(lv, THEME_COLORS["chart_text"]),
            )
        headroom = max(headroom, 1.9)
    if grade_cut_points:
        style_by_kind = {
            "9등급": ("#64748b", ":"),
            "5등급": ("#8b5cf6", "-."),
        }
        for i, point in enumerate(grade_cut_points):
            x = float(point.get("score", 0.0))
            label = str(point.get("label", "등급"))
            kind = str(point.get("kind", ""))
            color, linestyle = style_by_kind.get(kind, ("#475569", ":"))
            ax.axvline(x, color=color, linestyle=linestyle, linewidth=0.9, alpha=0.55)
            if i < 14:
                ax.text(
                    x, ymax + 0.70 + (i % 4) * 0.22, label,
                    ha="center", va="bottom", fontsize=6.9, rotation=90,
                    color=color,
                )
        headroom = max(headroom, 3.3)
    if highlight_scores:
        labels = highlight_labels or ["" for _ in highlight_scores]
        for i, (score, label) in enumerate(zip(highlight_scores, labels)):
            x = round(float(score))
            color = "#ef4444" if i % 2 == 0 else "#f59e0b"
            ax.axvline(x, color=color, linestyle="--", linewidth=1.4, alpha=0.95)
            ax.scatter([x], [ymax + 0.35 + (i % 3) * 0.22], s=34,
                       color=color, edgecolor="white", linewidth=0.7, zorder=5)
            if i < 5 and label:
                ax.text(x, ymax + 0.78 + (i % 3) * 0.28, label,
                        ha="center", va="bottom", fontsize=8,
                        rotation=25, color=THEME_COLORS["chart_text"],
                        bbox=dict(boxstyle="round,pad=0.18", facecolor=THEME_COLORS["chart_bg"],
                                  edgecolor=color, linewidth=0.8, alpha=0.9))
        headroom = max(headroom, 2.8)
    ax.set_ylim(0, ymax + headroom)
    ax.set_xlabel("환산점수 (반올림 정수 원점수)")
    ax.set_ylabel("학생 수")
    ax.set_xlim(-1, 101)
    ax.set_title(title)
    # 범례를 막대와 겹치지 않게 차트 바깥(우측)에 표시
    legend_order = ["A", "B", "C", "D", "E", "미도달"]
    handles = [bar_handles[lv] for lv in legend_order if lv in bar_handles]
    labels = [lv for lv in legend_order if lv in bar_handles]
    ax.legend(handles, labels, title="성취수준", loc="center left", bbox_to_anchor=(1.005, 0.5),
              fontsize=8.5, frameon=False, title_fontsize=9)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", linestyle=":", alpha=0.4)
    fig.subplots_adjust(left=0.08, right=0.86, top=0.88, bottom=0.16)
    return fig


def _normal_cdf(x: float, mean: float, std: float) -> float:
    if std <= 0:
        return 1.0 if x >= mean else 0.0
    return 0.5 * (1.0 + math.erf((x - mean) / (std * math.sqrt(2.0))))


def fig_score_normal_monitoring(
    totals,
    cuts: dict,
    level_pct: dict,
    title: str = "정규분포 기준 점검",
) -> Figure:
    fig = Figure(figsize=(8.2, 3.8), dpi=110)
    ax = fig.add_subplot(111)
    arr = np.array(totals, dtype=float)
    if arr.size == 0:
        ax.text(0.5, 0.5, "데이터 없음", ha="center", va="center")
        return fig

    mean = float(arr.mean())
    std = float(arr.std(ddof=1)) if arr.size > 1 else 0.0
    bins = np.arange(0, 102, 2)
    counts, _, _ = ax.hist(
        arr, bins=bins, color=THEME_COLORS["p_bar"], edgecolor="white",
        linewidth=0.35, alpha=0.72, label="실제 분포"
    )
    ymax = max(1.0, float(counts.max()) if counts.size else 1.0)

    if std > 0:
        x = np.linspace(0, 100, 500)
        pdf = (1 / (std * np.sqrt(2 * np.pi))) * np.exp(-0.5 * ((x - mean) / std) ** 2)
        y = pdf * len(arr) * 2
        ax.plot(x, y, color=THEME_COLORS["chart_text"], linewidth=2.0, label="정규분포 곡선")
        for mul, alpha in ((1, 0.16), (2, 0.08)):
            lo, hi = mean - mul * std, mean + mul * std
            ax.axvspan(max(0, lo), min(100, hi), color="#60a5fa", alpha=alpha, lw=0)
        for mul, style in ((0, "-"), (1, "--"), (-1, "--"), (2, ":"), (-2, ":")):
            x0 = mean + mul * std
            if 0 <= x0 <= 100:
                label = "평균" if mul == 0 else f"{mul:+d}σ"
                ax.axvline(x0, color="#f59e0b" if mul else "#ef4444",
                           linestyle=style, linewidth=1.2)
                ax.text(x0, ymax * 1.05, label, ha="center", va="bottom",
                        fontsize=8, color=THEME_COLORS["chart_text"])

    for lv, boundary in [("A", cuts.get("A")), ("B", cuts.get("B")), ("C", cuts.get("C")),
                         ("D", cuts.get("D")), ("E", cuts.get("E"))]:
        try:
            x0 = float(boundary)
        except (TypeError, ValueError):
            continue
        if 0 <= x0 <= 100:
            ax.axvline(x0, color=COLOR_LEVELS.get(lv, "#999999"),
                       linestyle="-", linewidth=0.8, alpha=0.5)
            ax.text(x0, ymax * 0.9, lv, ha="center", va="bottom",
                    fontsize=8, color=COLOR_LEVELS.get(lv, THEME_COLORS["chart_text"]),
                    fontweight="bold")

    expected_a = (1 - _normal_cdf(float(cuts.get("A", 90.0)), mean, std)) * 100 if std > 0 else 0.0
    observed_a = float(level_pct.get("A", 0.0))
    note = (
        f"평균 {mean:.2f} · 표준편차 {std:.2f}\n"
        f"실제 A {observed_a:.1f}% · 정규 기대 A {expected_a:.1f}%\n"
        f"차이 {observed_a - expected_a:+.1f}%p"
    )
    ax.text(
        0.985, 0.97, note, transform=ax.transAxes, ha="right", va="top",
        fontsize=8.8, color=THEME_COLORS["chart_text"],
        bbox=dict(boxstyle="round,pad=0.45", facecolor=THEME_COLORS["chart_bg"],
                  edgecolor=THEME_COLORS["chart_grid"], alpha=0.92)
    )
    ax.set_title(title)
    ax.set_xlabel("환산점수")
    ax.set_ylabel("학생 수")
    ax.set_xlim(0, 100)
    ax.set_ylim(0, ymax * 1.28)
    ax.grid(axis="y", linestyle=":", alpha=0.35)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(loc="upper left", frameon=False, fontsize=8.5)
    fig.subplots_adjust(left=0.08, right=0.96, top=0.88, bottom=0.16)
    return fig


def fig_monitoring_benchmarks(
    benchmarks: list[dict],
    title: str = "모니터링 기준 비교",
) -> Figure:
    """전국 평균±표준편차 기준 위에 현재 학교 값을 표시한다."""
    fig = Figure(figsize=(8.2, 3.6), dpi=110)
    ax = fig.add_subplot(111)
    if not benchmarks:
        ax.text(0.5, 0.5, "분석 후 모니터링 기준을 입력하세요.",
                ha="center", va="center", color=THEME_COLORS["chart_text"])
        ax.set_axis_off()
        return fig

    y_positions = np.arange(len(benchmarks))[::-1]
    labels = [row["label"] for row in benchmarks]
    text_color = THEME_COLORS["chart_text"]
    grid = THEME_COLORS["chart_grid"]

    for y, row in zip(y_positions, benchmarks):
        value = float(row.get("value", 0.0))
        ref = row.get("ref")
        sd = row.get("sd")
        color = row.get("color", "#ef4444")
        has_ref = ref is not None and sd is not None and float(sd) > 0
        if has_ref:
            ref = float(ref)
            sd = float(sd)
            lo2, hi2 = max(0, ref - 2 * sd), min(100, ref + 2 * sd)
            lo1, hi1 = max(0, ref - sd), min(100, ref + sd)
            ax.barh(y, hi2 - lo2, left=lo2, height=0.42,
                    color="#60a5fa", alpha=0.12, edgecolor="none")
            ax.barh(y, hi1 - lo1, left=lo1, height=0.42,
                    color="#60a5fa", alpha=0.24, edgecolor="none")
            ax.plot([ref, ref], [y - 0.32, y + 0.32],
                    color=text_color, linewidth=1.2, alpha=0.75)
            ax.text(ref, y + 0.36, "전국평균", ha="center", va="bottom",
                    fontsize=7.8, color=text_color)
            ax.text(hi1, y - 0.36, "+1σ", ha="center", va="top",
                    fontsize=7.8, color=text_color, alpha=0.72)
            ax.text(hi2, y - 0.36, "+2σ", ha="center", va="top",
                    fontsize=7.8, color=text_color, alpha=0.72)
        ax.scatter([value], [y], s=88, marker="D", color=color,
                   edgecolor="white", linewidth=0.8, zorder=5)
        ax.text(min(100, value + 1.2), y, f"{value:.1f}",
                ha="left", va="center", fontsize=9, fontweight="bold",
                color=text_color)

    ax.set_yticks(y_positions)
    ax.set_yticklabels(labels)
    ax.set_xlim(0, 100)
    ax.set_xlabel("비율 또는 점수")
    ax.set_title(title)
    ax.grid(axis="x", linestyle=":", alpha=0.35)
    ax.spines[["top", "right"]].set_visible(False)
    fig.subplots_adjust(left=0.20, right=0.98, top=0.86, bottom=0.18)
    return fig


def fig_perform_area_rates(
    area_rows: list[dict],
    title: str = "수행평가 영역별 평균 점수율",
) -> Figure:
    """수행평가 영역별 평균 점수율과 표준편차를 보여준다."""
    fig = Figure(figsize=(7.8, 3.8), dpi=110)
    ax = fig.add_subplot(111)
    if not area_rows:
        ax.text(0.5, 0.5, "수행평가 자료 없음", ha="center", va="center",
                color=THEME_COLORS["chart_text"])
        ax.set_axis_off()
        return fig

    labels = [row["name"] for row in area_rows]
    means = [row["mean_rate"] for row in area_rows]
    stds = [row["std_rate"] for row in area_rows]
    short = [(label[:12] + "…") if len(label) > 13 else label for label in labels]
    colors = [THEME_COLORS["p_bar"] if mean >= 66.7 else THEME_COLORS["d_bar"] for mean in means]
    bars = ax.bar(short, means, color=colors, yerr=stds, capsize=5,
                  edgecolor="white", linewidth=0.6,
                  error_kw={"ecolor": THEME_COLORS["chart_text"], "alpha": 0.45})
    ax.axhline(66.7, color=THEME_COLORS["chart_text"], linestyle=":",
               linewidth=1.1, alpha=0.45)
    ax.text(len(short) - 0.45, 68.5, "2/3 기준", ha="right", va="bottom",
            fontsize=8.5, color=THEME_COLORS["chart_text"], alpha=0.78)
    for b, row in zip(bars, area_rows):
        ax.text(
            b.get_x() + b.get_width() / 2,
            min(108, b.get_height() + max(2, row["std_rate"] * 0.18 + 1)),
            f"{row['mean_rate']:.1f}%",
            ha="center", va="bottom", fontsize=8.7,
            color=THEME_COLORS["chart_text"], fontweight="bold",
        )
    ax.set_ylim(0, 112)
    ax.set_ylabel("평균 점수율 (%)")
    ax.set_title(title)
    ax.grid(axis="y", linestyle=":", alpha=0.35)
    ax.spines[["top", "right"]].set_visible(False)
    fig.subplots_adjust(left=0.09, right=0.98, top=0.86, bottom=0.22)
    return fig


def fig_perform_scatter(
    pencil_scores,
    perform_scores,
    levels_arr,
    title: str = "지필총점 × 수행평가 환산",
) -> Figure:
    """지필총점과 수행평가 환산점수의 관계를 성취수준 색으로 표시한다."""
    fig = Figure(figsize=(7.8, 3.8), dpi=110)
    ax = fig.add_subplot(111)
    x = np.array(pencil_scores, dtype=float)
    y = np.array(perform_scores, dtype=float)
    levels = np.array(levels_arr)
    if x.size == 0 or y.size == 0:
        ax.text(0.5, 0.5, "수행평가 자료 없음", ha="center", va="center",
                color=THEME_COLORS["chart_text"])
        ax.set_axis_off()
        return fig

    for lv in ["미도달", "E", "D", "C", "B", "A"]:
        mask = levels == lv
        if mask.sum() == 0:
            continue
        ax.scatter(x[mask], y[mask], s=36, color=COLOR_LEVELS[lv],
                   edgecolor="white", linewidth=0.55, alpha=0.88, label=lv)

    ax.plot([0, 100], [0, 100], color=THEME_COLORS["chart_text"],
            linestyle=":", linewidth=1.2, alpha=0.45)
    x_mean = float(x.mean())
    y_mean = float(y.mean())
    ax.axvline(x_mean, color="#f59e0b", linestyle="--", linewidth=1.0, alpha=0.7)
    ax.axhline(y_mean, color="#2a7770", linestyle="--", linewidth=1.0, alpha=0.7)
    if x.size > 1 and x.std(ddof=0) > 0 and y.std(ddof=0) > 0:
        corr = float(np.corrcoef(x, y)[0, 1])
        note = f"상관 r={corr:.2f}\n지필 평균 {x_mean:.1f}\n수행 평균 {y_mean:.1f}"
    else:
        note = f"지필 평균 {x_mean:.1f}\n수행 평균 {y_mean:.1f}"
    ax.text(
        0.02, 0.98, note, transform=ax.transAxes, ha="left", va="top",
        fontsize=8.8, color=THEME_COLORS["chart_text"],
        bbox=dict(boxstyle="round,pad=0.4", facecolor=THEME_COLORS["chart_bg"],
                  edgecolor=THEME_COLORS["chart_grid"], alpha=0.92)
    )
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.set_xlabel("지필총점")
    ax.set_ylabel("수행평가 환산점수")
    ax.set_title(title)
    ax.grid(True, linestyle=":", alpha=0.32)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(loc="center left", bbox_to_anchor=(1.005, 0.5), frameon=False,
              fontsize=8.4, title="성취수준", title_fontsize=8.8)
    fig.subplots_adjust(left=0.09, right=0.86, top=0.86, bottom=0.16)
    return fig


def fig_level_means_with_error(level_mean: dict, level_std: dict, title: str = "성취수준별 평균±표준편차") -> Figure:
    fig = Figure(figsize=(6.2, 3.6), dpi=110)
    ax = fig.add_subplot(111)
    levels = ["A", "B", "C", "D", "E", "미도달"]
    means = [level_mean.get(lv, 0) for lv in levels]
    stds = [level_std.get(lv, 0) for lv in levels]
    colors = [COLOR_LEVELS[lv] for lv in levels]
    bars = ax.bar(levels, means, color=colors, yerr=stds, capsize=6, edgecolor="white",
                  error_kw={"ecolor": "#f4b942", "elinewidth": 2})
    for b, m, s in zip(bars, means, stds):
        ax.text(b.get_x() + b.get_width()/2,
                min(110, b.get_height() + s + 2.5),
                f"{m:.1f}", ha="center", va="bottom", fontsize=9.5,
                color=THEME_COLORS["chart_text"])
    ax.set_ylabel("평균 (환산점수)")
    ax.set_ylim(0, 115)
    ax.set_title(title)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", linestyle=":", alpha=0.4)
    fig.subplots_adjust(left=0.10, right=0.98, top=0.88, bottom=0.12)
    return fig


def fig_score_histogram(totals, cuts, title: str = "과목 총점 분포") -> Figure:
    fig = Figure(figsize=(6, 3.6), dpi=110)
    ax = fig.add_subplot(111)
    arr = np.array(totals, dtype=float)
    if arr.size == 0:
        ax.text(0.5, 0.5, "데이터 없음", ha="center", va="center")
        return fig
    bins = np.arange(0, 101, 5)
    ax.hist(arr, bins=bins, color=THEME_COLORS["p_bar"], edgecolor="white")
    for lv, c in cuts.items():
        ax.axvline(c, color=COLOR_LEVELS[lv], linestyle="--", linewidth=1.2)
        ax.text(c, ax.get_ylim()[1] * 0.96, lv, color=COLOR_LEVELS[lv],
                ha="center", va="top", fontsize=10, fontweight="bold")
    ax.set_xlabel("과목총점")
    ax.set_ylabel("학생 수")
    ax.set_title(title)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", linestyle=":", alpha=0.5)
    fig.tight_layout()
    return fig


def fig_class_means(by_class: dict, title: str = "학급별 평균") -> Figure:
    fig = Figure(figsize=(6.2, 3.6), dpi=110)
    ax = fig.add_subplot(111)
    classes = list(by_class.keys())
    means = [by_class[c]["mean"] for c in classes]
    if not classes:
        ax.text(0.5, 0.5, "학급 데이터 없음", ha="center", va="center")
        return fig
    bars = ax.bar([f"{c}반" for c in classes], means, color=COLOR_LEVELS["B"])
    top = max(means + [10]) * 1.25
    for b, m in zip(bars, means):
        ax.text(b.get_x() + b.get_width() / 2, b.get_height() + top * 0.02,
                f"{m:.1f}", ha="center", va="bottom", fontsize=9.5,
                color=THEME_COLORS["chart_text"])
    ax.set_ylabel("평균 환산점수")
    ax.set_title(title)
    ax.set_ylim(0, top)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", linestyle=":", alpha=0.4)
    fig.subplots_adjust(left=0.10, right=0.98, top=0.88, bottom=0.12)
    return fig


def fig_item_difficulty(items_stats, title: str = "문항별 정답률(난이도)") -> Figure:
    n = max(1, len(items_stats))
    fig = Figure(figsize=(max(8.2, 0.42 * n + 1.5), 3.9), dpi=110)
    ax = fig.add_subplot(111)
    nums = [s.item.number for s in items_stats]
    p = [s.p_value * 100 for s in items_stats]
    bars = ax.bar([str(x) for x in nums], p, color=THEME_COLORS["p_bar"], width=0.66)
    for thr in (20, 40, 60, 80):
        ax.axhline(thr, color=THEME_COLORS["chart_text"], linestyle=":",
                   linewidth=0.8, alpha=0.2)
    for b, v in zip(bars, p):
        ax.text(b.get_x() + b.get_width()/2, b.get_height() + 2.0, f"{v:.0f}",
                ha="center", va="bottom", fontsize=8.5,
                color=THEME_COLORS["chart_text"])
    ax.set_xlabel("문항번호")
    ax.set_ylabel("정답률 (%)")
    ax.set_ylim(0, 118)   # 라벨 공간 충분
    ax.set_title(title)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", linestyle=":", alpha=0.4)
    fig.subplots_adjust(left=0.10, right=0.98, top=0.88, bottom=0.18)
    return fig


def fig_item_discrimination(items_stats, title: str = "문항별 변별도(point-biserial)") -> Figure:
    n = max(1, len(items_stats))
    fig = Figure(figsize=(max(8.2, 0.42 * n + 1.5), 3.9), dpi=110)
    ax = fig.add_subplot(111)
    nums = [s.item.number for s in items_stats]
    d = [s.discrimination for s in items_stats]
    bars = ax.bar([str(x) for x in nums], d, color=THEME_COLORS["d_bar"], width=0.66)
    ax.axhline(0.30, color=THEME_COLORS["chart_text"], linestyle=":", linewidth=0.8, alpha=0.4)
    ax.axhline(0.20, color=THEME_COLORS["chart_text"], linestyle=":", linewidth=0.8, alpha=0.25)
    lo = min(0, min(d) - 0.12) if d else 0
    hi = max(1.0, max(d) + 0.22) if d else 1.0
    # 라벨 위치: 양수면 막대 위, 음수면 막대 아래. 같은 단위로 일정한 거리 두기.
    pad = (hi - lo) * 0.025
    for b, v in zip(bars, d):
        x = b.get_x() + b.get_width() / 2
        if v >= 0:
            ax.text(x, v + pad, f"{v:.2f}",
                    ha="center", va="bottom", fontsize=8,
                    color=THEME_COLORS["chart_text"])
        else:
            ax.text(x, v - pad, f"{v:.2f}",
                    ha="center", va="top", fontsize=8,
                    color=THEME_COLORS["chart_text"])
    ax.set_xlabel("문항번호")
    ax.set_ylabel("변별도 (r)")
    ax.set_ylim(lo, hi)
    ax.set_title(title)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", linestyle=":", alpha=0.4)
    fig.subplots_adjust(left=0.08, right=0.99, top=0.88, bottom=0.16)
    return fig


def fig_choice_dist_by_level(item_stats, title: str = "성취수준별 답지반응분포") -> Figure:
    """단일 문항의 성취수준별 5지선다 비율 (스택 막대)."""
    fig = Figure(figsize=(7.0, 3.4), dpi=110)
    ax = fig.add_subplot(111)
    levels = ["A", "B", "C", "D", "E", "미도달"]
    levels = [lv for lv in levels if lv in item_stats.choice_dist_by_level]
    if not levels:
        ax.text(0.5, 0.5, "데이터 없음", ha="center", va="center")
        return fig
    choices = [1, 2, 3, 4, 5, 0]
    color_choice = {1: "#3da9fc", 2: "#7fc6a4", 3: "#f4b942",
                    4: "#d9534f", 5: "#9b59b6", 0: "#bbb"}
    bottom = np.zeros(len(levels))
    correct = item_stats.item.answer
    for ch in choices:
        vals = np.array([item_stats.choice_dist_by_level[lv].get(ch, 0) * 100 for lv in levels])
        label = f"{ch}" if ch != 0 else "무응답"
        if str(ch) == str(correct):
            label += " (정답)"
        ax.bar(levels, vals, bottom=bottom, color=color_choice[ch],
               edgecolor="white", label=label)
        for i, v in enumerate(vals):
            if v >= 8:
                ax.text(i, bottom[i] + v / 2, f"{v:.0f}", ha="center", va="center",
                        fontsize=8.5, color="white" if ch in (1, 4, 5) else "#222")
        bottom += vals
    ax.set_ylabel("응답 비율 (%)")
    ax.set_xlabel("성취수준")
    ax.set_ylim(0, 105)
    ax.set_title(title)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=6,
              frameon=False, fontsize=8.5)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", linestyle=":", alpha=0.4)
    fig.subplots_adjust(left=0.10, right=0.98, top=0.88, bottom=0.26)
    return fig


def fig_standard_attainment(by_standard: list, title: str = "성취기준별 평균 정답률") -> Figure:
    """가로 막대 + hover 시 풀텍스트 툴팁(차트 안 박스).

    라벨이 길어 잘리는 문제를 두 방향으로 해결:
    1) 라벨을 너무 짧게 자르지 않음 (32자) + 좌측 마진을 충분히
    2) 마우스를 막대 위에 올리면 풀텍스트 박스가 차트 안에 표시됨
    """
    n = max(1, len(by_standard))
    h = max(3.8, 0.55 * n + 1.8)
    fig = Figure(figsize=(11.0, h), dpi=110)
    ax = fig.add_subplot(111)
    if not by_standard:
        ax.text(0.5, 0.5, "데이터 없음", ha="center", va="center",
                color=THEME_COLORS["chart_text"])
        return fig
    labels = [s["key"] for s in by_standard]
    means = [s["mean_p"] * 100 for s in by_standard]
    # 라벨은 한 줄 안에 들어가도록 적당히 자르되, 풀텍스트는 hover로 제공
    short = [(lbl[:30] + "…") if len(lbl) > 32 else lbl for lbl in labels]
    cmap = [COLOR_LEVELS["A"] if v >= 80
            else COLOR_LEVELS["B"] if v >= 60
            else COLOR_LEVELS["C"] if v >= 40
            else COLOR_LEVELS["미도달"]
            for v in means]
    bars = ax.barh(short, means, color=cmap)
    for i, v in enumerate(means):
        ax.text(v + 1.5, i, f"{v:.0f}%", va="center", fontsize=8.5,
                color=THEME_COLORS["chart_text"])
    ax.invert_yaxis()
    ax.set_xlim(0, 122)
    ax.set_xlabel("평균 정답률 (%)")
    ax.set_title(title)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="x", linestyle=":", alpha=0.4)
    # 좌측 마진을 충분히 (긴 한국어 라벨 보호) — 항상 라벨이 보이도록 0.42
    fig.subplots_adjust(left=0.42, right=0.97, top=0.92, bottom=max(0.10, 0.7 / h))

    # ── Hover 풀텍스트 박스 ─────────────────────────────────
    annot = ax.annotate(
        "", xy=(0, 0), xytext=(14, 14), textcoords="offset points",
        bbox=dict(boxstyle="round,pad=0.5",
                  fc=THEME_COLORS.get("chart_bg", "#ffffff"),
                  ec=COLOR_LEVELS["A"], lw=1.2, alpha=0.96),
        color=THEME_COLORS["chart_text"], fontsize=9, fontweight="normal",
        wrap=True, zorder=10, visible=False,
    )

    def _on_move(event):
        if event.inaxes is not ax:
            if annot.get_visible():
                annot.set_visible(False); fig.canvas.draw_idle()
            return
        # 어느 막대 위에 있는지 검사
        hit_idx = None
        for i, b in enumerate(bars):
            if b.contains(event)[0]:
                hit_idx = i; break
        if hit_idx is None:
            if annot.get_visible():
                annot.set_visible(False); fig.canvas.draw_idle()
            return
        full = labels[hit_idx]
        # 너무 긴 라벨은 줄바꿈으로 보기 좋게
        if len(full) > 50:
            mid = len(full) // 2
            split = full.find(" ", mid)
            if split == -1: split = mid
            full = full[:split] + "\n" + full[split:].lstrip()
        annot.xy = (event.xdata, event.ydata)
        annot.set_text(f"{full}\n평균 정답률 {means[hit_idx]:.1f}%")
        annot.set_visible(True)
        fig.canvas.draw_idle()

    fig.canvas.mpl_connect("motion_notify_event", _on_move)
    return fig
