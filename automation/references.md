# EDIT H 레퍼런스·트렌드 노트

잘 되는 계정·플랫폼 변화에서 배운 것을 모아 두고, 우리 성과표로 시험할 실험을 고른다.
**일요일 21:00 개선 루틴**이 매주 새로 조사해 고치고(출처 링크 필수), 07:00 제작·22:00 회고는 '지금 시험 중' 칸만 참고한다.
확인된 것은 `learnings.md` 원칙으로 올리고, 여기서는 지운다. 날짜는 조사한 날.

## 지금 시험 중 (시작일 · 판정 기준) — 2026-10-02 사용자 전권 위임, 한 번에 한 변수씩 겹치지 않게 일정을 나눴다

| 실험 | 기간 | 바꾸는 것 | 판정(성과표) |
|---|---|---|---|
| 실사 표지 기본 | 10/01~ | 표지를 실사 사진으로 | 실사 5호 이상 쌓이면 '비교'의 표지 줄(24시간 뒤 캐러셀 도달·조회) |
| 예비 호 날 릴스 없음 | 10/01~ | 지난 카드를 다시 엮은 영상은 올리지 않음 | — |
| **E1 세로 자막 릴스** | **10/03~10/07** | 4:5 카드 슬라이드쇼 → 1080×1920 전용 4장 약 10초(질문 훅 → 숫자 → 결론 → 에디터 H) | 5호 뒤 '릴스 형식' 줄: **평균 시청 ÷ 길이**(카드 릴스 기준 9%)·24시간 도달 |
| **E2 편집 개편** | **10/06~10/15** | 독자 '2030 직장인의 돈·일·소비' + Smart Brevity 문장 + 두 번째 장에 H PICK | 10호 뒤 '독자 축' 줄: 캐러셀 24시간 도달·조회·참여, 뉴스레터 답장·구독 |
| **E3 릴스 저녁 게시** | **10/08~10/12** | 릴스만 19:30 에 따로(아침엔 캐러셀만) — 저녁 예약이 3~6시간 늦어 19:30 은 저녁 일정 사슬(evening.yml)이 실행 | 5호 뒤 '릴스 형식' 줄의 세로·아침 vs 세로·저녁 |
| 문장 점검(E2 에 묶음) | 10/06~ | 토스 라이팅 8원칙 — 빌드가 `↘ 문장 점검` 경고(`edith/style.py`) | E2 와 같이 본다(같은 '문장' 변수) |
| **E5 구독 선물** | **10/05~11/01** | 환영 메일로 '2026 4분기 돈·일 체크리스트'(발행본의 확인된 사실 18가지, `gift/2026-q4.html`) + 구독 페이지·인스타 캡션 안내 | 성과표 '구독 경로'(최근 14일 신청 수·ref). 10/4 기준 14일 신청 0건 → 4주 동안 신청이 생기면 유지, 0건이면 선물 내용·안내 위치를 바꾼다 |
| **E4 수요일 연재 「H의 장부」** | **10/21~11/11 (4편)** | 수요일 H PICK = 소비 하나를 그 회사 숫자로 푸는 고정 연재(머니그라피 'B주류경제학' 차용) + 표지·카드·캡션에 '#회차 · 다음 편 예고' | 4편 뒤 성과표 '연재' 줄(연재 시작일부터 모든 호를 게시 24시간 뒤 점수·도달·조회로 — 14일 창 밖의 편도 포함): 연재 편 vs 그 밖의 호. 점수(저장·공유 포함)와 도달이 둘 다 앞서면 유지, 둘 다 뒤지면 되돌림 |

- E2 는 캐러셀·뉴스레터, E1·E3 는 릴스 지표로 본다(겹치는 기간의 릴스 판정은 E2 영향을 감안).
- 판정이 나면 일요일 개선 루틴이 유지·되돌림을 정하고 `learnings.md` 원칙/가설로 옮긴다. 되돌림 스위치:
  E1 `make_reel.py --cards`(또는 `reel_frames/` 빼기) · E2 `cards.PICK_FIRST_FROM`·RUNBOOK 1-4·`style.STYLE_FROM` · E3 `config.instagram.reel_evening_from`
  · E4 `config.series.from` · E5 `config.gift.until`(지난 날짜로).
