"""매거진 스타일 카드뉴스(1080×1350, 4:5) HTML.

구성(기본 8장)
  01 COVER     잡지 표지: 마스트헤드 + 세리프 헤드라인 + 커버라인 3개
  02 CONTENTS  오늘의 10가지 목차
  03 FEATURE   빅이슈: 핵심 문장 + 큰 숫자
  04 SO WHAT   빅이슈의 '그래서 마케터는?' + 오늘 점검할 것
  05~07 PICK   섹션별 대표 이슈 1개씩
  08 QUESTION  오늘의 질문 + 저장/공유/구독 CTA

이전 카드(2026-06, 크림+레드 산세리프) 대비 개선점
  - 한 장 = 한 메시지. 본문 글자 수 상한(content.CARD_LIMITS)과 자동 축소(최대 20%)로 빽빽함 방지
  - 세리프 헤드라인·큰 숫자·괘선·폴리오로 '잡지' 위계를 분명히
  - 밝은/어두운/레드 페이지 리듬으로 스와이프 이탈 방지
  - 모든 사실 카드에 출처, 하단 진행 막대로 남은 장 수 표시
  - 인스타 UI(하단 점·캡션)에 가리지 않도록 하단 안전영역 확보
"""
from .common import ROOT, WEEKDAYS_EN, esc, md, plain

W, H = 1080, 1350

