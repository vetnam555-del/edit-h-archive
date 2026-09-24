#!/usr/bin/env python3
"""1순위 소스 '안장출근길'(네이버 프리미엄콘텐츠) — 날짜별 글에서 헤드라인·요약·원 기사 링크를 뽑는다.

Claude Code 의 WebFetch 는 네이버 도메인을 열지 못해서(2026-09-24 확인) 이 스크립트로 직접 가져온다.
네트워크 허용 목록에 *.naver.com 이 있어야 한다. 막혀 있으면 코드 2로 끝나고, 그날은 WebSearch 로 대체한다.

  python3 automation/fetch_anjang.py                         # 오늘(KST) 글
  python3 automation/fetch_anjang.py --since 2026-09-24      # 직전 발행일 다음 날~오늘 글 전부(연휴 뒤 첫 호)
  python3 automation/fetch_anjang.py --date 2026-09-23 --json

출력은 주제를 고르는 '단서'다. 문장을 옮겨 쓰지 않고, 사실은 원 기사로 확인해 원 기사를 출처로 단다
(원 기사 읽기: automation/read_article.py).
종료 코드: 0 = 대상 날짜 글 있음, 3 = 대상 날짜 글 없음(가장 최근 글 제목만 안내), 2 = 접속 실패.
"""
import argparse
import datetime as dt
import html
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from edith.common import load_config, now_kst  # noqa: E402

BASE = "https://contents.premium.naver.com"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
_TITLE_DATE = re.compile(r"(\d{2})년\s*(\d{1,2})월\s*(\d{1,2})일")


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", errors="replace")


def _text(fragment):
    t = re.sub(r"<br\s*/?>", "\n", fragment)
    return re.sub(r"[ \t ​]+", " ", html.unescape(re.sub(r"<[^>]+>", "", t))).strip()


def list_posts(list_url):
    """목록 페이지 → [(날짜, 제목, 주소)] 최신순."""
    page = get(list_url)
    out, seen = [], set()
    for m in re.finditer(r'href="(/[^"]+/contents/[0-9a-z]+)"[^>]*>(.*?)</a>', page, re.S):
        path, inner = m.group(1), _text(m.group(2))
        dm = _TITLE_DATE.search(inner)
        if not dm or path in seen:
            continue
        seen.add(path)
        y, mo, d = (int(x) for x in dm.groups())
        out.append((dt.date(2000 + y, mo, d), inner.splitlines()[0][:80], BASE + path))
    if not out:  # 링크와 제목이 다른 태그에 있는 구조면 순서대로 짝을 맞춘다
        paths = list(dict.fromkeys(re.findall(r'href="(/[^"]+/contents/[0-9a-z]+)"', page)))
        titles = [_text(t) for t in re.findall(r'class="[^"]*content_title[^"]*"[^>]*>(.*?)<', page, re.S)]
        for path, title in zip(paths, titles):
            dm = _TITLE_DATE.search(title)
            if dm:
                y, mo, d = (int(x) for x in dm.groups())
                out.append((dt.date(2000 + y, mo, d), title[:80], BASE + path))
    return sorted(out, key=lambda x: x[0], reverse=True)


