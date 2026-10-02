@echo off
chcp 65001 >nul
rem 빌드된 dist\Goedu-Split 폴더를 .zip으로 패키징.
rem 사용:  build_scripts\pack_windows.bat
rem 결과:  dist\Goedu-Split-<버전>-windows.zip

setlocal
cd /d "%~dp0\.."
if errorlevel 1 exit /b 1

set "PACK_PYTHON=python"
if exist ".venv\Scripts\python.exe" set "PACK_PYTHON=%CD%\.venv\Scripts\python.exe"
set "VER="
for /f "delims=" %%v in ('""%PACK_PYTHON%" build_scripts\read_app_version.py"') do set "VER=%%v"
if not defined VER (
  echo [X] app.__version__ 읽기 실패. 패키징을 중단합니다.
  exit /b 1
)
"%PACK_PYTHON%" build_scripts\build_identity.py --target windows --app dist\Goedu-Split
if errorlevel 1 exit /b 1

if not exist "dist\Goedu-Split\Goedu-Split.exe" (
  echo.
  echo [X] dist\Goedu-Split 폴더가 없습니다. 먼저 다음을 실행해 빌드하세요:
  echo    build_scripts\build_windows.bat
  exit /b 1
)

echo [1/3] 개인정보/비밀값 감사
"%PACK_PYTHON%" -c "from pathlib import Path; assert not any(p.is_symlink() or getattr(p, 'is_junction', lambda: False)() for p in Path('dist/Goedu-Split').rglob('*')), 'external links are not allowed in package'"
if errorlevel 1 exit /b 1
"%PACK_PYTHON%" build_scripts\privacy_release_audit.py dist\Goedu-Split distribution\USER_GUIDE.md
if errorlevel 1 (
  echo.
  echo [X] 개인정보/비밀값 감사 실패. 패키징을 중단합니다.
  exit /b 1
)

set ZIP=dist\Goedu-Split-%VER%-windows.zip
if exist "%ZIP%" (
  echo [X] 기존 ZIP을 보존합니다: %ZIP%
  exit /b 1
)

echo [2/3] 사용 안내문 동봉
if not exist "distribution\USER_GUIDE.md" (
  echo [X] 필수 사용 안내가 없습니다.
  exit /b 1
)
"%PACK_PYTHON%" -c "from pathlib import Path; src=Path('distribution/USER_GUIDE.md').read_bytes(); dst=Path('dist/Goedu-Split/사용 안내.md'); assert not dst.exists() or dst.read_bytes()==src, 'existing guide differs; preserve it'; dst.open('xb').write(src) if not dst.exists() else None"
if errorlevel 1 exit /b 1

echo [3/3] zip 생성
powershell -NoLogo -NoProfile -Command ^
  "Compress-Archive -Path 'dist\Goedu-Split\*' -DestinationPath '%ZIP%' -ErrorAction Stop"
if errorlevel 1 exit /b 1
if not exist "%ZIP%" exit /b 1

echo.
echo [OK] 패키지 완성
echo    파일:   %CD%\%ZIP%
echo.
echo 전달 방법: 위 .zip 파일 하나를 메일/USB로 보내면 됩니다.
echo 받는 분은 압축 해제 후 'Goedu-Split.exe' 더블클릭.
echo.
echo (!) 처음 실행 시 Windows Defender SmartScreen 경고가 뜰 수 있습니다.
echo    distribution\USER_GUIDE.md 의 'Windows 처음 실행' 섹션 참고.
endlocal
