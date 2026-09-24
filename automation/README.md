# EDIT H 자동 발행 (클라우드)

노트북이 꺼져 있어도 매 영업일 아침 뉴스레터와 카드뉴스가 발행되도록, 로컬에서 하던 작업을 이 저장소 안으로 옮겼다.

```
08:00 KST  Claude 클라우드 루틴 시작 ─ automation/RUNBOOK.md 대로
           ├ 안장출근길 확인 → 없으면 주요 매체 검색으로 10개 선정·사실 확인
           ├ content/YYYY-MM-DD.json 작성
           ├ build_issue.py → 뉴스레터 HTML · 카드뉴스 10장 · manifest · index
           └ main 에 푸시 → GitHub Pages 에 게시
09:00 KST  GitHub Actions(send-newsletter.yml) → 구독자에게 메일 발송
           (08:40 에 예약 실행 → 09:00 까지 대기 후 발송. 루틴이 늦어 09:00 이후 푸시되면 푸시 즉시 발송)
```

- **금요일 주간 특집 'TOP5'**(2026-10-16부터): 그 주 데일리 카드 이슈 5개를 목록형 9장으로 다시 엮어 `instagram/YYYY-MM-DD-weekly/` 에 올린다(인스타 전용, 새 취재 없음). 설정은 `config.json` 의 `weekly_special`.
- 주말과 `holidays_kr.json` 의 공휴일은 건너뛴다(`config.json` 의 `publish_days` 로 요일 변경 가능).
- 카드뉴스는 `instagram/YYYY-MM-DD/` 에 PNG 10장 + 첫 댓글(`first_comment.txt`) + 캡션(`caption.txt`) + 휴대폰용 갤러리 페이지
  (`https://vetnam555-del.github.io/edit-h-archive/instagram/YYYY-MM-DD/`)로 올라간다.
  인스타그램 업로드는 이 페이지에서 저장·캡션 복사 후 직접 올리면 된다.

## 한 번만 해두면 되는 설정

### 1) 메일 발송용 GitHub Secrets

저장소 → **Settings → Secrets and variables → Actions → New repository secret**

| 이름 | 값 |
|---|---|
| `SMTP_USER` | 보내는 Gmail 주소 |
| `SMTP_PASSWORD` | Gmail **앱 비밀번호** 16자리 (Google 계정 → 보안 → 2단계 인증 → 앱 비밀번호) |
| `SUBSCRIBERS` | 구독자 이메일 목록. 쉼표나 줄바꿈으로 구분 |

선택: `MAIL_FROM`(보내는 주소가 로그인 계정과 다를 때), `SMTP_HOST`/`SMTP_PORT`(Gmail 이 아닐 때).
구독자 주소는 공개 저장소에 두면 안 되므로 **Secret 에만** 둔다. 신규 구독(Formspree 알림)·수신거부가 오면 `SUBSCRIBERS` 를 고쳐주면 된다.

설정 후 **Actions → Send EDIT H newsletter → Run workflow** 에서 `test_to` 에 내 주소를 넣어 테스트 발송해 보자
(테스트 발송은 발송 기록을 남기지 않는다).

### 2) 클라우드 환경 네트워크 (2026-09-24 설정 완료)

Claude 세션 상단 제목 옆 ⌄ → **클라우드 환경 편집** → 네트워크 액세스 **사용자 지정**, 허용된 도메인:

```
commons.wikimedia.org
upload.wikimedia.org
thumb.wikimedia.org      ← 표지 사진 썸네일(위키미디어는 봇에게 원본 대신 표준 크기 썸네일만 허용)
*.naver.com              ← 안장출근길(contents.premium.naver.com)·네이버 뉴스 기사·검색
```

