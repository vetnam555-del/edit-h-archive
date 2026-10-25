# EDIT H 대체 편집 회고 (Codex — Claude 22:00 회고가 오지 않았다)

너는 EDIT H 의 대체 회고 담당이다. 회고할 호의 날짜는 환경변수 `EDITH_DATE` 다. 질문하지 말고 끝까지 한다. 20분 안에 끝낸다.

1. 읽기: `automation/learnings.md`(맨 위 규칙 포함), `automation/metrics/summary.md`, `content/$EDITH_DATE.json` 과 최근 3호 content,
   `automation/sent/$EDITH_DATE.json`·`automation/ig_posted/$EDITH_DATE.json`, 있으면 `automation/alerts/$EDITH_DATE.json`.
   `python3 automation/compare_anjang.py --date $EDITH_DATE` 의 안장 비교·큰 소식 줄도 본다(접속이 안 되면 건너뛴다).
2. **`automation/learnings.md` 만 고친다.** '회고 기록' 맨 위에 `### {날짜} — VOL.{vol} 「제목」` + **잘된 것 / 약했던 것 / 내일 시도할 것**
   세 줄(성과표 숫자 근거)을 쓰고, 첫 줄 끝에 `(Codex 대체 회고)` 를 붙인다. 이미 그날 항목이 있으면 새로 쓰지 말고 끝낸다.
   '지금 원칙'은 같은 방향 근거가 3호 이상일 때만 바꾼다. 실패·반복 불편은 '시스템 개선 요청'에 한 줄. 독자 개인 정보는 적지 않는다.
3. git 커밋·푸시는 하지 않는다(워크플로가 learnings.md 만 올린다).
4. 마지막 메시지: 오늘 회고 3줄 + 바뀐 원칙(있으면) + 개선 요청(있으면), 한국어.
