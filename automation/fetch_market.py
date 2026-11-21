#!/usr/bin/env python3
"""뉴스레터 맨 위 시세판(2026-11-22~) — 코스피·코스닥·S&P 500·나스닥 마지막 종가를 네이버 증권에서 받아 저장한다.

2026-11-22 운영자 '1~4번 오늘부터'(경쟁 비교: 어피티 3칸·Morning Brew 6칸·순살 10칸이 모두 첫 화면에 시세를 둔다).
환율은 넣지 않는다 — 네이버 증권 환율은 은행 고시 환율(밤사이 움직임 포함)이라 본문에 쓰는 서울 외환시장 종가와 숫자가 달라 독자가 헷갈린다.
build_issue.py 가 그날 파일이 없으면 부른다. 받지 못하면 시세판만 빠지고 빌드는 계속된다(틀린 숫자를 싣지 않는다).

  python3 automation/fetch_market.py 2026-11-22          # automation/market/2026-11-22.json
  python3 automation/fetch_market.py 2026-11-22 --print  # 저장하지 않고 보기만
"""
import argparse
import datetime as dt
import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from edith.common import AUTOMATION  # noqa: E402

MARKET_DIR = AUTOMATION / "market"
UA = "Mozilla/5.0 (EDIT H newsletter market board)"
INDEXES = [   # (이름, 주소) — 국내는 한국거래소 시세(네이버 증권), 해외는 현지 종가
    ("코스피", "https://m.stock.naver.com/api/index/KOSPI/price?pageSize=2&page=1"),
    ("코스닥", "https://m.stock.naver.com/api/index/KOSDAQ/price?pageSize=2&page=1"),
    ("S&P 500", "https://api.stock.naver.com/index/.INX/price?pageSize=2&page=1"),
    ("나스닥", "https://api.stock.naver.com/index/.IXIC/price?pageSize=2&page=1"),
]
WD = "월화수목금토일"


def _get(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception:  # noqa: BLE001 — 잠깐 끊김은 다시 해 본다
            if i == tries - 1:
                raise
            time.sleep(2 * (i + 1))


def row_of(name, rows, issue_date):
    """API 줄 → {name, value, pct, day}. 발행일 아침(08:00)엔 그날 장이 아직 없다 — 발행일 전날까지의 마지막 종가만 쓴다
    (미국 장은 현지 날짜 — 발행일 전날 현지 종가가 우리 시각 그날 새벽에 나온다)."""
    for r in rows:
        day = str(r["localTradedAt"])[:10]
        if day >= issue_date:
            continue
        pct = float(str(r["fluctuationsRatio"]).replace(",", ""))
        return {"name": name, "value": str(r["closePrice"]), "pct": round(pct, 2), "day": day}
    raise ValueError(f"{name}: {issue_date} 이전 종가가 없습니다")


def asof_label(rows):
    """'11/21(금) 마감 · 미국은 현지 11/21 종가' — 국내·미국 거래일이 같으면 짧게."""
    def md(day):
        d = dt.date.fromisoformat(day)
        return f"{d.month}/{d.day}({WD[d.weekday()]})"
    kr = rows[0]["day"]
    us = rows[2]["day"]
    return f"{md(kr)} 마감" + ("" if us == kr else f" · 미국은 현지 {md(us)} 종가") + " · 네이버 증권"


def fetch(issue_date, getter=_get):
    rows = [row_of(name, getter(url), issue_date) for name, url in INDEXES]
    return {"date": issue_date, "rows": rows, "asof": asof_label(rows)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("date")
    ap.add_argument("--print", action="store_true")
    a = ap.parse_args()
    data = fetch(a.date)
    for r in data["rows"]:
        print(f"  {r['name']:<8} {r['value']:>10}  {r['pct']:+.2f}%  ({r['day']})")
    print(f"  {data['asof']}")
    if not a.print:
        MARKET_DIR.mkdir(parents=True, exist_ok=True)
        (MARKET_DIR / f"{a.date}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"✓ automation/market/{a.date}.json")


if __name__ == "__main__":
    main()
