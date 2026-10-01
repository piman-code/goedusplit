# 1.0.6 두 플랫폼 배포 후보 준비

현재는 로컬 구현·검증 진행 단계다. 이 문서의 절차가 존재하는 것과 실제 후보·CI·학교 PC 검증 성공은 구분한다. 기존 1.0.5 설치본과 배포 파일은 보존한다.

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

Windows는 `SHA256SUMS`의 같은 파일 행과 값이 정확히 일치해야 한다. 후보 실행·설치 범위는 확인한 후 결정한다. 설치를 피해서 시험하려면 portable ZIP 전체를 **새 폴더**에 풀어 실행한다. 실제 설치본 검증은 T07·T09 필수이며 기존 설치를 교체하는 행위는 사용자 승인 후 진행한다. Mac도 새 후보 위치/별도 사용자로 실행하며 기존 `/Applications` 앱을 먼저 바꾸지 않는다.

두 PC에서 [수동 QA](../distribution/MANUAL_QA_CHECKLIST.md)를 실행하고 날짜·OS·CPU·배율·SHA·파일 지문·합성 입력·T01~T09 결과를 기록한다. T03은 Mac 저장 → Windows 저장 → Mac 재열기를 실제로 수행한다. T04는 Windows Excel 열기도 포함한다. T08은 교사가 결과의 의미를 확인해야 한다.

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
