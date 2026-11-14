# 5가지 웹툰 3판 — 그림 프롬프트·구도 규칙

2026-11-01 운영자 "캐러셀을 H 극장처럼 웹툰으로" → "텍스트가 기존보다 부족하다"(2판: 카드 글 그대로) → **"이게 최선이야?"**.
2판은 영상 장면을 캡처해 흐렸고, 한 장에 한 컷이라 웹툰 같지 않았다. 3판은 **한 장에 두 컷(상황 → H 의 반응)**,
그림은 **그날 새로 그린 정지 그림**이다. 글은 2판과 같다(카드 제목·본문·'그래서 나는?'·출처·숫자를 그대로 — 검수를 거친 글).

## 한 장의 구성 (comic.py `layout: "duo"`)

| 자리 | 무엇 | 덮는 곳 |
|---|---|---|
| 위 컷(A) — 상황 | 그날 소식을 비유한 장면 + H 의 첫 반응 | 왼쪽 아래 = 내레이션 상자(카드 tag + 제목), 오른쪽 위 = 숫자 스티커(카드 number) |
| 가운데 | 카드 본문 | — |
| 아래 컷(B) — H 의 반응 | '그래서 나는?'을 H 가 몸으로 하는 장면 | 맨 위 띠 = 말풍선(두 컷 사이 경계에 걸친다, 'H · 그래서 나는?' + 카드 takeaway) |

글이 길면 두 컷이 같이 줄어든다(세로로 쌓은 칸). 그래도 넘치면 렌더가 실패한다(반쯤 잘린 장을 올리지 않게 — selftest 가 카드 글자 한도를 꽉 채워 확인).
한 묶음 = 표지(그림 1장 + 오늘 5가지 목차) + 두 컷 5장 + '오늘의 5가지 한눈에' + 끝 장 = **8장**.

## 그림 만들기 (하루 11장, 드롭샷 약 185 크레딧 — 2026-11-15~)

2026-11-14 운영자 "앞으로는 힉스필드가 아니라 드롭샷을 사용해서" → 그림은 **드롭샷(Dropshot AI Studio)** 으로 그린다. 도구 찾는 법·참고 그림 주소·크레딧 규칙은
`automation/RUNBOOK_REEL.md` 의 '도구'·'크레딧 계획'·5-1 에 있다(주소는 한 곳에만 적는다 — 거기가 맞다).

- 드롭샷 `generate_image` — model `google/nano-banana-2.1`, options `prompt`(2,000자 안)·`input_image`(참고 그림 주소 목록)·`aspect_ratio` `4:3`·`resolution` `1K`
  (1200×896, 장당 16.8 크레딧). 한 번에 한 장 — 11번 부르고 `get_generation(job_id)` 로 받는다.
- `input_image`: 늘 H 시트. 놀라는 장면은 + 놀람, 표지·커피 장면은 + 커피(주소는 RUNBOOK_REEL '도구').
- 같은 장이 두 번 다 H 모양이 틀릴 때만 그 장을 `bytedance/seedream-5.5`(같은 options, 장당 18)로. 장당 125 인 `openai/gpt-image-2.5-*` 는 쓰지 않는다.
- 표지 1장 + 주제마다 A·B 2장. 받은 PNG 는 `automation/pilots/ai_reel/{날짜}/stills/` 에 둔다(저장소에 올리지 않는다 — `.gitignore`). job id 는 brief.json comic 에 적는다.
- 프롬프트 = 아래 STYLE + CHARACTER + 그날 SCENE + 구도(A·B·표지) + NEGATIVE. STYLE·CHARACTER·NEGATIVE 는 그대로 붙이고 SCENE 만 새로 쓴다.
- 2026-11-14 시험: 같은 프롬프트·참고 그림으로 nano-banana-2.1 과 seedream-5.5 모두 H 모양(동그란 주황 공·검은 안경·가는 팔다리)을 맞게 그렸고, 장면·표정 지시는 nano-banana 가 더 잘 따랐다.
- (2026-11-01~11-14 는 힉스필드 `gpt_image_2_5` 로 그렸다 — 그때 brief.json 의 job 은 힉스필드 번호다.)

### STYLE (그대로)
```
3D animated feature-film still, soft matte vinyl-toy materials, bright warm morning light, palette of cream, coral-orange and ink black, cinematic composition.
```

### CHARACTER (그대로 — 표정 한 마디만 장면에 맞게 바꾼다)
```
The only character is H from the reference images: a perfectly round coral-orange ball body (the body IS the head), two big round black-rimmed glasses with white eyes and black pupils, a small curved black smile, thin black noodle arms and legs with round black feet; no nose, ears, hair or clothes.
```

