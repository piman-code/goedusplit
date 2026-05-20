#!/usr/bin/env bash
# macOS .app 빌드 스크립트.
# 사용:  bash build_scripts/build_mac.sh
# 결과:  dist/Goedu-Split.app

set -euo pipefail
cd "$(dirname "$0")/.."

# ── 1. Python 확인 ─────────────────────────────────────────────────────
if ! command -v python3 >/dev/null 2>&1; then
  echo
  echo "❌ Python 3가 설치되어 있지 않습니다."
  echo
  echo "   설치 방법 (둘 중 하나):"
  echo "   1) https://www.python.org/downloads/macos/  에서 3.11 이상 .pkg 다운로드 → 더블클릭"
  echo "   2) 터미널에서:  brew install python@3.11"
  echo
  echo "   설치 후 이 스크립트를 다시 실행해 주세요."
  exit 1
fi

PY_VER="$(python3 -c 'import sys; print("%d.%d"%sys.version_info[:2])')"
PY_MAJOR="$(python3 -c 'import sys; print(sys.version_info[0])')"
PY_MINOR="$(python3 -c 'import sys; print(sys.version_info[1])')"
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
  echo "❌ Python $PY_VER 이 감지되었지만, 3.10 이상이 필요합니다."
  echo "   https://www.python.org/downloads/macos/  에서 3.11 이상을 설치해 주세요."
  exit 1
fi
echo "[1/6] Python $PY_VER OK"

# ── 2. 가상환경 ────────────────────────────────────────────────────────
if [ ! -d ".venv" ]; then
  echo "[2/6] 가상환경(.venv) 생성"
  python3 -m venv .venv
fi
# shellcheck source=/dev/null
source .venv/bin/activate

# ── 3. 의존성 ──────────────────────────────────────────────────────────
echo "[3/6] 의존성 설치 (몇 분 걸릴 수 있어요)"
pip install --upgrade pip >/dev/null
pip install -r requirements.txt

# ── 4. 한글 폰트 확보 ─────────────────────────────────────────────────
echo "[4/6] 한글 폰트 확보 (Gowun Dodum, NanumGothic)"
python build_scripts/fetch_fonts.py || true

# ── 5. 앱 아이콘 생성 ─────────────────────────────────────────────────
echo "[5/6] 앱 아이콘 생성"
python build_scripts/generate_app_icon.py

# ── 6. PyInstaller 빌드 ────────────────────────────────────────────────
echo "[6/6] 앱 번들 빌드"
rm -rf build dist
export PYINSTALLER_CONFIG_DIR="${PYINSTALLER_CONFIG_DIR:-$(pwd)/.pyinstaller-cache}"
mkdir -p "$PYINSTALLER_CONFIG_DIR"
pyinstaller --noconfirm --clean goedusplit.spec
python build_scripts/repair_qtwebengine_macos.py

echo
echo "✅ 완료!"
echo "   결과:   $(pwd)/dist/Goedu-Split.app"
echo "   실행:   open dist/Goedu-Split.app"
echo
echo "💡 다른 분께 전달하려면 다음 스크립트로 .dmg를 만드세요:"
echo "      bash build_scripts/pack_mac.sh"
