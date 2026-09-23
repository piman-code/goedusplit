# Goedu-Split 작업 인계 (HANDOFF)

어느 플랫폼(Codex, Claude Code, Kilo 등)이든 이 파일과 git 기록만으로 이어서 작업할 수 있게 유지한다.
완료 조건 하나를 끝낼 때마다 **테스트 → 이 파일 갱신 → 로컬 커밋** 순서로 남긴다. 끝에 몰아서 쓰지 않는다.

- 마지막 갱신: 2026-09-23 23:55 KST
- 작업 브랜치: `work/1.0.3-hardening`
- 마지막 체크포인트 커밋: 이 파일을 추가한 커밋 (`git log -1 -- docs/HANDOFF.md`로 확인)

## 최종 목표

NEIS 정오표·문항정보표 기반 성취평가 분석과 **추정분할점수 설계**를 인터넷 없이 교사 PC에서 안전하게 쓰는 Windows·macOS 앱.
시험지 오류 점검과 외부 AI는 교사가 명시적으로 켜는 선택 기능으로만 붙인다.

## 단계 로드맵

| 단계 | 내용 | 추천 모델 / 강도 | 상태 |
|---|---|---|---|
| 1 | 작업 보존, 내보내기 가명화, CSV 수식 차단, CI 테스트, 이 인계 파일 | Claude Code `claude-opus-5-5` 또는 Codex `gpt-6-sol` / high | 진행 중 |
| 2 | 예측-실측 보정 리포트 (교사 예상정답률 vs 실제 수준별 정답률) | `gpt-6-sol` / medium | 대기 |
| 3 | 시험지(HWP/HWPX/PDF)에서 문항 번호·배점·유형만 로컬 추출 (kordoc 동봉) | `gpt-6-sol` / high, 패키징 설계만 `gpt-6-astra` / high | 대기 |
| 4 | 선택형 온라인 검토 모듈 (로컬 규칙 점검 → 복사-붙여넣기 브리지 → Jev 전송 게이트) | 설계·보안 `gpt-6-astra` / high → 구현 `gpt-6-sol` / high | 대기 |
| 부채 | React 원본 소스 복구, `app/main_window.py` 분할 | 필요할 때만 | 대기 |

- 매 단계 완료 판정은 구현과 다른 모델 계열이 맡는다(효과는 미측정).
- ultra는 비권장: 작업이 한 파일에 몰려 자동 위임 분리 실익이 작다.

## 1단계 완료 조건과 진행

- [x] 1. `work/1.0.3-hardening`에 기존 1.0.3 미커밋 작업 커밋 (`c43cc52`). stash 2개는 그대로 둠.
      stash@{0}의 코드·테스트는 `archive/exam-issue-2026-07` (`ed7a27a`)에 xlsx 없이 보존.
- [x] 2. 이 인계 파일 생성
- [ ] 3. CSV·그래프·포트폴리오 내보내기 기본값 가명화, 실명은 명시 선택 + 경고 후에만
- [ ] 4. CSV 수식 주입 차단 (`= + - @` 탭·CR 시작 값)
- [ ] 5. `.github/workflows/windows-build.yml`에 unittest, node test, privacy audit 추가
- [ ] 6. Windows 실기 검증 체크리스트 (아래, 사람 작업)

## 다음 첫 작업

완료 조건 3: 학생 식별정보가 나가는 내보내기 경로를 전수 확인하고, 가명화·CSV 처리를 작은 순수 함수로 분리한 뒤 테스트를 붙인다.

