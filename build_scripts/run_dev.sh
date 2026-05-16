#!/usr/bin/env bash
# 빌드 없이 바로 실행해 보고 싶을 때 (개발/테스트용).
# 사용:  bash build_scripts/run_dev.sh

set -euo pipefail
cd "$(dirname "$0")/.."

if ! command -v python3 >/dev/null 2>&1; then
  echo "❌ Python 3가 필요합니다. https://www.python.org/downloads/macos/ 에서 3.11 이상 설치 후 다시 시도해 주세요."
  exit 1
fi

if [ ! -d ".venv" ]; then
  echo "[1/2] 가상환경 만드는 중…"
  python3 -m venv .venv
fi
# shellcheck source=/dev/null
source .venv/bin/activate

echo "[2/3] 의존성 설치"
pip install --upgrade pip >/dev/null
pip install -r requirements.txt

echo "[3/3] 한글 폰트 확보 후 실행"
python build_scripts/fetch_fonts.py || true
exec python run.py
