"""아침 스토리 화면(1080×1920).

2026-10-29 운영자 ① '스토리에 릴스 첫 장 하나만 올라가니 아무 내용이 없다, 눌러도 반응 없는 껍데기'
              ② '스토리에서 볼 때 더 많은 인사이트를 얻고 싶다 — 한눈에 관련 기사를 보는 방향'.

앱에서 피드 게시물을 스토리에 붙이면(게시물 스티커) 누를 때 그 게시물로 가지만, 인스타그램 API(STORIES)는 이미지·영상만 받고
게시물·링크 스티커를 붙일 수 없다. 스토리는 우리 글이 가장 많이 읽히는 자리라(10/22~10/28 도달 22~36, 같은 날 캐러셀 5~14)
누르지 않고 넘기기만 해도 오늘 소식과 '왜 중요한지'·관련 기사가 보이게 스토리 전용 세로 화면을 만든다(build_briefing):

  (세로 릴스 첫 장 r1_hook — post_instagram 이 맨 앞에 붙인다. 없으면 같은 훅 화면 s1_hook)
  → H PICK 브리핑: 핵심 숫자·제목·'왜 중요해?' 요점·그래서 할 일·관련 기사·원문(출처)
  → 오늘의 소식 2·3 → 4·5: 숫자·제목·사실 한두 문장·그래서 할 일·관련 기사·원문, 마지막 장에 '원문 링크는 뉴스레터'

장마다 한 덩어리만(소식 두 개) 두어 5초 안에 읽히게 하고, 넘치면 글자를 줄이고(render_cards.cjs --k) 그래도 넘치면 카드 화면으로 낸다.
형식 2 가 아니거나 브리핑 화면을 못 만들면 캐러셀 카드(H PICK·N가지 한눈에)를 먹색 바탕에 얹은 화면(build_cards, 10/29 첫 판)을 쓴다.
인스타 스토리는 위(약 220px)에 진행 막대·계정 이름, 아래(약 200px)에 답장 칸이 덮으므로 글은 그 사이(250~1620px)에 둔다.
"""
import html
from pathlib import Path

from . import reel_frames
from .cards import ACC, ACC_FILL, ACC_INK, ACC_ON_DARK, CSS, INK, MUTED, PAPER, SUB, TEXT, esc, fit_size, fs, hero_value, mk

W, H = 1080, 1920
CARD_W = 1000
CARD_H = CARD_W * 1350 // 1080   # 1250
ROLES = ("pick", "summary")       # 카드 화면: 훅 다음에 보여 줄 카드(있는 것만, 이 순서로)
PER_FRAME = 2                     # 브리핑: 한 장에 소식 두 개
SAFE_TOP, SAFE_BOTTOM = 250, 300

