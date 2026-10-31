#!/usr/bin/env python3
"""새 호 페이지를 검색엔진에 바로 알린다 — IndexNow(네이버·빙 등 참여 검색엔진이 한 번에 받는다).

2026-10-31 경쟁 비교 2차(`reviews/2026-10-31-competitors.md`): 잘 되는 매체는 웹 검색으로도 독자를 모으는데 우리는 인스타·메일 둘뿐이다.
구글 서치 콘솔·네이버 서치어드바이저 등록은 운영자 계정이 필요하지만(OWNER_TODO), IndexNow 는 사이트에 키 파일만 두면 된다.
키는 공개 값이다 — 저장소 맨 위 `{키}.txt` 가 '이 사이트 주인이 보낸 알림'이라는 증명이다(config `indexnow_key`).
GitHub Pages 주소가 하위 경로(/edit-h-archive/)라 키 파일 위치(keyLocation)를 함께 보내고, 그 아래 주소만 알린다(IndexNow 규칙).

  python3 automation/indexnow.py --date 2026-10-31             # 그 호 페이지 + 첫 화면
  python3 automation/indexnow.py --commits "$EVENT_COMMITS"    # 푸시에서 새로 생기거나 바뀐 호 페이지(워크플로)
  python3 automation/indexnow.py --date 2026-10-31 --dry-run   # 보낼 내용만 출력

페이지가 아직 배포 전이면(푸시 직후 GitHub Pages 가 1~2분 걸린다) 키 파일·페이지가 열릴 때까지 최대 10분 기다린다.
종료 코드: 0 = 보냄(200·202) 또는 보낼 것 없음, 1 = 거절(키·주소 문제 — 400·403·422), 2 = 접속 실패·너무 잦음(429).
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from edith.common import ROOT, load_config, now_kst  # noqa: E402

ENDPOINT = "https://api.indexnow.org/indexnow"
UA = "EDIT-H-indexnow/1.0 (+https://github.com/vetnam555-del/edit-h-archive)"
ISSUE_PAGE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.html$")
KEY_RE = re.compile(r"^[A-Za-z0-9-]{8,128}$")


def settings(cfg=None):
    """(사이트 주소, 키, 키 파일 주소)."""
    cfg = cfg or load_config()
    site = cfg["site_url"].rstrip("/")
    key = str(cfg.get("indexnow_key") or "")
    if not KEY_RE.match(key):
        raise SystemExit("config indexnow_key 가 없거나 형식이 틀렸다(영문·숫자·- 8~128자)")
    return site, key, f"{site}/{key}.txt"


def urls_for(dates, site):
    """호 페이지 + 첫 화면(목록). 날짜는 중복 없이 들어온 순서대로."""
    pages = [f"{site}/{d}.html" for d in dict.fromkeys(dates)]
    return pages + [f"{site}/"] if pages else []


def dates_from_commits(commits_json):
    """푸시 이벤트의 commits(added·modified)에서 맨 위 호 페이지(YYYY-MM-DD.html) 날짜. 지운 파일은 알리지 않는다."""
    try:
        commits = json.loads(commits_json or "null") or []
    except json.JSONDecodeError:
        return []
    out = []
    for c in commits:
        for path in (c.get("added") or []) + (c.get("modified") or []):
            m = ISSUE_PAGE.match(path)
            if m:
                out.append(m.group(1))
    return list(dict.fromkeys(out))


def payload(urls, site, key, key_url):
    host = urllib.parse.urlsplit(site).hostname
    return {"host": host, "key": key, "keyLocation": key_url, "urlList": urls}


def fetch(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read().decode("utf-8", errors="replace")


def wait_live(url, expect=None, timeout=600, step=30):
    """주소가 200 으로 열리고(expect 가 있으면 본문에 그 글자가 있고) 나면 True. timeout 초 안에 안 되면 False."""
    end = time.time() + timeout
    while True:
        try:
            status, body = fetch(url)
            if status == 200 and (expect is None or expect in body):
                return True
        except (urllib.error.URLError, OSError):
            pass
        if time.time() >= end:
            return False
        time.sleep(step)


def submit(body, timeout=30):
    """(HTTP 코드, 응답 앞부분). 200 = 받음, 202 = 받음(키 확인 중)."""
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(ENDPOINT, data=data, method="POST",
                                 headers={"Content-Type": "application/json; charset=utf-8", "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", errors="replace")[:300]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")[:300]


MEANING = {200: "받음", 202: "받음(키 확인 중)", 400: "요청 형식 오류", 403: "키가 맞지 않음(키 파일 확인)",
           422: "주소가 사이트·키 위치 밖이거나 키 불일치", 429: "너무 잦은 요청(나중에 다시)"}


def summary(lines):
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", action="append", help="알릴 호 YYYY-MM-DD(여러 번 줄 수 있다). 없으면 --commits, 그것도 없으면 오늘")
    ap.add_argument("--commits", help="푸시 이벤트 commits JSON(워크플로의 toJSON(github.event.commits))")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--wait", type=int, default=600, help="페이지·키 파일이 열리길 기다릴 최대 초")
    args = ap.parse_args()

    site, key, key_url = settings()
    if args.date:
        dates = args.date
    elif args.commits is not None:
        dates = dates_from_commits(args.commits)
    else:
        dates = [now_kst().date().isoformat()]
    urls = urls_for(dates, site)
    if not urls:
        summary(["### IndexNow", "알릴 호 페이지가 없다(이번 푸시에 YYYY-MM-DD.html 변경 없음)."])
        return 0
    body = payload(urls, site, key, key_url)
    if args.dry_run:
        print(json.dumps(body, ensure_ascii=False, indent=1))
        return 0
    if not (ROOT / f"{key}.txt").exists():
        summary(["### IndexNow", f"키 파일 {key}.txt 가 저장소에 없다 — 보내지 않았다."])
        return 1
    if not wait_live(key_url, expect=key, timeout=args.wait):
        summary(["### IndexNow", f"키 파일이 {args.wait}초 안에 열리지 않았다(Pages 배포 지연?) — 보내지 않았다."])
        return 2
    live = [u for u in urls if wait_live(u, timeout=args.wait)]
    if not live:
        summary(["### IndexNow", "알릴 페이지가 아직 열리지 않는다 — 보내지 않았다."])
        return 2
    code, text = submit(payload(live, site, key, key_url))
    lines = ["### IndexNow", f"- 보낸 주소 {len(live)}개: " + " · ".join(live), f"- 응답 {code} {MEANING.get(code, '')}".rstrip()]
    if code not in (200, 202) and text.strip():
        lines.append(f"- 응답 본문: {text.strip()[:200]}")
    summary(lines)
    if code in (200, 202):
        return 0
    return 1 if code in (400, 403, 422) else 2


if __name__ == "__main__":
    sys.exit(main())
