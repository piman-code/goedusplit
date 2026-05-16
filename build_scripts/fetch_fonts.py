"""
한글 글꼴 자동 수집 스크립트.
- NanumGothic은 PyPI 패키지 koreanize-matplotlib에 번들되어 있어 안정적으로 확보.
- GowunDodum은 Google Fonts(GitHub)에서 직접 다운로드.

사용:
    python build_scripts/fetch_fonts.py
빌드 스크립트에서 자동으로 호출되며, 이미 폰트가 있으면 건너뜁니다.
"""
from __future__ import annotations

import shutil
import sys
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
FONT_DIR = ROOT / "assets" / "fonts"
FONT_DIR.mkdir(parents=True, exist_ok=True)


def _download(url: str, dest: Path) -> bool:
    if dest.exists() and dest.stat().st_size > 1024:
        return True
    try:
        print(f"  → {dest.name} 다운로드 …")
        with urllib.request.urlopen(url, timeout=20) as r, open(dest, "wb") as f:
            shutil.copyfileobj(r, f)
        return dest.stat().st_size > 1024
    except Exception as e:
        print(f"    실패: {e}")
        if dest.exists():
            try: dest.unlink()
            except OSError: pass
        return False


def fetch_gowun_dodum() -> bool:
    target = FONT_DIR / "GowunDodum-Regular.ttf"
    if target.exists() and target.stat().st_size > 1024:
        return True
    # GitHub raw가 막혀 있는 환경을 대비해 여러 URL 시도
    candidates = [
        "https://raw.githubusercontent.com/google/fonts/main/ofl/gowundodum/GowunDodum-Regular.ttf",
        "https://github.com/google/fonts/raw/main/ofl/gowundodum/GowunDodum-Regular.ttf",
    ]
    for url in candidates:
        if _download(url, target):
            return True
    return False


def fetch_nanum_via_pip() -> bool:
    """koreanize-matplotlib을 사용해 NanumGothic 확보 (사용자 PC에 인터넷이 있을 때 자동)."""
    target = FONT_DIR / "NanumGothic.ttf"
    bold = FONT_DIR / "NanumGothicBold.ttf"
    if target.exists() and bold.exists():
        return True
    try:
        import koreanize_matplotlib  # noqa: F401
    except ImportError:
        # 빌드 환경에서 의존성 설치 후 호출되므로 보통 들어와 있다.
        try:
            import subprocess
            subprocess.check_call([sys.executable, "-m", "pip", "install",
                                   "koreanize-matplotlib", "--quiet"])
            import koreanize_matplotlib  # noqa: F401
        except Exception as e:
            print(f"  koreanize-matplotlib 설치 실패: {e}")
            return False
    src_dir = Path(koreanize_matplotlib.__file__).parent / "fonts"
    for src_name, dst_name in [
        ("NanumGothic.ttf", "NanumGothic.ttf"),
        ("NanumGothicBold.ttf", "NanumGothicBold.ttf"),
    ]:
        s = src_dir / src_name
        d = FONT_DIR / dst_name
        if s.exists() and not d.exists():
            shutil.copyfile(s, d)
    return (FONT_DIR / "NanumGothic.ttf").exists()


def main() -> int:
    print(f"[fonts] {FONT_DIR}")
    a = fetch_nanum_via_pip()
    b = fetch_gowun_dodum()
    msg = []
    msg.append(("✓" if a else "✗") + " NanumGothic")
    msg.append(("✓" if b else "✗") + " GowunDodum")
    print("[fonts] 결과: " + " | ".join(msg))
    if not a and not b:
        print("⚠ 한글 폰트 다운로드에 모두 실패했지만, 시스템에 설치된 한글 폰트로 자동 폴백됩니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
