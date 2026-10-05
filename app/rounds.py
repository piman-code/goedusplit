"""회차(학기·차수) 기록과 비교. 화면 없이 계산만 한다.

분석할 때마다 한 줄 요약(평균·표준편차·성취수준 분포·분할점수·학생별 성취수준)을 회차 기록으로 남기고,
저장된 두 회차를 비교하거나 여러 회차의 추이를 만든다. 학생은 이름 없이 해시로만 기록한다.
같은 과목·학년·학년도·학기·차수는 최신 분석 하나만 남긴다(다시 분석하면 덮어쓴다).
"""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path

LEVELS = ["A", "B", "C", "D", "E", "미도달"]      # 앞쪽이 높은 수준
RECORD_VERSION = 1


def _nfc(text) -> str:
    return unicodedata.normalize("NFC", str(text or ""))


def parse_round(*texts) -> tuple[int | None, int | None]:
    """파일 이름·제목에서 (학기, 차수)를 찾는다. '1학기 1차', '2차 정기시험' 등. 못 찾으면 None."""
    semester = round_no = None
    for text in texts:
        text = _nfc(text)
        if semester is None:
            found = re.search(r"([12])\s*학기", text)
            if found:
                semester = int(found.group(1))
        if round_no is None:
            found = re.search(r"(?<![0-9-])([1-4])\s*차(?!이|원|시)", text)
            if found:
                round_no = int(found.group(1))
    return semester, round_no


def parse_year(*texts) -> int | None:
    for text in texts:
        found = re.search(r"(20\d{2})\s*학년도", _nfc(text))
        if found:
            return int(found.group(1))
    return None


def round_name(semester: int | None, round_no: int | None) -> str:
    """'1학기 1차' / '1학기' / '1차' / '회차 미지정'."""
    parts = []
    if semester:
        parts.append(f"{semester}학기")
    if round_no:
        parts.append(f"{round_no}차")
    return " ".join(parts) or "회차 미지정"


def round_label(year: int | None, semester: int | None, round_no: int | None) -> str:
    name = round_name(semester, round_no)
    return f"{year}학년도 {name}" if year else name


def tag_of(name: str) -> tuple[int | None, int | None]:
    """폴더 일괄 불러오기에서 파일을 시험별로 맞추기 위한 (학기, 차수)."""
    return parse_round(name)


def tags_conflict(a: tuple, b: tuple) -> bool:
    """두 파일이 서로 다른 시험을 가리키는가. 한쪽이 모르면(None) 충돌이 아니다."""
    return any(x is not None and y is not None and x != y for x, y in zip(a, b))


def record_key(subject: str, grade: str, year, semester, round_no) -> str:
    return "|".join(str(part or "") for part in (_nfc(subject), _nfc(grade), year, semester, round_no))


def sort_key(record: dict):
    return (record.get("year") or 0, record.get("semester_no") or 0, record.get("round_no") or 0,
            str(record.get("saved_at", "")))


def build_record(*, subject, grade, year, semester, round_no, n_students, mean, std, level_pct, level_n,
                 cuts, students, weights=None, saved_at=None) -> dict:
    """students: {student_hash: {'level': 'A', 'score': 71.5}}"""
    return {
        "kind": "round", "version": RECORD_VERSION,
        "saved_at": saved_at or datetime.now().isoformat(timespec="seconds"),
        "subject": subject, "grade": grade, "year": year, "semester_no": semester, "round_no": round_no,
        "label": round_label(year, semester, round_no),
        "n_students": int(n_students), "mean": round(float(mean), 2), "std": round(float(std), 2),
        "level_pct": {lv: round(float(level_pct.get(lv, 0.0)), 2) for lv in LEVELS},
        "level_n": {lv: int(level_n.get(lv, 0)) for lv in LEVELS},
        "cuts": {lv: round(float(cuts.get(lv, 0.0)), 2) for lv in "ABCDE"},
        "weights": dict(weights or {}),
        "students": students,
    }