'일반적인 패키지 매니저의 기본 목록도 포함'은 체크해 둔다(글꼴·도구 설치). 환경은 이 작업 세션과 08:00 발행 세션이 함께 쓴다.
Claude 의 WebFetch 는 네이버를 열지 못하므로 루틴은 `fetch_anjang.py`(안장출근길)·`read_article.py`(기사 본문·네이버 뉴스 검색)로 읽는다.
안장출근길 글은 로그인 없이 헤드라인·요약·원 기사 링크까지 보인다(2026-09-24 확인). 주제 단서로만 쓰고 출처는 원 기사로 단다.
다른 언론사 도메인은 막혀 있어도 된다 — 같은 기사를 네이버 뉴스판으로 찾아 읽는다.

### 3) 인스타그램 자동 게시 — 카드 캐러셀 + 음악 릴스 (처음 한 번 설정)

매 영업일 09:00 에 카드 10장 캐러셀(캡션·첫 댓글 포함)과, 같은 카드를 세로 영상으로 엮은 **음악 릴스**가 자동으로 올라간다.
금요일 주간 특집(TOP5)은 18:00. 공식 Instagram API 만 쓴다(비공식 자동화는 계정 정지 위험).
**인스타 음악 라이브러리 곡은 API 로 넣을 수 없어서**, 릴스에는 재배포가 허용된 CC BY 곡(`assets/music/`)을 영상에 직접 넣고
캡션에 출처를 단다. 릴스는 피드 격자에서 캐러셀과 겹치지 않게 릴스 탭에만 올린다(`config.instagram.reel_share_to_feed`).

**① 인스타 계정을 프로페셔널로** — 인스타 앱 → 설정 → 계정 유형 및 도구 → 프로페셔널 계정으로 전환(크리에이터 또는 비즈니스).

**② Meta 개발자 앱 만들기** (PC 권장)
1. https://developers.facebook.com → 로그인 → **내 앱 → 앱 만들기**
2. 사용 사례: **Instagram 관련(메시지·콘텐츠 관리)** 항목, 없으면 **기타 → 비즈니스** → 앱 이름 `EDIT H Publisher` → 만들기
3. 왼쪽 메뉴 **Instagram → Instagram 로그인을 사용한 API 설정**(Facebook 로그인 아님)
4. **액세스 토큰 생성 → 계정 추가** → @edit.h.kr 로 로그인해 권한 허용 → 표시되는 **토큰 복사**(다시 볼 수 없다)
   - 테스터 초대 수락이 필요하다고 나오면: 인스타 앱 → 설정 → 웹사이트 권한 → 앱 및 웹사이트 → 테스터 초대 → 수락
5. 같은 화면(또는 앱 설정)의 **Instagram 앱 시크릿 코드** 복사

**③ GitHub 토큰(토큰 자동 연장용)** — https://github.com/settings/personal-access-tokens/new
- Repository access: **Only select repositories → edit-h-archive**, Permissions → Repository → **Secrets: Read and write** → Generate → 복사

**④ Secrets 3개 넣기** — 저장소 Settings → Secrets and variables → Actions → New repository secret

| 이름 | 값 |
|---|---|
| `IG_ACCESS_TOKEN` | ②-4 인스타 토큰 |
| `IG_APP_SECRET` | ②-5 앱 시크릿 코드 |
| `GH_ADMIN_TOKEN` | ③ GitHub 토큰 |

인스타 토큰은 60일짜리다. 두 값(`IG_APP_SECRET`·`GH_ADMIN_TOKEN`)이 있으면 워크플로가 단기 토큰을 60일 토큰으로 바꾸고,
주 1회 연장해 `IG_ACCESS_TOKEN` 을 스스로 갱신한다. 없으면 60일마다 ②-4 를 다시 해서 넣어야 한다.

**⑤ 확인** — Actions → **Post EDIT H to Instagram → Run workflow**
1. mode `check` → 로그에 `인스타 계정 @edit.h.kr` 이 보이면 토큰 정상
2. mode `dry-run` → 게시 없이 이미지 10장·릴스 영상·컨테이너까지 확인(토큰 교환도 이때 한 번 된다)
3. 끝. 다음 영업일 09:00 부터 자동 게시. 수동으로 특정 호를 올리려면 key 에 날짜, mode `post`.

