"""카드뉴스(1080×1350, 4:5) — 최신 뉴스레터 양식(VOL.092)과 같은 디자인 언어, 6장 구성.

  01 COVER     @edit.h.kr · #호수/요일 칩 · 제목(굵게/보통 두 줄) · 세 줄 요약
  02 BIG ISSUE 번호 배지 · 제목 · 태그 · 핵심 문장 · 형광펜 큰 숫자 · 마케터의 한 줄
  03~05 PICK   섹션별 대표 이슈 1개씩(같은 구성)
  06 QUESTION  Q · 오늘의 질문 · 프로필 카드 · 구독 안내

한 장에 한 메시지만 담도록 글자 수 상한(content.CARD_LIMITS)과 자동 축소(최대 20%)를 둔다.
"""
from .common import esc, md, plain

W, H = 1080, 1350
TOTAL = 6

CSS = """
:root{--ink:#282F38;--body:#555558;--muted:#767676;--chipbg:#FFDCCB;--chipfg:#B23A0F;--hl:#FFC9AD;--box:#F3F3F3;
  --rule:#EAEAEA;--dchip:#363636;--dchipfg:#FF9466;}
*{box-sizing:border-box;margin:0;padding:0;}
body{background:#777;width:1080px;}
.card{width:1080px;height:1350px;position:relative;overflow:hidden;background:#FFFFFF;color:var(--ink);
  font-family:'Pretendard',sans-serif;word-break:keep-all;overflow-wrap:break-word;--k:1;
  display:flex;flex-direction:column;padding:62px 84px 0;}
.handle{flex:none;text-align:center;font-size:26px;font-weight:700;color:#5A5A5E;}
.body{flex:1;min-height:0;overflow:hidden;display:flex;flex-direction:column;padding:0 0 118px;}
.foot{position:absolute;left:0;right:0;bottom:50px;text-align:center;font-size:22px;font-weight:600;color:#A0A0A6;letter-spacing:.1em;}
h1,h2{text-wrap:balance;}
.hl{background:var(--hl);color:var(--ink);font-weight:700;}
.chips{display:flex;justify-content:center;gap:12px;margin-top:46px;}
.chips span{font-size:calc(28px*var(--k));font-weight:700;line-height:1;padding:13px 17px;background:var(--chipbg);color:var(--chipfg);white-space:nowrap;}
.chips span.d{background:var(--dchip);color:var(--dchipfg);}
.badge{flex:none;width:66px;height:66px;border-radius:15px;background:var(--ink);color:#FFFFFF;font-size:33px;font-weight:600;
  display:flex;align-items:center;justify-content:center;margin:56px auto 0;}
.tag{align-self:center;background:var(--chipbg);color:var(--chipfg);font-size:calc(26px*var(--k));font-weight:700;line-height:1;padding:12px 15px;margin-top:24px;}
h1{font-size:calc(82px*var(--k));line-height:1.38;text-align:center;letter-spacing:-.015em;margin-top:40px;color:var(--ink);}
h1 .l1{font-weight:700;} h1 .l2{font-weight:400;}
.meta{text-align:center;font-size:calc(25px*var(--k));color:var(--muted);margin-top:26px;}
.rule{border-top:2px solid var(--rule);margin:52px 0 20px;}
.pt{display:flex;gap:20px;align-items:flex-start;margin-top:26px;}
.pt .n{flex:none;width:44px;height:44px;border-radius:22px;background:var(--ink);color:#FFFFFF;font-size:23px;font-weight:700;
  display:flex;align-items:center;justify-content:center;margin-top:3px;}
.pt .t{font-size:calc(31px*var(--k));line-height:1.52;color:var(--body);}
.pt .t b{color:var(--ink);font-weight:700;}
.swipe{margin-top:auto;text-align:center;font-size:27px;font-weight:700;color:var(--chipfg);}
h2{font-size:calc(58px*var(--k));font-weight:700;line-height:1.36;text-align:center;margin-top:26px;letter-spacing:-.01em;}
p.txt{font-size:calc(32px*var(--k));line-height:1.7;color:var(--body);margin-top:36px;}
p.txt b{background:var(--hl);color:var(--ink);font-weight:700;}
.stat{align-self:center;background:var(--hl);padding:6px 26px;font-size:calc(108px*var(--k));font-weight:800;line-height:1.12;color:var(--ink);
  margin-top:40px;white-space:nowrap;}
.stat small{font-size:.48em;margin-left:4px;}
.stat.s{font-size:calc(86px*var(--k));margin-top:32px;}
.cap{text-align:center;font-size:calc(24px*var(--k));color:var(--muted);margin-top:16px;line-height:1.5;}
.box{background:var(--box);border-radius:30px;padding:30px 36px;margin-top:36px;}
.box .lb{font-size:calc(24px*var(--k));font-weight:700;color:var(--ink);}
.box .tx{font-size:calc(30px*var(--k));line-height:1.6;color:var(--body);margin-top:10px;font-weight:500;}
.box .tx b{color:var(--ink);font-weight:700;}
.src{font-size:calc(22px*var(--k));color:var(--muted);margin-top:auto;padding-top:24px;}
.pick .mid{margin:auto 0;padding:10px 0;}
.pick .mid p.txt{margin-top:0;}
.pick .src{margin-top:0;}
.q .mid{margin:auto 0;padding:20px 0 40px;}
.Q{text-align:center;font-size:50px;font-weight:800;color:var(--body);line-height:1;}
.q h2{font-size:calc(66px*var(--k));margin-top:28px;}
.q .box{text-align:center;}
.profile{margin-top:0;border:2px solid var(--rule);border-radius:36px;padding:30px 32px;display:flex;gap:28px;align-items:center;
  box-shadow:0 4px 14px rgba(0,0,0,.08);}
.avatar{flex:none;width:106px;height:106px;border-radius:50%;background:#0D0C0A;border:9px solid #FF5233;color:#F5F1E8;
  font-size:45px;font-weight:800;display:flex;align-items:center;justify-content:center;letter-spacing:-2px;}
.avatar i{font-style:normal;color:#FF5233;}
.profile .nm{font-size:29px;font-weight:500;color:var(--ink);}
.profile .stats{display:flex;gap:40px;margin-top:12px;}
.profile .stats b{display:block;font-size:31px;font-weight:700;color:#1B1B1E;}
.profile .stats span{font-size:21px;color:#6B6E75;}
.subscribe{margin-top:26px;background:var(--chipfg);color:#FFFFFF;border-radius:20px;text-align:center;font-size:30px;font-weight:700;padding:26px;}
"""


