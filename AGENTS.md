# EDIT H — AI 작업자 안내 (자비스·Codex 등 GPT 에이전트용)

이 저장소는 **EDIT H** — 2030이 알아야 할 경제·트렌드·마케팅·테크 소식을 고르는 데일리 뉴스레터와 인스타그램 카드뉴스를 만드는 시스템이다
(대표 한 줄 '2030의 아침을 편집합니다', 2026-11-01~).
평소엔 Claude 가 정해진 시각에 일하고, **Claude 사용량이 바닥나 멈추면 자비스(GPT)가 이 문서대로 이어서 한다**(2026-10-25 운영자 결정).
모든 보고·문서·커밋 설명은 **한국어**로 쓴다. 운영자에게는 짧고 쉬운 말로 보고한다.

## 0. 먼저 알 것 — AI 없이도 도는 부분

아래는 GitHub Actions 가 알아서 한다. AI 가 멈춰도 독자에게 메일은 간다.

| 시각(KST) | 무엇 | 워크플로 |
|---|---|---|
| 08:30 | 그날 호 메일 발송 | `send-newsletter.yml` |
| 08:30 | 인스타 캐러셀 게시 | `post-instagram.yml` |
| 08:35 | **그날 호가 main 에 없으면 예비 호(지난 이야기 다시 보기)를 대신 발행** | `rewind.yml` |
| 08:40 등 | 빠진 일 알림 메일 | `alerts.yml` |
| 17:30~21:30 | 주간 특집(금)·저녁 게시(웹툰 — 이미지를 이어 붙인 릴스는 2026-11-13~ 올리지 않는다)·성과 수집 | `evening.yml` |
| 새 호 푸시 직후 | 네이버·빙에 새 호 페이지 알림(IndexNow, 2026-10-31~) | `indexnow.yml` |
| 07~00시 20분마다 | 댓글 '에디트'·'구독' → 구독 링크 DM(공식 API 비공개 답장, 권한 없으면 공개 답글로 안내, 2026-11-02~) | `comment-dm.yml` |
| 일요일 12:00 | 경쟁 매체 인스타 지표(공식 API, 운영자 토큰을 넣은 뒤부터, 2026-11-01~) | `competitors-ig.yml` |
| 일요일 12:10 | 경쟁 매체 웹 — 이번 주 다룬 주제 vs 우리(토큰 없이, robots 지킴, 2026-11-01~) | `competitors-web.yml` |

그래서 **가장 중요한 일은 07:40 '제작'** 이다. 이게 빠지면 예비 호가 나가 새 소식이 없는 날이 된다.

### 0-1. 자동 대체 — ChatGPT Codex 가 GitHub Actions 에서 (`.github/workflows/codex-fallback.yml`, 2026-10-25~)

`OPENAI_API_KEY` 시크릿이 있으면 사람이 부르지 않아도 Codex 가 이어받는다:
- **제작**: Claude 제작 루틴은 시작하자마자 `run-claim/{날짜}-claude` 표시를 남긴다(RUNBOOK 0단계). **07:55 까지 그 표시도 오늘 호도 없으면**
  Codex 가 `run-claim/{날짜}-codex` 를 남기고 `automation/codex_prompts/produce.md` 대로 RUNBOOK 0~4단계를 한다. 워크플로가 허용 경로 밖 변경을
  되돌리고 다시 빌드해 main 에 올린 뒤 발송·인스타·저녁 사슬을 돌리고 알림 메일을 보낸다. 예비 호는 Codex 표시가 있으면 09:15 까지 기다린다.
- **회고**: 22:00 Claude 회고 커밋이 23:30 까지 없으면 Codex 가 `automation/codex_prompts/retro.md` 대로 learnings.md 회고를 쓴다.
- 08:50 점검·14:10 개선·일요일 주간 루틴은 자동 대체하지 않는다(발송·게시는 GitHub Actions 가 하고, 개선은 하루 쉬어도 된다).
- 수동으로 시험: Actions → 'EDIT H Codex fallback' → Run workflow(task, dry_run=true 면 만들고 검사까지만).

### 0-2. Claude 루틴은 매번 새 세션에서 (2026-11-12~)

