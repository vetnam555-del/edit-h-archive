#!/usr/bin/env python3
"""오늘의 큰 소식 — 여러 언론이 함께 다룬 소식과 경제·IT 매체에서 많이 읽힌 소식(RUNBOOK 1-1c).

2026-10-23 운영자 '경쟁사와 비교해도 부족함 없이': 평일엔 안장출근길 헤드라인 10개가 주제 고르기의 중심이라
그 10개 밖의 큰 소식을 놓쳐도 알 길이 없었고, 주말엔 WebSearch 말고 '오늘 무엇이 큰가'를 볼 잣대가 없었다.
네이버 뉴스(허용 도메인)가 두 가지를 그대로 보여 준다:
  · 섹션 헤드라인 묶음 — 경제·IT·생활·세계·사회 섹션 맨 위 소식과 '관련 기사 N건'(그 소식을 다룬 기사 수 = 크기)
  · 많이 본 뉴스 — 언론사마다 독자가 가장 많이 읽은 5건. 경제·IT 매체만 모아 여러 곳에 함께 오른 소식을 위로

  python3 automation/fetch_headlines.py                  # 큰 소식 목록
  python3 automation/fetch_headlines.py --save           # + automation/headlines/{날짜}.json(회고가 '큰 소식 놓침'을 견준다)
  python3 automation/fetch_headlines.py --cluster "https://news.naver.com/cluster/c_…/section/101"
                                                         # 그 소식을 다룬 언론사별 기사 — 출처 2건을 서로 다른 매체로 고를 때

목록은 '무엇을 다룰지' 고르는 단서다. 사실은 원 기사·원문(보도자료)으로 확인한다(RUNBOOK 1-3).
"""
import argparse
import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compare_anjang import _same  # noqa: E402
from edith.common import ROOT, now_kst  # noqa: E402
from fetch_releases import get  # noqa: E402

SECTIONS = {"경제": 101, "IT": 105, "생활": 103, "세계": 104, "사회": 102}
RANKING = "https://news.naver.com/main/ranking/popularDay.naver"
# 많이 본 뉴스는 경제·IT 매체만 본다(종합지 순위는 정치·사건이 대부분) — 네이버 언론사 번호
MONEY_PRESS = {"009": "매일경제", "015": "한국경제", "018": "이데일리", "008": "머니투데이", "011": "서울경제", "014": "파이낸셜뉴스",
               "016": "헤럴드경제", "277": "아시아경제", "366": "조선비즈", "648": "비즈워치", "215": "한국경제TV", "374": "SBS Biz",
               "031": "아이뉴스24", "092": "지디넷코리아", "138": "디지털데일리", "293": "블로터", "030": "전자신문"}
WIRE = ("연합뉴스", "연합뉴스TV", "뉴시스", "뉴스1")   # 통신사 — 같은 소식의 두 번째 출처로는 다른 매체를 고른다(RUNBOOK 1-3)
OUT_DIR = ROOT / "automation" / "headlines"


def _clean(s):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", s or "")).split())


def parse_section(page, name):
    out = []
    for li in re.split(r'<li class="sa_item _SECTION_HEADLINE(?: [^"]*)?">', page)[1:]:   # 뒤 절반은 'is_blind'(펼치기)로 숨어 있다(Codex 리뷰)
        li = li.split("</li>")[0] if "</li>" in li else li
        title = re.search(r'<strong class="sa_text_strong">(.*?)</strong>', li, re.S)
        url = re.search(r'href="(https://n\.news\.naver\.com/mnews/article/\d+/\d+)"', li)
        if not (title and url):
            continue
        n = re.search(r'sa_text_cluster_num">(\d+)<', li)
        press = re.search(r'sa_text_press">(.*?)<', li)
        lede = re.search(r'<div class="sa_text_lede">(.*?)</div>', li, re.S)
        cluster = re.search(r'href="(/cluster/[^"?]+)', li)
        out.append({"section": name, "count": int(n.group(1)) if n else 1, "title": _clean(title.group(1)),
                    "press": _clean(press.group(1)) if press else "", "lede": _clean(lede.group(1))[:160] if lede else "",
                    "url": url.group(1), "cluster": "https://news.naver.com" + cluster.group(1) if cluster else ""})
    return out


def parse_ranking(page, press_ids=MONEY_PRESS):
    out = []
    for box in page.split('class="rankingnews_box"')[1:]:
        head = re.search(r'media\.naver\.com/press/(\d+)/ranking', box)
        if not head or head.group(1) not in press_ids:
            continue
        for rank, (url, title) in enumerate(re.findall(
                r'<a href="(https://n\.news\.naver\.com/article/\d+/\d+)[^"]*" class="list_title[^"]*"[^>]*>(.*?)</a>', box, re.S)[:5], 1):
            out.append({"press": press_ids[head.group(1)], "rank": rank, "title": _clean(title), "url": url})
    return out


