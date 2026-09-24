# EDIT H 자동 발행 (클라우드)

노트북이 꺼져 있어도 매 영업일 아침 뉴스레터와 카드뉴스가 발행되도록, 로컬에서 하던 작업을 이 저장소 안으로 옮겼다.

```
08:00 KST  Claude 클라우드 루틴 시작 ─ automation/RUNBOOK.md 대로
           ├ 안장출근길 확인 → 없으면 주요 매체 검색으로 10개 선정·사실 확인
           ├ content/YYYY-MM-DD.json 작성
           ├ build_issue.py → 뉴스레터 HTML · 카드뉴스 8장 · manifest · index
           └ main 에 푸시 → GitHub Pages 에 게시
09:00 KST  GitHub Actions(send-newsletter.yml) → 구독자에게 메일 발송
           (08:40 에 예약 실행 → 09:00 까지 대기 후 발송. 루틴이 늦어 09:00 이후 푸시되면 푸시 즉시 발송)
```

- 주말과 `holidays_kr.json` 의 공휴일은 건너뛴다(`config.json` 의 `publish_days` 로 요일 변경 가능).
- 카드뉴스는 `instagram/YYYY-MM-DD/` 에 PNG 8장 + 캡션(`caption.txt`) + 휴대폰용 갤러리 페이지
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

## 이번에 바뀐 디자인

**뉴스레터** — VOL.091 매거진 스타일(잉크 블랙·크림·레드)을 기본으로:
워드마크 머리, 'IN THIS ISSUE' 목차, 빅이슈를 목록에서 반복하지 않기(01 빅이슈 + 02~10),
출처를 원문 링크로, '오늘 점검할 것' 체크리스트, 카드뉴스 블록, 작은 글씨 대비 WCAG AA 로 조정.

**카드뉴스(1080×1350, 8장)** — 표지 · 목차 · 빅이슈 · SO WHAT · 픽 3장 · 오늘의 질문.
세리프 헤드라인(Noto Serif KR)·큰 숫자·괘선·폴리오로 잡지 위계를 만들고, 밝은/어두운/레드 페이지를 번갈아
스와이프 리듬을 줬다. 한 장에 한 메시지만 담도록 글자 수 상한과 자동 축소(최대 20%)를 두고, 모든 사실 카드에 출처를 단다.
