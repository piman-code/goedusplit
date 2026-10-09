# Goedu-Split 현재 작업과 Mac 인계

2026-10-09 기준 작업 요약이다. 앱 수정 소스는 `codex/startup-optimized-20261007`의 `943115609854894bc7be8b5b6ec1edc6fef29095`에 이미 올라가 있다. 이번 추가 커밋은 인계 문서·검사 도구·결과 기록만 추가한다. **이번 문서 커밋과 실제 검증된 앱 후보 커밋 9431156을 구분한다.** 공개 릴리스나 정식 배포 완료 상태는 아니다.

## 완료한 제품 보완

- 시작 시 계산기 WebEngine 등의 초기화를 늦추고 예상정답률 시험지 인식 경로를 제외한 이전 시작 최적화가 현 후보에 포함돼 있다. 일반 시작의 실제 시간 개선율은 이번 QA 시간으로 계산하지 않는다.
- 분석 결과의 표·그래프가 실제 생성되는지 확인하고, 그래프 교체 시 이전 캔버스가 독립 창이 되는 경로를 보완했다. 계산기 탭 전환과 분석 후 주 창 native surface가 유지되는지 검사한다.
- 학생 포트폴리오에 현재 분석의 미저장 미리보기와 명시적 현재 과목 저장을 제공했다. 고유 이름·배타적 생성으로 이전 기록을 덮어쓰지 않는다. 재읽기·이름 복원·두 과목 연결·학생 필터·상담 리포트를 검사했다. 저장 식별자는 기존 방식의 keyed hash이며 기존 설정의 키 보존이 필요하다.
- 잘못된 개별 기록은 원본을 보존하고 진단하며 나머지 기록 표시를 계속한다. 환산점수와 회차 표기를 보완했다.
- Windows 빌드에서 release 대응 파일이 있는 중복 WebEngine debug 리소스만 새 수집 단계에서 제외했다. Qt 런타임·소프트웨어 OpenGL·폰트·라이선스를 유지했다. 이전 설치 폴더 588.56MiB에서 511.41MiB로 77.15MiB, 13.11% 감소했다. 더 큰 축소는 WebEngine 대체 같은 구조 변경이 필요하다.
- frozen GUI QA에서 stderr가 없어도 native 충돌 진단이 남도록 배타적 `NATIVE_CRASH.log`를 사용한다. 초기화된 그래프 캔버스만 감시한다.

## 실제 검증 결과

