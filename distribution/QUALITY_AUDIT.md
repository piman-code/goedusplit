# Goedu-Split 1.0.6 후보 품질 기준

상태: 개발·검증 진행 중. 기존 문서는 [이력](history/QUALITY_AUDIT-before-20261002.md)에 보존했다. 과거 AI 검사는 현재 필수 기준이 아니다.

자율 개발의 필수 기준은 [DEVELOPMENT_PLAN D01~D09](../docs/DEVELOPMENT_PLAN.md), 학교 사용자 인수 기준은 같은 문서의 T01~T09다. 현재 증거는 [완료 판정표](../docs/AUTONOMOUS_COMPLETION.md)·[GOAL_STATUS](../docs/GOAL_STATUS.md), 실제 PC 절차는 [수동 QA](MANUAL_QA_CHECKLIST.md)를 따른다.

정식 후보는 동일 SHA·버전의 Mac arm64와 Windows x64 앱이다. 정확한 의존성·합성 검사·소스/번들 감사·필수 파일·실행 파일 출처·checksum을 확인한다. 기존 배포 파일을 새로운 성공 파일로 재사용하지 않는다. 두 플랫폼 중 한쪽 실패, 실제 PC 미검증, 교사 확인 대기는 배포 준비 완료가 아니다.

교사 사용의 핵심은 로컬 분석 → 예상정답률·NEIS 표 → JSON 저장·PC 왕복 → 예측–실측 비교다. 계산 계약·가명 기본값·취소 보존·문항 가져오기 실패 안내·작은 화면 접근성을 실제 후보에서 확인한다. HWP 성공/부재를 구분하고 빈 결과를 성공으로 기록하지 않는다.

개발 완료·배포 준비·공개 배포를 별도로 기록한다. 공개 Release와 기존 설치 교체는 최종 파일·검증·복귀안을 제시하고 승인된 범위에서 진행한다.
