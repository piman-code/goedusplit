# 1.0.6 자율 개발 검증과 완료 판정

현재 상태: **자율 개발 완료 / 사용자 인수 대기 / 공개 배포 미실행**. 같은 SHA의 양 OS·pair 성공, 내려받은 실제 파일 재대조, Mac native 재실행과 독립 판정으로 D01~D09 개발 증거가 모두 충족됐다. 최종 문서 커밋·전송 감사·원격 반영은 별도 실행 기록으로 확인하며 이 문서는 Goal 도구 상태를 변경하지 않는다.

2026-10-02 사용자 요청에 따라 자율 개발 D01~D09와 실제 학교 사용자 인수 T01~T09를 분리했다. 승인된 작업 브랜치는 `codex/desktop-candidates-1.0.6`이다. main·설치본1.0.5·원자료·가상환경·개인 설정은 보존한다.

## 후보·원격 실행

- 버전: 1.0.6.
- 현재 후보 SHA: `a7f7d95b6a751606ac75d1f6958ed9686bd9884b`. 같은 SHA의 통합 CI·내려받은 9개 지문·후보 내부 구성·Mac 실제 재실행과 독립 최종 판정을 완료했다. 문서만 바꾸는 후속 커밋은 이 후보의 빌드 SHA를 바꾸지 않는다.
- 후보 CI: [36952967141](https://github.com/piman-code/goedusplit/actions/runs/36952967141)와 같은 SHA의 [push 검사 36952966860](https://github.com/piman-code/goedusplit/actions/runs/36952966860)가 성공했다. Mac arm64·Windows x64와 pair가 모두 성공했으며 [pair artifact 11204209837](https://github.com/piman-code/goedusplit/actions/runs/36952967141/artifacts/11204209837)를 생성했다. 내려받은 체크섬·내부 구성과 Mac DMG의 native frozen 재실행을 통과했고 독립 검토가 D01~D09 모두 충족·critical 발견0으로 판정했다.
- 새 실행의 Python은 양쪽 228개 실행으로 OK이며 Mac 7개·Windows 11개가 건너뛰어졌다. Node는 양쪽 43개 통과했고 빌드 단계 재검사도 같은 수로 통과했다. 양 OS frozen QA 필수 12개가 통과했다. 플랫폼 전용 검사와 선택 kordoc 부재의 건너뛰기는 실행 통과로 세지 않는다.
- 이전 `1866f4e`의 [CI 36951043652](https://github.com/piman-code/goedusplit/actions/runs/36951043652)는 Mac arm64·Windows x64 검사·빌드·포장·frozen QA를 통과했으나 **pair가 실패해 전체 실행은 실패**했다. artifact의 사용자 안내 실제 bytes를 비교해 Windows CRLF와 Mac LF만 달랐음을 확인했다. `.gitattributes`와 소스 키트의 Git blob 처리 보완을 새 후보에 포함했다. 이전 파일을 정규화해 새 실행의 통합 성공으로 바꾸지 않는다.
- 이전 `1866f4e` 실행의 Python은 양쪽 226개 실행으로 OK이며 Mac 7개·Windows 11개가 건너뛰어졌다. Node는 양쪽 43개 통과했다. 이는 과거 실행 수이며 새 후보의 결과를 예상하여 채우지 않는다. 플랫폼 전용 검사와 선택 kordoc 부재를 구분하며 건너뛰기를 실행 통과로 세지 않는다.
- 이전 후보 `9baded3`에서 `a7f7d95`까지 `app/`, `assets/`, `run.py`, `goedusplit.spec`, 의존성 lock, CI, 공통 사용자 안내의 Git diff가 비어 있음을 직접 확인했다. **`.gitattributes`, Windows 포장·버전 helper·build identity·소스 키트 처리 등 `build_scripts/`는 변경됐다.** 기존 Mac source/native 분석·NEIS·시험지·작은 화면 증거는 동일한 앱 코드의 증거로 연결한다. 변경된 포장·빌드 출처·frozen 후보·pair는 새 SHA로 다시 검증한다. 후속 SHA에서도 이 비교를 다시 확인한다.
- 후보 파일 SHA256과 내부 구성은 아래 실물 대조값으로 확정했다. 내려받은 Mac DMG를 읽기 전용 마운트해 native frozen QA12개를 다시 통과했다. 독립 완료 판정도 통과했다. 앞선 실행과 로컬 후보의 지문을 새 후보 지문으로 재사용하지 않는다.

## D01~D09 증거 지도

| 기준 | 증거와 범위 | 판정 |
| --- | --- | --- |
| D01 분석 | 양 OS 합성 파일 읽기·독립 분석 기대값·오류 뒤 보존 검사, Mac 실제 분석 UI13개 | 충족 — 독립 판정 PASS |
| D02 계산 | 양 OS expected_rates/grade_cut/neis 검사·Node43 계약, Mac NEIS/보정 native UI25개 | 충족 — 독립 판정 PASS |
| D03 저장 | 양 OS 직렬화·download 계약·frozen 실제 JSON 저장/재열기/취소와 업무 필드 보존 | 충족 — 독립 판정 PASS |
| D04 내보내기 | 양 OS writer의 파일·시트·수치·한글·취소·수식 보호 검사, Mac 실제 CSV4·근거/NEIS/보정 XLSX | 충족 — 독립 판정 PASS |
| D05 개인정보 | 양 OS 가명·실명 확인/취소·해시·설정/데이터 격리, 전송 전 commit blob 및 후보 구성 감사 | 충족 — 독립 판정 PASS |
| D06 시험지 | 양 OS 합성 HWPX/PDF 실제 내장 읽기와 기대값, Mac UI8개, mock HWP converter 성공/부재·읽기 실패 보존 | 충족 — 독립 판정 PASS; 실제 kordoc·학교 환경은 별도 |
| D07 실행 | 양 OS 새 runner의 lock 설치·개발 검사·frozen Qt/WebEngine 및 요청 차단 QA, Mac native 창2개·GitHub 새 clone source QA12개 | 충족 — 독립 판정 PASS; 학교 실행은 별도 |
| D08 화면 | Mac offscreen WebEngine 밝음/어두움1280×800/1080×7204개·앱 배율·별도 native 접기4개·창PNG 독립 읽기 | 충족 — 독립 판정 PASS; 작은 화면 제약 공개 |
| D09 후보·인계 | 동일 SHA 양 OS·pair 성공, MacDMG/WinZIP/setup·BUILD/QA·SHA256SUMS 실제 수집·재대조, 최신 안내·완료판정관 | 충족 — 독립 판정 PASS |

상세 source/native 증거는 [검증 기록](VERIFICATION_20261002.md)을 따른다. 모듈 검사와 Mac source UI가 Windows Excel·학교 UI 전체를 검증했다는 뜻은 아니다. 필수인 양 OS frozen 실행 QA는 실제 수행해 통과했다.

판정 근거는 [로컬 독립 완료 보고서](../out_test/goal-20261002-final-a7/INDEPENDENT_COMPLETION.json)다. 보고서를 직접 재읽고 SHA256 `7ab1b358d4c3f517ad5be106d18810441b726fc489c84ea0e01730271f4a1b4e`를 재계산했다. 보고서는 로컬에 보존하며 Git 전송 대상에서 제외한다. 독립 판정의 범위는 자율 개발 증거이며 학교 인수·공개 배포·설치 교체는 포함하지 않는다.

Mac GitHub 새 clone은 `e63a473`과 clean 추적 소스 감사를 확인하고 실제 앱 source QA12개·오류0으로 종료했다. 한글 버튼·문항표·소수 배점·합성 검토안을 native PNG에서 직접 읽었다. 기존 Python 환경을 빌려 사용했고 새 의존성 설치나 사용자 설정 변경은 없다. 보고서와 PNG는 로컬 `out_test/goal-20261002-github-clone-mac/`에 보존한다. 이는 동일 앱 코드의 source/native 증거이며 다른 SHA의 빌드·포장 성공을 증명하지 않는다. 새 환경 lock 설치는 별도 두 OS CI 증거를 사용한다.

`a7f7d95` 소스 키트는 123파일의 manifest·각 지문·압축 해제 감사와 Gitless identity를 통과했다. ZIP SHA256은 `9b73d6768cd4cf1b9a4e26e0403558eb4e6c46f765710accbf491cfef7557db7`이며 `out_test/goal-20261002-windows-source-kit-a7/SOURCE_KIT_QA.json`이 LF 규칙·버전 helper 포함을 확인한다. 소스 키트 자체를 native Windows에서 실행한 검사는 아니며 앱 설치 파일·pair의 대체물이 아니다. 이전 1866 키트도 이력으로 보존한다.

CI 근거는 [실행 기록](https://github.com/piman-code/goedusplit/actions/runs/36952967141)과 로컬 `out_test/goal-20261002-ci-36952967141/`에 연결한다. 이전 pair 실패 근거는 `out_test/goal-20261002-ci-36951043652/`에 보존한다. Windows frozen QA는 Windows Server runner의 offscreen Qt 실행이며 학교 Windows·Excel·사용자 설치 검증이 아니다. Mac native 실행과 DMG 내부 실행은 기존 설치 앱을 교체하지 않은 증거다. Windows portable·setup 생성 성공도 실제 설치 성공을 뜻하지 않는다.

## 최종 후보 지문 기입표

`a7f7d95`의 pair artifact를 내려받아 SHA256SUMS의 9개 파일 지문을 실제 bytes로 다시 계산했다. BUILD 두 개는 같은 SHA·버전1.0.6, Mac arm64/Windows AMD64를 기록하고 QA 두 개는 frozen true·passed·필수12개를 기록한다. 두 안내문은 서로 및 Git 소스와 bytes가 일치한다. 증거는 `out_test/goal-20261002-final-a7/CHECKSUM_READBACK.json`이며 파일은 `artifacts/Goedu-Split-1.0.6-a7f7d95/`에 보존한다.

같은 증거 폴더의 `MAC_DOWNLOAD_READBACK.json`은 읽기 전용 DMG 내부 앱의 arm64·ad-hoc 서명·identity/실행 파일 지문·native frozen QA12개·마운트 해제를 확인한다. `WINDOWS_DOWNLOAD_READBACK.json`은 ZIP3234개 항목 CRC·필수 runtime15개·AMD64 실행 파일·embedded identity/지문·LF 안내문을 확인한다. `WINDOWS_SOURCE_ASSETS_READBACK.json`은 web/font/icon27개를 Git 후보와 대조했다. binary는 지문 일치, 일부 텍스트는 Windows CRLF checkout과 같은 내용임을 별도로 기록한다. 이 Mac에서 Windows 실행 파일이나 installer를 실행한 증거는 아니며 학교·Excel·설치 인수는 대기다.

| 확인 대상 | 최종 값·판정 |
| --- | --- |
| 후보 전체 SHA | a7f7d95b6a751606ac75d1f6958ed9686bd9884b — 양 OS·pair·내려받은 지문 대조 성공 |
| 양 OS·pair 성공 CI와 artifact | 36952967141 성공 / pair artifact11204209837 — 내려받은 9파일 지문 대조 통과 |
| Mac DMG SHA256 | 2c9895bfb250ede8d072be2739cc76587a5aa981de1a9ae401040c230d094cf4 |
| Windows portable ZIP SHA256 | 446a5478fef905f60dee2e83269394c7a2f27f80e9feed7d8fdfad9057563069 |
| Windows setup EXE SHA256 | 8965b9e7116d7868bed3f39096524e0320578a12ffe168851066795063adfdc6 |
| BUILD·QA·두 사용자 안내·SHA256SUMS 재대조 | 두 BUILD의 동일 SHA/버전·arm64/AMD64, 두 frozen QA12개 passed, 양 안내 bytes 및 9개 지문 일치 |
| 내려받은 후보 내부 파일·Mac 실행 재확인 | Mac DMG native frozen12개·서명·arm64·실행 지문 확인, Windows ZIP CRC3234·runtime15·AMD64·identity·web/font/icon27개 대조 통과 |
| 독립 D01~D09 완료 판정 | 모두 충족·critical 발견0; 보고서 SHA2567ab1b358d4c3f517ad5be106d18810441b726fc489c84ea0e01730271f4a1b4e |

## 사용자 인수와 알려진 제약

T01~T09 전체 인수 합격은 아직 아니다. [PC 기록 양식](PC_VALIDATION_RECORD.md)에 학교 Windows의 OS/CPU·Excel·JSON실제왕복·OS오프라인/배율·교사 해석·설치/복귀 결과를 기록해야 한다. 공개 Release·main 병합·설치 교체는 별도 승인이다.

기본 전부 펼침의 작은 화면에서 그래프·학생표 높이가 부족할 수 있다. 기존 접기 버튼으로 축/제목/전체4행에 접근한 증거를 확보했으며 실제 학교 배율과 교사 시각 검토는 대기다. HWP 외부변환기는 선택 의존성이고 native HWP 성공·학교 환경은 별도 확인한다. CI의 실제 kordoc HWPX 검사는 외부변환기 부재로 건너뛰었으며, mock 변환기 계약과 실제 내장 HWPX/PDF 읽기 검사는 구분한다. 스캔 PDF OCR은 범위 밖이다. Mac ad-hoc 서명은 Apple 공증이 아니고 Windows 유료 서명은 도입하지 않았다. Intel Mac/Windows ARM은 지원 확인 전 대상에 넣지 않는다.

## 설치·배포 경계와 유지보수

[개발 안내](DEVELOPMENT.md), [릴리스 준비](RELEASE_CANDIDATES.md), [백업·복귀](BACKUP_AND_ROLLBACK.md), [인계](HANDOFF.md)를 연결한다. Actions artifact는14일 보관되므로 로컬 검증 폴더의 사본을 보존한다. 기존 README의1.0.5 파일/지문과 새1.0.6 후보를 섞지 않는다. 학생자료·설정·로그를 GitHub에 보내지 않는다.
