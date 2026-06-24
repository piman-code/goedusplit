"""Pure helpers for AI item-review level judgments."""

from __future__ import annotations

LEVELS_AE = ["A", "B", "C", "D", "E"]


def ai_review_target_threshold(sample_size: int) -> int:
    sample_size = max(1, min(10, int(sample_size or 3)))
    return max(1, min(sample_size, round(sample_size * 2 / 3)))


def ai_review_normalize_counts(
    counts: dict[str, int],
    sample_size: int = 3,
    *,
    target: str = "",
    enforce_target: bool = False,
) -> dict[str, int]:
    sample_size = max(1, min(10, int(sample_size or 3)))
    normalized = {
        lv: max(0, min(sample_size, int(round(counts.get(lv, 0)))))
        for lv in LEVELS_AE
    }
    target = (target or "").strip().upper()
    if enforce_target and target in LEVELS_AE:
        threshold = ai_review_target_threshold(sample_size)
        target_index = LEVELS_AE.index(target)
        normalized[target] = max(normalized[target], threshold)
        for idx, lv in enumerate(LEVELS_AE):
            if idx < target_index:
                normalized[lv] = max(normalized[lv], threshold)
            elif idx > target_index:
                normalized[lv] = min(normalized[lv], threshold)
    prev = sample_size
    for lv in LEVELS_AE:
        normalized[lv] = max(0, min(sample_size, prev, normalized[lv]))
        prev = normalized[lv]
    return normalized


def ai_review_target_from_counts(counts: dict[str, int], sample_size: int = 3) -> str:
    threshold = ai_review_target_threshold(sample_size)
    target = "A"
    for lv in LEVELS_AE:
        if int(counts.get(lv, 0)) >= threshold:
            target = lv
    return target


def ai_review_expected_values_from_rates(
    rates: dict[str, float],
    sample_size: int = 3,
) -> tuple[dict[str, str], str, dict[str, int]]:
    sample_size = max(1, min(10, int(sample_size or 3)))
    completed: dict[str, float] = {}
    last_rate = 1.0
    for lv in LEVELS_AE:
        raw = rates.get(lv, last_rate)
        rate = float(raw or 0.0)
        if rate > 1.0:
            rate = rate / 100.0
        rate = max(0.0, min(1.0, rate))
        rate = min(last_rate, rate)
        completed[lv] = rate
        last_rate = rate
    counts = {
        lv: round(completed[lv] * sample_size)
        for lv in LEVELS_AE
    }
    counts = ai_review_normalize_counts(counts, sample_size)
    target = ai_review_target_from_counts(counts, sample_size)
    expected = {
        f"{lv} 예상": f"{counts[lv]}/{sample_size}"
        for lv in LEVELS_AE
    }
    return expected, target, counts


def ai_review_rate_summary(rates: dict[str, float]) -> str:
    parts = []
    for lv in LEVELS_AE:
        if lv not in rates:
            continue
        rate = float(rates[lv] or 0.0)
        if rate <= 1.0:
            rate *= 100.0
        parts.append(f"{lv} {rate:.0f}%")
    return ", ".join(parts)
