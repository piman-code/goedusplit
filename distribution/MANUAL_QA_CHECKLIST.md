# Goedu-Split Manual QA Checklist

## Before Starting

- 실행 중인 `Goedu-Split` 앱을 모두 종료한다.
- macOS 새 빌드 대상은 `dist/Goedu-Split.app`이다.
- Windows 새 빌드 대상은 `dist\Goedu-Split\Goedu-Split.exe`이다.
- Codex CLI 테스트를 하려면 Windows 터미널에서 `winget install OpenJS.NodeJS.LTS`, `npm install -g @openai/codex`, `codex login` 후 `codex login status`가 `Logged in using ChatGPT`로 나와야 한다.
- Windows 터미널에서는 `where codex`, macOS 터미널에서는 `which codex`로 설치 위치를 확인한다. Windows 앱은 `codex.cmd`, npm/Node 경로, `~/.codex/config.toml`의 `CODEX_CLI_PATH`, 환경변수 `CODEX_CLI_PATH`를 확인해야 한다.
- Ollama 테스트를 하려면 `ollama --version`이 0.30.x 이상인지 확인하고, `ollama serve`가 실행 중이며 `gemma4:e4b` 같은 채팅 모델이 있어야 한다.
- `ollama --version`에서 server는 0.30.x 미만인데 client만 0.30.x로 나오면, 업데이트된 Ollama server가 아직 실행되지 않은 상태다. Ollama 앱과 `ollama serve`를 완전히 종료 후 다시 연다.

## Core Flow

1. macOS는 `open -n dist/Goedu-Split.app`, Windows는 `dist\Goedu-Split\Goedu-Split.exe`로 앱을 연다.
2. 입력 파일을 지정하고 `분석 실행`을 누른다.
3. Data, 전체 성취도, 문항, 답지반응, 성취기준 탭이 비지 않는지 확인한다.
4. 상담 모드를 켜고 학생 이름과 반/번호가 가려지는지 확인한다.

## Expected Rate Flow

1. `예상정답률 입력` 탭을 연다.
2. 분석자료가 없어도 상단에 기본 `A/B 90`, `B/C 80`, `C/D 70`, `D/E 60` 분할점수가 보이는지 확인한다.
3. 좌측 분할점수를 직접 바꾸면 예상정답률 탭의 분할점수가 `직접` 기준으로 갱신되는지 확인한다.
4. 분석자료를 보낸 뒤에는 상단에 `A/B`, `B/C`, `C/D`, `D/E` 전체 예상 분할점수가 보이고, 목표 성취수준 정답률 설정, `선택/문항/배점/난이도/목표/A/B/C/D/E` 헤더가 고정되는지 본다.
5. 문항별 목표 성취수준을 A에서 C 또는 E로 바꾸면 상단 `전체 예상 분할점수`가 현재 표 전체 문항의 배점과 A~D 예상정답률에 맞춰 다시 계산되는지 확인한다.
6. 한 문항만 체크해도 상단 분할점수는 선택 문항이 아니라 전체 문항 기준이라는 안내가 보이는지 확인한다.
7. 문항 행만 스크롤되는지 확인한다.
8. `상단 접기`, `요약 접기` 버튼으로 위쪽 배너가 접히고 다시 펼쳐지는지 확인한다.
9. A~E 셀을 클릭해 값이 순환하는지 확인한다.
10. `작업 저장` 후 다시 `작업 불러오기`해서 설정과 문항이 복원되는지 확인한다.

## AI Review Flow

1. `AI 검토` 탭에서 문항 자료와 성취기준·수준 자료를 넣는다.
2. 첫 진입 때 `AI 연결 안내` 팝업이 뜨는지 확인한다. 한 번 닫은 뒤에는 자동으로 반복 표시되지 않고, `AI 설정`의 `AI 연결 안내` 버튼으로 다시 열려야 한다.
3. `검토 초안 생성`을 누르고 로컬 초안 행 수와 근거를 확인한다.
4. `AI 설정`에서 `Ollama 로컬`을 선택하고 `모델 새로고침`, `연결 테스트`를 누른다.
5. Ollama 안내의 의미를 확인한다: Goedu-Split은 별도 MLX 서버를 설정하지 않고, Ollama 0.30.x 이상이 지원 모델을 Apple Silicon에서 실행할 때 내부적으로 MLX engine 최적화를 사용할 수 있다.
6. Ollama server가 0.30 미만이면 AI 설정 상태/진행 로그에 재시작 또는 업데이트 반영 안내가 남는지 확인한다.
7. `AI 설정`에서 `Codex CLI 클라우드 (OAuth)`를 선택하고 `연결 테스트`를 누른다. 실패하면 진행 로그가 CLI 경로, OAuth 로그인, 네트워크/JSON 실패 중 어느 단계인지 구분하는지 확인한다.
8. 화면 어디에도 API Key 입력칸이 보이지 않는지 확인한다.
9. 개인정보 제거 옵션을 켠 뒤 `AI로 보강`을 실행한다.
10. 실패하면 기존 로컬 초안이 유지되고 진행 로그에 실패 이유가 남는지 확인한다.

## Export And Release

1. CSV/XLSX 내보내기를 실행한다.
2. 저장된 파일에 불필요한 학생 개인정보가 들어가지 않았는지 상담 모드 목적에 맞게 확인한다.
3. `dist/slim-mac-report.txt`가 생성됐는지 확인한다.
4. macOS는 `codesign --verify --deep --strict dist/Goedu-Split.app`가 통과하는지 확인한다.
5. Windows는 `python build_scripts\windows_release_audit.py --source .`와 `python build_scripts\privacy_release_audit.py dist\Goedu-Split`가 통과하는지 확인한다.
