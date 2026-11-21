# 시세판 기록

뉴스레터 맨 위 시세판(2026-11-22~)에 쓴 전날 종가 — `automation/fetch_market.py` 가 빌드 때 받아 `{날짜}.json` 으로 남긴다(네이버 증권).
이 파일이 있어 폴더가 늘 있다 — 제작 커밋의 `git add ... automation/market/` 가 시세를 못 받은 날에도 멈추지 않게.
