"""Optional AI provider helpers for Goedu-Split.

The desktop app keeps analysis local by default.  This module is only used
when the user explicitly chooses an external/local model provider from the UI.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


CANONICAL_HEADERS = [
    "구분",
    "번호/요소",
    "성취기준 후보",
    "평가유형",
    "목표수준 후보",
    "난이도 후보",
    "A 예상",
    "B 예상",
    "C 예상",
    "D 예상",
    "E 예상",
    "근거",
    "다음 확인",
]

LEVELS_AE = ["A", "B", "C", "D", "E"]


@dataclass
class AIProviderConfig:
    provider: str = "local_draft"
    endpoint: str = ""
    model: str = ""
    api_key: str = ""
    timeout: int = 60

    @property
    def label(self) -> str:
        if self.provider == "ollama":
            return "Ollama 로컬"
        if self.provider == "openai_compatible":
            return "OpenAI 호환"
        return "로컬 초안"


def default_endpoint(provider: str) -> str:
    if provider == "ollama":
        return "http://127.0.0.1:11434/api/chat"
    if provider == "openai_compatible":
        return "http://127.0.0.1:8080/v1/chat/completions"
    return ""


def default_model(provider: str) -> str:
    if provider == "ollama":
        return "qwen2.5:7b"
    if provider == "openai_compatible":
        return "gpt-4.1-mini"
    return ""


def scrub_personal_data(text: str, student_names: list[str] | None = None) -> str:
    """Remove obvious personal data before cloud requests.

    This is intentionally conservative: it removes known student names from the
    loaded exam data and common identifiers, but it does not attempt to rewrite
    mathematical or rubric language.
    """
    cleaned = text
    for name in sorted(set(student_names or []), key=len, reverse=True):
        if len(name.strip()) >= 2:
            cleaned = cleaned.replace(name.strip(), "[학생명]")
    cleaned = re.sub(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", "[이메일]", cleaned)
    cleaned = re.sub(r"\b01[016789]-?\d{3,4}-?\d{4}\b", "[전화번호]", cleaned)
    cleaned = re.sub(r"\b\d{1,2}/\d{1,2}\b", "[반/번호]", cleaned)
    return cleaned


def run_completion(prompt: str, config: AIProviderConfig) -> str:
    if config.provider == "local_draft":
        return ""
    if config.provider == "ollama":
        return _run_ollama(prompt, config)
    if config.provider == "openai_compatible":
        return _run_openai_compatible(prompt, config)
    raise ValueError(f"지원하지 않는 AI 제공자입니다: {config.provider}")


def _post_json(url: str, payload: dict[str, Any], headers: dict[str, str], timeout: int) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=max(5, int(timeout))) as response:
            body = response.read().decode("utf-8", errors="replace")
            return json.loads(body)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"AI 요청 실패 HTTP {exc.code}: {body[:600]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"AI 제공자에 연결하지 못했습니다: {exc.reason}") from exc


def _run_ollama(prompt: str, config: AIProviderConfig) -> str:
    endpoint = config.endpoint or default_endpoint("ollama")
    model = config.model or default_model("ollama")
    payload = {
        "model": model,
        "stream": False,
        "messages": [
            {"role": "system", "content": "너는 성취평가 문항 검토 보조자다. 반드시 요청한 JSON 형식만 반환한다."},
            {"role": "user", "content": prompt},
        ],
        "options": {"temperature": 0.2},
    }
    data = _post_json(endpoint, payload, {"Content-Type": "application/json"}, config.timeout)
    message = data.get("message") or {}
    return str(message.get("content") or data.get("response") or "")


def _run_openai_compatible(prompt: str, config: AIProviderConfig) -> str:
    endpoint = config.endpoint or default_endpoint("openai_compatible")
    model = config.model or default_model("openai_compatible")
    headers = {"Content-Type": "application/json"}
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"
    payload = {
        "model": model,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": "너는 성취평가 문항 검토 보조자다. 반드시 요청한 JSON 형식만 반환한다."},
            {"role": "user", "content": prompt},
        ],
    }
    data = _post_json(endpoint, payload, headers, config.timeout)
    choices = data.get("choices") or []
    if not choices:
        return ""
    first = choices[0]
    message = first.get("message") or {}
    return str(message.get("content") or first.get("text") or "")


def parse_review_rows(text: str) -> list[dict[str, str]]:
    """Parse model output into canonical Korean review rows."""
    parsed = _parse_json_rows(text)
    if parsed:
        return parsed
    return _parse_pipe_table(text)


def _parse_json_rows(text: str) -> list[dict[str, str]]:
    candidates = [text.strip()]
    fenced = re.findall(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    candidates.extend(part.strip() for part in fenced)
    bracket = re.search(r"(\[[\s\S]*\])", text)
    if bracket:
        candidates.append(bracket.group(1))
    brace = re.search(r"(\{[\s\S]*\})", text)
    if brace:
        candidates.append(brace.group(1))

    for candidate in candidates:
        if not candidate:
            continue
        try:
            data = json.loads(candidate)
        except Exception:
            continue
        if isinstance(data, dict):
            data = data.get("rows") or data.get("items") or data.get("문항") or []
        if not isinstance(data, list):
            continue
        rows = [_normalize_row(item) for item in data if isinstance(item, dict)]
        rows = [row for row in rows if any(row.values())]
        if rows:
            return rows
    return []


def _parse_pipe_table(text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for raw in text.splitlines():
        line = raw.strip().strip("|")
        if "|" not in line:
            continue
        parts = [part.strip() for part in line.split("|")]
        if len(parts) < 6:
            continue
        if all(re.fullmatch(r"[-:\s]+", part or "-") for part in parts):
            continue
        if any("성취기준" in part for part in parts[:3]) and any("평가유형" in part for part in parts[:5]):
            continue
        if len(parts) >= 11:
            row = {
                "구분": parts[0] if len(parts) > 0 else "문항",
                "번호/요소": parts[1] if len(parts) > 1 else "",
                "성취기준 후보": parts[2] if len(parts) > 2 else "",
                "평가유형": parts[3] if len(parts) > 3 else "",
                "목표수준 후보": parts[4] if len(parts) > 4 else "",
                "난이도 후보": parts[5] if len(parts) > 5 else "",
                "A 예상": parts[6] if len(parts) > 6 else "",
                "B 예상": parts[7] if len(parts) > 7 else "",
                "C 예상": parts[8] if len(parts) > 8 else "",
                "D 예상": parts[9] if len(parts) > 9 else "",
                "E 예상": parts[10] if len(parts) > 10 else "",
                "근거": parts[11] if len(parts) > 11 else "",
                "다음 확인": parts[12] if len(parts) > 12 else "",
            }
        else:
            row = {
                "구분": parts[0] if len(parts) > 0 else "문항",
                "번호/요소": parts[1] if len(parts) > 1 else "",
                "성취기준 후보": parts[2] if len(parts) > 2 else "",
                "평가유형": parts[3] if len(parts) > 3 else "",
                "목표수준 후보": parts[4] if len(parts) > 4 else "",
                "난이도 후보": parts[5] if len(parts) > 5 else "",
                "A 예상": "",
                "B 예상": "",
                "C 예상": "",
                "D 예상": "",
                "E 예상": "",
                "근거": parts[6] if len(parts) > 6 else "",
                "다음 확인": parts[7] if len(parts) > 7 else "",
            }
        rows.append(row)
    return rows


def _normalize_row(item: dict[str, Any]) -> dict[str, str]:
    aliases = {
        "구분": ["구분", "kind", "type_kind"],
        "번호/요소": ["번호/요소", "번호", "요소", "label", "number", "item", "element"],
        "성취기준 후보": ["성취기준 후보", "성취기준", "standard", "achievement_standard"],
        "평가유형": ["평가유형", "유형", "assessment_type", "review_type"],
        "목표수준 후보": ["목표수준 후보", "목표수준", "성취수준", "target", "target_level"],
        "난이도 후보": ["난이도 후보", "난이도", "difficulty"],
        "A 예상": ["A 예상", "A", "A예상", "A 정답", "A정답", "A_expected", "a_expected", "expected_A"],
        "B 예상": ["B 예상", "B", "B예상", "B 정답", "B정답", "B_expected", "b_expected", "expected_B"],
        "C 예상": ["C 예상", "C", "C예상", "C 정답", "C정답", "C_expected", "c_expected", "expected_C"],
        "D 예상": ["D 예상", "D", "D예상", "D 정답", "D정답", "D_expected", "d_expected", "expected_D"],
        "E 예상": ["E 예상", "E", "E예상", "E 정답", "E정답", "E_expected", "e_expected", "expected_E"],
        "근거": ["근거", "evidence", "reason"],
        "다음 확인": ["다음 확인", "추가 확인 질문", "확인", "next_step", "question"],
    }
    row: dict[str, str] = {}
    for header, keys in aliases.items():
        value = ""
        for key in keys:
            if key in item and item[key] is not None:
                value = str(item[key]).strip()
                break
        row[header] = value
    expected = item.get("예상") or item.get("예상정답") or item.get("expected") or item.get("expected_rates")
    if isinstance(expected, dict):
        for level in LEVELS_AE:
            value = expected.get(level) or expected.get(level.lower())
            if value is not None:
                row[f"{level} 예상"] = str(value).strip()
    if not row["구분"]:
        row["구분"] = "수행평가" if "수행" in row["평가유형"] else "문항"
    return row
