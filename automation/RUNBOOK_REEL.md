# AI 릴스 '오늘 아침 5가지' + 5가지 웹툰 — 매일 08:15 (RUNBOOK_REEL)

매일 08:15 KST 에 **그날 새로 뜬 작업 세션**이 이 문서를 처음부터 읽고 그대로 한다(2026-11-12~ — 그 전에는 예약 지시문에 있던 내용을 옮겼다).
지켜보는 사람이 없으니 질문하지 말고 끝까지 진행한다. 08:30 뉴스레터·카드는 07:40 제작이 이미 만들었고 여기서는 고치지 않는다(지난 호도 마찬가지).

- **짝수 날(11월: 4·6·8…30일)**: AI 영상 릴스 '오늘 아침 5가지' 1편(20초 + 끝 화면) + 5가지 웹툰 8장 → 아침에 바로 게시(평소 08:50~09:05).
- **홀수 날**: 영상·목소리 없이 5가지 웹툰만 → main 에 올려 두면 19:30 저녁 사슬이 웹툰을 올린다. 이날은 **릴스가 없다**
  (카드·세로 프레임을 이어 붙인 이미지 릴스는 2026-11-13~ 올리지 않는다 — 운영자 11/12).
- H PICK 릴스는 만들지 않는다(운영자 11/01 "5가지로만 올려줘, 내일부터도 정상적으로").

## 운영자가 정한 것 (바꾸지 않는다 — 운영자가 다시 말할 때만)

- "패턴이 똑같네? 헉으로 시작하고 멘트가 비슷하다" → 같은 틀 반복 금지(0-2). '헉…'으로 열지 않는다.
- "기사 및 소스에 맞춰서" → 기사·출처 맞춤(0-1). "검은색으로 끊긴다" → 검은 화면 0.
- "화면이 꽉 차지 않고 가로형 같다 — H PICK 처럼 꽉 차게" → 프롬프트의 '가운데 띠' 지시가 가로 띠 + 위아래 흐린 채움을 만들었다. 꽉 찬 화면만(qa 가 막는다).
- "캐러셀을 H 극장처럼 웹툰으로" → "웹툰은 텍스트가 기존보다 부족하다"(컷마다 카드 글 그대로) → "이게 최선이야?"(3판 — 한 장에 두 컷: 상황 → H 의 반응, 그날 그린 정지 그림).
  11/09 판정(E20): 08:30 자리는 매거진 카드 유지, 웹툰은 두 번째 캐러셀로 계속.
- 11/02 "그냥 일단 기존 버전대로" — 11/02 새벽에 시험한 후킹 3법·첫 20초 설계·글자 자리 나누기·'끝까지 보면' 예고는 운영자가 다시 켜라고 할 때까지 쓰지 않는다.
  11/03 "3초 안이 가장 중요하다"로 그중 '숫자 + 나 질문' 제목만 (B0)로 켰다.
- 머니그라피 비교(`automation/reviews/2026-11-01-moneygraphy.md`): 쇼츠는 '삶의 결정' 한 마디가 터진다.
- 11/12 "릴스에서 이미지 붙여서 만드는 영상 릴스는 앞으로 하지 마" → 이미지를 이어 붙인 릴스(카드 릴스)는 만들지도 올리지도 않는다
  (`config.instagram.image_reel_until`). 릴스는 AI 영상(짝수 날)만. AI 영상을 못 만든 날 대신 올릴 릴스는 없다.
- 11/02 "릴스 나오면 바로 알려줘" → 7번. 11/05 "매일 발전하고 있는 거 맞아?" → 보고 첫 줄은 구독자 목표 줄.

## 크레딧 계획 (11/04 운영자 '480p로 해줘')

- 11월은 **날짜가 짝수인 날만 AI 영상** — seedance 2.5 **resolution 480p · bitrate_mode high**(20초 60크레딧, 720p 는 140. 다시 만들기도 480p).
- 홀수 날은 웹툰만(그림 11장 ≈ 2.75크레딧).
- 시작할 때 잔액(balance)을 본다: 영상 한 편 값(60)보다 적으면 영상은 멈추고 운영자에게 알린다. 300 아래면 그날 보고에 '남은 크레딧·남은 날' 한 줄.
- **12월 계획이 이 문서에 적히기 전에는(12/1~) 영상은 만들지 않고 웹툰만 만든다** — 11/30 잔액을 보고 운영자와 다시 정한다(계획 없이 크레딧을 쓰지 않는다).