Claude 가 하는 일(07:40 제작 · 08:15 릴스/웹툰 · 08:50 점검 · 14:10 개선 · 22:00 회고 · 일요일 21:00 주간)은 그날 새로 뜬 작업 세션이 한다.
지시 파일은 `automation/routines/`(README 에 구조·공통 규칙), 릴스/웹툰은 `automation/RUNBOOK_REEL.md`. 기억이 없는 세션이 읽고 하므로 **절차는 모두 저장소 문서에 적는다**.

## 1. 이어받을 때 순서

1. `git fetch origin main && git checkout main && git pull --ff-only origin main`
2. 지금 시각(KST)과 아래 2절 표를 보고 **놓친 일 중 아직 의미 있는 것**부터 한다.
   - 08:15 전이면 오늘 제작(2-1). 08:35 가 지나 예비 호가 나갔으면 그날 제작은 하지 않는다(이미 발행됨).
   - 그다음 08:50 점검(2-2) → 14:10 개선(2-3, 선택) → 22:00 회고(2-4) → 일요일 21:00 주간(2-5).
3. 한 일은 `automation/CHANGELOG.md` 맨 위에 `(자비스)` 를 붙여 한 줄씩 남긴다 — Claude 가 돌아오면 여기서 이어받는다.

## 2. 매일 하는 일 (원래 Claude 예약 작업의 내용 그대로)

### 2-1. 07:40 제작 — 가장 중요
- `automation/RUNBOOK.md` 를 **처음부터 읽고 0~6단계를 그대로** 한다. 시작은 `python3 automation/check_today.py`. `publish: false` 면 사유만 보고하고 끝.
- 목표: **08:15 전에 main 에 직접 푸시**(`git push origin HEAD:main`, 거절되면 `git pull --rebase origin main` 후 다시). PR 은 만들지 않는다.
  푸시할 수 없는 환경(PR 만 되는 경우)이면 PR 을 만들고 운영자에게 "08:30 전에 머지해 주세요"라고 알린다.
- 빌드(`automation/build_issue.py`)에는 Node + Playwright Chromium + 글꼴(npm 에서 받음)이 필요하다. **빌드가 안 되는 환경이면 반쯤 만든 호를 올리지 말고**
  예비 호(08:35)에 맡긴 뒤 이유를 보고한다.
- 소스(RUNBOOK 1-1~1-3): 안장출근길(`fetch_anjang.py`, 평일) · 보도자료 원문(`fetch_releases.py`) · 큰 소식(`fetch_headlines.py --save`) · 원 기사(`read_article.py`).
  숫자·날짜·고유명사는 **서로 다른 출처 2건** 이상, 통신사 2건으로 채우지 않는다. 확인 못 한 사실은 쓰지 않는다.
  빌드 전에 `python3 automation/check_sources.py`(숫자 2곳 대조, 2026-11-05 호~) — 원 기사 한 곳에만 있는 숫자는 빌드(`build_issue.py`)가 막는다(RUNBOOK 3단계).
- 마지막에 RUNBOOK 6단계 형식으로 보고.

### 2-2. 08:50 점검
- 오늘 `{날짜}.html` 이 main 에 있나. 없고 08:35 가 지났으면 `rewind.yml` 이 돌았는지 보고, 안 돌았으면 workflow_dispatch(dry_run=false).
- 오늘 content 에 `"rewind": true` 면 예비 호가 나간 날 — 제작이 왜 멈췄는지 운영자에게 알린다.
- `automation/sent/{날짜}.json` 이 없으면 `send-newsletter.yml` 을 workflow_dispatch(date={날짜}).
- `automation/ig_posted/{날짜}.json` 에 carousel permalink 가 없으면 `post-instagram.yml` 을 mode=post, key={날짜}, only=carousel.
  **어제** AI 영상 릴스(`instagram/{어제}/reel_ai.mp4`)가 있는데 reel permalink 가 없거나, 웹툰(`instagram/{어제}/comic/`)이 있는데 comic permalink 가 없으면
  mode=post, key={어제}, only=reel. 주말·예비 호 날은 릴스가 없는 게 정상이다. 평일 정규 호인데 어제 `reel_ai.mp4` 가 없으면 이유를 찾아 보고에 한 줄
  (2026-11-13~ 평일은 매일 AI 영상 — 22:25 알림 메일도 온다). 이미 돌고 있는 실행이 있으면 기다린다(중복 실행 금지).
