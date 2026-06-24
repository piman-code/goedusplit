import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.ai_client import (
    AIProviderConfig,
    _run_codex_cli,
    check_codex_cli_oauth,
    default_model,
    find_codex_cli,
    get_ollama_version,
    parse_review_rows,
    scrub_personal_data,
)


class CodexCliProviderTests(unittest.TestCase):
    def test_codex_cli_uses_oauth_path_without_api_key_env(self):
        seen = {}

        def fake_run(command, **kwargs):
            seen["command"] = command
            seen["env"] = kwargs["env"]
            seen["input"] = kwargs["input"]
            output_path = Path(command[command.index("-o") + 1])
            output_path.write_text(
                json.dumps(
                    {
                        "rows": [
                            {
                                "구분": "문항",
                                "번호/요소": "1번",
                                "성취기준 후보": "[10공수1-01-01]",
                                "평가유형": "선택형",
                                "목표수준 후보": "C",
                                "난이도 후보": "보통",
                                "A 예상": "3/3",
                                "B 예상": "3/3",
                                "C 예상": "2/3",
                                "D 예상": "1/3",
                                "E 예상": "0/3",
                                "근거": "이전시험 성취수준별 정답률",
                                "다음 확인": "",
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            codex = Path(tmp) / ("codex.exe" if os.name == "nt" else "codex")
            codex.write_text("", encoding="utf-8")
            codex.chmod(0o755)
            with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test", "CODEX_API_KEY": "codex-test"}):
                with patch("app.ai_client._codex_cli_path_from_config", return_value=""):
                    with patch("app.ai_client.CODEX_CLI_EXTRA_PATHS", ()):
                        with patch("app.ai_client.shutil.which", return_value=str(codex)):
                            with patch("app.ai_client.subprocess.run", side_effect=fake_run):
                                output = _run_codex_cli(
                                    "문항을 검토하세요.",
                                    AIProviderConfig(provider="codex_cli", model="gpt-5.5", timeout=60),
                                )

        self.assertIn("문항", output)
        self.assertEqual(seen["command"][:4], [str(codex), "exec", "--sandbox", "read-only"])
        self.assertNotIn("--ephemeral", seen["command"])
        self.assertIn("--skip-git-repo-check", seen["command"])
        self.assertIn("--output-schema", seen["command"])
        self.assertNotIn("OPENAI_API_KEY", seen["env"])
        self.assertNotIn("CODEX_API_KEY", seen["env"])
        self.assertIn("파일을 읽거나 고치거나 명령을 실행하지 말고", seen["input"])
        self.assertEqual(parse_review_rows(output)[0]["목표수준 후보"], "C")

    def test_codex_cli_missing_binary_explains_login_path(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch("app.ai_client.CODEX_CLI_EXTRA_PATHS", ()):
                with patch("app.ai_client._codex_cli_path_from_config", return_value=""):
                    with patch("app.ai_client.shutil.which", return_value=None):
                        with self.assertRaisesRegex(RuntimeError, "codex CLI"):
                            _run_codex_cli("test", AIProviderConfig(provider="codex_cli"))

    def test_find_codex_cli_uses_homebrew_fallback_when_path_is_minimal(self):
        with tempfile.TemporaryDirectory() as tmp:
            codex = Path(tmp) / "codex"
            codex.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            codex.chmod(0o755)
            with patch.dict(os.environ, {}, clear=True):
                with patch("app.ai_client.CODEX_CLI_EXTRA_PATHS", (tmp,)):
                    with patch("app.ai_client._codex_cli_path_from_config", return_value=""):
                        with patch("app.ai_client.shutil.which", return_value=None):
                            self.assertEqual(find_codex_cli(), str(codex))

    def test_find_codex_cli_prefers_config_path_over_path_binary(self):
        with tempfile.TemporaryDirectory() as tmp:
            configured = Path(tmp) / ("codex.exe" if os.name == "nt" else "codex")
            configured.write_text("", encoding="utf-8")
            configured.chmod(0o755)
            with patch.dict(os.environ, {}, clear=True):
                with patch("app.ai_client._codex_cli_path_from_config", return_value=str(configured)):
                    with patch("app.ai_client.shutil.which", return_value="/usr/bin/codex"):
                        self.assertEqual(find_codex_cli(), str(configured))

    def test_codex_oauth_check_runs_version_status_and_smoke_without_api_keys(self):
        calls = []

        def fake_run(command, **kwargs):
            calls.append((command, kwargs))
            if command[1:] == ["--version"]:
                return SimpleNamespace(returncode=0, stdout="codex-cli 0.136.0", stderr="")
            if command[1:] == ["login", "status"]:
                return SimpleNamespace(returncode=0, stdout="Logged in using ChatGPT", stderr="")
            output_path = Path(command[command.index("-o") + 1])
            output_path.write_text(
                json.dumps(
                    {
                        "rows": [
                            {
                                "구분": "상태",
                                "번호/요소": "테스트",
                                "성취기준 후보": "",
                                "평가유형": "선택형",
                                "목표수준 후보": "C",
                                "난이도 후보": "보통",
                                "A 예상": "3/3",
                                "B 예상": "3/3",
                                "C 예상": "2/3",
                                "D 예상": "1/3",
                                "E 예상": "0/3",
                                "근거": "Codex CLI OAuth 연결 확인",
                                "다음 확인": "",
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test", "CODEX_API_KEY": "codex-test"}):
            with patch("app.ai_client.shutil.which", return_value="/opt/homebrew/bin/codex"):
                with patch("app.ai_client.subprocess.run", side_effect=fake_run):
                    result = check_codex_cli_oauth(model="gpt-5.5", timeout=60)

        self.assertEqual(result["version"], "codex-cli 0.136.0")
        self.assertEqual(result["status"], "Logged in using ChatGPT")
        self.assertEqual([call[0][1:] for call in calls[:2]], [["--version"], ["login", "status"]])
        for _, kwargs in calls:
            self.assertNotIn("OPENAI_API_KEY", kwargs["env"])
            self.assertNotIn("CODEX_API_KEY", kwargs["env"])
            self.assertEqual(kwargs["env"]["TERM"], "xterm-256color")

    def test_scrub_personal_data_removes_common_identifiers(self):
        text = "홍길동 2/14 010-1234-5678 test@example.com"
        scrubbed = scrub_personal_data(text, ["홍길동"])
        self.assertNotIn("홍길동", scrubbed)
        self.assertNotIn("010-1234-5678", scrubbed)
        self.assertNotIn("test@example.com", scrubbed)
        self.assertIn("[학생명]", scrubbed)

    def test_ollama_default_model_is_fast_product_default(self):
        self.assertEqual(default_model("ollama"), "gemma4:e4b")

    def test_get_ollama_version_uses_server_version_endpoint(self):
        with patch("app.ai_client._get_json", return_value={"version": "0.30.10"}) as get_json:
            self.assertEqual(get_ollama_version("http://127.0.0.1:11434/api/chat"), "0.30.10")
        get_json.assert_called_once_with("http://127.0.0.1:11434/api/version", {}, 5)


if __name__ == "__main__":
    unittest.main()
