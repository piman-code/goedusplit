from tests.runtime_isolation import ensure_isolated
ensure_isolated()

import os
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
import zipfile

from build_scripts.windows_release_audit import REQUIRED_FILES

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "build_scripts"
SOURCE_SCRIPT = SCRIPTS / "make_windows_source_zip.sh"


@unittest.skipUnless(os.name != "nt" and shutil.which("bash"), "source-kit fallback requires POSIX bash")
class SourceKitPreservationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        required = set(REQUIRED_FILES) | {
            ".gitignore", "SECURITY.md", "requirements-build-lock.txt", "run_tests.py",
            "tests/__init__.py", "tests/runtime_isolation.py", "docs/DEVELOPMENT_PLAN.md",
            "app/__init__.py", "build_scripts/make_windows_source_zip.sh",
            "build_scripts/build_identity.py", "build_scripts/read_app_version.py",
            "distribution/한글 공백 안내.txt",
        }
        for name in required:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("synthetic source\n", encoding="utf-8")
        (self.root / "app/__init__.py").write_text('__version__ = "1.0.5"\n')
        (self.root / "requirements.txt").write_text("Pillow>=10\n")
        (self.root / "app/ai_client.py").write_text("# codex.cmd\n")
        for name in ("windows_release_audit.py", "make_windows_source_zip.sh", "build_windows.bat", "build_identity.py", "read_app_version.py"):
            shutil.copyfile(SCRIPTS / name, self.root / "build_scripts" / name)
        self.git("init", "-q")
        self.commit()

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), *args], check=True,
                              capture_output=True).stdout

    def commit(self):
        self.git("add", ".")
        self.git("-c", "user.name=Synthetic QA", "-c", "user.email=synthetic@example.invalid",
                 "-c", "core.hooksPath=/dev/null", "commit", "--no-gpg-sign", "-qm", "Synthetic fixture")

    def pack(self, **environment):
        env = os.environ.copy()
        env.update(environment)
        return subprocess.run(["bash", str(self.root / "build_scripts/make_windows_source_zip.sh")],
                              cwd=self.root, env=env, capture_output=True, text=True)

    def output(self):
        return self.root / "dist/Goedu-Split-1.0.5-source.zip"

    def test_committed_allowlist_only_roundtrip_includes_new_required_files(self):
        student = self.root / "actual-local-student.xlsx"
        student.write_bytes(b"opaque synthetic student fixture")
        shared = self.root / "external-share"
        shared.mkdir()
        marker = shared / "keep.txt"
        marker.write_text("preserve external files")
        result = self.pack(GOEDU_WINDOWS_OUT_DIR=str(shared))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        with zipfile.ZipFile(self.output()) as archive:
            names = archive.namelist()
            for name in ("run_tests.py", "tests/runtime_isolation.py", "docs/DEVELOPMENT_PLAN.md",
                         "SECURITY.md", "requirements-build-lock.txt", "distribution/한글 공백 안내.txt",
                         "build_scripts/read_app_version.py"):
                self.assertIn(name, names)
            self.assertNotIn(student.name, names)
            self.assertFalse(any(name.startswith(".git/") for name in names))
            manifest = archive.read("WINDOWS_DEV_KIT_MANIFEST.txt").decode()
            self.assertIn("version: 1.0.5", manifest)
            self.assertIn(self.git("rev-parse", "HEAD").decode().strip(), manifest)
            identity = json.loads(archive.read("WINDOWS_SOURCE_IDENTITY.json"))
            self.assertEqual("1.0.5", identity["version"])
            self.assertEqual(self.git("rev-parse", "HEAD").decode().strip(), identity["source_commit"])
            self.assertEqual(set(names) - {"WINDOWS_SOURCE_IDENTITY.json"}, set(identity["file_sha256"]))
            for name, digest in identity["file_sha256"].items():
                self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(), digest)
        self.assertEqual(["keep.txt"], [p.name for p in shared.iterdir()])
        self.assertEqual(b"opaque synthetic student fixture", student.read_bytes())

    def test_existing_source_zip_is_preserved(self):
        self.output().parent.mkdir()
        self.output().write_bytes(b"previous candidate")
        result = self.pack()
        self.assertNotEqual(0, result.returncode)
        self.assertIn("Existing source ZIP preserved", result.stderr)
        self.assertEqual(b"previous candidate", self.output().read_bytes())

    def test_extracted_gitless_kit_records_and_verifies_build_identity(self):
        result = self.pack()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        extracted = self.root / "extracted"
        with zipfile.ZipFile(self.output()) as archive:
            archive.extractall(extracted)
        app = extracted / "dist/Goedu-Split"
        app.mkdir(parents=True)
        binary = app / "Goedu-Split.exe"
        binary.write_bytes(b"synthetic executable")
        helper = extracted / "build_scripts/build_identity.py"
        command = [os.sys.executable, "-B", str(helper), "--target", "windows", "--app", str(app)]
        result = subprocess.run([*command, "--write"], cwd=extracted, capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)
        marker = app / "BUILD_SOURCE.json"
        before = marker.read_bytes()
        result = subprocess.run(command, cwd=extracted, capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)
        result = subprocess.run([*command, "--write"], cwd=extracted, capture_output=True, text=True)
        self.assertNotEqual(0, result.returncode)
        self.assertEqual(before, marker.read_bytes())
        source = extracted / "app/main_window.py"
        source_before = source.read_bytes()
        source.write_text("# changed synthetic source\n")
        result = subprocess.run(command, cwd=extracted, capture_output=True, text=True)
        self.assertNotEqual(0, result.returncode)
        self.assertIn("source changed", result.stderr)
        source.write_bytes(source_before)
        binary.write_bytes(b"changed synthetic executable")
        result = subprocess.run(command, cwd=extracted, capture_output=True, text=True)
        self.assertNotEqual(0, result.returncode)
        self.assertIn("Executable changed", result.stderr)

    def test_dirty_staged_and_untracked_code_fail_instead_of_omitting_changes(self):
        for state in ("dirty", "staged", "untracked"):
            with self.subTest(state=state):
                if state == "untracked":
                    target = self.root / "app/new_module.py"
                    target.write_text("# new code\n")
                else:
                    target = self.root / "app/main_window.py"
                    target.write_text(f"# {state} code\n")
                    if state == "staged":
                        self.git("add", "app/main_window.py")
                result = self.pack()
                self.assertNotEqual(0, result.returncode)
                self.assertFalse(self.output().exists())
                if state == "untracked":
                    target.unlink()
                else:
                    self.git("restore", "--staged", "--worktree", "app/main_window.py")

    def test_required_uncommitted_lock_fails_with_specific_missing_message(self):
        self.git("rm", "requirements-build-lock.txt")
        self.commit()
        (self.root / "requirements-build-lock.txt").write_text("not committed\n")
        result = self.pack()
        self.assertNotEqual(0, result.returncode)
        self.assertIn("Required committed files missing", result.stderr)
        self.assertIn("requirements-build-lock.txt", result.stderr)
        self.assertFalse(self.output().exists())

    def test_tracked_student_filename_is_rejected_before_git_blob_read(self):
        target = self.root / "assets/student.xlsx"
        target.write_bytes(b"opaque synthetic input")
        self.commit()
        result = self.pack()
        self.assertNotEqual(0, result.returncode)
        self.assertIn("Student/input or credential file", result.stderr)
        self.assertFalse(self.output().exists())

    def test_committed_symlink_rejected_without_reading_external_content(self):
        with tempfile.TemporaryDirectory() as external:
            target = Path(external) / "unread.txt"
            target.write_text("opaque external fixture")
            (self.root / "assets/symlink.txt").symlink_to(target)
            self.commit()
            result = self.pack()
            self.assertNotEqual(0, result.returncode)
            self.assertIn("Symlink/submodule is not allowed", result.stderr)
            self.assertFalse(self.output().exists())


