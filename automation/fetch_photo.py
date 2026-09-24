#!/usr/bin/env python3
"""카드뉴스 표지 사진 — 위키미디어 커먼즈에서 재사용 가능한 사진을 찾아 내려받는다.

뉴스 보도사진은 라이선스 없이 쓸 수 없으므로, 출처 표기만 하면 되는 사진(CC0·퍼블릭 도메인·CC BY)만 고른다.
CC BY-SA 는 글자를 얹은 표지 이미지까지 같은 라이선스로 공개해야 할 수 있어 기본에서 뺐다(--allow-sa 로만 허용).
해상도: 표지(1080×1350)를 꽉 채울 때 10% 넘게 늘려야 하는 사진은 흐려지므로 후보에서 뺀다
(가로로 아주 긴 파노라마도 여기서 빠진다 — 4:5 로 자르면 대부분이 잘려 나가 어차피 맞지 않는다).
내려받을 때는 1280px 또는 1920px 폭 중 표지를 채우는 가장 작은 쪽을 받는다(용량 절약).
키 없이 쓸 수 있는 공개 API 라서 클라우드 환경의 네트워크 허용 목록에
*.wikimedia.org(검색 commons · 원본 upload · 썸네일 thumb)만 있으면 된다. 막혀 있으면 코드 2로 끝나고,
그날은 사진 없이(핵심어 표지) 발행하면 된다.

사용
  python3 automation/fetch_photo.py "fresh vegetables market"            # 후보 목록(번호·라이선스·작가·설명)
  python3 automation/fetch_photo.py "fresh vegetables market" --pick 3 --date 2026-09-28
      → assets/photos/2026-09-28.jpg 저장 + content JSON 에 넣을 cards.cover 조각 출력

고른 사진은 반드시 Read 도구로 눈으로 보고 쓴다(인물 얼굴·브랜드 로고·특정 매장 오인·사건 현장 사진 금지).
"""
import argparse
import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = "https://commons.wikimedia.org/w/api.php"
UA = "EDIT-H-newsletter/1.0 (https://vetnam555-del.github.io/edit-h-archive/)"
OK_LICENSE = re.compile(r"^(cc0|pd|public domain|cc-by-\d|cc by \d)", re.I)
SA_LICENSE = re.compile(r"^(cc-by-sa-\d|cc by-sa \d)", re.I)
CARD_W, CARD_H, MAX_UPSCALE = 1080, 1350, 1.1  # content.py 의 표지 사진 검사와 같은 기준
THUMB_WIDTHS = (1280, 1920)  # 위키미디어 표준 썸네일 폭


def fetch_width(w, h):
    """표지를 채우는 데 충분한 가장 작은 표준 썸네일 폭. 없으면 None.
    원본 파일은 위키미디어가 봇 요청을 제한(429)하므로 원본보다 작은 표준 썸네일만 쓴다."""
    for tw in [x for x in THUMB_WIDTHS if x < w]:
        if max(CARD_W / tw, CARD_H / (h * tw / w)) <= MAX_UPSCALE:
            return tw
    return None


def _get(url, tries=4):
    """클라우드 공용 IP 는 위키미디어가 요청 수를 제한한다(429 + Retry-After). 알려준 시간만큼 기다렸다가 다시 시도한다."""
    for attempt in range(tries):
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code not in (429, 503) or attempt == tries - 1:
                raise
            wait = min(int(e.headers.get("Retry-After") or 0) or 10 * (attempt + 1), 60)
            print(f"… 위키미디어 요청 제한({e.code}) — {wait}초 뒤 다시 시도합니다", file=sys.stderr)
            time.sleep(wait)


def _text(v):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", v or ""))).strip()


