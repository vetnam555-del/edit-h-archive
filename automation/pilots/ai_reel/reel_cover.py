"""릴스 표지(썸네일) — 2026-11-21 운영자 "썸네일도 엄청 중요하다, 1~3초가 가장 중요한 거 몰라?".

그전에는 표지를 따로 만들지 않고 영상 0.8초 프레임(thumb_offset 800)을 썼다 — 첫 장면 그대로라 프로필 격자·릴스 탭·탐색 탭에서
'무슨 이야기인지'가 안 보였다. 이 스크립트는 영상에서 H 가 크게 잡힌 한 프레임을 골라 그 위에 큰 훅 글자 두 줄을 얹은 1080×1920 JPEG 를 만든다.
post_instagram.py 가 instagram/{날짜}/reel_cover.jpg 를 보면 그걸 표지(cover_url)로 올린다.

  python3 automation/pilots/ai_reel/reel_cover.py <brief.json> <영상(자막 없는 원본도 되고 완성본도 된다)>

brief.json 의 "cover": {"at": 초(H 가 크게·표정이 센 프레임), "line1": "첫 줄", "hl": "강조(숫자·핵심어)", "line2": "둘째 줄(선택)"}.
글자는 프로필 격자(3:4 — 세로 240~1680px)와 릴스 탭(9:16) 모두에서 보이게 위아래 240px 안쪽 가운데 띠에만 둔다.
"""
import argparse
import html
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "automation"))
from edith.fonts import font_css  # noqa: E402

SHOT = ROOT / "automation" / "screenshot.cjs"
SAFE_TOP, SAFE_BOTTOM = 240, 1680      # 프로필 격자(3:4)로 잘려도 보이는 세로 범위
LINE_MAX = 11                          # 한 줄 글자 수(띄어쓰기 포함) — 썸네일은 작은 화면에서 한눈에

PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
{fonts}
html,body{{margin:0;width:1080px;height:1920px;font-family:'Pretendard',sans-serif;word-break:keep-all;overflow:hidden}}
.bg{{position:absolute;inset:0;background:url('{bg}') center/cover no-repeat}}
.shade{{position:absolute;left:0;right:0;top:0;height:{shade_h}px;background:linear-gradient(180deg,rgba(0,0,0,.30) 0%,rgba(0,0,0,.62) 25%,rgba(0,0,0,.40) 70%,rgba(0,0,0,0) 100%)}}
.mark{{position:absolute;left:0;right:0;top:{mark_top}px;text-align:center;font-weight:850;font-size:44px;letter-spacing:-1px;color:#fff;text-shadow:0 2px 14px rgba(0,0,0,.6)}}
.mark .dot{{color:#FF5233}}
.cap{{position:absolute;left:40px;right:40px;top:{cap_top}px;height:420px;overflow:hidden;text-align:center}}
.l{{display:block;font-weight:900;font-size:128px;line-height:1.12;letter-spacing:-4px;color:#fff;
   text-shadow:0 6px 24px rgba(0,0,0,.8),0 0 4px rgba(0,0,0,.95)}}
.hl{{background:#FF5233;color:#111;padding:0 18px;border-radius:18px;text-shadow:none}}
</style></head><body>
<div class="bg"></div><div class="shade"></div>
<div class="mark">EDIT H<span class="dot">.</span></div>
<div class="cap fit">{lines}</div>
</body></html>"""


def cover_gaps(cover):
    """brief.json "cover" 검사 → 실패 목록(빈 목록이면 통과)."""
    fails = []
    if not isinstance(cover, dict):
        return ["brief.json 에 \"cover\" 가 없다 — {\"at\": 초, \"line1\": …, \"hl\": …}"]
    if not isinstance(cover.get("at"), (int, float)) or cover["at"] < 0:
        fails.append("cover.at(표지로 쓸 프레임 초)이 없다")
    if not str(cover.get("line1", "")).strip():
        fails.append("cover.line1(첫 줄)이 없다")
    if not str(cover.get("hl", "")).strip():
        fails.append("cover.hl(강조 — 숫자·핵심어)이 없다")
    first = f"{cover.get('line1', '')}".strip()
    second = f"{cover.get('hl', '')} {cover.get('line2', '')}".strip()
    for name, text in (("첫 줄", first), ("둘째 줄(hl + line2)", second)):
        if len(text) > LINE_MAX:
            fails.append(f"표지 {name} '{text}' 가 {len(text)}자 — {LINE_MAX}자 안으로(작은 화면에서 한눈에)")
    return fails


def cover_html(cover, bg_uri):
    first = html.escape(str(cover["line1"]).strip())
    second = f'<span class="hl">{html.escape(str(cover["hl"]).strip())}</span>'
    if str(cover.get("line2", "")).strip():
        second += " " + html.escape(str(cover["line2"]).strip())
    return PAGE.format(fonts=font_css(), bg=bg_uri, shade_h=SAFE_TOP + 820, mark_top=SAFE_TOP + 30, cap_top=SAFE_TOP + 120,
                       lines=f'<span class="l">{first}</span><span class="l">{second}</span>')


def make(brief_path, video, out=None):
    ep = json.loads(Path(brief_path).read_text(encoding="utf-8"))
    cover = ep.get("cover")
    fails = cover_gaps(cover)
    if fails:
        raise SystemExit("✗ 표지를 만들지 않는다\n  - " + "\n  - ".join(fails))
    out = Path(out) if out else ROOT / "instagram" / ep["date"] / "reel_cover.jpg"
    with tempfile.TemporaryDirectory() as tmp:
        frame = Path(tmp) / "f.png"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{float(cover['at']):.2f}", "-i", str(video), "-frames:v", "1",
                        "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920", str(frame)], check=True)
        page = Path(tmp) / "p.html"
        page.write_text(cover_html(cover, frame.as_uri()), encoding="utf-8")
        out.parent.mkdir(parents=True, exist_ok=True)
        r = subprocess.run(["node", str(SHOT), str(page), str(out), "1080", "1920"], check=True, capture_output=True, text=True)
    info = json.loads(r.stdout.strip().splitlines()[-1])
    if "Pretendard" not in info["fonts"]:
        raise SystemExit(f"Pretendard 없이 그렸다(한글이 깨진다): {info['fonts']}")
    if info.get("overflow"):
        raise SystemExit("표지 글자가 칸을 넘쳤다 — line1·hl·line2 를 줄인다")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("brief")
    ap.add_argument("video")
    ap.add_argument("--out")
    a = ap.parse_args()
    print(f"ok {make(a.brief, a.video, a.out)}")


if __name__ == "__main__":
    main()