class PackagingVersionTests(unittest.TestCase):
    def test_helper_prints_only_canonical_version_using_stdlib_without_ui(self):
        with tempfile.TemporaryDirectory(prefix="version path with spaces ") as tmp:
            root = Path(tmp)
            (root / "build_scripts").mkdir()
            (root / "app").mkdir()
            helper = root / "build_scripts/read_app_version.py"
            shutil.copyfile(SCRIPTS / helper.name, helper)
            for value in ("1.0.5", "0.0.0", "12.34.56", "1.0.5-rc1", "01.0.5", "1.0", None):
                with self.subTest(value=value):
                    (root / "app/__init__.py").write_text(
                        f"__version__ = {value!r}\n", encoding="utf-8")
                    result = subprocess.run([os.sys.executable, "-B", "-S", str(helper)],
                                            cwd=root, capture_output=True)
                    if value in ("1.0.5", "0.0.0", "12.34.56"):
                        self.assertEqual(0, result.returncode, result.stderr)
                        self.assertEqual((value + os.linesep).encode(), result.stdout)
                        self.assertEqual(b"", result.stderr)
                    else:
                        self.assertNotEqual(0, result.returncode)
                        self.assertEqual(b"", result.stdout)
                        self.assertIn(b"Invalid app version", result.stderr)


