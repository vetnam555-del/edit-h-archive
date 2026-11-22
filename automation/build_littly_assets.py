#!/usr/bin/env python3
"""리틀리(litt.ly) 프로필 페이지용 그림 — 위 배너 1장 + 링크 버튼 썸네일 4장(2026-11-22 운영자 '프로필은 리틀리로 꾸며 줘').

리틀리 편집은 운영자 로그인이 필요해 Claude 가 직접 못 한다 — 그림과 문구·링크(assets/littly/README.md)를 만들어 두고
운영자가 리틀리 앱에서 올린다. 그림은 3D H(assets/mascot/3d)로 — 크게 보이는 자리라 표지와 같은 판(E28).

  python3 automation/build_littly_assets.py     # assets/littly/*.png
"""
import base64
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from edith.common import ROOT, load_config  # noqa: E402
from edith.fonts import font_css  # noqa: E402

OUT = ROOT / "assets" / "littly"
SHOT = ROOT / "automation" / "screenshot.cjs"
H3D = ROOT / "assets" / "mascot" / "3d"
ORANGE, INK, CREAM, PEACH = "#FF5233", "#282F38", "#F5F1E8", "#FFC9AD"


def uri(pose):
    return "data:image/png;base64," + base64.b64encode((H3D / f"h-{pose}.png").read_bytes()).decode()


def page(body, w, h):
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>{font_css()}
html,body{{margin:0;width:{w}px;height:{h}px;overflow:hidden}}
body{{font-family:'Pretendard',sans-serif;color:{INK};position:relative;word-break:keep-all}}
.hl{{background:{PEACH};padding:0 10px}}
</style></head><body>{body}</body></html>"""


def banner(when):
    return page(f"""
<div style="position:absolute;inset:0;background:{CREAM};"></div>
<div style="position:absolute;left:64px;top:70px;width:640px;">
  <div style="font-size:30px;font-weight:800;color:{ORANGE};letter-spacing:1px;">EDIT H · 무료 뉴스레터</div>
  <div style="margin-top:22px;font-size:76px;font-weight:900;line-height:1.18;letter-spacing:-2.5px;">바쁜 아침,<br><span class="hl">꼭 알아야 할 것만</span></div>
  <div style="margin-top:26px;font-size:32px;font-weight:600;color:#555558;line-height:1.5;">매일 아침 {when} · 경제부터 트렌드까지<br>숫자는 두 번 확인해서 5분 분량으로</div>
</div>
<img src="{uri('redpen')}" style="position:absolute;right:30px;bottom:6px;width:470px;height:470px;">
""", 1200, 600)


def thumb(pose, bg):
    return page(f"""
<div style="position:absolute;inset:0;background:{bg};border-radius:0;"></div>
<img src="{uri(pose)}" style="position:absolute;left:10px;top:18px;width:380px;height:380px;">
""", 400, 400)


def shot(html, out, w, h):
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "p.html"
        p.write_text(html, encoding="utf-8")
        subprocess.run(["node", str(SHOT), str(p), str(out), str(w), str(h)], check=True, capture_output=True, text=True)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    when = load_config()["send_time_kst"].lstrip("0").replace(":00", "시")
    shot(banner(when), OUT / "banner.png", 1200, 600)
    for name, pose, bg in [("subscribe", "celebrate", PEACH), ("today", "point", CREAM),
                           ("archive", "thinking", CREAM), ("share", "wink", CREAM)]:
        shot(thumb(pose, bg), OUT / f"btn-{name}.png", 400, 400)
    print("✓", ", ".join(sorted(p.name for p in OUT.glob("*.png"))))


if __name__ == "__main__":
    main()
