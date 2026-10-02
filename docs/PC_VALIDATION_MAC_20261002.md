# Mac 후속 검증 실제 기록 — 2026-10-02

**Mac의 동일 1.0.6 후보 합성 검사12개 통과 / 실제 JSON 첫 저장 준비 완료.** Windows 재저장과 마지막 Mac 재열기는 미실행이며, 같은 파일의 왕복과 학교 인수 전체는 미완료다. 기존 [PC 기록 양식](PC_VALIDATION_RECORD.md)은 빈 양식 그대로 보존한다.

## 이번 실행과 보존 범위

- 요청한 `codex/desktop-candidates-1.0.6` 브랜치를 확인했다. 시작 시 local·remote 모두 `00f0aee422b868ec2102acd0f988882f3953ed69`, worktree clean. [학교 준비 기록](SCHOOL_HANDOFF_20261002.md)·[Windows 검사 안내](WINDOWS_SCHOOL_QA.md)·[PC 기록 양식](PC_VALIDATION_RECORD.md)을 읽었다.
- 연결된 호스트는 Mac local뿐이다. Windows에 전달할 합성 파일과 재개 프롬프트를 준비하며, 이 Mac에서 Windows 앱을 실행한 것으로 기록하지 않는다.
- 2026-10-02 21:02 KST에 Darwin/arm64의 native Cocoa로 frozen 후보를 실제 실행했다. DMG는 읽기 전용으로 마운트하고 새 결과 폴더를 사용했다. 앱 설치·일반 실행·보안정책 변경·공개 배포는 하지 않았다.
- child process에 별도 HOME·TMPDIR·cache·config·data·matplotlib 경로만 전달했다. ambient 인증정보·Codex 경로·Qt 환경 override를 넘기지 않았다. 후보의 QA는 명시 INI와 fallback false, 격리 portfolio, off-the-record WebEngine profile, 로컬 요청 interceptor를 사용한다.
- 원래 설치 앱과 원래 dist의 1.0.5 버전·실행 파일 지문, 기존 venv·stash refs를 보존했다. 확인한 Qt 설정 파일과 앱 자료 폴더의 실행 전후 **메타데이터가 같았다**. 설정 값·학생자료·stash 내용은 읽지 않았다. 이 확인은 지정 경로의 메타데이터 대조이며 컴퓨터 전체 파일 쓰기 감사가 아니다.
- DMG detach exit0, 부모 process 환경 전후 동일. 이는 이번 Mac 실행기의 관찰이며 Windows에서 보고한 `process_environment_restored=false`의 원인을 해결했다는 뜻이 아니다.

로컬 원본 증거: `out_test/mac-followup-20261002-210040/`. 이 경로는 Git 전송 제외이며 clean clone에서는 열리지 않는다. 실제 QA 보고서·PNG·실행 로그·읽기 전용 마운트 기록·보존 대조·후처리의 초기 실패와 최종 대조를 이 폴더에 함께 보존했다.

## 후보 출처와 실제 지문

| 항목 | 실제 대조 결과 |
| --- | --- |
| 앱 버전·내장 BUILD source | 1.0.6 / `a7f7d95b6a751606ac75d1f6958ed9686bd9884b`, clean true |
| 사용한 DMG SHA256 | `2c9895bfb250ede8d072be2739cc76587a5aa981de1a9ae401040c230d094cf4` |
| 실제 Mac 실행 파일 SHA256 | `2a6bee7078f88999a57c5073ac0e4f3adda188ab0b735c258a58f4e70731f21c` |
| 내장 안내 SHA256 | `7539ac6d1f4b5863a7f73a44f6c151a1060207d78aa8e1c7dd5dd50e3c93143f` |
| 검증 | SHA256SUMS·외부 BUILD·내장 BUILD_SOURCE·Info.plist·arm64 지문 일치, hdiutil verify·codesign strict/deep 성공 |
| 서명 한계 | ad-hoc 후보 검증이며 Apple notarization 확인을 뜻하지 않음 |
| 원래 앱·자산·진입점 | a7 이후 이번 작업에서 변경하지 않음; 문서·검증 fixture 커밋은 앱의 빌드 SHA가 아님 |

