import unittest
from pathlib import Path


class AISettingsPolicyTests(unittest.TestCase):
    def test_product_ui_does_not_offer_openai_api_key_provider(self):
        source = Path("app/main_window.py").read_text(encoding="utf-8")
        self.assertNotIn('addItem("OpenAI 클라우드 API (API Key)"', source)
        self.assertNotIn('form.addRow("API 키"', source)
        self.assertIn('addItem("Codex CLI 클라우드 (OAuth)", "codex_cli")', source)
        self.assertIn('addItem("Ollama 로컬", "ollama")', source)

    def test_ai_connection_help_is_in_product_ui(self):
        source = Path("app/main_window.py").read_text(encoding="utf-8")
        self.assertIn("AI 연결 안내", source)
        self.assertIn("ai/connection_help_seen_v3", source)
        self.assertIn("MLX engine 최적화를 내부적으로 사용할 수 있습니다", source)
        self.assertIn("Goedu-Split에서 MLX를 따로 설정하지 않습니다", source)
        self.assertIn("Codex CLI 클라우드 (OAuth)", source)
        self.assertIn("winget install OpenJS.NodeJS.LTS", source)
        self.assertIn("npm install -g @openai/codex", source)
        self.assertIn("/opt/homebrew/bin/codex", source)

    def test_mac_build_runs_privacy_release_audit(self):
        if not Path("build_scripts/build_mac.sh").exists():
            self.skipTest("Windows source kit does not include build_mac.sh")
        script = Path("build_scripts/build_mac.sh").read_text(encoding="utf-8")
        self.assertIn("build_scripts/privacy_release_audit.py dist/Goedu-Split.app", script)

    def test_windows_build_runs_source_and_privacy_audits(self):
        script = Path("build_scripts/build_windows.bat").read_text(encoding="utf-8")
        self.assertIn("build_scripts\\windows_release_audit.py --source .", script)
        self.assertIn("build_scripts\\privacy_release_audit.py dist\\Goedu-Split", script)
        self.assertIn("if errorlevel 1 exit /b 1", script)


if __name__ == "__main__":
    unittest.main()
