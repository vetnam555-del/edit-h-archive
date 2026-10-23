# 큰 소식 기록

제작 루틴이 매일 `python3 automation/fetch_headlines.py --save` 로 남기는 그날 아침의 '여러 언론이 함께 다룬 소식'과
'경제·IT 매체에서 많이 읽힌 소식'(`{날짜}.json`, RUNBOOK 1-1c). 22:00 회고의 `compare_anjang.py` 와 성과표 '출처 품질' 칸이
우리 호가 큰 소식을 얼마나 다뤘는지 잰다. 제목·주소·언론사 이름만 있고 개인 정보는 없다.

이 파일은 폴더가 늘 있게 둔다 — 제작 5단계 `git add … automation/headlines/` 가 기록이 없는 날에도 실패하지 않게.
