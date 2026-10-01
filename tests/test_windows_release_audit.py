from tests.runtime_isolation import ensure_isolated
ensure_isolated()

import contextlib
import io
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from build_scripts import windows_release_audit as audit


REPO_ROOT = Path(__file__).resolve().parents[1]
BUILD_SCRIPT = REPO_ROOT / "build_scripts" / "build_windows.bat"


class WindowsReleaseAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in audit.REQUIRED_FILES:
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("source placeholder\n", encoding="utf-8")
        (self.root / "requirements.txt").write_text("Pillow>=10\n", encoding="utf-8")
        (self.root / "app/ai_client.py").write_text("# search codex.cmd\n", encoding="utf-8")
        (self.root / "build_scripts/build_windows.bat").write_text(
            "python windows_release_audit.py --source .\nif errorlevel 1 exit /b 1\n",
            encoding="utf-8",
        )

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), *args], check=True,
                              capture_output=True)

    def repository(self):
        self.git("init", "-q")
        self.git("add", ".")

    def track(self, name, content):
        target = self.root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        self.git("add", "--", name)
        return target

    def test_repository_ignores_untracked_student_data_and_dev_directories(self):
        self.repository()
        for name in (".venv", "build", "dist", "__pycache__"):
            folder = self.root / name
            folder.mkdir()
            (folder / "untracked.txt").write_text("preserve me", encoding="utf-8")
        student = self.root / "private-student.xlsx"
        student.write_bytes(b"opaque local student data")
        real_read = audit._read_text

        def tracked_only(path):
            self.assertNotEqual(path, student, "untracked student data must not be opened")
            return real_read(path)

        with patch.object(audit, "_read_text", side_effect=tracked_only):
            self.assertEqual([], audit.audit_repository(self.root))
        self.assertEqual(b"opaque local student data", student.read_bytes())
        self.assertEqual("preserve me", (self.root / "dist/untracked.txt").read_text())
        self.assertTrue((self.root / ".git").is_dir())

    def test_tracked_student_file_is_rejected_without_opening_it(self):
        self.repository()
        self.track("학생성적.xlsx", "opaque data")
        with patch.object(audit, "_read_text", wraps=audit._read_text) as reader:
            findings = audit.audit_repository(self.root)
        self.assertTrue(any("student/input data" in finding for finding in findings))
        self.assertNotIn(self.root / "학생성적.xlsx", [call.args[0] for call in reader.call_args_list])

    def test_untracked_and_ignored_runtime_data_is_rejected_without_reading(self):
        self.repository()
        blocked = self.root / "app/spliter_ox_web/local-project.json"
        ignored = self.root / "assets/app_icon/ignored.json"
        ignored.parent.mkdir(parents=True, exist_ok=True)
        blocked.write_text('{"students":[{"name":"synthetic"}]}')
        ignored.write_text("unread local payload")
        self.track(".gitignore", "assets/app_icon/ignored.json\napp/**/__pycache__/\n")
        cache = self.root / "app/__pycache__/module.pyc"
        cache.parent.mkdir()
        cache.write_bytes(b"generated Python cache")
        real_read = audit._read_text
        def only_tracked(path):
            self.assertNotIn(path, {blocked, ignored, cache})
            return real_read(path)
        with patch.object(audit, "_read_text", side_effect=only_tracked):
            findings = audit.audit_repository(self.root)
        self.assertIn("untracked/ignored packaged source file is not allowed: app/spliter_ox_web/local-project.json", findings)
        self.assertIn("untracked/ignored packaged source file is not allowed: assets/app_icon/ignored.json", findings)
        self.assertFalse(any("module.pyc" in finding for finding in findings))

    def test_tracked_secrets_are_rejected_without_echoing_payload(self):
        self.repository()
        secret = "sk-" + "q" * 30
        self.track("config.json", '{"token":"' + secret + '"}')
        findings = audit.audit_repository(self.root)
        self.assertIn("secret-like token pattern: config.json", findings)
        self.assertNotIn(secret, "\n".join(findings))

    def test_student_json_payload_is_rejected_but_configuration_is_allowed(self):
        self.repository()
        self.track("settings.json", '{"theme":"light"}')
        self.track("portfolio.json", '{"students":[{"name":"synthetic","final_score":50}]}')
        self.track("evidence.json", '{"sourceFiles":{"response":"input.xlsx"}}')
        findings = audit.audit_repository(self.root)
        self.assertNotIn("student/input JSON payload is not allowed in source: settings.json", findings)
        self.assertIn("student/input JSON payload is not allowed in source: portfolio.json", findings)
        self.assertIn("student/input JSON payload is not allowed in source: evidence.json", findings)

    def test_dirty_tracked_content_is_audited(self):
        self.repository()
        target = self.root / "README.md"
        target.write_text("OPENAI_API_KEY=" + "x" * 20, encoding="utf-8")
        self.assertIn("secret-like token pattern: README.md", audit.audit_repository(self.root))

    def test_credentials_and_tracked_build_outputs_are_rejected(self):
        self.repository()
        self.track(".env.local", "private=opaque")
        self.track("dist/output.bin", "opaque")
        findings = audit.audit_repository(self.root)
        self.assertIn("credential file is not allowed in source: .env.local", findings)
        self.assertIn("blocked tracked source directory: dist/output.bin", findings)

    def test_personal_paths_are_rejected_on_both_platforms(self):
        self.repository()
        self.track("config.txt", "/" + "Users/teacher/Desktop/input.xlsx\n")
        self.track("setup.txt", "C:" + "\\Users\\teacher\\Documents\\input.xlsx")
        findings = audit.audit_repository(self.root)
        self.assertIn("local development path leaked: config.txt", findings)
        self.assertIn("local development path leaked: setup.txt", findings)

    def test_synthetic_path_exception_is_limited_to_existing_privacy_fixture(self):
        self.repository()
        synthetic = "/" + "Users/someone/Desktop/input.xlsx"
        self.track("tests/test_export_privacy.py", synthetic)
        self.track("tests/unrelated.py", synthetic)
        findings = audit.audit_repository(self.root)
        self.assertNotIn("local development path leaked: tests/test_export_privacy.py", findings)
        self.assertIn("local development path leaked: tests/unrelated.py", findings)

    def test_source_kit_still_rejects_git_and_venv(self):
        self.assertEqual([], audit.audit_source(self.root))
        (self.root / ".git").mkdir()
        (self.root / ".venv").mkdir()
        findings = audit.audit_source(self.root)
        self.assertIn("blocked source-kit directory included: .git", findings)
        self.assertIn("blocked source-kit directory included: .venv", findings)

    def test_source_kit_rejects_symlinks_before_reading_required_contents(self):
        with tempfile.TemporaryDirectory() as external:
            target = Path(external) / "target.py"
            target.write_text("external content", encoding="utf-8")
            required = self.root / "app/main_window.py"
            required.unlink()
            try:
                required.symlink_to(target)
                (self.root / "outside-dir").symlink_to(external, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"symlink creation unavailable: {exc}")
            with patch.object(audit, "_read_text", side_effect=AssertionError("no content read")):
                findings = audit.audit_source(self.root)
            self.assertIn("source symlink is not allowed: app/main_window.py", findings)
            self.assertIn("source symlink is not allowed: outside-dir", findings)

    def test_mock_junction_is_rejected_before_descent_or_any_content_read(self):
        junction = self.root / "assets/external-junction"
        junction.mkdir()
        (junction / "student.xlsx").write_bytes(b"synthetic external fixture")
        real_scandir = os.scandir
        def no_external_descent(path):
            self.assertNotEqual(Path(path), junction)
            self.assertNotIn(junction, Path(path).parents)
            return real_scandir(path)
        for method in (audit.audit_source, audit.audit_repository):
            with self.subTest(mode=method.__name__), \
                    patch.object(Path, "is_junction", lambda path: path == junction, create=True), \
                    patch.object(audit.os, "scandir", side_effect=no_external_descent), \
                    patch.object(audit, "_read_text", side_effect=AssertionError("no content read")), \
                    patch.object(audit.subprocess, "run", side_effect=AssertionError("no Git inventory before link rejection")):
                self.assertIn("source junction is not allowed: assets/external-junction", method(self.root))

    def test_requested_root_and_ancestor_junctions_are_not_resolved_away(self):
        for linked in (self.root, self.root.parent):
            with self.subTest(linked=linked.name), \
                    patch.object(Path, "is_junction", lambda path: path == linked, create=True), \
                    patch.object(Path, "resolve", side_effect=AssertionError("do not resolve junction")), \
                    patch.object(audit.os, "scandir", side_effect=AssertionError("do not enumerate linked root")), \
                    patch.object(audit.subprocess, "run", side_effect=AssertionError("do not run Git in linked root")):
                self.assertEqual(["source root junction is not allowed"], audit.audit_source(self.root))
                self.assertEqual(["source root junction is not allowed"], audit.audit_repository(self.root))
                with contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(1, audit.main(["--source", str(self.root), "--repository"]))

    def test_packaged_cache_named_directories_do_not_hide_nested_junctions(self):
        for location in ("assets/__pycache__/linked", "app/spliter_ox_web/__pycache__/linked"):
            junction = self.root / location
            junction.mkdir(parents=True)
            with self.subTest(location=location), \
                    patch.object(Path, "is_junction", lambda path: path == junction, create=True), \
                    patch.object(audit, "_read_text", side_effect=AssertionError("no content read")), \
                    patch.object(audit.subprocess, "run", side_effect=AssertionError("no Git inventory before link rejection")):
                self.assertIn(f"source junction is not allowed: {location}", audit.audit_repository(self.root))

    @unittest.skipUnless(os.name == "nt" and hasattr(Path, "is_junction"), "requires actual Windows junction support")
    def test_real_windows_junction_is_rejected_without_external_descent(self):
        self.repository()
        with tempfile.TemporaryDirectory() as external:
            junction = self.root / "assets/external-junction"
            result = subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), external], capture_output=True)
            if result.returncode:
                self.skipTest("Windows junction creation unavailable")
            self.assertTrue(junction.is_junction())
            real_scandir = os.scandir
            def no_external_descent(path):
                self.assertNotEqual(Path(path), junction)
                return real_scandir(path)
            with patch.object(audit.os, "scandir", side_effect=no_external_descent), \
                    patch.object(audit, "_read_text", side_effect=AssertionError("no content read")):
                self.assertIn("source junction is not allowed: assets/external-junction", audit.audit_source(self.root))
                self.assertIn("source junction is not allowed: assets/external-junction", audit.audit_repository(self.root))

    def test_repository_requires_git_and_tracked_required_files(self):
        self.assertTrue(audit.audit_repository(self.root))
        self.repository()
        self.git("rm", "--cached", "run.py")
        self.assertIn("required tracked file missing: run.py", audit.audit_repository(self.root))

    def test_repository_cli_reports_failure_and_requires_explicit_mode(self):
        self.repository()
        out = io.StringIO()
        with contextlib.redirect_stderr(out):
            self.assertEqual(1, audit.main(["--source", str(self.root)]))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(0, audit.main(["--source", str(self.root), "--repository"]))
        self.track("input.csv", "synthetic,student")
        with contextlib.redirect_stderr(out):
            self.assertEqual(1, audit.main(["--source", str(self.root), "--repository"]))
        self.assertIn("repository audit failed", out.getvalue())

    def test_symlink_is_rejected_without_reading_external_target(self):
        self.repository()
        with tempfile.TemporaryDirectory() as external:
            target = Path(external) / "target"
            target.write_text("do not read", encoding="utf-8")
            link = self.root / "linked.py"
            try:
                link.symlink_to(target)
            except OSError as exc:
                self.skipTest(f"symlink creation unavailable: {exc}")
            self.git("add", "linked.py")
            with patch.object(audit, "_read_text", wraps=audit._read_text) as reader:
                findings = audit.audit_repository(self.root)
            self.assertIn("source symlink is not allowed: linked.py", findings)
            self.assertNotIn(link, [call.args[0] for call in reader.call_args_list])


