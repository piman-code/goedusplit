# Goedu-Split

성취평가 결과 분석과 예상정답률 설계를 돕는 Windows/macOS 데스크톱 앱입니다.

제작자: 이준서  
© 2026 이준서. All rights reserved.

Goedu-Split은 학생 성적 자료를 웹 서버에 올리지 않고, 선생님 PC에서 분석하도록 만든 로컬 실행형 도구입니다. KICE의 성취평가 결과 분석 web-app 2.1.2 화면과 도움말을 참고해 분석 흐름을 재구성했으며, 원본 R/Shiny 코드를 복제한 것은 아닙니다.

## 선생님용 빠른 안내

대부분의 선생님은 소스코드를 내려받을 필요가 없습니다. 아래 순서대로 완성된 Windows 배포 파일을 받으면 됩니다.

1. 이 저장소 오른쪽 또는 상단의 **Releases**를 누릅니다.
2. 가장 위에 있는 **Latest** 버전을 엽니다.
3. **Assets**에서 `Goedu-Split-...선생님배포...zip` 파일을 다운로드합니다.
4. 다운로드한 zip 파일을 우클릭하고 **압축 풀기**를 선택합니다.
5. 압축을 푼 폴더 안의 `Goedu-Split` 폴더를 엽니다.
6. `Goedu-Split.exe`를 더블클릭합니다.
7. Windows에서 “PC 보호” 또는 “알 수 없는 게시자” 안내가 뜨면, 신뢰할 수 있는 배포 파일인지 확인한 뒤 **추가 정보 > 실행**을 누릅니다.

처음 실행할 때는 Windows 보안 안내가 뜰 수 있습니다. 현재 배포 파일은 디지털 코드 서명 인증서로 서명되어 있지 않기 때문입니다. 파일을 받기 전에는 반드시 GitHub Releases의 제작자, 버전, SHA256 값을 확인해 주세요.

## 업데이트 받는 방법

새 버전이 나오면 기존 프로그램 위에 덮어쓰지 말고, 새 zip을 다시 받아 압축을 푸는 방식을 권장합니다.

1. Goedu-Split을 종료합니다.
2. GitHub **Releases**에서 가장 최신 버전을 다운로드합니다.
3. 새 폴더에 압축을 풉니다.
4. 새 폴더의 `Goedu-Split.exe`를 실행합니다.
5. 이전 버전 폴더는 새 버전이 정상 실행되는 것을 확인한 뒤 삭제해도 됩니다.

성적 엑셀 파일은 프로그램 폴더 안에 보관하지 않는 편이 좋습니다. 학교 업무 폴더에 따로 보관하면 프로그램을 업데이트해도 자료가 섞이지 않습니다.

## 개인정보와 보안

- 기본 분석은 선생님 PC 안에서 실행됩니다.
- 학생 이름, 반/번호, 응답 자료를 별도 서버에 자동 업로드하지 않습니다.
- AI 검토 기능은 선택 기능입니다. 기본 초안은 로컬 규칙으로 만들고, 외부 AI를 사용할 때는 사용자가 설정한 연결 방식에 따릅니다.
- Codex CLI 방식은 API Key가 아니라 `codex login`의 ChatGPT OAuth 로그인을 사용하도록 안내합니다.
- 클라우드/외부 서버로 보낼 때는 학생 이름과 반/번호 제거 옵션을 제공합니다.
- 배포 전에는 `windows_release_audit.py`와 `privacy_release_audit.py`로 소스/배포 폴더를 점검합니다.

더 자세한 보안 정책은 [SECURITY.md](SECURITY.md)를 참고하세요.

## 현재 배포 후보 체크섬

아래 값은 2026-06-22 Windows 배포 후보를 기준으로 기록한 SHA256입니다. Release에 첨부된 파일을 받은 뒤 PowerShell에서 `Get-FileHash -Algorithm SHA256 파일명.zip`으로 비교할 수 있습니다.

| 파일 | SHA256 |
| --- | --- |
| `Goedu-Split-1.0.1-선생님배포-fixed-20260622.zip` | `BBC1F79B6F410B6929D1513A078CC52064D1884E2D2152A8624D04AEA538F387` |
| `Goedu-Split-Windows-1.0.1-source-fixed-20260622.zip` | `387BB885AE1831DE4392AA78D22FF189912405ED795181ECFFB1B474C656F86E` |

완성된 zip 파일은 용량이 크므로 `main` 브랜치에 직접 커밋하지 않습니다. 실행 파일 배포본은 GitHub **Releases**의 첨부파일로 제공합니다.

## 주요 기능

