# 1.0.6 배포 후보 보완 범위

공개 릴리스가 아닌 검증용 후보다. CI 성공과 실제 PC 검사, 학교 인수는 각각 구분한다.

## 포트폴리오

- 기존 화면은 Data 탭에서 별도 저장하기 전까지 분석 완료 후에도 비어 있었다.
- 현재 분석을 미저장 미리보기로 표시한다. 포트폴리오 탭의 현재 과목 저장으로 명시적으로 보관한다. 자동 저장은 하지 않는다.
- 학생 해시, 익명 저장, 기존 버전 1 기록 읽기와 현재 분석을 통한 이름 복원을 유지한다. 같은 PC 설정의 해시 키가 필요하다.
- 기존 저장 결과와 같은 미리보기는 중복 표시하지 않는다. 저장 파일은 고유 이름으로 배타적으로 생성하며 기존 기록을 덮어쓰지 않는다.
- 학기·차수를 기록하며 다과목 학생 선택과 상담 리포트를 frozen synthetic QA에서 검사한다.
- 손상된 JSON, 잘못된 구조, 비유한 점수는 개별 파일 단위로 건너뛰고 개수를 안내한다. 원본은 보존한다.

## Windows 용량

Qt의 공식 Windows 배포 도구는 release와 debug WebEngine 리소스를 별도로 선택한다.
이 후보도 release 대응 파일이 수집된 경우에만 중복 `.debug.pak`와 `v8_context_snapshot.debug.bin`을 COLLECT 이전에 제외한다. 기존 설치 파일이나 빌드 산출물을 삭제하지 않는다.

출처: https://github.com/qt/qtbase/blob/dev/src/tools/windeployqt/main.cpp
설명: https://doc.qt.io/qt-6/qtwebengine-deploying.html

WebEngine 런타임, release devtools 리소스, locales, 소프트웨어 OpenGL 호환성 DLL, 한국어 글꼴, 라이선스는 유지한다. 계산기 웹엔진 자체를 교체하는 더 큰 축소는 별도 구조 변경과 호환성 검증이 필요하다.

## 검증과 배포 경계

합성자료만 사용한다. 새 결과 폴더, 격리 INI·appdata·cache, off-the-record WebEngine과 네트워크 차단으로 검사한다.
CI는 소스 테스트, 계산기 계약 검사, Windows/Mac 패키징, 양 플랫폼 frozen QA와 동일 커밋 증명을 수행한다.
실제 Windows 검사는 별도 보고서의 EXE SHA256, 원래 창 유지, 그래프·포트폴리오 캡처, 저장·재읽기 결과로 확인해야 한다.

학교 인수, 실제 교사 사용성, Windows 설치 프로그램 실행, 서명·운영체제 보안 경고 확인, 실제 Mac 사용자 PC 실행은 자동 검사 통과로 대체되지 않는다. 공개 배포와 보안 정책 변경은 수행하지 않는다.

## 실제 Windows 창 보완

중간 e99fabf 후보에서 주 창은 유지됐지만 분석 중 부모 없는 일반 창 두 개가 잠시 나타났다. 그래프 교체 시 이전 캔버스의 setParent(None)을 제거하고 숨긴 상태에서 부모를 유지한 채 deleteLater로 처리한다. Qt 객체의 수명 처리이며 파일 삭제는 하지 않는다. frozen QA에서 독립 그래프 창의 Show 이벤트가 없는지를 별도로 검사한다. 상담 리포트 요약은 QTextBrowser에 맞는 네 열 표로 배치한다.