class WindowsBuildSafetyTests(unittest.TestCase):
    def test_build_has_no_automatic_environment_install_or_asset_mutation(self):
        source = BUILD_SCRIPT.read_text(encoding="utf-8").lower()
        for forbidden in ("rmdir ", "del ", "pip install", "-m venv", "activate.bat",
                          "fetch_fonts.py", "generate_app_icon.py", "--clean"):
            self.assertNotIn(forbidden, source)
        self.assertIn('.venv\\scripts\\python.exe', source)
        self.assertIn('if exist .git set "audit_mode=--repository"', source)
        self.assertLess(source.index("if exist dist"), source.index('"%build_python%" --version'))
        for command in ("windows_release_audit.py --source . %audit_mode%",
                        "build_scripts\\build_preflight.py",
                        "-m pip check", '"%build_python%" run_tests.py',
                        "node --test tests/test_expected_rate_web.cjs",
                        "-m pyinstaller --noconfirm goedusplit.spec",
                        "slim_windows_dist.py dist\\goedu-split",
                        "privacy_release_audit.py dist\\goedu-split"):
            line = next(line for line in source.splitlines() if command in line)
            self.assertIn(line + "\nif errorlevel 1 exit /b 1", source)
        self.assertIn("build_identity.py --target windows --app dist\\goedu-split --write\nif errorlevel 1 exit /b 1", source)

    @unittest.skipUnless(os.name == "nt", "requires Windows cmd.exe")
    def test_existing_build_outputs_are_preserved_and_stop_execution(self):
        for folder in ("build", "dist"):
            with self.subTest(folder=folder), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "build_scripts").mkdir()
                shutil.copyfile(BUILD_SCRIPT, root / "build_scripts/build_windows.bat")
                (root / folder).mkdir()
                marker = root / folder / "keep.txt"
                marker.write_text("saved candidate", encoding="utf-8")
                result = subprocess.run(["cmd", "/c", str(root / "build_scripts/build_windows.bat")],
                                        cwd=root, capture_output=True)
                self.assertNotEqual(0, result.returncode)
                self.assertEqual("saved candidate", marker.read_text())
                self.assertFalse((root / ".venv").exists())

    @unittest.skipUnless(os.name == "nt", "requires Windows cmd.exe")
    def test_failed_audit_stops_before_build_or_environment_mutations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scripts = root / "build_scripts"
            scripts.mkdir()
            shutil.copyfile(BUILD_SCRIPT, scripts / "build_windows.bat")
            (scripts / "windows_release_audit.py").write_text("raise SystemExit(1)\n")
            result = subprocess.run(["cmd", "/c", str(scripts / "build_windows.bat")],
                                    cwd=root, capture_output=True)
            self.assertNotEqual(0, result.returncode)
            for name in ("build", "dist", ".venv", "assets"):
                self.assertFalse((root / name).exists())


if __name__ == "__main__":
    unittest.main()
