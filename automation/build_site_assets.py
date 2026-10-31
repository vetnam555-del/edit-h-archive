#!/usr/bin/env python3
"""사이트 그림 만들기 — 공유 미리보기(og_image.png)·파비콘·홈 화면 아이콘·머리 아바타.

2026-11-01 운영자 "아카이브 사이트 싹 다 업데이트 … 프로필 이미지도 최신본으로". 그날 확인해 보니 og_image.png(카톡·인스타에
링크를 붙이면 뜨는 미리보기)의 한글이 전부 □ 로 깨져 있었고 문구도 옛것('마케팅 브리프'·'아침 8시'·'12가지')이었다 —
한글 글꼴 없이 그렸기 때문이다. 이제 카드와 같은 Pretendard(edith/fonts.py, npm 에서 받음)로 그리고, 그림은 마스코트
(assets/mascot/README.md — 캐릭터, 사람인 척하지 않는다)를 쓴다.

매일 빌드와 상관없다 — 문구·마스코트를 바꿀 때만 손으로 돌리고 결과 그림을 커밋한다.
  python3 automation/build_site_assets.py
만드는 것: og_image.png(1200×630) · favicon.png(64, 동그라미) · apple-touch-icon.png(180) · assets/mascot/avatar-96.png(96, 동그라미)
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from edith.common import ROOT  # noqa: E402
from edith.fonts import font_css  # noqa: E402

MASCOT = ROOT / "assets" / "mascot"
SHOT = ROOT / "automation" / "screenshot.cjs"

OG_HTML = """<!doctype html><html lang="ko"><head><meta charset="utf-8"><style>
{fonts}
html,body{{margin:0;width:1200px;height:630px}}
body{{font-family:'Pretendard',sans-serif;background:#0D0C0A;color:#F5F1E8;position:relative;overflow:hidden}}
.bar{{position:absolute;left:0;top:0;width:1200px;height:10px;background:#FF5233}}
.wrap{{position:absolute;left:80px;top:84px;width:660px}}
.eyebrow{{font-size:24px;font-weight:700;letter-spacing:3px;color:#FF5233}}
h1{{font-size:74px;line-height:1.17;font-weight:850;letter-spacing:-2.5px;margin:24px 0 0}}
.sub{{font-size:28px;line-height:1.5;color:#BDB6AA;margin-top:26px;font-weight:500;letter-spacing:-.4px}}
.foot{{position:absolute;left:80px;bottom:58px;display:flex;align-items:baseline;gap:22px}}
.logo{{font-size:46px;font-weight:900;letter-spacing:-1.5px}}
.logo .h{{color:#FF5233}}
.meta{{font-size:22px;color:#8E887D;font-weight:600}}
.glow{{position:absolute;right:-10px;bottom:-30px;width:540px;height:540px;border-radius:50%;
  background:radial-gradient(circle,rgba(255,82,51,.20),rgba(255,82,51,0) 68%)}}
.mascot{{position:absolute;right:60px;bottom:52px;width:390px;height:390px}}
</style></head><body>
<div class="bar"></div>
<div class="wrap">
  <div class="eyebrow">매일 아침 8:30 · 무료 뉴스레터</div>
  <h1>내 돈·일·소비에<br>바로 쓰는 뉴스</h1>
  <div class="sub">2030 직장인 데일리 브리프<br>확인된 숫자로, 5분 안에</div>
</div>
<div class="foot"><div class="logo">EDIT<span class="h"> H</span></div><div class="meta">주말 포함 매일 · 광고 없음</div></div>
<div class="glow"></div>
<img class="mascot" src="{hello}" alt="">
</body></html>"""

ICON_HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
html,body{{margin:0;background:transparent}}
img{{display:block;width:{size}px;height:{size}px;{round}}}
</style></head><body><img src="{face}" alt=""></body></html>"""


def shot(html, out, w, h, transparent=False):
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "page.html"
        page.write_text(html, encoding="utf-8")
        cmd = ["node", str(SHOT), str(page), str(out), str(w), str(h)] + (["--transparent"] if transparent else [])
        res = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return json.loads(res.stdout.strip().splitlines()[-1])


def main():
    face = (MASCOT / "profile.png").as_uri()
    og = shot(OG_HTML.format(fonts=font_css(), hello=(MASCOT / "h-hello.png").as_uri()), ROOT / "og_image.png", 1200, 630)
    if "Pretendard" not in og["fonts"]:
        raise SystemExit(f"공유 미리보기를 Pretendard 없이 그렸다(한글이 깨진다): {og['fonts']}")
    print(f"  ✓ og_image.png 1200×630 (글꼴 {', '.join(og['fonts'])})")
    for name, size, rounded, transparent in (("favicon.png", 64, True, True),
                                              ("apple-touch-icon.png", 180, False, False),
                                              ("assets/mascot/avatar-96.png", 96, True, True)):
        shot(ICON_HTML.format(size=size, round="border-radius:50%" if rounded else "", face=face), ROOT / name, size, size, transparent)
        print(f"  ✓ {name} {size}×{size}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