def _t(text):
    """**굵게** → <b>, ==강조== → 형광펜(.hl), \\n → 줄바꿈."""
    return md(text).replace("<span>", '<span class="hl">')


def _frame(n, cls, inner):
    return (f'<section class="card {cls}"><div class="handle">@edit.h.kr</div><div class="body">{inner}</div>'
            f'<div class="foot">{n} / {TOTAL}</div></section>')


def _src(sources):
    names = "·".join(esc(s["name"]) for s in sources)
    return f'<div class="src">출처 · {names} {esc(sources[-1].get("date", ""))}</div>'.replace(" </div>", "</div>")


def _stat(st, small=False):
    return (f'<div class="stat{" s" if small else ""}">{esc(st["value"])}<small>{esc(st.get("unit", ""))}</small></div>'
            f'<div class="cap">{_t(st["caption"])}</div>')


def _box(label, text):
    return f'<div class="box"><div class="lb">{label}</div><div class="tx">{_t(text)}</div></div>'


def cover(d):
    lines = d.get("cover_title", d["hero_title"]).split("\n")
    title = f'<span class="l1">{_t(lines[0])}</span>' + "".join(f'<br><span class="l2">{_t(x)}</span>' for x in lines[1:])
    pts = d.get("lead_points") or [{"title": t["label"], "text": t["text"]} for t in d["three_lines"]]
    points = "".join(
        f'<div class="pt"><div class="n">{i}</div><div class="t"><b>{_t(p["title"])}</b> — {_t(p["text"])}</div></div>'
        for i, p in enumerate(pts[:3], 1))
    return _frame(1, "cover", f"""
<div class="chips"><span class="d">#{esc(d['vol'])}</span><span>{d['weekday']}요일의</span><span>마케팅</span><span>브리프</span></div>
<h1 data-fit>{title}</h1>
<div class="meta">VOL.{esc(d['vol'])} · {d['date_obj'].strftime('%Y.%m.%d')} {d['weekday']}요일</div>
<div class="rule"></div>
{points}
<div class="swipe">밀어서 {len(d['all_items'])}가지 보기 →</div>""")


