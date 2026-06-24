#!/usr/bin/env python3
"""Windows source-kit release audit for Goedu-Split."""
from __future__ import annotations

import argparse
import re
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
    ".bat",
    ".css",
    ".html",
    ".js",
    ".json",
    ".md",
    ".py",
    ".spec",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}


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
        rel = path.relative_to(root)
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name != ".gitignore":
            continue
        text = _read_text(path)
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                findings.append(f"secret-like token pattern: {rel}")
                break
        if path.name in {"privacy_release_audit.py", "windows_release_audit.py"}:
            continue
        mac_user_path = "/" + "Users/piman/"
        mac_temp_path = "/" + "private/var/folders/"
        if mac_user_path in text or mac_temp_path in text:
            findings.append(f"local development path leaked: {rel}")

    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=".", help="source-kit root to audit")
    args = parser.parse_args(argv)

    root = Path(args.source).resolve()
    findings = audit_source(root)
    if findings:
        print("Goedu-Split Windows source-kit audit failed:", file=sys.stderr)
        for finding in findings:
            print(f"- {finding}", file=sys.stderr)
        return 1
    print("Goedu-Split Windows source-kit audit passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
