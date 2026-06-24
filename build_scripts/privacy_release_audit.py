#!/usr/bin/env python3
"""Lightweight privacy and secret audit for Goedu-Split release artifacts."""
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

BLOCKED_PATH_PARTS = {
    ".git",
    ".venv",
    "__pycache__",
    "sample_data",
}

TEXT_SUFFIXES = {
    ".cfg",
    ".conf",
    ".css",
    ".csv",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".log",
    ".md",
    ".plist",
    ".py",
    ".qss",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}


def iter_files(root: Path):
    if root.is_file():
        yield root
        return
    for path in root.rglob("*"):
        if path.is_file() and not path.is_symlink():
            yield path


def is_text_candidate(path: Path) -> bool:
    return path.suffix.lower() in TEXT_SUFFIXES or path.name in {"Info.plist"}


def audit_path(root: Path) -> list[str]:
    findings: list[str] = []
    if not root.exists():
        return [f"missing: {root}"]
    for path in iter_files(root):
        rel_parts = set(path.relative_to(root).parts)
        blocked = rel_parts & BLOCKED_PATH_PARTS
        if blocked:
            findings.append(f"blocked packaged path: {path} ({', '.join(sorted(blocked))})")
            continue
        if not is_text_candidate(path):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError as exc:
            findings.append(f"read failed: {path}: {exc}")
            continue
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                findings.append(f"secret-like token pattern: {path}")
                break
        if path.name == "privacy_release_audit.py":
            continue
        if "/Users/piman/" in text or "/private/var/folders/" in text:
            findings.append(f"local development path leaked: {path}")
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", help="Release artifact paths to audit")
    args = parser.parse_args(argv)

    all_findings: list[str] = []
    for raw in args.paths:
        all_findings.extend(audit_path(Path(raw)))
    if all_findings:
        print("Goedu-Split release privacy audit failed:", file=sys.stderr)
        for finding in all_findings:
            print(f"- {finding}", file=sys.stderr)
        return 1
    print("Goedu-Split release privacy audit passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
