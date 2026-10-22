#!/usr/bin/env python3
"""정부·기관 보도자료(원문, 1차 자료) — 발굴과 숫자 확인용(RUNBOOK 1-1·1-3).

2026-10-22 운영자 '기사 소스가 부족하다': 최근 정규 11호 메인·H PICK 55건의 출처가 모두 네이버뉴스 기사였고 원문은 0건이었다.
클라우드 환경 네트워크 허용 목록에 원문 도메인을 넣은 뒤(같은 날) 실제로 읽히는 곳만 쓴다:
  · 금융위원회(www.fsc.go.kr) · 고용노동부(www.moel.go.kr) · 금융감독원(www.fss.or.kr — 소비자경보 등) 보도자료 — 목록·본문 모두 읽힌다
  · 정책브리핑(www.korea.kr, 모든 부처 보도자료) — 자주 503·연결 끊김이라 다시 시도하고, 안 되면 건너뛴다
  (한국은행 보도자료 목록은 자바스크립트로 그려져 읽히지 않고, 국토부·공정위 사이트는 연결을 끊고, 기획재정부는 mofe.go.kr 로 옮겨 허용 밖이다
   — 그 부처 보도자료는 정책브리핑에 함께 올라온다.)

  python3 automation/fetch_releases.py                       # 어제·오늘 보도자료 목록(기관 · 날짜 · 제목 · 주소)
  python3 automation/fetch_releases.py --date 2026-10-22 --days 1
  python3 automation/fetch_releases.py --grep 대출 금리      # 제목·요약에 낱말이 든 것만
  python3 automation/fetch_releases.py --read "https://www.fsc.go.kr/no010101/87977"   # 본문(숫자 확인용)
  (정책브리핑은 본문이 첨부에만 있는 게 많다 — '첨부 PDF' 주소를 curl -sSL -o 로 받아 PDF 로 읽는다)

본문은 사실 확인용으로만 읽는다. 뉴스레터에는 문장을 옮기지 않고 우리 말로 다시 쓴다.
"""
import argparse
import datetime as dt
import html
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from edith.common import now_kst  # noqa: E402
from edith.style import is_primary  # noqa: E402,F401 — 원문 주소 판정(빌드 경고와 같은 기준)

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
SOURCES = {
    "금융위원회": "https://www.fsc.go.kr/no010101",
    "고용노동부": "https://www.moel.go.kr/news/enews/report/enewsList.do",
    "금융감독원": "https://www.fss.or.kr/fss/bbs/B0000188/list.do?menuNo=200218",
    "정책브리핑": "https://www.korea.kr/briefing/pressReleaseList.do",
}


def get(url, tries=4):
    """정부 사이트는 클라우드 IP 에 503 이나 연결 끊김을 자주 준다 — 몇 번 쉬었다 다시."""
    last = None
    for attempt in range(tries):
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"})
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                return r.read().decode(r.headers.get_content_charset() or "utf-8", errors="replace")
        except (urllib.error.URLError, OSError) as e:
            last = e
            if attempt < tries - 1:
                time.sleep(4 * (attempt + 1))
    raise OSError(f"{url}: {last}")


def _text(fragment):
    t = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", fragment, flags=re.S)
    t = re.sub(r"<br\s*/?>|</p>|</div>|</li>|</tr>", "\n", t)
    t = html.unescape(re.sub(r"<[^>]*$", "", re.sub(r"<[^>]+>", " ", t)))   # 잘린 페이지 끝의 닫히지 않은 태그도 뺀다
    return "\n".join(re.sub(r"[ \t ​]+", " ", l).strip() for l in t.splitlines() if l.strip())


def parse_fsc(page, base="https://www.fsc.go.kr"):
    out = []
    for li in re.findall(r"<li>\s*<div class=\"inner\">(.*?)</li>", page, re.S):
        a = re.search(r'<a href="(/no010101/\d+)[^"]*"\s+title="([^"]+)"', li)
        day = re.search(r'<div class="day">(\d{4}-\d{2}-\d{2})</div>', li)
        if a and day:
            out.append({"org": "금융위원회", "date": day.group(1), "title": " ".join(html.unescape(a.group(2)).split()), "url": base + a.group(1)})
    return out


def parse_moel(page, base="https://www.moel.go.kr/news/enews/report/"):
    out = []
    for tr in re.findall(r"<tr>(.*?)</tr>", page, re.S):
        a = re.search(r'<a href="(enewsView\.do\?news_seq=\d+)"[^>]*title="([^"]+)"', tr)
        day = re.search(r'aria-label="등록일">(\d{4})\.(\d{2})\.(\d{2})<', tr)
        if a and day:
            out.append({"org": "고용노동부", "date": "-".join(day.groups()), "title": " ".join(html.unescape(a.group(2)).split()), "url": base + a.group(1)})
    return out