- `instagram/{날짜}/reel_frames/` 에 r1~r4 JPEG 가 있나, 어제 `evening.yml` 이 성공했나, 어제 성과 스냅숏(`automation/metrics/daily/`)이 21:00 뒤에 모였나.
- 평일이면 `python3 automation/compare_anjang.py` 의 '겹침 N/10' 과 '큰 소식 다룸 N/M' 을 붙여 **모두 정상이면 한 줄**로 보고.

### 2-3. 14:10 개선 (선택 — 사용량이 넉넉할 때만)
- `automation/RUNBOOK_IMPROVE.md` 0~5단계 그대로. **하루 PR 하나**, 고치는 건 1~2건, `python3 automation/selftest.py` 가 '✓ 자동 점검 통과' 여야 PR.
- 우선순위: 어제·오늘 발행 실패 → 구독자 길에서 가장 좁은 칸(RUNBOOK_IMPROVE '북극성') → `automation/learnings.md` '시스템 개선 요청' → 판정일이 된 실험(`automation/references.md` '지금 시험 중') → 3일 넘게 반복되는 빌드 경고 → 표지 사진 목록 채우기.

### 2-4. 22:00 편집 회고
1. main 최신으로. `python3 automation/request_metrics.py`(성과표가 오늘 21:00 이후 것이 아니면 수집을 요청하고 최대 9분 기다린다 — 코드 0 최신, 2 기존 것으로 진행).
2. 읽기: `automation/learnings.md`(맨 위 규칙 포함), `automation/metrics/summary.md`, 오늘·최근 3호 `content/*.json`, 오늘 `sent`·`ig_posted`, 있으면 `automation/alerts/{날짜}.json`.
   `python3 automation/compare_anjang.py --date {날짜}` 의 안장 비교·큰 소식 줄도 본다(fallback 호면 '안장 칸 N/5' 안내 줄대로 메인 5가지 중
   RUNBOOK 1-4 의 7 ①~③ 칸에 드는 수를 눈으로 세어 회고에 한 줄, 2026-11-08 호~).
3. **`automation/learnings.md` 만 고친다**: '회고 기록' 맨 위에 `### {날짜} — VOL.{vol} 「제목」` + 잘된 것 / 약했던 것 / 내일 시도할 것.
   '지금 원칙'은 같은 방향 근거가 3호 이상일 때만 바꾼다. 실패·반복 불편은 '시스템 개선 요청'에 한 줄(코드는 고치지 않는다).
4. `git add automation/learnings.md && git commit -m "Editor retrospective {날짜}" && git push origin HEAD:main`.

### 2-6. 08:15 AI 릴스 '오늘 아침 5가지' + 5가지 웹툰
- `automation/RUNBOOK_REEL.md` 를 처음부터 읽고 그대로. 평일(월~금)은 AI 영상 릴스 + 웹툰(아침 게시), 주말은 웹툰만(19:30 저녁 사슬이 올린다)
  — 2026-11-13 운영자 '릴스 영상은 주말만 제외'(그 전 11/05~11/12 는 짝수 날만).
- 힉스필드 도구(영상·그림·목소리 생성)가 있어야 한다 — 없는 환경이면 하지 않는다(그날은 릴스·웹툰 없이 08:30 카드·스토리만 나간다).
- **이미지를 이어 붙인 릴스(카드 릴스)는 올리지 않는다**(2026-11-12 운영자 결정, `config.instagram.image_reel_until`). 릴스는 AI 영상만.

### 2-5. 일요일 21:00 주간 루틴
이번 주 `automation/CHANGELOG.md`·`automation/learnings.md`·`automation/metrics/summary.md`(출처 품질 칸 포함)·`automation/references.md`·Actions 실행을 훑고,
숫자가 오르내린 원인 진단 → 판정일이 된 실험 판정 → 레퍼런스 조사(20분) → 효과 큰 변경 1개 PR → 운영자에게 한국어 주간 리포트.
리포트 첫 줄은 **구독자 1만 목표 줄**(성과표 '한눈에' 그대로 — 2026-11-01 운영자 결정, `automation/reviews/2026-11-01-growth-10k.md`)과 한 주 변화, 가장 좁은 칸.

