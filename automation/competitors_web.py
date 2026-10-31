#!/usr/bin/env python3
"""경쟁 매체 웹 추적기 — 토큰 없이, 경쟁 매체의 공개 RSS·글 목록에서 이번 주 다룬 주제를 모아 우리 호와 견준다.

2026-11-01 운영자 "모든 걸 너가 알아서 해줘" → "지금 바로 웹 추적기 만들어줘".
인스타 숫자(competitors_ig.py)는 운영자가 메타 토큰을 넣어야 돈다. 이건 운영자 손이 전혀 필요 없는 쪽이다.

지키는 것(공개 저장소·남의 사이트):
- 각 사이트 robots.txt 를 먼저 읽고 허락된 주소만 연다(urllib.robotparser). 거부되거나 막히면 그 매체만 건너뛴다.
- 주 1회, 매체당 몇 번만 요청하고 같은 사이트는 1초씩 쉰다. 인스타 페이지는 열지 않는다(약관).
- 제목·주소·날짜만 남긴다(본문은 저장하지 않는다).

읽는 방식(config competitors_web.sources 의 kind):
  rss     — RSS 2.0/Atom(pubDate·updated)
  links   — 글 목록 페이지에서 href 가 match(정규식)에 맞는 링크와 그 글자. 날짜가 글자에 있으면(2026.10.30) 쓰고,
            없으면 지난 수집에 없던 글을 '새 글'로 센다
  sitemap — 사이트맵에서 match 에 맞는 주소를 lastmod 최신순 limit 개 → 각 글의 og:title

결과: automation/competitors/web/{날짜}.json + summary.md — 매체별 이번 주 글, 우리와 겹친 글(같은 말), 여러 매체가 다뤘는데
우리는 안 다룬 말. 일요일 21:00 주간 루틴과 개선 루틴이 읽는다.

  python3 automation/competitors_web.py             # 모아 저장(오늘 이미 모았으면 건너뜀)
  python3 automation/competitors_web.py --dry-run   # 모아서 요약만 출력
  python3 automation/competitors_web.py --force     # 오늘 이미 모았어도 다시
종료 코드: 0 = 저장(한 곳이라도 읽음)·오늘 이미 모음, 1 = 한 곳도 못 읽음.
"""
import argparse
import email.utils
import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from edith.common import CONTENT_DIR, KST, ROOT, load_config, now_kst  # noqa: E402

OUT = ROOT / "automation" / "competitors" / "web"
UA = "EDIT-H-competitors-web/1.0 (+https://github.com/vetnam555-del/edit-h-archive)"
WINDOW_DAYS = 7
MAX_BYTES = 8 * 1024 * 1024
DAY_FILE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.json$")
DATE_IN_TEXT = re.compile(r"(20\d{2})\.\s?(\d{1,2})\.\s?(\d{1,2})")
SHORT_DATE = re.compile(r"(?<![\d.])(\d{2})\.(\d{2})\.(\d{2})(?![\d.])")      # 26.10.30 (트렌드어워드 레터)
VERB_END = ("지", "데", "할", "까", "요", "다", "죠", "듯", "걸", "던", "된", "될", "줄", "함", "됨")   # 같지·건데·영원할 같은 말끝
JOSA = ("에서는", "으로는", "에서", "으로", "에게", "까지", "부터", "보다", "처럼", "하고", "이랑", "이다", "했다", "한다", "된다",
        "은", "는", "이", "가", "을", "를", "의", "에", "로", "과", "와", "도", "만", "랑")
STOP = set("""오늘 이번 이번주 지금 요즘 최근 올해 내년 작년 우리 나의 너의 무엇 뭐가 뭘까 왜 어떻게 얼마나 정리 총정리 요약 추천 가이드 방법 이유
뉴스 소식 레터 뉴스레터 트렌드 이야기 모음 시리즈 특집 단독 속보 영상 사진 공개 발표 시작 진행 관련 대한 위한 통해 이상 이하 가지 하나 모두
있다 없다 있는 없는 하는 되는 같은 다른 그리고 하지만 그래서 정말 진짜 가장 매우 다시 함께 바로 이제 처음 마지막 오늘의 이번엔 주간 월간
trend word a the of and to in for 용례 oo 트워드 휴재 vs 사람 인기 광고 feat""".split())


