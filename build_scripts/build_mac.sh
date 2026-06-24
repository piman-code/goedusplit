#!/usr/bin/env bash
# macOS app build script.
# Usage: bash build_scripts/build_mac.sh
# Result: dist/Goedu-Split.app

set -euo pipefail
cd "$(dirname "$0")/.."

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is required."
  exit 1
fi

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

# shellcheck source=/dev/null
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

python build_scripts/fetch_fonts.py || true
python build_scripts/generate_app_icon.py

rm -rf build dist
pyinstaller --noconfirm --clean goedusplit.spec

if [ -f build_scripts/repair_qtwebengine_macos.py ]; then
  python build_scripts/repair_qtwebengine_macos.py
fi

python build_scripts/privacy_release_audit.py dist/Goedu-Split.app

echo "Done: $(pwd)/dist/Goedu-Split.app"
