@echo off
chcp 65001 >nul
rem Windows .exe 빌드. 기존 환경/산출물 보존, 자동 설치 없음.
rem 사용: build_scripts\build_windows.bat
rem 결과: dist\Goedu-Split\Goedu-Split.exe
setlocal
set "PYTHONDONTWRITEBYTECODE=1"
cd /d "%~dp0\.."
if errorlevel 1 exit /b 1

rem 기존 후보는 사용자가 보관하거나 별도 복제본에서 빌드한다.
if exist build (
  echo [X] 기존 build 폴더를 보존합니다. 별도 복제본에서 빌드하세요.
  exit /b 1
)
if exist dist (
  echo [X] 기존 dist 폴더를 보존합니다. 별도 복제본에서 빌드하세요.
  exit /b 1
)

set "BUILD_PYTHON=python"
if exist ".venv\Scripts\python.exe" set "BUILD_PYTHON=%CD%\.venv\Scripts\python.exe"
"%BUILD_PYTHON%" --version
if errorlevel 1 (
  echo [X] Python이 없습니다. 개발 환경 설치를 승인한 뒤 안내에 따라 준비하세요.
  exit /b 1
)

echo [1/8] 소스 보안/구성 감사
set "AUDIT_MODE="
if exist .git set "AUDIT_MODE=--repository"
"%BUILD_PYTHON%" build_scripts\windows_release_audit.py --source . %AUDIT_MODE%
if errorlevel 1 exit /b 1
"%BUILD_PYTHON%" build_scripts\preflight.py
if errorlevel 1 exit /b 1

echo [2/8] 기존 의존성 확인 - 자동 설치 없음
"%BUILD_PYTHON%" -c "import PySide6, matplotlib, numpy, openpyxl, pypdf, PyInstaller, PIL"
if errorlevel 1 (
  echo [X] 빌드 의존성이 없습니다. 설치 승인 후 선택한 Python으로 requirements.txt를 설치하세요.
  exit /b 1
)
"%BUILD_PYTHON%" -m pip check
if errorlevel 1 exit /b 1

echo [3/8] 기존 폰트/아이콘 확인 - 다운로드/재생성 없음
for %%F in (assets\fonts\GowunDodum-Regular.ttf assets\fonts\NanumGothic.ttf assets\fonts\NanumGothicBold.ttf assets\app_icon\goedusplit.ico assets\app_icon\goedusplit.png) do (
  if not exist "%%F" (
    echo [X] 필수 자산이 없습니다: %%F
    exit /b 1
  )
)

echo [4/8] 격리된 Python / 계산기 웹 검사
"%BUILD_PYTHON%" run_tests.py
if errorlevel 1 exit /b 1
node --test tests/test_expected_rate_web.cjs
if errorlevel 1 exit /b 1

echo [5/8] PyInstaller 빌드
"%BUILD_PYTHON%" -m PyInstaller --noconfirm goedusplit.spec
if errorlevel 1 exit /b 1

echo [6/8] Windows 배포 폴더 경량화
"%BUILD_PYTHON%" build_scripts\slim_windows_dist.py dist\Goedu-Split
if errorlevel 1 exit /b 1

echo [7/8] 개인정보/비밀값 감사
"%BUILD_PYTHON%" build_scripts\privacy_release_audit.py dist\Goedu-Split
if errorlevel 1 exit /b 1

echo [8/8] 배포 폴더 구성 확인
if not exist "dist\Goedu-Split\Goedu-Split.exe" (
  echo [X] dist\Goedu-Split\Goedu-Split.exe 가 없습니다.
  exit /b 1
)
"%BUILD_PYTHON%" build_scripts\build_identity.py --target windows --app dist\Goedu-Split --write
if errorlevel 1 exit /b 1

echo.
echo === 완료 ===
echo 실행 파일: %CD%\dist\Goedu-Split\Goedu-Split.exe
echo 경량화 보고서: %CD%\dist\slim-windows-report.txt
echo Goedu-Split 폴더 전체를 다른 PC로 복사하면 그대로 동작합니다.
endlocal