- 트라이얼 릴스: 10/02 확인 결과 **API 는 `trial_params` 를 받는다**(Codex 의 '앱 전용' 판단은 틀림). 다만 우리 계정은
  `account does not meet the trial reel follower requirement` — **팔로워 기준 미달**이라 아직 못 쓴다(`automation/ig_posted/trial_probe.json`).
  팔로워가 늘면 post-instagram `mode: probe-trial` 로 다시 확인하고, 되면 E1 변형(훅 문구 A/B)을 비팔로워에게 먼저 시험한다.

## 주간 진단·조사 (2026-10-04, 일요일 루틴)

**숫자(성과표 10/4 01:32 수집, 24시간 뒤 캐러셀 기준)**: 팔로워 47(9/29) → 48(10/1) → **97(10/2) → 107(10/3)** — 한 주에 두 배 넘게 늘었다(원인은 특정 못 함,
10/1 릴스가 하루 뒤 조회 119로 회복한 시기와 겹친다). 캐러셀 도달은 하루 10~22로 그대로, 릴스는 하루 100 안팎(9/29~9/30 두 호만 2~4).
세로 릴스 첫날(10/3) 평균 시청 2.5초/10.1초 = **25%** — 카드 릴스 평균 14%보다 높다(E1, 10/8 판정). 좋아요는 9/27 부터 1~6개 생겼지만
**댓글·저장·공유·답장은 9호 연속 0**, **최근 14일 구독 신청 0건**(발송 대상 11명 그대로). → 새 사람은 오는데(팔로워·릴스) 붙잡지 못한다:
'저장할 이유'와 '구독할 이유'가 약하다.

