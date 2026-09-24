#!/usr/bin/env python3
"""릴스 배경음악 준비 — assets/music/tracks.json 의 곡 중 아직 없는 것을 내려받아 75초 클립(m4a)으로 만든다.

재배포가 허용된 곡(CC0·CC BY)만 넣는다. 공개 저장소에 파일을 두기 때문에 '단독 재배포 금지' 조건이 붙은
스톡 음원(유료 구독·Pixabay 등)은 넣지 않는다. CC BY 곡은 릴스 캡션에 출처가 자동으로 붙고, 전체 표기는 CREDITS.md.
위키미디어는 클라우드 공용 IP 의 원본 파일 요청을 막을 때가 있어(429) GitHub Actions(fetch-music.yml)에서 돌린다.

  python3 automation/fetch_music.py            # 없는 곡만 받기 + CREDITS.md 갱신
"""
import json
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MUSIC = ROOT / "assets" / "music"
UA = "EDIT-H-newsletter/1.0 (https://vetnam555-del.github.io/edit-h-archive/) python-urllib"
CLIP_SECONDS = 75


def download(url, dest, tries=5):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
                shutil.copyfileobj(r, f)
            return
        except urllib.error.HTTPError as e:
            if e.code not in (429, 503) or i == tries - 1:
                raise
            wait = min(int(e.headers.get("Retry-After") or 30), 300)
            print(f"  … {e.code} — {wait}초 뒤 다시", flush=True)
            time.sleep(wait)


def main():
    ffmpeg = shutil.which("ffmpeg") or sys.exit("ffmpeg 가 필요합니다")
    tracks = json.loads((MUSIC / "tracks.json").read_text(encoding="utf-8"))
    for t in tracks:
        out = MUSIC / t["file"]
        if out.exists():
            continue
        print(f"↓ {t['title']} — {t['artist']} ({t['license']})", flush=True)
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / ("src." + t["url"].rsplit(".", 1)[-1])
            download(t["url"], src)
            # 앞쪽 무음을 걷어내고 75초만 남긴다(릴스는 30~40초) — 음량 맞춤은 make_reel.py 에서
            subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", str(src),
                            "-af", "silenceremove=start_periods=1:start_threshold=-45dB",
                            "-t", str(CLIP_SECONDS), "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2", str(out)],
                           check=True)
        print(f"  ✓ {out.name} ({out.stat().st_size // 1024}KB)", flush=True)
        time.sleep(5)
    lines = ["# 릴스 배경음악 출처", "",
             "EDIT H 인스타그램 릴스에 쓰는 곡입니다. 모두 재배포·변경이 허용된 라이선스이며, 앞부분 75초로 잘라(편집) 씁니다.", ""]
    for t in tracks:
        lines.append(f"- **{t['title']}** — {t['artist']} · {t['license']} · [{t['source_name']}]({t['page']}) · 75초 클립으로 편집")
    lines += ["", "CC BY 4.0: https://creativecommons.org/licenses/by/4.0/deed.ko", ""]
    (MUSIC / "CREDITS.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