## 새 세션 준비 (맨 처음)

- `git fetch origin main` → `git checkout main` → `git pull --ff-only origin main`.
- `python3 -c "import faster_whisper"` 가 실패하면 `pip install -q faster-whisper`(새 세션엔 없다 — qa.py 의 받아쓰기가 쓴다. 처음 실행 때 small 모델을 내려받는다).
- 힉스필드 도구(balance·generate_video·generate_image_batch·generate_audio_batch·jobs_wait)와 GitHub 도구(PR·actions)는 ToolSearch 로 불러 쓴다.
  힉스필드 도구가 없으면 만들 수 없다 — PushNotification 으로 알리고 끝낸다.
- 받은 영상·그림·프레임 시트·시험 렌더는 저장소 밖 임시 폴더(scratchpad 나 `mktemp -d`)에 둔다. 저장소 루트에 임시 파일을 남기지 않는다.
- 그림은 ffmpeg 로 한 장에 모아(tile) Read 로 본다(PIL 이 안 되는 환경이 있다).
- 흐름 문서: `automation/reviews/2026-11-01-ai-video.md`('오늘 아침 5가지'·'같은 틀 반복 금지'·'기사·출처 맞춤'·'검은 화면'·'멈춘 듯한 구간'),
  웹툰 규칙 `automation/pilots/ai_reel/webtoon_prompt.md`.
- 본보기: 가장 최근 짝수 날 `automation/pilots/ai_reel/{날짜}/brief.json`·`brief_prompt.txt`(예: 2026-11-12 — 후킹·tts 칸·source_video_prep·comic 3판),
  홀수 날은 2026-11-09. 틀만 빌리고 장면·동작은 그날 소식으로 새로 쓴다. FULL-BLEED 문장·NEGATIVE 의 가로 띠 금지는 그대로 둔다.

## (A) 목소리 — Hana(만화 캐릭터 말투) + Knox(중계 아나운서) 한 줄

11/02 운영자 "오늘 서울 도심 버스 편에서 나왔던 여자와 남자 목소리가 딱 좋았던 것 같은데". Ian·Brooks·차분한 진행자 말투는 쓰지 않는다.
번갈아 시험·목소리 없는 판은 하지 않는다. 운영자가 다른 걸 고르면 바꾼다.

- **Hana**(주제 줄 대부분 + 끝인사): generate_audio — model `qwen_audio_tts`, prompt 대사, voice_type `preset`,
  voice_id `c25f78a0-714e-42af-8da3-a399cef94968`, language `ko`, use_unlim false, instruction 은 줄마다 그 소식에 맞게 —
  '귀여운 만화 캐릭터, 깜짝 놀라서 신나게 전하는 말투'·'귀엽고 장난스러운 만화 캐릭터, 놀라서 또박또박 전하는 말투'·'귀여운 만화 캐릭터, 다급하게 또박또박 알려 주는 말투'·
  '귀여운 만화 캐릭터, 신나서 들뜬 말투'·'귀여운 만화 캐릭터, 여유 있고 다정하게 조언하는 말투'('나'에게 닿는 줄), 끝인사 '귀엽고 밝은 만화 캐릭터, 경쾌하게 인사'(줄당 약 0.05크레딧).
- **Knox**(그날 가장 센 숫자·장면 한 줄 = 0초 여는 한 마디): model `elevenlabs_v4`, prompt '그날 짧은 이름',
  dialogue `[{text '[excited] …습니다!', voice_type preset, voice_id 195e386a-cb61-5c1b-a53b-0e2f0669c408}]`, use_unlim false.
  '[excited]'는 말투 표시라 brief 의 text 칸에는 넣지 않는다.
