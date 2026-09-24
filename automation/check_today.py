#!/usr/bin/env python3
"""루틴 첫 단계: 오늘(KST) 발행해야 하는지, 이미 발행됐는지, 다음 VOL, 최근 다룬 주제를 알려준다.

사용: python3 automation/check_today.py [YYYY-MM-DD]
출력: JSON 한 덩어리. publish=false 면 루틴은 아무것도 만들지 않고 끝낸다.
"""
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

    warn = []
    if str(d.year) not in years:
        warn.append(f"holidays_kr.json 에 {d.year}년 공휴일이 없습니다 — 공휴일을 확인해 추가하세요")

    ws = cfg.get("weekly_special") or {}
    weekly_due = (reason is None and ws.get("enabled_from") is not None and date >= ws["enabled_from"]
                  and wd == ws.get("weekday", "금"))

    print(json.dumps({
        "date": date,
        "weekday": wd,
        "publish": reason is None and not exists,
        "skip_reason": reason or ("이미 발행됨" if exists else None),
        "already_published": exists,
        "next_vol": next_vol(date),
        "send_time_kst": cfg["send_time_kst"],
        "weekly_special_due": weekly_due,  # true 면 데일리 발행 뒤 RUNBOOK '금요일 주간 특집'도 만든다
        "recent_issues": recent,
        "recent_item_titles": recent_items,
        "warnings": warn,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
