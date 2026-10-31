#!/usr/bin/env python3
"""표지 후보 사진 받기 — assets/photos/incoming.json 의 주소를 GitHub 서버에서 받아 assets/photos/{name}.jpg 로 바꿔 넣는다.

2026-11-01 운영자 '힉스필드 연동했는데 활용해서 개선할 부분 개선해 줘': 10/31 회고 — 대체 사진 20장 중 30일 재사용 금지에 안 걸린 게
2장뿐이라 표지가 다시 핵심어(글자) 표지로 나갔다. 힉스필드로 만든 '사람·글자·상표 없는 일상 정물' 사진을 대체 후보로 더한다.
Claude 작업 환경은 이미지 서버(클라우드프런트) 접속이 막혀 있어, 음악 받기(fetch-music.yml)처럼 GitHub 서버에서 받는다.

받기만 한다 — 표지 후보가 되는 건 개선 루틴이 눈으로 검수해 assets/photos/library.json 에 올린 뒤다(검수 전 사진은 쓰이지 않는다).
허용한 주소(ALLOWED_HOSTS)·이미지 형식·크기만 받고, 이미 받은 이름은 건너뛴다. 가로 1280px JPEG 로 줄인다(대체 사진들과 같은 크기).
마스코트(2026-11-01 운영자 '마스코트 캐릭터 만들어 줘')는 "dir": "assets/mascot", "format": "png" 로 — 투명 배경을 살린 PNG(가로 1024 이하).

  python3 automation/fetch_incoming_photos.py            # 받기
  python3 automation/fetch_incoming_photos.py --dry-run  # 받을 목록만
"""
import argparse
import io
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "assets" / "photos" / "incoming.json"
PHOTOS = ROOT / "assets" / "photos"
ALLOWED_HOSTS = {"d8j0ntlcm91z4.cloudfront.net"}   # 힉스필드 생성 이미지 저장소
MAX_BYTES = 25 * 1024 * 1024
WIDTH = 1280
UA = "EDIT-H-photo-fetch/1.0 (+https://github.com/vetnam555-del/edit-h-archive)"


DIRS = {"assets/photos", "assets/mascot"}     # 받아 넣을 수 있는 폴더
FORMATS = {"jpg", "png"}                      # png = 투명 배경 유지(마스코트)


def target(it):
    """항목이 들어갈 파일 경로. 폴더·형식이 규칙에 맞지 않으면 ValueError."""
    folder, fmt = str(it.get("dir") or "assets/photos"), str(it.get("format") or "jpg")
    if folder not in DIRS or fmt not in FORMATS:
        raise ValueError(f"허용하지 않은 폴더·형식: {folder} · {fmt}")
    return ROOT / folder / f"{it['name']}.{fmt}"


def todo(manifest=None):
    """[(name, url, 받을 경로)] — 아직 받지 않은 항목. 주소·이름·폴더가 규칙에 맞지 않으면 ValueError."""
    data = json.loads((manifest or MANIFEST).read_text(encoding="utf-8"))
    out = []
    for it in data.get("items") or []:
        name, url = str(it.get("name") or ""), str(it.get("url") or "")
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
            raise ValueError(f"이름은 영문 소문자·숫자·- 만: {name!r}")
        u = urllib.parse.urlsplit(url)
        if u.scheme != "https" or u.hostname not in ALLOWED_HOSTS:
            raise ValueError(f"허용하지 않은 주소: {url}")
        path = target(it)
        if not path.exists():
            out.append((name, url, path))
    return out


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError(f"{MAX_BYTES // 1024 // 1024}MB 를 넘는다")
    return data


def convert(data, out_path):
    """.jpg 는 가로 WIDTH JPEG, .png 는 투명 배경을 살려 가로 1024 이하 PNG 로."""
    from PIL import Image   # GitHub 서버에서만 설치한다(워크플로)
    im = Image.open(io.BytesIO(data))
    if im.format not in ("PNG", "JPEG", "WEBP"):
        raise ValueError(f"이미지 형식이 아니다: {im.format}")
    png = out_path.suffix == ".png"
    im = im.convert("RGBA" if png else "RGB")
    limit = 1024 if png else WIDTH
    if im.width > limit:
        im = im.resize((limit, round(im.height * limit / im.width)), Image.LANCZOS)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if png:
        im.save(out_path, "PNG", optimize=True)
    else:
        im.save(out_path, "JPEG", quality=86, optimize=True, progressive=True)
    return im.size


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    items = todo()
    if not items:
        print("받을 사진 없음(모두 받았다)")
        return 0
    failed = 0
    for name, url, path in items:
        if args.dry_run:
            print(f"  받을 것: {path.relative_to(ROOT)} ← {urllib.parse.urlsplit(url).hostname}")
            continue
        try:
            size = convert(fetch(url), path)
            print(f"  ✓ {path.relative_to(ROOT)} {size[0]}×{size[1]}")
        except Exception as e:  # noqa: BLE001 — 한 장이 실패해도 나머지는 받는다
            failed += 1
            print(f"  ✗ {name}: {type(e).__name__}: {str(e)[:120]}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
