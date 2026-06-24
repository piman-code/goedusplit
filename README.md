# Goedu-Split

성취평가 결과 분석과 예상정답률 설계를 돕는 Windows 데스크톱 앱입니다.

제작자: 이준서  
버전: 1.0.1  
© 2026 이준서. All rights reserved.

Goedu-Split은 NEIS 정오표와 문항정보표를 선생님 PC에서 분석하는 로컬 실행형 도구입니다. 학생 성적 자료를 자동으로 서버에 올리지 않습니다.

## 선생님용 다운로드

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
- A/B, B/C, C/D, D/E 전체 예상 분할점수 계산
- NEIS 입력표 생성
- 시험지 반영표 생성
- 문항 구성안과 근거 엑셀 저장
- 작업 저장/불러오기

상단의 **전체 예상 분할점수**는 체크한 문항만 계산한 값이 아닙니다. 표에 있는 전체 문항의 배점과 A~E 예상정답률을 합산해 계산합니다.

NEIS 입력표를 만들기 전에는 다음을 확인해 주세요.

- 문항 수가 실제 시험 문항 수와 같은가?
- 배점 합계가 실제 총점과 같은가?
- 목표 성취수준이 문항의 성취기준과 맞는가?
- A~E 예상정답률이 지나치게 낙관적이거나 비관적이지 않은가?
- 상단 전체 예상 분할점수가 학교에서 예상한 흐름과 크게 어긋나지 않는가?

## Codex CLI 클라우드 AI

AI 문항 검토에서 **Codex CLI 클라우드 (OAuth)** 를 쓰려면 Windows 터미널 또는 PowerShell에서 한 번 로그인해야 합니다. API Key를 입력하지 않습니다.

```powershell
winget install OpenJS.NodeJS.LTS
npm install -g @openai/codex
where codex
codex --version
codex login
codex login status
```

`codex login status`가 `Logged in using ChatGPT`로 나오면 Goedu-Split에서 **AI 문항 검토 > AI 설정 > Codex CLI 클라우드 (OAuth) > 연결 테스트**를 누릅니다.

## 보안 원칙

- 기본 분석은 선생님 PC 안에서 실행됩니다.
- 배포 zip에는 `.git`, `.env`, `.venv`, 실제 학생자료, API Key, 토큰 파일을 포함하지 않도록 점검합니다.
- AI 문항 검토에서 Codex CLI 클라우드 AI를 사용할 때만 선택한 검토 자료가 Codex CLI를 통해 처리됩니다.
- 공유용 자료를 만들 때는 학생 이름, 반/번호 등 개인정보가 필요 이상 포함되지 않았는지 확인해 주세요.

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
python build_scripts\windows_release_audit.py --source .
python -m PyInstaller --noconfirm --clean goedusplit.spec
python build_scripts\slim_windows_dist.py dist\Goedu-Split
python build_scripts\privacy_release_audit.py dist\Goedu-Split
Compress-Archive -LiteralPath dist\Goedu-Split -DestinationPath dist\Goedu-Split-1.0.1.zip -Force
```

## 라이선스와 사용 범위

학교 현장에서 도구를 내려받아 사용하는 것은 허용합니다. 별도 라이선스가 명시되지 않은 한 저작권은 제작자 이준서에게 있으며, 무단 상업적 재배포나 명의 변경 배포는 허용하지 않습니다.
