# Goedu-Split

성취평가 결과 분석과 예상정답률 설계를 돕는 Windows/macOS 데스크톱 앱입니다.

제작자: 이준서  
버전: 1.0.5
© 2026 이준서. All rights reserved.

Goedu-Split은 NEIS 정오표와 문항정보표를 선생님 PC에서 분석하는 로컬 실행형 도구입니다. 학생 성적 자료를 자동으로 서버에 올리지 않습니다.

## 선생님용 다운로드

소스코드를 내려받을 필요 없이 완성된 배포 파일을 받으면 됩니다. 오른쪽 또는 상단의 **Releases**에서 최신 버전 `v1.0.5`를 엽니다.

### Windows

1. **Assets**에서 `Goedu-Split-1.0.5-windows-setup.exe`(설치형) 또는 `Goedu-Split-1.0.5-windows.zip`(압축형)을 받습니다.
2. 설치형은 더블클릭해 안내대로 설치합니다. 압축형은 zip을 우클릭해 **모두 압축 풀기** 후 폴더 안의 `Goedu-Split.exe`를 실행합니다. `Goedu-Split.exe`만 따로 꺼내지 말고 폴더 전체를 그대로 쓰세요.
3. Windows 보안 안내가 뜨면 파일 출처를 확인한 뒤 **추가 정보 > 실행**을 선택합니다.

### macOS

1. **Assets**에서 `Goedu-Split-1.0.5-mac.dmg`를 받아 엽니다.
2. `Goedu-Split.app`을 옆의 `Applications` 폴더로 끌어다 놓습니다.
3. 처음 실행할 때 '확인되지 않은 개발자' 안내가 뜨면 Finder의 응용 프로그램 폴더에서 앱을 **우클릭 > 열기**로 한 번 엽니다.
4. HWP 시험지를 읽으려면 이 Mac에 Node.js와 kordoc이 설치되어 있어야 합니다(HWPX·PDF는 없어도 됩니다).

## SHA256 확인값

아래 값은 배포 파일의 지문입니다. 받은 파일이 바뀌지 않았는지 확인할 때 씁니다.

| 파일 | SHA256 |
| --- | --- |
| `Goedu-Split-1.0.5-windows-setup.exe` | `E075124E609C2021A9E6F7AAE7DA97008E23ABC8B0EB12945230E08D813D024B` |
| `Goedu-Split-1.0.5-windows.zip` | `45630DA4FB481123E3E6F7E351446872DF0E17489C9AB63A850A0CF2DC98E6E2` |
| `Goedu-Split-1.0.5-mac.dmg` | `4EDC762E17CDEE5FDE71A3CDE21A299946195412CA8CEA6B21241DA4FE7875DE` |

Windows PowerShell: `Get-FileHash -Algorithm SHA256 .\파일이름` · macOS 터미널: `shasum -a 256 파일이름`

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
- 시험 후 예측-실측 비교(분할점수 경계 학생 정답률과 교사 예측의 문항별 상대차, 다음 시험 기준표 제안, 엑셀 저장)
- 시험지(HWP·HWPX·PDF)에서 문항 번호·유형·배점을 이 PC 안에서 읽어 계산기 문항 초안 만들기

상단의 **예상 분할점수 · 100점 환산**은 체크한 문항만 계산한 값이 아닙니다. 표에 있는 전체 문항의 배점과 A~E 예상정답률을 합산해 계산합니다. **점수 비교**를 펼치면 원점수와 NEIS 반올림 후 결과를 확인할 수 있습니다.

작은 창에서는 입력 패널이 자동으로 접히고, 각 탭의 그래프·표·안내 영역도 제목을 눌러 접을 수 있습니다. **문항표 / 선택 문항 / 검토안·근거** 보기로 작업하며, 수동으로 접거나 펼친 패널 상태는 창 크기를 바꿔도 유지됩니다. 자료 전달과 문항 구성안은 상단 **자료** 메뉴에 있습니다.

직접 입력한 소수 정답률과 100%를 임의로 보정하지 않습니다. 여러 판단자가 있으면 문항별 예상정답률의 평균을 사용합니다. NEIS 준비표에서는 문항구분·난이도가 같은 문항을 배점 가중평균한 뒤 A~E 모두 가장 가까운 5%로 반올림합니다(중간값은 올림). 원래 계산값과 반올림 후 분할점수를 함께 확인하세요. 이 표는 NEIS 자동 전송이나 공식 확정값을 대신하지 않습니다.

NEIS 입력표를 만들기 전에는 다음을 확인해 주세요.

- 문항 수가 실제 시험 문항 수와 같은가?
- 배점 합계가 실제 총점과 같은가?
- 목표 성취수준이 문항의 성취기준과 맞는가?
- A~E 예상정답률이 지나치게 낙관적이거나 비관적이지 않은가?
- 상단 전체 예상 분할점수가 학교에서 예상한 흐름과 크게 어긋나지 않는가?

## 이번 버전의 범위

시험지 문항 오류 검토, 오류 후보 탐지 및 로컬/클라우드 AI 연결은 후속 버전으로 미룹니다. 시험지에서는 문항 번호·유형·배점만 읽습니다. 현재 화면에서는 해당 진입점을 제공하지 않으며, 기본 분석과 예상정답률 설계에 AI 설치나 로그인이 필요하지 않습니다. 관련 소스는 후속 개발을 위해 남아 있습니다.

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
Compress-Archive -LiteralPath dist\Goedu-Split -DestinationPath dist\Goedu-Split-1.0.5-windows.zip
```

## 라이선스와 사용 범위

학교 현장에서 도구를 내려받아 사용하는 것은 허용합니다. 별도 라이선스가 명시되지 않은 한 저작권은 제작자 이준서에게 있으며, 무단 상업적 재배포나 명의 변경 배포는 허용하지 않습니다.
