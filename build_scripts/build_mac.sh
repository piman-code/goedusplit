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

PY="$(pwd)/.venv/bin/python"

"$PY" -m pip install -r requirements.txt

"$PY" build_scripts/fetch_fonts.py
"$PY" build_scripts/generate_app_icon.py

if [ -e dist/Goedu-Split.app ] || [ -e dist/Goedu-Split ]; then
  echo "Existing build found in dist. Move it to a backup location before building."
  exit 1
fi
"$PY" -m unittest discover -s tests -v
node --test tests/test_expected_rate_web.cjs
"$PY" -m PyInstaller --noconfirm --clean goedusplit.spec

if [ -f build_scripts/repair_qtwebengine_macos.py ]; then
  "$PY" build_scripts/repair_qtwebengine_macos.py
fi

"$PY" build_scripts/privacy_release_audit.py dist/Goedu-Split.app
codesign --force --deep --sign - dist/Goedu-Split.app
codesign --verify --deep --strict dist/Goedu-Split.app

echo "Done: $(pwd)/dist/Goedu-Split.app"