- 녹음은 한 번에 6줄(Hana 주제 4줄 + 끝인사, Knox 1줄) generate_audio_batch — 다른 배치 바로 뒤에 보내면 429 가 나니 실패한 줄만 1분쯤 뒤 다시.
- 말: Hana 는 존댓말 '~해요!/~래요!', Knox 는 '~습니다!'. 녹음 문구 끝 '!'는 말투용이고 자막·캡션의 느낌표는 아낀다. '~해 보자!' 반복 금지.
- 길이: 한 줄 14~18음절. 녹음 뒤 앞뒤 무음을 자르고(ffmpeg silenceremove), 장면 칸(약 3.3초)보다 길 때만 tempo 1.0~1.2(그보다 길면 대사를 줄여 다시 녹음, 짧으면 늘리지 않는다).
  episode.py 가 녹음 속 0.25초 넘는 쉼을 0.2초로 줄인다 — 줄 길이·tempo 는 `qa.py <brief.json> --stems` 의 '목소리 구간'으로 잰다.
  끝인사는 끝 화면까지 이어져도 된다(칸 3.4초). 끝인사도 그날 새로 녹음한다(문구는 `automation/pilots/ai_reel/signoffs/signoffs.json`, 그 폴더의 예전 파일은 쓰지 않는다).
- **숫자·영문이 든 줄은 text(화면·검수용, content 숫자 그대로 예 '63억 달러'·'G마켓')와 "tts"(실제 녹음 문구 — 소리 나는 대로 한글만 예 '육십삼억 달러'·'지마켓')를 따로 적고 tts 로 녹음한다**(qa 가 요구).
- 받아쓰기 95% 미만이면 같은 말투로 2번까지 다시 녹음, 그래도 같은 낱말이 틀리면 더 흔한 말로 바꾼다
  (걸렸던 말: '제2세대'·'연세'·'매일'·'띄었대요'·'폭나'·'빚투라면'·'해외서 산'·'백여 개'·'유류세 인하' → '낮춘 유류세').

## (B0) 첫 3초 (11/03 운영자 "3초 안이 가장 중요하다")

① **0초 첫 프레임에 H 가 크게(화면 1/3 이상) 이미 벌어진 사건 한가운데** — 다가오는 장면·빈 배경·설명 장면으로 시작하지 않는다
  (프롬프트 Shot 1 첫 문장에 'H is already in the middle of the action in the very first frame, large in frame').
② **0초 첫 소리는 Knox 의 가장 센 한 마디**('[excited] …!', 후킹 제목과 같은 사실·숫자) + 효과음 한 방 — Hana 는 2번 장면부터. 첫 마디는 날마다 다르게.
③ **제목은 1.5초 안에 읽히게** — main 은 두 줄까지: 가장 센 숫자 한 줄(hl, 10자 안팎) + '나'에게 닿는 짧은 질문 한 줄('내 주식 돈은?'·'여행 가는 나는?'처럼, 기사 사실 범위 안).
  비교·설명은 sub 로 내리고, 자막은 첫 장면 끝까지 하나.
④ 0.8초 썸네일 프레임에 H 얼굴 + 숫자가 다 보이는지 눈으로 본다(글자가 얼굴을 덮으면 top 이나 구도를 바꾼다).

## (B) 여는 제목 = 후킹 — 첫 장면 내내 자막 하나

0초부터 첫 장면이 끝날 때(첫 휙 넘김, 보통 3~3.5초)까지 움직이는 첫 장면 위에 그날 hook 종류에 맞는 **한 방**을 크게 — 가장 센 사실을 숫자 hl 로
(content 숫자만, '빠졌다·넘었다·처음'처럼 짧고 센 끝맺음) + kick 'M월 D일 · 오늘 아침 5가지 · 1/5 · 분야' + sub 한 줄 + 작은 출처 줄(class "sub src").
후킹이 1번 주제 자막을 겸한다(따로 '1/5' 자막을 넣지 않는다). 예:

```json
{"start": 0, "end": 3.3, "top": 300, "size": 104, "html": "<div class=\"kick\">11월 1일 · 오늘 아침 5가지 · 1/5 · 증시</div><div class=\"main\">인텔이 하루 만에<br><span class=\"hl\">28.58%</span> 빠졌다</div><div class=\"sub\">출근 전에 꼭 알아야 할 소식, 지금 시작해요</div><div class=\"sub src\" style=\"font-size:27px;margin-top:12px;opacity:.85\">출처 매체·매체</div>"}
```

