# 늦은 발행 — 예비 호가 나간 날, 운영자가 "오늘 자 발행해줘"라고 했을 때

**언제 쓰나**: 아침 제작이 멈춰 예비 호('놓쳤다면, 다시 볼 만한 5가지')가 대신 나간 날, **운영자가 그날 정규 호를 내 달라고 직접 말했을 때만**.
AGENTS 1절 '예비 호가 나갔으면 그날 제작은 하지 않는다'의 예외다 — 자동 루틴이 스스로 하지 않는다.
처음 쓴 날: 2026-11-13(운영자 "오늘자 안올라왔는데? 발행해줘" — 아침에 Claude 사용량 한도로 제작이 멈췄다).

**하는 일**: 그날 정규 호를 만들어 예비 호 자리에 올리고(같은 날짜·같은 VOL), 메일을 한 번 더 보내고, 인스타 캐러셀을 새로 올린다.
지켜보는 사람이 없으니 질문하지 말고 끝까지 진행한다. 릴스·웹툰은 여기서 만들지 않는다(정규 호가 올라온 뒤 따로 뜨는 릴스 작업 세션이 `automation/RUNBOOK_REEL.md` 대로 한다).

## 순서

1. **준비** — 한 줄씩 따로: `git fetch origin main` → `git checkout main` → `git pull --ff-only origin main`.
   `python3 automation/check_today.py` 는 `publish: false`(이미 발행됨)라고 답한다 — **이 절차에서는 그 답을 무시하고 진행한다**(나머지 값은 평소처럼 쓴다).
   `next_vol` 은 오늘 날짜에 이미 있는 VOL(예비 호가 쓴 번호)을 그대로 준다 — **그 번호를 쓴다**(새 번호를 만들지 않는다).
   `recent_issues`·`recent_item_titles` 에 오늘 예비 호가 섞여 있으면 빼고 본다.
2. **예비 호 기록 떠 두기**(원고를 덮어쓰기 전에 먼저):
   ```bash
   mkdir -p automation/replaced/{오늘}
   git show HEAD:content/{오늘}.json > automation/replaced/{오늘}/content.json          # 예비 호 원고(기록)
   git mv automation/sent/{오늘}.json automation/replaced/{오늘}/sent.json               # 이 기록이 있으면 발송이 건너뛴다(없으면 넘어간다)
   git mv automation/ig_posted/{오늘}.json automation/replaced/{오늘}/ig_posted.json     # 이 기록의 carousel 이 있으면 새 캐러셀이 안 올라간다(없으면 넘어간다)
   ```
   이 파일들에는 구독자 주소가 없다(수만 있다) — 내용을 고치지 않고 옮기기만 한다.
3. **제작** — `automation/RUNBOOK.md` 를 처음부터 읽고 0~4단계를 그대로(소스·출처 2건·`check_sources.py`·빌드). 다른 점만:
   - 안장출근길 오늘 글은 이미 올라와 있다 — 기다리지 말고 `python3 automation/fetch_anjang.py --since {직전 정규 호 날짜}` 로 읽어 평소처럼 고른다
     (`source_mode` 는 RUNBOOK 1-1 정의대로. 주말이면 안장이 없다).
   - `content/{오늘}.json` 은 예비 호 것(`"rewind": true`)이다 — 새 원고로 **통째로 덮어쓴다**(`rewind` 키 없이, `vol` 은 1번의 번호).
   - 리드(인사말) **첫 문장**에 늦은 사정을 한 번만: "오늘 아침엔 지난 이야기를 보내드렸어요. 늦었지만 오늘 소식을 전합니다." (변명·과장 없이 이 정도로)
   - '오늘 아침'·'출근길에'처럼 때를 말하는 표현은 보내는 때(낮·저녁)에 어색하지 않게 쓴다(저녁이면 인사도 저녁 인사로). 아침에 이미 끝난 일정은 '오늘 챙길 것'에 넣지 않는다.
   - 금요일 주간 특집 원고(RUNBOOK '금요일 주간 특집')는 17:20 KST 가 넘었으면 만들지 않는다(18:00 게시 시각을 지났다). 정규 호 푸시를 늦추지 않는다.
4. **빌드 뒤 확인** — `instagram/{오늘}/ig/` 에 예비 호 때 만든 카드가 남지 않았나 본다(빌드가 이번 호 장수만큼만 남기는지 — 남았으면 이번 호에 없는 번호의 jpg 를 지운다).
   `{오늘}.html`·`index.html`·`feed.xml`·`manifest.json` 의 오늘 줄이 새 제목으로 바뀌었나 본다.
5. **푸시** — RUNBOOK 5단계의 산출물 + `automation/replaced/{오늘}/` + `automation/CHANGELOG.md` 맨 위 한 줄(늦은 발행 — 언제·왜·무엇을 옮겼나)을 **한 커밋**으로:
   `git push origin HEAD:main`(거절되면 `git pull --rebase origin main` 후 다시). 커밋 제목: `Publish EDIT H {오늘} VOL.{vol} (늦은 발행 — 예비 호를 대체)`.
   호(원고·카드)를 올리는 푸시는 저녁에도 된다 — 머지 금지 시간대(18:00~20:00)는 발송·게시 **코드**를 바꾸는 머지에만 해당한다.
   게시는 워크플로가 한 번에 하나씩 차례로 한다(저녁 사슬 19:30 실행과 겹쳐도 순서대로 돈다). 다만 22:00 이 넘으면 그날은 내지 않고 사유를 알린다.
6. **발송·게시 확인** — 발송 시각이 이미 지났으므로 푸시가 발송·캐러셀 게시를 바로 띄운다(push 실행).
   - 6분쯤 뒤 `git fetch origin main` — `automation/sent/{오늘}.json` 이 새로 생겼나(`sent` 수, `failed` 0). 12분이 지나도 없으면
     send-newsletter.yml 을 workflow_dispatch(date={오늘})로 한 번 돌린다(이미 도는 실행이 있으면 기다린다 — 두 번 보내지 않는다).
   - `automation/ig_posted/{오늘}.json` 에 carousel permalink 가 생겼나. 없으면 post-instagram.yml 을 mode=post, key={오늘}, only=carousel(도는 실행이 있으면 기다린다).
   - 평일이면 이 실행은 카드 스토리를 건너뛴다(영상 스토리 뒤에 올리려고) — 정상이다. 릴스 작업 세션이 뒤에 올린다.
7. **알림·보고** — 발송 기록을 확인하면 바로 PushNotification 한 줄: '오늘 자 VOL.{vol} 발행했어요 — 메일 N명, 캐러셀 {permalink}'.
   발송이나 게시가 끝내 안 되면 그 사실과 이유를 PushNotification 으로 알린다. 마지막 답은 RUNBOOK 6단계 형식 + '늦은 발행(예비 호 대체)' 한 줄.

## 하지 않는 것

- 아침에 올라간 예비 호 인스타 게시물은 지우지 않는다(API 로 못 지운다 — 운영자가 앱에서 정한다).
- 발송 명단·발송 시각 설정·워크플로는 건드리지 않는다. 구독자 주소를 출력하지 않는다.
- 다른 날짜의 호·기록은 건드리지 않는다.