class WindowsPackagingSafetyTests(unittest.TestCase):
    def test_version_and_guide_python_commands_are_valid_and_preserve_existing_guide(self):
        for name in ("pack_windows.bat", "pack_windows_installer.bat"):
            with self.subTest(name=name):
                source = (SCRIPTS / name).read_text(encoding="utf-8")
                commands = re.findall(r'-c "([^"\n]+)"', source)
                self.assertEqual(2, len(commands))
                for command in commands:
                    compile(command, name, "exec")
                self.assertNotIn("app.main_window", source)
                self.assertIn('"%PACK_PYTHON%" build_scripts\\read_app_version.py', source)
                self.assertNotIn('-c "from app import __version__', source)
                for helper in re.findall(r'build_scripts\\([\w-]+\.py)', source):
                    self.assertTrue((SCRIPTS / helper).is_file(), f"missing helper: {helper}")
                self.assertIn("if not defined VER", source)
                for forbidden in ("copy /y", "del ", "rmdir ", "-Force", "pip install"):
                    self.assertNotIn(forbidden, source)
                self.assertIn("if errorlevel 1 exit /b 1", source)
                self.assertIn("build_identity.py --target windows --app dist\\Goedu-Split\nif errorlevel 1 exit /b 1", source)
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    (root / "distribution").mkdir()
                    (root / "dist/Goedu-Split").mkdir(parents=True)
                    (root / "distribution/USER_GUIDE.md").write_bytes(b"new guide")
                    guide = root / "dist/Goedu-Split/사용 안내.md"
                    guide.write_bytes(b"previous guide")
                    result = subprocess.run([os.sys.executable, "-c", commands[-1]], cwd=root,
                                            capture_output=True)
                    self.assertNotEqual(0, result.returncode)
                    self.assertEqual(b"previous guide", guide.read_bytes())
                    guide.unlink()
                    result = subprocess.run([os.sys.executable, "-c", commands[-1]], cwd=root,
                                            capture_output=True)
                    self.assertEqual(0, result.returncode, result.stderr)
                    self.assertEqual(b"new guide", guide.read_bytes())

    @unittest.skipUnless(os.name == "nt", "requires Windows cmd.exe")
    def test_existing_windows_zip_and_setup_are_preserved(self):
        for script, output in (("pack_windows.bat", "Goedu-Split-1.0.5-windows.zip"),
                               ("pack_windows_installer.bat", "Goedu-Split-1.0.5-windows-setup.exe")):
            with self.subTest(script=script), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "build_scripts").mkdir()
                (root / "app").mkdir()
                (root / "app/__init__.py").write_text('__version__ = "1.0.5"\n')
                (root / "dist/Goedu-Split").mkdir(parents=True)
                (root / "dist/Goedu-Split/Goedu-Split.exe").write_bytes(b"synthetic executable")
                existing = root / "dist" / output
                existing.write_bytes(b"old candidate")
                shutil.copyfile(SCRIPTS / script, root / "build_scripts" / script)
                shutil.copyfile(SCRIPTS / "read_app_version.py", root / "build_scripts/read_app_version.py")
                (root / "build_scripts/privacy_release_audit.py").write_text("raise SystemExit(0)\n")
                (root / "build_scripts/build_identity.py").write_text(
                    "from pathlib import Path\nPath('identity-reached').write_bytes(b'checked')\n", encoding="utf-8")
                result = subprocess.run(["cmd", "/c", str(root / "build_scripts" / script)],
                                        cwd=root, capture_output=True)
                self.assertNotEqual(0, result.returncode)
                self.assertEqual(b"checked", (root / "identity-reached").read_bytes())
                self.assertIn(output.encode(), result.stdout)
                self.assertEqual(b"old candidate", existing.read_bytes())

    @unittest.skipUnless(os.name == "nt", "requires Windows cmd.exe")
    def test_version_lookup_with_spaced_python_path_reaches_identity_guard(self):
        for script in ("pack_windows.bat", "pack_windows_installer.bat"):
            with self.subTest(script=script), tempfile.TemporaryDirectory(prefix="pack path with spaces ") as tmp:
                root = Path(tmp)
                (root / "build_scripts").mkdir()
                (root / "app").mkdir()
                (root / "app/__init__.py").write_text('__version__ = "1.0.5"\n', encoding="utf-8")
                shutil.copyfile(SCRIPTS / script, root / "build_scripts" / script)
                shutil.copyfile(SCRIPTS / "read_app_version.py", root / "build_scripts/read_app_version.py")
                (root / "build_scripts/build_identity.py").write_text(
                    "from pathlib import Path\nimport sys\n"
                    "Path('identity-reached').write_bytes(b'checked')\n"
                    "print('PACK_IDENTITY_GUARD_REACHED', file=sys.stderr)\nraise SystemExit(42)\n", encoding="utf-8")
                # A temporary interpreter copy and pyvenv.cfg exercise the existing
                # .venv path choice; no packages or installed environments change.
                scripts = root / ".venv/Scripts"
                scripts.mkdir(parents=True)
                shutil.copyfile(os.sys.executable, scripts / "python.exe")
                (root / ".venv/pyvenv.cfg").write_text(
                    f"home = {os.sys.base_prefix}\ninclude-system-site-packages = true\n", encoding="utf-8")
                environment = {**os.environ, "PATH": os.sys.base_prefix + os.pathsep + os.environ["PATH"]}
                result = subprocess.run(["cmd", "/c", str(root / "build_scripts" / script)],
                                        cwd=root, env=environment, capture_output=True)
                self.assertEqual(1, result.returncode, result.stdout + result.stderr)
                self.assertIn(b"PACK_IDENTITY_GUARD_REACHED", result.stderr)
                self.assertEqual(b"checked", (root / "identity-reached").read_bytes())
                self.assertFalse((root / "dist").exists())
                for value, keep_helper in (("1.0.5-rc1", True), ("1.0.5", False)):
                    (root / "identity-reached").unlink(missing_ok=True)
                    (root / "app/__init__.py").write_text(f"__version__ = {value!r}\n", encoding="utf-8")
                    if not keep_helper:
                        (root / "build_scripts/read_app_version.py").unlink()
                    result = subprocess.run(["cmd", "/c", str(root / "build_scripts" / script)],
                                            cwd=root, env=environment, capture_output=True)
                    self.assertEqual(1, result.returncode, result.stdout + result.stderr)
                    self.assertIn(b"Invalid app version" if keep_helper else b"read_app_version.py", result.stderr)
                    self.assertNotIn(b"PACK_IDENTITY_GUARD_REACHED", result.stderr)
                    self.assertFalse((root / "identity-reached").exists())
                    self.assertFalse((root / "dist").exists())


if __name__ == "__main__":
    unittest.main()
