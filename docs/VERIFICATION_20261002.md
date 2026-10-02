# 검증 기록 — 최신 실행 안내

최신 후보 판정은 [AUTONOMOUS_COMPLETION](AUTONOMOUS_COMPLETION.md)과 [GOAL_STATUS](GOAL_STATUS.md)를 따른다. 아래 기록은 시간순 이력이며 처음의9baded3 후보·당시 미실행 상태는 현재 상태와 구분한다.

# 2026-10-02 현재 검증 증거

상태: **Mac 후보 빌드·격리 실행 부분 검증 / Windows CI·실기·교사 확인 대기.**

## 고정 소스와 후보

- 제품 버전: 1.0.6.
- 후보 기준 SHA: `9baded3257d10c9d0e80f0782bea15f55efd180f`.
- 로컬 브랜치: `codex/desktop-candidates-1.0.6`. 현재 기록 시점 push 미실행, 사용자 승인 질문 대기.
- Mac 후보: `Goedu-Split-1.0.6-mac.dmg`.
- Mac DMG SHA256: `3eefc2f5a73b76a34f7b73c17f15e834c2ee70b2994f2a641e045ae270598df9`.
- 소스 clean SHA·버전·Mac arm64·실행 파일 출처를 BUILD manifest로 대조했다. 기존 Mac Python 환경을 읽기 사용한 새 관리 worktree 빌드이며, 새 환경 설치 증거는 아니다.

## 직접 실행한 검사

| 검사 | 결과 | 증거 범위 |
| --- | --- | --- |
| 격리 Python 전체 | 224개 OK, 5개 Windows 전용 건너뜀 | 코드와 합성 입력. Windows cmd/junction 실제 검사 대기 |
| 계산기 JS 계약 | 43개 통과 | 소수·0/100·저장·반올림·검증 계약 |
| 소스 감사·preflight·pip check | 새 후보 worktree 통과 | 실제 원본 checkout의 비추적 .DS_Store는 보존하며 새 checkout에 포함 안 함 |
| PyInstaller Mac 앱 | 성공 | 새 고정 SHA에서 생성, QtTest·unittest.mock 포함 확인은 아래 실제 실행으로 확보 |
| QtWebEngine 필수 구성·보정 | 통과 | process·resources 존재, 잘못된 위치 보정 전 파일 보존 |
| 개인정보 번들 감사 | 통과 | 한정 패턴 검사와 파일 구성. 모든 개인정보가 없다는 일반 보증 아님 |
| ad-hoc codesign 검증 | 통과 | Apple Developer ID·공증 증거 아님 |
| DMG 만들기·hdiutil verify | 통과 | 실제 새 DMG 파일의 내부 checksum 유효 |
| frozen 후보 합성 QA | `passed`, `frozen: true`, 필수 12개 true, errors 0 | Mac 실행 파일 자체의 실제 Qt·WebEngine·다운로드 흐름 |
| 실제 DMG에서 앱 실행 | 읽기 전용으로 마운트한 앱의 frozen QA 12개 passed | 안내서·실행 파일 지문이 manifest와 일치, 실행 후 마운트 해제. Applications 설치 교체 아님 |
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

키트 생성기·native 분석 harness·안내가 포함된 `9baded3`를 후보 소스로 고정했다. 이 문서의 후속 검증 기록 변경만으로 후보 소스를 바꾸지 않는다. Windows CI도 명시적으로 같은 `9baded3`를 checkout하여 최종 두 플랫폼 파일을 대조한다.

