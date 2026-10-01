#!/usr/bin/env bash
# Build only in a fresh checkout/candidate directory with preinstalled dependencies.
set -euo pipefail
cd "$(dirname "$0")/.."
if [ -e build ] || [ -e dist ]; then
  echo "Existing build or dist preserved. Use a fresh checkout/candidate directory." >&2
  exit 1
fi
if [ -n "${GOEDUSPLIT_BUILD_PYTHON:-}" ]; then
  PY="$GOEDUSPLIT_BUILD_PYTHON"
elif [ -x .venv/bin/python ]; then
  PY="$(pwd)/.venv/bin/python"
else
  PY=python3
fi
"$PY" build_scripts/build_preflight.py
"$PY" -m pip check
if [ -e .git ]; then
  "$PY" build_scripts/windows_release_audit.py --source . --repository
else
  "$PY" build_scripts/windows_release_audit.py --source .
fi
"$PY" -B run_tests.py
node --test tests/test_expected_rate_web.cjs
"$PY" -m PyInstaller --noconfirm goedusplit.spec
"$PY" build_scripts/repair_qtwebengine_macos.py dist/Goedu-Split.app
"$PY" build_scripts/privacy_release_audit.py dist/Goedu-Split.app
test -x dist/Goedu-Split.app/Contents/MacOS/Goedu-Split
codesign --force --deep --sign - dist/Goedu-Split.app
codesign --verify --deep --strict dist/Goedu-Split.app
"$PY" -B build_scripts/build_identity.py --target macos --app dist/Goedu-Split.app --write
echo "Built candidate: $(pwd)/dist/Goedu-Split.app (ad-hoc signed)"
