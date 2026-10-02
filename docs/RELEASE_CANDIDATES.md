# 1.0.6 두 플랫폼 배포 후보 준비

현재는 **자율 개발 완료 / 사용자 인수 대기 / 공개 배포 미실행**이다. 승인된 새 브랜치 push·CI와 실제 후보·독립 D01~D09 판정을 완료했다. 학교 PC·교사·설치/복귀 인수는 별도로 남아 있으며 기존 1.0.5 설치본과 배포 파일은 보존한다. 최종 문서 커밋·전송 감사·원격 반영은 별도 실행 기록으로 확인한다.

## 현재 후보 확인 상태

고정 후보 SHA는 `a7f7d95b6a751606ac75d1f6958ed9686bd9884b`이며 [후보 CI 36952967141](https://github.com/piman-code/goedusplit/actions/runs/36952967141)와 [push 검사 36952966860](https://github.com/piman-code/goedusplit/actions/runs/36952966860)가 성공했다. Mac arm64·Windows x64·pair가 모두 성공해 [pair artifact11204209837](https://github.com/piman-code/goedusplit/actions/runs/36952967141/artifacts/11204209837)를 생성했다. 양쪽 Python은 228개 실행으로 OK(Mac7/Windows11 skipped), Node43 및 빌드 재검사·frozen12개 QA가 통과했다. 내려받은 실제 9파일의 체크섬·내부 구성과 Mac DMG native 재실행도 통과했다. 독립 최종 검토는 D09를 포함한 D01~D09 모두 충족으로 판정했다.

이전 `1866f4e`의 [CI 36951043652](https://github.com/piman-code/goedusplit/actions/runs/36951043652)에서는 Mac arm64·Windows x64의 개발 검사·앱 빌드·포장·frozen QA가 성공했으나 pair가 두 사용자 안내의 지문 불일치를 감지해 **전체 CI는 실패**했다. 실제 artifact bytes와 Git blob을 대조해 Windows CRLF/Mac LF 차이만 있었음을 확인했다. 새 후보는 `.gitattributes` 및 소스 키트의 Git blob 처리 보완을 포함한다. 이전 파일을 고쳐 새 실행의 성공 증거로 사용하지 않는다.

후보 SHA·성공 CI·pair artifact·세 배포 파일의 SHA256·내부 구성·Mac 실제 재실행은 확인했다. **독립 완료 판정은 D01~D09 모두 충족·critical 발견0**이다. [자율 개발 판정표](AUTONOMOUS_COMPLETION.md)가 실제 증거와 별도 사용자 인수를 연결한다. [로컬 독립 완료 보고서](../out_test/goal-20261002-final-a7/INDEPENDENT_COMPLETION.json)를 직접 재읽고 SHA256 `7ab1b358d4c3f517ad5be106d18810441b726fc489c84ea0e01730271f4a1b4e`를 확인했다. 보고서는 로컬 보존·Git 전송 제외다. 기존 로컬 `9baded3` DMG와 실패한 실행의 파일은 이력으로 보존하며 새 SHA로 재표시하지 않는다. 문서만 바꾸는 후속 커밋도 고정 후보의 빌드 SHA를 대체하지 않는다.

## 동일한 소스를 확정하는 절차

1. 변경 파일·합성 검사 결과·전송 대상 감사를 검토한다. 정식 후보는 clean commit에서만 만든다.
2. 사용자 승인 범위의 브랜치를 GitHub에 push한다. 병합·태그 게시·Release 생성은 별도 승인 대상이다.
3. Actions의 `Test and Build Desktop Candidates`를 연다. 테스트만 할 때는 `candidate_version`을 비운다. 후보가 필요할 때 `checkout_ref`에 검토된 **전체 SHA**, `candidate_version`에 `1.0.6`을 입력한다. workflow 자체도 해당 구현이 포함된 브랜치에서 실행한다.
4. source job이 SHA를 한 번 확정하고 macOS arm64·Windows x64 두 작업에 같은 SHA를 넘긴다. 버전 불일치, 필수 검사·빌드·포장 실패는 성공 후보 수집을 중단한다.
5. 양쪽이 성공해야 pair job이 필수 파일·manifest·SHA256을 검사한다. 한 플랫폼만 성공한 artifact는 두 플랫폼 준비 완료 증거가 아니다.

통합 workflow는 PR·작업 브랜치 변경 시 두 플랫폼 검사, 수동 버전 지정 또는 `vX.Y.Z` 태그 시 후보 빌드를 구분한다. CI runner의 새 환경에만 lock 의존성을 설치한다. 로컬 설치·지속 설정을 변경하는 동작은 없다. 자동 Release 게시도 없다.

## 받아야 하는 파일

`desktop-candidates-1.0.6-<SHA>` artifact 안에 아래 파일이 모두 있어야 한다.

- `Goedu-Split-1.0.6-mac.dmg`
- `Goedu-Split-1.0.6-windows-setup.exe`
- `Goedu-Split-1.0.6-windows.zip`
- `USER_GUIDE-macos.md`, `USER_GUIDE-windows.md`
- `BUILD-macos.json`, `BUILD-windows.json`
- `QA-macos.json`, `QA-windows.json` (각 frozen 후보의 합성 실행 보고서)
- `SHA256SUMS`

BUILD에는 동일 source SHA·clean 여부·버전, OS·아키텍처·Python·Node·패키지 버전과 배포 파일 hash를 남긴다. 실행 파일의 빌드 출처와 hash도 묶어 이전 앱을 새 소스 버전 이름으로 포장하는 것을 막는다. 합성 QA 보고서의 frozen·버전·실행 파일 hash·필수 12개 결과도 대조한다. Mac은 앱 내부 plist 버전도 대조한다. 합성 검사·CI는 실제 학교 사용을 대체하지 않는다.

Actions artifact 보관은 14일이다. 사용자용 영구 다운로드 주소로 안내하지 않는다. 승인된 전송·내려받기 후 별도 검증 보관 폴더에 보존한다. 공개 게시 전까지 파일명과 checksum은 준비안이며 기존 README 배포 값에 섞지 않는다.

### 최종 지문 기록

`a7f7d95`의 성공한 pair에서 내려받은 실제 bytes를 재대조했다. 아래 지문은 이 후보의 실제 값이며 이전 후보의 값이나 예상값이 아니다. 원본 SHA256SUMS와 `out_test/goal-20261002-final-a7/CHECKSUM_READBACK.json`을 함께 보존한다.

| 파일·확인 항목 | SHA256·실제 결과 |
| --- | --- |
| Goedu-Split-1.0.6-mac.dmg | 2c9895bfb250ede8d072be2739cc76587a5aa981de1a9ae401040c230d094cf4 |
| Goedu-Split-1.0.6-windows.zip | 446a5478fef905f60dee2e83269394c7a2f27f80e9feed7d8fdfad9057563069 |
| Goedu-Split-1.0.6-windows-setup.exe | 8965b9e7116d7868bed3f39096524e0320578a12ffe168851066795063adfdc6 |
| BUILD-macos / BUILD-windows의 전체 SHA·버전·아키텍처 | a7f7d95b6a751606ac75d1f6958ed9686bd9884b / 1.0.6 / arm64·AMD64 |
| QA-macos / QA-windows의 frozen·실행 파일 지문·필수 결과 | 두 보고서 frozen true·passed·필수12개, 실제 내려받은 내부 실행 파일 지문·BUILD identity와 재대조 통과; Mac DMG native12개 재실행 통과 |
| 두 USER_GUIDE bytes·manifest 지문 일치 | 둘 다 Git 소스와 bytes 일치, SHA2567539ac6d1f4b5863a7f73a44f6c151a1060207d78aa8e1c7dd5dd50e3c93143f |
| SHA256SUMS와 모든 내려받은 파일 대조 | 수록 9개 지문 전부 실제 bytes 대조 통과; SHA256SUMS 자체를 포함해 파일10개 보존 |
| artifact·로컬 보존 위치와 독립 재검증 | artifact11204209837 / artifacts/Goedu-Split-1.0.6-a7f7d95/; 내부 구성·실제 Mac 실행 통과, 독립 D01~D09 충족·critical 발견0 |

실물 근거는 `out_test/goal-20261002-final-a7/`의 CHECKSUM/MAC_DOWNLOAD/WINDOWS_DOWNLOAD/WINDOWS_SOURCE_ASSETS_READBACK 보고서에 보존한다. Mac은 읽기 전용 DMG에서 native frozen QA12개를 확인했고 설치 앱을 교체하지 않았다. Windows는 ZIP3234개 CRC·runtime15개·AMD64 실행 파일 지문/identity·web/font/icon27개를 대조했다. 일부 텍스트는 Git LF와 Windows CRLF의 동일 내용이며 binary 지문은 일치한다. Windows 실행 자체는 CI frozen QA 증거이며 이 Mac에서 installer를 실행한 검증은 아니다.

## 파일 지문과 실행 확인

Mac 터미널의 후보 폴더:

```bash
shasum -a 256 -c SHA256SUMS
hdiutil verify Goedu-Split-1.0.6-mac.dmg
```

Windows PowerShell의 후보 폴더:

```powershell
Get-FileHash -Algorithm SHA256 .\Goedu-Split-1.0.6-windows-setup.exe
Get-FileHash -Algorithm SHA256 .\Goedu-Split-1.0.6-windows.zip
```

Windows는 `SHA256SUMS`의 같은 파일 행과 값이 정확히 일치해야 한다. 후보 실행·설치 범위는 확인한 후 결정한다. 설치를 피해서 시험하려면 portable ZIP 전체를 **새 폴더**에 풀어 실행한다. 실제 학교 사용을 위한 설치본 검증은 별도 사용자 인수 T07·T09의 필수 조건이며 기존 설치를 교체하는 행위는 사용자 승인 후 진행한다. Mac도 새 후보 위치/별도 사용자로 실행하며 기존 `/Applications` 앱을 먼저 바꾸지 않는다.

두 PC에서 [수동 QA](../distribution/MANUAL_QA_CHECKLIST.md)를 실행하고 날짜·OS·CPU·배율·SHA·파일 지문·합성 입력·T01~T09 결과를 기록한다. T03은 Mac 저장 → Windows 저장 → Mac 재열기를 실제로 수행한다. T04는 Windows Excel 열기도 포함한다. T08은 교사가 결과의 의미를 확인해야 한다.

D01~D09는 자동·합성 개발 검사, 양 OS frozen QA, 실제 Mac source/native 증거, 동일 SHA pair·파일 대조 및 독립 완료 판정을 요구한다. Windows runner의 offscreen 실행을 학교 PC 검증으로, portable 실행을 설치·복귀로, Mac 별도 후보 실행을 기존 설치 교체로 표시하지 않는다. D통과와 T01~T09 사용자 인수 대기는 함께 기록할 수 있으나, T증거 전에는 학교 사용을 위한 배포 준비 완료를 선언하지 않는다.

## 서명과 알려진 지원 제약

현재 Mac 후보는 ad-hoc 서명 검사를 사용한다. Developer ID·Apple 공증 완료라는 뜻이 아니다. Windows 유료 코드 서명도 도입하지 않았다. 첫 실행 안내와 학교 보안 정책상 실행 가능 여부는 실제 PC에서 확인한다. 시스템 보안 기능을 포괄적으로 끄지 않는다.

초기 지원 목표는 Apple Silicon Mac와 학교 Windows x64이다. CI의 Windows Server runner는 학교 Windows 데스크톱 검증을 대신하지 않는다. Intel Mac·Windows ARM은 별도 후보와 실기 증거 전까지 지원으로 선언하지 않는다. HWP는 기존 Node/kordoc이 필요하고, 없으면 HWPX/텍스트 PDF로 변환해 사용한다. 스캔 PDF의 OCR, AI·온라인 검토, 클라우드 동기화·자동 업데이트는 이번 범위 밖이다.

## 기존 정상 버전으로 복귀

구체적인 백업 대상·Mac 저장 위치·Windows 앱 설정 키와 실행 경계는 [백업·복귀 안내](BACKUP_AND_ROLLBACK.md)를 따른다. 실제 양쪽 PC 결과는 [검증 기록 양식](PC_VALIDATION_RECORD.md)에 남긴다.

1. 새 버전에서 저장하기 전에 원래 JSON 작업 파일을 다른 이름으로 복사한다. 사용자 앱 저장 폴더와 hash key가 있는 설정도 로컬 백업한다. 학생자료를 Git이나 CI로 보내지 않는다.
2. 1.0.5 설치본·설치 파일·기존 파일 지문을 보존한다. 후보는 새 폴더/별도 사용자로 검증해 기존 자료에 덮어쓰지 않는다.
3. 문제 발생 시 후보를 종료하고 보존한 1.0.5를 실행한다. 원본 JSON 사본을 연다. 후보가 쓴 파일을 기존 파일 위에 덮어쓰지 않는다.
4. 설치 교체 후 복귀가 필요하면 사용자 승인 범위에서 보존한 이전 설치 파일로 복귀한다. 단순 앱 복귀로 사용자 저장 데이터를 초기화하지 않는다.
5. 실제 두 PC에서 원래 작업이 다시 열리는지 확인한 결과를 T09에 기록한다. 절차만 작성한 상태를 복귀 검증 완료로 처리하지 않는다.

## 릴리스 노트·게시 준비안

예정 버전: 1.0.6. 원격 Release는 아직 생성·게시하지 않았다.

변경: 사용자 데이터와 분리된 합성 검사, 기존 빌드·포장 파일 보존, Git 복제본/소스 키트 감사 구분, 정확한 의존성 기준, 동일 SHA의 Mac·Windows 검사·후보 포장·체크섬 절차, 개발·QA 안내 최신화. 핵심 계산 계약과 사용자 저장 형식은 보존한다.

게시 전 반드시 채울 내용: 실제 후보 SHA·파일 지문, 성공한 CI URL, 지원 OS, T01~T09·교사 확인, 알려진 문제와 우회 방법, 실제 복귀 결과. 데이터 손실·개인정보 노출·계산 오류·실행 불가가 남으면 게시하지 않는다. 최종 파일 목록과 검증 결과를 제시해 공개 게시 승인을 받은 후 실행한다.

runner 선택은 2026-10-02 [GitHub 공식 지원표](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)의 macos-15 arm64·windows-2022 x64를 확인했다. [Windows2022 이미지 목록](https://github.com/actions/runner-images/blob/main/images/windows/Windows2022-Readme.md)에 Inno Setup이 있지만 실제 CI에서 설치 프로그램 생성·파일 존재를 필수 검사한다.
