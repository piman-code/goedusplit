#!/usr/bin/env bash
# GitHub 복제본을 쓸 수 없을 때의 소스 키트 fallback.
# clean Git 커밋의 허용된 추적 파일만 포함하며 기존 ZIP을 덮어쓰지 않는다.
# 자동 설치/외부 공유 폴더 복사 없음.
set -euo pipefail
cd "$(dirname "$0")/.."
PY="python3"
if [ -x ".venv/bin/python" ]; then PY=".venv/bin/python"; fi
"$PY" - <<'PY'
import ast
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import zipfile

root = Path.cwd()

def git(*args):
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True).stdout

def stop(message):
    raise SystemExit("[X] " + message)

try:
    if Path(git("rev-parse", "--show-toplevel").decode().strip()).resolve() != root:
        stop("Run from the Git worktree root.")
    head = git("rev-parse", "HEAD").decode().strip()
    entries = {}
    for entry in git("ls-tree", "-rz", "--full-tree", head).split(b"\0"):
        if not entry:
            continue
        meta, raw_name = entry.split(b"\t", 1)
        mode, kind, oid = meta.decode().split()
        name = raw_name.decode("utf-8")
        entries[name] = (mode, kind, oid)
except (OSError, subprocess.CalledProcessError, UnicodeError):
    stop("A committed Git repository is required; no version fallback.")

folders = {"app", "assets", "build_scripts", "distribution", "tests", "docs"}
files = {".gitignore", "README.md", "SECURITY.md", "requirements.txt",
         "requirements-build-lock.txt", "run.py", "run_tests.py", "goedusplit.spec"}
selected = {name: meta for name, meta in entries.items()
            if name in files or Path(name).parts[0] in folders}
required = files | {"app/__init__.py", "tests/runtime_isolation.py", "tests/__init__.py",
                    "docs/DEVELOPMENT_PLAN.md", "build_scripts/windows_release_audit.py",
                    "build_scripts/build_identity.py"}
missing = sorted(required - selected.keys())
if missing:
    stop("Required committed files missing (untracked/staged code is not included): " + ", ".join(missing))

blocked_parts = {".git", ".venv", "__pycache__", "build", "dist", "sample_data"}
blocked_suffixes = {".xlsx", ".xls", ".xlsm", ".ods", ".csv", ".tsv", ".hwp", ".hwpx",
                    ".pdf", ".doc", ".docx", ".zip", ".db", ".sqlite", ".sqlite3", ".pem", ".key", ".p12", ".pfx"}
for name, (mode, kind, _) in selected.items():
    path = Path(name)
    if mode not in {"100644", "100755"} or kind != "blob":
        stop("Symlink/submodule is not allowed in source kit: " + name)
    if path.is_absolute() or ".." in path.parts or set(path.parts) & blocked_parts:
        stop("Blocked tracked source path: " + name)
    if path.suffix.lower() in blocked_suffixes or path.name.lower().startswith(".env"):
        stop("Student/input or credential file must not enter source kit: " + name)

# Name-only untracked inventory; no local student input is opened.
for raw_name in git("ls-files", "--others", "--exclude-standard", "-z").split(b"\0"):
    if not raw_name:
        continue
    name = raw_name.decode("utf-8")
    path = Path(name)
    if (name in files or path.parts[0] in folders) and path.suffix.lower() not in blocked_suffixes:
        stop("Untracked source file must be committed before source-kit creation: " + name)
try:
    git("diff", "--quiet", head, "--", *selected.keys())
except subprocess.CalledProcessError:
    stop("Source-kit requires clean committed source; staged/dirty code cannot be omitted.")

version_blob = git("cat-file", "blob", selected["app/__init__.py"][2]).decode("utf-8")
version = None
for node in ast.parse(version_blob).body:
    if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__version__" for t in node.targets):
        version = ast.literal_eval(node.value)
if not isinstance(version, str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
    stop("A valid app.__version__ is required.")
output = root / "dist" / f"Goedu-Split-{version}-source.zip"
if output.exists() or output.is_symlink():
    stop("Existing source ZIP preserved: " + output.name)

with tempfile.TemporaryDirectory(prefix="goedusplit-source-kit-") as scratch:
    stage = Path(scratch)
    for name, (_, _, oid) in selected.items():
        target = stage / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(git("cat-file", "blob", oid))
    manifest = stage / "WINDOWS_DEV_KIT_MANIFEST.txt"
    manifest.write_text(f"Goedu-Split Windows development kit\nversion: {version}\ncommit: {head}\n\ncontents:\n"
                        + "\n".join(sorted(selected)) + "\n", encoding="utf-8")
    source_names = [*sorted(selected), "WINDOWS_DEV_KIT_MANIFEST.txt"]
    source_identity = {"version": version, "source_commit": head,
                       "file_sha256": {name: hashlib.sha256((stage / name).read_bytes()).hexdigest()
                                       for name in source_names}}
    (stage / "WINDOWS_SOURCE_IDENTITY.json").write_text(
        json.dumps(source_identity, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    subprocess.run([sys.executable, str(stage / "build_scripts/windows_release_audit.py"),
                    "--source", str(stage)], check=True)
    output.parent.mkdir(exist_ok=True)
    # Exclusive creation prevents replacing a candidate, including concurrent writers.
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in [*source_names, "WINDOWS_SOURCE_IDENTITY.json"]:
            archive.write(stage / name, name)
print(f"[OK] {output.name} (commit {head})")
print("Use a GitHub clone when available. No external-folder copy was performed.")
PY
