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

## 아직 증명하지 않은 것

동일 SHA의 Windows 후보·합동 SHA256SUMS·GitHub CI 성공, 학교 Windows OS/CPU·Excel·실제 네트워크 차단·배율/작은 화면·설치·복귀, Mac→Windows→Mac JSON 왕복, 기대값 키트의 양쪽 후보 실기 및 Windows 파일 입력/내보내기/문항 가져오기, 교사의 실제 유용성 확인이 남았다. Mac 정상 사용자 환경 첫 실행·실제 설치 교체도 이번 합성 QA로 대체하지 않는다.

이 증거로 T01~T09 전체나 개발 Goal 완료를 선언하지 않는다. 새 후보 SHA/파일이 바뀌면 해당 후보로 관련 검증을 다시 한다. 다음 독립 작업은 합성 실기 키트·안내 준비이며 원격 push/CI는 사용자 승인 후 실행한다.