**음악** — `assets/music/tracks.json` 의 곡을 날짜마다 돌려 쓴다(출처 `assets/music/CREDITS.md`).
곡 파일은 Actions **Fetch reel music** 가 위키미디어에서 받아 75초 클립으로 넣는다(tracks.json 이 바뀌면 자동 실행).
바꾸고 싶으면 위키미디어 커먼즈의 CC0·CC BY 곡을 tracks.json 에 추가하면 된다. 유료 스톡 음원은 공개 저장소에 둘 수 없어 넣지 않는다.
곡이 하나도 없으면 릴스만 건너뛰고 캐러셀은 올라간다.

## 수동으로 할 일이 생겼을 때

| 상황 | 방법 |
|---|---|
| 특정 호 다시 빌드 | `python3 automation/build_issue.py 2026-09-24` (JSON 수정 후) |
| 오늘 발행 여부 확인 | `python3 automation/check_today.py` |
| 구독자 수·메일 계정 확인 | Actions → Send EDIT H newsletter → Run workflow 에서 `check_only` 체크. 메일은 보내지 않고 로그에 발송 대상 인원과 SMTP 로그인 결과만 나온다(공개 저장소라 주소는 출력하지 않음) |
| 메일 재발송/특정 날짜 발송 | Actions → Send EDIT H newsletter → Run workflow (`date` 입력). 이미 보낸 날은 `automation/sent/날짜.json` 을 지워야 다시 보낸다 |
| 임시공휴일 추가 | `holidays_kr.json` 에 한 줄 추가 |
| 발송 시각 변경 | `config.json` 의 `send_time_kst`(문구·대기 시각이 따라 바뀜) + 워크플로 `cron`(발송 20분 전) + 루틴 시각(발송 1시간 전)을 함께 바꾼다 |

## 파일 구조

```
automation/
  RUNBOOK.md            루틴이 따르는 절차(소스 우선순위·사실 확인 규칙 포함)
  config.json           사이트 URL·발송 시각·발행 요일·1순위 소스
  holidays_kr.json      쉬는 날
  check_today.py        오늘 발행해야 하는지 + 다음 VOL + 최근 주제
  build_issue.py        JSON → 뉴스레터·카드·manifest·index
  render_cards.cjs      카드 HTML → PNG (Playwright, 넘침 감지·자동 축소)
  preview_newsletter.cjs  검수용 뉴스레터 스크린샷
  send_newsletter.py    메일 발송(GitHub Actions 에서 실행)
  wait_until_send.py    예약 실행이 일찍 시작돼도 발송 시각까지 기다림
  sent/                 발송 기록(주소 없이 날짜·건수만)
  edith/                템플릿 모듈(newsletter·cards·site·content·fonts)
content/YYYY-MM-DD.json 호마다의 원본 콘텐츠(출처 URL 포함)
.claude/settings.json   무인 발행 세션이 확인 창 없이 실행할 수 있는 명령 목록
                        (커밋·main 푸시·빌드 스크립트만. 지켜보는 사람이 없어 이 목록이 없으면 푸시 단계에서 멈춘다)
```

## 디자인 — 최신호(VOL.092) 양식 기준