- Python 전체: `out_test/goal-20261002-checks/python-tests-kit.log`, 224개 OK, Windows 전용 5개 skipped. 신규 키트 10개 검사 포함.
- 합성 키트: `out_test/synthetic-validation-kit-20261002-02`, 11파일. NEIS 형태 지필/문항정보/수행 XLSX, 한국어 TXT/minimal HWPX/텍스트 PDF, 서로 다른 검토안 JSON을 독립 수기 상수와 대조한 6개 검사 passed. PDF 전체 페이지 시각 확인. 실제 학생자료 입력 없음.
- 최종 native 분석 보고: `out_test/goal-20261002-analysis-qa-4/ANALYSIS_QA.json`, `source_app: true`, `frozen: false`, 13개 true, errors 0, passed.
- 실제 MainWindow 파일 선택·분석 버튼으로 학생4/문항3, 수준별 인원·정답률50%·지필 평균46.875·수행60/40 평균45.625 대조. 잘못된 합성 파일을 선택한 뒤 기존 분석 객체·값 보존.
- CSV4개·근거 XLSX를 실제 작성하고 가명별 점수·전체 학생 집합·전체 합성 식별자 부재를 읽어 확인. 옵션/저장 취소와 실명 거절 때 출력 파일 bytes 보존. 명시적으로 승인한 가짜 실명 출력은 수식 모양 이름을 CSV escape/XLSX 문자로 저장.
- 새 격리 snapshot에 학생4의 고유 해시·점수만 저장, 직접 식별자 없음. 키트 전체 입력과 manifest bytes 보존.
- 파일 선택·modal 응답은 합성 대상으로 통제했다. 실제 작성기·분석기는 mock하지 않았다. 기존 사용자 설정·포트폴리오·설치본을 사용하지 않았다.
- native `analysis-window.png` 시각 확인: 한글·학생4/문항3·100점 행·그래프 렌더링 확인. 1280×800에서 그래프 하단·학생 표 표시 높이가 작고 tight_layout 경고가 있어 작은 화면 전체 시각 합격으로 처리하지 않는다.

재실행 안내: [SYNTHETIC_VALIDATION](SYNTHETIC_VALIDATION.md). 예측–실측 보고서·NEIS XLSX·시험지 가져오기 UI·Windows Excel·설치·교사 확인은 이 13개 검사에 포함되지 않는다.

## 시험지 가져오기·작은 화면 추가 소스 검증

후보 소스 `9baded3`의 Mac 개발 실행에서 합성 HWPX·텍스트 PDF를 실제 자료 메뉴와 확인/취소 버튼으로 처리했다. 미리보기 번호·유형·37.5/37.5/25점과 실제 WebEngine 작업 반영, 미리보기·파일 선택 취소 시 이전 작업 유지, 텍스트 없는 합성 빈 PDF 실패 안내와 작업 보존을 포함한 8개 검사가 passed다. 증거는 `out_test/goal-20261002-paper-ui/PAPER_UI_QA.json`과 PNG/harness/SOURCE_RECORD다. 빈 PDF는 스캔 시험지의 성공 검증이 아니며 HWP 바이너리·한글 앱 편집 호환성도 미검증이다.

1280×800에서 기존 요약·표 읽는 법·학생 표를 접으면 그래프 제목·축이 전부 보이고, 그래프를 접으면 학생4행이 전부 보이는 것을 실제 창과 픽셀 범위로 확인했다. `out_test/goal-20261002-fold-layout/LAYOUT_WORKAROUND_QA.json`의 4개 검사와 두 PNG를 보존했다. 제품 화면/지속 설정 변경 없이 기존 접기 버튼을 쓴 우회 방법이다. 기본 전부 펼침의 높이 제약·다른 배율·학교 PC·교사 확인은 별도로 남긴다.

## NEIS·예측–실측 저장 추가 소스 검증

`9baded3`의 실제 Mac 개발 창·WebEngine·자료 메뉴·modal 저장 버튼으로 25개 검사 passed, errors 0을 확보했다. 증거는 `out_test/goal-20261002-neis-calibration-new/NEIS_CALIBRATION_QA.json`과 `INDEPENDENT_READBACK_FINAL.json`, XLSX·PNG·임시 harness다.

- NEIS 엑셀 3개 시트에서 배점1.5/3.25·총점4.75·원값과 5% 반올림100/75/60/35/10을 수기 상수와 대조했다.
- 보정은 다른 배점의 계산기 예제를 재사용하지 않고 동일 시험37.5/37.5/25의 별도 합성 예측을 실제 WebEngine에 넣었다. 엑셀2개 시트의 문항3개·예측/적용/실측 분할점수·경계 학생 정답률·상대차를 독립 수기 기대값과 대조했다.
- 실제 두 저장 버튼에서 취소 시 기존 엑셀 bytes 유지, 합성 키트 전체 manifest 지문과 제품 소스6개 지문 보존, 직접 합성 식별자 제외를 확인했다.
- 완료판정관이 저장 파일·해시와 PNG2장을 직접 읽어 재검증했다. 당시 부모의 동시 변경은 이 검증 기록 문서뿐이다.

이 결과는 source_app이며 frozen 후보의 해당 추가 기능·Windows Excel·실제 NEIS 업로드·교사 확인을 대체하지 않는다. 실제 NEIS에 합성 값을 업로드하지 않았다.

## 이전 후보 이력

