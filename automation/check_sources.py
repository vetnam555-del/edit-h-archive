#!/usr/bin/env python3
"""숫자 2곳 대조 — 빌드 전에(RUNBOOK 3단계) content 의 숫자가 그 이슈 원 기사 두 곳에 다 있는지 본다(edith/twosource.py).

  python3 automation/check_sources.py                       # 오늘(KST) 호
  python3 automation/check_sources.py --date 2026-11-04     # 그날 호(지난 호는 기록 — 재 보기만)
  python3 automation/check_sources.py --offline             # 읽어 둔 기사로만(네트워크 없이)

기사는 read_article.py 로 하나씩 읽는다(병렬이면 시간 초과가 난다 — 11/04 11곳 중 3곳). 읽은 기사는 automation/.state/articles/ 에 두고,
build_issue.py 가 그 기사로 네트워크 없이 다시 대조해 한 곳에만 있는 숫자가 남아 있으면 빌드를 막는다(2026-11-05 호~).
못 읽은 기사는 경고만 — 발행을 멈추지 않는다.
종료 코드: 0 통과(경고는 있을 수 있음) · 1 막음(원 기사 한 곳에만 있는 숫자).
"""
import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path

AUTOMATION = Path(__file__).resolve().parent
sys.path.insert(0, str(AUTOMATION))
from edith import content, twosource  # noqa: E402
from edith.common import now_kst  # noqa: E402

CACHE = AUTOMATION / ".state" / "articles"


def cache_path(url, cache=None):
    return Path(cache or CACHE) / (hashlib.sha1(url.encode("utf-8")).hexdigest()[:16] + ".json")


