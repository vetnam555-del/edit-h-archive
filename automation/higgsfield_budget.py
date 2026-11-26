#!/usr/bin/env python3
"""힉스필드 크레딧 — 연동된 계정 전체 기준 한 달 1,500.

2026-11-22 운영자: "힉스필드 한 달에 3000 크레딧이지만 친구랑 같이 쓰는 거라 한 달에 1500 만 써야 한다".
2026-11-27 운영자: "다른 프로젝트에서 릴스 만든 것도 포함해야 한다 — 나랑 연동된 전체 힉스필드 기준이야"
  · "지금 친구랑 쓰고 있기 때문에 연동되어 있는 힉스필드 기준이다".
→ 1,500 은 EDIT H 장부가 아니라 **연동된 계정에서 이번 달 쓴 전체**(EDIT H·다른 프로젝트 모두)로 센다.
  계정 전체 사용 = 이번 달 시작 잔액 − 지금 잔액(`balance`). 그래서 지금 잔액이 '시작 잔액 − 1,500'(바닥) 아래로 내려가지 않게
  만들기 전에 검사한다. 시작 잔액은 장부(automation/credits/higgsfield.jsonl)의 `start_balance` 줄 — 달마다 첫 검사 전에 `start` 로 적는다.
  EDIT H 가 쓴 것도 계속 `add` 로 적는다(무엇에 썼는지 기록 — 검사는 계정 잔액으로).

  python3 automation/higgsfield_budget.py status --balance 1580.03   # 이번 달 계정 전체 쓴 것·남은 것·영상 몇 편
  python3 automation/higgsfield_budget.py check 53 --balance 1580.03 # 53 을 더 써도 되나(바닥 아래면 코드 1 — 만들지 않는다)
  python3 automation/higgsfield_budget.py start 3000 "12/18 구독 크레딧 들어온 뒤 첫 잔액"   # 달마다 한 번(없으면 check 가 막는다)
  python3 automation/higgsfield_budget.py add 53 "11/30 릴스 영상 50 + 그림 3"            # 쓴 뒤 바로 적는다(기록)
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


def start_balance(rows, start, end):
    """이번 달 [start, end) 의 시작 잔액(장부의 `start_balance` 줄 중 이 달 첫 줄). 없으면 None."""
    for r in rows:
        if "start_balance" in r and start.isoformat() <= r["date"] < end.isoformat():
            return float(r["start_balance"])
    return None


def entries(path=LEDGER):
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def used(rows, start, end):
    """EDIT H 가 장부에 적은 것(기록용 — 검사는 계정 잔액으로)."""
    return round(sum(float(r.get("credits", 0)) for r in rows if start.isoformat() <= r["date"] < end.isoformat()), 2)


def state(balance=None, today=None, rows=None):
    """balance(지금 계정 잔액)가 있으면 계정 전체 기준. 이번 달 시작 잔액이 장부에 없으면 used·left 는 None."""
    cap, day = settings()
    today = today or now_kst().date()
    start, end = cycle(today, day)
    rows = entries() if rows is None else rows
    sb = start_balance(rows, start, end)
    s = {"start": start.isoformat(), "end": end.isoformat(), "cap": cap, "start_balance": sb,
         "edith": used(rows, start, end), "used": None, "left": None, "reels_left": None}
    if sb is not None and balance is not None:
        u = round(sb - float(balance), 2)
        s.update(used=u, left=round(cap - u, 2), reels_left=int(max(cap - u, 0) // REEL), floor=round(sb - cap, 2))
    return s


def can_spend(need, balance, today=None, rows=None):
    """지금 잔액에서 need 를 써도 이번 달 계정 전체 사용이 cap 이하인가. 시작 잔액이 없으면 False(먼저 start)."""
    s = state(balance, today, rows)
    return s["used"] is not None and s["used"] + float(need) <= s["cap"], s


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    st = sub.add_parser("status")
    st.add_argument("--balance", type=float, help="지금 계정 잔액(힉스필드 balance)")
    c = sub.add_parser("check")
    c.add_argument("need", type=float)
    c.add_argument("--balance", type=float, required=True, help="지금 계정 잔액(힉스필드 balance — 만들기 바로 전에 불러 온 값)")
    b = sub.add_parser("start")
    b.add_argument("balance", type=float)
    b.add_argument("what", nargs="?", default="이번 달 시작 잔액")
    a = sub.add_parser("add")
    a.add_argument("credits", type=float)
    a.add_argument("what")
    args = ap.parse_args()
    cap, _ = settings()
    if args.cmd in ("add", "start"):
        s = state()
        if args.cmd == "start":
            if s["start_balance"] is not None:
                print(f"이번 달({s['start']}~) 시작 잔액이 이미 {s['start_balance']:g} 로 적혀 있어요 — 다시 적지 않습니다.", file=sys.stderr)
                sys.exit(1)
            if args.balance < cap:
                print(f"잔액 {args.balance:g} 이 한 달 몫 {cap:g} 보다 적어요 — 구독 크레딧이 아직 안 들어왔을 수 있어 적지 않습니다"
                      "(들어온 뒤 다시).", file=sys.stderr)
                sys.exit(1)
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        now = now_kst()
        row = {"date": now.date().isoformat(), "kst": now.strftime("%H:%M")}
        row.update({"start_balance": args.balance, "credits": 0} if args.cmd == "start" else {"credits": args.credits})
        row["what"] = args.what
        with LEDGER.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        if args.cmd == "add":
            return
    if args.cmd == "check":
        ok, s = can_spend(args.need, args.balance)
        if s["used"] is None:
            print(f"✗ 힉스필드 {s['start']}~{s['end']}: 이번 달 시작 잔액이 장부에 없어요 — 먼저 "
                  "`python3 automation/higgsfield_budget.py start <잔액>`(구독 크레딧이 들어온 뒤 첫 잔액). 그 전엔 만들지 않는다.")
            sys.exit(1)
        print(f"{'✓' if ok else '✗'} 힉스필드 계정 전체 {s['start']}~{s['end']}: 쓴 {s['used']:g} + 이번 {args.need:g} "
              f"{'≤' if ok else '>'} {s['cap']:g} (잔액 {args.balance:g} · 바닥 {s['floor']:g})"
              + ("" if ok else " — 만들지 않는다(운영자 11/27 '연동된 전체 힉스필드 기준 1500')"))
        sys.exit(0 if ok else 1)
    s = state(args.balance if args.cmd == "status" else None)
    if s["used"] is None:
        why = "시작 잔액이 장부에 없음(start)" if s["start_balance"] is None else "--balance 로 지금 잔액을 주세요"
        print(f"힉스필드 {s['start']}~{s['end']}: 계정 전체 사용을 모름 — {why} · EDIT H 가 적은 것 {s['edith']:g}")
        return
    print(f"힉스필드 계정 전체 {s['start']}~{s['end']}: 쓴 {s['used']:g} / {s['cap']:g} · 남은 {s['left']:g} · 영상 날 약 {s['reels_left']}편"
          f" (그중 EDIT H 가 적은 것 {s['edith']:g})")


if __name__ == "__main__":
    main()
