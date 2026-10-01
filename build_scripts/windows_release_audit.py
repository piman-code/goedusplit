#!/usr/bin/env python3
"""Audit a Windows source kit or the tracked files of a Git working tree."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"sk-proj-[A-Za-z0-9_-]{20,}"),
    re.compile(r"CODEX_API_KEY\s*=\s*[A-Za-z0-9_-]{12,}"),
    re.compile(r"OPENAI_API_KEY\s*=\s*[A-Za-z0-9_-]{12,}"),
]

REQUIRED_FILES = [
    "README.md",
    "WINDOWS_DEV_KIT_MANIFEST.txt",
    "requirements.txt",
    "run.py",
    "goedusplit.spec",
    "app/main_window.py",
    "app/ai_client.py",
    "app/spliter_ox_web/index.html",
    "assets/app_icon/goedusplit.ico",
    "assets/app_icon/goedusplit.png",
    "build_scripts/build_windows.bat",
    "build_scripts/pack_windows.bat",
    "build_scripts/pack_windows_installer.bat",
    "build_scripts/privacy_release_audit.py",
    "build_scripts/windows_release_audit.py",
    "distribution/Goedu-Split_Windows_설치_실행_안내.txt",
    "distribution/Windows_빌드_안내.txt",
]

BLOCKED_DIR_NAMES = {
    ".git",
    ".venv",
    "__pycache__",
    "build",
    "dist",
}

TEXT_SUFFIXES = {
    ".cfg",
    ".conf",
    ".csv",
    ".bat",
    ".css",
    ".html",
    ".js",
    ".json",
    ".ini",
    ".log",
    ".md",
    ".py",
    ".spec",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}

# Source distributions have no reason to contain teacher/student input files.
DATA_SUFFIXES = {".xlsx", ".xls", ".xlsm", ".ods", ".csv", ".tsv", ".hwp", ".hwpx", ".pdf", ".doc", ".docx", ".zip", ".db", ".sqlite", ".sqlite3"}
SECRET_SUFFIXES = {".pem", ".key", ".p12", ".pfx"}
USER_PATH_PATTERN = re.compile(r"(?:/Users/|[A-Za-z]:[\\/]+Users[\\/]+)([^\\/\s\"']+)")


def _audit_file(root: Path, path: Path) -> list[str]:
    rel = path.relative_to(root)
    findings: list[str] = []
    if path.is_symlink():
        return [f"source symlink is not allowed: {rel}"]
    if path.suffix.lower() in DATA_SUFFIXES:
        return [f"student/input data file is not allowed in source: {rel}"]
    if path.name.lower().startswith(".env") or path.suffix.lower() in SECRET_SUFFIXES:
        return [f"credential file is not allowed in source: {rel}"]
    if path.suffix.lower() not in TEXT_SUFFIXES and path.name != ".gitignore":
        return findings
    try:
        text = _read_text(path)
    except OSError:
        return [f"source file cannot be read: {rel}"]
    if any(pattern.search(text) for pattern in SECRET_PATTERNS):
        findings.append(f"secret-like token pattern: {rel}")
    if path.suffix.lower() == ".json":
        try:
            payload = json.loads(text)
        except (ValueError, RecursionError):
            payload = None
        if isinstance(payload, dict) and any(payload.get(key) for key in
                ("students", "sourceFiles", "source_files", "studentRecords")):
            findings.append(f"student/input JSON payload is not allowed in source: {rel}")
    # Audit scripts themselves contain detection literals, never application data.
    if path.name in {"privacy_release_audit.py", "windows_release_audit.py"}:
        return findings
    for match in USER_PATH_PATTERN.finditer(text):
        username = match.group(1)
        if username.startswith("<"):
            continue
        # These existing privacy tests intentionally use fictional source paths.
        if rel.as_posix() == "tests/test_export_privacy.py" and username in {"someone", "t"}:
            continue
        findings.append(f"local development path leaked: {rel}")
        break
    if "/" + "private/var/folders/" in text:
        findings.append(f"local development path leaked: {rel}")
    return findings


def audit_repository(root: Path) -> list[str]:
    """Inspect only Git-tracked working files; never walk local student inputs."""
    try:
        top = subprocess.run(["git", "-C", str(root), "rev-parse", "--show-toplevel"],
                             capture_output=True, check=True).stdout.decode().strip()
        if Path(top).resolve() != root.resolve():
            return ["repository audit must run at the Git worktree root"]
        result = subprocess.run(["git", "-C", str(root), "ls-files", "-z"],
                                capture_output=True, check=True)
        local_names = b""
        for options in (("--others", "--exclude-standard"),
                        ("--others", "--ignored", "--exclude-standard")):
            local_names += subprocess.run(["git", "-C", str(root), "ls-files", *options, "-z"],
                                          capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError, UnicodeError):
        return ["cannot list Git-tracked files; repository audit failed"]
    names = [name.decode("utf-8", errors="surrogateescape") for name in result.stdout.split(b"\0") if name]
    findings = [f"required tracked file missing: {rel}" for rel in REQUIRED_FILES
                if rel != "WINDOWS_DEV_KIT_MANIFEST.txt" and rel not in names]
    # PyInstaller's datas directories include local files regardless of Git status.
    # Only inventory their names; refuse them before opening any local payload.
    for raw_name in set(local_names.split(b"\0")) - {b""}:
        rel = Path(raw_name.decode("utf-8", errors="surrogateescape"))
        if rel.parts[0] not in {"app", "assets"}:
            continue
        python_cache = (rel.parts[0] == "app" and "spliter_ox_web" not in rel.parts
                        and "__pycache__" in rel.parts and rel.suffix == ".pyc")
        if not python_cache:
            findings.append(f"untracked/ignored packaged source file is not allowed: {rel}")
    for name in names:
        rel = Path(name)
        path = root / rel
        if rel.is_absolute() or ".." in rel.parts:
            findings.append("unsafe tracked file path")
        elif set(rel.parts) & BLOCKED_DIR_NAMES:
            findings.append(f"blocked tracked source directory: {rel}")
        elif not path.exists():
            findings.append(f"tracked file missing from working tree: {rel}")
        elif any(parent.is_symlink() for parent in [path, *path.parents] if parent != root and root in parent.parents):
            findings.append(f"source symlink is not allowed: {rel}")
        elif not path.is_file():
            findings.append(f"tracked submodule/directory must not be packaged implicitly: {rel}")
        else:
            findings.extend(_audit_file(root, path))
    return findings


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _iter_files(root: Path):
    for path in root.rglob("*"):
        if path.is_file() and not path.is_symlink():
            yield path


def audit_source(root: Path) -> list[str]:
    findings: list[str] = []
    if not root.exists():
        return [f"source path does not exist: {root}"]

    # Check metadata before reading any required file or traversing content.
    for path in root.rglob("*"):
        if path.is_symlink():
            findings.append(f"source symlink is not allowed: {path.relative_to(root)}")
    if findings:
        return findings

    for rel in REQUIRED_FILES:
        if not (root / rel).exists():
            findings.append(f"required file missing: {rel}")

    for path in root.rglob("*"):
        if path.is_dir() and path.name in BLOCKED_DIR_NAMES:
            findings.append(f"blocked source-kit directory included: {path.relative_to(root)}")

    requirements = root / "requirements.txt"
    if requirements.exists():
        req_text = _read_text(requirements).lower()
        if "pillow" not in req_text:
            findings.append("requirements.txt must include Pillow because generate_app_icon.py imports PIL")

    ai_client = root / "app" / "ai_client.py"
    if ai_client.exists():
        text = _read_text(ai_client)
        if 'Path("/private/tmp' in text or "Path('/private/tmp" in text:
            findings.append("app/ai_client.py contains a macOS-only /private/tmp Codex workdir")
        if "codex.cmd" not in text:
            findings.append("app/ai_client.py should search for codex.cmd on Windows")

    build_script = root / "build_scripts" / "build_windows.bat"
    if build_script.exists():
        text = _read_text(build_script)
        if "windows_release_audit.py --source ." not in text:
            findings.append("build_windows.bat must run windows_release_audit.py before building")
        if "if errorlevel 1 exit /b 1" not in text:
            findings.append("build_windows.bat must stop after failed critical commands")

    for path in _iter_files(root):
        findings.extend(_audit_file(root, path))

    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=".", help="source-kit root to audit")
    parser.add_argument("--repository", action="store_true", help="audit only Git-tracked working files instead of a source kit")
    args = parser.parse_args(argv)

    root = Path(args.source).resolve()
    findings = audit_repository(root) if args.repository else audit_source(root)
    label = "repository" if args.repository else "source-kit"
    if findings:
        print(f"Goedu-Split Windows {label} audit failed:", file=sys.stderr)
        for finding in findings:
            print(f"- {finding}", file=sys.stderr)
        return 1
    print(f"Goedu-Split Windows {label} audit passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
