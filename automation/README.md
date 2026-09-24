# EDIT H 자동 발행 (클라우드)

노트북이 꺼져 있어도 매 영업일 아침 뉴스레터와 카드뉴스가 발행되도록, 로컬에서 하던 작업을 이 저장소 안으로 옮겼다.

```
08:00 KST  Claude 클라우드 루틴 시작 ─ automation/RUNBOOK.md 대로
           ├ 안장출근길 확인 → 없으면 주요 매체 검색으로 10개 선정·사실 확인
           ├ content/YYYY-MM-DD.json 작성
           ├ build_issue.py → 뉴스레터 HTML · 카드뉴스 9장 · manifest · index
           └ main 에 푸시 → GitHub Pages 에 게시
09:00 KST  GitHub Actions(send-newsletter.yml) → 구독자에게 메일 발송
           (08:40 에 예약 실행 → 09:00 까지 대기 후 발송. 루틴이 늦어 09:00 이후 푸시되면 푸시 즉시 발송)
```

- 주말과 `holidays_kr.json` 의 공휴일은 건너뛴다(`config.json` 의 `publish_days` 로 요일 변경 가능).
- 카드뉴스는 `instagram/YYYY-MM-DD/` 에 PNG 9장 + 캡션(`caption.txt`) + 휴대폰용 갤러리 페이지
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

### 2) 클라우드 환경 네트워크 (권장)

지금 환경은 네트워크가 제한돼 있어 `contents.premium.naver.com`(안장출근길)과 대부분의 뉴스 사이트를 직접 열 수 없고,
루틴은 **웹 검색 결과만으로** 사실을 교차 확인한다. 기사 원문까지 읽게 하려면
Claude 세션 상단의 클라우드 환경 메뉴 → **Edit → Network access** 를 넓히거나 뉴스 도메인을 허용 목록에 추가하자.
(안장출근길은 유료 채널이라 네트워크를 열어도 무료 미리보기까지만 볼 수 있다.)

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
`@edit.h.kr` 머리 → `#VOL` `요일의` `마케팅` `브리프` 칩 → 두 줄 제목(첫 줄 굵게) → 오늘의 편지(핵심 3개·H의 한 줄 관찰)
→ 번호 배지 빅이슈(큰 숫자 박스·마케터의 한 줄·오늘 점검할 것) → `#1` `#2` 섹션별 02~10 → 짧게 볼 것 → Q 오늘의 질문
→ 프로필 카드·구독 버튼. VOL.092 대비 바꾼 점은 출처를 원문 링크로 건 것과 '카드뉴스 보기' 링크를 더한 것뿐이다.

**카드뉴스(1080×1350, 9장)** — VOL.092 정식 발행에 쓴 로컬 '매거진 엔진'(`마케팅카드뉴스_260703/templates/magazine/cards.js`,
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

출처 글자는 흰 배경에서 #767676(대비 4.5:1)로 올렸다(키트 실측색 #939393 은 3.1:1 이라 접근성 기준 미달).
키트 원본 파일·이미지는 쓰지 않는다. 프로필 마크는 VOL.092 발행 뒤 바뀐 최신 버전(버밀리언 원 + 안경).
