# Mac·학교 Windows에서 개발 이어가기

기준: 1.0.6 개발 후보 / Python 3.14.2 / Node 22.23.1. 기존 설치·배포 1.0.5는 보존한다. Mac 소스 실행·합성 검증은 진행 중이며 Windows 새 복제본 실행과 CI 설치는 아직 미검증이다. 학교 OS·아키텍처 확인 전 Windows x64는 예정 지원 대상이다.

## 1. 각 컴퓨터에서 별도 저장소 사용

GitHub `piman-code/goedusplit`의 자기 작업 브랜치를 각 PC의 로컬 폴더로 clone한다. 같은 공유 드라이브의 한 폴더를 Mac·Windows에서 함께 편집하지 않는다. 소스·문서는 Git으로 공유하지만 학생자료·앱 설정·포트폴리오는 Git에 넣지 않는다. 실제 학생자료는 저장소 바깥에서 관리한다.

기존 복제본에서는 먼저 아래 상태를 확인하고, 미커밋 변경을 보존한 후 fetch/pull한다. stash 전체 적용은 하지 않는다. 해당 프로젝트의 과거 stash에 실제 학생자료가 있어 내용 열람·외부 전송이 허용되지 않았다.

```bash
git status --short
git branch --show-current
git rev-parse HEAD
git fetch origin
```

Mac·Windows가 동시에 작업하면 서로 다른 `codex/<작업명>` 브랜치를 사용한다. 다른 PC가 같은 작업을 이어갈 때는 먼저 이전 PC에서 검사·커밋·승인된 push를 완료한다. 새 PC는 `git pull --ff-only`로 해당 브랜치를 받고 커밋이 인계 기록과 같은지 확인한다. 충돌이 나면 강제 push/reset 대신 양쪽 변경을 읽어 합친다.

현재 Goal에서 에이전트의 새 설치·지속 설정·push·병합·공개 배포에는 구체적 변경안 검토 후 사용자 승인이 필요하다. 아래 준비 명령은 사용자가 직접 환경을 준비할 때의 안내이며 에이전트가 이를 실행했다는 뜻이 아니다.

## 2. 개발 환경 준비

기존 `.venv`는 삭제하거나 교체하지 않는다. Python 3.14.2·Node 22.23.1이 없으면 설치 범위를 먼저 결정한다. 기본 앱 분석에는 Node가 필요하지 않지만 웹 계산기 개발 검사에는 필요하다. HWP 변환의 kordoc은 선택 의존성이며 이 안내에서 자동 설치하지 않는다. HWPX·텍스트 PDF는 별도 kordoc 없이 읽는다.

새 복제본의 Mac 터미널:

```bash
python3 --version
node --version
python3 -m venv .venv
.venv/bin/python -m pip install --only-binary=:all: -r requirements-build-lock.txt
.venv/bin/python -m pip check
.venv/bin/python -B build_scripts/build_preflight.py
.venv/bin/python -B run_tests.py
node --test tests/test_expected_rate_web.cjs
.venv/bin/python run.py
```

새 복제본의 Windows PowerShell:

```powershell
py -3.14 --version
node --version
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --only-binary=:all: -r requirements-build-lock.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -B build_scripts\build_preflight.py
.\.venv\Scripts\python.exe -B run_tests.py
node --test tests/test_expected_rate_web.cjs
.\.venv\Scripts\python.exe run.py
```

PowerShell 실행 정책을 바꾸지 않아도 된다. activate 대신 `.venv`의 Python을 직접 실행한다. Windows setup 후보를 만들 때만 Inno Setup이 필요하다. 기존 설치를 감지하고, 없으면 자동 설치하지 않고 중단한다.

`requirements.txt`는 허용 범위, `requirements-build-lock.txt`는 후보용 정확한 버전이다. lock은 2026-10-02 기존 Mac 환경의 읽기 결과로 작성하고 Windows 전용 의존성 2개에 platform marker를 붙였다. 새 환경의 lock 설치 성공은 CI 미실행으로 아직 증명되지 않았다. 변경할 때는 새 후보 환경에서 두 OS의 검사를 통과한 후 반영한다. Python·Node는 위 버전에 맞추고 OS·CPU·전체 패키지 버전은 BUILD manifest에 기록한다.

## 3. 격리 검사와 실제 앱을 구분하기

`run_tests.py`와 각 `test_*.py`의 bootstrap은 설정의 명시적 INI 파일, 앱 저장 루트, 포트폴리오, WebEngine 프로필·캐시, AI 작업 폴더를 프로세스 전용 임시 폴더에 둔다. 기존 HOME·CODEX_HOME·설정을 변경하지 않는다. mock되지 않은 urllib 통신과 WebEngine 외부 URL은 차단한다. CLI 검사는 가짜 CLI를 명시해 호스트 환경변수의 영향을 받지 않는다.

```bash
.venv/bin/python -B run_tests.py -v
.venv/bin/python -B run_tests.py --pattern test_runtime_isolation.py
.venv/bin/python -B -m unittest discover -s tests
.venv/bin/python -B tests/manual_calculator_flows.py --run
.venv/bin/python -B tests/manual_laptop_ui.py --run
.venv/bin/python -B tests/manual_native_window.py --run
```

Windows는 `.venv/bin/python`을 `.\.venv\Scripts\python.exe`로 바꾼다. 마지막 native window 검사는 macOS 전용이다. 수동 스크립트도 합성 자료·임시 저장 위치를 사용하지만 일반 `run.py`는 실제 사용자 설정·저장 위치를 사용한다. 실제 후보 검증은 별도 사용자/격리 환경과 합성 자료를 준비해 진행한다. Mac sandbox의 QtWebEngine이 종료되면 화면 접근 권한이 있는 환경에서 같은 격리 스크립트를 실행한다. QtWebEngine sandbox 끄기를 일반 실행 절차로 사용하지 않는다.

## 4. 새 후보 작업 폴더에서 빌드하기

Mac의 기존 checkout에 있는 `build`·`dist`는 건드리지 않는다. 후보용 새 clone을 만들고 대상 SHA를 checkout한다. 그 clone의 환경을 위 절차로 준비한 뒤 실행한다.

```bash
bash build_scripts/build_mac.sh
bash build_scripts/pack_mac.sh
```

Windows PowerShell은 새 clone에서 실행한다.

```powershell
cmd /c build_scripts\build_windows.bat
cmd /c build_scripts\pack_windows.bat
cmd /c build_scripts\pack_windows_installer.bat
```

빌드 스크립트는 의존성·폰트를 자동 설치하거나 내려받지 않는다. 기존 `build`·`dist`가 있으면 중단한다. 학생 입력 등이 app/assets 포장 경로에 섞이면 내용을 열기 전에 거부한다. 기존 ZIP·DMG·setup을 덮어쓰지 않는다. 실패한 후보 폴더는 보존해 로그를 조사하고, 수정 후에는 새 후보 폴더를 사용한다.

## 5. 다른 PC로 넘길 기록

커밋 SHA, 브랜치, 제품 버전, 변경 범위, 실행한 검사·결과, 미검증, 다음 첫 작업을 `docs/GOAL_STATUS.md`와 새 세션 기록에 남긴다. Git 차이·후보 파일 구성을 감사한 뒤 승인된 브랜치로 push한다. 공유 기록에 개인 PC 절대경로·학생 행·실자료 화면을 넣지 않는다. 사용자 저장 JSON의 PC 간 이동은 T03에서 따로 확인한다. 포트폴리오 hash key는 PC별 설정이며 Git으로 동기화되지 않는다.
