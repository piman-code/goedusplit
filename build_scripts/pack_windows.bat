@echo off
rem 빌드된 dist\Goedu-Split 폴더를 .zip으로 패키징.
rem 사용:  build_scripts\pack_windows.bat
rem 결과:  dist\Goedu-Split-<버전>-windows.zip

setlocal enabledelayedexpansion
cd /d "%~dp0\.."

if not exist "dist\Goedu-Split" (
  echo.
  echo [X] dist\Goedu-Split 폴더가 없습니다. 먼저 다음을 실행해 빌드하세요:
  echo    build_scripts\build_windows.bat
  exit /b 1
)

rem 버전 추출
set PY=python
if exist ".venv\Scripts\python.exe" set PY=.venv\Scripts\python.exe
for /f %%v in ('%PY% -c "from app.main_window import APP_VERSION; print(APP_VERSION)"') do set VER=%%v

set ZIP=dist\Goedu-Split-%VER%-windows.zip
if exist "%ZIP%" del "%ZIP%"

rem 사용 안내문 동봉
if exist distribution\USER_GUIDE.md copy /y distribution\USER_GUIDE.md "dist\Goedu-Split\사용 안내.md" >nul

powershell -NoLogo -NoProfile -Command ^
  "Compress-Archive -Path 'dist\Goedu-Split\*' -DestinationPath '%ZIP%' -Force"

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