hook 종류가 질문이면 '…라고?', 반전이면 '…인데 …' 꼴로 — 날마다 틀을 바꾼다. 한 줄이 860px 를 넘지 않게 size·줄바꿈을 맞춘다.
**자막 한 장은 2초 이상**(장면 하나에 자막 하나, 중간에 바꾸거나 옮기지 않는다 — 11/03 운영자 "문구가 2번 확확 바뀐다").
'N가지'는 5가지만, 기사에 없는 숫자('20초' 등)는 쓰지 않는다. 정지 표지 카드는 넣지 않는다. 게시 썸네일(0.8초)이 이 후킹 화면이 된다.

## (C) 말투 형식

웃음은 그림(H 몸개그·효과음)에, 말·자막은 사실만 — 숫자는 기사 2곳 확인값, 장면마다 출처, 과장·느낌표 남발 금지(자막·캡션의 느낌표는 끝인사에 하나까지),
반말·유행어 남발 금지. 가볍고 친근하게, 전문성은 숫자·출처로 보인다. 두 기사 중 한 곳에만 있는 사실은 자막·대사에 사실로 쓰지 않는다. 투자 조언·기사에 없는 일반화 금지.

## 순서

### 0. 준비
**두 번 만들지 않기**: `automation/pilots/ai_reel/{오늘}/brief.json` 이 이미 main 에 있거나 `git ls-remote --heads origin run-claim/{오늘}-reel` 에 표시가 있으면
다른 실행이 오늘 것을 만들었거나 만드는 중이다 — 만들지 않고 한 줄 보고하고 끝낸다(크레딧을 두 번 쓰지 않는다). 둘 다 없으면
`git push origin origin/main:refs/heads/run-claim/{오늘}-reel` 로 '시작' 표시를 남기고 시작한다(표시는 사흘 뒤 자동으로 지워진다).
운영자가 "다시 만들어"라고 한 경우에만 표시가 있어도 진행한다.
오늘 호가 main 에 있나(`content/{오늘}.json`). 없으면 send_later 로 10분 뒤 자신을 다시 깨운다(최대 3번, 그래도 없으면 한 줄 보고하고 끝).
예비 호(`"rewind": true`)면 만들지 않고 한 줄 보고. 잔액은 위 '크레딧 계획'대로. 영상 다시 만들기는 1번까지
(그래도 사람·로고·실제 제품이 보이면 그날 영상은 쉬고 웹툰만 올린 뒤 알린다 — 그날은 릴스가 없다).

### 0-1. 기사·출처 맞춤 + 오늘 호 함께 점검
- `python3 automation/check_sources.py --date {오늘}` 를 먼저 돌려 첫 줄(막음·경고·기사 읽음)을 보고에 그대로 쓴다(막음이 0 이 아니면 이유를 찾아 보고).
- card_issues 1~5(big_issue·items) 이슈마다 content sources 두 곳을 `python3 automation/read_article.py <url>` 로 읽는다(병렬로 부르면 시간 초과 — 하나씩).
  숫자·날짜·고유명사·발언은 두 곳 다 있는 것만 쓴다. 한 곳이 계속 접속되지 않으면 `--search` 로 같은 사실을 다룬 다른 매체 기사를 하나 더 읽어 확인하고 보고에 적는다.
- content 의 숫자·날짜·고유명사(big_issue 의 paragraphs·why·stat·numbers·checklist, items, cards.issues)가 그 이슈 두 기사에 다 있는지 본다.
  한 곳에만 있는 것은 릴스·웹툰에 쓰지 않고(웹툰 그 컷은 panel 의 "body"·"take"·"number" 로 두 곳에서 확인된 말로 바꾼다), 보고와 CHANGELOG 한 줄에 적는다(22:00 회고가 센다).
- **이어짐 점검**(11/05 운영자 '소식과 그 결과로 적합한지 전체적으로 검토한 거 맞아?'): 카드만 보고 제목 → '그래서 나는?'을 이어 읽어, 본문 곁가지에서 따온 할 일이거나
  오늘 소식이 없어도 맞는 생활 팁이면 웹툰 그 컷의 "take"(필요하면 "body"·B 그림도)를 두 기사에 공통으로 있는 사실에서 이어지는 할 일로 바꾸고,
  보고에 '이어짐 점검: 바꾼 컷 N(무엇 → 무엇)'(없으면 '이어짐 점검: 5장 모두 이어짐').