FRAME_CSS = """
.story{height:1920px;background:%(ink)s;}
.story .body{padding:%(top)dpx 90px %(bottom)dpx;}
.story .shot{position:absolute;left:%(left)dpx;width:%(w)dpx;height:%(h)dpx;border-radius:28px;overflow:hidden;
  border:2px solid rgba(255,255,255,.16);}
.story .shot img{display:block;width:100%%;height:100%%;}
.story .cta{position:absolute;left:60px;right:60px;top:1530px;text-align:center;color:#FFFFFF;}
""" % {"ink": INK, "top": SAFE_TOP, "bottom": SAFE_BOTTOM, "left": (W - CARD_W) // 2, "w": CARD_W, "h": CARD_H}


def _page(frames, font_css, extra_css=""):
    return f"""<!DOCTYPE html><html lang="ko"><head><meta charset="UTF-8">
<style>{font_css}
{CSS}
{extra_css}
{FRAME_CSS}</style></head><body>
{''.join(frames)}
</body></html>"""


# ── 브리핑 화면(2026-10-29 ②~) ─────────────────────────────────────────────

def _source(it, dark=False):
    color = "rgba(255,255,255,.62)" if dark else MUTED
    return (f'<div style="margin-top:18px;font-weight:500;font-size:{fs(28)};line-height:1.45;color:{color};">'
            f'관련 기사·원문 · {esc(it["source"])}</div>') if it.get("source") else ""


def _pick(d):
    """H PICK 브리핑 — 먹색 바탕(캐러셀 H PICK 카드와 같은 반전)."""
    it, deep = d["card_issues"][0], d["cards"]["deep"]
    val = hero_value(it)
    label = f"H PICK · {d['series']['label']}" if d.get("series") else f"H PICK · {it['tag']}"
    points = "".join(
        f'<div style="display:flex;gap:18px;margin-top:16px;"><span style="flex:none;color:{ACC_ON_DARK};">•</span>'
        f'<span>{mk(p, strong="#FFFFFF", dark=True)}</span></div>' for p in deep["points"])
    return f"""<section class="card story" style="background:{INK};">
<div class="body" style="justify-content:center;color:#FFFFFF;">
  <div style="font-weight:800;font-size:{fs(34)};line-height:1;color:{ACC_ON_DARK};">{esc(label)}</div>
  <div style="margin-top:34px;font-weight:900;font-size:{fs(fit_size(val, 190))};line-height:1;letter-spacing:-5px;color:{ACC_FILL};">{esc(val)}</div>
  <div class="bal" style="margin-top:30px;font-weight:800;font-size:{fs(62)};line-height:1.28;letter-spacing:-1.5px;">{mk(it["headline"], strong="#FFFFFF", dark=True)}</div>
  <div style="margin-top:44px;padding:34px 38px;border-radius:26px;background:rgba(255,255,255,.08);">
    <div style="font-weight:800;font-size:{fs(40)};line-height:1.35;">{mk(deep["headline"], strong="#FFFFFF", dark=True)}</div>
    <div style="font-weight:500;font-size:{fs(35)};line-height:1.5;color:rgba(255,255,255,.9);">{points}</div>
  </div>
  <div style="margin-top:34px;align-self:flex-start;background:{ACC};color:{INK};font-weight:800;font-size:{fs(36)};line-height:1.35;
    padding:18px 30px;border-radius:22px;">그래서? {esc(it["takeaway"])}</div>
  {_source(it, dark=True)}
</div></section>"""


def _news(d, chunk, last):
    """오늘의 소식 두 개 — 크림색 바탕. 가운데 정렬, 마지막 장만 위에서부터 쌓고 맨 아래에 '원문 링크는 뉴스레터'."""
    total = len(d["card_issues"])
    nos = [it["no"] for it in chunk]
    blocks = "".join(f"""
  <div style="padding:40px 0 38px;border-top:2px solid #DDD6C6;">
    <div style="display:flex;align-items:flex-end;justify-content:space-between;gap:24px;">
      <div style="font-weight:700;font-size:{fs(32)};line-height:1.2;color:{SUB};">{it["no"]:02d} · {esc(it["tag"])}</div>
      <div style="font-weight:900;font-size:{fs(min(70, fit_size(hero_value(it), 70)))};line-height:1;letter-spacing:-2px;color:{TEXT};
        background:linear-gradient(180deg,transparent 60%,{ACC_FILL} 60%);padding:0 .06em;white-space:nowrap;">{esc(hero_value(it))}</div>
    </div>
    <div class="bal" style="margin-top:18px;font-weight:800;font-size:{fs(58)};line-height:1.28;letter-spacing:-1.5px;color:{TEXT};">{mk(it["headline"].replace(chr(10), " "))}</div>
    <div style="margin-top:16px;font-weight:500;font-size:{fs(37)};line-height:1.5;color:{SUB};">{mk(it["body"])}</div>
    <div style="margin-top:14px;font-weight:700;font-size:{fs(37)};line-height:1.45;color:{ACC_INK};">→ {esc(it["takeaway"])}</div>
    {_source(it)}
  </div>""" for it in chunk)
    span = f"{nos[0]:02d}" + (f"–{nos[-1]:02d}" if len(nos) > 1 else "")
    foot = (f'<div style="margin-top:auto;padding-top:28px;border-top:2px solid #DDD6C6;font-weight:700;font-size:{fs(32)};line-height:1.45;color:{TEXT};">'
            f'원문 링크·한 줄 뉴스는 뉴스레터에<br><span style="font-weight:500;color:{SUB};">왼쪽 위 프로필 → 링크에서 받아 보세요</span></div>') if last else ""
    return f"""<section class="card story" style="background:{PAPER};">
<div class="body" style="justify-content:{'flex-start' if last else 'center'};">
  <div style="font-weight:800;font-size:{fs(34)};line-height:1;color:{TEXT};">오늘의 소식 <span style="color:{ACC};">{span}</span>
    <span style="font-weight:600;color:{MUTED};">/ {total:02d}</span></div>
  <div style="margin-top:26px;">{blocks}</div>
  {foot}
</div></section>"""


def build_briefing(d, hook, font_css):
    """(html, 파일명 목록) — 형식 2(H PICK 이 있는) 호의 스토리 전용 화면. 형식이 맞지 않으면 ("", [])."""
    issues = d.get("card_issues") or []
    if d.get("format") != 2 or len(issues) < 2 or not (d.get("cards") or {}).get("deep"):
        return "", []
    rest = issues[1:]
    chunks = [rest[i:i + PER_FRAME] for i in range(0, len(rest), PER_FRAME)]
    frames = ([] if hook else [reel_frames.hook(d)]) + [_pick(d)] + [_news(d, c, i == len(chunks) - 1) for i, c in enumerate(chunks)]
    names = ([] if hook else ["hook"]) + ["pick"] + [f"news{i}" for i in range(1, len(chunks) + 1)]
    return _page(frames, font_css, reel_frames.FRAME_CSS), [f"s{i}_{n}.png" for i, n in enumerate(names, 1)]


# ── 카드 화면(10/29 첫 판 — 브리핑을 못 만들 때) ─────────────────────────────

def role(name):
    """'02_edit_h_2026-10-29_pick.jpg' → 'pick'."""
    return Path(name).stem.rsplit("_", 1)[-1]


def choose(card_files, hook):
    """스토리에 쓸 카드 파일 — 훅(세로 릴스 첫 장)이 없으면 표지부터. 고를 카드가 하나도 없으면 빈 목록."""
    by = {}
    for f in card_files:
        by.setdefault(role(f), f)
    picked = ([] if hook else [by.get("cover")]) + [by.get(r) for r in ROLES]
    return list(dict.fromkeys(f for f in picked if f))


def _card_frame(src, n_cards, last):
    top = 250 if last else (H - CARD_H) // 2
    cta = (f'<div class="cta"><div style="font-weight:800;font-size:46px;line-height:1.3;letter-spacing:-1px;">'
           f'카드 {n_cards}장 전체와 출처는 피드에</div>'
           f'<div style="margin-top:16px;font-weight:500;font-size:34px;line-height:1.4;opacity:.85;">'
           f'왼쪽 위 프로필을 눌러 오늘 게시물을 보세요</div></div>') if last else ""
    src = html.escape(src, quote=True)
    return (f'<section class="card story">'
            f'<div class="shot" style="top:{top}px;"><img src="{src}" alt=""></div>{cta}</section>')


def build_cards(card_dir, card_files, hook, font_css):
    """(html, 파일명 목록). card_dir 의 게시용 JPEG(ig/) 중 고른 카드를 세로 화면으로. 고를 카드가 없으면 ("", [])."""
    chosen = choose(card_files, hook)
    if not chosen:
        return "", []
    frames = [_card_frame(Path(card_dir).resolve().joinpath(f).as_uri(), len(card_files), i == len(chosen) - 1)
              for i, f in enumerate(chosen)]
    return _page(frames, font_css), [f"s{i}_{role(f)}.png" for i, f in enumerate(chosen, 1)]
