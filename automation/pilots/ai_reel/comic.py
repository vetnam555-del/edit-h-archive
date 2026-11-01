#!/usr/bin/env python3
"""'H 극장' 4컷 만화 캐러셀 — 그날 AI 릴스 장면 4컷 + 말풍선(확인된 숫자) + 끝 장, 1080×1350 JPEG.

2026-11-01 운영자 "캐러셀도 조금 더 재미있는 양식으로" → 시안 승인("좋네 오늘부터"). 08:30 기존 캐러셀(실험 E11·E12 중)은 그대로 두고,
AI 릴스와 함께 따로 올리는 두 번째 캐러셀이다(post_instagram.py 가 instagram/{날짜}/comic/*.jpg 를 올린다, AI 정보 라벨).
같은 AI 영상에서 장면을 뽑으므로 크레딧이 더 들지 않는다.

사용: python3 automation/pilots/ai_reel/comic.py <episode.json> <힉스필드 영상.mp4> [--out 폴더]
     → instagram/{날짜}/comic/c1.jpg … + instagram/{날짜}/comic_alt.json(대체 텍스트).
     --out 은 미리보기용 — 컷과 대체 텍스트를 모두 그 폴더 안에 둔다(게시 파일을 덮어쓰지 않게)
episode.json 의 "comic": {series, title, panels:[{t, pos, who, bubble, box, src?}], sources, end:{title, sub}}
  t = 원래 AI 영상에서 뽑을 시각(초), pos = 그림 자르는 기준점(CSS object-position), bubble·box 의 숫자는 content 에서만.
  src = 그 컷의 출처(5가지 웹툰처럼 컷마다 소식이 다를 때 — 없으면 sources). 2026-11-01 운영자 '캐러셀을 H 극장처럼 웹툰으로' →
  11/02~ '오늘 아침 5가지' 영상 장면 5컷으로 5가지 웹툰(brief.json 의 comic).
웹툰 3판(2026-11-01 운영자 '이게 최선이야?'): "layout": "duo" 면 영상 없이 그날 생성한 정지 그림으로 한 장에 두 컷(상황 → H 의 반응) —
  표지(cover.img + 오늘 5가지 목차) + 두 컷 장(panels[i].img_a·img_b) + 요약 + 끝 장. 그림 규칙·손잡이: webtoon_prompt.md.
  사용: python3 automation/pilots/ai_reel/comic.py <brief.json> [--out 폴더]   (그림 경로는 brief.json 폴더 기준)
"""
import argparse
import html as htmlmod
import json
import re
import shutil
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
.body2{{margin-top:22px;font-size:34px;line-height:1.48;font-weight:600;color:#3d3a35;text-wrap:balance}}
.take{{margin-top:20px;background:#FFC9AD;border:4px solid #111;border-radius:24px 24px 24px 6px;padding:18px 26px;font-weight:800;font-size:35px;line-height:1.38;letter-spacing:-.5px}}
.take .lab{{display:block;font-size:24px;font-weight:800;color:#B23A0F;margin-bottom:4px;letter-spacing:0}}
.row{{display:flex;align-items:center;gap:22px;padding:34px 0;border-bottom:3px solid #E4DED2}}
.row .n{{flex:none;width:58px;height:58px;border-radius:14px;background:#111;color:#fff;font-weight:900;font-size:30px;display:flex;align-items:center;justify-content:center}}
.row .h{{flex:1;min-width:0;font-weight:800;font-size:40px;line-height:1.3;letter-spacing:-1px}}
.row .v{{flex:none;font-weight:900;font-size:40px;background:linear-gradient(180deg,transparent 58%,#FFC9AD 58%)}}
.duo{{position:absolute;left:56px;right:56px;top:106px;bottom:80px;display:flex;flex-direction:column}}
.fr{{position:relative;flex:1 1 470px;min-height:250px;border:7px solid #111;border-radius:26px;overflow:hidden;background:#ddd}}
.fr.b{{flex-basis:400px}}
.fr img{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}}
.stk{{position:absolute;top:16px;right:16px;background:#FF5233;color:#fff;font-weight:900;font-size:44px;padding:10px 22px;border:5px solid #111;border-radius:18px;box-shadow:5px 5px 0 #111;letter-spacing:-1px;white-space:nowrap}}
.stk.l{{right:auto;left:88px}}
.narr{{position:relative;z-index:2;align-self:flex-start;max-width:740px;margin-top:-84px;background:#FFF6D8;border:5px solid #111;border-radius:6px;padding:16px 24px;font-weight:850;font-size:40px;line-height:1.25;letter-spacing:-1px;box-shadow:6px 6px 0 #111}}
.narr .k{{display:block;font-size:22px;font-weight:800;color:#B23A0F;letter-spacing:0;margin-bottom:4px}}
.body3{{margin:20px 8px 0;font-size:31px;line-height:1.45;font-weight:600;color:#3d3a35}}
.say{{position:relative;z-index:2;max-width:660px;margin:24px 30px -58px;background:#fff;border:6px solid #111;border-radius:36px;padding:18px 28px;font-weight:850;font-size:38px;line-height:1.28;letter-spacing:-1px;box-shadow:0 8px 0 rgba(0,0,0,.12)}}
.say.l{{align-self:flex-start}} .say.r{{align-self:flex-end}}
.say .who{{display:block;font-size:23px;font-weight:800;color:#FF5233;letter-spacing:0;margin-bottom:4px}}
.say:after{{content:'';position:absolute;bottom:-26px;width:40px;height:40px;background:#fff;border-right:6px solid #111;border-bottom:6px solid #111;transform:rotate(45deg)}}
.say.l:after{{right:90px}} .say.r:after{{left:90px}} .say.l.out:after{{right:auto;left:90px}} .say.r.out:after{{left:auto;right:90px}}
.cov{{position:absolute;left:56px;right:56px;top:104px;bottom:124px;display:flex;flex-direction:column}}
.ct{{font-weight:900;font-size:62px;line-height:1.18;letter-spacing:-2.5px;margin:0 4px}}
.cov .fr{{flex:1 1 560px;min-height:300px;margin-top:30px}}
.idx{{margin:30px 6px 0}}
.idx div{{display:flex;gap:16px;align-items:baseline;font-weight:800;font-size:32px;line-height:1.25;padding:9px 0;border-bottom:2px solid #E4DED2}}
.idx b{{flex:none;color:#FF5233;font-weight:900}} .idx i{{font-style:normal;margin-left:auto;font-weight:900;background:linear-gradient(180deg,transparent 58%,#FFC9AD 58%)}}
"""


def page(fonts, body, **kw):
    d = dict(ptop=120, ph=740, pos="50% 45%", bt=780, ml=30, mr=30, bs=50, tail="left:140px;")
    d.update(kw)
    return f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS.format(fonts=fonts, **d)}</style></head><body>{body}</body></html>"


def shot(html, out):
    with tempfile.TemporaryDirectory() as t:
        p = Path(t) / "p.html"
        p.write_text(html, encoding="utf-8")
        jpg = Path(t) / "p.jpg"   # 인스타 API 는 JPEG 만 — 렌더러가 바로 JPEG(품질 95)로 찍는다(ffmpeg 없는 곳에서도, 2026-11-01)
        r = subprocess.run(["node", str(SHOT), str(p), str(jpg), str(W), str(H)], check=True, capture_output=True, text=True)
        info = json.loads(r.stdout.strip().splitlines()[-1])
        if "Pretendard" not in info["fonts"]:
            raise SystemExit("Pretendard 없이 그렸다(한글이 깨진다)")
        if info.get("overflow"):   # 두 컷 장: 글이 너무 길어 두 컷을 최소 높이까지 줄여도 넘쳤다 — 반쯤 잘린 장을 올리지 않는다
            raise SystemExit(f"{Path(out).name}: 글이 칸을 넘쳤어요({', '.join(info['overflow'])}) — 카드 글을 줄이거나 그림 위치를 다시 보세요")
        shutil.copyfile(jpg, out)   # 검사를 통과한 장만 내보낸다


def plain(s):
    return re.sub(r"\s+", " ", htmlmod.unescape(re.sub(r"<br\s*/?>", " ", re.sub(r"<(?!br)[^>]+>", "", s)))).strip()


def _md(text):
    """content 카드 글(==강조==·**굵게**·줄바꿈) → 말풍선 HTML."""
    out = htmlmod.escape(str(text or ""))
    out = re.sub(r"==(.+?)==", r"<span class='hl'>\1</span>", out)
    out = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", out)
    return out.replace("\n", "<br>")


def from_cards(c, date):
    """panels[i].card = N 이면 그날 content 카드 N번의 제목·본문·'그래서'·출처를 그대로 쓴다 — 08:30 카드와 같은, 검수를 거친 글.
    2026-11-01 운영자 "웹툰으로 하면 텍스트가 기존보다 조금 부족한 것 같은데" → 컷마다 제목(말풍선)·본문·'그래서 나는?'·출처를 카드와 똑같이."""
    if not any(p.get("card") for p in c["panels"]) and not c.get("summary"):
        return []
    sys.path.insert(0, str(ROOT / "automation"))
    from edith import content
    issues = content.load(date)["card_issues"]
    for p in c["panels"]:
        if not p.get("card"):
            continue
        it = issues[int(p["card"]) - 1]
        p.setdefault("bubble", _md(it["headline"]))
        p.setdefault("body", _md(it["body"]))
        p.setdefault("take", _md(it["takeaway"]))
        p.setdefault("src", it["source"].replace("\u2060", ""))
    order = [int(p["card"]) for p in c["panels"] if p.get("card")] or list(range(1, len(issues) + 1))
    return [issues[n - 1] for n in order]


def _src(p, c):
    return htmlmod.escape(htmlmod.unescape(re.sub(r"<[^>]+>", "", str(p.get("src") or c.get("sources") or "")))).replace("\u2060", "")


def duo_cover(c, picked, img, pos):
    """두 컷 웹툰 표지 — 제목(그날 가장 센 사실) + 생성 그림 한 컷 + 오늘 다룰 5가지 목차(번호·주제·숫자).
    세로로 쌓아 제목·목차가 길면 그림이 줄어든다(넘치면 렌더가 멈춘다)."""
    rows = "".join(f"<div><b>{j}</b>{htmlmod.escape(it.get('tag') or '')}<i>{htmlmod.escape(str(it.get('number') or ''))}</i></div>"
                   for j, it in enumerate(picked, 1))
    return (f"<div class='cov fit'><div class='ct'>{c['title']}</div>"
            f"<div class='fr'><img src='{img.as_uri()}' style='object-position:{pos}'></div>"
            f"<div class='idx'>{rows}</div></div><div class='swipe'>넘겨서 {len(picked)}가지 보기 →</div>")


def duo_slide(c, i, p, img_a, img_b):
    """두 컷 한 장(2026-11-01 운영자 '이게 최선이야?' → 웹툰 3판): 위 컷 = 상황(아래 왼쪽에 걸친 내레이션 상자에 카드 제목,
    오른쪽 위 숫자 스티커), 가운데 = 카드 본문, 아래 컷 = H 의 반응(두 컷 사이 경계에 걸친 말풍선에 카드 '그래서 나는?').
    세로로 쌓고(flex) 글이 길면 두 컷이 같이 줄어든다 — 말풍선·상자가 컷 안쪽은 가장자리만 덮어 얼굴을 가리지 않게.
    그림은 그날 생성한 정지 그림(영상 캡처보다 선명). say_side = 말풍선 쪽(left·right), tail = 'out' 이면 꼬리를 바깥 끝에,
    stk_side = 숫자 스티커 자리(right 기본·left·none) — 그림을 보고 인물을 덮지 않는 쪽으로."""
    side = "r" if p.get("say_side") == "right" else "l"
    out = " out" if p.get("tail") == "out" else ""
    stk_side = p.get("stk_side") or "right"
    stk = (f"<div class='stk{' l' if stk_side == 'left' else ''}'>{htmlmod.escape(str(p.get('number') or ''))}</div>"
           if p.get("number") and stk_side != "none" else "")
    return (f"<div class='duo fit'>"
            f"<div class='fr'><img src='{img_a.as_uri()}' style='object-position:{p.get('pos_a', '50% 50%')}'><div class='num'>{i - 1}</div>{stk}</div>"
            f"<div class='narr'><span class='k'>{htmlmod.escape(p.get('tag') or '')}</span>{p['bubble'].replace('<br>', ' ')}</div>"
            f"<div class='body3'>{p.get('body', '')}</div>"
            f"<div class='say {side}{out}'><span class='who'>H · 그래서 나는?</span>{p.get('take', '')}</div>"
            f"<div class='fr b'><img src='{img_b.as_uri()}' style='object-position:{p.get('pos_b', '50% 30%')}'></div>"
            f"</div><div class='src'>출처 · {_src(p, c)}</div>")


def build(ep, video, outdir, alt_path=None, base=None):
    """컷 JPEG 를 outdir 에, 대체 텍스트를 alt_path(기본 outdir 옆 comic_alt.json — 게시 코드 post_comic 이 읽는 자리)에.
    미리보기(--out)는 대체 텍스트도 미리보기 폴더 안에 둔다 — 게시용 comic_alt.json 을 덮어쓰지 않게(Codex 리뷰)."""
    c = ep["comic"]
    picked = from_cards(c, ep["date"])
    fonts = font_css()
    duo = c.get("layout") == "duo"   # 두 컷 웹툰(생성 그림) — 표지가 따로 한 장
    n = len(c["panels"]) + 1 + bool(c.get("summary") and picked) + duo
    img = lambda q: (Path(q) if Path(q).is_absolute() else Path(base or ".") / q).resolve()  # noqa: E731
    if duo:   # 그림이 하나라도 없으면 아무것도 지우거나 그리기 전에 멈춘다(지난 장을 반쯤 덮어쓰지 않게)
        need = [(c.get("cover") or {}).get("img")] + [p.get(k) for p in c["panels"] for k in ("img_a", "img_b")]
        missing = [str(q) for q in need if not q or not img(q).exists()]
        if missing:
            raise SystemExit(f"두 컷 웹툰 그림이 없어요: {', '.join(missing)} — cover.img·panels[i].img_a·img_b(brief.json 폴더 기준)")
    elif video is None:
        raise SystemExit("영상 장면 만화(layout 없음)는 영상이 필요해요 — comic.py <episode.json> <영상.mp4>")
    outdir.mkdir(parents=True, exist_ok=True)
    for old in outdir.glob("c*.jpg"):
        old.unlink()
    top = lambda i: (f"<div class='top'><div class='series'><span class='pill'>H 극장</span>{c['series']} · {i}/{n}</div>"  # noqa: E731
                     "<div class='logo'>EDIT H<b>.</b></div></div>")
    src_line = lambda p: f"<div class='src'>출처 · {p.get('src') or c['sources']}</div>"  # noqa: E731
    alts = {}
    if duo:
        cov = c.get("cover") or {}
        shot(page(fonts, top(1) + duo_cover(c, picked, img(cov["img"]), cov.get("pos", "50% 50%"))), outdir / "c1.jpg")
        alts["c1.jpg"] = f"H 극장 표지 — {plain(c['title'])} · 오늘 다룰 {len(picked)}가지: " + " / ".join(str(it.get("tag") or "") for it in picked)
        cards = iter(picked)   # picked = card 가 있는 컷만, 컷 순서대로(from_cards) — card 없는 컷이 섞여도 어긋나지 않게
        for i, p in enumerate(c["panels"], 2):
            it = next(cards) if p.get("card") else {}
            p.setdefault("number", it.get("number"))
            p.setdefault("tag", it.get("tag"))
            shot(page(fonts, top(i) + duo_slide(c, i, p, img(p["img_a"]), img(p["img_b"]))), outdir / f"c{i}.jpg")
            alts[f"c{i}.jpg"] = (f"H 극장 {i - 1}번 소식 — {plain(p['bubble'])}. {plain(p.get('body', ''))} "
                                 f"H: 그래서 나는? {plain(p.get('take', ''))}")
    with tempfile.TemporaryDirectory() as tmp:
        for i, p in enumerate([] if duo else c["panels"], 1):
            frame = Path(tmp) / f"f{i}.jpg"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(p["t"]), "-i", str(video), "-frames:v", "1", "-q:v", "2", str(frame)], check=True)
            bubble = f"<div class='bubble'><span class='who'>{p.get('who', 'H')}</span>{p['bubble']}</div>"
            box = f"<div class='box'>{p['box']}</div>" if p.get("box") else ""
            rich = bool(p.get("body") or p.get("take"))   # 카드 글을 다 싣는 컷(11/02~ 5가지 웹툰) — 그림을 줄이고 본문·'그래서 나는?'을 단다
            if rich:
                box = ((f"<div class='body2'>{p['body']}</div>" if p.get("body") else "")
                       + (f"<div class='take'><span class='lab'>그래서 나는?</span>{p['take']}</div>" if p.get("take") else ""))
            if i == 1:   # 표지: 제목 + 큰 컷 + 넘기기 안내
                body = (top(i) + f"<div class='title'>{c['title']}</div>"
                        f"<div class='panel'><img src='{frame.as_uri()}'><div class='num'>1</div></div>"
                        f"<div class='stack'>{bubble}{box}</div><div class='swipe'>넘겨서 {len(c['panels'])}컷으로 보기 →</div>"
                        # 컷마다 출처가 다른 날(5가지 웹툰): 표지 출처는 제목 아래 한 줄 — 아래쪽은 설명·넘기기 안내 자리라 겹친다
                        + (src_line(p).replace("class='src'", "class='src' style='top:282px;bottom:auto;font-size:22px'") if p.get("src") else ""))
                if rich:
                    html = page(fonts, body, ptop=320, ph=520, pos=p.get("pos", "50% 40%"), bt=780, ml=40, mr=80, bs=44,
                                tail=p.get("tail", "left:150px;"))
                else:
                    html = page(fonts, body, ptop=320 if p.get("src") else 310, ph=750 if p.get("src") else 760,
                                pos=p.get("pos", "50% 40%"), bt=990, ml=60, mr=140, tail="left:150px;")
            else:
                body = (top(i) + f"<div class='panel'><img src='{frame.as_uri()}'><div class='num'>{i}</div></div>"
                        f"<div class='stack'>{bubble}{box}</div>{src_line(p)}")
                ph = p.get("ph", 680 if rich else 740)
                html = page(fonts, body, ph=ph, bt=ph + 60, pos=p.get("pos", "50% 45%"), bs=46 if rich else 50,
                            tail=p.get("tail", "left:170px;"))
            shot(html, outdir / f"c{i}.jpg")
            alts[f"c{i}.jpg"] = (f"H 극장 {i}컷 — {plain(p.get('who', 'H'))}: {plain(p['bubble'])}" + (f" {plain(p['box'])}" if p.get("box") else "")
                                 + (f" {plain(p['body'])}" if p.get("body") else "") + (f" 그래서 나는? {plain(p['take'])}" if p.get("take") else ""))
    if c.get("summary") and picked:   # 저장해 두는 한 장 — 5가지를 번호·제목·숫자로(08:30 카드의 '5가지 한눈에'와 같은 글)
        k = n - 1
        rows = "".join(
            f"<div class='row'><div class='n'>{j}</div><div class='h'>{htmlmod.escape(re.sub(r'==|[*]{2}', '', it['headline']).replace(chr(10), ' '))}</div>"
            f"<div class='v'>{htmlmod.escape(str(it.get('number') or (it.get('compare') or {}).get('to', {}).get('value', '')))}</div></div>"
            for j, it in enumerate(picked, 1))
        body = (top(k) + "<div style='position:absolute;left:70px;right:70px;top:190px'>"
                "<div style='text-align:center;font-weight:700;font-size:30px;color:#57534C'>저장해 두고 두고두고 보세요</div>"
                f"<div style='text-align:center;margin-top:18px;font-weight:900;font-size:66px;letter-spacing:-2px'>오늘의 <span class='hl'>{len(picked)}가지</span> 한눈에</div>"
                f"<div style='margin-top:46px;border-top:4px solid #111'>{rows}</div></div>")
        shot(page(fonts, body), outdir / f"c{k}.jpg")
        alts[f"c{k}.jpg"] = "오늘의 5가지 한눈에 — " + " / ".join(plain(_md(it["headline"])) for it in picked)
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
    (alt_path or outdir.parent / "comic_alt.json").write_text(json.dumps(alts, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("episode")
    ap.add_argument("video", nargs="?", help="장면을 뽑을 AI 영상 — 두 컷 웹툰(layout duo, 생성 그림)이면 없어도 된다")
    ap.add_argument("--out", help="미리보기 폴더(기본 instagram/{날짜}/comic — 게시 폴더)")
    a = ap.parse_args()
    ep = json.loads(Path(a.episode).read_text(encoding="utf-8"))
    out = Path(a.out) if a.out else ROOT / "instagram" / ep["date"] / "comic"
    n = build(ep, Path(a.video) if a.video else None, out, alt_path=out / "comic_alt.json" if a.out else None,
              base=Path(a.episode).resolve().parent)
    print(f"ok {out} {n}장")


if __name__ == "__main__":
    main()
