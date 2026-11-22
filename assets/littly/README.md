# 리틀리(litt.ly) 프로필 페이지 — 그림·문구·링크

2026-11-22 운영자: "요즘 프로필은 리틀리로 한다는데 이걸로 꾸며 줘". 리틀리 편집은 운영자 로그인이 필요해 Claude 가 대신 못 한다 —
그림(`python3 automation/build_littly_assets.py`)과 아래 문구·링크를 운영자가 리틀리 앱에 그대로 넣는다.

**원칙**: 인스타 프로필 링크가 구독 페이지로 바로 가던 길에 한 번 더 누르는 칸이 생긴다 → **구독 버튼을 맨 위·가장 크게, 하나만 강조**.
구독 링크엔 `?ref=littly` — 성과표 '구독 경로'에 리틀리 경유가 따로 잡힌다(그 전엔 `?ref=ig`). 2주 뒤(12/6) `littly` 구독 수가 그 전 2주 `ig` 보다 줄면 프로필 링크를 구독 페이지 직행으로 되돌린다.

## 넣을 순서

| # | 리틀리 블록 | 내용 |
|---|---|---|
| 0 | 프로필 | 사진 `assets/mascot/profile.png`(2D 얼굴 — 작게 보여서 2D) · 이름 `EDIT H 에디트 에이치` · 소개 `바쁜 아침을 편집합니다` |
| 1 | 이미지(배너) | `banner.png` — 누르면 구독 링크 |
| 2 | 링크 버튼(강조) | 썸네일 `btn-subscribe.png` · 제목 `🎁 무료 구독하고 체크리스트 받기` · 주소 `https://vetnam555-del.github.io/edit-h-archive/subscribe.html?ref=littly` |
| 3 | 링크 버튼 | 썸네일 `btn-today.png` · 제목 `오늘 아침 소식 먼저 보기` · 주소 `https://vetnam555-del.github.io/edit-h-archive/` |
| 4 | 링크 버튼 | 썸네일 `btn-share.png` · 제목 `친구에게 추천하기` · 주소 `https://vetnam555-del.github.io/edit-h-archive/share.html` |
| 5 | 텍스트 | `매일 아침 8시 · 무료 · 광고 없음 / 숫자는 두 군데서 확인해요` |
| 6 | SNS 아이콘 | 인스타그램 `@edit.h.kr` |

- 배경색 `#F5F1E8`(크림), 버튼색 `#FF5233`(주황) 글자 흰색, 강조 버튼만 애니메이션(흔들림 등)을 켠다.
- `btn-archive.png`(생각하는 H)는 예비 — '지난 호 다시 보기' 버튼을 따로 둘 때.
- 선물(`config.gift`, 12/31 까지)이 끝나면 2번 제목을 `무료로 매일 아침 받아 보기` 로 바꾼다.