def popular_groups(items, top=12):
    """여러 매체 '많이 본' 목록에 함께 오른 소식을 묶는다 — 매체 수가 많고 순위가 높은 순."""
    groups = []
    for it in sorted(items, key=lambda i: i["rank"]):
        g = next((g for g in groups if _same(g[0]["title"], it["title"])), None)
        if g is None:
            groups.append([it])
        elif all(x["press"] != it["press"] for x in g):
            g.append(it)
    groups.sort(key=lambda g: (-len(g), min(x["rank"] for x in g)))
    return [{"title": g[0]["title"], "url": g[0]["url"], "presses": [f"{x['press']} {x['rank']}위" for x in g]} for g in groups[:top]]


def parse_cluster(page):
    out = []
    for li in re.findall(r'<li class="sa_item[^"]*"(.*?)</li>', page, re.S):
        title = re.search(r'<strong class="sa_text_strong">(.*?)</strong>', li, re.S)
        url = re.search(r'href="(https://n\.news\.naver\.com/mnews/article/\d+/\d+)"', li)
        press = re.search(r'sa_text_press">(.*?)<', li)
        if title and url and press:
            out.append({"press": _clean(press.group(1)), "title": _clean(title.group(1)), "url": url.group(1)})
    return out


def collect():
    """(묶음 목록, 많이 본 묶음, 못 읽은 곳). 섹션 하나가 막혀도 나머지는 낸다."""
    clusters, failed = [], []
    for name, sid in SECTIONS.items():
        try:
            got = parse_section(get(f"https://news.naver.com/section/{sid}"), name)
            if not got:
                failed.append(f"{name}(목록을 못 알아봄)")
            clusters += got
        except OSError as e:
            failed.append(f"{name}({type(e).__name__})")
    seen, uniq = set(), []
    for c in sorted(clusters, key=lambda c: -c["count"]):   # 같은 소식이 두 섹션에 오르면 한 번만
        if c["url"] not in seen:
            seen.add(c["url"])
            uniq.append(c)
    popular = []
    try:
        ranked = parse_ranking(get(RANKING))
        if not ranked:
            failed.append("많이 본 뉴스(목록을 못 알아봄)")
        popular = popular_groups(ranked)
    except OSError as e:
        failed.append(f"많이 본 뉴스({type(e).__name__})")
    return uniq, popular, failed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--save", action="store_true", help="automation/headlines/{날짜}.json 에 저장(회고 비교용)")
    ap.add_argument("--cluster", metavar="URL", help="한 소식을 다룬 언론사별 기사")
    args = ap.parse_args()
    if args.cluster:
        rows = parse_cluster(get(args.cluster))
        for r in rows:
            print(f"[{r['press']}{' · 통신사' if r['press'] in WIRE else ''}] {r['title']}\n    {r['url']}")
        print(f"— {len(rows)}건 · 매체 {len({r['press'] for r in rows})}곳", file=sys.stderr)
        return 0 if rows else 2
    clusters, popular, failed = collect()
    print("■ 여러 언론이 함께 다룬 소식(섹션 헤드라인 · 관련 기사 수)")
    for c in clusters:
        print(f"[{c['section']} {c['count']}] {c['title']} — {c['press']}\n    {c['url']}"
              + (f"\n    같은 소식 다른 언론: {c['cluster']}" if c["cluster"] else ""))
    print("■ 경제·IT 매체에서 많이 읽힌 소식(여러 곳에 함께 오른 것부터)")
    for g in popular:
        print(f"[{len(g['presses'])}곳] {g['title']} — {' · '.join(g['presses'])}\n    {g['url']}")
    if args.save and (clusters or popular):
        now = now_kst()
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        path = OUT_DIR / f"{now.date().isoformat()}.json"
        path.write_text(json.dumps({"fetched_at": now.isoformat(timespec="minutes"), "failed": failed, "clusters": clusters, "popular": popular},
                                   ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"저장: {path.relative_to(ROOT)}", file=sys.stderr)
    print(f"— 묶음 {len(clusters)}개 · 많이 본 {len(popular)}개" + (f" · 못 읽음: {', '.join(failed)}" if failed else ""), file=sys.stderr)
    return 0 if clusters or popular else 2


if __name__ == "__main__":
    sys.exit(main())
