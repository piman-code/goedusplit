# 2026-10-02 현재 검증 증거

상태: **Mac 후보 빌드·격리 실행 부분 검증 / Windows CI·실기·교사 확인 대기.**

## 고정 소스와 후보

- 제품 버전: 1.0.6.
- 후보 기준 SHA: `07ea42c2fc8e750be407aa1228a51a5a715e8b64`.
- 로컬 브랜치: `codex/desktop-candidates-1.0.6`. 현재 기록 시점 push 미실행, 사용자 승인 질문 대기.
- Mac 후보: `Goedu-Split-1.0.6-mac.dmg`.
- Mac DMG SHA256: `702b64b657c9537069b18dbe4635634f235a03117020df7e48283d8cbf1a304f`.
- 소스 clean SHA·버전·Mac arm64·실행 파일 출처를 BUILD manifest로 대조했다. 기존 Mac Python 환경을 읽기 사용한 새 관리 worktree 빌드이며, 새 환경 설치 증거는 아니다.

## 직접 실행한 검사

| 검사 | 결과 | 증거 범위 |
| --- | --- | --- |
| 격리 Python 전체 | 214개 OK, 4개 Windows 전용 건너뜀 | 코드와 합성 입력. Windows cmd/junction 실제 검사 대기 |
| 계산기 JS 계약 | 43개 통과 | 소수·0/100·저장·반올림·검증 계약 |
| 소스 감사·preflight·pip check | 새 후보 worktree 통과 | 실제 원본 checkout의 비추적 .DS_Store는 보존하며 새 checkout에 포함 안 함 |
| PyInstaller Mac 앱 | 성공 | 새 고정 SHA에서 생성, QtTest·unittest.mock 포함 확인은 아래 실제 실행으로 확보 |
| QtWebEngine 필수 구성·보정 | 통과 | process·resources 존재, 잘못된 위치 보정 전 파일 보존 |
| 개인정보 번들 감사 | 통과 | 한정 패턴 검사와 파일 구성. 모든 개인정보가 없다는 일반 보증 아님 |
| ad-hoc codesign 검증 | 통과 | Apple Developer ID·공증 증거 아님 |
| DMG 만들기·hdiutil verify | 통과 | 실제 새 DMG 파일의 내부 checksum 유효 |
| frozen 후보 합성 QA | `passed`, `frozen: true`, 필수 12개 true, errors 0 | Mac 실행 파일 자체의 실제 Qt·WebEngine·다운로드 흐름 |
| release_manifest 수집 | 통과 | source SHA·clean·버전·arch·QA 실행 파일 hash·필수 체크 이름·배포 파일 hash 대조 |

## 실제 frozen QA가 확인한 12개

1. 사용자 설정 대신 명시적 새 INI 파일 사용.
2. 포트폴리오 저장이 새 QA 루트 내부.
3. WebEngine off-the-record 프로필.
4. 앱에 내장된 계산기 실제 렌더링.
5. 합성 파일 선택·소수 배점·0/100/63.25%·여러 검토안 업무 값 보존.
6. 실제 WebEngine JSON 다운로드 후 업무 값 일치.
7. 다른 합성 작업(배점 6.25)으로 바뀐 상태를 확인하고 저장 파일로 원래 값 복원.
8. 저장 취소 시 추가 JSON 없음과 입력·기존 저장 파일 바이트 보존.
9. 탭 전환 후 작업 보존.
10. JavaScript 오류·네이티브 경고 대화상자 없음.
11. 핵심 흐름의 외부 네트워크 요청 시도 없음.
12. 실제 후보 창 캡처 파일 생성.

QA_REPORT·입력·설정·PNG는 로컬 합성 증거 폴더에 보존한다. 소스 저장소에는 자료 파일을 추가하지 않는다. `QA-macos.json`과 `BUILD-macos.json`은 전송 승인 이후 후보 artifact에 포함할 수 있다. 실제 학생자료·사용자 저장 위치는 열거나 수정하지 않았다.

## 후속 합성 키트·Mac 개발 소스 검증

후속 키트와 문서 추가는 위 Mac frozen 후보 SHA에 포함되지 않았다. 새 소스 커밋을 고정한 뒤 최종 두 플랫폼 후보를 같은 SHA로 다시 만들어야 한다.

- Python 전체: `out_test/goal-20261002-checks/python-tests-kit.log`, 224개 OK, Windows 전용 5개 skipped. 신규 키트 10개 검사 포함.
- 합성 키트: `out_test/synthetic-validation-kit-20261002-02`, 11파일. NEIS 형태 지필/문항정보/수행 XLSX, 한국어 TXT/minimal HWPX/텍스트 PDF, 서로 다른 검토안 JSON을 독립 수기 상수와 대조한 6개 검사 passed. PDF 전체 페이지 시각 확인. 실제 학생자료 입력 없음.
- 최종 native 분석 보고: `out_test/goal-20261002-analysis-qa-4/ANALYSIS_QA.json`, `source_app: true`, `frozen: false`, 13개 true, errors 0, passed.
- 실제 MainWindow 파일 선택·분석 버튼으로 학생4/문항3, 수준별 인원·정답률50%·지필 평균46.875·수행60/40 평균45.625 대조. 잘못된 합성 파일을 선택한 뒤 기존 분석 객체·값 보존.
- CSV4개·근거 XLSX를 실제 작성하고 가명별 점수·전체 학생 집합·전체 합성 식별자 부재를 읽어 확인. 옵션/저장 취소와 실명 거절 때 출력 파일 bytes 보존. 명시적으로 승인한 가짜 실명 출력은 수식 모양 이름을 CSV escape/XLSX 문자로 저장.
- 새 격리 snapshot에 학생4의 고유 해시·점수만 저장, 직접 식별자 없음. 키트 전체 입력과 manifest bytes 보존.
- 파일 선택·modal 응답은 합성 대상으로 통제했다. 실제 작성기·분석기는 mock하지 않았다. 기존 사용자 설정·포트폴리오·설치본을 사용하지 않았다.
- native `analysis-window.png` 시각 확인: 한글·학생4/문항3·100점 행·그래프 렌더링 확인. 1280×800에서 그래프 하단·학생 표 표시 높이가 작고 tight_layout 경고가 있어 작은 화면 전체 시각 합격으로 처리하지 않는다.

재실행 안내: [SYNTHETIC_VALIDATION](SYNTHETIC_VALIDATION.md). 예측–실측 보고서·NEIS XLSX·시험지 가져오기 UI·Windows Excel·설치·교사 확인은 이 13개 검사에 포함되지 않는다.

## 아직 증명하지 않은 것

동일 SHA의 Windows 후보·합동 SHA256SUMS·GitHub CI 성공, 학교 Windows OS/CPU·Excel·실제 네트워크 차단·배율/작은 화면·설치·복귀, Mac→Windows→Mac JSON 왕복, 기대값 키트의 양쪽 실제 파일 입력/내보내기/문항 가져오기, 교사의 실제 유용성 확인이 남았다. Mac 정상 사용자 환경 첫 실행·실제 설치 교체도 이번 합성 QA로 대체하지 않는다.

이 증거로 T01~T09 전체나 개발 Goal 완료를 선언하지 않는다. 새 후보 SHA/파일이 바뀌면 해당 후보로 관련 검증을 다시 한다. 다음 독립 작업은 합성 실기 키트·안내 준비이며 원격 push/CI는 사용자 승인 후 실행한다.
