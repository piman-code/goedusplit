# 학교 Windows에서 후보 검사하기

이 안내는 **1.0.6 / a7f7d95b6a751606ac75d1f6958ed9686bd9884b** portable 후보의 실제 PC 실행을 확인하는 절차입니다. 설치와 기존 앱 교체 없이 합성 작업을 새 폴더에서 검사합니다. Python·Git·Node 설치는 필요하지 않습니다.

## 학교 PC에서 먼저 할 일

1. Mac에서 준비한 `Goedu-Split-1.0.6-school-check.zip` 전체를 학교 Windows로 옮기거나, [학교 검증 CI](https://github.com/piman-code/goedusplit/actions/workflows/school-candidate-validation.yml)의 성공한 실행에서 `school-handoff-1.0.6-…` artifact를 내려받습니다. GitHub 로그인·접근 권한이 필요하며 artifact는 14일 보관됩니다. 학생 자료는 포함하지 않습니다.
2. Windows 탐색기에서 **모두 압축 풀기**를 누릅니다. GitHub artifact 안에 전달 ZIP이 있으면 그것도 **모두 압축 풀기**합니다. 짧은 로컬 경로를 사용합니다. 내부의 `Goedu-Split-1.0.6-windows.zip`은 그대로 둡니다.
3. **`START_HERE.txt`·`build_scripts`·`synthetic`·후보 ZIP이 함께 보이는 폴더**를 엽니다. 압축 풀기로 같은 이름의 폴더가 한 겹 더 생겼으면 안쪽으로 들어갑니다. 주소 표시줄에 `powershell`을 입력하고 Enter를 누릅니다.
4. 아래 한 줄을 실행합니다.

```powershell
powershell.exe -NoProfile -File .\build_scripts\validate_school_candidate.ps1 -CandidateZip .\Goedu-Split-1.0.6-windows.zip -OutputRoot .\school-result-01 -Context School
```

검사기는 고정 ZIP·실행 파일 지문과 내장 빌드 출처를 확인하고, 새 전용 폴더에만 압축을 풉니다. 합성 검사 앱은 자체 격리 INI 설정·포트폴리오·웹 프로필을 사용합니다. 이미 있는 출력 폴더는 덮어쓰지 않으므로 다시 실행할 때는 `school-result-02`처럼 새 이름을 지정합니다.

학교 보안 정책·서명·실행 정책이 실행을 막으면 표시된 문구와 검사 단계만 기록합니다. 관리자 실행, 보안 기능 해제, 실행 정책 변경으로 우회하지 않습니다. 결과에 개인 PC 이름·사용자명·학생정보를 적을 필요는 없습니다.

## 결과를 확인하는 방법

콘솔과 새 출력 폴더의 `SCHOOL_VALIDATION_REPORT.json`을 확인합니다. 그 안의 `status: passed-synthetic-only`와 `synthetic-qa/QA_REPORT.json`의 `status: passed`, 필수 12개 `true`가 자동 검사 성공을 뜻합니다. 실제 창 그림은 `synthetic-qa/candidate-window.png`입니다. 그 PC에서 수행한 **자동 합성 실행·저장 검사**의 성공이며 전체 사용자 인수 합격은 아닙니다.

검사에는 계산기 표시, 소수 배점 1.5·3.25, 직접 정답률 0·63.25·100%, 실제 JSON 저장·재열기, 저장 취소, 탭 이동, 격리 설정과 요청한 외부 네트워크 없음이 포함됩니다. 학교 망의 차단 설정 자체와 모든 화면 조작을 검증한 것은 아닙니다. `Context School`은 실행자가 지정한 장소이며 검사기가 독립적으로 장소를 확인하지 않습니다.

결과 파일은 로컬에 보존합니다. 정상 결과는 QA 보고서·실행기 보고서·합성 창 PNG만 전달해 확인할 수 있습니다. 오류 콘솔에 사용자 경로가 있으면 공유 전에 해당 부분을 지웁니다. 상태 폴더·레지스트리·학생 입력을 GitHub에 올리지 않습니다.

## 자동 검사 후 남은 실제 인수

[PC 검증 기록 양식](PC_VALIDATION_RECORD.md)을 복사해 실제 결과만 적습니다. 자동 검사 통과로 T01~T09 전체를 통과 처리하지 않습니다.

- [합성 키트 안내](SYNTHETIC_VALIDATION.md)의 분석·NEIS·보정 내보내기 값을 대조하고 Windows Excel로 파일을 엽니다. 입력은 묶음의 `synthetic/`에 있습니다.
- 같은 합성 JSON을 실제로 Mac → Windows → Mac에 옮겨 저장·재열기합니다. 각 PC가 독립적으로 새 fixture를 만든 것은 왕복 검증이 아닙니다.
- 학교 해상도·배율과 밝음/어두움, 한글 경로, 교사가 직접 수행한 흐름을 기록합니다. 실제 HWP 변환 환경은 별도 확인합니다.
- 설치·이전 버전 복귀는 [백업과 복귀 절차](BACKUP_AND_ROLLBACK.md)에 따라 구체적인 설치 대상이 승인된 뒤 진행합니다.

정상 일반 실행은 자동 QA와 달리 기존 앱 설정을 사용할 수 있습니다. 위 명령은 `--synthetic-qa`로만 실행하며 일반 앱 실행·학교 수업 자료 분석·설치를 대신 수행하지 않습니다.

## Mac에서 전달 묶음 다시 만들기

기존 개발 환경과 검증된 로컬 후보를 사용합니다. 명령은 새 출력에만 쓰며 네트워크와 설치를 사용하지 않습니다.

```bash
.venv/bin/python -B build_scripts/make_school_validation_bundle.py --candidate-dir artifacts/Goedu-Split-1.0.6-a7f7d95 --output artifacts/Goedu-Split-1.0.6-school-check
```

완성 폴더의 `HANDOFF_MANIFEST.json`은 실행기·문서·합성 자료·후보 파일의 지문을 기록합니다. 전달 ZIP 생성은 학교 실행 결과가 아닙니다. 앱 후보의 빌드 SHA와 이후 추가한 검사기·문서의 소스 SHA를 구분합니다.
