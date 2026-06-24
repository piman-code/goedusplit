"""Optional AI provider helpers for Goedu-Split.

The desktop app keeps analysis local by default.  This module is only used
when the user explicitly chooses an external/local model provider from the UI.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path
import urllib.error
import urllib.parse
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


def _default_codex_cli_workdir() -> Path:
    override = os.environ.get("GOEDUSPLIT_CODEX_WORKDIR", "").strip()
    if override:
        return Path(override).expanduser()
    return Path(tempfile.gettempdir()) / "goedusplit-codex-ai"


def _codex_cli_extra_paths() -> tuple[str, ...]:
    if os.name == "nt":
        candidates = [
            os.environ.get("LOCALAPPDATA", "") and str(Path(os.environ["LOCALAPPDATA"]) / "Programs" / "codex"),
            os.environ.get("APPDATA", "") and str(Path(os.environ["APPDATA"]) / "npm"),
            os.environ.get("ProgramFiles", "") and str(Path(os.environ["ProgramFiles"]) / "nodejs"),
            os.environ.get("ProgramFiles(x86)", "") and str(Path(os.environ["ProgramFiles(x86)"]) / "nodejs"),
        ]
        return tuple(path for path in candidates if path)
    return (
        "/opt/homebrew/bin",
        "/usr/local/bin",
        "/usr/bin",
        "/bin",
        "/usr/sbin",
        "/sbin",
    )


CODEX_CLI_WORKDIR = _default_codex_cli_workdir()
CODEX_CLI_EXTRA_PATHS = _codex_cli_extra_paths()


def _codex_cli_path_from_config() -> str:
    if os.environ.get("CODEX_HOME"):
        codex_home = Path(os.environ["CODEX_HOME"]).expanduser()
    else:
        home = os.environ.get("USERPROFILE") or os.environ.get("HOME")
        try:
            codex_home = (Path(home) if home else Path.home()) / ".codex"
        except RuntimeError:
            return ""
    config_path = codex_home / "config.toml"
    try:
        text = config_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    match = re.search(r"(?m)^\s*CODEX_CLI_PATH\s*=\s*(['\"])(.*?)\1", text)
    if not match:
        return ""
    return match.group(2).strip()


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
        if self.provider == "mlx_compatible":
            return "MLX/LM Studio 로컬"
        if self.provider == "openai_cloud":
            return "OpenAI 클라우드"
        if self.provider == "codex_cli":
            return "Codex CLI 클라우드"
        if self.provider == "openai_compatible":
            return "OpenAI 호환"
        return "로컬 초안"


def default_endpoint(provider: str) -> str:
    if provider == "ollama":
        return "http://127.0.0.1:11434/api/chat"
    if provider == "mlx_compatible":
        return "http://127.0.0.1:8080/v1/chat/completions"
    if provider == "openai_cloud":
        return "https://api.openai.com/v1/chat/completions"
    if provider == "codex_cli":
        return ""
    if provider == "openai_compatible":
        return "http://127.0.0.1:8080/v1/chat/completions"
    return ""


def default_model(provider: str) -> str:
    if provider == "ollama":
        return "gemma4:e4b"
    if provider == "mlx_compatible":
        return "mlx-community/Qwen3-0.6B-4bit"
    if provider == "openai_cloud":
        return "gpt-5.5"
    if provider == "codex_cli":
        return "gpt-5.5"
    if provider == "openai_compatible":
        return "local-model"
    return ""


def normalize_endpoint(provider: str, endpoint: str = "") -> str:
    value = (endpoint or "").strip()
    if not value:
        return default_endpoint(provider)
    value = value.replace(" ", "")
    if value.startswith("0.1:"):
        value = f"127.0.0.1:{value.split(':', 1)[1]}"
    if value.startswith(("127.0.0.1", "localhost", "0.0.0.0")):
        value = f"http://{value}"
    if provider == "ollama":
        if "11434" in value and "/api/" not in value:
            value = value.rstrip("/") + "/api/chat"
        if value.endswith("/api/generate"):
            value = value[:-len("/api/generate")] + "/api/chat"
    elif provider in {"mlx_compatible", "openai_compatible"}:
        value = value.rstrip("/")
        if value.endswith("/v1"):
            value = value + "/chat/completions"
        elif "/v1/" not in value and not value.endswith("/chat/completions"):
            value = value + "/v1/chat/completions"
    return value


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


def run_completion(prompt: str, config: AIProviderConfig, max_tokens: int | None = None) -> str:
    if config.provider == "local_draft":
        return ""
    if config.provider == "ollama":
        return _run_ollama(prompt, config, max_tokens=max_tokens)
    if config.provider == "codex_cli":
        return _run_codex_cli(prompt, config, max_tokens=max_tokens)
    if config.provider in {"openai_compatible", "mlx_compatible", "openai_cloud"}:
        return _run_openai_compatible(prompt, config, max_tokens=max_tokens)
    raise ValueError(f"지원하지 않는 AI 제공자입니다: {config.provider}")


def _timeout_message(timeout: int) -> str:
    return (
        f"AI 요청 시간이 초과되었습니다({timeout}초). "
        "로컬 AI라면 모델이 너무 크거나, 첫 실행 모델 다운로드/로딩 중이거나, "
        "서버는 열렸지만 아직 답변 가능한 상태가 아닐 수 있습니다."
    )


def _get_json(url: str, headers: dict[str, str], timeout: int) -> dict[str, Any]:
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=max(5, int(timeout))) as response:
            body = response.read().decode("utf-8", errors="replace")
            return json.loads(body)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"AI 요청 실패 HTTP {exc.code}: {body[:600]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"AI 제공자에 연결하지 못했습니다: {exc.reason}") from exc
    except (TimeoutError, socket.timeout) as exc:
        raise RuntimeError(_timeout_message(max(5, int(timeout)))) from exc


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
    except (TimeoutError, socket.timeout) as exc:
        raise RuntimeError(_timeout_message(max(5, int(timeout)))) from exc


def _ollama_tags_endpoint(endpoint: str) -> str:
    normalized = normalize_endpoint("ollama", endpoint)
    if "/api/" in normalized:
        return normalized.split("/api/", 1)[0].rstrip("/") + "/api/tags"
    return normalized.rstrip("/") + "/api/tags"


def _ollama_version_endpoint(endpoint: str) -> str:
    normalized = normalize_endpoint("ollama", endpoint)
    if "/api/" in normalized:
        return normalized.split("/api/", 1)[0].rstrip("/") + "/api/version"
    return normalized.rstrip("/") + "/api/version"


def get_ollama_version(endpoint: str = "", timeout: int = 5) -> str:
    data = _get_json(_ollama_version_endpoint(endpoint), {}, timeout)
    return str(data.get("version") or "").strip()


def list_ollama_models(endpoint: str = "", timeout: int = 10) -> list[str]:
    data = _get_json(_ollama_tags_endpoint(endpoint), {}, timeout)
    models = data.get("models") or []
    names = [str(item.get("name", "")).strip() for item in models if isinstance(item, dict)]
    return [name for name in names if name]


def _openai_models_endpoint(endpoint: str, provider: str = "openai_compatible") -> str:
    normalized = normalize_endpoint(provider, endpoint)
    if "/v1/" in normalized:
        return normalized.split("/v1/", 1)[0].rstrip("/") + "/v1/models"
    parsed = urllib.parse.urlparse(normalized)
    root = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else normalized.rstrip("/")
    return root + "/v1/models"


def list_openai_compatible_models(
    endpoint: str = "",
    api_key: str = "",
    provider: str = "openai_compatible",
    timeout: int = 10,
) -> list[str]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    data = _get_json(_openai_models_endpoint(endpoint, provider), headers, timeout)
    models = data.get("data") or []
    names = [str(item.get("id", "")).strip() for item in models if isinstance(item, dict)]
    return [name for name in names if name]


def _message_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or ""))
        return "\n".join(part for part in parts if part).strip()
    return str(value)


def _chat_output_text(choice: dict[str, Any]) -> str:
    message = choice.get("message") or {}
    if isinstance(message, dict):
        for key in ("content", "text", "reasoning_content", "reasoning", "thinking"):
            text = _message_text(message.get(key)).strip()
            if text:
                return text
    return _message_text(choice.get("text")).strip()


def _system_prompt() -> str:
    return (
        "너는 성취평가 문항 검토 보조자다. 반드시 요청한 JSON 형식만 반환한다. "
        "추론 과정, thinking process, 설명 문단, markdown 코드는 출력하지 않는다."
    )


def _user_prompt_for_provider(prompt: str, config: AIProviderConfig) -> str:
    if config.provider == "mlx_compatible" and "qwen3" in (config.model or "").lower():
        return "/no_think\n" + prompt
    return prompt


def _run_ollama(prompt: str, config: AIProviderConfig, max_tokens: int | None = None) -> str:
    endpoint = normalize_endpoint("ollama", config.endpoint)
    model = config.model or default_model("ollama")
    options = {"temperature": 0.2}
    if max_tokens is not None:
        options["num_predict"] = int(max_tokens)
    payload = {
        "model": model,
        "stream": False,
        "messages": [
            {"role": "system", "content": _system_prompt()},
            {"role": "user", "content": _user_prompt_for_provider(prompt, config)},
        ],
        "options": options,
    }
    data = _post_json(endpoint, payload, {"Content-Type": "application/json"}, config.timeout)
    message = data.get("message") or {}
    return _message_text(message.get("content") or data.get("response")).strip()


def _run_openai_compatible(prompt: str, config: AIProviderConfig, max_tokens: int | None = None) -> str:
    endpoint = normalize_endpoint(config.provider, config.endpoint)
    model = config.model or default_model(config.provider)
    headers = {"Content-Type": "application/json"}
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"
    payload = {
        "model": model,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": _system_prompt()},
            {"role": "user", "content": _user_prompt_for_provider(prompt, config)},
        ],
    }
    if max_tokens is not None:
        payload["max_tokens"] = int(max_tokens)
    if config.provider == "mlx_compatible" and "qwen3" in model.lower():
        payload["chat_template_kwargs"] = {"enable_thinking": False}
    data = _post_json(endpoint, payload, headers, config.timeout)
    choices = data.get("choices") or []
    if not choices:
        return ""
    first = choices[0]
    return _chat_output_text(first)


def _codex_review_rows_schema_path() -> Path:
    CODEX_CLI_WORKDIR.mkdir(parents=True, exist_ok=True)
    schema_path = CODEX_CLI_WORKDIR / "ai-review-rows.schema.json"
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "required": ["rows"],
        "additionalProperties": False,
        "properties": {
            "rows": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "required": CANONICAL_HEADERS,
                    "additionalProperties": False,
                    "properties": {
                        header: {"type": "string"}
                        for header in CANONICAL_HEADERS
                    },
                },
            },
        },
    }
    schema_path.write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")
    return schema_path


def _codex_cli_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("OPENAI_API_KEY", None)
    env.pop("CODEX_API_KEY", None)
    current_path = env.get("PATH", "")
    path_parts = [part for part in CODEX_CLI_EXTRA_PATHS if part]
    if current_path:
        path_parts.append(current_path)
    env["PATH"] = os.pathsep.join(dict.fromkeys(path_parts))
    env["TERM"] = "xterm-256color"
    env["NO_COLOR"] = "1"
    return env


def find_codex_cli() -> str:
    """Find Codex CLI even when the GUI app has a minimal PATH."""
    candidates: list[str] = []
    env_path = os.environ.get("CODEX_CLI_PATH", "").strip()
    if env_path:
        candidates.append(env_path)
    config_path = _codex_cli_path_from_config()
    if config_path:
        candidates.append(config_path)
    for executable in ("codex", "codex.cmd", "codex.exe"):
        which_path = shutil.which(executable)
        if which_path:
            candidates.append(which_path)
    executable_names = ("codex.cmd", "codex.exe", "codex") if os.name == "nt" else ("codex",)
    for base in CODEX_CLI_EXTRA_PATHS:
        candidates.extend(str(Path(base) / name) for name in executable_names)
    seen: set[str] = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        path = Path(candidate).expanduser()
        if path.exists() and os.access(path, os.X_OK):
            return str(path)
    return ""


def _codex_cli_missing_message() -> str:
    if os.name == "nt":
        return (
            "codex CLI를 찾지 못했습니다. Windows 터미널에서 `where codex`와 `codex login status`를 확인해 주세요.\n"
            "앱에서만 실패한다면 CODEX_CLI_PATH 환경변수에 codex.cmd 전체 경로를 지정한 뒤 다시 여세요."
        )
    return (
        "codex CLI를 찾지 못했습니다. 터미널에서는 보이는데 앱에서 실패한다면 macOS GUI PATH 문제일 수 있습니다.\n"
        "Homebrew 설치 기준 `/opt/homebrew/bin/codex`를 확인하고, 터미널에서 `codex login`을 실행한 뒤 앱을 다시 여세요."
    )


def _run_codex_cli_status_command(args: list[str], timeout: int = 15) -> str:
    exe = find_codex_cli()
    if not exe:
        raise RuntimeError(_codex_cli_missing_message())
    try:
        completed = subprocess.run(
            [exe, *args],
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            cwd=str(CODEX_CLI_WORKDIR) if CODEX_CLI_WORKDIR.exists() else None,
            env=_codex_cli_env(),
            timeout=max(5, int(timeout)),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(_timeout_message(max(5, int(timeout)))) from exc
    output = (completed.stdout or completed.stderr or "").strip()
    if completed.returncode != 0:
        raise RuntimeError(output or f"codex {' '.join(args)} 실패: {completed.returncode}")
    return output


def _codex_cli_prompt(prompt: str, max_tokens: int | None = None) -> str:
    token_note = f"\n최대 출력 길이는 약 {int(max_tokens)} 토큰 안에서 맞춘다." if max_tokens else ""
    return (
        "너는 Goedu-Split 앱 안에서 호출된 성취평가 문항 검토 보조자다.\n"
        "중요: 이 요청은 코드 수정 작업이 아니다. 파일을 읽거나 고치거나 명령을 실행하지 말고, "
        "제공된 텍스트만 근거로 교사용 검토표 JSON을 작성한다.\n"
        "반드시 rows 배열을 가진 JSON 객체만 출력한다. 설명, 마크다운, 코드블록, 진행상황 문장은 출력하지 않는다.\n"
        f"rows의 각 객체는 다음 13개 문자열 키만 사용한다: {json.dumps(CANONICAL_HEADERS, ensure_ascii=False)}.\n"
        "학생 개인정보로 보이는 값은 재출력하지 말고 [학생명], [반/번호] 같은 익명 표기로 유지한다."
        f"{token_note}\n\n"
        "[검토 요청]\n"
        f"{prompt}"
    )


def _run_codex_cli(prompt: str, config: AIProviderConfig, max_tokens: int | None = None) -> str:
    exe = find_codex_cli()
    if not exe:
        raise RuntimeError(_codex_cli_missing_message())
    schema_path = _codex_review_rows_schema_path()
    CODEX_CLI_WORKDIR.mkdir(parents=True, exist_ok=True)
    output_path = CODEX_CLI_WORKDIR / "ai-review-output.json"
    if output_path.exists():
        try:
            output_path.unlink()
        except OSError:
            pass
    command = [
        exe,
        "exec",
        "--sandbox",
        "read-only",
        "--skip-git-repo-check",
        "--output-schema",
        str(schema_path),
        "-o",
        str(output_path),
    ]
    model = (config.model or default_model("codex_cli")).strip()
    if model:
        command.extend(["--model", model])
    command.append("-")
    try:
        completed = subprocess.run(
            command,
            input=_codex_cli_prompt(prompt, max_tokens=max_tokens),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            cwd=str(CODEX_CLI_WORKDIR),
            env=_codex_cli_env(),
            timeout=max(30, int(config.timeout or 60)),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(_timeout_message(max(30, int(config.timeout or 60)))) from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        if "auth" in detail.lower() or "login" in detail.lower() or "unauthorized" in detail.lower():
            raise RuntimeError("Codex CLI OAuth 로그인이 필요합니다. 터미널에서 `codex login`을 실행한 뒤 다시 시도하세요.")
        if any(term in detail.lower() for term in ("dns", "lookup", "resolve", "network", "connect", "reachability")):
            raise RuntimeError("Codex CLI가 ChatGPT에 연결하지 못했습니다. 네트워크, DNS, VPN, 방화벽 상태를 확인한 뒤 다시 시도하세요.")
        raise RuntimeError(f"Codex CLI 실행 실패: {detail[:1200] or completed.returncode}")
    output = ""
    if output_path.exists():
        output = output_path.read_text(encoding="utf-8", errors="replace").strip()
    if not output:
        output = (completed.stdout or "").strip()
    if not output:
        raise RuntimeError("Codex CLI가 빈 응답을 반환했습니다.")
    return output


def probe_codex_cli_chat(model: str = "", timeout: int = 60) -> str:
    config = AIProviderConfig(
        provider="codex_cli",
        model=model or default_model("codex_cli"),
        timeout=max(30, int(timeout)),
    )
    return _run_codex_cli(
        '다음 JSON 객체만 반환하세요: {"rows":[{"구분":"상태","번호/요소":"테스트","성취기준 후보":"","평가유형":"선택형","목표수준 후보":"C","난이도 후보":"보통","A 예상":"3/3","B 예상":"3/3","C 예상":"2/3","D 예상":"1/3","E 예상":"0/3","근거":"Codex CLI OAuth 연결 확인","다음 확인":""}]}',
        config,
        max_tokens=256,
    )


def check_codex_cli_oauth(model: str = "", timeout: int = 60) -> dict[str, str]:
    """Verify the local Codex CLI ChatGPT OAuth path with a real JSON request."""
    CODEX_CLI_WORKDIR.mkdir(parents=True, exist_ok=True)
    version = _run_codex_cli_status_command(["--version"], timeout=15)
    status = _run_codex_cli_status_command(["login", "status"], timeout=15)
    if "chatgpt" not in status.lower():
        raise RuntimeError("Codex CLI가 ChatGPT OAuth로 로그인되어 있지 않습니다. 터미널에서 `codex login`을 실행해 주세요.")
    smoke = probe_codex_cli_chat(model=model, timeout=timeout)
    return {"version": version, "status": status, "smoke": smoke}


def probe_openai_compatible_chat(
    endpoint: str = "",
    api_key: str = "",
    provider: str = "openai_compatible",
    model: str = "",
    timeout: int = 20,
) -> str:
    config = AIProviderConfig(
        provider=provider,
        endpoint=endpoint,
        model=model or default_model(provider),
        api_key=api_key,
        timeout=max(5, int(timeout)),
    )
    return _run_openai_compatible(
        '다음 JSON만 반환하세요: {"status":"ok"}',
        config,
        max_tokens=128,
    )


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
