#!/usr/bin/env python3
"""Conservative Windows dist slimming for Goedu-Split.

This removes low-risk build leftovers and documentation/sample payloads from a
PyInstaller onedir build. It intentionally keeps QtWebEngine, Qt QML, plugins,
fonts, and application resources because those are runtime-sensitive.
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path


LOW_RISK_DIR_NAMES = {
    "__pycache__",
    "sample_data",
    "tests",
    "test",
    "doc",
    "docs",
    "examples",
}

LOW_RISK_FILE_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".log",
}

LOW_RISK_RELATIVE_PARTS = {
    ("matplotlib", "mpl-data", "sample_data"),
    ("PySide6", "Qt", "translations"),
}


def size_of(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    return sum(child.stat().st_size for child in path.rglob("*") if child.is_file())


def should_remove_dir(path: Path, root: Path) -> bool:
    if path.name in LOW_RISK_DIR_NAMES:
        return True
    rel = path.relative_to(root).parts
    return any(tuple(rel[-len(parts):]) == parts for parts in LOW_RISK_RELATIVE_PARTS)


def should_remove_file(path: Path) -> bool:
    if path.suffix.lower() in LOW_RISK_FILE_SUFFIXES:
        return True
    if path.name in {".DS_Store", "Thumbs.db", "desktop.ini"}:
        return True
    return False


def slim(root: Path) -> tuple[int, list[str]]:
    before = size_of(root)
    removed: list[str] = []
    if not root.exists():
        raise FileNotFoundError(root)

    for path in sorted(root.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        if not path.exists():
            continue
        if path.is_dir() and should_remove_dir(path, root):
            removed.append(str(path.relative_to(root)))
            shutil.rmtree(path, ignore_errors=True)
        elif path.is_file() and should_remove_file(path):
            removed.append(str(path.relative_to(root)))
            path.unlink(missing_ok=True)

    after = size_of(root)
    return max(0, before - after), removed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dist_dir", nargs="?", default="dist/Goedu-Split")
    parser.add_argument("--report", default="dist/slim-windows-report.txt")
    args = parser.parse_args(argv)

    dist_dir = Path(args.dist_dir)
    saved, removed = slim(dist_dir)
    report = Path(args.report)
    report.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "Goedu-Split Windows slim report",
        f"target: {dist_dir}",
        f"saved_bytes: {saved}",
        f"saved_mb: {saved / (1024 * 1024):.1f}",
        "",
        "removed:",
        *[f"- {item}" for item in removed],
    ]
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[slim] saved {saved / (1024 * 1024):.1f}MB; report: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