## 검증 명령

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests
node --test tests/test_expected_rate_web.cjs
```

1단계 시작 시점 기준: Python 65개, Node 43개 통과.

## 경계 (현재 유효한 사용자 승인)

- 허용: 로컬 브랜치 생성, 로컬 커밋.
- 금지: push, 배포, 코드서명, 패키지 설치, 네트워크 사용, 실제 학생자료 열람, `rm` 계열 삭제(휴지통만).
- 이번 단계에서 건드리지 않음: 시험지·AI 기능, React 번들, 계산 계약(`app/expected_rates.py`)과 저장 형식.
- 두 플랫폼이 같은 작업 폴더에서 동시에 작업하지 않는다.

## 보관 현황과 주의 파일

- `stash@{0}` (2026-07): 시험지 오류 점검 작업. 미추적 파일에 xlsx 4개 포함 — 실제 학생자료일 수 있음, 내용 미열람.
  `학생 답 정오표data(1학년).xlsx`, `지필평가 교과목별 일람표(공통수학1).xlsx`, `문항정보표(공통수학1) 샘플.xlsx`, `예상추정분할점수조회(공통수학1)1학기 1차.xlsx`.
  stash는 push되지 않지만 로컬 git 객체에 남아 있다. 처리 방법은 사용자 결정 필요.
- `stash@{1}` (2026-06-11): `app/spliter_ox_source/` React 원본(Vite+TS)이 있다. 이후 빌드 JS를 직접 수정해 왔으므로 복구 시 현재 번들과 대조가 필요하다.
- `sample_data/` (gitignore): `학생답 정오표(1학기 1차)data.xlsx`는 이름에 '샘플'이 없어 실제 자료일 수 있음, 내용 미열람.
- `archive/exam-issue-2026-07` push 전: 테스트 픽스처의 가짜 경로 `/Users/<로컬 사용자>/Desktop/...`를 일반 이름으로 바꿀 것.
- 원격 `origin`은 GitHub 저장소다(공개 여부 미확인). push 전 개인정보 감사를 먼저 돌린다.

## Windows 실기 검증 체크리스트 (사람 작업)

에이전트가 Mac에서 대신할 수 없다. Windows PC에서 합성 자료로 확인한다.

1. 빌드: `python -m PyInstaller --noconfirm --clean goedusplit.spec` 성공, `dist\Goedu-Split\Goedu-Split.exe` 실행.
2. 첫 실행: SmartScreen 안내 문구, 한글 폰트, 창 크기 1280x800·1366x768에서 입력 패널 접기.
3. 불러오기: 한글 경로·공백 있는 폴더의 정오표·문항정보표 불러오기, 분석 실행.
4. 예상정답률 탭: 화면 표시(WebEngine), 소수 정답률 입력, 저장·불러오기, NEIS 입력표 XLSX 저장 후 Excel에서 열기.
5. 내보내기: CSV를 Excel로 열었을 때 한글 깨짐 없음, 기본 가명 확인, 실명 선택 시 경고 확인.
6. 오프라인: 네트워크를 끊은 상태에서 1~5가 동일하게 동작.
7. 결과 기록: 이 파일의 해당 항목에 날짜·Windows 버전·결과를 적는다.

## 재개 프롬프트 (다른 플랫폼에서 붙여넣기)

```text
작업 위치: Goedu-Split 저장소 루트 (Mac: Projects/003-goedusplit)
먼저 읽기: docs/HANDOFF.md → git status, git log -5 → HANDOFF의 '다음 첫 작업'에 필요한 파일만.
상황: 이전 실행이 사용 한도 등으로 중간에 끊겼을 수 있다. 마지막 커밋 이후의 미커밋 변경은 버리지 말고, HANDOFF의 현재 상태와 대조해 끝난 것과 덜 끝난 것을 먼저 판정하라. 테스트를 한 번 돌려 현재 상태를 확인하라.
진행: HANDOFF의 최종 목표·현재 단계·완료 조건·경계를 그대로 따른다. 완료 조건 하나마다 테스트 → HANDOFF 갱신 → 로컬 커밋.
경계: push·배포·설치·네트워크·실제 학생자료 열람은 HANDOFF에 사용자 승인 기록이 없으면 하지 않는다. 다른 에이전트가 같은 폴더에서 작업 중이면 멈추고 알린다. 삭제는 휴지통만.
보고: 한국어로 이번에 끝낸 것 / 미검증 / 다음 첫 작업.
```

## 작업 기록

- 2026-09-23: 1단계 시작. 조건 1·2 완료.
