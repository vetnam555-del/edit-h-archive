#!/usr/bin/env python3
"""힉스필드 크레딧 — EDIT H 몫(한 달 1,500) 장부.

2026-11-22 운영자: "힉스필드 한 달에 3000 크레딧이지만 친구랑 같이 쓰는 거라 한 달에 1500 만 써야 한다".
계정 잔액(`balance`)은 친구 몫까지 섞여 있어 우리 몫을 알려 주지 못한다 — 우리가 쓴 만큼을 여기(automation/credits/higgsfield.jsonl)에 적고
이번 달(구독 크레딧이 들어오는 날부터 한 달) 합계가 config.higgsfield.monthly_cap 을 넘지 않게 만들기 전에 검사한다.

  python3 automation/higgsfield_budget.py status                 # 이번 달 쓴 것·남은 것·영상 몇 편
  python3 automation/higgsfield_budget.py check 53               # 53 을 더 써도 되나(넘으면 코드 1 — 만들지 않는다)
  python3 automation/higgsfield_budget.py add 62.75 "11/24 릴스 영상 60 + 표지 그림 11장"   # 쓴 뒤 바로 적는다
"""
import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from edith.common import AUTOMATION, load_config, now_kst  # noqa: E402

LEDGER = AUTOMATION / "credits" / "higgsfield.jsonl"
REEL = 53   # 영상 날 한 편(영상 magi_2 1080p 20초 50 + 그림 약 3, 2026-11-27~ — 그 전 seedance 60 → 63) — RUNBOOK_REEL '크레딧 계획'


def settings():
    h = load_config().get("higgsfield") or {}
    return float(h.get("monthly_cap", 1500)), int(h.get("cycle_day", 18))


def cycle(today, day):
    """today 가 든 한 달 [시작, 끝) — 구독 크레딧이 들어오는 날(day, KST)부터 다음 달 같은 날 전까지."""
    def at(y, m):
        last = (dt.date(y + m // 12, m % 12 + 1, 1) - dt.timedelta(days=1)).day
        return dt.date(y, m, min(day, last))
    start = at(today.year, today.month)
    if today < start:
        start = at(today.year - (today.month == 1), (today.month - 2) % 12 + 1)
    end = at(start.year + (start.month == 12), start.month % 12 + 1)
    return start, end


def entries(path=LEDGER):
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def used(rows, start, end):
    return round(sum(float(r["credits"]) for r in rows if start.isoformat() <= r["date"] < end.isoformat()), 2)


def state(today=None, rows=None):
    cap, day = settings()
    today = today or now_kst().date()
    start, end = cycle(today, day)
    u = used(entries() if rows is None else rows, start, end)
    return {"start": start.isoformat(), "end": end.isoformat(), "cap": cap, "used": u, "left": round(cap - u, 2),
            "reels_left": int(max(cap - u, 0) // REEL)}


def can_spend(need, today=None, rows=None):
    s = state(today, rows)
    return s["used"] + float(need) <= s["cap"], s


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    c = sub.add_parser("check")
    c.add_argument("need", type=float)
    a = sub.add_parser("add")
    a.add_argument("credits", type=float)
    a.add_argument("what")
    args = ap.parse_args()
    if args.cmd == "add":
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        now = now_kst()
        with LEDGER.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"date": now.date().isoformat(), "kst": now.strftime("%H:%M"), "credits": args.credits, "what": args.what},
                               ensure_ascii=False) + "\n")
    if args.cmd == "check":
        ok, s = can_spend(args.need)
        print(f"{'✓' if ok else '✗'} 힉스필드 EDIT H 몫 {s['start']}~{s['end']}: 쓴 {s['used']:g} + 이번 {args.need:g} "
              f"{'≤' if ok else '>'} {s['cap']:g}" + ("" if ok else " — 만들지 않는다(운영자 11/22 '한 달 1500 만')"))
        sys.exit(0 if ok else 1)
    s = state()
    print(f"힉스필드 EDIT H 몫 {s['start']}~{s['end']}: 쓴 {s['used']:g} / {s['cap']:g} · 남은 {s['left']:g} · 영상 날 약 {s['reels_left']}편")


if __name__ == "__main__":
    main()
