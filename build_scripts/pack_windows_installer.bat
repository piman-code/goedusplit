@echo off
chcp 65001 >nul
rem 빌드된 dist\Goedu-Split 폴더를 Windows 설치파일(.exe)로 패키징합니다.
rem 필요: Inno Setup 6 (ISCC.exe)
rem 사용:  build_scripts\pack_windows_installer.bat
rem 결과:  dist\Goedu-Split-<버전>-windows-setup.exe

setlocal
cd /d "%~dp0\.."
if errorlevel 1 exit /b 1

set "PACK_PYTHON=python"
if exist ".venv\Scripts\python.exe" set "PACK_PYTHON=%CD%\.venv\Scripts\python.exe"
set "VER="
for /f "delims=" %%v in ('""%PACK_PYTHON%" -c "from app import __version__; import re; assert re.fullmatch(r'[0-9]+[.][0-9]+[.][0-9]+', __version__); print(__version__)""') do set "VER=%%v"
if not defined VER (
  echo [X] app.__version__ 읽기 실패. 패키징을 중단합니다.
  exit /b 1
)
"%PACK_PYTHON%" build_scripts\build_identity.py --target windows --app dist\Goedu-Split
if errorlevel 1 exit /b 1

if not exist "dist\Goedu-Split\Goedu-Split.exe" (
  echo.
  echo [X] dist\Goedu-Split\Goedu-Split.exe 가 없습니다.
  echo     먼저 다음을 실행해 빌드하세요:
  echo     build_scripts\build_windows.bat
  exit /b 1
)

echo [1/4] 개인정보/비밀값 감사
"%PACK_PYTHON%" -c "from pathlib import Path; assert not any(p.is_symlink() or getattr(p, 'is_junction', lambda: False)() for p in Path('dist/Goedu-Split').rglob('*')), 'external links are not allowed in package'"
if errorlevel 1 exit /b 1
"%PACK_PYTHON%" build_scripts\privacy_release_audit.py dist\Goedu-Split distribution\USER_GUIDE.md
if errorlevel 1 (
  echo.
  echo [X] 개인정보/비밀값 감사 실패. 설치파일 생성을 중단합니다.
  exit /b 1
)

set "SETUP=dist\Goedu-Split-%VER%-windows-setup.exe"
set "ISS=dist\Goedu-Split-%VER%-installer.iss"
if exist "%SETUP%" (
  echo [X] 기존 설치파일을 보존합니다: %SETUP%
  exit /b 1
)
if exist "%ISS%" (
  echo [X] 기존 설치 구성 파일을 보존합니다: %ISS%
  exit /b 1
)
if not exist "assets\app_icon\goedusplit.ico" exit /b 1

set ISCC=
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe
where ISCC.exe >nul 2>nul
if not errorlevel 1 set ISCC=ISCC.exe

if "%ISCC%"=="" (
  echo.
  echo [X] Inno Setup 6 을 찾지 못했습니다.
  echo     https://jrsoftware.org/isdl.php 에서 Inno Setup 6 설치 후 다시 실행하세요.
  exit /b 1
)

echo [2/4] 사용 안내문 동봉
if not exist "distribution\USER_GUIDE.md" (
  echo [X] 필수 사용 안내가 없습니다.
  exit /b 1
)
"%PACK_PYTHON%" -c "from pathlib import Path; src=Path('distribution/USER_GUIDE.md').read_bytes(); dst=Path('dist/Goedu-Split/사용 안내.md'); assert not dst.exists() or dst.read_bytes()==src, 'existing guide differs; preserve it'; dst.open('xb').write(src) if not dst.exists() else None"
if errorlevel 1 exit /b 1

echo [3/4] Inno Setup 스크립트 생성
(
  echo #define MyAppName "Goedu-Split"
  echo #define MyAppVersion "%VER%"
  echo #define MyAppPublisher "Lee Junseo"
  echo #define MyAppExeName "Goedu-Split.exe"
  echo.
  echo [Setup]
  echo AppId={{B9B56B7A-30E0-4D26-9B5F-9B5F090B6D11}
  echo AppName={#MyAppName}
  echo AppVersion={#MyAppVersion}
  echo AppPublisher={#MyAppPublisher}
  echo DefaultDirName={autopf}\{#MyAppName}
  echo DefaultGroupName={#MyAppName}
  echo DisableProgramGroupPage=yes
  echo OutputDir=.
  echo OutputBaseFilename=Goedu-Split-%VER%-windows-setup
  echo SetupIconFile=..\assets\app_icon\goedusplit.ico
  echo Compression=lzma
  echo SolidCompression=yes
  echo WizardStyle=modern
  echo ArchitecturesAllowed=x64compatible
  echo ArchitecturesInstallIn64BitMode=x64compatible
  echo.
  echo [Languages]
  echo Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"
  echo.
  echo [Tasks]
  echo Name: "desktopicon"; Description: "바탕 화면 바로가기 만들기"; GroupDescription: "추가 아이콘:"; Flags: unchecked
  echo.
  echo [Files]
  echo Source: "..\dist\Goedu-Split\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
  echo.
  echo [Icons]
  echo Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
  echo Name: "{group}\사용 안내"; Filename: "{app}\사용 안내.md"
  echo Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
  echo.
  echo [Run]
  echo Filename: "{app}\{#MyAppExeName}"; Description: "Goedu-Split 실행"; Flags: nowait postinstall skipifsilent
) > "%ISS%"
if errorlevel 1 exit /b 1

pushd dist >nul
if errorlevel 1 exit /b 1
echo [4/4] 설치파일 빌드
"%ISCC%" "Goedu-Split-%VER%-installer.iss"
set BUILD_STATUS=%ERRORLEVEL%
popd >nul

if not "%BUILD_STATUS%"=="0" (
  echo.
  echo [X] 설치파일 생성 실패
  exit /b %BUILD_STATUS%
)

if not exist "%SETUP%" exit /b 1

echo.
echo [OK] 설치파일 완성
echo    파일: %CD%\dist\Goedu-Split-%VER%-windows-setup.exe
echo.
echo 받는 분은 위 setup.exe 를 더블클릭해 설치하면 됩니다.
endlocal
