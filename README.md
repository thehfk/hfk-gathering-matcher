# HFK 게더링

멤버가 만나고 싶은 사람의 조건(연차·직무·주제)을 직접 선택해 그룹으로 매칭되는 네트워킹 프로그램의 신청·자동 배정 웹페이지.

## 사용

- **웹에서 열기**: (배포 후 GitHub Pages URL)
- **로컬 실행**: `index.html`을 브라우저로 열면 바로 동작 (외부 의존성 없음)

## 파일

- `index.html` — 사용자·관리자 UI + 매칭 알고리즘 (단일 파일)
- `matcher.py` — 매칭 알고리즘 Python 프로토타입
- `apps-script.gs` — Google Sheets 저장용 Apps Script 백엔드

## Google Sheets 연동 (선택)

신청 내용을 Google Sheets에 자동 저장하려면:

1. [sheets.new](https://sheets.new)로 새 스프레드시트 생성
2. 확장 프로그램 → Apps Script → `apps-script.gs` 붙여넣기 → 저장
3. 배포 → 새 배포 → 유형: 웹 앱 / 실행: 나 / 액세스: 모든 사용자
4. 발급된 웹 앱 URL을 페이지의 관리자 → Google Drive 연동에 입력

## 알고리즘

요구서 6장 기반:
- 매칭 점수 100점 (기준 30 + 세부 30 + 연차 15 + 직무 15 + 주제 20 + 고민-경험 10)
- 방식 C: 기준별 우선 분리 → 잔여 인원 통합 배정
- 그룹 크기 4~6명 (목표 5명)