### 0-2. 같은 틀 반복 금지
hook 종류(숫자 먼저·질문·반전·상황·할 일 먼저·비교·대화)·첫 마디(전날 릴스 첫 마디와도 다르게)·끝 자막 머리말·끝인사(signoffs.json — 보통 bye_newsletter, 가끔 다른 것)·
첫/끝 그림을 날마다 바꾼다. 최근 3편의 brief.json 을 보고 겹치지 않게 고른다.

### 1. 장면 짜기 (짝수 날)
그날 가장 센 장면(움직임이 큰 소식)을 1번으로 — 오프닝 없이 첫 프레임부터 사건, 첫 프레임에 H 가 크게 사건 한가운데((B0) ①).
장면 5개 × 약 3.5초 + 마무리 2초(H 제스처, 날마다 다르게). 장면마다 H 가 그날 소식에 맞는 새 몸개그, 장면 사이 whip-pan(검은 화면 금지), 만화 효과음(말·노래 없음).
실존 인물·회사·제품은 비유로만 — NEGATIVE 에 사람·관중·실제 제품 모양·로고·글자·숫자·기호·국기·검은 화면 + 가로 띠·흐린 위아래
(no letterboxing, no black or blurred bars, no frame inside the frame, no picture-in-picture) + 간판·안내판·표지판의 글자(no signage text, blank signs).
**화면은 꽉 차게**: CAMERA 에 'FULL-BLEED VERTICAL FRAMING IN EVERY SHOT'(장면이 네 가장자리 밖까지, 세로로 높게·가까이). 자막 자리는 위쪽 배경을 벽·하늘처럼 단순하게만 —
'가운데 띠에 모아라·위아래를 비워라'는 쓰지 않는다. 장면 아래쪽이 밋밋한 바닥뿐이면 '위아래 띠' 검사에 걸린다(11/12) — 바닥에도 물건·무늬를 둔다.
운동화·옷·차는 줄무늬·로고 없는 민무늬. **멈추지 않게**: ACTION TIMELINE 장면마다 끝을 'keeps moving until the whip-pan'으로,
CAMERA 에 'continuous motion in every shot — no held poses, no frozen moments'.

### 2. 영상 (짝수 날만)
generate_video — model seedance_2_5, mode omni_reference, duration 20, resolution 480p, bitrate_mode high, aspect_ratio 9:16, generate_audio true, use_unlim false,
medias image_references `3d8becae-2f05-4b51-b4d2-db71e052f311`·`f485f5d5-8a54-4c78-8b04-d2efcd3bed2f`·`9dc42fcf-8cdc-4c35-ac3b-1de2c6c3c21a`(@image1 시트·@image2 놀람·@image3 커피).
프리셋 추천 notice 가 오면 declined_preset_id 를 넣어 그대로. 60크레딧, 생성 약 15분(jobs_wait 로 기다린다 — 그동안 5-1 웹툰 그림을 먼저 만든다).

### 3. 받기·눈 검수
원본을 임시 폴더에 받는다 → 0.5초 간격 프레임 시트로 사람·로고·실제 제품·글자·H 모양을 본다.
- AI 가 그린 엉터리 글자: 카메라가 멈춘 구간이면 ffmpeg delogo, 카메라가 흐르면 글자 칸 안 무채색 화소만 판 색으로 누른다(geq — 11/12 brief.json source_video_prep 본보기).
  쓴 명령은 brief.json `source_video_prep` 에 적는다. 상표처럼 보이는 작은 무늬는 H 를 피해 아래쪽만 흐리게.