**뉴스레터** — VOL.092 양식을 그대로 따른다: 흰 바탕, 먹색(#282F38) 글자, 피치색 칩·형광펜(#FFDCCB/#FFC9AD), 회색 박스.
`@edit.h.kr` 머리 → `#VOL` `요일의` `트렌드` `브리프` 칩 → 두 줄 제목(첫 줄 굵게) → 오늘의 편지(핵심 3개·H의 한 줄 관찰)
→ 번호 배지 빅이슈(큰 숫자 박스·'그래서 뭐가 달라져?'·알아두면 좋은 것) → `#1` `#2` 섹션별 02~10 → 짧게 볼 것 → Q 오늘의 질문
→ 프로필 카드·구독 버튼. VOL.092 대비 바꾼 점은 출처를 원문 링크로 건 것과 '카드뉴스 보기' 링크를 더한 것뿐이다.

**카드뉴스(1080×1350, 10장)** — VOL.092 정식 발행에 쓴 로컬 '매거진 엔진'(`마케팅카드뉴스_260703/templates/magazine/cards.js`,
디자인엠 키트 '매거진 세트' 표지 24 → 본문 9 → 마무리 9 재현)을 옮긴 뒤, 2026-09-24 시안 비교로 개선안(B)을 채택했다.
표지(칩 + 핵심어 대형 형광 마커 + 두 줄 제목) · 오늘의 6가지 요약 · 이슈 6장(말풍선 태그 → 형광 숫자 → 보조 수치 → 번호 → 제목 →
1~2문장 본문 → 인사이트 상자, H PICK 1장은 검정 반전, 이전→이후는 BEFORE/AFTER 상자) · 마무리(프로필 카드).

| 시안 비교(같은 VOL.093 내용, 휴대폰 피드 390px·프로필 그리드 130px 크기로 측정) | A 현재 | **B 채택** | C 블랙 |
|---|---|---|---|
| 그리드 썸네일 표지 최대 글자 | 10.4px | **36px** | 12.5px |
| 카드당 글자 수(평균) | 127자 | **90자** | 90자 |
| 피드 본문 글자 | 10.5px | **11.9px** | 10.8px |
| 뉴스레터와 디자인 통일 | ○ | ○ | ✕ |
| 저장 유도 장치 | 마무리 | **요약 + 마무리** | 마무리 |

2026-09-24 뉴닉(@newneek.official) 게시물 비교 후 보강: 표지 제목을 줄마다 띠 상자로(그리드에서 읽히게), 표지에 다른 이슈
스티커 3개, 인사이트를 대화 말풍선으로('그래서 뭐가 달라져?' — 2026-09-24 독자를 마케터에서 누구나로 넓힘), 캡션을 '질문형 훅 → 오늘의 목록 → 저장·댓글 유도 → 댓글 키워드 DM 안내'로.
표지 실사 사진은 위키미디어 커먼즈의 CC0·퍼블릭 도메인·CC BY 사진만(`automation/fetch_photo.py`, 네트워크 허용 필요) 쓰고,
못 구하면 핵심어 표지로 자동 전환한다. 2026-09-24 실사 원본 크기 점검 후: 사진 위 흰 막(사진의 40%를 가림)을 없애고
뉴닉식 풀블리드(위·아래만 어둡게, 사진 표지에서는 스티커 제외)로 바꿨고, 표지를 채울 때 10% 넘게 확대되는 저해상도 사진은 빌드가 막는다. 비스킷(@biscit.co.kr) 비교 후: 표지 상단 `EDIT H.` 워드마크(모든 표지 같은 자리 — 공유·저장돼도 브랜드가 보이게), 쓸모형 목록 제목 유형, 캡션에 표지 사진 출처와 브랜드 서명 줄.
마트(@mart_eting) 비교 후: 표지 밖 모든 장에 작은 `EDIT H.` 워드마크(한 장만 캡처돼 퍼져도 브랜드가 보이게), 마무리 앞 'H의 한 줄 관찰' 장(마트 '시식후기'식 에디터 결론 — 뉴스레터 관찰 문장 재사용), 캡션 번호 목록(❶~❻)과 '/ 에디터. H' 서명, 올린 직후 달아 고정할 첫 댓글(팔로우·DM 안내, 갤러리 페이지에서 복사). 댓글 키워드는 `config.json` 의 `instagram.dm_keyword`(기본 '에디트') — DM 은 직접 보낸다.
출처 글자는 흰 배경에서 #767676(대비 4.5:1)로 올렸다(키트 실측색 #939393 은 3.1:1 이라 접근성 기준 미달).
키트 원본 파일·이미지는 쓰지 않는다. 프로필 마크는 VOL.092 발행 뒤 바뀐 최신 버전(버밀리언 원 + 안경).
