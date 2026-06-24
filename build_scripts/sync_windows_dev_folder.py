#!/usr/bin/env python3
"""Create a clean Windows development kit folder and source zip.

The output is intentionally source-only: no virtualenv, no build/dist output,
no Git history, no sample student data, and no bytecode caches. Build the .exe
on a Windows PC with build_scripts\\build_windows.bat.

Bundled font files and macOS-only helpers are also excluded from this source kit
because the Windows build script can recreate the needed fonts and icon assets.
The built Windows distribution still contains the runtime assets it needs.
"""
from __future__ import annotations

import argparse
import fnmatch
import shutil
import sys
import zipfile
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INCLUDES = [
    "app",
    "assets",
    "build_scripts",
    "distribution",
    "tests",
    "goedusplit.spec",
    "requirements.txt",
    "run.py",
    "README.md",
    ".gitignore",
]
EXCLUDE_PARTS = {
    ".git",
    ".venv",
    ".pyinstaller-cache",
    "__pycache__",
    "build",
    "dist",
    "sample_data",
    "dist.old.44551",
    "dist.old.81311",
}
EXCLUDE_NAMES = {
    ".DS_Store",
    "Thumbs.db",
    "desktop.ini",
}
EXCLUDE_PATTERNS = [
    "*.pyc",
    "*.pyo",
    "*.log",
    "*.spec.bak",
]
EXCLUDE_REL_PATHS = {
    Path("assets/fonts"),
    Path("assets/app_icon/goedusplit.icns"),
    Path("assets/app_icon/goedusplit.iconset"),
    Path("build_scripts/build_mac.sh"),
    Path("build_scripts/pack_mac.sh"),
    Path("build_scripts/repair_qtwebengine_macos.py"),
    Path("build_scripts/run_dev.sh"),
    Path("build_scripts/slim_mac_app.py"),
}


def should_skip(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    if any(rel == excluded or excluded in rel.parents for excluded in EXCLUDE_REL_PATHS):
        return True
    if any(part in EXCLUDE_PARTS for part in rel.parts):
        return True
    if path.name in EXCLUDE_NAMES:
        return True
    return any(fnmatch.fnmatch(path.name, pattern) for pattern in EXCLUDE_PATTERNS)


def copy_item(src: Path, dst: Path) -> None:
    if should_skip(src):
        return
    if src.is_dir():
        for child in src.iterdir():
            copy_item(child, dst / child.name)
        return
    if src.is_file():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def write_manifest(stage: Path, version: str) -> None:
    manifest = stage / "WINDOWS_DEV_KIT_MANIFEST.txt"
    files = sorted(
        str(path.relative_to(stage)).replace("/", "\\")
        for path in stage.rglob("*")
        if path.is_file()
    )
    manifest.write_text(
        "\n".join(
            [
                "Goedu-Split Windows development kit",
                f"version: {version}",
                f"created_at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                "",
                "contents:",
                *files,
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def zip_stage(stage: Path, zip_path: Path) -> None:
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(stage.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(stage.parent))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_root", help="Google Drive 업무 folder or another output directory")
    parser.add_argument("--version", default="")
    parser.add_argument("--name", default="")
    args = parser.parse_args(argv)

    version = args.version.strip()
    if not version:
        sys.path.insert(0, str(ROOT))
        from app import __version__  # pylint: disable=import-outside-toplevel

        version = __version__

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    folder_name = args.name.strip() or f"Goedu-Split-Windows-{version}-{stamp}"
    output_root = Path(args.output_root).expanduser()
    output_root.mkdir(parents=True, exist_ok=True)
    stage = output_root / folder_name
    if stage.exists():
        raise FileExistsError(f"output folder already exists: {stage}")
    stage.mkdir(parents=True)

    for item in INCLUDES:
        copy_item(ROOT / item, stage / item)
    write_manifest(stage, version)

    zip_path = output_root / f"{folder_name}.zip"
    zip_stage(stage, zip_path)
    print(stage)
    print(zip_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
