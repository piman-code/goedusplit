"""Keep student identity out of exported files unless the teacher opts in.

Pseudonyms replace direct identifiers (학번, 반/번호, 이름). This is
pseudonymization, not anonymization: row order, class and scores can still
re-identify a student for anyone holding the roster.
"""

from __future__ import annotations

import copy
import re

CSV_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

REAL_IDENTITY_CHECKBOX_TEXT = "학번·반/번호·이름 실명 포함 (개인정보)"
REAL_IDENTITY_WARNING = (
    "학번·반/번호·이름이 그대로 들어간 파일을 만듭니다.\n\n"
    "이 파일은 학생 개인정보입니다. 메일·메신저·공유 드라이브로 보내거나 "
    "학교 밖 PC에 두지 마세요.\n\n실명을 포함해 저장할까요?"
)


def pseudonym_id(index: int) -> str:
    return f"학생 {index + 1:03d}"


def csv_safe_cell(value):
    """Stop spreadsheet apps from running a text cell as a formula."""
    if isinstance(value, str) and value.startswith(CSV_FORMULA_PREFIXES):
        return "'" + value
    return value


def student_result_table(students, levels, *, include_identity: bool) -> tuple[list[str], list[list]]:
    """Headers and rows for 학생결과.csv."""
    score_headers = ["학급", "선택형", "서답형", "기타", "지필총점", "수행환산", "환산점수", "성취도"]
    id_headers = ["학번", "반/번호", "이름"] if include_identity else ["가명 ID"]
    rows = []
    for index, st in enumerate(students):
        identity = [st.sid, st.class_no, st.name] if include_identity else [pseudonym_id(index)]
        rows.append(identity + [
            st.grade_class, st.multi_score, st.serdap_score, st.etc_score,
            round(st.total, 2), round(st.perform_score, 2), round(st.final_score, 2),
            levels[index],
        ])
    return id_headers + score_headers, rows


def _file_name_only(path) -> str:
    return re.split(r"[\\/]", str(path or ""))[-1]


def pseudonymize_evidence_payload(payload: dict) -> dict:
    """Copy of the spliter evidence payload without student identity or local folders."""
    result = copy.deepcopy(payload)
    for index, student in enumerate(result.get("students", [])):
        student["id"] = pseudonym_id(index)
        student["name"] = pseudonym_id(index)
        student["classNo"] = ""
    result["sourceFiles"] = {
        key: _file_name_only(value) for key, value in (result.get("sourceFiles") or {}).items()
    }
    return result
