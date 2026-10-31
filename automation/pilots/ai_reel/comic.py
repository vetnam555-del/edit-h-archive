#!/usr/bin/env python3
"""'H 극장' 4컷 만화 캐러셀 — 그날 AI 릴스 장면 4컷 + 말풍선(확인된 숫자) + 끝 장, 1080×1350 JPEG.

2026-11-01 운영자 "캐러셀도 조금 더 재미있는 양식으로" → 시안 승인("좋네 오늘부터"). 08:30 기존 캐러셀(실험 E11·E12 중)은 그대로 두고,
AI 릴스와 함께 따로 올리는 두 번째 캐러셀이다(post_instagram.py 가 instagram/{날짜}/comic/*.jpg 를 올린다, AI 정보 라벨).
같은 AI 영상에서 장면을 뽑으므로 크레딧이 더 들지 않는다.

사용: python3 automation/pilots/ai_reel/comic.py <episode.json> <힉스필드 영상.mp4>
     → instagram/{날짜}/comic/c1.jpg … + comic_alt.json(대체 텍스트)
episode.json 의 "comic": {series, title, panels:[{t, pos, who, bubble, box}], sources, end:{title, sub}}
  t = 원래 AI 영상에서 뽑을 시각(초), pos = 그림 자르는 기준점(CSS object-position), bubble·box 의 숫자는 content 에서만.
"""
import argparse
import html as htmlmod
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "automation"))
from edith.fonts import font_css  # noqa: E402

SHOT = ROOT / "automation" / "screenshot.cjs"
FACE = (ROOT / "assets" / "mascot" / "profile.png").as_uri()
W, H = 1080, 1350

CSS = """{fonts}
html,body{{margin:0;width:1080px;height:1350px;background:#F5F1E8;font-family:'Pretendard',sans-serif;word-break:keep-all;color:#111}}
.top{{position:absolute;left:60px;right:60px;top:44px;display:flex;align-items:center;justify-content:space-between}}
.series{{display:flex;align-items:center;gap:14px;font-weight:800;font-size:30px}}
.pill{{background:#FF5233;color:#fff;font-weight:850;font-size:28px;padding:8px 18px;border-radius:999px}}
.logo{{font-weight:900;font-size:34px;letter-spacing:-1px}} .logo b{{color:#FF5233}}
.panel{{position:absolute;left:60px;right:60px;top:{ptop}px;height:{ph}px;border:7px solid #111;border-radius:30px;overflow:hidden;background:#ddd}}
.panel img{{width:100%;height:100%;object-fit:cover;object-position:{pos}}}
.num{{position:absolute;left:22px;top:18px;background:#111;color:#fff;font-weight:900;font-size:30px;width:56px;height:56px;border-radius:50%;
  display:flex;align-items:center;justify-content:center}}
.stack{{position:absolute;left:60px;right:60px;top:{bt}px}}
.bubble{{position:relative;margin:0 {mr}px 0 {ml}px;background:#fff;border:6px solid #111;border-radius:40px;padding:26px 34px;
  font-weight:850;font-size:{bs}px;line-height:1.28;letter-spacing:-1.5px;box-shadow:0 10px 0 rgba(0,0,0,.12)}}
.bubble:after{{content:'';position:absolute;{tail}top:-29px;width:46px;height:46px;background:#fff;border-right:6px solid #111;border-bottom:6px solid #111;transform:rotate(225deg)}}
.who{{display:block;font-size:26px;font-weight:800;color:#FF5233;letter-spacing:0;margin-bottom:6px}}
.hl{{background:#FF5233;color:#111;padding:0 10px;border-radius:10px}}
.box{{margin-top:34px;font-size:31px;line-height:1.5;font-weight:600;color:#3d3a35}}
.box b{{color:#111}}
.tag{{display:inline-block;background:#111;color:#fff;font-weight:800;font-size:28px;padding:6px 16px;border-radius:10px;margin-bottom:12px}}
.src{{position:absolute;left:60px;right:60px;bottom:34px;font-size:24px;color:#8A857C;font-weight:500}}
.title{{position:absolute;left:60px;right:60px;top:120px;font-weight:900;font-size:66px;line-height:1.18;letter-spacing:-2.5px}}
.swipe{{position:absolute;right:60px;bottom:60px;font-weight:800;font-size:32px}}
"""


def page(fonts, body, **kw):
    d = dict(ptop=120, ph=740, pos="50% 45%", bt=780, ml=30, mr=30, bs=50, tail="left:140px;")
    d.update(kw)
    return f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS.format(fonts=fonts, **d)}</style></head><body>{body}</body></html>"


