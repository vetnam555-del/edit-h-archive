# 07:40 제작 — 오늘 호 만들기 (매일, 주말·공휴일 포함)

운영자가 승인한 자동 발행 작업이다. 지켜보는 사람이 없으니 질문하지 말고 끝까지 진행한다.
메일 발송·인스타 게시는 GitHub Actions 가 08:30 에 하므로 여기서 보내지 않는다.

1. 아래 명령을 한 줄씩 따로 실행한다(&& 로 묶지 않는다): `git fetch origin main` → `git checkout main` → `git pull --ff-only origin main`
2. `python3 automation/check_today.py` — `publish: false` 면 사유를 한 줄로 보고하고 끝낸다.
   `publish: true` 면 **바로** `python3 automation/codex_fallback.py claim claude` 로 '제작 시작' 표시를 남긴다
   (07:55 보험 예약·Codex 자동 대체·예비 호가 이 표시를 본다 — RUNBOOK 을 읽기 전에 먼저 남긴다).
3. `automation/RUNBOOK.md` 를 처음부터 읽고 0~6단계를 순서대로 그대로 수행한다(날짜는 오늘 KST. 2번에서 한 check_today·claim 은 다시 하지 않아도 된다).
4. 목표는 **08:15 전 푸시**(08:30 발송). 평일엔 안장출근길을 07:55 까지 기다려도 된다(RUNBOOK 1-1).
   푸시는 `git push origin HEAD:main`. 거절되면 `git pull --rebase origin main` 후 다시 푸시한다.
   푸시 직전에 `git fetch origin main` 으로 `origin/main:{날짜}.html` 이 이미 있는지 보고, 있으면(다른 실행이 먼저 올림) 푸시하지 않고 그 사실만 보고한다.
   PR 은 만들지 않고, RUNBOOK 5단계의 발행 산출물 외 파일은 수정하지 않는다.
5. 출처는 RUNBOOK 1-3 그대로 지킨다. 특히:
   - 숫자·날짜·고유명사는 두 번째 기사 본문에서도 같은 값을 직접 찾은 뒤에만 쓰고, 빌드 전에 `python3 automation/check_sources.py` 를 돌린다.
   - 실적·공시 이야기는 가능하면 회사 공시(DART 등) 원문을 출처에 함께 건다.
   - 결론(takeaway)은 '지켜보세요' 대신 지금 할 수 있는 한 가지(해지·비교·확인할 곳)로 쓴다.
   - 기사는 저장소의 `automation/read_article.py` 로 읽는다(임시로 만든 읽기 도구는 쓰지 않는다).
6. 마지막 답은 RUNBOOK 6단계 형식의 보고로 끝낸다. 08:15 까지 푸시하지 못했으면 이유를 PushNotification 한 줄로도 알린다.
