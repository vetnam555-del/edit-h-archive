#!/usr/bin/env python3
"""인스타 게시 계획 — 이번 실행이 무엇을(캐러셀·릴스·주간 특집) 몇 시에 올릴지 정한다. post-instagram.yml 'Decide what to post'.

릴스 저녁 게시(2026-10-02 성장 검토 — 릴스는 19~21시가 강하다는 자료, 캐러셀과 2분 간격으로 같은 그림을 두 번 올리지 않게):
config.instagram.reel_time_kst(예 "19:30")와 reel_evening_from(시작일)이 있고 오늘이 시작일 이후면
아침 실행(예약·push)은 캐러셀만, 저녁 예약 실행은 reel_time_kst 까지 기다렸다 릴스만 올린다. 아니면 예전처럼 아침에 둘 다.
저녁 예약은 실제로 3~6시간 늦게 돌아서(2026-10-05 실측) 19:30 게시는 저녁 일정 사슬(evening.py)이 수동 실행(workflow_dispatch)으로 하고,
저녁 예약은 예비로 남는다(이미 올렸으면 게시 스크립트가 건너뛴다).

  python3 automation/ig_plan.py <event> "<cron>"     # GITHUB_OUTPUT 에 kind·at·only·skip 을 쓴다(없으면 출력만)
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from edith.common import load_config, now_kst  # noqa: E402

WEEKLY_CRON = "40 8 * * 5"                       # 금 17:40 KST → 18:00 주간 특집
EVENING_CRONS = ("20 9 * * *", "35 11 * * *")    # 18:20 KST(19:30 까지 대기) · 20:35 KST 예비


def evening_reel(date=None):
    """이 날짜(기본 오늘 KST)의 릴스를 저녁에 올리는가 → 'HH:MM' 또는 None."""
    ig = load_config().get("instagram") or {}
    at, start = ig.get("reel_time_kst"), ig.get("reel_evening_from")
    date = date or now_kst().date().isoformat()
    return at if at and start and date >= start else None


def plan(event, cron, date=None):
    if cron == WEEKLY_CRON:
        return {"kind": "weekly", "at": "18:00", "only": "", "skip": "false"}
    reel_at = evening_reel(date)
    if cron in EVENING_CRONS:
        if not reel_at:
            return {"kind": "daily", "at": "", "only": "", "skip": "true"}   # 저녁 게시를 안 쓰는 날 — 아침에 둘 다 올렸다
        return {"kind": "daily", "at": reel_at, "only": "reel", "skip": "false"}
    only = "carousel" if reel_at and event in ("schedule", "push") else ""   # 수동 실행은 입력값(only)을 따른다
    return {"kind": "daily", "at": "", "only": only, "skip": "false"}


def main():
    event = sys.argv[1] if len(sys.argv) > 1 else "manual"
    cron = sys.argv[2] if len(sys.argv) > 2 else ""
    p = plan(event, cron)
    print(f"게시 계획: {event} {cron or '-'} → " + " ".join(f"{k}={v or '-'}" for k, v in p.items()))
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
            f.write("".join(f"{k}={v}\n" for k, v in p.items()))


if __name__ == "__main__":
    main()
