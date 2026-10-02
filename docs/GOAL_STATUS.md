# Goal 현재 상태 — 2026-10-02

**상태: 자율 개발 완료 / 사용자 인수 대기 / 공개 배포 미실행.**

사용자 최신 요청에 따라 이번 목표는 [D01~D09 자율 개발 완료](DEVELOPMENT_PLAN.md)다. 승인된 `codex/desktop-candidates-1.0.6` push·CI·필요한 수정·검증·기록을 수행했다. 최초 Goal 도구의 objective에는 학교 인수 T조건이 남아 있지만, 이번 판정은 사용자의 명시적인 범위 변경을 따른다. T01~T09를 통과로 바꾸거나 새 Goal을 중복 생성하지 않는다.

## 확정 후보와 증거

- 앱 버전1.0.6, 후보 소스 `a7f7d95b6a751606ac75d1f6958ed9686bd9884b`.
- [후보 CI36952967141](https://github.com/piman-code/goedusplit/actions/runs/36952967141) source·Mac arm64·Windows x64·pair 모두 성공. [동일 SHA push36952966860](https://github.com/piman-code/goedusplit/actions/runs/36952966860)도 성공.
- 양 OS Python228개 OK(Mac7/Windows11개 플랫폼 전용·선택 kordoc 생략), Node43개·빌드 전 재검사 통과. 해당 OS의 필수 개발 검사는 생략하지 않았다.
- 양 OS frozen 후보의 필수12개 실행 QA·오류0. 실제 받은 Mac DMG 내부 앱도 읽기 전용으로 직접 실행해12개·오류0·동일 실행 파일 지문 확인.
- 최종10개 파일 수집, SHA256SUMS의9개 지문·동일 source SHA/버전·안내 LF bytes 대조 통과. Windows ZIP 전체 CRC·AMD64 실행 파일·필수 Qt/웹/폰트·내장 출처·추적 자산 독립 대조 통과.
- 개발 소스의 실제 Mac 분석·내보내기13개, NEIS/보정25개, 시험지8개, native 창2개·접기4개, 작은 화면 offscreen WebEngine4개 증거는 동일한 앱 코드와 연결했다.

최종 파일은 `artifacts/Goedu-Split-1.0.6-a7f7d95/`, 실제 재검증 보고서는 `out_test/goal-20261002-final-a7/`에 보존했다. [완료 판정표](AUTONOMOUS_COMPLETION.md)에 파일 지문·검증 범위·독립 최종 결과를 기록했다. 후보 소스와 후속 문서 기록 커밋은 구분한다.

## 보존과 남은 인수

기존 설치 앱·원래dist는1.0.5, 원래 `.venv`와 stash2개 refs는 보존 재확인했다. main SHA도71d9b33 그대로다. 기존 사용자 설정·실제 학생자료·stash 내용은 열지 않았고 설치를 교체하지 않았다.

[PC 기록 양식](PC_VALIDATION_RECORD.md)의 T01~T09는 미실행이다. 학교 Windows·Excel 실제 열기·Mac→Windows→Mac JSON 왕복·학교 배율/오프라인·교사·실제 HWP 의존성·설치/복귀는 별도 사용자 인수다. [개발 안내](DEVELOPMENT.md), [릴리스 준비](RELEASE_CANDIDATES.md), [백업/복귀](BACKUP_AND_ROLLBACK.md)를 따른다. main 병합·공개 Release·설치 교체는 실행하지 않았다.

알려진 제약: 기본 전부 펼침의 작은 분석 창은 높이가 부족할 수 있으며 기존 접기 버튼으로 그래프 축/제목·학생4행 접근을 검증했다. 실제 학교 배율·교사 시각 검토는 대기다. native HWP 외부변환기는 선택 의존성, 스캔 PDF OCR은 범위 밖이다. Mac ad-hoc 서명은 Apple 공증이 아니고 Windows 유료 서명은 도입하지 않았다. Intel Mac·Windows ARM은 지원 검증 대상에 포함하지 않았다.

## 진행 이력

UTF-8 파일 읽기·Mac 전용 검사 플랫폼 범위, Windows CMD inline 버전 조회, 안내 CRLF/LF 불일치를 실제 실패 원인에 맞춰 수정했다. 품질·출처·파일 동일성 검사를 완화하지 않았다. 이전 후보는 새 후보로 재표시하지 않고 보존했다. [상세 검증 이력](VERIFICATION_20261002.md)과 [당시 진행 기록](https://github.com/piman-code/goedusplit/blob/a7f7d95b6a751606ac75d1f6958ed9686bd9884b/docs/GOAL_STATUS.md)에 원래 결과와 승인 경계를 남겼다.


## 완료 판정

완료판정관이 실제 파일·CI·동일 앱 코드의 source/native 증거를 직접 재대조해 D01~D09 모두 충족, 치명 문제0으로 판정했다. `out_test/goal-20261002-final-a7/INDEPENDENT_COMPLETION.json`의 SHA256은 `7ab1b358d4c3f517ad5be106d18810441b726fc489c84ea0e01730271f4a1b4e`다. 문서와 로컬 DevDocs 기록까지 완료한 뒤 Goal 상태를 complete로 마무리한다. 이번 완료는 사용자의 범위 변경 뒤 자율 개발 완료이며 학교 인수·공개 배포 완료가 아니다.
