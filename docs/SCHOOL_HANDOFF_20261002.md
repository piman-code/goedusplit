# 학교 Windows 인수 준비 결과 — 2026-10-02

**학교 검증 도구와 전달 묶음 준비 완료 / 실제 학교 인수 미실행.**

사용자는 학교 Windows에서도 작업 가능하다고 확인했다. 현재 채팅에서 연결된 호스트는 Mac local뿐이므로 실제 학교 실행은 그 PC에서 이어간다. 앞선 D01~D09 자율 개발 완료와 이번 전달 준비, 실제 학교 T01~T09를 구분한다.

## 실제 수행한 검사

- 검사기·문서 소스: `9ddec21db325ea0803bbe655ca040e3603e99a89`. 앱 후보는 기존 `a7f7d95b6a751606ac75d1f6958ed9686bd9884b` / 1.0.6 그대로다. 앱·자산·run.py·spec·lock·기존 후보 CI·사용자 안내의 변경은 없다.
- [학교 검사기 CI36979736361](https://github.com/piman-code/goedusplit/actions/runs/36979736361) 성공. Windows Server 2022 / PowerShell5.1.20348.5622 / AMD64에서 고정 portable 후보를 실행했다. 한글·공백 경로, ZIP·실행 파일·내장 출처·안내 지문, 필수12개 boolean true·오류0·frozen true, PNG1280×800을 확인했다. 실행기 보고서의 맥락은 `CI`, 표현은 `offscreen`이다.
- 같은 CI에서 잘못된 ZIP을 압축 해제 전에 거부하고, 기존 폴더의 sentinel·이전 보고서와 파일 수를 보존했다. 학교 PC의 실제 보안 정책·설치·일반 실행을 시험한 것은 아니다.
- [양 OS 회귀 CI36979736245](https://github.com/piman-code/goedusplit/actions/runs/36979736245) 성공. Python229개 중 Mac222개 성공/7개 skipped, Windows218개 성공/11개 skipped. 해당 OS의 필수 검사는 실행했고 플랫폼 비적용·선택 외부 변환기는 제외했다. Node43개씩 성공. 후보 입력이 없어 pair는 정상 skipped이며 새 앱 빌드가 아니다.
- 실제 GitHub 학교 artifact를 내려받아 전달 ZIP28파일·CRC전체·manifest27개 지문·원본과 같은 검사기 bytes·합성 키트6개 검사를 재확인했다. 상태 폴더·개인 설정·학생 원자료는 전달하지 않는다.

초기 [CI36978911920](https://github.com/piman-code/goedusplit/actions/runs/36978911920)은 정상 ZIP을 읽는 단계에서 실패했다. Windows PowerShell5.1에서 압축 타입 assembly를 명시적으로 로드하고 진단 단계·예외 종류·줄 번호만 추가한 뒤 실제 재실행이 통과했다. 실패 원본은 보존했고 검사 기준을 완화하지 않았다. 기존 두 OS [602e77d 회귀36978911841](https://github.com/piman-code/goedusplit/actions/runs/36978911841)도 통과했다.

## 학교에서 받을 파일

[학교 전달 artifact11214639642](https://github.com/piman-code/goedusplit/actions/runs/36979736361/artifacts/11214639642)를 내려받아 [학교 검사 안내](WINDOWS_SCHOOL_QA.md)를 따른다. GitHub artifact의 바깥 ZIP과 그 안의 전달 ZIP을 구분하며 로그인·접근 권한이 필요하다. artifact는14일 보관이므로 받은 사본을 보존한다.

| 대상 | SHA256 |
| --- | --- |
| CI에서 받은 내부 전달 ZIP `Goedu-Split-1.0.6-school-check.zip` | `741662962f3a5ad53d91e2d0963b47279bcbfab03e5963ecadf3d43dd7da12ac` |
| 그 안의 앱 portable ZIP | `446a5478fef905f60dee2e83269394c7a2f27f80e9feed7d8fdfad9057563069` |

Mac에서 독립 생성한 전달 ZIP은 `d33da056f1f9cbf11c81ab1945d7582663cb75b90f356c1359458765e29a4ea7`이다. 합성 XLSX/PDF 생성 시각·OS 문서 줄바꿈 때문에 두 전달 ZIP의 지문은 다르지만 **앱 portable ZIP과 검사기 bytes는 동일**하다. 내부 manifest로 각 사본을 확인한다. GitHub API artifact digest는 바깥 다운로드 ZIP의 지문이므로 위 내부 ZIP 지문과 혼동하지 않는다.

## 화면 증거의 한계와 남은 일

CI PNG에서 WebEngine 계산기 한글은 보이지만 Qt 상단·탭·하단의 일부 한글은 네모로 보인다. 필수12개 검사는 글자 가독성을 판정하지 않는다. 코드상 합성 QA는 `MainWindow()`를 만들며, 일반 앱은 `ThemeManager`의 `NanumGothic` 글꼴 테마를 적용한다. 후보에는 한글 글꼴3개가 원본 그대로 포함돼 있다. QA의 글꼴 선택 차이가 가능한 설명이며 **일반 앱 오류로 확정한 것은 아니다**. 등록 성공·학교 OS 글꼴·일반 실행의 실제 한글 표시를 별도로 확인한다.

학교 `--synthetic-qa` 역시 같은 합성 실행 경로다. 그 PNG만으로 일반 앱 글자·테마·교사 가독성까지 통과 처리하지 않는다. [PC 기록 양식](PC_VALIDATION_RECORD.md)의 T08에서 실제 일반 실행의 탭·버튼·상태바·대화상자 한글을 확인한다. 기존 설정을 사용하는 일반 실행과 설치/교체는 승인된 인수 범위에서 진행한다.

Windows Excel 실제 열기, 동일 JSON Mac→Windows→Mac 왕복, 교사 업무 확인, 학교 배율·오프라인, 실제 HWP 변환 환경, 설치·이전 버전 복귀는 아직 미실행이다. main 병합·공개 Release·기존1.0.5 교체도 수행하지 않았다. 이 준비 결과로 학교 사용자 인수 완료를 선언하지 않는다.

로컬 재대조·실행 로그·독립 감사 보고서는 `out_test/school-handoff-20261002-root/`, `out_test/school-helper-ci-36979736361/`, `out_test/school-handoff-20261002-prepush/`에 보존했다. 이 폴더들은 Git 전송 제외이며 GitHub/clean clone에서 로컬 증거로 열리지 않는다. 공개 실행 근거는 위 실제 CI 링크를 사용한다.