`07ea42c2fc8e750be407aa1228a51a5a715e8b64`의 frozen Mac QA와 DMG도 통과했으며 원본을 보존했다. 해당 DMG SHA256은 `702b64b657c9537069b18dbe4635634f235a03117020df7e48283d8cbf1a304f`다. 현재 선택한 후보 소스는 위 `9baded3`이며 이전 파일을 새 SHA 후보로 재표시하지 않는다.

## Windows 인계 ZIP·실기 기록 준비

후보 소스 `9baded3`의 허용된 Git blob만 담은 `Goedu-Split-1.0.6-source.zip`을 새 후보 worktree의 dist에 생성했다. 파일118개·ZIP 파일 집합과 manifest·모든 파일 지문·Gitless source identity·압축 해제 후 개인정보 소스 감사가 통과했다. ZIP SHA256은 `9a65b5bffd3c5a237153ca6592d48fdfe9754f6c573cd6fe1fca19d3f63b0f37`, 증거는 `out_test/goal-20261002-windows-handoff/SOURCE_KIT_QA.json`이다. 기존 후보/설치/원자료를 덮어쓰거나 외부 폴더로 복사·전송하지 않았다. 이 ZIP은 코드 인계 자료이며 Windows 앱 빌드/실행 성공은 아니다. 기본 개발 방식은 GitHub의 별도 clone이다.

[PC 실기 기록 양식](PC_VALIDATION_RECORD.md)은 T01~T09·실제 JSON 왕복·교사 질문·설치/복귀 항목을 모두 미실행/확인 대기로 둔다. [백업·복귀 안내](BACKUP_AND_ROLLBACK.md)는 현재 소스와 시작1.0.5의 동일 설정 키/저장 루트, Mac QSettings fileName 메타데이터 및 Qt/Microsoft 공식 규칙을 대조해 작성했다. 실제 사용자 설정 값·학생자료는 열지 않았고 백업·레지스트리 내보내기·복원·설치 교체도 실행하지 않았다. Windows 실제 경로/키 존재와 실제 양쪽 복귀는 실기 확인 대상이다.

## 아직 증명하지 않은 것

동일 SHA의 Windows 후보·합동 SHA256SUMS·GitHub CI 성공, 학교 Windows OS/CPU·Excel·실제 네트워크 차단·배율/작은 화면·설치·복귀, Mac→Windows→Mac JSON 왕복, 기대값 키트의 양쪽 후보 실기 및 Windows 파일 입력/내보내기/문항 가져오기, 교사의 실제 유용성 확인이 남았다. Mac 정상 사용자 환경 첫 실행·실제 설치 교체도 이번 합성 QA로 대체하지 않는다.

이 증거로 T01~T09 전체나 개발 Goal 완료를 선언하지 않는다. 새 후보 SHA/파일이 바뀌면 해당 후보로 관련 검증을 다시 한다. 다음 독립 작업은 합성 실기 키트·안내 준비이며 원격 push/CI는 사용자 승인 후 실행한다.


## 승인 후 최초 두 OS CI와 Windows 검사 수정

