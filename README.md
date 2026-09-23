# Goedu-Split

성취평가 결과 분석과 예상정답률 설계를 돕는 Windows/macOS 데스크톱 앱입니다.

제작자: 이준서  
개발 버전: 1.0.3 (배포 전 검증 중)
© 2026 이준서. All rights reserved.

Goedu-Split은 NEIS 정오표와 문항정보표를 선생님 PC에서 분석하는 로컬 실행형 도구입니다. 학생 성적 자료를 자동으로 서버에 올리지 않습니다.

## 선생님용 다운로드

아래 다운로드와 SHA256은 기존 1.0.1 배포본 기준입니다. 1.0.3의 변경사항이 포함된 공개 배포를 의미하지 않습니다.

소스코드를 내려받을 필요 없이 완성된 Windows 배포 파일을 받으면 됩니다.

1. 오른쪽 또는 상단의 **Releases**를 누릅니다.
2. 최신 버전 `v1.0.1`을 엽니다.
3. **Assets**에서 `Goedu-Split-1.0.1.zip`을 다운로드합니다.
4. zip 파일을 우클릭해 **모두 압축 풀기**를 선택합니다.
5. 압축을 푼 폴더 안의 `Goedu-Split.exe`를 더블클릭합니다.
6. Windows 보안 안내가 뜨면 파일 출처를 확인한 뒤 **추가 정보 > 실행**을 선택합니다.

`Goedu-Split.exe`만 따로 꺼내지 말고, 압축을 푼 `Goedu-Split` 폴더 전체를 그대로 사용해 주세요.

## SHA256 확인값

아래 값은 배포 zip의 파일 지문입니다.

| 파일 | SHA256 |
| --- | --- |
| `Goedu-Split-1.0.1.zip` | `57ADFA2CB392F45E4310E9E0ACA0701F04E5A41BA430D79BA09430037BCAF67B` |

PowerShell에서 다음 명령으로 확인할 수 있습니다.

```powershell
Get-FileHash -Algorithm SHA256 .\Goedu-Split-1.0.1.zip
```

## 프로그램 사용 흐름

1. 왼쪽 **입력 데이터**에서 NEIS `학생답 정오표 data` 엑셀을 선택합니다.
2. `문항정보표` 엑셀을 선택합니다.
3. 필요하면 `예상추정분할점수 조회` 또는 수행평가 자료를 추가합니다.
4. **분석 실행**을 누릅니다.
5. 오른쪽 탭에서 전체 성취도, 문항 분석, 답지반응분포, 성취기준별 결과를 확인합니다.

자세한 사용법은 배포 zip 안의 `사용 안내.md` 또는 이 저장소의 [distribution/USER_GUIDE.md](distribution/USER_GUIDE.md)를 보세요.

## 예상정답률 입력 탭

이 탭은 자료를 모두 올리지 않아도 사용할 수 있습니다. 문항별 배점, 난이도, 목표 성취수준, A~E 수준별 예상정답률을 조정해 NEIS 입력표를 만들 수 있습니다.

주요 기능:

- 문항별 목표 성취수준 설정
- A/B, B/C, C/D, D/E, E/미도달 전체 예상 분할점수 계산
- NEIS 입력표 생성
- 원점수·100점 환산·NEIS 반올림 결과 비교
- 문항 구성안과 근거 엑셀 저장
- 작업 저장/불러오기
- 시험 후 예측-실측 비교(수준별 경계 학생 정답률과 교사 예측 비교, 엑셀 저장)

상단의 **예상 분할점수 · 100점 환산**은 체크한 문항만 계산한 값이 아닙니다. 표에 있는 전체 문항의 배점과 A~E 예상정답률을 합산해 계산합니다. **점수 비교**를 펼치면 원점수와 NEIS 반올림 후 결과를 확인할 수 있습니다.

작은 창에서는 입력 패널이 자동으로 접힙니다. **문항표 / 선택 문항 / 검토안·근거** 보기로 작업하며, 수동으로 접거나 펼친 패널 상태는 창 크기를 바꿔도 유지됩니다. 자료 전달과 문항 구성안은 상단 **자료** 메뉴에 있습니다.

직접 입력한 소수 정답률과 100%를 임의로 보정하지 않습니다. 여러 판단자가 있으면 문항별 예상정답률의 평균을 사용합니다. NEIS 준비표에서는 문항구분·난이도가 같은 문항을 배점 가중평균한 뒤 A~E 모두 가장 가까운 5%로 반올림합니다(중간값은 올림). 원래 계산값과 반올림 후 분할점수를 함께 확인하세요. 이 표는 NEIS 자동 전송이나 공식 확정값을 대신하지 않습니다.

NEIS 입력표를 만들기 전에는 다음을 확인해 주세요.

- 문항 수가 실제 시험 문항 수와 같은가?
- 배점 합계가 실제 총점과 같은가?
- 목표 성취수준이 문항의 성취기준과 맞는가?
- A~E 예상정답률이 지나치게 낙관적이거나 비관적이지 않은가?
- 상단 전체 예상 분할점수가 학교에서 예상한 흐름과 크게 어긋나지 않는가?

## 이번 버전의 범위

시험지 PDF/HWP 문항 검토, 오류 후보 탐지, 시험지 자동 반영 및 로컬/클라우드 AI 연결은 후속 버전으로 미룹니다. 현재 화면에서는 해당 진입점을 제공하지 않으며, 기본 분석과 예상정답률 설계에 AI 설치나 로그인이 필요하지 않습니다. 관련 소스는 후속 개발을 위해 남아 있습니다.

## 보안 원칙

- 기본 분석은 선생님 PC 안에서 실행됩니다.
- 배포 zip에는 `.git`, `.env`, `.venv`, 실제 학생자료, API Key, 토큰 파일을 포함하지 않도록 점검합니다.
- 이번 버전의 작업 화면은 AI 제공자를 호출하지 않습니다. 로컬에 저장한 분석·작업·내보내기 파일은 사용자가 별도로 관리해야 합니다.
- 공유용 자료를 만들 때는 학생 이름, 반/번호 등 개인정보가 필요 이상 포함되지 않았는지 확인해 주세요.
- 결과 CSV·근거 엑셀·계산기 분석자료는 기본적으로 가명(학생 001…)을 씁니다. 실명은 저장 창에서 직접 선택하고 경고를 확인한 경우에만 포함됩니다. 가명은 익명이 아니므로 성적 자료로 관리하세요.

보안 정책은 [SECURITY.md](SECURITY.md)를 참고하세요.

## 개발자용 실행

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python run.py
```

## Windows 배포 빌드

```powershell
python -m py_compile app\main_window.py app\ai_client.py app\data_loader.py
python -m unittest discover -s tests -v
node --test tests/test_expected_rate_web.cjs
python build_scripts\windows_release_audit.py --source .
python -m PyInstaller --noconfirm --clean goedusplit.spec
python build_scripts\slim_windows_dist.py dist\Goedu-Split
python build_scripts\privacy_release_audit.py dist\Goedu-Split
Compress-Archive -LiteralPath dist\Goedu-Split -DestinationPath dist\Goedu-Split-1.0.3.zip
```

## 라이선스와 사용 범위

학교 현장에서 도구를 내려받아 사용하는 것은 허용합니다. 별도 라이선스가 명시되지 않은 한 저작권은 제작자 이준서에게 있으며, 무단 상업적 재배포나 명의 변경 배포는 허용하지 않습니다.