CSS = """
:root{--ink:#0D0C0A;--paper:#F5F1E8;--cream:#F5F1E8;--red:#FF5233;--red-ink:#D23A12;--muted:#6E665A;--muted-d:#A39A8B;--rule:#D9D1C2;}
*{box-sizing:border-box;margin:0;padding:0;}
body{background:#777;width:1080px;}
.card{width:1080px;height:1350px;position:relative;overflow:hidden;background:var(--paper);color:var(--ink);
  font-family:'Pretendard',sans-serif;word-break:keep-all;overflow-wrap:break-word;--k:1;
  display:flex;flex-direction:column;padding:78px 88px 0;}
.card.dark{background:var(--ink);color:var(--cream);}
.card.red{background:var(--red);color:var(--ink);}
.serif{font-family:'Noto Serif KR',serif;}
h1,h2,blockquote{text-wrap:balance;}
.mast{display:flex;justify-content:space-between;align-items:center;border-bottom:3px solid currentColor;padding-bottom:20px;flex:none;}
.mast img{height:40px;display:block;}
.mast .folio{font-size:21px;font-weight:800;letter-spacing:.16em;}
.body{flex:1;min-height:0;overflow:hidden;display:flex;flex-direction:column;padding:0 0 150px;}
.foot{position:absolute;left:88px;right:88px;bottom:58px;display:flex;justify-content:space-between;align-items:baseline;
  font-size:22px;font-weight:600;color:var(--muted);}
.dark .foot{color:var(--muted-d);} .red .foot{color:var(--ink);}
.foot .pg{font-weight:800;color:var(--ink);letter-spacing:.06em;} .dark .foot .pg{color:var(--cream);}
.progress{position:absolute;left:0;bottom:0;height:12px;background:var(--red);} .red .progress{background:var(--ink);}
.kicker{font-size:calc(24px*var(--k));font-weight:800;letter-spacing:.14em;color:var(--red-ink);}
.dark .kicker{color:var(--red);} .red .kicker{color:var(--ink);}
.chip{display:inline-block;align-self:flex-start;font-size:calc(24px*var(--k));font-weight:800;padding:10px 16px 9px;background:var(--ink);color:var(--cream);}
.dark .chip{background:var(--red);color:var(--ink);}
.acc{color:var(--red-ink);} .dark .acc{color:var(--red);} .red .acc{color:var(--cream);}
.src{font-size:calc(21px*var(--k));color:var(--muted);margin-top:auto;padding-top:22px;} .dark .src{color:var(--muted-d);}
.swipe{font-size:26px;font-weight:800;color:var(--red);}

/* COVER */
.cover .issue{margin-top:44px;display:flex;justify-content:space-between;align-items:flex-end;}
.cover .issue .no{font-size:150px;font-weight:900;line-height:.8;color:var(--red);letter-spacing:-.02em;}
.cover .issue .date{font-size:24px;font-weight:700;text-align:right;line-height:1.5;color:var(--muted-d);}
.cover h1{font-size:calc(92px*var(--k));font-weight:900;line-height:1.22;letter-spacing:-.01em;margin-top:64px;}
.cover .deck{font-size:calc(30px*var(--k));line-height:1.6;color:var(--muted-d);margin-top:30px;font-weight:500;}
.cover .lines{margin-top:auto;border-top:1px solid #3A352D;}
.cover .lines div{display:flex;gap:22px;padding:17px 0;border-bottom:1px solid #3A352D;font-size:calc(27px*var(--k));font-weight:600;}
.cover .lines b{color:var(--red);font-weight:800;min-width:40px;}
.cover .swipe{margin-top:26px;}

/* CONTENTS */
.contents h2{font-size:calc(66px*var(--k));font-weight:900;margin-top:10px;line-height:1.2;}
.contents .top{margin-top:44px;}
.contents ol{list-style:none;margin-top:26px;border-top:2px solid var(--ink);}
.contents li{display:flex;align-items:baseline;gap:26px;padding:calc(15px*var(--k)) 0;border-bottom:1px solid var(--rule);}
.contents li .n{font-size:calc(34px*var(--k));font-weight:900;color:var(--red-ink);min-width:52px;}
.contents li .t{font-size:calc(31px*var(--k));font-weight:700;line-height:1.3;flex:1;}
.contents li .g{font-size:calc(21px*var(--k));font-weight:600;color:var(--muted);white-space:nowrap;}
.contents li.big .t{font-weight:900;}

/* FEATURE / PICK */
.feature .top,.pick .top{margin-top:48px;display:flex;flex-direction:column;gap:22px;}
.feature h2,.pick h2{font-size:calc(70px*var(--k));font-weight:900;line-height:1.24;letter-spacing:-.01em;}
.feature p,.pick p{font-size:calc(33px*var(--k));line-height:1.62;font-weight:500;color:#3B362E;margin-top:34px;}
.dark .feature p{color:#D9D2C5;}
.stat{margin-top:auto;padding-top:28px;border-top:2px solid currentColor;display:flex;align-items:flex-end;gap:28px;}
.stat .v{font-size:calc(168px*var(--k));font-weight:900;line-height:.9;color:var(--red-ink);letter-spacing:-.02em;white-space:nowrap;}
.stat .v small{font-size:.42em;margin-left:6px;}
.stat .c{font-size:calc(23px*var(--k));line-height:1.5;color:var(--muted);padding-bottom:10px;}
.pick .num{font-size:calc(150px*var(--k));font-weight:900;line-height:.8;color:var(--red-ink);}
.pick .row{display:flex;justify-content:space-between;align-items:flex-end;}
.pick .take{margin-top:44px;border-left:8px solid var(--red);padding:6px 0 6px 26px;font-size:calc(31px*var(--k));line-height:1.55;font-weight:700;}
.pick .take b{color:var(--red-ink);}
.pick .ministat{margin-top:30px;display:flex;align-items:baseline;gap:18px;}
.pick .ministat .v{font-size:calc(92px*var(--k));font-weight:900;color:var(--red-ink);line-height:1;}
.pick .ministat .c{font-size:calc(23px*var(--k));color:var(--muted);line-height:1.45;}

/* SO WHAT */
.sowhat .center{margin:auto 0;padding:40px 0;}
.sowhat .q{font-size:260px;line-height:.62;color:var(--red);height:120px;}
.sowhat blockquote{font-size:calc(62px*var(--k));font-weight:700;line-height:1.5;margin-top:26px;}
.sowhat blockquote b{color:var(--red);font-weight:900;}
.sowhat .check{border-top:1px solid #3A352D;padding-top:22px;}
.sowhat .check h3{font-size:calc(22px*var(--k));letter-spacing:.14em;color:var(--red);font-weight:800;}
.sowhat .check div{font-size:calc(28px*var(--k));line-height:1.55;margin-top:12px;color:#E4DDD0;font-weight:500;}

/* QUESTION */
.question .top{margin-top:70px;}
.question h2{font-size:calc(88px*var(--k));position:relative;z-index:1;font-weight:900;line-height:1.3;margin-top:26px;}
.question .cta{margin-top:auto;border-top:3px solid var(--ink);}
.question .cta div{display:flex;gap:22px;align-items:baseline;padding:20px 0;border-bottom:1px solid rgba(13,12,10,.25);font-size:calc(30px*var(--k));font-weight:700;}
.question .cta span{font-size:24px;font-weight:800;min-width:40px;}
.question .mark{position:absolute;right:40px;top:330px;font-size:620px;line-height:1;font-weight:900;color:rgba(13,12,10,.10);pointer-events:none;}
.question .cta,.question .handle{position:relative;z-index:1;}
.question .handle{font-size:calc(40px*var(--k));font-weight:900;margin-top:28px;}
"""


