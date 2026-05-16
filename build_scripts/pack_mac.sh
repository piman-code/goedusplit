#!/usr/bin/env bash
# 빌드된 .app을 .dmg로 패키징해 다른 분께 한 파일로 전달.
# 사용:  bash build_scripts/pack_mac.sh
# 결과:  dist/Goedu-Split-<버전>-mac.dmg

set -euo pipefail
cd "$(dirname "$0")/.."

APP_PATH="dist/Goedu-Split.app"
if [ ! -d "$APP_PATH" ]; then
  echo "❌ $APP_PATH 가 없습니다. 먼저 다음을 실행해 빌드하세요:"
  echo "   bash build_scripts/build_mac.sh"
  exit 1
fi

PY="python3"
if [ -x ".venv/bin/python" ]; then
  PY=".venv/bin/python"
fi
VER="$("$PY" -c 'from app.main_window import APP_VERSION; print(APP_VERSION)')"
DMG="dist/Goedu-Split-${VER}-mac.dmg"
TMP="dist/_dmg_staging"
rm -rf "$TMP" "$DMG"
mkdir -p "$TMP"

# .app + Applications 바로가기 + 안내문 배치
cp -R "$APP_PATH" "$TMP/"
ln -s /Applications "$TMP/Applications"
cp distribution/USER_GUIDE.md "$TMP/사용 안내.md" 2>/dev/null || true

hdiutil create -volname "Goedu-Split" \
  -srcfolder "$TMP" -ov -format UDZO "$DMG"

rm -rf "$TMP"
SIZE=$(du -h "$DMG" | cut -f1)
echo
echo "✅ 패키지 완성"
echo "   파일:   $(pwd)/$DMG  (${SIZE})"
echo
echo "📤 전달 방법: 위 .dmg 파일 하나를 카톡/메일/USB로 보내면 됩니다."
echo "   받는 분은 더블클릭 → Goedu-Split.app을 Applications 폴더로 끌어다 놓기 → 끝."
echo
echo "⚠️  처음 실행 시 Mac이 '확인되지 않은 개발자' 경고를 띄울 수 있습니다."
echo "   안내는 distribution/USER_GUIDE.md 의 'macOS 처음 실행' 섹션을 참고."
