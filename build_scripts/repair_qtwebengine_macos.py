from __future__ import annotations

import shutil
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
        raise RuntimeError("필수 QtWebEngineCore.framework 없음")

    versions = framework / "Versions"
    misplaced = versions / "Resources"
    target_version = versions / "A"
    if not target_version.is_dir():
        raise RuntimeError("필수 QtWebEngine framework Versions/A 없음")
    if misplaced.exists():
        backup = app_path.resolve().parent.parent / "build" / "qtwebengine-resources-before-repair"
        if backup.exists():
            raise FileExistsError(f"기존 QtWebEngine 보존 위치가 있습니다: {backup}")
        backup.parent.mkdir(parents=True, exist_ok=True)
        _merge_tree(misplaced / "Resources", target_version / "Resources")
        _merge_tree(misplaced / "Helpers", target_version / "Helpers")

    process = target_version / "Helpers" / "QtWebEngineProcess.app" / "Contents" / "MacOS" / "QtWebEngineProcess"
    resources = target_version / "Resources" / "qtwebengine_resources.pak"
    if not process.exists() or not resources.exists():
        raise RuntimeError(
            "QtWebEngine 보정 실패: "
            f"process={process.exists()} resources={resources.exists()}"
        )

    if misplaced.exists():
        shutil.move(str(misplaced), str(backup))
        print("[qtwebengine] macOS QtWebEngine 리소스 위치 보정 완료")
        return True
    print("[qtwebengine] 필수 process/resources 확인: 보정 불필요")
    return False


def main() -> int:
    app_path = Path(sys.argv[1]) if len(sys.argv) > 1 else APP_PATH
    repair(app_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
