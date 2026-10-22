# 학교 Windows 격리 합성 검사 — 1.0.17 후보 06776f0

이 폴더는 `docs/handoff/20261021/`(1.0.17 후보 5b2792b)의 같은 도구를 후보 06776f0으로 옮긴 것이다.
검사 내용은 그대로이고 고정값만 바뀌었다. 예전 폴더는 기록으로 남겨 둔다.

## 고정된 후보
- 소스 커밋: `06776f0379d1a7e2e97bbc673dc1975fed02394a` (버전 1.0.17)
- CI: run 39772682990, artifact `desktop-candidates-1.0.17-06776f03…` 또는 `candidate-windows-06776f03…`
- `Goedu-Split-1.0.17-windows.zip` SHA256 `44028378b613a624c490a9bc2b50db57266edcaff5b0cb502a15e5622f8d90e8`
- `Goedu-Split.exe` SHA256 `390898c43269a5b0612caac1f975d23d8c15bbe2a7fc820b19d65657201a556d`
- 앱 자체 검사(`--synthetic-qa`) 49개, 파일 목록 2,453개(`WINDOWS_FILES.json.gz`)

## 순서
1. 새 빈 폴더에 이 폴더의 `CANDIDATE_LOCK.json`, `WINDOWS_FILES.json.gz`, `RUN_WINDOWS_CHECK.ps1`을 넣는다.
2. 같은 폴더에 `Goedu-Split-1.0.17-windows.zip`을 넣는다(압축을 풀지 않는다).
3. PowerShell에서 아직 없는 새 결과 경로를 주고 실행한다.
   `powershell.exe -NoProfile -File .\RUN_WINDOWS_CHECK.ps1 -OutputRoot <새 절대 경로> -Context School`
4. 결과 폴더의 `RUN_RESULT.json`이 `passed-automated-synthetic-only`이고 `checks_passed`가 49인지 본다.

## 지켜야 할 것
- 설치(setup.exe), EXE 더블클릭, 보안 정책 변경, 바로가기 변경을 하지 않는다. 격리된 합성 검사만 한다.
- 정책 차단이 나오면 우회하지 말고 오류 문구·단계·종료 코드를 기록한다.
- 이 검사는 자동 합성 검사다. 교사 인수(T01–T09, `docs/PC_VALIDATION_RECORD.md`)와 실제 NEIS 파일 호환성은 따로 확인한다.
- 검사가 4분 넘게 걸리면 `synthetic-qa/QA_HANG_STACKS.log`에 그 시점 위치가 남는다. 크래시가 아니며 판정은 `NATIVE_CRASH.log`(비어 있어야 함)로 한다.
