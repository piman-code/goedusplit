@echo off
rem Windows .exe 빌드 스크립트.
rem 사용:  build_scripts\build_windows.bat
rem 결과:  dist\Goedu-Split\Goedu-Split.exe

setlocal
cd /d "%~dp0\.."

if not exist .venv (
  echo [1/6] .venv 생성
  python -m venv .venv
)
call .venv\Scripts\activate.bat

echo [2/6] 의존성 설치
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo [3/6] 한글 폰트 확보 (Gowun Dodum, NanumGothic)
python build_scripts\fetch_fonts.py

echo [4/6] 앱 아이콘 생성
python build_scripts\generate_app_icon.py

echo [5/6] 이전 빌드 정리
if exist build rmdir /s /q build
if exist dist  rmdir /s /q dist

echo [6/6] PyInstaller 빌드
pyinstaller --noconfirm --clean goedusplit.spec

echo.
echo === 완료 ===
echo 실행 파일: %CD%\dist\Goedu-Split\Goedu-Split.exe
echo Goedu-Split 폴더 전체를 다른 PC로 복사하면 그대로 동작합니다.
endlocal