WORDMARKS = {  # 바탕별 워드마크: 레드 바탕에선 빨간 취소선이 묻히므로 크림 취소선 버전을 쓴다
    "paper": "edit_h_wordmark_strike_paper.png",
    "dark": "edit_h_wordmark_strike_cream.png",
    "red": "edit_h_wordmark_strike_onred.png",
}


def _mast(d, bg):
    wm = WORDMARKS[bg]
    folio = f"VOL.{d['vol']} · {d['date_obj'].strftime('%Y.%m.%d')} {WEEKDAYS_EN[d['date_obj'].weekday()]}"
    return (f'<div class="mast"><img src="{(ROOT / "assets" / wm).as_uri()}" alt="EDIT H">'
            f'<div class="folio">{folio}</div></div>')


def _foot(n, total):
    return (f'<div class="foot"><span>@edit.h.kr · 매 영업일 08:30</span><span class="pg">{n:02d} / {total:02d}</span></div>'
            f'<div class="progress" style="width:{n / total * 100:.2f}%"></div>')


def _src(sources):
    names = "·".join(esc(s["name"]) for s in sources)
    return f'<div class="src">출처 · {names} {esc(sources[-1].get("date", ""))}</div>'


def _acc(text):
    """==강조== 는 레드(.acc), **굵게** 는 굵게. 색은 CSS 가 페이지 바탕(밝음/어둠/레드)에 맞춰 준다."""
    return md(text).replace("<span>", '<span class="acc">')


def cover(d, n, total):
    title = d.get("cover_title", d["hero_title"])
    lines = "".join(
        f'<div><b>{it["no"]}</b><span>{esc(plain(it.get("short_title", it["title"])))}</span></div>'
        for it in d["pick_items"]
    )
    return f"""<section class="card dark cover">{_mast(d, "dark")}<div class="body">
<div class="issue"><div class="no serif">{esc(d['vol'])}</div><div class="date">DAILY MARKETING BRIEF<br>{d['date_obj'].strftime('%Y.%m.%d')} {d['weekday']}요일</div></div>
<div class="kicker" style="margin-top:56px">TODAY'S BIG ISSUE · {esc(d['big_issue']['tag'])}</div>
<h1 class="serif" data-fit>{_acc(title)}</h1>
<div class="deck">{esc(plain(d.get('cover_deck', d['subtitle'])))}</div>
<div class="lines">{lines}</div>
<div class="swipe">밀어서 10가지 보기 →</div>
</div>{_foot(n, total)}</section>"""


def contents(d, n, total):
    rows = "".join(
        f'<li class="{"big" if i == 0 else ""}"><span class="n serif">{it["no"]}</span>'
        f'<span class="t">{esc(plain(it.get("short_title", it.get("title", d["title"]))))}</span>'
        f'<span class="g">{esc(it["tag"])}</span></li>'
        for i, it in enumerate(d["all_items"])
    )
    return f"""<section class="card contents">{_mast(d, "paper")}<div class="body">
<div class="top"><div class="kicker">IN THIS ISSUE</div><h2 class="serif">오늘의 10가지</h2></div>
<ol>{rows}</ol>
</div>{_foot(n, total)}</section>"""