# ── 읽기 ──────────────────────────────────────────────────────────────

class Fetcher:
    """robots.txt 를 지키고 같은 사이트는 1초씩 쉬며 읽는다. 거부·실패는 RuntimeError(주소만, 비밀값 없음)."""

    def __init__(self, delay=1.0, tries=2):
        self.delay, self.tries, self.robots, self.why, self.last = delay, tries, {}, {}, {}

    def allowed(self, url):
        origin = "{0.scheme}://{0.netloc}".format(urllib.parse.urlsplit(url))
        if origin not in self.robots:
            rp = urllib.robotparser.RobotFileParser()
            for attempt in range(self.tries):
                try:
                    req = urllib.request.Request(origin + "/robots.txt", headers={"User-Agent": UA})
                    with urllib.request.urlopen(req, timeout=20) as r:
                        rp.parse(r.read(512 * 1024).decode("utf-8", "replace").splitlines())
                    break
                except urllib.error.HTTPError as e:
                    rp.disallow_all = e.code in (401, 403)   # 막힌 사이트는 읽지 않는다
                    rp.allow_all = e.code >= 404 and not rp.disallow_all
                    if rp.disallow_all:
                        self.why[origin] = f"사이트가 자동 접속을 막음(robots.txt {e.code})"
                    break
                except (urllib.error.URLError, TimeoutError, OSError) as e:
                    rp.disallow_all = True    # 규칙을 못 읽으면 읽지 않는다(다음 수집 때 다시)
                    self.why[origin] = f"robots.txt 를 읽지 못함({type(getattr(e, 'reason', e)).__name__})"
                    time.sleep(self.delay * 2)
            if not rp.disallow_all:
                self.why.pop(origin, None)
            self.robots[origin] = rp
        return self.robots[origin].can_fetch(UA, url)

    def get(self, url):
        if not self.allowed(url):
            origin = "{0.scheme}://{0.netloc}".format(urllib.parse.urlsplit(url))
            raise RuntimeError(f"{self.why.get(origin, 'robots.txt 가 허락하지 않음')}: {url}")
        host = urllib.parse.urlsplit(url).netloc
        for attempt in range(self.tries):
            wait = self.delay - (time.monotonic() - self.last.get(host, -1e9))
            if wait > 0:
                time.sleep(wait)
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ko,en;q=0.5"})
                with urllib.request.urlopen(req, timeout=30) as r:
                    data = r.read(MAX_BYTES + 1)
                break
            except urllib.error.HTTPError as e:
                if e.code < 500 or attempt + 1 == self.tries:
                    raise RuntimeError(f"HTTP {e.code}: {url}") from None
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                if attempt + 1 == self.tries:
                    raise RuntimeError(f"접속 실패({type(getattr(e, 'reason', e)).__name__}): {url}") from None
            finally:
                self.last[host] = time.monotonic()
        if len(data) > MAX_BYTES:
            raise RuntimeError(f"{MAX_BYTES // 1024 // 1024}MB 를 넘는다: {url}")
        return data.decode("utf-8", "replace")


def clean(text, n=140):
    text = html.unescape(re.sub(r"<[^>]+>", " ", str(text or "")))
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= n else text[: n - 1] + "…"


def parse_when(s):
    """RSS pubDate·ISO 8601·'2026.10.30' → KST datetime(없으면 None)."""
    s = str(s or "").strip()
    if not s:
        return None
    try:
        t = email.utils.parsedate_to_datetime(s)
        return t.astimezone(KST) if t.tzinfo else t.replace(tzinfo=KST)
    except (TypeError, ValueError, IndexError):
        pass
    try:
        t = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return t.astimezone(KST) if t.tzinfo else t.replace(tzinfo=KST)
    except ValueError:
        pass
    m = DATE_IN_TEXT.search(s)
    year = None
    if not m:
        m, year = SHORT_DATE.search(s), 2000
    if m:
        try:
            return datetime((year or 0) + int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=KST)
        except ValueError:
            return None
    return None