**조사**: 인스타는 비팔로워 노출에서 **DM 공유(sends per reach)를 좋아요의 3~5배로**, 릴스는 시청 시간, 캐러셀은 **저장**을 가장 무겁게 본다
([eclincher](https://www.eclincher.com/articles/how-the-instagram-algorithm-works-in-2026) · [dataslayer — Mosseri 확인 신호](https://www.dataslayer.ai/blog/instagram-algorithm-2025-complete-guide-for-marketers)).
구독 전환은 **체크리스트·치트시트형 선물이 랜딩 페이지 전환 24~42%로 높고**, 인스타에선 **댓글 키워드 → DM 링크(18~35%)**가 가장 높다
([postengage — 인스타 리드 12가지](https://postengage.ai/blog/instagram-lead-generation-guide-2026) · [optinmonster — 리드 마그넷 사례](https://optinmonster.com/9-lead-magnets-to-increase-subscribers/) ·
[스티비 — 인스타 매거진과 뉴스레터](https://blog.stibee.com/texthip-trend-instamagazine-newsletter/)). 개인 재테크 뉴스레터가 '예산 템플릿'을 구독 선물로 걸어
전환율 3% → 12% 로 올린 사례처럼, **독자가 이미 신경 쓰는 문제를 바로 푸는 선물**이 맞다.
→ 이번 주 변경: **E5 구독 선물**(위 표). 댓글 → DM 은 권한·앱 검수가 필요해 OWNER_TODO 에 순서를 올려 둔다(댓글을 부르는 장치이기도 하다).
※ GitHub 예약 실행은 이번 주 3~4시간씩 늦었다 — 일찍 거는 방식(10/3·10/4)이 통하는지 10/5 매일 개선 루틴이 확인한다.

## 토스·머니그라피 심층 (2026-10-03, 사용자 요청 '토스 머니그라피·토스 마케팅도 참고했나')

그전엔 한 줄('진행자·연재 고정')만 적었었다. 이번에 따로 조사했다. 원문 사이트(toss.im·toss.tech·koreatimes·brunch 등)는 이 환경에서 열리지 않아
**검색 결과에 실린 기사 요약**을 근거로 했다 — 숫자는 기사에 적힌 그대로이고, 시기마다 다르다.

| 무엇 | 확인한 사실 | 우리에게 옮길 것 |
|---|---|---|
| 머니그라피 성장 | 2021-09 시작, 50만(2026-01) → 약 73만 구독·누적 조회 1억 회 이상. 광고보다 **자연 유입**으로 컸다는 평가 | 숫자를 키우는 건 광고보다 '다시 오게 하는 형식'이다 |
| B주류경제학 | 웹툰·커피·스니커즈·**대형마트(최다 조회 편)**처럼 찐팬 많은 소비를 **그 회사 재무제표**로 푸는 토크쇼. 고정 패널(회계사) + 주제별 게스트, 시즌제(1~3) | **E4 수요일 연재 「H의 장부」** — 소비 하나 → 회사 숫자 → 내 지갑 |
| 업로드 원칙 | 보도: **매주 같은 시각에 꾸준히** 올린 것이 확산을 키웠다. 토스 파란색·금융 채널 문법을 일부러 벗어났다(PD 인터뷰 — 브랜드 노출보다 이야기) | 같은 요일·같은 이름·회차 표시, 카드에 회사 홍보색을 빼고 우리 문법 유지 |
| 진행자 | 'B주류초대석'은 출연자가 **눈치 보지 않고 솔직한 의견**을 내는 점이 인기 요인 — 2026-05 공연 1,500석 즉시 매진 | 연재 편 노트 끝에 **'H의 판정'**(확인한 숫자에서 나온 분명한 의견) |
| 숏폼 | 긴 영상을 쇼츠로 잘라 **본편으로 다시 끌어오는** 고리, 본편 링크를 댓글에 | 저녁 릴스 캡션 → '아침 카드에 나머지 4가지' → 뉴스레터 |
| 토스피드 | 2018 시작, 월 100만+ 방문. **처음엔 금융 초보만 겨냥**하고 팬이 생긴 뒤 주제를 넓힘. '돈 이야기'(사람들의 실제 돈 사연) 연재 | E2 독자 좁히기(2030 직장인)와 같은 방향 — 넓히는 건 팬이 생긴 뒤 |
| 토스 라이팅 8원칙 | 다음 화면 예고 · 군더더기 빼기 · 빈 문장 빼기 · 핵심만 · 쉬운 말 · 강요 대신 제안 · 모두에게 통하는 말 · 숨은 감정 + 해요체·능동형 | RUNBOOK '토스 라이팅 원칙' + 빌드 경고(`edith/style.py`) |
| 토스 마케팅 | 만보기·행운퀴즈 같은 **게임화**로 매일 들어오게, 마케팅팀은 **작게 많이 실험**하고 데이터로 판정 | 월요일 투표·실험 달력이 같은 방향. 퀴즈형 훅(질문 → 다음 장 정답)은 다음 후보 |

따라 하지 않는 것: 영상 진행자·스튜디오 촬영·오프라인 공연(예산·사람 필요 — 팔로워가 생긴 뒤 OWNER_TODO 결정 항목), 토스 앱 안 노출(우리에겐 없음).

출처: [머니그라피 50만 돌파(토스피드)](https://toss.im/tossfeed/article/44957) · [더밸류뉴스 — 소비와 금융 구조를 잇는 방식](https://www.thevaluenews.co.kr/news/196211) ·
[Korea Times — Moneygraphy PD 인터뷰](https://www.koreatimes.co.kr/business/banking-finance/20240527/youtube-producer-behind-toss-successful-spin-off-channel-moneygraphy) ·
[디지털투데이 — 금융사 유튜브 성과](https://www.digitaltoday.co.kr/en/view/50194/financial-groups-youtube-content-racks-up-hits-in-south-korea) ·
[B주류경제학 기획 인터뷰(토스피드)](https://toss.im/tossfeed/article/interview-moneygraphy) · [경향신문 — B주류초대석 1500석](https://www.khan.co.kr/article/202605101558001) ·
[토스의 8가지 라이팅 원칙(Toss Tech)](https://toss.tech/article/8-writing-principles-of-toss) · [토스 UX 라이팅 가이드](https://developers-apps-in-toss.toss.im/design/ux-writing.html) ·
[오픈애즈 — 토스가 콘텐츠 마케팅에 진심인 이유](https://www.openads.co.kr/content/contentDetail?contsId=14607) · [토스 마케팅팀 인터뷰(토스피드)](https://toss.im/tossfeed/article/marketingteam-interview) ·
[뉴스핌 — 머니그라피 구독자](https://www.newspim.com/news/view/20260122000186)

## 진단 — 2026-10-01 (조회수 저조)

성과표 숫자: 팔로워 47. 릴스 도달 9/26 107 · 9/27 128 · 9/28 49 → **9/29 2 · 9/30 1**. 캐러셀 도달은 줄곧 4~17.
성과표가 추적하는 최근 게시물(9/25~)의 좋아요·저장·공유가 0 이다(그 전 게시물은 측정하지 않음).

1. **반응 신호가 전혀 없다** — 인스타는 조회 수보다 시청 시간·도달당 공유(DM)·도달당 좋아요로 더 퍼뜨릴지 정한다.
   새 계정의 첫 릴스는 시험 삼아 수십~수백 명에게 보여지는데, 그때 반응이 0 이면 다음부터 거의 보여주지 않는다.
2. **릴스가 길고 정지 화면이다** — 글자 많은 카드 10장을 3.8초씩 넘기는 32초 슬라이드쇼. 첫 1.7~3초에 붙잡지 못하면 도달이 크게 준다.
3. **같은 이미지를 두 번 올린다** — 캐러셀과 거의 같은 카드 영상을 2분 뒤 올리고(9/30 은 지난 카드 재게시), 원본성 점수가 낮을 수 있다.
4. **올리는 시각** — 둘 다 08:00. 조사한 자료들은 한국 기준 피드 11~13시, 릴스 19~21시를 권한다(출근길 08시는 상대적으로 낮음).
5. (확인 필요) **추천 제외 상태** — 인스타 앱 설정 → 계정 → **계정 상태**에서 '추천 가능' 여부를 사람만 볼 수 있다.
   음원 저작권 신고나 가이드라인 문제가 있으면 여기 뜬다.

## 조사 요약 (2026-10-01)

- 2026 인스타 순위 신호(Mosseri 확인): 총 시청 시간·다시 보기, 도달당 공유(DM), 도달당 좋아요, 대화, 원본성.
  DM 공유가 비팔로워 확산에 가장 큰 신호. 재게시·거의 같은 영상은 원본에 밀리고, 30일에 10건 넘게 재게시하면 추천에서 빠진다.
  — [Dataslayer](https://www.dataslayer.ai/blog/instagram-algorithm-2025-complete-guide-for-marketers), [SocialPilot](https://www.socialpilot.co/blog/instagram-reels-algorithm)
- 릴스 길이: 15~30초가 완주·공유가 좋다는 자료와, 30~60초의 도달률이 가장 높다는 자료(Socialinsider 14만 건)가 갈린다 —
  우리처럼 글자 카드면 짧게. 첫 3초 이탈이 적은(60%↑) 영상은 도달이 5~10배. — [Upgrow](https://www.upgrow.com/blog/instagram-reels-statistics-2026-views-watch-time-reach-engagement), [원포인트](https://1point.kr/blog/insights/2026-reels-algorithm-guide/)
- 새 계정의 릴스는 50~500 조회가 보통이고, 조회가 0 근처로 떨어지면 먼저 계정 상태(추천 가능 여부)를 본다. 신고된 음원은 추천 제외 사유. — [Creatorflow](https://creatorflow.so/blog/why-instagram-reels-not-getting-views/), [Captain Hook](https://captain-hook.ai/article/instagram-reels-zero-views)
- 캐러셀: 7~10장, 2번째 장에 두 번째로 강한 내용(2장까지 넘긴 사람은 대개 끝까지 본다), 음악을 붙이면 릴스 탭에도 노출. — [Socime](https://socime.io/en/blog/instagram-carousel-best-practices), [TryMyPost](https://www.trymypost.com/blog/instagram-carousel-algorithm-2026-guide)
- 게시 시각(한국): 피드 평일 11~13시, 릴스 저녁 19~21시(수·목 강세). — [LinkFarm](https://linkfarm.ai/blog/instagram-best-posting-time-data-2026), [ContentsPilot](https://www.contentspilot.com/ko/articles/instagram-choejeok-gaesi-sigan-dodalryul)
- 레퍼런스 계정: 뉴닉(150만 구독) — 캐릭터 '고슴이'와 친근한 문답체로 어려운 이슈를 쉽게. MBC 14F — MZ 전용 숏폼 뉴스,
  눈에 띄는 자막과 짧은 길이로 완주율을 높여 구독자 100만. — [flex 블로그](https://flex.team/blog/2025/04/16/newneek), [KDI](https://eiec.kdi.re.kr/publish/columnView.do?cidx=13398&sel_year=2021&sel_month=07), [미디어오늘](https://www.mediatoday.co.kr/news/articleView.html?idxno=213152), [한국기자협회](https://www.journalist.or.kr/news/article.html?no=52379)

## 경쟁·레퍼런스 계정 비교 (2026-10-02)

| 계정 | 규모 | 인스타에서 하는 것 | 우리와 다른 점 |
|---|---|---|---|
| 뉴닉 | 구독 150만 · 인스타 약 108만 | 캐릭터 '고슴이' + 대화체·문답으로 시사를 쉽게. 뉴스레터·앱·인스타를 함께 굴린다 | **얼굴(캐릭터)과 말투**가 있다 |
| 어피티 | 전체 115만 · 머니레터 45만 · 인스타 약 6만 | 2030 사회초년생(25~35세 73%, 여성 80%)의 '돈'에만 집중(머니·커리어·잘쓸레터). 영상 PD 채용 중 | **독자가 좁고 분명**하다. 인스타는 보조, 뉴스레터가 본진 |
| 캐릿 | 구독 약 24만 | 인스타를 '가장 빠른 소식' 창구로, Z세대 찐일상 카드뉴스 주 3회. 매주 신조어 퀴즈 | 인스타 **전용** 콘텐츠·참여형(퀴즈) |
| Morning Brew | 뉴스레터 400만+ · 인스타 90일에 21.2만 증가 | 하루 3~4개 정적 게시물(헤드라인 그래픽 + 밈), 사람 얼굴이 나오는 짧은 영상 주 3~4개(질 낮으면 건너뜀). 추천 프로그램이 성장의 30%(초기 80%) | **유머·밈, 사람 목소리, 추천 보상** |
| theSkimm | 약 700만 | 인스타를 주 소셜로, '하루의 일부' 전략(06시 발송). 앰배서더 추천이 독자의 20% | **추천 프로그램** |
| Finshots | 50만+ | 3분 스토리텔링 뉴스를 캐러셀·릴스로 잘게 | 설명형 캐러셀(우리와 가장 비슷) |
| 스브스뉴스·14F | 14F 유튜브 100만 | 1분 안팎 영상 + 큰 자막, 검색될 만한 태그. 주제 선정이 반응을 가른다 | **세로 영상 문법**(큰 자막·빠른 전개) |

공통점 5가지 — 우리가 아직 안 하는 것:
1. **얼굴과 말투** — 캐릭터(고슴이)나 진행자(Morning Brew)가 있다. 우리는 카드가 '정보 판'이라 누가 말하는지 안 보인다.
2. **좁은 독자** — 어피티(2030 돈)·캐릿(Z세대 트렌드를 알고 싶은 직장인). 우리는 '트렌드 브리프'로 주제가 넓다(해킹·LNG·AI·퀵커머스가 한 호에). 2026 알고리즘도 '주제 일관성'을 본다.
3. **인스타 전용·참여형 콘텐츠** — 헤드라인 한 장, 밈, 퀴즈. 우리는 뉴스레터를 옮긴 카드 한 묶음뿐.
4. **세로 영상 문법** — 큰 자막·빠른 전개·사람 목소리. 우리 릴스는 4:5 카드를 흐린 배경에 얹은 슬라이드쇼(10/1 평균 시청 3.3초 = 첫 화면에서 대부분 넘김).
5. **추천 보상** — 뉴스레터 성장의 20~30%가 추천. 우리는 추천 버튼만 있고 보상이 없다.

출처: [flex 블로그(뉴닉)](https://flex.team/blog/2025/04/16/newneek), [어피티 광고 안내](https://adrop.io/ko/adnote/kit/01JHPQZAP5AXK742MQPF257512), [어피티 회사 소개](https://uppity.co.kr/company/), [캐릿 광고 소개서](https://s3.ap-northeast-2.amazonaws.com/package-univ/Download/CAREET_MEDIA.pdf), [미디어오늘(캐릿)](https://www.mediatoday.co.kr/news/articleView.html?idxno=212929),
[Morning Brew 인스타 전략](https://www.flipthefeed.com/p/heres-morning-brews-instagram-strategy), [Morning Brew 영상 전략](https://www.linkinbio.news/p/steal-morning-brews-social-video), [Morning Brew 추천 프로그램](https://referralrock.com/blog/morning-brew-referral-program/),
[theSkimm 성장](https://producthabits.com/the-skimm-7-million-subscribers-in-7-years/), [Finshots](https://finshots.in/archive/the-age-of-newsletters/), [스브스뉴스 분석](http://www.storyofseoul.com/news/articleView.html?idxno=3147), [14F](https://www.mediatoday.co.kr/news/articleView.html?idxno=213152)

## 추가 레퍼런스 (2026-10-02, 2차)

| 계정·방식 | 규모·숫자 | 배울 점 |
|---|---|---|
| Chartr | 인스타 약 40만, 주 12개 차트 | **차트 한 장 + 한 줄 해석**. 스톡 사진 대신 데이터 그림이 공유된다 |
| The Economist | 인스타 120만(18~34세가 2/3), 주 50개 게시물, 인스타 영상 조회 1.8억 회(2025) | 기사·차트·일러스트를 잘게 + **세로 영상이 핵심 전략**("젊은 독자에게 닿으려면 세로 영상이 필수") |
| NowThis | — | **소리 없이 보는 자막 영상**의 원조 — 릴스·쇼츠의 85%가 무음 재생 |
| Axios 'Smart Brevity' | — | 6단어 이하 제목 → 강한 첫 문장 1개 → '왜 중요해'. 40% 짧게 써도 정보는 같다 |
| 1440 | 330만, 직원 15명 | 편향 없는 5분 요약. 소셜 광고로 구독자 1명당 약 3달러에 모은다(측정 가능한 유료 성장) |
| 댓글 키워드 → DM 자동 응답 | 댓글 남긴 사람의 60~85%가 이메일을 남김 | '댓글에 ○○ 남기면 링크 DM' — 뉴스레터 구독 전환에 가장 많이 쓰는 방법(인스타 공식 API) |
| 부딩 | 주 2회 | 밀레니얼 세입자·실수요자의 **부동산만** 쉬운 말로 — 좁은 독자 |
| 디에디트·까탈로그 | 유튜브 + 뉴스레터 | 두 에디터의 **얼굴과 취향**이 브랜드 |
| 롱블랙 | 유료, 월 4,900원 | 하루 지나면 못 읽는 노트 → 매일 여는 습관. 이메일 + **카카오톡 채널**로 아침마다 알림 |
| 트렌드라이트 | 국내 최대 커머스 뉴스레터 | '사고파는 모든 것' 한 분야 + 인스타·카카오·커리어리로 채널 확장 |

정리하면, 앞의 다섯 가지(얼굴·좁은 독자·인스타 전용·세로 영상·추천)에 더해 세 가지가 새로 보인다.
- **차트·숫자 한 장** — 우리는 숫자가 많은데 그림(차트)으로 안 보여준다.
- **무음 자막 영상** — 우리 릴스는 음악만 있고 화면 글자는 카드 그대로(작다).
- **구독 전환 장치** — 댓글 키워드 DM, 카카오톡 채널. 우리는 프로필 링크뿐.

출처: [Chartr 인스타 통계](https://www.followerstat.com/report/chartrdaily), [Chartr](https://www.chartr.co/), [INMA — The Economist 세로 영상](https://www.inma.org/blogs/young-audiences-initiative/post.cfm/the-economist-s-shift-to-vertical-video-meets-younger-audience-need), [Economist 인스타](https://medium.com/economist-group-media/how-instagram-helps-the-economist-to-reach-a-new-generation-fbc0fd1bfb37),
[NowThis](https://en.wikipedia.org/wiki/NowThis), [Axios Smart Brevity](https://www.axioshq.com/research/smart-brevity-communication-checklist), [Press Gazette — 1440](https://pressgazette.co.uk/publishers/digital-journalism/1440-media-interview/), [댓글 → DM 자동화](https://www.replyrush.com/post/instagram-comment-to-dm-automation),
[인스타 → 이메일 퍼널](https://creatorflow.so/blog/instagram-to-email-funnel-build-list-automatically/), [뉴스레터 추천 모음(부딩·까탈로그)](https://brunch.co.kr/@jhw28/54), [롱블랙 뜯어보기](https://brunch.co.kr/@seastbest/1), [트렌드라이트](https://trendlite.stibee.com/)

## 다음 실험 후보 (효과 큰 순 — 한 번에 한 변수, 5~10호 묶어 판정 · 2026-10-02 Codex 검토 반영)

선행: 앱에서 **계정 상태(추천 가능 여부)** 확인(사용자) · 타깃 독자 5~10명에게 첫 화면을 보여 주는 정성 테스트(사용자) ·
`collect_metrics.py` 에 릴스 길이·'평균 시청 ÷ 길이'·도달당 공유/저장/좋아요·실험 태그 기록(코드).

1. **세로 전용 자막 릴스(14F·NowThis·Economist 문법)** — content JSON 에서 1080×1920 전용 프레임을 렌더해 **0~1초 질문 훅 → 핵심 숫자 → 한 줄 결론 → CTA,
   3~5장·약 8~12초**(Codex 지침). 소리 없이 봐도 읽히게. 근거: 추적한 릴스 6개 평균 시청 1.5~3.8초. 코드로 가능(게시 시각 그대로).
   비교는 트라이얼 릴스로(API 지원 여부를 먼저 확인 — `reviews/2026-10-02-growth-review.md`).
2. **독자·주제 좁히기** — 예: '2030 직장인의 돈·일·소비'(어피티·부딩·트렌드라이트). content 에 `audience`·주제 축, `issue_facts()` 에 기록, 10호 고정. 편집 방향이라 사용자 결정.
3. **Smart Brevity·첫 훅·두 번째 카드** — 제목 6단어 안팎·강한 첫 문장·'왜 중요해'(Axios·Finimize 틀), 2번째 장을 가장 센 숫자로. 출처·조건 문장은 지킨다.
4. **숫자 → 차트 한 장(Chartr·Visual Capitalist)** — 의미 있는 시계열·비교가 있을 때만. 주장 하나, 출처는 그림 안에.
5. **'에디터 H' 얼굴과 말투** — 안경 마크를 캐릭터처럼 일관되게, 연재 포맷 고정(뉴닉·토스 머니그라피·디에디트).
6. **댓글 키워드 → 구독 링크 DM** — 댓글·메시지 권한 2개와 앱 검수, comments 웹훅(또는 폴링), 비공개 답장은 댓글 후 7일 안 1번. 댓글이 생긴 뒤에.
7. **릴스 저녁(19~21시) 게시** — 게시 워크플로에서 아침·예비 실행 `--only carousel`, 저녁 실행 `--only reel`, push 경로 분기까지. 사용자 확인 후.
8. **점심 헤드라인 한 장** — 게시 추가라 사용자 확인 후.
9. **추천 보상 / 카카오톡 채널 / 소액 광고** — 비용·개인정보 설계가 필요해 사용자 결정.

## 레퍼런스 3차 — Codex 추천과 신뢰도 (2026-10-02)

검토 문서: `automation/reviews/2026-10-02-growth-review.md`(PR #43). 따라 할 형식만 옮긴다 — 제3자 숫자는 출처 주장(미검증)으로 본다.
- Visual Capitalist(차트 한 장 = 주장 하나, 출처를 그림 안에) · The Pudding(질문 하나에서 단계적 공개) · Semafor Signals(사실·해석·반대 관점 칸 나눔)
- Finimize('무슨 일 → 왜 중요 → 내게 영향' 고정 틀) · 순살브리핑(밈·고유 말투, 원문 링크 분리) · 토스 머니그라피(진행자·연재 고정)
- 미스터동(예상 읽기 시간·중요도 순서를 먼저) · 업계 기준선: 인스타 평균 참여율 0.45%(Socialinsider 2026 2분기) — 우리는 0%.
- 확실하게 하려면: 우리 계정 A/B(트라이얼 릴스, 지원 확인 후) + 경쟁 계정 숫자 직접 측정(Business Discovery, Facebook 로그인 토큰 필요).