def parse_fss(page, base="https://www.fss.or.kr"):
    out = []
    for tr in re.findall(r"<tr>(.*?)</tr>", page, re.S):
        a = re.search(r'<td class="title"><a href="(/fss/bbs/B0000188/view\.do\?nttId=\d+)[^"]*">(.*?)</a>', tr, re.S)
        day = re.search(r"<td>\s*(\d{4}-\d{2}-\d{2})\s*</td>", tr)
        if a and day:
            out.append({"org": "금융감독원", "date": day.group(1), "title": _text(a.group(2)), "url": base + a.group(1) + "&menuNo=200218"})
    return out


def parse_korea(page, base="https://www.korea.kr"):
    out = []
    for li in re.findall(r"<li>\s*<a href=\"(/briefing/pressReleaseView\.do\?newsId=\d+)[^\"]*\">(.*?)</a>\s*</li>", page, re.S):
        href, body = li
        title = re.search(r"<strong>(.*?)</strong>", body, re.S)
        lead = re.search(r'<span class="lead">(.*?)</span>', body, re.S)
        src = re.search(r'<span class="source">\s*<span>(\d{4})\.(\d{2})\.(\d{2})</span>\s*<span>([^<]+)</span>', body)
        if title and src:
            out.append({"org": src.group(4).strip(), "date": "-".join(src.groups()[:3]), "title": _text(title.group(1)),
                        "lead": _text(lead.group(1))[:160] if lead else "", "url": base + href})
    return out


PARSERS = {"금융위원회": parse_fsc, "고용노동부": parse_moel, "금융감독원": parse_fss, "정책브리핑": parse_korea}


def releases(days, pages=3):
    """days(YYYY-MM-DD 목록)에 올라온 보도자료 — 기관별로 읽히는 것만. 실패한 기관은 이름만 따로 돌려준다."""
    found, failed = [], []
    for name, url in SOURCES.items():
        try:
            items = []
            for n in range(1, (pages if name == "정책브리핑" else 1) + 1):   # 정책브리핑은 하루 100건 넘게 올라와 몇 쪽 본다
                items += PARSERS[name](get(url + (f"?pageIndex={n}" if name == "정책브리핑" else "")))
                if items and min(i["date"] for i in items) < min(days):
                    break
            found += [i for i in items if i["date"] in days]
        except OSError as e:
            failed.append(f"{name}({type(e).__name__})")
    return found, failed


def read(url):
    return read_page(get(url))


def read_page(page):
    for pat in (r'class="board-view-wrap"[^>]*>(.*?)<div class="board-btn',      # 금융위원회
                r'class="board_view_wrap"[^>]*>(.*?)<div class="(?:synap_view|file)',   # 고용노동부(본문 뒤 미리보기·첨부 전까지)
                r'class="krds-bd-view"[^>]*>(.*?)<div class="btn-wrap"'):   # 금융감독원
        m = re.search(pat, page, re.S)
        if m:
            return _text(m.group(1))
    title = re.search(r'<div class="view_title">\s*<h1>(.*?)</h1>', page, re.S)   # 정책브리핑 — 제목·본문만(메뉴·글자크기 버튼 빼고)
    if title:
        body = re.search(r'class="view_cont"[^>]*>(.*?)<div class="article_footer', page, re.S)
        # 본문이 문서 보기 창(자바스크립트)에만 있는 보도자료가 많다 — 첨부 PDF 주소를 함께 준다(받아서 PDF 로 읽는다)
        pdfs = [f"첨부 PDF: {name.strip()}\n    https://www.korea.kr{html.unescape(href)}"
                for href, name in re.findall(r'<a href="(/common/download\.do\?fileId=\d+[^"]*)">\s*<img[^>]*>([^<]+?\.pdf)\s*</a>', page)]
        return "\n".join([_text(title.group(1)), _text(body.group(1)) if body else "", *pdfs]).strip()
    return _text(page)[:6000]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="YYYY-MM-DD(기본 오늘 KST)")
    ap.add_argument("--days", type=int, default=2, help="이 날짜부터 거꾸로 며칠(기본 2 — 어제·오늘)")
    ap.add_argument("--grep", nargs="*", help="제목·요약에 이 낱말 중 하나라도 든 것만")
    ap.add_argument("--read", metavar="URL", help="보도자료 본문 읽기")
    args = ap.parse_args()
    if args.read:
        print(read(args.read))
        return 0
    end = dt.date.fromisoformat(args.date) if args.date else now_kst().date()
    days = [(end - dt.timedelta(days=k)).isoformat() for k in range(args.days)]
    items, failed = releases(days)
    if args.grep:
        items = [i for i in items if any(w in i["title"] + i.get("lead", "") for w in args.grep)]
    for i in sorted(items, key=lambda i: (i["date"], i["org"]), reverse=True):
        print(f"[{i['org']}] {i['date']} · {i['title']}\n    {i['url']}" + (f"\n    {i['lead']}" if i.get("lead") else ""))
    print(f"— {len(items)}건" + (f" · 못 읽음: {', '.join(failed)}" if failed else ""), file=sys.stderr)
    return 0 if items or not failed else 2


if __name__ == "__main__":
    sys.exit(main())
