#!/usr/bin/env python3
"""원 기사 읽기·네이버 뉴스 검색 — 사실 확인(RUNBOOK 1-3)용.

Claude Code 의 WebFetch 는 네이버 도메인을 열지 못해서(2026-09-24 확인) 기사는 이 스크립트로 연다.
네트워크 허용 목록에 *.naver.com 이 있어야 한다. 네이버 뉴스(n.news.naver.com)는 거의 모든 언론사 기사를
같은 형식으로 보여주므로, 다른 언론사 도메인이 막혀 있으면 --search 로 같은 기사의 네이버 뉴스판을 찾아 읽는다.

  python3 automation/read_article.py "https://n.news.naver.com/article/015/0005335256"      # 제목·언론사·날짜·본문
  python3 automation/read_article.py --search "쿠팡 입어보고 결제"                             # 네이버 뉴스 최신순 상위 5건
  python3 automation/read_article.py --search "우버 배민 공정위" --n 8

본문은 사실 확인용으로만 읽는다. 뉴스레터에는 문장을 옮기지 않고 우리 말로 다시 쓴다.
"""
import argparse
import html
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"})
    with urllib.request.urlopen(req, timeout=20) as r:
        charset = r.headers.get_content_charset() or "utf-8"
        return r.read().decode(charset, errors="replace")


def _meta(page, prop):
    m = (re.search(r'<meta[^>]+(?:property|name)="%s"[^>]+content="([^"]*)"' % re.escape(prop), page)
         or re.search(r'<meta[^>]+content="([^"]*)"[^>]+(?:property|name)="%s"' % re.escape(prop), page))
    return html.unescape(m.group(1)).strip() if m else ""


def _clean(fragment):
    t = re.sub(r"<(script|style|figure|table)[^>]*>.*?</\1>", " ", fragment, flags=re.S)
    t = re.sub(r"<br\s*/?>|</p>|</div>", "\n", t)
    t = html.unescape(re.sub(r"<[^>]+>", "", t))
    return "\n".join(re.sub(r"[ \t ​]+", " ", l).strip() for l in t.splitlines() if l.strip())


def read(url):
    page = get(url)
    title = _meta(page, "og:title") or _clean(re.search(r"<title>(.*?)</title>", page, re.S).group(1)) if "<title>" in page else _meta(page, "og:title")
    press = (_meta(page, "og:article:author") or _meta(page, "twitter:creator") or _meta(page, "og:site_name")).replace(" | 네이버", "")
    date = ""
    for pat in (r'data-date-time="([^"]+)"', r'"datePublished"\s*:\s*"([^"]+)"', r'property="article:published_time"[^>]+content="([^"]+)"'):
        m = re.search(pat, page)
        if m:
            date = m.group(1)
            break
    body = ""
    for pat in (r'<article[^>]*id="dic_area"[^>]*>(.*?)</article>',   # 네이버 뉴스
                r'<div[^>]*id="newsct_article"[^>]*>(.*?)</div>\s*</div>',
                r'<article[^>]*>(.*?)</article>',
                r'<div[^>]*(?:id|class)="[^"]*(?:article_?body|articleBody|news_body|view_con)[^"]*"[^>]*>(.*?)</div>'):
        m = re.search(pat, page, re.S | re.I)
        if m and len(_clean(m.group(1))) > 200:
            body = _clean(m.group(1))
            break
    if not body:  # 마지막 수단: 긴 문단들
        body = "\n".join(p for p in (_clean(x) for x in re.findall(r"<p[^>]*>(.*?)</p>", page, re.S)) if len(p) > 40)
    return {"url": url, "title": title, "press": press, "date": date, "body": body,
            "description": _meta(page, "og:description")}


def search(query, n=5):
    url = "https://search.naver.com/search.naver?" + urllib.parse.urlencode({"where": "news", "query": query, "sort": 1})
    page = get(url)
    links = []
    for u in re.findall(r'href="(https://n\.news\.naver\.com/(?:mnews/)?article/\d+/\d+[^"]*)"', page):
        u = html.unescape(u).split("?")[0]
        if u not in links:
            links.append(u)
    return links[:n]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url", nargs="?")
    ap.add_argument("--search", help="네이버 뉴스 검색어(최신순)")
    ap.add_argument("--n", type=int, default=5)
    ap.add_argument("--chars", type=int, default=2500, help="본문 출력 글자 수")
    args = ap.parse_args()
    if not args.url and not args.search:
        ap.error("URL 또는 --search 가 필요합니다")
    try:
        if args.search:
            links = search(args.search, args.n)
            if not links:
                print("✗ 네이버 뉴스 검색 결과에서 기사 링크를 찾지 못했습니다 — 검색어를 바꾸거나 WebSearch 를 쓰세요.")
                sys.exit(1)
            for u in links:
                try:
                    a = read(u)
                    print(f"- {a['date'][:16]} | {a['press']} | {a['title']}\n  {u}\n  {a['description'][:150]}")
                except (urllib.error.URLError, OSError) as e:
                    print(f"- {u} (읽기 실패: {e})")
            return
        a = read(args.url)
    except urllib.error.HTTPError as e:
        print(f"✗ {e.code} — 기사를 열지 못했습니다. --search 로 같은 기사의 네이버 뉴스판을 찾아보세요.")
        sys.exit(2)
    except (urllib.error.URLError, OSError) as e:
        host = urllib.parse.urlsplit(args.url or "https://search.naver.com").hostname
        print(f"✗ {host} 에 접속하지 못했습니다({e}) — 허용 목록 밖 도메인이면 "
              f"--search 로 같은 기사의 네이버 뉴스판(n.news.naver.com)을 찾아 읽으세요.")
        sys.exit(2)
    print(f"제목: {a['title']}\n언론사: {a['press'] or '-'}\n날짜: {a['date'] or '(표기 못 찾음 — 본문·URL 로 확인)'}\n주소: {a['url']}\n")
    print(a["body"][:args.chars] or a["description"] or "(본문을 찾지 못했습니다)")


if __name__ == "__main__":
    main()
