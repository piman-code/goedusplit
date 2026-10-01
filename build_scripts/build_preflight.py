"""Validate local assets and pinned dependencies without installing or downloading."""
from __future__ import annotations

import importlib.metadata
from pathlib import Path
import sys
from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parents[1]


def check(root=ROOT):
    errors = []
    assets = ["assets/fonts/NanumGothic.ttf", "assets/fonts/NanumGothicBold.ttf",
              "assets/fonts/GowunDodum-Regular.ttf", "assets/app_icon/goedusplit.png",
              "assets/app_icon/goedusplit.icns" if sys.platform == "darwin" else "assets/app_icon/goedusplit.ico",
              "app/spliter_ox_web/index.html", "distribution/USER_GUIDE.md", "run_tests.py"]
    for name in assets:
        path = root / name
        if path.is_symlink() or not path.is_file() or not path.stat().st_size:
            errors.append(f"missing, empty, or symlink asset: {name}")
    for line in (root / "requirements-build-lock.txt").read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        requirement = Requirement(line)
        if requirement.marker and not requirement.marker.evaluate():
            continue
        try:
            version = importlib.metadata.version(requirement.name)
        except importlib.metadata.PackageNotFoundError:
            errors.append(f"missing dependency: {requirement.name}")
            continue
        if version not in requirement.specifier:
            errors.append(f"dependency mismatch: {requirement.name} {version}; expected {requirement.specifier}")
    return errors


if __name__ == "__main__":
    errors = check()
    for message in errors:
        print(message, file=sys.stderr)
    if not errors:
        print("Build preflight passed; no environment or asset changes.")
    raise SystemExit(bool(errors))
