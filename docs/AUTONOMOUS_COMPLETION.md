# 1.0.6 자율 개발 완료 판정

현재 상태: **검증 진행 중**. 이 문서는 실제 증거를 모으는 판정표이며 CI가 끝나기 전 완료로 표시하지 않는다.

2026-10-02 사용자 요청에 따라 자율 개발 D01~D09와 실제 학교 사용자 인수 T01~T09를 분리했다. 승인된 작업 브랜치는 `codex/desktop-candidates-1.0.6`이다. main·설치본1.0.5·원자료·가상환경·개인 설정은 보존한다.

## 후보·원격 실행

- 버전: 1.0.6.
- 현재 후보 SHA: `e63a4734c76701240e7c4c0297390c28622caaa8`.
- 후보 CI: [36949722429](https://github.com/piman-code/goedusplit/actions/runs/36949722429).
- 같은 SHA push 검사: [36949718251](https://github.com/piman-code/goedusplit/actions/runs/36949718251).
- 이전 후보9baded3에서 바뀐 것은 문서와 테스트뿐이다. `app/`, `assets/`, `run.py`, `goedusplit.spec`, `build_scripts/`, 의존성 lock, CI, 공통 사용자 안내의 Git diff가 비어 있음을 직접 확인했다. 기존 Mac source/native 분석·NEIS·시험지·작은 화면 증거는 이 동일 코드의 증거로 연결한다. frozen 후보/빌드 출처·두 OS pair는 새 SHA로 다시 검증한다.

## D01~D09 증거 지도

| 기준 | 증거와 범위 | 판정 |
| --- | --- | --- |
| D01 분석 | test_synthetic_validation_kit/test_export_privacy, Mac actual 분석 UI13개·독립 기대값·잘못된 입력 보존 | 양쪽 최종 CI 대기 |
| D02 계산 | Python expected_rates/grade_cut/neis 검사, Node43 계약, Mac NEIS/보정 native UI25개 | 양쪽 최종 CI 대기 |
| D03 저장 | Node 직렬화·Python download 계약·frozen 실제 JSON 저장/재열기/취소 업무 필드 | 양쪽 frozen QA 대기 |
| D04 내보내기 | Mac 실제 CSV4·근거/NEIS/보정 XLSX 값·시트·가명·수식문자·취소, 양 OS writer 계약 | 양쪽 최종 CI 대기 |
| D05 개인정보 | export_privacy/runtime_isolation/windows_release_audit/synthetic_qa, 전송 전 commit blob·출력 감사 | 양쪽 최종 CI·후보 대기 |
| D06 시험지 | 합성 한국어 HWPX/PDF 실제 내장 파서·Mac UI8개, mock HWP converter 성공/부재 처리 계약 | 양쪽 최종 CI 대기 |
| D07 실행 | 새 runner의 pinned 설치/개발 검사·Mac native 창2개·GitHub 새 Mac clone source QA12개 통과, frozen Qt/WebEngine·network request 차단 | 양쪽 frozen QA 대기 |
| D08 화면 | Mac offscreen WebEngine 밝음/어두움1280×800/1080×7204개·앱 배율·별도 native 접기4개·창PNG 독립 읽기 | 동일 코드 Mac 증거 확보, 최종 독립 판정 대기 |
| D09 후보·인계 | 동일 SHA 두 OS CI·MacDMG/WinZIP/setup·BUILD/QA·SHA256SUMS·다운로드 재대조·문서·완료판정관 | CI/pair/파일/판정 대기 |

상세 source/native 증거는 [검증 기록](VERIFICATION_20261002.md)을 따른다. 모듈 검사와 Mac source UI가 Windows Excel·학교 UI 전체를 검증했다는 뜻은 아니다. 필수인 양 OS frozen 실행 QA는 실제로 수행해야 한다.

Mac GitHub 새 clone은 후보e63a473과 clean 추적 소스 감사를 확인하고 실제 앱 source QA12개·오류0으로 종료했다. 한글 버튼·문항표·소수 배점·가짜 검토안을 native PNG에서 직접 읽었다. 기존 Python 환경을 빌려 사용했고 새 의존성 설치나 사용자 설정 변경은 없다. 보고서와 PNG는 로컬 `out_test/goal-20261002-github-clone-mac/`에 보존한다. 새 환경 lock 설치는 별도 두 OS CI 증거를 사용한다.

## 사용자 인수와 알려진 제약

T01~T09 전체 인수 합격은 아직 아니다. [PC 기록 양식](PC_VALIDATION_RECORD.md)에 학교 Windows의 OS/CPU·Excel·JSON실제왕복·OS오프라인/배율·교사 해석·설치/복귀 결과를 기록해야 한다. 공개 Release·main 병합·설치 교체는 별도 승인이다.

기본 전부 펼침의 작은 화면에서 그래프·학생표 높이가 부족할 수 있다. 기존 접기 버튼으로 축/제목/전체4행에 접근한 증거를 확보했으며 실제 학교 배율과 교사 시각 검토는 대기다. HWP 외부변환기는 선택 의존성이고 native HWP 성공·학교 환경은 별도 확인한다. CI의 실제 kordoc HWPX 검사는 외부변환기 부재로 건너뛰었으며, mock 변환기 계약과 실제 내장 HWPX/PDF 읽기 검사는 구분한다. 스캔 PDF OCR은 범위 밖이다. Mac ad-hoc 서명은 Apple 공증이 아니고 Windows 유료 서명은 도입하지 않았다. Intel Mac/Windows ARM은 지원 확인 전 대상에 넣지 않는다.

## 설치·배포 경계와 유지보수

[개발 안내](DEVELOPMENT.md), [릴리스 준비](RELEASE_CANDIDATES.md), [백업·복귀](BACKUP_AND_ROLLBACK.md), [인계](HANDOFF.md)를 연결한다. Actions artifact는14일 보관되므로 로컬 검증 폴더의 사본을 보존한다. 기존 README의1.0.5 파일/지문과 새1.0.6 후보를 섞지 않는다. 학생자료·설정·로그를 GitHub에 보내지 않는다.