이 후보는 [양 OS 후보 CI36952967141](https://github.com/piman-code/goedusplit/actions/runs/36952967141)에서 만든 artifact11204209837의 보존 사본이다. 이번 Mac 검사는 그 사본의 실제 지문을 다시 대조한 로컬 실행이며 새 CI 앱 빌드가 아니다.

## 자동 합성 검사와 Windows 보고

이번 Mac `QA_REPORT.json`: exit0, status passed, frozen true, 필수12개 모두 boolean true, errors 0, 실행 파일 지문 일치. 실제 WebEngine 렌더링·불러오기·JSON 다운로드·다른 작업 후 저장본 재열기·저장 취소·탭 이동·격리 설정을 확인했다. 네트워크 검사는 QA 페이지 요청과 패치된 URL 요청 범위이며 학교 방화벽·완전한 오프라인 OS 검사가 아니다.

실제 PNG에서 Mac 상단·탭·상태바와 계산기 한글이 보였다. 화면 표시는 63.3%로 반올림되지만 저장 값은 63.25다. 이 관찰은 합성 QA 화면 하나의 증거이며 일반 앱 테마·학교 배율·모든 대화상자·교사 인수 완료를 뜻하지 않는다.

사용자가 이 Mac 채팅에 전달한 Windows 실행 보고: CI36979736361/artifact11214639642의 원본 검사기 `passed-synthetic-only`, 합성 QA 필수12개 true·오류0. PowerShell5.1 정책 차단, 별도 도구 샌드박스의 계산기 로딩 실패, `process_environment_restored=false` 진단도 있었다. **이 Mac에서는 그 Windows 원본 보고서·실행 로그를 재읽지 않았다.** 성공 보고와 별도 실패 진단을 분리해 기록하고 학교 인수 완료로 바꾸지 않는다.

## T03 실제 JSON 첫 저장과 왕복 상태

Mac 후보는 실제 저장 버튼으로 `합성 저장.json`을 만들고 다른 작업을 불러온 뒤 이 다운로드를 재열기했다. 전달용 `T03-Mac-first.json`은 그 저장본의 **bytes 그대로인 사본**이다. 입력 fixture를 새로 생성한 파일이 아니며 이후 왕복의 기준 파일이다.

기존 QA의 재열기 대조는 `business_values()`가 정한 문항·검토안 필드 범위다. 기준표 전체는 실제 저장 JSON에서 대조했으며 재열기 후 메모리의 기준표 전체를 별도로 검증한 것은 아니다. 이후 Windows·Mac 반환 단계에서 기준표를 포함한 전체 업무 값을 확인해야 한다.

첫 저장 시 앱이 입력에 없던 기본 `targetRatePresets`를 추가했다. 초기 보조 실행기의 전체 객체 동일 assertion은 이 추가 필드 때문에 실패했으나 앱의 실제 QA12개와 종료는 모두 성공했다. 초기 실패 보고서를 수정·폐기하지 않고 보존했으며, 별도 후처리에서 모든 원래 필드가 정확히 같고 추가 기준표가 앱 기본값과 같음을 확인했다. 앱을 다시 실행하거나 기준을 완화하지 않았다. 이후 왕복은 **기준표까지 포함한 실제 저장본 전체**를 대조한다.

| 실제 단계 | 파일·출처 | 결과 |
| --- | --- | --- |
| Mac 첫 저장·같은 Mac에서 재열기 | a7 frozen 후보 실제 다운로드, `T03-Mac-first.json` | 실행 완료; 원본과 전달 사본 지문 같음 |
| Mac→Windows 파일 전달 | Git의 합성 fixture와 별도 전달 ZIP 준비 | 준비 완료; Windows 수신 지문 확인 미실행 |
| Windows 같은 파일 불러오기·재저장 | `T03-Windows-saved.json` 기대 | 미실행 — 연결된 Windows 없음·고정 QA CLI의 기존 JSON 입력 미지원 |
| Windows→Mac 반환·마지막 재열기·저장 | `T03-Mac-final.json` 기대 | 미실행 — Windows 반환 파일 없음 |
| 전체 왕복 | 같은 입력 계보와 세 단계 실제 저장 필요 | 미완료 |

| 기준 값 | 실제 저장 내용 |
| --- | --- |
| 문항 | 2개 / 번호1·2 / 선택형 / 배점1.5·3.25 / 목표 C |
| 검토안·활성 검토안 | 합성 검토안 j1·j2 / 활성 j2 |
| 1번 직접 정답률 | A100 / B82.5 / C63.25 / D40 / E0, 두 검토안 모두 보존 |
| 기준표·근거 | targetRatePresets 전체 5×5 / difficultyAverage / evidenceData null |
| 실제 저장본·전달 사본 SHA256 | `19c6ee86b0ed5096a239eeaf49716d354ed99c8e6b98b2373011db554608aba5` |
| 업무 객체 SHA256 | `1495c4669ac27b58ff73e23c4df28edf1cef5f545c065042ec68254dae951863` |

업무 지문은 top-level `exportedAt`만 제외하고 모든 문항 필드·judgment·기준표를 포함해 `json.dumps(ensure_ascii=False, sort_keys=True, separators=(',', ':'))`의 UTF-8에 SHA256을 적용했다. 전체 파일 지문도 별도로 유지하며 생성 시각은 업무 값 손실과 구분한다. 전체 기준 값은 [T03 manifest](../tests/fixtures/T03-20261002-Mac-first/T03_MANIFEST.json)에 있다.

### Windows 재개에 반드시 필요한 경계

고정 a7의 `--synthetic-qa`는 새 출력 폴더만 받으며 외부 JSON 입력을 지원하지 않는다. 기존 Windows 검사기를 또 실행하면 별도 fixture를 생성한다. 이 성공을 이번 Mac 저장 파일의 Windows 재저장으로 처리하면 안 된다.

Windows의 정상 진입점은 기존 QSettings registry와 앱 자료에 접근할 수 있다. 별도 portable 폴더나 APPDATA만으로 그 접근이 격리됐다고 주장하지 않는다. **기존 사용자 설정·자료 접근이 차단된 실제 경로가 확보된 경우에만** 이 파일 자체를 같은 후보로 저장·재열기한다. 격리가 없으면 일반 실행하지 않고 차단 진단과 미실행을 기록한다. 새 후보 빌드·설치·보안정책 변경으로 이 조건을 우회하지 않는다. 마지막 Mac 재열기에도 같은 CLI 입력 제한이 적용된다.

## 전달 파일과 후속

Git으로 전달할 합성 묶음: [tests/fixtures/T03-20261002-Mac-first](../tests/fixtures/T03-20261002-Mac-first/README.md). Windows에서 기존 변경을 보존하며 이 브랜치를 내려받은 후 `README.md`와 `WINDOWS_RESUME_PROMPT.txt`를 읽는다. 이 묶음은 실제 첫 저장 JSON·manifest·Mac QA 요약·사용자가 보고한 Windows 상태·README·재개 프롬프트6개만 포함한다. 설정/state/로그/학생자료/앱 설치 파일은 포함하지 않는다.

Git의 자동 줄바꿈 변환으로 Windows 수신 지문이 달라지지 않도록 이 첫 저장 JSON에만 `.gitattributes`의 `-text`를 적용했다. 나머지 전달 문서5개는 LF를 유지한다. 앱·사용자 설정을 바꾼 것이 아니며 Windows 수신 후에도 파일 SHA256을 실제 확인한다.

별도 로컬 ZIP: `out_test/mac-followup-20261002-210040/Goedu-Split-1.0.6-T03-Mac-first-20261002.zip`, SHA256 `02e3ef89d234822c8898cdcdf186e82e08cb596306b7cb6d12b2e3237ca25466`. 압축 CRC·6개 구성·실제 저장 JSON bytes 일치를 확인했다. 전송 준비와 실제 Windows 수신·앱 저장을 구분한다.

T01 전체 분석, T02 계획서 전체 계산, T04 Windows Excel 실제 열기, T05 전체 개인정보 대화상자, T06 실제 HWP, T07 일반 첫 실행/오프라인/개발 clone, T08 교사·학교 화면, T09 설치/복귀는 이번 실행에서 미실행이다. T03는 Mac 첫 저장만 완료다. 필수12개 성공으로 해당 인수 항목들을 통과 처리하지 않는다.
