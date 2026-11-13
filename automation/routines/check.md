# 08:20 발송·게시 확인 (매일 — 빠지면 수동 실행)

GitHub 예약 실행은 아침 0~3시간·낮저녁 3~6시간 늦거나 빠지므로 매일 확인한다. 날짜는 오늘(KST).
워크플로를 돌릴 때는 GitHub 도구(actions_run_trigger)를 쓰고, 없으면 `gh workflow run <파일> -f 이름=값` 을 쓴다. 둘 다 안 되면 그 사실을 운영자에게 알린다.

1) `git fetch origin main` 후 오늘 `{날짜}.html` 이 main 에 있는지 본다. 없으면 07:05 제작(그날 새로 뜬 'EDIT H 제작' 세션)이 실패했거나 늦는 것이다 —
   `python3 automation/check_today.py` 의 사유(검증된 소식 부족으로 발행 안 함 등)가 정상적인 건너뜀이면 조용히 끝내고, 실패·중단(사용량 한도 등)이면
   운영자에게 원인을 짧게 알린다. 08:05 이후에도 없으면 rewind.yml(예비 호)이 08:05 에 대신 발행한다 — 그것도 안 돌았으면 workflow_dispatch(dry_run=false)로 돌린다.
1-1) 오늘 content 에 `"rewind": true` 가 있으면 예비 호가 나간 날이다 — 제작이 왜 멈췄는지(`run-claim/{날짜}-claude` 표시가 있었나, Actions 알림) 확인해 운영자에게 알린다
   (예비 호 날엔 릴스를 올리지 않는 게 정상). 평일 정규 호인데 `source_mode` 가 `fallback` 이면 안장출근길을 왜 못 썼는지(늦게 올라옴·접속 실패) 보고에 한 줄.
2) 호가 있으면: main 의 `automation/sent/{날짜}.json` 이 없으면 send-newsletter.yml 을 workflow_dispatch(date={날짜})로 돌린다.
   인스타: `python3 automation/ig_plan.py` 의 저녁 게시인 날은 **아침엔 캐러셀만** 확인한다 — `automation/ig_posted/{날짜}.json` 에 carousel permalink 가 없으면
   post-instagram.yml 을 mode=post, key={날짜}, only=carousel 로 돌린다. 그리고 **어제** AI 영상 릴스(`instagram/{어제}/reel_ai.mp4`)가 있는데
   reel permalink 가 없거나, 웹툰(`instagram/{어제}/comic/`)이 있는데 comic permalink 가 없으면 mode=post, key={어제}, only=reel 로 돌린다.
   주말·예비 호 날은 AI 영상이 없어 릴스가 없는 게 정상이다 — 이미지를 이어 붙인 릴스는 2026-11-13~ 올리지 않는다(운영자 11/12).
   **평일(월~금) 정규 호인데 어제 `reel_ai.mp4` 가 없으면** 07:45 릴스 작업이 멈춘 날이다(2026-11-13 운영자 '릴스 영상은 주말만 제외' — 평일은 매일 만든다):
   이유(크레딧 부족·검수 탈락·작업 세션이 안 뜸)를 `automation/CHANGELOG.md` 맨 위와 `automation/alerts/{어제}.json` 에서 찾아 보고에 한 줄 적는다(지난 날 영상을 다시 만들지는 않는다). 이미 돌고 있는 'Post EDIT H to Instagram' 실행(in_progress/queued)이 있으면 기다린다
   (중복 실행 금지 — 기록이 있으면 스크립트가 알아서 건너뛴다).
2-1) 저녁 일정 사슬(evening.yml, 'EDIT H evening chain'): 오늘 호 push 로 시작해 17:30 까지 기다렸다가 18:00 주간 특집·19:30 릴스·20:45 점검·21:30 성과 수집을 실행한다.
   오늘 사슬 실행이 in_progress 인지 보고(정상), **어제** 사슬이 실패·취소로 끝났으면 원인(Actions 작업·단계)을 보고에 한 줄.
   어제 성과 스냅숏(`automation/metrics/daily/`)이 21:00 뒤에 모였는지도 본다.
3) 세로 프레임: 오늘 `instagram/{날짜}/reel_frames/` 에 r1~r4 JPEG 가 있는지 본다(스토리 훅 화면이 r1 을 쓴다). 없으면 빌드 경고(넘침 등) — 보고에 한 줄.
4) 모두 정상이면 한 줄로만 남기고 끝낸다(평일이면 `python3 automation/compare_anjang.py` 의 '겹침 N/10'·'큰 소식 다룸 N/M' 을 그 한 줄에 붙인다).
   수동으로 돌렸거나 실패가 있으면 원인(예약 미실행·루틴 지연·API 오류·GitHub 러너 미할당)을 찾아 운영자에게 한국어로 짧게 알린다
   (PushNotification 한 줄 + 마지막 답). 코드 문제면 고쳐서 PR(작업 브랜치 `routine/check`) → selftest 초록 → 머지한다(발송·게시 경로 머지는 06:00~08:30·18:00~20:00 피하기 —
   급하면 workflow_dispatch 로 먼저 메운다). GitHub 러너 미할당 실패는 alert.py 가 한 번 자동 재실행한다.