- 프레임 차이로 장면 경계를 잰다. 검은 화면(blackdetect) 0.
- **가로 띠 영상인지 원본부터 본다**: `python3 -c "import sys;sys.path.insert(0,'automation/pilots/ai_reel');import qa,statistics;r=qa.band_ratios('<원본>',0.1);print(qa.letterboxed(r),statistics.median(r))"`
  — True 면 다시 만들기(꽉 찬 영상은 중앙값 0.3 안팎). 아래쪽 바닥이 밋밋해서 걸린 것이면 그 장면만 1.15~1.2배로 당겨 잘라(위쪽 기준 crop → scale) 다시 잰다(11/12).
- **멈춘 구간**: `python3 -c "import sys;sys.path.insert(0,'automation/pilots/ai_reel');import qa;print(qa.stalls(qa.motion_windows('<원본>',20)))"` — 1초 넘게 멈춘 구간이 나오면
  brief.json 에 "push": [[시작, 끝]](끝은 그 장면의 휙 넘김 시각, 선택 "push_zoom" 기본 0.06)을 적어 천천히 다가가게 한다.

### 4. 대사·자막
- 첫 장면은 Knox 여는 한 마디((B0)), 2~5번 장면은 Hana 주제마다 1줄(그 장면 안, 보통 3초, 숫자는 content 그대로 한글 읽기).
  **다섯 줄 중 1~2줄은 '나'에게 닿는 말로** — 돈·집·일·출근길·결혼처럼 2030 삶의 결정과 이어지는 소식은 그 각도로(기사에 있는 사실 범위 안).
- **싱크**: 자막 start 는 장면 경계(그 줄 목소리 0~0.6초 앞), end 는 그 줄 목소리가 끝난 뒤(다음 장면 경계) — 한 줄 말하는 동안 자막은 한 장, 자막엔 대사와 같은 낱말이 하나 이상.
  마지막 주제 자막은 끝인사 목소리가 시작하기 전에 끝낸다(11/12).
- 녹음하고 자막 시각까지 적었으면 렌더 전에 `python3 automation/pilots/ai_reel/qa.py <brief.json> --stems`(약 15초).
- 자막: 첫 장면은 후킹 하나, 그다음 장면마다 '2/5 · 분야'…, 숫자는 hl, 장면마다 작게 '출처 매체·매체'(class "sub src").
  자막이 H 를 가리면 그 자막만 size 를 줄이거나 장면 처음부터 끝까지 다른 자리(top)에 둔다(중간 옮김 금지). 마무리 장면은 자막 없이.
- 끝 화면: line = 끝인사 end_line, note '숫자는 기사 2곳 이상에서 확인했어요<br>(출처는 장면마다·캡션에)', sub = 아래 5번 명령의 둘째 줄.
- 음악: `automation/pilots/ai_reel/2026-10-31/stems`(m1_chase offset 1.7부터, 곡 이음 0.25초 넘게 겹치기, m2_morning 강박이 끝인사 숨에 오게), duck mix 0.6
  (끝인사 직후 음악이 꺼지면 release 350 — 11/12), sfx 0.4 안팎(0.3 아래로 내리지 않는다).

### 5. 설정·렌더
`automation/pilots/ai_reel/{오늘}/brief.json`("date"·"hook"·"items" 이슈 tag 5개 영상 순서·seedance job·cut·source_video_prep·필요하면 push) + `brief_prompt.txt`(그날 영어 프롬프트) +
`stems/`(그날 녹음) → `python3 automation/pilots/ai_reel/episode.py <brief.json> <손질한 영상> --out instagram/{오늘}/reel_ai.mp4`.

`instagram/{오늘}/reel_ai_caption.txt`:
1. **첫 줄 12~16자 한 마디** — 그날 가장 센 사실을 주장·반전·감정으로(숫자·사실은 content 그대로, 과장 금지).
2. **둘째 줄(빈 줄 없이) '구독하면 받는 것' 한 줄** = `python3 -c "import sys; sys.path.insert(0, 'automation'); from edith import site, gift; print(site.reel_letter('{오늘}')); print(gift.screen_line('{오늘}'))"` 의
   첫 줄 그대로(글자 하나라도 바꾸면 qa 에 걸린다). 같은 명령의 둘째 줄은 끝 화면 `end_card.sub`.