def big_issue(d):
    b = d["big_issue"]
    take = b.get("card_takeaway", b["takeaway"]).replace("\n", " ")
    return _frame(2, "feature", f"""
<div class="badge">1</div>
<h2>{esc(plain(d['title']))}</h2>
<div class="tag">01 · {esc(b['tag'])}</div>
<p class="txt">{_t(b.get('card_text', b['paragraphs'][0]))}</p>
{_stat(b['stat'])}
{_box('마케터의 한 줄', take)}
{_src(b['sources'])}""")


def pick(d, it, n):
    card = it.get("card", {})
    stat = _stat(card["stat"], small=True) if card.get("stat") else ""
    return _frame(n, "pick", f"""
<div class="badge">{int(it['no'])}</div>
<h2>{_t(card.get('title', it['title']))}</h2>
<div class="tag">{it['no']} · {esc(it['tag'])}</div>
{stat}
<div class="mid"><p class="txt">{_t(card.get('text', it['body']))}</p>
{_box('마케터의 한 줄', card.get('takeaway', it['takeaway']))}</div>
{_src(it['sources'])}""")


def question(d):
    q = d["question"]
    n_items = len(d["all_items"])
    return _frame(TOTAL, "q", f"""
<div class="mid"><div class="Q">Q</div>
<h2>{_t(q['text'])}</h2>
<div class="box"><div class="tx">💬 댓글로 여러분의 답을 남겨주세요<br>📌 저장해두고 회의 전에 다시 꺼내보세요</div></div></div>
<div class="profile"><div class="avatar">H<i>.</i></div><div><div class="nm">edit.h.kr</div>
<div class="stats"><div><b>{n_items}개</b><span>이슈 전문</span></div><div><b>{TOTAL}장</b><span>카드뉴스</span></div><div><b>{int(d['vol'])}호</b><span>누적 발행</span></div></div></div></div>
<div class="subscribe">매일 아침 {n_items}가지 이슈 — 프로필 링크에서 구독</div>""")


CARD_NAMES = ["cover", "bigissue", "pick1", "pick2", "pick3", "question"]


def build(d, font_css):
    """(html 문자열, 파일명 목록)을 돌려준다. 카드 순서 = 파일명 순서."""
    picks = d["pick_items"][:3]
    if len(picks) != 3:
        raise ValueError("카드뉴스 픽 아이템은 3개여야 합니다(card_picks 또는 섹션 3개 이상)")
    sections = [cover(d), big_issue(d)] + [pick(d, it, 3 + i) for i, it in enumerate(picks)] + [question(d)]
    files = [f"{i:02d}_edit_h_{d['date']}_{name}.png" for i, name in enumerate(CARD_NAMES, 1)]
    page = f"""<!DOCTYPE html><html lang="ko"><head><meta charset="UTF-8">
<style>{font_css}
{CSS}</style></head><body>
{''.join(sections)}
</body></html>"""
    return page, files
