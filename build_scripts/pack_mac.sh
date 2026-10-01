#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${GOEDUSPLIT_BUILD_PYTHON:-python3}"
if [ -z "${GOEDUSPLIT_BUILD_PYTHON:-}" ] && [ -x .venv/bin/python ]; then PY=.venv/bin/python; fi
APP_PATH=dist/Goedu-Split.app
VER="$("$PY" -B -c 'from app import __version__; print(__version__)')"
DMG="dist/Goedu-Split-${VER}-mac.dmg"
if [ -e "$DMG" ]; then echo "Existing DMG preserved: $DMG" >&2; exit 1; fi
test -d "$APP_PATH"
"$PY" -B -c 'import plistlib,sys; from app import __version__; p=plistlib.load(open(sys.argv[1], "rb")); assert p.get("CFBundleShortVersionString") == p.get("CFBundleVersion") == __version__, "App bundle version differs from source"' "$APP_PATH/Contents/Info.plist"
test -s distribution/USER_GUIDE.md
"$PY" build_scripts/privacy_release_audit.py "$APP_PATH" distribution/USER_GUIDE.md
codesign --verify --deep --strict "$APP_PATH"
"$PY" -B build_scripts/build_identity.py --target macos --app "$APP_PATH"
STAGING="$(mktemp -d "${TMPDIR:-/tmp}/goedusplit-dmg.XXXXXX")"
# Retain staging for inspection/recovery; it is never an existing release folder.
ditto "$APP_PATH" "$STAGING/Goedu-Split.app"
ln -s /Applications "$STAGING/Applications"
cp distribution/USER_GUIDE.md "$STAGING/사용 안내.md"
cp dist/BUILD_SOURCE-macos.json "$STAGING/BUILD_SOURCE.json"
hdiutil create -volname Goedu-Split -srcfolder "$STAGING" -format UDZO "$DMG"
hdiutil verify "$DMG"
echo "Candidate: $(pwd)/$DMG"
echo "Staging retained: $STAGING"
