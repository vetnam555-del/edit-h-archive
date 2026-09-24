#!/usr/bin/env python3
"""루틴 첫 단계: 오늘(KST) 발행해야 하는지, 이미 발행됐는지, 다음 VOL, 최근 다룬 주제를 알려준다.

사용: python3 automation/check_today.py [YYYY-MM-DD]
출력: JSON 한 덩어리. publish=false 면 루틴은 아무것도 만들지 않고 끝낸다.
"""
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from edith.common import AUTOMATION, CONTENT_DIR, MANIFEST, ROOT, load_config, now_kst, parse_date, weekday_ko  # noqa: E402
from edith.content import next_vol  # noqa: E402


def holidays():
    data = json.loads((AUTOMATION / "holidays_kr.json").read_text(encoding="utf-8"))
    out = {}
    for k, v in data.items():
        if not k.startswith("_"):
            out.update(v)
    return out, sorted(k for k in data if not k.startswith("_"))


def poll_status(d, wd, cfg):
    """(poll_due, poll_result). 그 주 첫 발행 호면 투표를 낸다. 금요일(또는 투표 주가 지난 첫 호)이면
    아직 싣지 않은 지난 투표 결과를 알려준다 — 참여가 config.poll.min_votes 보다 적으면 싣지 않는다(note 로 사유)."""
    monday = d - dt.timedelta(days=d.weekday())
    files = {p.stem: p for p in CONTENT_DIR.glob("20*.json")}
    this_week = [k for k in files if monday.isoformat() <= k < d.isoformat()]
    poll_due = not this_week

    polls = sorted(k for k in files if k < d.isoformat() and (d - parse_date(k)).days <= 14
                   and json.loads(files[k].read_text(encoding="utf-8")).get("poll"))
    if not polls:
        return poll_due, None
    pid = polls[-1]
    shown = any(json.loads(files[k].read_text(encoding="utf-8")).get("poll_result", {}).get("id") == pid
                for k in files if k > pid)
    poll_week_over = parse_date(pid) < monday
    if shown or not (wd == "금" or poll_week_over):
        return poll_due, None
    path = AUTOMATION / "polls" / f"{pid}.json"
    if not path.exists():
        return poll_due, {"id": pid, "show": False, "note": "집계 파일이 아직 없어요(tally-poll.yml 06:20) — 오늘은 결과 없이 발행"}
    t = json.loads(path.read_text(encoding="utf-8"))
    total = sum(t["votes"].values())
    need = int((cfg.get("poll") or {}).get("min_votes", 5))
    if total < need:
        return poll_due, {"id": pid, "show": False, "total": total,
                          "note": f"참여 {total}명(기준 {need}명 미만) — 결과는 싣지 않는다"}
    return poll_due, {"id": pid, "show": True, "question": t["question"], "options": t["options"],
                      "votes": t["votes"], "total": total, "channels": t.get("channels", {})}


def main():
    cfg = load_config()
    date = sys.argv[1] if len(sys.argv) > 1 else now_kst().date().isoformat()
    d = parse_date(date)
    hol, years = holidays()
    wd = weekday_ko(d)

    reason = None
    if wd not in cfg["publish_days"]:
        reason = f"{wd}요일은 발행일이 아님"
    elif cfg.get("skip_kr_public_holidays") and date in hol:
        reason = f"공휴일({hol[date]})"

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    exists = (ROOT / f"{date}.html").exists() or any(i["date"] == date for i in manifest["issues"])
    recent = [
        {"vol": i["vol"], "date": i["date"], "title": i["title"], "keywords": i.get("key_keywords", [])}
        for i in manifest["issues"][-10:]
    ]
    # 최근 5호의 개별 아이템 제목(중복 주제 방지용). content/*.json 이 있는 호만.
    recent_items = []
    for p in sorted(CONTENT_DIR.glob("*.json"))[-5:]:
        c = json.loads(p.read_text(encoding="utf-8"))
        recent_items += [it["title"] for sec in c.get("sections", []) for it in sec.get("items", [])]
        recent_items += [it["title"] for it in c.get("items", [])]  # 형식 2

    warn = []
    if str(d.year) not in years:
        warn.append(f"holidays_kr.json 에 {d.year}년 공휴일이 없습니다 — 공휴일을 확인해 추가하세요")

    ws = cfg.get("weekly_special") or {}
    weekly_due = (reason is None and ws.get("enabled_from") is not None and date >= ws["enabled_from"]
                  and wd == ws.get("weekday", "금"))

    poll_due, poll_result = poll_status(d, wd, cfg)

    print(json.dumps({
        "date": date,
        "weekday": wd,
        "publish": reason is None and not exists,
        "skip_reason": reason or ("이미 발행됨" if exists else None),
        "already_published": exists,
        "next_vol": next_vol(date),
        "send_time_kst": cfg["send_time_kst"],
        "weekly_special_due": weekly_due,  # true 면 데일리 발행 뒤 RUNBOOK '금요일 주간 특집'도 만든다
        "poll_due": poll_due,              # true 면 오늘 호에 content.poll(A/B 투표)을 넣는다(그 주 첫 호)
        "poll_result": poll_result,        # 있으면 오늘 호에 content.poll_result 로 결과를 싣는다(RUNBOOK '독자 투표')
        "recent_issues": recent,
        "recent_item_titles": recent_items,
        "warnings": warn,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