2026-10-02 사용자 승인으로 새 브랜치를 push하고 [후보 CI 36948926765](https://github.com/piman-code/goedusplit/actions/runs/36948926765)를 실행했다. workflow HEAD32f6702, 실제 checkout 후보9baded3/1.0.6이다. Mac job은 preflight·pip check·소스 감사·전체 검사·빌드·DMG·frozen QA·manifest/artifact까지 성공했다. Windows는 224검사 중 오류2·실패1·건너뜀9로 중단했다. pair는 건너뛰었으며 이 실행을 양쪽 후보 성공으로 표시하지 않는다.

Windows 오류는 UTF-8 한글 bat/validation JSON을 기본cp1252로 읽는 테스트 두 곳, 실패는 Mac 포장 스크립트 검사에 Windows Bash를 사용한 부분이었다. 구축관은 테스트 두 파일에서 UTF-8 읽기3곳을 명시하고 Mac 빌드·포장 integration2개를 해당 Mac에서만 실행하도록 수정했다. 전역 UTF-8 강제·제품 코드·계산/저장/보안 정책 변경은 없다. Mac에서 관련21개 검사 OK(실제 Windows junction1개만 건너뜀), 기본cp1252를 재현한 파일 읽기3개도 통과했다. Mac 전용 검사2개는 실제 Mac에서 실행·통과했다. 수정 커밋으로 양쪽 후보 CI를 다시 실행해야 한다.

이번 사용자는 자율 개발 중심으로 Goal을 변경했다. 최신 판정 기준은 DEVELOPMENT_PLAN의 D01~D09다. 기존 T01~T09는 별도 학교 사용자 인수이며 미실행 상태를 보존한다.


## 두 번째 CI — Windows 앱 빌드 성공·portable 포장 오류

[CI36949722429](https://github.com/piman-code/goedusplit/actions/runs/36949722429)의 checkout은e63a473/1.0.6이다. Mac job 전체는 성공했다. Windows 새 환경은 Python224개 OK/skip11, Node43개 통과, build_windows.bat 안의 재검사, PyInstaller, 경량화, 개인정보 감사, 실행 파일 build_identity까지 성공했다. portable 포장의 inline Python `for /f` 버전 조회에서 CMD 구문 오류255가 나서 frozen QA·setup·manifest·pair는 미실행이다. 성공한 Mac과 실패한 Windows를 합쳐 최종 pair로 소개하지 않는다.

Windows skip11은 Mac/Finder 전용3·POSIX source-kit7·선택 real kordoc1이다. Windows cmd 보존/실패중단과 실제 junction2개는 수행했다. Mac skip6은 Windows 전용5·선택 real kordoc1이며 내장 HWPX/PDF 실제 읽기와 mock HWP 변환기 계약은 양쪽에서 별도로 수행했다. native 외부 HWP 성공은 아직 인수 대기다.

또한 같은e63a473을 GitHub에서 실제 새 Mac clone으로 받아 repository 소스 감사와 실제 앱 source QA12개/errors0을 확인했다. report/PNG/로그는 `out_test/goal-20261002-github-clone-mac/`에 보존했다. 기존 Python 환경을 빌려 사용하고 새 설치/설정변경은 하지 않았다. 이는 frozen 후보나 Windows 학교 사용 결과가 아니다.


포장 수정: `build_scripts/read_app_version.py`가 UI 없이 app 버전을 읽고 canonical 숫자3부 버전만 stdout에 출력한다. 두 packbat는 이 도구를 호출해 inline Python 괄호/인용구를 제거했다. helper stdlib(-S)/정확버전/부정확버전, sourcekit helper포함, 필요한 helper 존재, 가이드/원본 출력 보존의 Mac 관련22개 검사 OK(Windows CMD2개만 미적용). Windows 회귀 검사는 공백 저장소/공백 Python 경로, 버전 조회 뒤 identity guard 도달, invalid/missing helper 조기 중단, 기존 ZIP/setup 보존과 정확한 파일명 출력까지 확인하도록 보강했다. 실제 Windows CI 결과는 후속에서 확인한다.


## 세 번째 CI: 양쪽 후보 성공·안내 파일 pair 중단

후보 `1866f4e2e288ac0763a3291d32ecb492419daa91`의 [CI36951043652](https://github.com/piman-code/goedusplit/actions/runs/36951043652)에서 Mac arm64·Windows x64 작업은 모두 성공했다. Python226개(Mac7/Windows11개 플랫폼 전용 또는 선택 kordoc 건너뜀), Node43개와 빌드 전 재검사, PyInstaller·출처/개인정보 검사·포장·실제 frozen QA·명세·artifact 업로드가 통과했다. Windows CMD 공백 Python 경로·버전 오류·기존 파일 보존 회귀는 실제 Windows에서 실행했다. Inno Setup6.7.1로 설치 EXE를 생성했으며 실제 학교 설치 성공이라는 뜻은 아니다.

최종 pair 작업110666231824는 각 플랫폼 출처·파일 해시·frozen QA 검증을 거친 후 `The two candidates contain different user guides`로 실패했다. 동일성 검사를 완화하지 않고 원인 수정 뒤 새 SHA의 두 플랫폼을 다시 검증한다. 양쪽 실행·pair 로그는 `out_test/goal-20261002-ci-36951043652/`에 보존한다. 전체 CI를 통합 성공으로 기록하지 않는다.


수정 후 검증: `.gitattributes`는 `distribution/USER_GUIDE.md text eol=lf` 한 파일만 고정한다. 실제 Git scratch checkout에서 정책 부재의 autocrlf=true/false는 CRLF/LF로 달라지는 것을 재현했고 새 정책에서는 같은 LF bytes를 확인했다. 개별 manifest hash가 유효해도 안내 줄바꿈이 다르면 pair는 여전히 실패한다. source kit의 파일·출처 허용목록에는 `.gitattributes`만 추가했다. Mac 관련24개 검사 OK(Windows CMD2개만 건너뜀). 안내문 내용·제품 UI·계산·학생자료 접근·개인 설정은 바꾸지 않았다. 새 커밋으로 양쪽을 다시 빌드한다.


## 최종 안내 줄바꿈 수정 후보

실제 다운로드한1866 안내는 Mac16156bytes/LF139, Windows16295bytes/CRLF139였다. Windows의CRLF를LF로 바꾸면 Mac·Git blob과 bytes가 정확히 같고 각 원본 hash는 해당 BUILD와 일치했다. 원인 확인 기록은 `out_test/goal-20261002-ci-36951043652/GUIDE_READBACK.json`이다. 원본 파일은 보존했다.

새 후보 `a7f7d95b6a751606ac75d1f6958ed9686bd9884b`는 독립24개 검사(WinCMD2개 미적용)·clean123추적 파일·13새 blob 감사·문서 링크38개 확인을 통과했다. 보고서는 `out_test/goal-20261002-approved-push-a7f7d95/`다. 승인된 새 브랜치에 push한 후 [후보 CI36952967141](https://github.com/piman-code/goedusplit/actions/runs/36952967141)와 [push 검사36952966860](https://github.com/piman-code/goedusplit/actions/runs/36952966860)를 실행했다. 결과·최종 체크섬은 아직 대기다.


GitHub 새 복제본의 a7 소스 인계 키트123파일·모든 path/hash·LF 속성·버전 helper 포함·압축 해제 소스 감사·Gitless clean identity가 통과했다. 소스 ZIP SHA256은 `9b73d6768cd4cf1b9a4e26e0403558eb4e6c46f765710accbf491cfef7557db7`이며 `out_test/goal-20261002-windows-source-kit-a7/`에 보고서와 함께 보존했다. 이 ZIP의 실행 파일은 없고 실제 Windows 실행 검증을 대신하지 않는다.

GitHub 최신 공개 Release의 읽기 전용 메타데이터는2026-10-02 `v1.0.5`, 게시 시각2026-09-25T15:22:56Z였으며3개 기존 배포 파일명·GitHub SHA256 digest가 README의1.0.5 값과 일치했다. 1.0.6 Release는 생성하지 않았다. 최신 메타데이터 대조이며1.0.5 파일을 새로 설치하거나 다운로드·실행한 증거는 아니다.


## 최종 동일 SHA CI 통합 성공

[a7 후보 CI36952967141](https://github.com/piman-code/goedusplit/actions/runs/36952967141)의 source·Mac arm64·Windows x64·pair가 모두 success로 종료했다. 같은 SHA의 push 검사36952966860도 success다. 양쪽 Python228개 OK(Mac7/Windows11개 플랫폼 전용·선택 kordoc 건너뜀), Node43개와 빌드 내 재검사도 통과했다. Windows에서 LF 체크아웃 회귀·안내 불일치 거부·공백 Python CMD·기존 파일 보존을 실제 실행했다. 두 frozen 후보12개 QA·오류0, PyInstaller·출처/개인정보 감사·DMG/ZIP/setup·BUILD/QA 수집·pair가 성공했다.

최종 pair artifact ID는11204209837, 이름은 `desktop-candidates-1.0.6-a7f7d95b6a751606ac75d1f6958ed9686bd9884b`다. GitHub outer artifact ZIP digest는 `85d3790db44081d0ed1baedc7b3f3fb1a252838e7ca59349b82834ea169a4eb0`이고 실제 배포 DMG·ZIP·EXE의 지문과는 별개다. `artifacts/Goedu-Split-1.0.6-a7f7d95/`로 다운로드 중이며 실제 파일 재대조·Mac DMG 내부 native 실행·독립 D완료 판정은 후속 기록으로 확정한다. 원격 상태·artifact 메타데이터·양쪽 실행·pair 로그는 `out_test/goal-20261002-ci-36952967141/`에 보존한다.


## 최종 내려받은 후보 지문·Mac DMG 실제 실행

최종10개 파일을 `artifacts/Goedu-Split-1.0.6-a7f7d95/`에 보존했다. SHA256SUMS에 있는9개 파일의 실제 SHA256이 모두 일치하고, 두 사용자 안내는 Git 원본과 정확히 같은 LF bytes다. 양 BUILD의 버전1.0.6·전체a7 SHA·clean·OS/아키텍처·실행 파일 지문과 두 frozen QA의12개 true/errors0을 대조했다. 기록은 `out_test/goal-20261002-final-a7/CHECKSUM_READBACK.json`이다.

| 실제 파일 | SHA256 |
| --- | --- |
| Goedu-Split-1.0.6-mac.dmg | 2c9895bfb250ede8d072be2739cc76587a5aa981de1a9ae401040c230d094cf4 |
| Goedu-Split-1.0.6-windows.zip | 446a5478fef905f60dee2e83269394c7a2f27f80e9feed7d8fdfad9057563069 |
| Goedu-Split-1.0.6-windows-setup.exe | 8965b9e7116d7868bed3f39096524e0320578a12ffe168851066795063adfdc6 |

실제 받은 DMG의 hdiutil verify와 읽기 전용 mount, 내부 plist1.0.6·BUILD_SOURCE와 BUILD 동일·arm64 lipo·deep/strict codesign·실행 파일 hash를 확인했다. 내부 앱을 기존 설치로 복사하지 않고 직접 `--synthetic-qa` 실행해 frozen12개/errors0/exit0을 확보했다. QA 실행 파일 hash는 CI의 Mac QA/BUILD와 같다. native PNG에서1.0.6·한글 버튼·문항1.5/3.25·합성 검토안·직접 소수 정답률을 시각 확인했고 DMG를 정상 분리했다. 보고서·로그·PNG는 `out_test/goal-20261002-final-a7/MAC_DOWNLOAD_READBACK.json`과 `downloaded-mac-native-qa/`에 보존한다. Mac 공증·설치 교체·학교/교사 인수는 이 증거의 범위가 아니다.

최종 보존 readback은 설치 앱·원래dist1.0.5, 원래가상환경 존재, stash2개 refs 동일, main SHA71d9b33 유지였다. 설정 값·실제 학생자료·stash 내용은 열지 않았다. `out_test/goal-20261002-final-a7/PRESERVATION_FINAL.json`과 `REMOTE_SOURCE_READBACK.txt`를 따른다.


최종 Windows 다운로드 ZIP은3234개 항목 전체 CRC·중복/안전 경로·symlink 부재, 필수 Qt/WebEngine/웹/폰트15개·비어 있지 않음, 실제 EXE AMD64 PE와 지문·내장 BUILD_SOURCE를 독립 재대조했다. 실행 파일 SHA256은 `ca46662ff46611a8dc7716d356a102eb12acb7a240453f8bcac5ec398c22b965`로 CI QA/BUILD와 같다. setup EXE의 PE는 Inno 엔진 x86이며 앱 payload는AMD64다. 설치 파일 실제 실행은 하지 않았다. 내부/외부 안내16156bytes/LF139/CRLF0은 Git a7와 정확히 같고, app/assets27개 추적 자산은21개 byte-exact·6개 웹 텍스트의 Git Windows CRLF 변환만 있었다. 새 합성 검사와 Node 계약은 실제 Windows 체크아웃에서 실행/통과했다.

보고서는 `out_test/goal-20261002-final-a7/WINDOWS_DOWNLOAD_READBACK.json`과 `WINDOWS_SOURCE_ASSETS_READBACK.json`이다. 원본 Windows5파일을 별도 검사 폴더에 hardlink해 읽기만 했고 원본 bytes·설치·압축 해제·로컬 Windows 실행·사용자 설정을 바꾸지 않았다. Windows 실제 frozen 실행은 별도 CI의 증거이며 학교 Windows/Excel/설치 인수와 구분한다.


## 독립 자율 개발 완료 판정

완료판정관이 원본10개 파일·9개 체크섬을 직접 계산하고 BUILD·정확12개 QA 이름·실행 파일 지문·canonical LF 안내·Windows ZIP의 AMD64/내장 출처/27자산, Mac DMG native12개·PNG·분리 로그를 직접 읽었다. 동일 앱 코드의 기존 source/native 증거까지 연결하여 D01~D09 모두 충족, 치명 문제0으로 판정했다. 보고서 `out_test/goal-20261002-final-a7/INDEPENDENT_COMPLETION.json` SHA256은 `7ab1b358d4c3f517ad5be106d18810441b726fc489c84ea0e01730271f4a1b4e`이며 실물 대조는 `INDEPENDENT_ARTIFACT_READBACK.json`에 보존한다.

현재 완료 범위는 사용자의2026-10-02 명시 변경에 따른 **자율 개발 완료 / 사용자 인수 대기 / 공개 배포 미실행**이다. 문서 기록 커밋은 앱 후보 소스a7와 분리하고, 전송 직전 독립 감사를 마친 뒤 승인된 같은 브랜치에 push한다. 실제 학교 T01~T09와 Release·main 병합·설치/복귀는 실행하지 않았다.