3. 빈 줄 + 주제 5줄 ①~⑤ + (DM 약속 줄 — 아래 (D)) + '이 영상과 목소리는 AI로 만들었어요. 숫자는 기사 2곳 이상에서 확인했어요.' +
   '출처: 매체·매체 / …'(영상 순서, 칸마다 그 이슈 content sources 매체 2곳 — 이름은 content 그대로, '식약처·관세청 보도자료'처럼 이름에 '·'가 든 출처는 매체 2곳을 따로 더 적는다) + 해시태그 5개 이하.
   숫자 표기는 content 그대로('12개 증권사'를 '12곳'으로 바꾸면 qa 에 걸린다).

### 5-1. 5가지 웹툰 3판 (매일)
규칙 문서 `automation/pilots/ai_reel/webtoon_prompt.md` 를 먼저 읽는다.
- (가) 그림 11장 = 표지 1 + 주제마다 A(상황 — 소식이 벌어지는 순간의 몸개그)·B(H 의 반응 — 카드 '그래서 나는?'을 H 가 하는 모습).
  프롬프트 = 문서의 STYLE + CHARACTER(그대로) + 그날 SCENE(기사에 있는 사실만, 실존 인물·회사·제품·장소는 비유로 — 사람 대신 작은 하얀 도우미 로봇, 차·폰은 장난감 덩어리) +
  구도 문장 A·B·표지(그대로) + NEGATIVE(그대로 + 그날 것). 전날과 다른 장소·동작·카메라.
  generate_image_batch — model gpt_image_2_5, resolution 1k, aspect_ratio 4:3, use_unlim false, medias(role image_references) `3d8becae-2f05-4b51-b4d2-db71e052f311`(늘) +
  `f485f5d5-8a54-4c78-8b04-d2efcd3bed2f`(놀라는 장면) 또는 `9dc42fcf-8cdc-4c35-ac3b-1de2c6c3c21a`(표지·커피). 11×0.25 ≈ 2.75크레딧.
- (나) jobs_wait → `automation/pilots/ai_reel/{오늘}/stills/` 에 받는다(.gitignore — 저장소에 안 올린다). 11장을 한 장으로 모아 눈 검수:
  H 모양(동그란 주황 공 몸·동그란 검은 안경·가는 검은 팔다리, 코·귀·머리카락·옷 없음), 사람·로고·글자·숫자·실제 제품 모양 없음. 걸리면 그 장만 다시(장당 1번).
- (다) brief.json 에 "comic": {"series": "오늘 아침 5가지", "layout": "duo", "title": 그날 가장 센 사실 + '오늘 아침 5가지'(숫자 hl, content 숫자만),
  "cover": {"img": "stills/cover.png", "pos", "job"}, "summary": true, "panels": 5개(영상 순서 — {"card": 그 주제의 카드 번호(제목·본문·'그래서 나는?'·출처·숫자를 카드 글 그대로),
  "img_a", "pos_a", "img_b", "pos_b", "say_side", 필요하면 "tail": "out"·"stk_side": "left"/"none", "jobs": [A, B]}), "sources": "장마다 표시",
  "end": {"title": "오늘 아침 5가지,<br>매일 8시 30분", "sub": "경제부터 트렌드까지, 오늘 소식 5가지를<br>웹툰으로 풀어 드려요"}}. 홀수 날 brief.json 엔 date·items·comic 만 있으면 된다.
- (라) `python3 automation/pilots/ai_reel/comic.py automation/pilots/ai_reel/{오늘}/brief.json` → `instagram/{오늘}/comic/c1~c8.jpg`·`comic_alt.json`.
  '글이 칸을 넘쳤어요'로 멈추면 카드 글 문제라 보고(카드 글은 바꾸지 않는다).
- (마) 8장을 눈으로 본다: 내레이션 상자·숫자 스티커·말풍선이 H 얼굴을 덮나 → pos_a·pos_b(세로 % 를 줄이면 그림 위쪽이 보인다)·stk_side·say_side·tail 로 맞춘다. H 가 잘렸나, 엉터리 글자.
- (바) `instagram/{오늘}/comic_caption.txt`: 첫 줄 한 마디(+ '넘겨서 5가지 보기 👉') + 둘째 줄 같은 '구독하면 받는 것' 한 줄 + 빈 줄 + 5줄 ①~⑤ + (DM 약속 줄) +
  '이 그림은 AI로 만들었어요. 숫자는 기사 2곳 이상에서 확인했어요.' + '출처: …'(컷 순서) + 해시태그 5개 이하.