| 범위 | 실제 결과 및 한계 |
|---|---|
| GitHub CI [37599918029](https://github.com/piman-code/goedusplit/actions/runs/37599918029) | source·Windows·Mac·pair 모두 성공, 후보 커밋 9431156 |
| Windows Python / 계산기 | 267개 중 256 통과·환경별 11 제외 / 43 통과 |
| Mac Python / 계산기 | 267개 중 258 통과·환경별 9 제외 / 43 통과 |
| Mac frozen CI | Cocoa arm64 hosted runner 29/29 성공. 사용자의 실제 Mac 결과 아님 |
| 현재 Windows native 후보 | 29/29 성공, 종료 0, 분석 그래프 12개, 두 반 5명·2회차 |
| 포트폴리오 | 저장 3개·기록 15개·과목 2개·선택 학생 기록 3개, 잘못된 파일 1개 보존 |
| 추가 Qt 배율 1.25 | 2026-10-08, 29/29·종료 0·35.284초 |
| 추가 Qt 배율 1.5 | 2026-10-08, 29/29·종료 0·31.193초 |
| 새 학교 검사 도구 | 2026-10-09 Windows PowerShell 5.1 실제 실행, 압축 manifest·2,453개 파일 검증, 29/29·종료 0·36.893초. 현재 PC 결과이며 학교 인수 아님 |
| 양 플랫폼 대조 | 동일 커밋·버전·필수 파일·체크섬 및 29개 검사 확인. 로컬 대조도 성공 |
| 기존 파일 | 이전 다섯 설치본 12,280개 파일 크기·해시 및 a7 EXE 확인·보존. 바탕화면은 새 final 9431156 후보 폴더 사용 |

Qt 배율은 자식 프로세스 환경값 모의검사다. 실제 Windows OS 배율·테마·학교 인수를 대신하지 않는다. QA 전체 시간은 일반 시작 시간이 아니다. stderr에는 GLES3 context 생성 실패·GLES2 fallback·shared context 오류가 남았으나 UI 검사와 정상 종료는 성공했다. 모든 GPU 환경이 성공했다고 단정하지 않는다.

처음 추가 배율 검사 `current-qt125-01`은 도구 세션이 없어져 완료 결과를 회수하지 못했다. QA_REPORT·RUN_RESULT가 없고 원인 미확정이다. 원본을 보존하고 새 경로 `current-qt125-02`에서 정상 결과를 얻었다. 중간 4af15c7 Mac 후보의 종료 139, 43c6831 Windows frozen timeout도 최종 후보 성공과 구분한다. 이전 충돌 원인을 확정했다고 표현하지 않는다.

기계 판독 요약은 [STATUS.json](handoff/20261009/STATUS.json), 후보와 검사 목록은 [CANDIDATE_LOCK.json](handoff/20261009/CANDIDATE_LOCK.json), 새 학교 도구의 실제 결과는 [WINDOWS_HELPER_CHECK.json](handoff/20261009/WINDOWS_HELPER_CHECK.json)에 있다. 업로드한 결과는 원래 로그에서 필요한 비식별 항목을 추출한 요약이며 전체 원본 로그 대체물이 아니다. 원본 Windows 로그·캡처·설정은 기존 PC 결과 폴더에 보존했다. CI 원본은 해당 run/artifact를 사용한다.

## Mac에서 같은 후보 받기

GitHub Actions의 위 run에서 `candidate-macos-943115609854894bc7be8b5b6ec1edc6fef29095` artifact **11473932968**을 내려받는다. 인증된 GitHub 연결 또는 이미 설치된 CLI를 사용한다. 새 도구 설치는 하지 않는다.

| 파일 | SHA256 |
|---|---|
| Mac artifact ZIP 바깥 봉투 | `803c2dee9ff078590ab27d3c119fe6f6f16212fb81c8fdcbc7629898dca90daa` |
| Goedu-Split-1.0.6-mac.dmg | `b1b6366318c2514e060cac7640af18477ad881d0438ab5b1e723fd230aee52ed` |
| Mac 앱 실행 파일 | `5aeb8a5102960471ec245ece1c8f3237d37f12eea6247a06e407739b7f7ee548` |
| Windows portable ZIP | `f9cb228af774b53fa6ccb73a64f5a9b55a6c15fc1b551b253ded9adad6f6aaaa` |
| Windows EXE | `a7c157823a648433d9d420fdd73216b8777fe7066a5bf37b3484e3758f3b9701` |

artifact ZIP에는 `BUILD-macos.json`、`QA-macos.json`、DMG、가이드가 포함된다. 추출 전 경로 탈출·중복·링크를 확인하고 기존 폴더를 재사용하지 않는다. 후보 DMG 크기는 235,923,549바이트다. 바깥 artifact ZIP과 DMG 해시를 혼동하지 않는다.

2026-10-09 GitHub에서 Mac/Windows/pair artifact가 미만료임을 확인했다. 표시된 만료일은 2026-10-21 UTC다. 만료됐다면 다른 후보로 대체하지 말고 보존 파일 또는 명시적 새 빌드 계획을 기록한다. 저장소에는 큰 설치본이나 DMG를 추가하지 않고 CI artifact를 참조한다.

Mac 검증 순서:

1. 기존 작업 상태를 읽기 전용으로 확인한다. dirty checkout을 전환·덮어쓰지 말고 새 체크아웃 또는 작업 폴더를 쓴다. 문서는 브랜치 최신, 후보 소스·산출물은 위 9431156으로 고정한다.
2. Mac 모델·OS·CPU 아키텍처와 artifact·DMG·실행 파일 해시, embedded BUILD_SOURCE를 확인한다. 현재 Mac 후보는 arm64다. 호환성 문제를 Rosetta 설치나 보안 우회로 해결하지 않는다.
3. `run.py`와 `app/synthetic_qa.py`를 읽어 명시적 INI·포트폴리오·off-the-record WebEngine 격리를 확인한다. 필요하면 DMG를 읽기 전용으로 마운트한다. Applications 설치·덮어쓰기는 하지 않는다.
4. 검증한 앱 실행 파일에 `--synthetic-qa <아직 없는 새 절대 결과 경로>`만 지정한다. stdout/stderr, 종료 코드·QA_REPORT·NATIVE_CRASH·캡처를 보존한다. 일반 실행이나 `open -a`는 하지 않는다. Gatekeeper 등 차단이 있으면 xattr 삭제·실행 허용 변경·서명 변조로 우회하지 않는다.
5. 29개 실제 검사·그래프 12개·포트폴리오·native window를 확인하고 hosted CI와 실제 Mac 결과를 각각 기록한다. 설치·정책 변경 없이 가능한 범위에서 후속 검증을 계속한다.

## 남은 작업과 선행 조건

- **학교 Windows PC:** 사용 가능은 확인됐고 실제 검사·교사 인수는 미실행이다. [Windows 검사 도구](handoff/20261009/RUN_WINDOWS_CHECK.ps1)와 압축 manifest를 같은 새 폴더에 받고, 고정 후보 Windows ZIP을 놓아 실행한다. 압축 manifest 자체 해시는 STATUS.json에 있다. 기존 로컬 학교 검사 ZIP도 보존돼 있지만 GitHub에 그 대용량 묶음은 올리지 않았다.
- **동일 파일 Mac→Windows→Mac:** 구 [Mac 문서](PC_VALIDATION_MAC_20261002.md)와 `tests/fixtures/T03-20261002-Mac-first/`는 고정 a7의 실제 Mac 저장 파일 증거다. 삭제·대체하지 않는다. 고정 a7에는 기존 JSON 입력 기능이 없고 최신 격리 QA는 외부 JSON 입력을 받지 않는다. Windows 재저장·Mac 재열기는 미실행이다. 서로 다른 기기의 자체 생성 파일 성공을 동일 파일 왕복으로 취급하지 않는다.
- **개발 후속 우선순위:** 안전한 격리 대화형 실행 및 외부 JSON 입력·저장 경로를 구현·검증해야 실제 동일 파일 왕복, 교사 업무 흐름과 호환성 검사를 진행할 수 있다. 일반 실행의 설정 격리가 확보되기 전에는 실행하지 않는다. 기존 일반 사용자 설정·키·저장 의미를 보존한다.
- **Excel/HWP·실제 OS 배율·테마·오프라인:** COM 등록만 확인했고 실제 파일 열기·교사 인수는 미실행이다. 안전한 격리 대화형 흐름이 선행 조건이다.
- **정식 서명·공증·배포:** Windows Authenticode는 NotSigned다. Mac Developer ID·공증과 Windows 코드 서명은 별도 인증서·계정 작업이 필요하다. 설치·보안정책 변경·공개 배포는 이번 인계 범위에 포함하지 않는다.

`docs/WINDOWS_SCHOOL_QA.md` 및 기존 학교 검사 workflow는 고정 65cfc79/a7의 12개 검사다. 이번 9431156의 29개 기준과 섞지 않는다. 최신 [Mac handoff 프롬프트](handoff/20261009/MAC_RESUME_PROMPT.txt)를 사용한다.
