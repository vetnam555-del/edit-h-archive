# 22:00 편집 회고 (매일)

오늘(KST) 호의 회고를 쓴다. 지켜보는 사람이 없으니 질문하지 말고 끝까지 진행한다.

1. 한 줄씩 따로 실행: `git fetch origin main` → `git checkout main` → `git pull --ff-only origin main`
1-1. 성과표 먼저 받기: `python3 automation/request_metrics.py` 를 Bash timeout 600000 으로 실행한다(성과표가 오늘 21:00 이후 것이 아니면 수집 요청을 푸시하고
   최대 9분 기다린다). 종료 코드 0 이면 main 이 최신, 2 면 기존 성과표로 진행하고 회고 기록에 '성과표 지연' 한 줄, 1 이면 `git pull --rebase origin main` 후 한 번만 다시.
2. 읽기: `automation/learnings.md`(맨 위 규칙 포함), `automation/metrics/summary.md`, 오늘 `content/{날짜}.json` 과 최근 3호의 content,
   `automation/sent/{날짜}.json`·`automation/ig_posted/{날짜}.json`, 있으면 `automation/alerts/{날짜}.json`.
   `python3 automation/compare_anjang.py --date {날짜}` 의 안장 비교·큰 소식 줄도 본다(fallback 호면 '안장 칸 N/5' 안내 줄대로 메인 5가지 중
   RUNBOOK 1-4 의 7 ①~③ 칸에 드는 수를 눈으로 세어 회고에 한 줄).
3. `automation/learnings.md` 만 고친다: '회고 기록' 맨 위에 `### {날짜} — VOL.{vol} 「제목」` + **잘된 것 / 약했던 것 / 내일 시도할 것** 3줄
   (성과표 숫자 근거, 숫자가 없으면 제목 유형·H PICK 깊이·'그래서 뭐가 달라져?'의 구체성·출처를 스스로 평가). '지금 원칙'은 같은 방향 근거가 3호 이상일 때만
   바꾸고(최대 10개, 근거 날짜), 부족하면 '가설'. 실패(운영 알림 포함)·카드 넘침·빌드 오류·반복 불편은 '시스템 개선 요청'에 한 줄(코드는 고치지 않는다).
   회고 기록은 최근 14개만 자세히. 독자 개인 정보는 절대 적지 않는다. 회고 기록에 오늘 항목이 이미 있으면 새로 쓰지 말고 보탤 것만 보탠다.
4. `git add automation/learnings.md` → `git commit -m "Editor retrospective {날짜}"` → `git push origin HEAD:main`(거절되면 `git pull --rebase origin main` 후 다시).
   수집 요청 파일 외 다른 파일은 수정하지 않는다. 새 브랜치·PR 은 만들지 않는다.
5. 마지막 답: 오늘 회고 3줄 + 바뀐 원칙(있으면) + 개선 요청(있으면).
오늘 호가 없으면 그 사유만 회고 기록에 한 줄 남기고 끝낸다.