def parse_rss(text):
    """RSS 2.0·Atom → [{title, link, date}]."""
    root = ET.fromstring(text.encode("utf-8") if isinstance(text, str) else text)
    out = []
    for it in root.iter():
        tag = it.tag.rsplit("}", 1)[-1]
        if tag not in ("item", "entry"):
            continue
        fields = {c.tag.rsplit("}", 1)[-1]: c for c in it}
        title = clean(fields["title"].text if "title" in fields else "")
        link = ""
        if "link" in fields:
            link = (fields["link"].text or fields["link"].get("href") or "").strip()
        when = None
        for key in ("pubDate", "published", "updated", "date"):
            if key in fields and fields[key].text:
                when = parse_when(fields[key].text)
                break
        if title:
            out.append({"title": title, "link": link, "date": when.strftime("%Y-%m-%d") if when else None})
    return out


def parse_links(text, match, base):
    """글 목록 페이지 → [{title, link, date}] — href 가 match 에 맞는 a 태그(같은 주소는 처음 것만)."""
    pat = re.compile(match)
    out, seen = [], set()
    for href, inner in re.findall(r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', text, re.S | re.I):
        href = html.unescape(href)
        if not pat.search(href):
            continue
        link = urllib.parse.urljoin(base, href)
        title = clean(inner)
        if link in seen or len(title) < 4:
            continue
        seen.add(link)
        when = parse_when(clean(inner, 2000))   # 날짜는 자르기 전 전체 글자에서(레터 목록은 날짜가 끝에 있다)
        out.append({"title": title, "link": link, "date": when.strftime("%Y-%m-%d") if when else None})
    return out


def parse_sitemap(text, match, limit):
    """사이트맵 → lastmod 최신순으로 match 에 맞는 주소 limit 개 [(link, date)]."""
    rows = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>\s*(?:<lastmod>\s*([^<\s]+)\s*</lastmod>)?", text)
    pat = re.compile(match)
    rows = [(loc, parse_when(mod)) for loc, mod in rows if pat.search(loc)]
    rows.sort(key=lambda r: r[1] or datetime.min.replace(tzinfo=KST), reverse=True)
    return [(loc, when.strftime("%Y-%m-%d") if when else None) for loc, when in rows[:limit]]


def og_title(text):
    m = re.search(r'<meta[^>]+property="og:title"[^>]*content="([^"]*)"', text) or re.search(r"<title>(.*?)</title>", text, re.S)
    return clean(m.group(1)) if m else ""


def read_source(src, fetch):
    """한 매체 → [{title, link, date}]. 실패는 RuntimeError."""
    kind, url = src["kind"], src["url"]
    if kind == "rss":
        try:
            return parse_rss(fetch(url))
        except ET.ParseError as e:
            raise RuntimeError(f"RSS 를 읽지 못함: {e}") from None
    if kind == "links":
        return parse_links(fetch(url), src["match"], url)
    if kind == "sitemap":
        items = []
        for link, date in parse_sitemap(fetch(url), src["match"], int(src.get("limit") or 10)):
            try:
                title = og_title(fetch(link))
            except RuntimeError:
                continue
            if title:
                items.append({"title": title, "link": link, "date": date})
        return items
    raise RuntimeError(f"모르는 kind: {kind}")


# ── 주제 견주기 ─────────────────────────────────────────────────────────

def keywords(text):
    """한국어 제목 → 의미 있는 말 집합(조사 떼기·불용어·숫자 빼기). 형태소 분석 없이 가볍게."""
    out = set()
    for tok in re.findall(r"[0-9A-Za-z가-힣]+", str(text or "")):
        tok = tok.lower()
        for j in JOSA:
            if tok.endswith(j) and len(tok) - len(j) >= 2:
                tok = tok[: -len(j)]
                break
        if len(tok) < 2 or tok.isdigit() or tok in STOP or re.fullmatch(r"\d+[a-z가-힣]?", tok) or tok.endswith(VERB_END):
            continue
        out.add(tok)
    return out


def our_text(day, days=WINDOW_DAYS, folder=CONTENT_DIR):
    """최근 days 일 우리 호의 제목·키워드·소식 제목 → ({날짜: 글}, 말 집합)."""
    texts = {}
    for i in range(days):
        d = (day - timedelta(days=i)).strftime("%Y-%m-%d")
        f = folder / f"{d}.json"
        if not f.exists():
            continue
        try:
            c = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            continue
        parts = [c.get("title"), c.get("hero_title"), " ".join(c.get("keywords") or [])]
        for it in c.get("items") or []:
            parts += [it.get("title"), it.get("tag")]
        for b in c.get("briefs") or []:
            parts.append(b.get("title") if isinstance(b, dict) else b)
        big = c.get("big_issue")
        if isinstance(big, dict):
            parts.append(big.get("title"))
        texts[d] = " ".join(str(p) for p in parts if p)
    words = set()
    for t in texts.values():
        words |= keywords(t)
    return texts, words


def shared(words_a, words_b):
    """겹친 말 — 2개 이상이거나, 3글자 이상 말 하나."""
    common = words_a & words_b
    return sorted(common) if len(common) >= 2 or any(len(w) >= 3 for w in common) else []


def compare(results, ours):
    """매체 글마다 우리와 겹친 말을 붙이고, 2곳 이상이 다뤘는데 우리는 안 다룬 말을 센다."""
    missed = defaultdict(set)
    for r in results:
        for it in r.get("items") or []:
            words = keywords(it["title"])
            it["overlap"] = shared(words, ours) if it.get("recent") else []
            if it.get("recent"):
                for w in words - ours:
                    missed[w].add(r["name"])
    gaps = sorted(((w, sorted(names)) for w, names in missed.items() if len(names) >= 2), key=lambda x: (-len(x[1]), x[0]))
    return gaps[:15]


# ── 모으기·남기기 ────────────────────────────────────────────────────────

def settings(cfg=None):
    cfg = cfg or load_config()
    sources = []
    for s in (cfg.get("competitors_web") or {}).get("sources") or []:
        if s.get("kind") not in ("rss", "links", "sitemap") or not str(s.get("url", "")).startswith("https://"):
            raise ValueError(f"competitors_web 출처 형식이 틀렸다: {s}")
        if s["kind"] in ("links", "sitemap"):
            re.compile(s.get("match") or "")
        sources.append(dict(s))
    return sources


def previous(day, folder=OUT):
    """지난 수집의 {매체: 글 주소 집합}."""
    names = [DAY_FILE.match(f.name) for f in folder.glob("*.json")] if folder.exists() else []
    days = sorted(m.group(1) for m in names if m and m.group(1) < day)
    if not days:
        return {}, None
    data = json.loads((folder / f"{days[-1]}.json").read_text(encoding="utf-8"))
    return {s["name"]: {i["link"] for i in s.get("items") or []} for s in data.get("sources") or []}, days[-1]


def collect(sources, fetch, now, prev):
    since = (now - timedelta(days=WINDOW_DAYS)).strftime("%Y-%m-%d")
    results = []
    for src in sources:
        row = {"name": src["name"], "group": src.get("group", ""), "url": src["url"], "kind": src["kind"]}
        try:
            items = read_source(src, fetch)
        except RuntimeError as e:
            row.update(ok=False, error=str(e), items=[])
            results.append(row)
            continue
        seen_before = prev.get(src["name"])
        for it in items:
            if it["date"]:
                it["recent"] = it["date"] >= since
            else:   # 날짜가 없는 목록: 지난 수집에 없던 글이 새 글(첫 수집이면 모두)
                it["recent"] = seen_before is None or it["link"] not in seen_before
        row.update(ok=True, items=items[:40])
        results.append(row)
    return results


def render(results, gaps, ours_days, prev_day, now):
    lines = [f"# 경쟁 매체 웹 — 이번 주 다룬 주제 ({now:%Y-%m-%d %H:%M} KST 자동 생성)", "",
             f"공개 RSS·글 목록만 robots.txt 를 지켜 읽는다(제목·주소만 저장). 이번 주 = 최근 {WINDOW_DAYS}일"
             + (f"(날짜가 없는 목록은 지난 수집 {prev_day} 뒤 새로 보인 글)." if prev_day else "(날짜가 없는 목록은 첫 수집이라 지금 보이는 글 모두)."),
             f"우리 호: {', '.join(sorted(ours_days)) or '없음'}. 만든 곳: `automation/competitors_web.py`(주 1회, `.github/workflows/competitors-web.yml`).", "",
             "| 매체 | 무리 | 이번 주 글 | 우리와 겹친 글 |", "|---|---|---|---|"]
    for r in results:
        if r["ok"]:
            recent = [i for i in r["items"] if i.get("recent")]
            lines.append(f"| {r['name']} | {r['group'] or '–'} | {len(recent)} | {sum(1 for i in recent if i['overlap'])} |")
        else:
            lines.append(f"| {r['name']} | {r['group'] or '–'} | 못 읽음 | – |")
    if gaps:
        lines += ["", "## 여러 매체가 다뤘는데 우리는 안 다룬 말 (2곳 이상)", ""]
        lines += [f"- **{w}** — {', '.join(names)}" for w, names in gaps]
    over = [(r["name"], i) for r in results if r["ok"] for i in r["items"] if i.get("recent") and i["overlap"]]
    if over:
        lines += ["", "## 우리와 겹친 글", ""]
        lines += [f"- {name}: 「{i['title'][:80]}」 — 겹친 말: {'·'.join(i['overlap'][:5])}" for name, i in over]
    lines += ["", "## 매체별 이번 주 글", ""]
    for r in results:
        if not r["ok"]:
            continue
        recent = [i for i in r["items"] if i.get("recent")]
        lines += [f"### {r['name']} ({len(recent)})", ""]
        lines += [f"- {(i['date'] or '')[5:].replace('-', '/')} 「{i['title'][:90]}」 {urllib.parse.unquote(i['link'])}".replace("-  「", "- 「")
                  for i in recent[:12]] or ["- (이번 주 새 글 없음)"]
        lines.append("")
    failed = [r for r in results if not r["ok"]]
    if failed:
        lines += ["## 못 읽은 곳", ""]
        lines += [f"- {r['name']}: {r['error']}" for r in failed]
    return "\n".join(lines).rstrip() + "\n"


def main(argv=None, fetch=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true", help="모아서 요약만 출력, 저장 안 함")
    ap.add_argument("--force", action="store_true", help="오늘 이미 모았어도 다시")
    args = ap.parse_args(argv)
    now = now_kst()
    day = now.strftime("%Y-%m-%d")
    path = OUT / f"{day}.json"
    if path.exists() and not (args.force or args.dry_run):
        print(f"오늘({day}) 이미 모았다 — 건너뜀(다시 모으려면 --force)")
        return 0
    sources = settings()
    prev, prev_day = previous(day)
    results = collect(sources, fetch or Fetcher().get, now, prev)
    ours_texts, ours_words = our_text(now.date())
    gaps = compare(results, ours_words)
    md = render(results, gaps, ours_texts, prev_day, now)
    good = sum(r["ok"] for r in results)
    if args.dry_run:
        print(md)
    else:
        OUT.mkdir(parents=True, exist_ok=True)
        record = {"collected_at": now.strftime("%Y-%m-%d %H:%M KST"), "window_days": WINDOW_DAYS, "ours": sorted(ours_texts),
                  "gaps": [{"word": w, "sources": n} for w, n in gaps], "sources": results}
        path.write_text(json.dumps(record, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        (OUT / "summary.md").write_text(md, encoding="utf-8")
        print(f"✓ 경쟁 매체 웹 {good}/{len(results)}곳 — {path.relative_to(ROOT)}")
    for r in results:
        if not r["ok"]:
            print(f"  ✗ {r['name']}: {r['error']}")
    return 0 if good else 1


if __name__ == "__main__":
    sys.exit(main())