def parse_post(page):
    """스마트에디터 본문을 순서대로 읽어 헤드라인 목록과 항목별 요약·원 기사 링크로 묶는다."""
    blocks = []  # ("text", 문장) 또는 ("link", 주소, 제목, 도메인)
    for m in re.finditer(r'<p class="se-text-paragraph[^"]*"[^>]*>(.*?)</p>|'
                         r'<a href="([^"]+)" class="se-oglink-info[^"]*"[^>]*>(.*?)</a>', page, re.S):
        if m.group(1) is not None:
            t = _text(m.group(1))
            if t:
                blocks.append(("text", t))
        else:
            inner = m.group(3)
            title = re.search(r'class="se-oglink-title"[^>]*>(.*?)<', inner, re.S)
            domain = re.search(r'class="se-oglink-url"[^>]*>(.*?)<', inner, re.S)
            blocks.append(("link", html.unescape(m.group(2)), _text(title.group(1)) if title else "",
                           _text(domain.group(1)) if domain else ""))

    texts = [b[1] for b in blocks if b[0] == "text"]
    insight = next((t.split(":", 1)[1].strip() for t in texts if t.startswith("👀") and ":" in t), "")
    numbered = re.compile(r"^(\d{1,2})\.\s+(.+)")
    headlines, items, extras, cur = {}, {}, [], None
    for b in blocks:
        if b[0] == "text":
            t = b[1]
            m = numbered.match(t)
            if m:
                n, title = int(m.group(1)), m.group(2).strip()
                if n not in headlines:          # 첫 등장 = '헤드라인 요약' 목록
                    headlines[n] = title
                    continue
                cur = items.setdefault(n, {"no": n, "headline": headlines[n], "summary": [], "links": []})
                continue
            if t.startswith("📋"):
                if t.lstrip("📋 ").strip() not in extras:
                    extras.append(t.lstrip("📋 ").strip())
                cur = None
                continue
            if cur is not None and "본문 읽기" not in t and len(cur["summary"]) < 3:
                cur["summary"].append(t)
        elif cur is not None:
            cur["links"].append({"url": b[1], "title": b[2], "domain": b[3]})
    for n, title in headlines.items():
        items.setdefault(n, {"no": n, "headline": title, "summary": [], "links": []})
    return {"insight": insight, "items": [items[n] for n in sorted(items)], "extras": extras}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="YYYY-MM-DD (기본: 오늘 KST)")
    ap.add_argument("--since", help="YYYY-MM-DD — 이 날짜 다음 날부터 --date 까지 모든 글(직전 발행일을 넣는다)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    until = dt.date.fromisoformat(args.date) if args.date else now_kst().date()
    since = dt.date.fromisoformat(args.since) if args.since else until - dt.timedelta(days=1)

    try:
        posts = list_posts(load_config()["primary_source"]["url"])
    except (urllib.error.URLError, OSError) as e:
        print(f"✗ 안장출근길에 접속하지 못했습니다({e}) — 네트워크 허용 목록에 *.naver.com 이 있는지 확인하세요. "
              "오늘은 WebSearch 로 소스를 모읍니다(RUNBOOK 1-2).")
        sys.exit(2)
    if not posts:
        print("✗ 안장출근길 목록에서 글을 찾지 못했습니다(페이지 구조가 바뀌었을 수 있음) — WebSearch 로 대체하세요.")
        sys.exit(2)
    targets = [p for p in posts if since < p[0] <= until]
    if not targets:
        latest = posts[0]
        print(f"… {since + dt.timedelta(days=1)}~{until} 안장출근길 글이 아직 없습니다. 가장 최근 글: {latest[0]} {latest[1]}")
        sys.exit(3)

    result = []
    for day, title, url in sorted(targets):
        post = parse_post(get(url))
        result.append({"date": day.isoformat(), "title": title, "url": url, **post})
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=1))
        return
    for r in result:
        print(f"■ 안장출근길 {r['date']} — {r['url']}")
        if r["insight"]:
            print(f"  오늘의 인사이트: {r['insight']}")
        for it in r["items"]:
            print(f"  {it['no']}. {it['headline']}")
            if it["summary"]:
                print(f"     요약: {' '.join(it['summary'])[:220]}")
            for ln in it["links"]:
                print(f"     기사: {ln['domain'] or '-'} | {ln['title'][:60]} | {ln['url']}")
        for x in r["extras"]:
            print(f"  (부록) {x}")
        print()
    print("※ 단서로만 쓴다: 문장을 옮기지 말고, 사실은 원 기사(read_article.py)로 확인해 원 기사를 출처로 단다.")


if __name__ == "__main__":
    main()