def _stat_block(st):
    return (f'<div class="stat"><div class="v serif">{esc(st["value"])}<small>{esc(st.get("unit", ""))}</small></div>'
            f'<div class="c">{md(st["caption"])}</div></div>')


def feature(d, n, total):
    b = d["big_issue"]
    text = b.get("card_text", b["paragraphs"][0])
    return f"""<section class="card feature">{_mast(d, "paper")}<div class="body">
<div class="top"><div class="kicker">01 · TODAY'S BIG ISSUE</div><span class="chip">{esc(b['tag'])}</span>
<h2 class="serif">{_acc(b.get('card_title', d['hero_title']))}</h2></div>
<p>{_acc(text)}</p>
{_stat_block(b['stat'])}
{_src(b['sources'])}
</div>{_foot(n, total)}</section>"""


def sowhat(d, n, total):
    b = d["big_issue"]
    checks = b.get("checklist") or []
    check_html = ""
    if checks:
        check_html = '<div class="check"><h3>오늘 점검할 것</h3>' + "".join(
            f"<div>☐ {esc(plain(c))}</div>" for c in checks[:3]) + "</div>"
    return f"""<section class="card dark sowhat">{_mast(d, "dark")}<div class="body">
<div class="kicker" style="margin-top:48px">SO WHAT · 그래서, 마케터는?</div>
<div class="center"><div class="q serif">“</div>
<blockquote class="serif">{_acc(b.get('card_takeaway', b['takeaway']))}</blockquote></div>
{check_html}
</div>{_foot(n, total)}</section>"""


def pick(d, it, n, total):
    card = it.get("card", {})
    text = card.get("text", it["body"])
    take = card.get("takeaway", it["takeaway"])
    st = card.get("stat")
    ministat = ""
    if st:
        ministat = (f'<div class="ministat"><div class="v serif">{esc(st["value"])}<small style="font-size:.45em">{esc(st.get("unit", ""))}</small></div>'
                    f'<div class="c">{md(st["caption"])}</div></div>')
    return f"""<section class="card pick">{_mast(d, "paper")}<div class="body">
<div class="top"><div class="row"><div class="num serif">{it['no']}</div><span class="chip">{esc(it['tag'])}</span></div>
<h2 class="serif">{_acc(card.get('title', it['title']))}</h2></div>
{ministat}
<p>{_acc(text)}</p>
<div class="take">→ {_acc(take)}</div>
{_src(it['sources'])}
</div>{_foot(n, total)}</section>"""


def question(d, n, total):
    q = d["question"]
    return f"""<section class="card red question">{_mast(d, "red")}<div class="body">
<div class="top"><div class="kicker">TODAY'S QUESTION · 오늘의 질문</div>
<h2 class="serif">{_acc(q['text'])}</h2></div>
<div class="cta">
<div><span>01</span>💬 댓글로 여러분의 답을 남겨주세요</div>
<div><span>02</span>📌 저장해두고 회의 전에 다시 꺼내보세요</div>
<div><span>03</span>📩 전문 10가지는 뉴스레터로 — 프로필 링크</div>
</div>
<div class="handle">@edit.h.kr</div>
</div><div class="mark serif" aria-hidden="true">?</div>{_foot(n, total)}</section>"""


CARD_NAMES = ["cover", "contents", "feature", "sowhat", "pick1", "pick2", "pick3", "question"]


def build(d, font_css):
    """(html 문자열, 파일명 목록)을 돌려준다. 카드 순서 = 파일명 순서."""
    picks = d["pick_items"][:3]
    names = CARD_NAMES[:4] + [f"pick{i}" for i in range(1, len(picks) + 1)] + ["question"]
    total = len(names)
    sections = [cover(d, 1, total), contents(d, 2, total), feature(d, 3, total), sowhat(d, 4, total)]
    sections += [pick(d, it, 5 + i, total) for i, it in enumerate(picks)]
    sections.append(question(d, total, total))
    files = [f"{i:02d}_edit_h_{d['date']}_{name}.png" for i, name in enumerate(names, 1)]
    page = f"""<!DOCTYPE html><html lang="ko"><head><meta charset="UTF-8">
<style>{font_css}
{CSS}</style></head><body>
{''.join(sections)}
</body></html>"""
    return page, files