class RoundStore:
    """회차 기록 폴더. 파일 하나가 한 회차이고, 같은 회차는 같은 파일 이름이라 다시 분석하면 덮어쓴다."""

    def __init__(self, directory):
        self.directory = Path(directory)

    def path_for(self, record: dict) -> Path:
        key = record_key(record["subject"], record["grade"], record.get("year"), record.get("semester_no"),
                         record.get("round_no"))
        safe = re.sub(r"[\\/:*?\"<>|\s]+", "_", key).strip("_")
        return self.directory / f"round_{safe}.json"

    def save(self, record: dict) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.path_for(record)
        temp = path.with_suffix(".json.tmp")
        temp.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)
        return path

    def load_all(self) -> list[dict]:
        records = []
        for path in sorted(self.directory.glob("round_*.json")) if self.directory.exists() else []:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(data, dict) and data.get("kind") == "round" and isinstance(data.get("students"), dict):
                records.append(data)
        return sorted(records, key=sort_key)


def same_course(records: list[dict], subject: str, grade: str) -> list[dict]:
    subject, grade = _nfc(subject), _nfc(grade)
    return sorted((r for r in records if _nfc(r.get("subject")) == subject and _nfc(r.get("grade")) == grade),
                  key=sort_key)


def previous_year(records: list[dict], subject: str, grade: str, year, semester, round_no) -> dict | None:
    """같은 과목·학년·학기·차수의 전년도 기록. 없으면 None."""
    if not year:
        return None
    for record in reversed(same_course(records, subject, grade)):
        if (record.get("year") == year - 1 and record.get("semester_no") == semester
                and record.get("round_no") == round_no):
            return record
    return None


def _diff(a, b):
    return None if a is None or b is None else round(b - a, 2)


def compare(base: dict, other: dict) -> dict:
    """base(기준) → other(비교). rows: [(항목, 기준값, 비교값, 변화)], matrix, 이동 요약."""
    rows = [
        ("학생 수", base["n_students"], other["n_students"], _diff(base["n_students"], other["n_students"])),
        ("평균(점)", base["mean"], other["mean"], _diff(base["mean"], other["mean"])),
        ("표준편차(점)", base["std"], other["std"], _diff(base["std"], other["std"])),
    ]
    for lv in LEVELS:
        a, b = base["level_pct"].get(lv, 0.0), other["level_pct"].get(lv, 0.0)
        if lv == "미도달" and not (a or b):
            continue
        rows.append((f"{lv} 비율(%)", a, b, _diff(a, b)))
    for lv in "ABCDE":
        a, b = base["cuts"].get(lv, 0.0), other["cuts"].get(lv, 0.0)
        rows.append((f"{lv} 분할점수(점)", a, b, _diff(a, b)))
    matrix = {src: {dst: 0 for dst in LEVELS} for src in LEVELS}
    up = same = down = 0
    shared = set(base["students"]) & set(other["students"])
    for student in shared:
        src, dst = base["students"][student].get("level"), other["students"][student].get("level")
        if src not in matrix or dst not in matrix[src]:
            continue
        matrix[src][dst] += 1
        order = LEVELS.index(dst) - LEVELS.index(src)
        if order < 0:
            up += 1
        elif order > 0:
            down += 1
        else:
            same += 1
    return {"rows": rows, "matrix": matrix, "paired": up + same + down, "up": up, "same": same, "down": down,
            "only_base": len(set(base["students"]) - shared), "only_other": len(set(other["students"]) - shared)}


def trend(records: list[dict]) -> dict:
    """여러 회차의 추이. labels와 같은 길이의 값 목록."""
    years = {r.get("year") for r in records}
    labels = [r["label"] if len(years) > 1 else round_name(r.get("semester_no"), r.get("round_no")) for r in records]
    return {
        "labels": labels,
        "mean": [r["mean"] for r in records], "std": [r["std"] for r in records],
        "a_pct": [r["level_pct"].get("A", 0.0) for r in records],
        "ab_pct": [r["level_pct"].get("A", 0.0) + r["level_pct"].get("B", 0.0) for r in records],
        "cut_a": [r["cuts"].get("A", 0.0) for r in records],
    }
