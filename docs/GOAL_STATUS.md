# Goal 현재 상태 — 2026-10-02

**상태: 개발 진행 중 / 배포 준비 미완료 / 공개 배포 미실행.**

Goal은 [DEVELOPMENT_PLAN](DEVELOPMENT_PLAN.md)의 필수 조건과 T01~T09 전체를 유지한다. 실제 새 Mac frozen 후보 증거는 [VERIFICATION_20261002](VERIFICATION_20261002.md)에 기록했다. 현재 개발 후보는 1.0.6이며 기존 설치·배포 1.0.5는 보존한다.

시작 기준은 `3b9dab6927f2d64379e3f9fbe4c6d4ee5ee84e95`다. 작업 브랜치는 `codex/desktop-candidates-1.0.6`, 실제 frozen QA를 통과한 최신 Mac 후보 소스는 `9baded3257d10c9d0e80f0782bea15f55efd180f`다. 이 후보의 DMG SHA256은 `3eefc2f5a73b76a34f7b73c17f15e834c2ee70b2994f2a641e045ae270598df9`다. 필수 12개 QA, 실행 파일·manifest 지문, codesign과 hdiutil 검증을 완료판정관이 독립 재확인했다. 읽기 전용 DMG 내부 앱을 직접 실행한 frozen QA도 통과했다. 이전 `adb89d5`·`07ea42c` 후보와 기존 설치는 보존한다.

GitHub `piman-code/goedusplit`은 2026-10-02 읽기 조회에서 공개 저장소·기본 브랜치 main으로 확인했다. 새 브랜치 push와 CI 임시 환경 의존성 설치·후보 artifact 생성에 대한 구체적인 승인 질문이 대기 중이다. 원격 push·CI 실행은 아직 하지 않았다. 최종 두 플랫폼의 후보 소스는 `9baded3`로 고정하며, 후속 검증 기록은 별도 문서 커밋으로 보존한다. CI 실행 시 최신 기록 커밋 대신 명시적으로 후보 SHA를 checkout한다.

## 현재 확보한 증거

| 확인 | 결과 | 한계 |
| --- | --- | --- |
| 기존 변경·환경 보존 | 실행 전 파일 백업, 설치 앱·기존 dist·.venv·원자료·stash·사용자 저장 데이터 보존 | 새 후보 설치·복귀는 아직 미검증 |
| Python 격리 검사 | 224개 실행, OK / 5개 Windows 전용 검사 건너뜀(배치 3·실제 junction 2). PYTHONPATH 없이 호스트 CODEX_CLI_PATH를 가짜값으로 넣어도 통과 | 건너뜀은 Windows 실행 통과가 아님 |
| 웹 계산기 계약 | Node 43개 통과 | 실제 Windows WebEngine 전체 검증 아님 |
| Mac 합성 계산기 흐름 | 6항목 통과: 예제 판단, 저장 작업 재열기, 비교, 문항/OX 변경 계산, 오류 없음 | 개발 소스 실행이며 배포 후보 아님 |
| Mac 합성 분석·내보내기 | 실제 MainWindow 파일 선택/분석 버튼·수행 60/40·CSV 4개·근거 XLSX·취소·실명 거절·수식 보호·격리 snapshot·키트 원본 보존, 13개 통과 | 개발 소스 실행. 예측–실측 XLSX·NEIS XLSX·Windows Excel·교사 확인 대기 |
| 합성 실기 키트 | XLSX 3개·한국어 TXT/HWPX/PDF·검토안 JSON·독립 수기 기대값/지문 생성과 6개 대조 통과 | minimal HWPX 파서 입력. native 한글앱 편집·HWP 바이너리·스캔 PDF 미검증 |
| 시험지 가져오기 Mac 소스 UI | HWPX/PDF 실제 메뉴·미리보기·WebEngine 반영·취소·빈 PDF 실패 보존 8개 통과 | 실제 후보 양쪽/HWP/스캔 PDF 성공/교사 확인 아님 |
| NEIS·예측–실측 Mac 소스 UI | 실제 WebEngine·자료 메뉴·modal 저장/취소, 엑셀3/2시트·독립 기대값·입력/출력 보존 25개 통과. 완료판정관이 XLSX/PNG 직접 대조 | 해당 추가 기능 frozen 후보·Windows Excel·학교/교사 확인 별도 |
| Mac 실제 창 | GPU 창 생성·계산기 탭 전환 시 창 재생성 없음, 2항목 통과 | 학교 Windows와 설치 후보는 별도 |
| Mac 작은 화면 | 밝음/어두움 × 1280×800/1080×720, 4개 합성 화면과 도구 배율 검사 통과 | 현재 소스의 offscreen WebEngine 검사. 실제 OS 배율·1366×768·교사 확인 대기 |
| 의존성 기준 | 기존 Mac 패키지 버전 읽기, pip check·build_preflight 통과, 새 lock 작성 | 새 clone의 lock 설치·Windows 전용 패키지·CI 미검증 |
| 빌드·포장 보존 | 자동 설치·출력 삭제 제거, 기존 build/dist/ZIP/DMG/setup/ISS 존재 시 중단 | Windows cmd 배치 실제 실행 대기 |
| 소스 감사 | Git/소스kit 구분, symlink·학생 입력·비추적 포장 경로 유입 차단 회귀 검사 통과. 고정 커밋의 새 worktree 감사 통과 | 원본 checkout 감사는 app/assets의 .DS_Store 2개를 감지해 중단. 내용을 열거나 삭제하지 않음 |
| 후보 신원·필수 파일 | clean source SHA·버전·OS/CPU·실행 파일 hash·같은 두 플랫폼 후보 검증 코드와 회귀 검사 통과 | 실제 두 플랫폼 후보가 만들어진 증거는 아직 없음 |
| 통합 CI | 한 SHA resolve→Mac arm64/Win x64→frozen QA→필수 후보 pair 확인 작성. YAML parse·resolver 합성 실행 통과 | 원격 push·CI 실행 미실행. 통합 성공으로 표시하지 않음 |
| 독립 검토 | 계획관·구축관·완료판정관이 실제 파일 검토. 발견한 import·symlink/junction·비추적 자산·버전·WebEngine·아키텍처·Windows preflight 경로·재열기 오탐을 수정. 실제 Mac frozen 후보 12개 QA·manifest·DMG·서명 독립 재검증 통과 | Windows CI·학교 실기·교사 확인은 대기 |

