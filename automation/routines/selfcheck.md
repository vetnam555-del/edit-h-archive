# 전환·환경 점검 (필요할 때만 — 예약 없음)

'매번 새 세션' 구조가 끝에서 끝까지 도는지 확인하는 짧은 루틴이다. 운영 대화가 구조를 바꾼 뒤 시험할 때만 배차한다.
(예약 → 배차 세션 → 작업 세션 → 지시 파일 읽기 → main 에 직접 푸시까지 사람 없이 되는지 본다.)

1. 한 줄씩 따로: `git fetch origin main` → `git checkout main` → `git pull --ff-only origin main`
2. `python3 automation/check_today.py | head -5` 를 실행한다(출력은 보고에만 쓴다).
3. 도구 확인: ToolSearch 로 다음 도구가 있는지 본다 — PushNotification, GitHub 의 create_pull_request·actions_run_trigger,
   **드롭샷(Dropshot AI Studio)** 의 generate_image·generate_video·get_generation·get_credit_balance(ToolSearch 'dropshot' 또는 'get_credit_balance' —
   이름에 Higgsfield 가 없는 쪽. 있으면 `get_credit_balance` 를 한 번 불러 잔액 숫자를 적는다. **그림·영상은 만들지 않는다** — 크레딧이 든다),
   힉스필드의 generate_audio_batch(목소리)·balance. 그리고 `python3 -c "import faster_whisper"` 가 되는지.
4. `automation/CHANGELOG.md` 에서 가장 위에 있는 `### ` 제목 줄 바로 아래에 한 줄을 더한다(날짜·시각은 지금 KST, 도구는 있으면 ○ 없으면 ×):
   `- (점검) YYYY-MM-DD HH:MM KST — 작업 세션이 지시 파일을 읽고 main 에 직접 올렸다. 도구: 알림 ○ · GitHub PR ○ · GitHub Actions ○ · 드롭샷 그림 ○ 영상 ○ 확인 ○ 잔액 23968 · 힉스필드 목소리 ○ · faster_whisper ×`
5. `git add automation/CHANGELOG.md` → `git commit -m "Routine self-check YYYY-MM-DD"` → `git push origin HEAD:main`
   (거절되면 `git pull --rebase origin main` 후 다시). 다른 파일은 건드리지 않는다. PR 은 만들지 않는다.
6. 마지막 답: 푸시한 커밋 id 와 도구 확인 결과 한 줄.