### 5-2. 검수
- 짝수 날: `python3 automation/pilots/ai_reel/qa.py <brief.json>` ✓(숫자·싱크·발음(녹음 95%·완성본 85%)·음량·끊김·소리 구멍·검은 화면·번쩍임·꽉 찬 화면·멈춘 구간·반복·출처·만화) →
  완성본 프레임 눈 검수(0.8초 썸네일·장면마다·끝 화면 — 자막이 H 를 가리지 않나, 깨진 글자).
- 홀수 날: `python3 automation/pilots/ai_reel/qa.py <brief.json> --comic` ✓.
- `python3 automation/selftest.py` 가 '✓ 자동 점검 통과'인지도 본다(PR 의 점검과 같다).

### 6. 올리기
- 커밋(`automation/CHANGELOG.md` 맨 위에 한 줄 — 무엇을 만들었고 무엇을 고쳤나, 다시 녹음한 줄·바꾼 컷) → 브랜치 `routine/reel`(`git checkout -B routine/reel origin/main` 뒤 커밋 — routines/README '작업 세션이 지킬 것')로 푸시 → PR(초안 아님) →
  Actions 'EDIT H selftest' 초록 + Codex 리뷰(지적이 맞으면 처리, 10분 넘게 안 오면 selftest 초록만으로) → 머지.
  데이터·문서뿐이면 아침에도 머지해도 된다(18:00~20:00 은 피한다).
- **짝수 날**: 실행 중인 post-instagram 이 없을 때 post-instagram.yml 을 workflow_dispatch(key={오늘}, mode=post, only=reel) — 릴스·AI 스토리·카드 스토리·5가지 웹툰이 함께 올라간다.
  → `automation/ig_posted/{오늘}.json` 의 reel(style ai)·permalink·ai_label·story_ai·comic(permalink) 확인.
  머지 전에는 영상 공개 주소를 curl 로 찌르지 않는다(GitHub Pages 가 404 를 몇 분 기억해 게시가 늦어진다). 게시는 한 번에 하나만, 저녁 사슬 19:30 과 겹치지 않게.
- **홀수 날**: post-instagram 은 돌리지 않는다(19:30 저녁 사슬이 main 의 웹툰을 올린다 — 릴스는 없다).

### 7. 알리기·보고
- **릴스가 올라가면 바로**(11/02 운영자): reel permalink 를 확인한 그 즉시 PushNotification(한 줄 '오늘 릴스 올라갔어요: {permalink}') +
  SendUserFile(files [instagram/{오늘}/reel_ai.mp4], status proactive, display render).
- 못 올리게 되면(생성 실패·검수 탈락·게시 오류·그날 쉬기) 정해지는 즉시, 10:00 KST 가 넘도록 아직 진행 중이면 그때 한 번, 사실과 이유를 PushNotification 으로 알린다.
- 홀수 날은 알림 없이 마지막 답에 '오늘은 웹툰만 — 19:30 에 올라가요'.
- 마지막 답(한국어로 짧게): **첫 줄은 구독자 목표 줄**(`automation/metrics/summary.md` '한눈에'의 '목표 구독자' 줄 그대로 — 뉴스레터 N(7일 ±n)·인스타 N(7일 ±n)),
  릴스·웹툰 링크, 검수 결과(원 기사 대조 첫 줄·한 곳에만 있던 숫자 N개·이어짐 점검·검은 화면·꽉 찬 화면·멈춘 구간·글자 지움 여부·줄마다 받아쓰기 %·다시 녹음한 줄),
  쓴 크레딧(영상·웹툰 그림 따로)·남은 크레딧.

## (D) 댓글 DM 약속 줄
`python3 -c "import sys;sys.path.insert(0,'automation');from edith.site import dm_line;print(dm_line('{오늘}') or '')"` 가 글을 내면 그 한 줄을 릴스·만화 캡션에 넣고,
빈 줄이면 넣지 않는다(지키지 못할 약속 금지). 댓글 답장은 comment-dm.yml 이 알아서 한다.
