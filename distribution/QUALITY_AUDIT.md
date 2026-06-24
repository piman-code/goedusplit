# Goedu-Split Windows Release Quality Audit

## Release Goal

Windows용 `dist\Goedu-Split\Goedu-Split.exe`, `dist\Goedu-Split-1.0.1-windows.zip`, 선택 설치파일이 교사용 성취평가 분석 도구로 배포 가능한 상태인지 확인한다. 소스 테스트만으로 완료하지 않고, 실제 앱 실행과 개인정보/AI 연결/예상정답률 UI를 함께 본다.

## Required Checks

- 분석 기능: 정오표, 문항정보표, 선택 자료를 넣고 분석 실행이 완료된다.
- 예상정답률: 분석자료가 없어도 기본 또는 직접 입력 분할점수가 상단에 표시된다. 문항 표가 있으면 현재 표 전체 문항의 배점과 A/B/C/D/E 예상정답률을 합산한 전체 예상 분할점수가 우선 표시되고, 목표 성취수준 변경 즉시 다시 계산된다. 한 문항만 체크해도 상단 점수는 선택 문항이 아닌 전체 문항 기준임을 안내한다. 상단/요약 배너는 접고 펼칠 수 있으며, 목표 설정/표 헤더는 고정되고 문항 행만 스크롤된다.
- AI 검토: 기본값은 외부 전송 없는 로컬 초안이다.
- Ollama 로컬: Ollama 서버와 채팅 모델이 있을 때 `/api/chat` 경로로 짧은 JSON 응답이 온다. Ollama 0.30.x의 Apple Silicon MLX engine 최적화는 Goedu-Split의 별도 MLX 설정이 아니라 Ollama 런타임 내부 동작으로 안내한다.
- Ollama server version이 0.30 미만이면, client만 업데이트된 상태일 수 있으므로 AI 설정 상태/진행 로그에서 Ollama 앱 또는 `ollama serve` 재시작을 안내한다.
- Codex CLI 클라우드: API Key 없이 `codex login`의 ChatGPT OAuth 세션으로만 연결된다.
- Codex CLI 탐색: Windows GUI 앱의 PATH가 짧아도 `codex.cmd`, npm/Node 경로, `~/.codex/config.toml`의 `CODEX_CLI_PATH`, 환경변수 `CODEX_CLI_PATH`를 확인한다. macOS 빌드에서는 Homebrew 경로도 확인한다.
- 개인정보: AI 전송 전 학생 이름, 반/번호, 전화번호, 이메일 제거 옵션이 적용된다.
- 번들: `sample_data`, `.git`, `.venv`, API key 형태 문자열, 로컬 개발 경로가 앱 번들에 포함되지 않는다.
- 경량화: QtWebEngine, Qt QML, PySide6 필수 리소스는 보존하고 저위험 리소스만 제거한다.

## Automated Gate

```bash
python -m py_compile app/main_window.py app/ai_client.py
node --check app/spliter_ox_web/assets/index-DE5gZsFK.js
python build_scripts/windows_release_audit.py --source .
python -m unittest discover -s tests
build_scripts\build_windows.bat
python build_scripts\privacy_release_audit.py dist\Goedu-Split
build_scripts\pack_windows.bat
```

## Release Notes

- OpenAI Platform API Key provider는 Windows 제품 UI에서 제공하지 않는다.
- 클라우드 AI는 `Codex CLI 클라우드 (OAuth)`만 사용한다.
- `AI 검토` 첫 진입과 `AI 설정`의 `AI 연결 안내` 버튼은 Ollama/MLX 사용법, Windows 터미널의 Node.js/Codex CLI 설치 명령, Codex CLI OAuth 사용법, timeout 대응, API Key 미사용 경계를 교사용 문구로 설명한다.
- Windows 공개 배포는 Windows 소스 키트 감사, dist 개인정보/비밀값 감사, 실제 실행 QA를 모두 통과한 뒤 진행한다.
