from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "dist" / "Goedu-Split.app"
FRAMEWORK = (
    APP_PATH
    / "Contents"
    / "Frameworks"
    / "PySide6"
    / "Qt"
    / "lib"
    / "QtWebEngineCore.framework"
)


def _merge_tree(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    dst.mkdir(parents=True, exist_ok=True)
    for child in src.iterdir():
        target = dst / child.name
        if child.is_dir() and not child.is_symlink():
            shutil.copytree(child, target, dirs_exist_ok=True)
        else:
            shutil.copy2(child, target)


def repair(app_path: Path = APP_PATH) -> bool:
    framework = (
        app_path
        / "Contents"
        / "Frameworks"
        / "PySide6"
        / "Qt"
        / "lib"
        / "QtWebEngineCore.framework"
    )
    if not framework.exists():
        print("[qtwebengine] QtWebEngineCore.framework 없음: 건너뜀")
        return False

    versions = framework / "Versions"
    misplaced = versions / "Resources"
    target_version = versions / "A"
    if not misplaced.exists() or not target_version.exists():
        print("[qtwebengine] 보정할 리소스 위치 없음: 건너뜀")
        return False

    _merge_tree(misplaced / "Resources", target_version / "Resources")
    _merge_tree(misplaced / "Helpers", target_version / "Helpers")

    process = target_version / "Helpers" / "QtWebEngineProcess.app" / "Contents" / "MacOS" / "QtWebEngineProcess"
    resources = target_version / "Resources" / "qtwebengine_resources.pak"
    if not process.exists() or not resources.exists():
        raise RuntimeError(
            "QtWebEngine 보정 실패: "
            f"process={process.exists()} resources={resources.exists()}"
        )

    shutil.rmtree(misplaced)
    print("[qtwebengine] macOS QtWebEngine 리소스 위치 보정 완료")
    return True


def main() -> int:
    app_path = Path(sys.argv[1]) if len(sys.argv) > 1 else APP_PATH
    changed = repair(app_path)
    if changed:
        subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(app_path)], check=True)
        print("[qtwebengine] 보정 후 ad-hoc 재서명 완료")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