### SCENE (날마다 새로 — 기사에 있는 사실만, 비유로)
- 실존 인물·회사·제품·장소는 그리지 않는다. 사람 대신 작고 하얀 도우미 로봇, 차·폰은 '장난감 같은 둥근 덩어리'(바퀴·화면만), 도시는 장난감 미니어처.
- A = 소식이 벌어지는 순간(움직임이 큰 몸개그), B = 카드 '그래서 나는?'을 H 가 하는 모습(차분한 행동 하나).
- 같은 틀 반복 금지(qa 8번과 같은 뜻): 전날과 다른 장소·동작·카메라(넓게·가까이·위에서·아래에서).

### 구도 (그대로 붙인다)
- A: `Keep H's face and the key action inside the central band of the frame (the top and bottom will be cropped); keep the top-right corner and the bottom-left corner as plain background.`
- B: `H large with the face in the middle of the frame, not at the very top; plain wall or sky in the top quarter of the frame.`
- 표지: `H large in the center, cheerful morning mood, plain soft background around H.`

### NEGATIVE (그대로 + 그날 것)
```
No people, no human figures, no text, no letters, no numbers, no logos, no emblems, no signs, no flags.
```
그날 것 예: 차 → `no grilles, no real car designs`, 폰 → `no apple shapes, no real phone designs`, 운동화 → `no stripes`, 길 → `no route numbers`.

## 눈 검수 (11장 모아 한 장으로 보고)

1. H 모양 — 동그란 주황 공 몸, 동그란 검은 안경, 가는 검은 팔다리. 코·귀·머리카락·옷이 생기면 다시.
2. 사람·로고·글자·숫자·실제 제품 모양(상표 같은 줄무늬·로고 같은 무늬)이 없나. 있으면 그 장만 다시(한 장에 1번, 장당 16.8).
3. 렌더한 8장에서 내레이션 상자·숫자 스티커·말풍선이 H 얼굴을 덮지 않나 — 덮으면 아래 손잡이로 맞춘다.

## 손잡이 (brief.json comic.panels[i])

| 키 | 뜻 | 기본 |
|---|---|---|
| `card` | 그 주제의 카드 번호(제목·본문·'그래서 나는?'·출처·숫자·tag 를 카드에서) | — |
| `img_a`·`img_b` | 위·아래 컷 그림(brief.json 폴더 기준 경로) | — |
| `pos_a`·`pos_b` | 그림을 자르는 기준점(CSS object-position) — 세로 % 를 줄이면 그림 위쪽이 보인다 | `50% 50%`·`50% 30%` |
| `say_side` | 말풍선 쪽 `left`·`right` — H 얼굴 반대쪽 위 | `left` |
| `tail` | `out` 이면 말풍선 꼬리를 바깥 끝에(기본은 가운데 쪽 끝 — H 가 가운데일 때) | — |
| `stk_side` | 숫자 스티커 `right`·`left`·`none` — H 가 오른쪽 위에 있으면 `left` | `right` |

표지: `comic.cover = {"img", "pos"}`. 본보기: `automation/pilots/ai_reel/2026-11-01/brief.json` 의 comic(11/01 시안, job id 포함).

## 11/01 시안의 SCENE (본보기 — 그대로 쓰지 말고 틀만)

| 장 | SCENE |
|---|---|
| 표지 | at a sunny breakfast table by a window, H holds open a big plain newspaper with blank pages and a takeaway coffee cup, winking at the viewer |
| 인텔 A | on a wooden desk a tall tower of shiny green toy microchips collapses in mid-air, chips flying everywhere; H tumbles backwards with the falling chips, glasses slightly askew, mouth open in comic shock |
| 인텔 B | H sits at a tidy wooden desk, calmly sorting shiny green toy microchips into three neat small piles of different heights |
| BYD A | a tiny toy race track on a tabletop at sunrise; one glossy red bubble-shaped toy car zooms past a line of chunky white bubble toy cars; H at the track edge holding a small checkered flag, hopping back from the gust |
| BYD B | a tiny cozy toy car showroom; H between two plain bubble-shaped toy cars (red, white) with blank paper tags, chin on one hand, comparing |
| 아이폰 A | at a tiny workbench H unfolds a chunky two-screen toy foldable phone and a thin bright zig-zag crack zips along the hinge; H gasps with both hands pressed to its cheeks |
| 아이폰 B | at a tiny repair counter, a small round white helper robot hands H a freshly repaired toy foldable phone with a little sparkle |
| 마라톤 A | high-angle tiny toy city; main road closed with cones and ribbon, a parade of plain white wind-up toy sneakers hops along it; cream toy buses detour onto a side street, H riding the first bus roof |
| 마라톤 B | inside a bright plain toy subway car, H holds a hanging strap and gives a cheerful thumbs up |
| 올트먼 A | a tiny meeting room; rows of small glowing white helper robots around a long table, all turned toward H pointing with a little stick at a blank board |
| 올트먼 B | H at a tidy desk raises one finger as if choosing just one task while one small white helper robot stacks a single pile of papers |