def cached(url, cache=None):
    try:
        return json.loads(cache_path(url, cache).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


GOV_HOSTS = ("korea.kr", "fsc.go.kr", "moel.go.kr", "fss.or.kr", "mofe.go.kr")   # 보도자료는 fetch_releases 가 본문 칸을 안다
MIN_NUMBERS = 3   # 본문에서 숫자를 이만큼도 못 찾으면 '못 읽음' — 11/02 정책브리핑은 본문이 문서 보기 창에만 있어 저작권 안내문만 읽혔다


def is_gov(url):
    from urllib.parse import urlsplit
    host = urlsplit(url).hostname or ""
    return any(host == h or host.endswith("." + h) for h in GOV_HOSTS)


def read_one(url):
    """기사·보도자료 한 곳 → dict. 정책브리핑 등 부처 보도자료는 fetch_releases.read(본문 칸·첨부 PDF 주소), 그 밖은 read_article.read.
    첨부 PDF 를 하나라도 못 읽으면 그 보도자료는 통째로 '못 읽음'(OSError → 경고만) — 반쯤 읽은 본문으로 대조하면 못 받은 PDF 에만 있는
    숫자를 '다른 기사 한 곳에만 있다'고 잘못 막는다(2026-11-05 고용 '324만명'·'19.9%' — 두 번째 PDF 가 접속 끊김으로 안 받아졌다)."""
    if is_gov(url):
        import fetch_releases
        text = fetch_releases.read(url)
        extra = []
        for pdf in re.findall(r"첨부 PDF:[^\n]*\n\s*(https?://\S+)", text)[:2]:   # 본문이 첨부 PDF 에만 있는 보도자료가 많다(11/02 수출입 동향)
            try:
                extra.append(pdf_text(pdf))
            except Exception as e:   # 내려받기 실패·PDF 아님·pdftotext 없음 모두
                raise OSError(f"첨부 PDF 못 읽음 {pdf} ({str(e)[:60]}) — 본문 일부만 읽힌 보도자료라 대조에 안 쓴다") from e
        return {"url": url, "title": "", "press": "", "date": "", "description": "", "body": "\n".join([text, *extra])}
    import read_article
    return read_article.read(url)


def download(url, timeout=40, tries=3, wait=2.0):
    """주소 → 바이트. 끊김·시간 초과·5xx 는 tries 번까지 다시(11/05 정책브리핑 PDF 'connection reset'), 4xx 는 바로 실패."""
    import urllib.error
    import urllib.request
    from read_article import UA
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code < 500 or i + 1 >= tries:
                raise
        except Exception:   # 접속 끊김(ConnectionResetError)·시간 초과·덜 받은 응답(IncompleteRead)
            if i + 1 >= tries:
                raise
        time.sleep(wait * (i + 1))


def pdf_text(url, timeout=40):
    """첨부 PDF → 글(pdftotext). PDF 가 아닌 응답(오류 페이지)·pdftotext 실패는 오류 — 그 보도자료는 '못 읽음'(read_one)."""
    import subprocess
    import tempfile
    data = download(url, timeout=timeout)
    if not data.startswith(b"%PDF"):
        raise ValueError("PDF 가 아닌 응답(오류 페이지·다른 문서 형식)")
    with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
        f.write(data)
        f.flush()
        return subprocess.run(["pdftotext", "-layout", f.name, "-"], capture_output=True, text=True, timeout=60, check=True).stdout


def usable(a):
    """숫자 대조에 쓸 만한 본문인가 — 날짜(년·월·일)를 뺀 숫자가 MIN_NUMBERS 개 이상(제목·안내문만 읽힌 페이지를 걸러 낸다)."""
    return sum(1 for n in twosource.article_numbers(a) if n[2] not in twosource.DATE_UNITS | {"년"}) >= MIN_NUMBERS


def fetch(url, tries=2, cache=None):
    """기사 한 곳 → dict(제목·언론사·요약·본문) 또는 None(못 읽음). 읽으면 .state/articles/ 에 둔다."""
    tries = 1 if is_gov(url) else tries   # fetch_releases.get 이 이미 4번까지 다시 시도한다(정책브리핑 503)
    for i in range(tries):
        try:
            a = read_one(url)
            if not usable(a):   # 본문을 못 찾은 쪽(문서 보기 창·로그인 벽·사진 기사) — 숫자 대조에 못 쓴다
                raise OSError(f"본문에서 숫자를 {MIN_NUMBERS}개도 못 찾음(본문이 첨부 문서에만 있거나 본문 칸을 못 찾음)")
            p = cache_path(url, cache)
            p.parent.mkdir(parents=True, exist_ok=True)
            keep = {k: a.get(k) for k in ("url", "title", "press", "date", "description", "body")}
            p.write_text(json.dumps({**keep, "read_at": now_kst().isoformat(timespec="seconds")}, ensure_ascii=False), encoding="utf-8")
            return keep
        except Exception as e:   # noqa: BLE001 — 접속 실패·시간 초과·HTML 바뀜 모두 '못 읽음'(경고)으로
            if i + 1 < tries:
                time.sleep(2)
            else:
                print(f"  · 못 읽음 {url} ({str(e)[:80]})", file=sys.stderr)
    return None


def urls(d):
    return [s["url"] for _, sources, _ in twosource.issue_texts(d) for s in sources if s.get("url")]


def articles_for(d, offline=False, cache=None):
    """그 호 이슈 sources 의 기사 → {url: 기사 dict 또는 None}. offline 이면 읽어 둔 것만."""
    out = {}
    for url in dict.fromkeys(urls(d)):
        out[url] = cached(url, cache) or (None if offline else fetch(url, cache=cache))
    return out


def report(res):
    """사람이 읽는 줄들 — 첫 줄은 RUNBOOK 6단계 보고 '숫자 2곳 대조:' 줄에 그대로 쓴다."""
    read = sum(r["read"] for r in res["issues"])
    total = sum(r["sources"] for r in res["issues"])
    lines = [f"숫자 2곳 대조: 막음 {len(res['blocked'])} · 경고 {len(res['warnings'])} · 기사 {read}/{total}곳 읽음"]
    lines += [f"  ✗ {b}" for b in res["blocked"]]
    lines += [f"  ↘ {w}" for w in res["warnings"]]
    return lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="YYYY-MM-DD (기본: 오늘 KST)")
    ap.add_argument("--offline", action="store_true", help="읽어 둔 기사로만 대조(네트워크 없이)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    day = args.date or now_kst().date().isoformat()
    try:
        d = content.load(day)
    except content.ContentError as e:
        raise SystemExit(f"✗ 콘텐츠 검증 실패\n{e}")
    res = twosource.check(d, articles_for(d, offline=args.offline))
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
    else:
        print("\n".join(report(res)))
        if res["blocked"]:
            print("→ content 를 고친 뒤 이 검사를 다시 돌리고 빌드하세요(build_issue.py 도 같은 기사로 다시 대조해 막는다)")
    sys.exit(1 if res["blocked"] else 0)


if __name__ == "__main__":
    main()
