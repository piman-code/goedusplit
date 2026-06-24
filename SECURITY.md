# Security Policy

Goedu-Split은 학교 성취평가 자료를 다루는 도구이므로, 배포 전 보안 점검을 필수 절차로 둡니다.

## 지원 버전

현재 보안 점검 대상 버전은 `1.0.1`입니다. 새 배포본을 만들 때는 README의 체크섬과 이 문서를 함께 갱신합니다.

현재 Windows 배포 파일:

- 파일명: `Goedu-Split-1.0.1.zip`
- SHA256: `57ADFA2CB392F45E4310E9E0ACA0701F04E5A41BA430D79BA09430037BCAF67B`

## 개인정보 처리 원칙

- 기본 분석은 로컬 PC에서 실행합니다.
- 학생 답안, 이름, 반/번호, 성적 파일을 자동으로 외부 서버에 업로드하지 않습니다.
- AI 검토 기능은 선택 기능이며, 외부 AI를 사용할 때는 사용자가 직접 연결 방식을 선택해야 합니다.
- 외부 AI 사용 시 학생 이름과 반/번호 제거 옵션을 제공합니다.
- 배포 zip에는 실제 학생 자료, 샘플 성적 파일, 개인 PC 경로, 계정 정보, API Key, 토큰을 포함하지 않습니다.
- Codex CLI 클라우드 AI는 API Key 입력 방식이 아니라 `codex login`의 ChatGPT OAuth 세션을 사용합니다.

## 배포 전 필수 감사

Windows 배포자는 아래 명령을 통과한 뒤 Release 파일을 올립니다.

```powershell
python -m py_compile app\main_window.py app\ai_client.py
python -m unittest discover -s tests -v
python build_scripts\windows_release_audit.py --source .
python -m PyInstaller --noconfirm --clean goedusplit.spec
python build_scripts\slim_windows_dist.py
python build_scripts\privacy_release_audit.py dist\Goedu-Split
```

배포 zip을 만든 뒤에는 압축을 새 임시 폴더에 풀고, 압축 해제된 `Goedu-Split` 폴더에 대해 `privacy_release_audit.py`를 한 번 더 실행합니다.

추가로 zip 내부에 아래 항목이 없는지 확인합니다.

- `.git`, `.env`, `.venv`, `__pycache__`
- `build`, `dist` 같은 이전 빌드 산출물
- 실제 학생 엑셀 자료 또는 샘플 성적 파일
- API Key, 토큰, 비밀번호, 인증서, 개인키
- 개인 PC 경로 또는 계정 정보

## 체크섬 확인

배포자는 Release에 첨부한 zip 파일의 SHA256을 README에 기록합니다.

사용자는 PowerShell에서 아래 명령으로 파일이 바뀌지 않았는지 확인할 수 있습니다.

```powershell
Get-FileHash -Algorithm SHA256 .\Goedu-Split-1.0.1.zip
```

README에 적힌 SHA256과 결과가 다르면 실행하지 말고 다시 다운로드해 주세요.

## 알려진 배포상 주의점

현재 Windows 실행 파일은 디지털 코드 서명 인증서로 서명되어 있지 않을 수 있습니다. 이 경우 Windows SmartScreen에서 “알 수 없는 게시자” 또는 “PC 보호” 안내가 뜰 수 있습니다.

이 안내가 뜨는 것만으로 악성 파일이라는 뜻은 아니지만, 사용자는 반드시 아래를 확인해야 합니다.

- GitHub Releases에서 받은 파일인지
- README의 SHA256과 다운로드 파일의 SHA256이 일치하는지
- 파일명이 안내된 배포 파일명과 같은지

## 취약점 또는 개인정보 포함 의심 신고

다음 문제가 보이면 배포를 중단하고 제작자에게 알려 주세요.

- 배포 zip에 실제 학생 자료가 들어 있음
- API Key, 토큰, 비밀번호처럼 보이는 문자열이 들어 있음
- 앱이 사용자의 동의 없이 외부 서버로 자료를 전송함
- 다운로드 파일의 SHA256이 README와 다름
- 실행 중 개인정보가 의도치 않게 화면 또는 내보내기 파일에 포함됨

신고 시에는 문제 파일명, 버전, 재현 방법, 화면 캡처 또는 로그 일부를 함께 전달해 주세요. 단, 실제 학생 개인정보는 가려서 보내야 합니다.