def search(query, limit=15, allow_sa=False):
    params = {
        "action": "query", "format": "json", "generator": "search", "gsrnamespace": 6,
        "gsrsearch": f"{query} filetype:bitmap", "gsrlimit": limit,
        "prop": "imageinfo", "iiprop": "url|extmetadata|size|mime", "iiurlwidth": 1280,
    }
    data = json.loads(_get(f"{API}?{urllib.parse.urlencode(params)}"))
    out, skipped = [], {"라이선스": 0, "해상도": 0}
    for page in sorted((data.get("query") or {}).get("pages", {}).values(), key=lambda p: p.get("index", 0)):
        info = (page.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata") or {}
        lic = _text((meta.get("LicenseShortName") or {}).get("value")) or _text((meta.get("License") or {}).get("value"))
        if not (OK_LICENSE.match(lic) or (allow_sa and SA_LICENSE.match(lic))) or info.get("mime") not in ("image/jpeg", "image/png"):
            skipped["라이선스"] += 1
            continue  # NC·ND·공정 이용 등 재사용 조건이 맞지 않는 사진은 뺀다
        tw = fetch_width(info.get("width") or 1, info.get("height") or 1)
        if not tw:
            skipped["해상도"] += 1
            continue  # 표지를 채우려면 늘려야 해서 흐려지는 사진
        out.append({
            "title": page["title"], "license": lic,
            "artist": _text((meta.get("Artist") or {}).get("value"))[:80] or "작가 미상",
            "description": _text((meta.get("ImageDescription") or {}).get("value"))[:160],
            "thumb": info.get("thumburl") or info.get("url"), "page": info.get("descriptionurl"),
            "size": f"{info.get('width')}×{info.get('height')}", "fetch_width": tw,
            "original": info.get("url"), "original_width": info.get("width"),
        })
    search.skipped = skipped
    return out


def download_url(c):
    """고른 표준 폭의 썸네일 주소(thumb.wikimedia.org)."""
    params = {"action": "query", "format": "json", "titles": c["title"], "prop": "imageinfo",
              "iiprop": "url", "iiurlwidth": c["fetch_width"]}
    data = json.loads(_get(f"{API}?{urllib.parse.urlencode(params)}"))
    page = next(iter(data["query"]["pages"].values()))
    return page["imageinfo"][0].get("thumburl") or page["imageinfo"][0]["url"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query", help="영어 검색어가 결과가 많다 (예: 'shopping mall crowd', 'delivery scooter')")
    ap.add_argument("--pick", type=int, help="내려받을 후보 번호")
    ap.add_argument("--date", help="YYYY-MM-DD — 저장 파일명")
    ap.add_argument("--allow-sa", action="store_true", help="CC BY-SA 사진도 후보에 넣는다(표지도 같은 라이선스가 될 수 있음)")
    args = ap.parse_args()
    try:
        cands = search(args.query, allow_sa=args.allow_sa)
    except OSError as e:
        print(f"✗ 위키미디어 커먼즈에 접속하지 못했습니다({type(e).__name__}) — 네트워크 허용 목록에 "
              "*.wikimedia.org(commons·upload·thumb)가 있는지 확인하세요. 오늘은 사진 없이 발행합니다.")
        sys.exit(2)
    if not cands:
        why = ", ".join(f"{k} {v}장" for k, v in getattr(search, "skipped", {}).items() if v) or "검색 결과 없음"
        print(f"✗ 재사용 가능한 후보가 없습니다({why} 제외) — 더 일반적인 영어 검색어로 바꾸거나 사진 없이 발행하세요.")
        sys.exit(1)
    if args.pick is None:
        for i, c in enumerate(cands, 1):
            print(f"[{i}] {c['title']} · {c['license']} · {c['artist']} · {c['size']}\n     {c['description']}\n     {c['page']}")
        return
    if not args.date:
        sys.exit("--pick 에는 --date 가 필요합니다")
    c = cands[args.pick - 1]
    try:
        url = download_url(c)
        data = _get(url)
    except OSError as e:
        # 위키미디어는 봇의 원본 요청을 막고 표준 크기 썸네일(thumb.wikimedia.org)만 허용한다
        print(f"✗ 사진을 내려받지 못했습니다({e}) — 네트워크 허용 목록에 thumb.wikimedia.org 가 있는지 확인하세요. "
              "오늘은 사진 없이 발행합니다.")
        sys.exit(2)
    ext = ".png" if urllib.parse.urlsplit(url).path.lower().endswith(".png") else ".jpg"
    dest = ROOT / "assets" / "photos" / f"{args.date}{ext}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    credit = f"사진 = {c['artist']} / Wikimedia Commons ({c['license']})"
    print(f"✓ {dest.relative_to(ROOT)} 저장 ({dest.stat().st_size // 1024}KB) — Read 도구로 사진을 직접 보고 쓸지 결정하세요")
    print(json.dumps({"photo": str(dest.relative_to(ROOT)), "credit": credit, "photo_source": c["page"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
