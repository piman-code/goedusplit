# 같은 JSON의 Mac → Windows → Mac 왕복 인계

현재: Mac 첫 실제 저장·동일 Mac에서 재열기 완료. Windows 재저장과 Mac 최종 재열기는 미실행이며 왕복 전체는 미완료입니다.

`T03-Mac-first.json`은 같은 1.0.6/a7 Mac 후보가 실제 WebEngine 저장으로 작성한 `합성 저장.json`의 byte-exact 사본입니다. 새 fixture가 아닙니다. SHA256: `19c6ee86b0ed5096a239eeaf49716d354ed99c8e6b98b2373011db554608aba5`.

`T03_MANIFEST.json`에 원본 저장 파일 지문, 입력 fixture 지문, 문항 전체·검토안·활성 검토안·배점·직접 정답률과 실제 저장된 기준표를 기록했습니다. 전체 기준표는 최초 앱 저장 때 기본값이 추가됐으며 원래 업무 필드는 모두 보존됐습니다. 이 **실제 저장 파일** 전체가 이후 대조 기준입니다.

## 학교 Windows에서

1. 이 작은 ZIP만 승인된 파일 전달 방식으로 옮겨 **새 로컬 폴더**에 압축을 풉니다. 설정/state/학생자료/앱 설치 파일은 이 묶음에 없습니다.
2. 그 폴더의 PowerShell에서 `Get-FileHash -Algorithm SHA256 .\T03-Mac-first.json`으로 위 지문을 확인합니다. 지문이 다르면 진행하지 않습니다.
3. `WINDOWS_RESUME_PROMPT.txt` 전체를 기존 학교 Codex 채팅에 붙여넣습니다. 후보는 기존 artifact11214639642에 들어 있는 고정 a7 portable을 사용합니다. 기대 exe SHA256: `ca46662ff46611a8dc7716d356a102eb12acb7a240453f8bcac5ec398c22b965`.

**중요한 제한:** a7의 `--synthetic-qa`와 기존 학교 검사기는 전달 JSON을 입력받지 않습니다. 둘을 다시 돌려도 Windows가 이 파일을 저장한 증거가 아닙니다. 기존 QSettings·사용자 자료에 닿지 않는 실행 경로가 확보되지 않으면 일반 앱을 실행하지 말고 Windows 재저장 단계는 미실행으로 남깁니다. APPDATA만 변경하면 Windows registry 설정까지 격리되지 않습니다. 설치·보안정책 변경·새 후보 빌드는 이 요청 범위에 없습니다.

## 왕복 파일과 기록

- Windows 성공 시 전달받은 바로 이 파일을 입력으로 사용하고 새 `T03-Windows-saved.json`을 실제 앱에서 저장·재열기합니다. 새 fixture 생성이나 파서 검사만으로 성공 처리하지 않습니다.
- 원본/전달본/Windows 저장본 SHA256과 문항·모든 judgment·활성 j2·1.5/3.25·0/63.25/100%·전체 targetRatePresets를 대조합니다. 시각 차이는 별도로 기록합니다.
- Windows 저장 JSON·실제 단계 보고서만 Mac으로 돌려보냅니다. 이 Mac에서 그 반환 파일을 같은 a7 후보로 격리 실행해 저장·재열기한 뒤 마지막 단계를 판정합니다. 고정 CLI 입력 제한은 Mac에도 동일합니다.
- 실제 파일 전달도 아직 수행하지 않았습니다. 이 문서는 전달 준비이며 Windows 완료 증거가 아닙니다.

`MAC_QA_SUMMARY.json`은 이번 Mac 실제 합성12개 결과 요약입니다. `WINDOWS_REPORTED_STATUS.json`은 사용자가 전달한 Windows 보고를 기록한 것이며 이 Mac에서 원본 파일을 확인한 증거가 아닙니다. Excel·교사·HWP·설치/복귀·학교 인수는 별도로 남아 있습니다.
