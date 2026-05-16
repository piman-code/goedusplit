#!/usr/bin/env bash
# Windows에서 .exe로 빌드할 수 있도록 소스 코드를 zip으로 묶고
# Google Drive 폴더(서해고/자료)로 자동 복사한다.
#
# 사용:  bash build_scripts/make_windows_source_zip.sh
#
# 결과:
#   1) dist/Goedu-Split-<버전>-source.zip 생성
#   2) /Users/piman/Library/CloudStorage/GoogleDrive-ljs7555@gmail.com/다른 컴퓨터/서해고/자료/ 에 복사
#      (드라이브 폴더가 없으면 생성)

set -euo pipefail
cd "$(dirname "$0")/.."

PY="python3"
if [ -x ".venv/bin/python" ]; then
  PY=".venv/bin/python"
fi
VER="$("$PY" -c 'from app.main_window import APP_VERSION; print(APP_VERSION)' 2>/dev/null || echo "1.0.1")"
ZIP_NAME="Goedu-Split-${VER}-source.zip"
OUT_DIR="dist"
mkdir -p "$OUT_DIR"
ZIP_PATH="$OUT_DIR/$ZIP_NAME"
rm -f "$ZIP_PATH"

GDRIVE_DIR="/Users/piman/Library/CloudStorage/GoogleDrive-ljs7555@gmail.com/다른 컴퓨터/서해고/자료"

# zip 에 포함할 항목 — 빌드에 필요한 모든 것 (단, sample_data 는 개인정보 보호 차원에서 제외)
INCLUDES=(
  "app"
  "assets"
  "build_scripts"
  "distribution"
  "goedusplit.spec"
  "requirements.txt"
  "run.py"
  "README.md"
  ".gitignore"
)
EXCLUDES=(
  "*/__pycache__/*" "*/.venv/*" "*/dist/*" "*/build/*"
  "*.pyc" ".DS_Store"
  "sample_data/*"     # 개인정보 보호
  "out_test/*" "ppt_extract/*" "ppt_images/*"
)

EXCLUDE_ARGS=()
for p in "${EXCLUDES[@]}"; do
  EXCLUDE_ARGS+=( -x "$p" )
done

echo "[1/3] zip 생성: $ZIP_PATH"
zip -r -q "$ZIP_PATH" "${INCLUDES[@]}" "${EXCLUDE_ARGS[@]}"
SIZE=$(du -h "$ZIP_PATH" | cut -f1)
echo "  ✓ 크기: $SIZE"

echo "[2/3] Google Drive 폴더로 복사"
if [ -d "$GDRIVE_DIR" ]; then
  cp -f "$ZIP_PATH" "$GDRIVE_DIR/"
  echo "  ✓ 복사 완료: $GDRIVE_DIR/$ZIP_NAME"
elif mkdir -p "$GDRIVE_DIR" 2>/dev/null; then
  cp -f "$ZIP_PATH" "$GDRIVE_DIR/"
  echo "  ✓ 폴더 생성 + 복사 완료: $GDRIVE_DIR/$ZIP_NAME"
else
  echo "  ⚠ Google Drive 폴더에 쓸 수 없습니다. 수동으로 옮겨 주세요:"
  echo "      $ZIP_PATH"
  echo "    → $GDRIVE_DIR/"
fi

# Windows_빌드_안내.txt 도 함께 복사 (없으면 무시)
if [ -f "distribution/Windows_빌드_안내.txt" ] && [ -d "$GDRIVE_DIR" ]; then
  cp -f "distribution/Windows_빌드_안내.txt" "$GDRIVE_DIR/"
  echo "  ✓ Windows_빌드_안내.txt 도 복사"
fi

echo "[3/3] 완료"
echo
echo "→ 학교 Windows PC에서 zip 풀고  build_scripts\\build_windows.bat  실행하면 .exe 가 만들어집니다."
echo "→ 자세한 안내: $GDRIVE_DIR/Windows_빌드_안내.txt"
