# 14:10 개선(진화) 루틴 (매일)

운영자 요청 "매일매일 진화·개선하는 시스템으로 발전해줘, 너의 판단을 믿을게"(2026-10-03).

1) `automation/RUNBOOK_IMPROVE.md` 를 처음부터 읽고 0~5단계를 그대로 수행한다.
2) 고칠 거리 우선순위: 어제·오늘 발행 흐름 실패(alerts·Actions 실패·sent/ig_posted 빠짐) → learnings.md '시스템 개선 요청' → 판정일이 된 실험
   (references.md '지금 시험 중') → 3일 이상 반복되는 빌드 경고 → (비었으면) 지금 실험과 겹치지 않는 다음 실험 준비.
3) 하루 PR 하나, 고치는 건 1~2건. 재현 → 수정 → `python3 automation/selftest.py` 통과 → PR(초안 아님, Codex 리뷰 지적은 확인해 처리) →
   Actions 'EDIT H selftest' 초록 → merge. 작업 브랜치는 `routine/improve`(README '작업 세션이 지킬 것').
   발송·게시 경로 머지는 06:00~08:30·18:00~20:00 KST 피하기. 오늘 이미 머지된 개선 PR 이 있으면(CHANGELOG 맨 위가 오늘 14:10 개선) 새로 만들지 않는다.
4) `automation/CHANGELOG.md` 에 한 줄(바꾼 것 — 왜 — 어떻게 확인), 처리한 개선 요청은 learnings.md 에서 지운다.
5) 비용·개인정보·발송 시각·공개 호스팅 변경은 하지 말고 OWNER_TODO.md 에 제안만. 비밀값 출력·커밋 금지.
6) 마지막 답은 한국어로 짧게(🛠 {날짜} 개선 — PR #N …). 고칠 게 없으면 한 줄. 첫 줄은 구독자 목표 줄(`automation/metrics/summary.md` '한눈에' 그대로).
