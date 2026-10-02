# 1.0.6 자율 개발 검증과 완료 판정

현재 상태: **검증 진행 중 / 사용자 인수 대기 / 공개 배포 미실행**. 양쪽 플랫폼 작업 성공만으로 완료하지 않는다. 같은 SHA의 pair·실제 파일 재대조·독립 판정까지 갖춰야 D01~D09 전체를 완료로 표시한다.

2026-10-02 사용자 요청에 따라 자율 개발 D01~D09와 실제 학교 사용자 인수 T01~T09를 분리했다. 승인된 작업 브랜치는 `codex/desktop-candidates-1.0.6`이다. main·설치본1.0.5·원자료·가상환경·개인 설정은 보존한다.

## 후보·원격 실행

- 버전: 1.0.6.
- 현재 검증한 후보 SHA: `1866f4e2e288ac0763a3291d32ecb492419daa91`. 최종 두 플랫폼 후보 SHA는 pair 수정·재실행 후 확정한다.
- 후보 CI: [36951043652](https://github.com/piman-code/goedusplit/actions/runs/36951043652). Mac arm64·Windows x64 작업은 검사·빌드·포장·frozen QA를 통과했으나 **pair의 양쪽 사용자 안내 지문 대조가 실패해 전체 실행은 실패**했다. 이 실행을 최종 통합 성공으로 표시하지 않는다.
- 이 실행의 Python은 양쪽 226개 실행으로 OK이며 Mac 7개·Windows 11개가 건너뛰어졌다. Node는 양쪽 43개 통과했다. 플랫폼 전용 검사와 선택 kordoc 부재를 구분하며 건너뛰기를 실행 통과로 세지 않는다.
- 이전 후보 `9baded3`에서 현재 `1866f4e`까지 `app/`, `assets/`, `run.py`, `goedusplit.spec`, 의존성 lock, CI, 공통 사용자 안내의 Git diff가 비어 있음을 직접 확인했다. **Windows 포장 스크립트 2개와 버전 조회 helper 등 `build_scripts/`는 변경됐다.** 기존 Mac source/native 분석·NEIS·시험지·작은 화면 증거는 동일한 앱 코드의 증거로 연결한다. 변경된 포장·빌드 출처·frozen 후보·pair는 새 SHA로 다시 검증한다. 후속 SHA에서도 이 비교를 다시 확인한다.
- 최종 CI URL·pair artifact·후보 파일 SHA256·독립 완료 판정: 아직 확정하지 않았다. 앞선 실행과 로컬 후보의 지문을 새 후보 지문으로 재사용하지 않는다.

## D01~D09 증거 지도

| 기준 | 증거와 범위 | 판정 |
| --- | --- | --- |
| D01 분석 | 양 OS 합성 파일 읽기·독립 분석 기대값·오류 뒤 보존 검사, Mac 실제 분석 UI13개 | 1866 CI 개발 검사 통과, 최종 SHA 대조 대기 |
| D02 계산 | 양 OS expected_rates/grade_cut/neis 검사·Node43 계약, Mac NEIS/보정 native UI25개 | 1866 CI 계약 검사 통과, 최종 SHA 대조 대기 |
| D03 저장 | 양 OS 직렬화·download 계약·frozen 실제 JSON 저장/재열기/취소와 업무 필드 보존 | 1866 양 OS frozen QA 통과, 최종 후보 재검증 대기 |
| D04 내보내기 | 양 OS writer의 파일·시트·수치·한글·취소·수식 보호 검사, Mac 실제 CSV4·근거/NEIS/보정 XLSX | 1866 CI 개발 검사 통과, 최종 SHA 대조 대기 |
| D05 개인정보 | 양 OS 가명·실명 확인/취소·해시·설정/데이터 격리, 전송 전 commit blob 및 후보 구성 감사 | 1866 개발·출력 감사 통과, 최종 후보 재대조 대기 |
| D06 시험지 | 양 OS 합성 HWPX/PDF 실제 내장 읽기와 기대값, Mac UI8개, mock HWP converter 성공/부재·읽기 실패 보존 | 1866 내장 읽기·계약 검사 통과, 실제 kordoc 별도, 최종 SHA 대조 대기 |
| D07 실행 | 양 OS 새 runner의 lock 설치·개발 검사·frozen Qt/WebEngine 및 요청 차단 QA, Mac native 창2개·GitHub 새 clone source QA12개 | 1866 양 OS frozen QA 통과, 학교 실행 아님, 최종 후보 재검증 대기 |
| D08 화면 | Mac offscreen WebEngine 밝음/어두움1280×800/1080×7204개·앱 배율·별도 native 접기4개·창PNG 독립 읽기 | 동일 코드 Mac 증거 확보, 최종 독립 판정 대기 |
| D09 후보·인계 | 동일 SHA 양 OS·pair 성공, MacDMG/WinZIP/setup·BUILD/QA·SHA256SUMS 실제 수집·재대조, 최신 안내·완료판정관 | pair 실패 수정 중, 최종 파일/지문/판정 대기 |

상세 source/native 증거는 [검증 기록](VERIFICATION_20261002.md)을 따른다. 모듈 검사와 Mac source UI가 Windows Excel·학교 UI 전체를 검증했다는 뜻은 아니다. 필수인 양 OS frozen 실행 QA는 실제로 수행해야 한다.

Mac GitHub 새 clone은 `e63a473`과 clean 추적 소스 감사를 확인하고 실제 앱 source QA12개·오류0으로 종료했다. 한글 버튼·문항표·소수 배점·합성 검토안을 native PNG에서 직접 읽었다. 기존 Python 환경을 빌려 사용했고 새 의존성 설치나 사용자 설정 변경은 없다. 보고서와 PNG는 로컬 `out_test/goal-20261002-github-clone-mac/`에 보존한다. 이는 동일 앱 코드의 source/native 증거이며 다른 SHA의 빌드·포장 성공을 증명하지 않는다. 새 환경 lock 설치는 별도 두 OS CI 증거를 사용한다.

`1866f4e` 소스 키트는 122파일의 manifest·각 지문·압축 해제 감사와 Gitless identity를 통과했다. `out_test/goal-20261002-windows-source-kit-1866/SOURCE_KIT_QA.json`은 native Windows 실행을 하지 않았음을 명시한다. 소스 ZIP은 앱 설치 파일이나 최종 pair의 대체물이 아니다.

CI 로그 근거는 로컬 `out_test/goal-20261002-ci-36951043652/`에 보존한다. Windows frozen QA는 Windows Server runner의 offscreen Qt 실행이며 학교 Windows·Excel·사용자 설치 검증이 아니다. Mac native 실행과 DMG 내부 실행은 기존 설치 앱을 교체하지 않은 증거다. Windows portable·setup 생성 성공도 실제 설치 성공을 뜻하지 않는다.

## 사용자 인수와 알려진 제약

T01~T09 전체 인수 합격은 아직 아니다. [PC 기록 양식](PC_VALIDATION_RECORD.md)에 학교 Windows의 OS/CPU·Excel·JSON실제왕복·OS오프라인/배율·교사 해석·설치/복귀 결과를 기록해야 한다. 공개 Release·main 병합·설치 교체는 별도 승인이다.

기본 전부 펼침의 작은 화면에서 그래프·학생표 높이가 부족할 수 있다. 기존 접기 버튼으로 축/제목/전체4행에 접근한 증거를 확보했으며 실제 학교 배율과 교사 시각 검토는 대기다. HWP 외부변환기는 선택 의존성이고 native HWP 성공·학교 환경은 별도 확인한다. CI의 실제 kordoc HWPX 검사는 외부변환기 부재로 건너뛰었으며, mock 변환기 계약과 실제 내장 HWPX/PDF 읽기 검사는 구분한다. 스캔 PDF OCR은 범위 밖이다. Mac ad-hoc 서명은 Apple 공증이 아니고 Windows 유료 서명은 도입하지 않았다. Intel Mac/Windows ARM은 지원 확인 전 대상에 넣지 않는다.

## 설치·배포 경계와 유지보수

[개발 안내](DEVELOPMENT.md), [릴리스 준비](RELEASE_CANDIDATES.md), [백업·복귀](BACKUP_AND_ROLLBACK.md), [인계](HANDOFF.md)를 연결한다. Actions artifact는14일 보관되므로 로컬 검증 폴더의 사본을 보존한다. 기존 README의1.0.5 파일/지문과 새1.0.6 후보를 섞지 않는다. 학생자료·설정·로그를 GitHub에 보내지 않는다.