## 3. 꼭 지킬 것

- **비밀값**(토큰·비밀번호)을 출력·커밋하지 않는다. 운영자에게도 채팅으로 붙여 넣지 말라고 안내한다(GitHub Secrets 에만).
- **구독자 이메일 주소**를 저장소·로그·보고에 넣지 않는다. Design M 키트 파일·프롬프트를 옮기지 않는다.
- 발송·게시 경로(send_newsletter·post_instagram·post_threads·워크플로)를 바꾸는 머지는 **06:30~09:00, 18:00~20:00 KST 에 하지 않는다**.
- **07:00~08:30 KST 에는 제작 세션만 일한다**(2026-11-13 사고 — 그 시간에 큰 세션 둘이 같이 돌아 Claude 5시간 사용량 한도가 07:55 에 바닥났고 예비 호가 나갔다).
  운영 대화(운영자와 이야기하는 긴 세션)와 다른 루틴은 그 시간에 일하지 않는다 — 운영자 요청이 와도 '08:30 뒤에 할게요' 한 줄만 답하고 08:30 뒤에 처리한다
  (꼭 필요한 문서 한 줄만 예외). 같은 일을 두 세션이 겹쳐 하지 않는다(보험은 예비 호·Codex 대체에 둔다). 자세히: `automation/routines/README.md` '사용량'.
- 테스트·점검을 끄거나 건너뛰어 초록을 만들지 않는다. 강제 푸시하지 않는다. 하루에 PR 을 여러 개 열지 않는다.
- 비용이 드는 가입·광고, 발송 시각, 공개 호스팅 방식, 구독자 명단 변경은 **하지 말고** `automation/OWNER_TODO.md` 에 제안만.
- 커밋·PR 에 AI 모델 이름을 쓰지 않는다(공동 작성 줄은 `Co-Authored-By: Claude <noreply@anthropic.com>` — 'Claude Opus 5.5'처럼 이름·버전을 붙이지 않는다). 지난 호의 html·카드·content 는 다시 만들지 않는다(기록이다).

## 4. 상태를 어디서 보나

| 파일 | 내용 |
|---|---|
| `automation/RUNBOOK.md` | 제작 절차(가장 자세한 규칙) |
| `automation/routines/` | Claude 루틴 지시 파일(제작·점검·개선·회고·주간)과 '매번 새 세션' 구조 |
| `automation/RUNBOOK_REEL.md` | 08:15 AI 릴스·5가지 웹툰 절차 |
| `automation/learnings.md` | 지금 원칙·가설·시스템 개선 요청·회고 기록 |
| `automation/references.md` | 지금 시험 중인 실험(판정일)·조사·다음 실험 후보 |
| `automation/CHANGELOG.md` | 날마다 무엇을 바꿨나(최신이 위) |
| `automation/OWNER_TODO.md` | 운영자만 할 수 있는 일 |
| `automation/metrics/summary.md` | 최근 14호 성과표·출처 품질 |
| `automation/competitors/ig/summary.md` | 경쟁 매체 인스타 지표(주 1회, 토큰을 넣은 뒤부터) |
| `automation/competitors/web/summary.md` | 경쟁 매체 웹 — 이번 주 다룬 주제·우리와 겹친 글·여러 매체가 다뤘는데 우리는 안 다룬 말(주 1회) |
| `automation/codex_fallback.py` | Codex 자동 대체의 판단(표시·기다림·회고 빠짐·허용 경로) |

## 5. 실행 환경이 갖춰야 할 것

- Python 3.11, Node 20, `npm i -g playwright` + Chromium(`npx playwright install chromium`), git, GitHub CLI(`gh`) 또는 GitHub 웹 화면(workflow_dispatch·PR 머지).
- 인터넷 허용: `*.naver.com`(기사·안장출근길·큰 소식), `www.korea.kr` `www.fsc.go.kr` `www.moel.go.kr` `www.fss.or.kr` `www.mofe.go.kr`(보도자료),
  `*.wikimedia.org`(표지 사진), `registry.npmjs.org`(글꼴), `github.com`.
- 저장소 푸시 권한(main). 없으면 PR 로 올리고 운영자에게 머지를 부탁한다.