로컬 비식별 증거: `out_test/goal-20261002-checks/python-tests-kit.log`, `out_test/goal-20261002-laptop/metrics.json`과 합성 PNG. 이 폴더들은 Git·전송 대상에서 제외한다. 밝은 1280×800 문항표와 어두운 1080×720 선택 문항 화면 2장을 직접 시각 확인했다. 전체 그래프·모든 배율의 시각 검토와 교사 확인은 대기다.

## 단계와 필수 기준의 남은 일

| 묶음 | 상태 | 다음 증거 |
| --- | --- | --- |
| P0 | 로컬 구현·안내 정비, 검증 부분 완료 | clean clone의 양쪽 개발 실행, Windows cmd 검사, 최종 독립 검토 |
| P1 | 합성 소스 검사·Mac frozen UI 일부 통과, 합성 NEIS 기대값 키트 및 Mac 분석·내보내기 소스 실행 통과 | 양쪽 frozen 후보/학교 PC의 분석·파일 호환·UI 실기 |
| P2 | CI·빌드 준비 구현 | 검토된 commit, 전송 직전 감사, 승인 범위 push/CI, 같은 SHA 양쪽 빌드 |
| P3 | 파일·게시·복귀 절차 준비안 | 실제 후보·SHA256·다운로드·설치·복귀·지원표 확정 |
| P4 | README/SECURITY/QA/개발/인계 문서 정비 | 현재 후보와 실제 증거로 최종 재현·교사 확인·릴리스 노트 확정 |

T01~T09는 **어느 항목도 전체 합격으로 표시하지 않는다**. 소스 계산·저장·가명·문항 파서 검사와 Mac UI 일부 증거가 있지만 동일 SHA의 두 OS 후보 실기, Windows Excel, Mac→Windows→Mac JSON 실제 왕복, HWP 성공/부재 환경, 실제 오프라인·OS 배율·교사 유용성·설치·복귀 결과가 남았다.

## 확인된 제약과 처리

- 원본 checkout의 비추적 `.DS_Store` 2개는 내용 미열람·보존한다. clean 후보 checkout에는 Git 추적 파일만 들어가므로 이 파일을 옮기거나 삭제할 필요 없이 새 checkout에서 빌드한다.
- sandbox에서 QtWebEngine이 시스템 알림 접근 오류와 exit134로 종료됐다. 동일 격리 스크립트를 Mac 그래픽 시스템 접근으로 재실행해 통과했다. 제품 crash로 확정하지 않으며 sandbox 끄기를 제품 실행 절차에 추가하지 않는다.
- 작은 화면 검사와 native 분석 실행 중 일부 그래프의 tight_layout 경고가 있었다. 1280×800 캡처에서 그래프 하단·학생 표의 표시 높이가 작아 일부가 잘리는 모습을 확인했다. 계산기 조작 검사는 통과했지만 기존 접기 버튼으로 그래프 전체 축/제목과 표4행을 각각 확인하는 4개 검사·PNG는 통과했다. 기본 전부 펼침/다른 배율/학교 실기·교사 시각 검토는 대기다.
- React 원본은 현재 추적 파일에 없다. 실제 학생자료를 포함한 stash 전체를 적용하지 않는다. 이번 변경은 기존 번들·계산 계약·저장 형식을 재작성하지 않았다.
- Mac ad-hoc 서명은 Apple 공증이 아니다. Windows 코드 서명·학교 정책 확인도 대기다. Intel Mac/Windows ARM은 검증 전 지원표에 넣지 않는다.

## 다음 안전한 작업

합성 실기 키트와 Mac 분석·내보내기 소스 검증을 완료했다. 안내는 [SYNTHETIC_VALIDATION](SYNTHETIC_VALIDATION.md)를 따른다. NEIS/예측–실측 저장과 시험지 가져오기 소스 UI도 통과했다. 다음은 승인된 원격 CI에서 같은 후보 SHA의 Windows 파일 확보와 양쪽 후보 실기다. GitHub 전송은 승인 답변 후 같은 브랜치의 검토·검사된 소스로 진행하며, 실제 Windows PC 확인을 기다리는 동안 로컬 작업을 계속한다. 설치 교체·main 병합·공개 Release는 현재 승인 범위에 포함하지 않는다.
