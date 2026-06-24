@echo off
chcp 65001 >nul
rem Windows .exe 빌드 스크립트.
rem 사용:  build_scripts\build_windows.bat
rem 결과:  dist\Goedu-Split\Goedu-Split.exe

setlocal
cd /d "%~dp0\.."

echo [0/9] Windows 소스 키트 보안/구성 감사
python build_scripts\windows_release_audit.py --source .
if errorlevel 1 exit /b 1

if not exist .venv (
  echo [1/9] .venv 생성
  python -m venv .venv
  if errorlevel 1 exit /b 1
)
call .venv\Scripts\activate.bat
if errorlevel 1 exit /b 1

echo [2/9] 의존성 설치
python -m pip install --upgrade pip
if errorlevel 1 exit /b 1
python -m pip install -r requirements.txt
if errorlevel 1 exit /b 1

echo [3/9] 한글 폰트 확보 (Gowun Dodum, NanumGothic)
python build_scripts\fetch_fonts.py
if errorlevel 1 exit /b 1

echo [4/9] 앱 아이콘 생성
python build_scripts\generate_app_icon.py
if errorlevel 1 exit /b 1

echo [5/9] 이전 빌드 정리
if exist build rmdir /s /q build
if exist dist  rmdir /s /q dist

echo [6/9] PyInstaller 빌드
pyinstaller --noconfirm --clean goedusplit.spec
if errorlevel 1 exit /b 1

echo [7/9] Windows 배포 폴더 경량화
python build_scripts\slim_windows_dist.py dist\Goedu-Split
if errorlevel 1 exit /b 1

echo [8/9] 개인정보/비밀값 감사
python build_scripts\privacy_release_audit.py dist\Goedu-Split
if errorlevel 1 (
  echo.
  echo [X] 개인정보/비밀값 감사 실패. dist 폴더를 배포하지 마세요.
  exit /b 1
)

echo [9/9] 배포 폴더 구성 확인
if not exist "dist\Goedu-Split\Goedu-Split.exe" (
  echo [X] dist\Goedu-Split\Goedu-Split.exe 가 없습니다.
  exit /b 1
)

echo.
echo === 완료 ===
echo 실행 파일: %CD%\dist\Goedu-Split\Goedu-Split.exe
echo 경량화 보고서: %CD%\dist\slim-windows-report.txt
echo Goedu-Split 폴더 전체를 다른 PC로 복사하면 그대로 동작합니다.
endlocal