def shot(html, out):
    with tempfile.TemporaryDirectory() as t:
        p = Path(t) / "p.html"
        p.write_text(html, encoding="utf-8")
        png = Path(t) / "p.png"
        r = subprocess.run(["node", str(SHOT), str(p), str(png), str(W), str(H)], check=True, capture_output=True, text=True)
        if "Pretendard" not in json.loads(r.stdout.strip().splitlines()[-1])["fonts"]:
            raise SystemExit("Pretendard 없이 그렸다(한글이 깨진다)")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(png), "-q:v", "2", str(out)], check=True)  # 인스타 API 는 JPEG 만


def plain(s):
    return re.sub(r"\s+", " ", htmlmod.unescape(re.sub(r"<br\s*/?>", " ", re.sub(r"<(?!br)[^>]+>", "", s)))).strip()


def build(ep, video, outdir):
    c = ep["comic"]
    fonts = font_css()
    n = len(c["panels"]) + 1
    outdir.mkdir(parents=True, exist_ok=True)
    for old in outdir.glob("c*.jpg"):
        old.unlink()
    top = lambda i: (f"<div class='top'><div class='series'><span class='pill'>H 극장</span>{c['series']} · {i}/{n}</div>"  # noqa: E731
                     "<div class='logo'>EDIT H<b>.</b></div></div>")
    src = f"<div class='src'>출처 · {c['sources']}</div>"
    alts = {}
    with tempfile.TemporaryDirectory() as tmp:
        for i, p in enumerate(c["panels"], 1):
            frame = Path(tmp) / f"f{i}.jpg"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(p["t"]), "-i", str(video), "-frames:v", "1", "-q:v", "2", str(frame)], check=True)
            bubble = f"<div class='bubble'><span class='who'>{p.get('who', 'H')}</span>{p['bubble']}</div>"
            box = f"<div class='box'>{p['box']}</div>" if p.get("box") else ""
            if i == 1:   # 표지: 제목 + 큰 컷 + 넘기기 안내
                body = (top(i) + f"<div class='title'>{c['title']}</div>"
                        f"<div class='panel'><img src='{frame.as_uri()}'><div class='num'>1</div></div>"
                        f"<div class='stack'>{bubble}{box}</div><div class='swipe'>넘겨서 {len(c['panels'])}컷으로 보기 →</div>")
                html = page(fonts, body, ptop=310, ph=760, pos=p.get("pos", "50% 40%"), bt=990, ml=60, mr=140, tail="left:150px;")
            else:
                body = (top(i) + f"<div class='panel'><img src='{frame.as_uri()}'><div class='num'>{i}</div></div>"
                        f"<div class='stack'>{bubble}{box}</div>{src}")
                html = page(fonts, body, ph=p.get("ph", 740), bt=p.get("ph", 740) + 60, pos=p.get("pos", "50% 45%"),
                            tail=p.get("tail", "left:170px;"))
            shot(html, outdir / f"c{i}.jpg")
            alts[f"c{i}.jpg"] = f"H 극장 {i}컷 — {plain(p.get('who', 'H'))}: {plain(p['bubble'])}" + (f" {plain(p['box'])}" if p.get("box") else "")
    e = c.get("end") or {}
    body = (top(n) + "<div style='position:absolute;left:90px;right:90px;top:250px;text-align:center'>"
            f"<img src='{FACE}' style='width:220px;height:220px;border-radius:50%'>"
            f"<div style='margin-top:30px;font-weight:900;font-size:64px;letter-spacing:-2px'>{e.get('title', 'H 극장은 매일 아침')}</div>"
            f"<div style='margin-top:14px;font-weight:600;font-size:36px;color:#57534C;line-height:1.5'>"
            f"{e.get('sub', '경제부터 트렌드까지, 오늘 소식 하나를<br>4컷으로 풀어 드려요')}</div>"
            "<div style='display:inline-block;margin-top:50px;background:#111;color:#fff;font-weight:800;font-size:42px;padding:28px 60px;border-radius:999px'>"
            "팔로우하고 내일 아침에 받기</div>"
            "<div style='margin-top:30px;font-weight:600;font-size:30px;color:#3d3a35'>숫자·출처 전문은 프로필 링크 뉴스레터에서</div></div>")
    shot(page(fonts, body), outdir / f"c{n}.jpg")
    alts[f"c{n}.jpg"] = "H 극장 끝 장 — 매일 아침 8시 30분 EDIT H 뉴스레터, 팔로우 안내"
    (outdir.parent / "comic_alt.json").write_text(json.dumps(alts, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("episode")
    ap.add_argument("video")
    a = ap.parse_args()
    ep = json.loads(Path(a.episode).read_text(encoding="utf-8"))
    out = ROOT / "instagram" / ep["date"] / "comic"
    n = build(ep, Path(a.video), out)
    print(f"ok {out} {n}장")


if __name__ == "__main__":
    main()
