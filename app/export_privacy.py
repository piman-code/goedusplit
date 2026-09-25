"""Keep student identity out of exported files unless the teacher opts in.

Pseudonyms replace direct identifiers (학번, 반/번호, 이름). Numbers are
shuffled so they do not follow roster order. This is pseudonymization, not
anonymization: class and scores can still re-identify a student for anyone
holding the roster.
"""

from __future__ import annotations

import copy
import csv
import hashlib
import hmac
import io
import random
import re
import secrets

CSV_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

REAL_IDENTITY_CHECKBOX_TEXT = "학번·반/번호·이름 실명 포함 (개인정보)"
REAL_IDENTITY_WARNING = (
    "학번·반/번호·이름이 그대로 들어간 파일을 만듭니다.\n\n"
    "이 파일은 학생 개인정보입니다. 메일·메신저·공유 드라이브로 보내거나 "
    "학교 밖 PC에 두지 마세요.\n\n실명을 포함해 저장할까요?"
)


def pseudonym_ids(count: int, rng: random.Random | None = None) -> list[str]:
    """One pseudonym per student, numbered in shuffled order.

    Zero padding grows with the count so text order matches number order.
    """
    width = max(3, len(str(count)))
    numbers = list(range(1, count + 1))
    (rng or random.SystemRandom()).shuffle(numbers)
    return [f"학생 {number:0{width}d}" for number in numbers]


def csv_safe_cell(value):
    """Stop spreadsheet apps from running a text cell as a formula."""
    if isinstance(value, str) and value.startswith(CSV_FORMULA_PREFIXES):
        return "'" + value
    return value


def _is_number(text: str) -> bool:
    try:
        float(text)
    except ValueError:
        return False
    return True


def sanitize_csv_text(text: str) -> str:
    """Escape formula-like cells in CSV text written by the calculator.

    Cells read back from CSV are all text, so numbers such as -5 are kept as is.
    """
    bom = "\ufeff" if text.startswith("\ufeff") else ""
    body = text[len(bom):]
    newline = "\r\n" if "\r\n" in body else "\n"
    out = io.StringIO()
    writer = csv.writer(out, lineterminator=newline)
    for row in csv.reader(io.StringIO(body, newline="")):
        writer.writerow([cell if _is_number(cell) else csv_safe_cell(cell) for cell in row])
    return bom + out.getvalue()


def new_student_hash_key() -> bytes:
    return secrets.token_bytes(32)


def student_hash(key: bytes, sid, class_no="", name="") -> str:
    """Link one student across subject snapshots without storing 학번 or 이름.

    Keyed so the small 학번 space cannot be brute-forced from a snapshot alone.
    Uses the same identity as the old portfolio key (학번 with 반/번호·이름), so a
    reused or sequential 학번 does not merge different students.
    """
    sid = str(sid or "").strip()
    rest = f"class:{str(class_no or '').strip()}|name:{str(name or '').strip()}"
    source = f"sid:{sid}|{rest}" if sid else rest
    return hmac.new(key, source.encode("utf-8"), hashlib.sha256).hexdigest()[:24]


def student_result_table(students, levels, *, include_identity: bool,
                         pseudonyms: list[str] | None = None) -> tuple[list[str], list[list]]:
    """Headers and rows for 학생결과.csv. Pseudonymized rows are sorted by pseudonym."""
    score_headers = ["학급", "선택형", "서답형", "기타", "지필총점", "수행환산", "환산점수", "성취도"]
    id_headers = ["학번", "반/번호", "이름"] if include_identity else ["가명 ID"]
    rows = []
    for index, st in enumerate(students):
        identity = [st.sid, st.class_no, st.name] if include_identity else [pseudonyms[index]]
        rows.append(identity + [
            st.grade_class, st.multi_score, st.serdap_score, st.etc_score,
            round(st.total, 2), round(st.perform_score, 2), round(st.final_score, 2),
            levels[index],
        ])
    if not include_identity:
        rows.sort(key=lambda row: row[0])
    return id_headers + score_headers, rows


def _file_name_only(path) -> str:
    return re.split(r"[\\/]", str(path or ""))[-1]


def pseudonymize_evidence_payload(payload: dict, pseudonyms: list[str]) -> dict:
    """Copy of the spliter evidence payload without student identity or local folders.

    Students are sorted by pseudonym so list order does not reveal roster order.
    The calculator reseeds its sampling on every load, so order carries no meaning there.
    """
    result = copy.deepcopy(payload)
    for index, student in enumerate(result.get("students", [])):
        student["id"] = pseudonyms[index]
        student["name"] = pseudonyms[index]
        student["classNo"] = ""
    result.get("students", []).sort(key=lambda student: student["id"])
    result["sourceFiles"] = {
        key: _file_name_only(value) for key, value in (result.get("sourceFiles") or {}).items()
    }
    return result