- 학생답 정오표와 문항정보표를 불러와 성취수준을 분석합니다.
- 전체 성취도, 문항 분석, 답지반응분포, 성취기준 분석을 표와 그래프로 확인합니다.
- 예상정답률 입력 탭에서 A/B, B/C, C/D, D/E 예상 분할점수를 계산하고 NEIS 입력표 작성에 활용할 수 있습니다.
- 문항별 목표 성취수준과 난이도, 배점, 예상정답률을 조정할 수 있습니다.
- 분석 결과를 CSV/XLSX로 내보낼 수 있습니다.
- 라이트/다크/자동 테마와 확대/축소를 지원합니다.
- 상담 모드에서 다른 학생의 이름과 반/번호를 가릴 수 있습니다.

## 입력 파일

| 파일 | 형식 | 설명 |
| --- | --- | --- |
| 학생답 정오표 | `.xlsx` | NEIS에서 내려받은 학생별 정오표 |
| 문항정보표 | `.xlsx` | 문항번호, 내용영역, 성취기준, 난이도, 배점, 정답이 들어 있는 문항 정보표 |
| 예상추정분할점수 조회 | `.xlsx` | 선택 파일. A/B, B/C, C/D, D/E, E/미도달 분할점수 자동 입력에 사용 |
| 수행평가 결과 | `.xlsx` | 선택 파일. 지원 범위는 버전에 따라 다를 수 있음 |

학교마다 엑셀 양식이 조금씩 다를 수 있습니다. 양식이 크게 다르면 일부 열을 자동으로 인식하지 못할 수 있습니다.

## 소스코드로 직접 실행하기

개발자나 관리자는 소스코드를 내려받아 직접 실행할 수 있습니다.

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python run.py
```

## Windows 배포본 직접 빌드하기

Windows용 `.exe`는 Windows에서 빌드해야 합니다.

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m py_compile app\main_window.py app\ai_client.py
python -m unittest discover -s tests -v
python build_scripts\windows_release_audit.py --source .
python -m PyInstaller --noconfirm --clean goedusplit.spec
python build_scripts\slim_windows_dist.py
python build_scripts\privacy_release_audit.py dist\Goedu-Split
Compress-Archive -LiteralPath dist\Goedu-Split -DestinationPath dist\Goedu-Split-1.0.1-windows.zip -Force
```

빌드 후 선생님께는 `dist\Goedu-Split` 폴더 전체가 들어 있는 zip 파일을 전달해야 합니다. `Goedu-Split.exe`만 따로 보내면 `_internal` 폴더가 없어 실행되지 않습니다.

## 배포 전 점검표

배포자는 새 버전을 올리기 전에 아래를 확인합니다.

- `python -m py_compile app\main_window.py app\ai_client.py` 통과
- `python -m unittest discover -s tests -v` 통과
- `python build_scripts\windows_release_audit.py --source .` 통과
- `python build_scripts\privacy_release_audit.py dist\Goedu-Split` 통과
- 새 exe를 직접 실행해 첫 화면이 뜨는지 확인
- zip 안에 `.git`, `.env`, `.venv`, `__pycache__`, `build`, `dist`, `sample_data`, 개인 엑셀 자료, API Key, 토큰 파일이 없는지 확인
- README의 SHA256 값을 새 배포 파일 기준으로 갱신

## 저장소 구조

```text
app/                    앱 코드
app/spliter_ox_web/      내장 예상정답률 계산기 정적 웹앱
assets/                 아이콘과 번들 리소스
build_scripts/          빌드/감사/패키징 스크립트
distribution/           사용자 안내와 QA 문서
tests/                  자동 테스트
requirements.txt        Python 의존성
goodusplit.spec         PyInstaller 빌드 설정
run.py                  앱 진입점
```

## 라이선스와 사용 범위

본 저장소의 소스코드는 투명한 검토와 학교 업무 활용을 위해 공개될 수 있습니다. 별도 라이선스가 명시되지 않은 한 저작권은 제작자 이준서에게 있으며, 무단 상업적 재배포나 명의 변경 배포는 허용하지 않습니다.

학교 현장에서 도구를 내려받아 사용하는 것은 허용합니다. 수정본을 공개 배포하려면 제작자에게 먼저 확인해 주세요.

## 변경 이력

### 1.0.1

- Windows 배포 안내와 보안 감사 절차 정리
- 예상정답률 입력 탭의 상단 배너 접기/펼치기 개선
- 문항별 목표 성취수준 변경 시 예상 분할점수 재계산
- Codex CLI OAuth 연결 안내와 초보자용 설치 안내 보강
- Windows 배포 폴더 개인정보/비밀값 감사 통과

### 1.0.0

- 성취평가 결과 분석 데스크톱 앱 기본 기능 구성
- Data, 전체 성취도, 문항 분석, 답지반응분포, 성취기준 분석 탭 제공
- 예상정답률 계산기 통합
