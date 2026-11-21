# 뉴스레터 시안(drafts)

정규 호가 아니다. 운영자 확인용 시안만 둔다 — 구독자에게는 나가지 않는다.

- 보내기: Actions → `send-newsletter.yml` → Run workflow(date=시안의 호 날짜, test_to=`owner`, page=`drafts/<파일>.html`).
  `owner` 는 운영자 메일(SMTP_USER — 알림이 가는 곳)이라 주소가 실행 기록에 남지 않는다. 발송 기록(automation/sent)도 남지 않는다.
- `send_newsletter.py --page` 는 이 폴더의 `.html` 이고 `--test-to` 가 있을 때만 받는다(selftest 가 지킨다).
- 2026-11-21: v7(에디토리얼형 + 그날 웹툰 표지 H 그림) — 운영자 '나한테만 시험발송해줘'.
