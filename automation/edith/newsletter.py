"""뉴스레터(이메일) HTML — 최신 양식(VOL.092, 2026-09-18) 기준.

@edit.h.kr 머리 → #호수·요일 칩 → 가운데 정렬 제목(굵게/보통 두 줄) → 오늘의 편지(세 줄 요약 + H의 한 줄 관찰)
→ 01 빅이슈(큰 숫자 박스 + 마케터의 한 줄) → #1~#N 섹션(번호 배지 · 태그 칩 · 회색 요약 박스)
→ 짧게 볼 것 → Q(오늘의 질문) → 프로필 카드·구독 버튼 → 푸터.
색: 글자 #282F38 · 본문 #555558 · 보조 #767676 · 칩 #FFDCCB/#B23A0F · 형광펜 #FFC9AD · 회색 박스 #F3F3F3.
VOL.092 대비 보강: 출처를 원문 링크로, '카드뉴스 보기' 링크 추가. 이메일 호환을 위해 table + 인라인 스타일만 쓴다.
"""
from .common import esc, md, plain

F = "'Pretendard','Apple SD Gothic Neo','Malgun Gothic',sans-serif"
INK = "#282F38"
BODY = "#555558"
MUTED = "#767676"
CHIP_BG = "#FFDCCB"
CHIP_FG = "#B23A0F"
HL = "#FFC9AD"
BOX = "#F3F3F3"
RULE = "#EAEAEA"
DARK_CHIP = "#363636"
DARK_CHIP_FG = "#FF9466"

HL_B = f"color:{INK};background-color:{HL};"   # 본문 **굵게** = 형광펜
BOLD = "font-weight:700;"                       # 요약 박스 안 **굵게**


def _div(style, inner, center=False):
    align = "text-align:center;" if center else ""
    return f'<div style="font-family:{F};{style}{align}word-break:keep-all;">{inner}</div>'


def _body(text, size="15px", lh="1.8", mt=16):
    return _div(f"font-size:{size};font-weight:400;line-height:{lh};color:{BODY};margin-top:{mt}px;",
                md(text, HL_B, HL_B))


def _box(inner, pad="16px 20px", mt=14):
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{BOX};'
            f'border-radius:16px;margin-top:{mt}px;"><tr><td style="padding:{pad};">{inner}</td></tr></table>')


def _divider(after=28):
    return (f'<tr><td class="px" style="padding:36px 36px 0;"><div style="border-top:1px solid {RULE};font-size:0;'
            f'line-height:0;">&nbsp;</div></td></tr><tr><td style="height:{after}px;font-size:0;line-height:0;">&nbsp;</td></tr>')


def _chips(items):
    """[(text, dark?)] → 가운데 정렬 칩 한 줄."""
    tds = []
    for i, (text, dark) in enumerate(items):
        if i:
            tds.append('<td style="width:6px;font-size:0;line-height:0;">&nbsp;</td>')
        bg, fg = (DARK_CHIP, DARK_CHIP_FG) if dark else (CHIP_BG, CHIP_FG)
        tds.append(f'<td style="background:{bg};color:{fg};font-family:{F};font-size:14px;font-weight:700;line-height:1;'
                   f'padding:7px 9px;white-space:nowrap;">{esc(text)}</td>')
    return f'<table role="presentation" align="center" cellpadding="0" cellspacing="0"><tr>{"".join(tds)}</tr></table>'


def _tag(text):
    return (f'<table role="presentation" align="center" cellpadding="0" cellspacing="0" style="margin-top:10px;"><tr><td>'
            f'<div style="display:inline-block;background:{CHIP_BG};color:{CHIP_FG};font-family:{F};font-size:12.5px;'
            f'font-weight:700;line-height:1;padding:6px 8px;">{esc(text)}</div></td></tr></table>')


def _badge(n):
    return (f'<table role="presentation" align="center" cellpadding="0" cellspacing="0"><tr><td align="center" valign="middle" '
            f'style="width:30px;height:30px;background:{INK};border-radius:7px;font-family:{F};font-size:15px;font-weight:600;'
            f'line-height:30px;color:#FFFFFF;">{int(n)}</td></tr></table>')


def _sources(sources):
    links = "⁠·⁠".join(
        f'<a href="{esc(s["url"])}" style="color:{MUTED};text-decoration:underline;">{esc(s["name"])}</a>' for s in sources)
    date = esc(sources[-1].get("date", ""))
    return _div(f"font-size:12px;font-weight:400;line-height:1.5;color:{MUTED};margin-top:10px;", f"출처 · {links} {date}".rstrip())


def _utm(site, path, campaign, content):
    return f"{site}{path}?utm_source=edit_h&amp;utm_medium=email&amp;utm_campaign={campaign}&amp;utm_content={content}"


def _cover_title(hero):
    lines = hero.split("\n")
    first = f'<span style="font-weight:700;">{md(lines[0], "", HL_B)}</span>'
    rest = "".join(f'<br><span style="font-weight:400;">{md(x, "", HL_B)}</span>' for x in lines[1:])
    return first + rest


def _header(d):
    date_txt = d["date_obj"].strftime("%Y.%m.%d")
    chips = [(f"#{d['vol']}", True), (f"{d['weekday']}요일의", False), ("마케팅", False), ("브리프", False)]
    return f"""
<tr><td class="px" style="padding:30px 36px 0;">{_div(f"font-size:13px;font-weight:700;line-height:1;color:#5A5A5E;", "@edit.h.kr", True)}</td></tr>
<tr><td class="px" style="padding:26px 36px 0;">{_chips(chips)}
  <div class="h-cover" style="font-family:{F};font-size:31px;line-height:1.45;color:{INK};text-align:center;margin-top:18px;word-break:keep-all;letter-spacing:-0.5px;">{_cover_title(d['hero_title'])}</div>
  {_div(f"font-size:12.5px;font-weight:400;line-height:1.5;color:{MUTED};margin-top:14px;", f"VOL.{esc(d['vol'])} · {date_txt} {d['weekday']}요일 · 읽는 시간 {d['read_minutes']}분", True)}</td></tr>"""


def _lead_points(d):
    pts = d.get("lead_points") or [{"title": t["label"], "text": t["text"]} for t in d["three_lines"]]
    rows = []
    for i, p in enumerate(pts[:3], 1):
        rows.append(
            f'<tr><td valign="top" style="width:26px;padding:6px 0;"><div style="width:20px;height:20px;border-radius:10px;'
            f'background:{INK};color:#FFFFFF;text-align:center;font-family:{F};font-size:11px;font-weight:700;line-height:20px;">{i}</div></td>'
            f'<td valign="top" style="padding:6px 0;">'
            + _div(f"font-size:14.5px;font-weight:400;line-height:1.6;color:{BODY};",
                   f'<b style="font-weight:700;color:{INK};">{md(p["title"])}</b> — {md(p["text"])}')
            + "</td></tr>")
    return f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:16px;">{"".join(rows)}</table>'


def _letter(d):
    heading = _div(f"font-size:17px;font-weight:700;line-height:1.4;color:{INK};",
                   '오늘의 편지 <span style="color:#C4C4C4;font-weight:400;">|</span> '
                   f'<span style="font-size:12px;font-weight:500;color:{MUTED};">EDITOR&#39;S NOTE</span>')
    lead = _div(f"font-size:15.5px;font-weight:400;line-height:1.85;color:{BODY};margin-top:12px;", md(d["lead"], HL_B, HL_B))
    obs = _box(_div(f"font-size:14.5px;font-weight:400;line-height:1.7;color:{INK};",
                    f'<b style="font-weight:700;color:{INK};">H의 한 줄 관찰 ·</b> ' + md(d["observation"])), mt=16)
    return f'\n<tr><td class="px" style="padding:0 36px;">{heading}\n  {lead}\n  {_lead_points(d)}\n  {obs}</td></tr>'


def _hero(d):
    b = d["big_issue"]
    st = b["stat"]
    paras = "".join(_body(p, "15.5px", "1.85", 18 if i == 0 else 12) for i, p in enumerate(b["paragraphs"]))
    title = plain(d["title"])  # VOL.092: 빅이슈 제목 = 표지 제목(한 줄)
    check = ""
    if b.get("checklist"):
        items = "".join(_div(f"font-size:14px;line-height:1.7;color:{BODY};margin-top:6px;", "☐ " + md(c)) for c in b["checklist"])
        check = _box(_div(f"font-size:12.5px;font-weight:700;line-height:1.3;color:{INK};", "오늘 점검할 것") + items, mt=12)
    return f"""
<!-- 이슈 01 -->
<tr><td class="px" style="padding:0 36px;">{_badge(1)}
  {_div(f"font-size:22px;font-weight:700;line-height:1.45;color:{INK};margin-top:12px;", esc(title), True)}
  {_tag(f"01 · {b['tag']}")}
  {paras}
  <table role="presentation" align="center" cellpadding="0" cellspacing="0" style="margin-top:22px;"><tr><td class="stat" style="background:{HL};padding:4px 14px;font-family:{F};font-size:44px;font-weight:800;line-height:1.1;color:{INK};">{esc(st['value'])}<span style="font-size:24px;">{esc(st.get('unit', ''))}</span></td></tr></table>
  {_div(f"font-size:12.5px;font-weight:400;line-height:1.6;color:{MUTED};margin-top:8px;", esc(plain(st['caption'])), True)}
  {_box(_div(f"font-size:12.5px;font-weight:700;line-height:1.3;color:{INK};", "마케터의 한 줄") + _div(f"font-size:14.5px;font-weight:400;line-height:1.75;color:{BODY};margin-top:8px;", md(b['takeaway'], BOLD)), mt=18)}
  {check}
  {_sources(b['sources'])}</td></tr>"""


def _section_head(i, sec):
    return (f'<tr><td class="px" style="padding:30px 36px 0;">{_chips([(f"#{i}", True), (plain(sec["title"]), False)])}'
            + _div(f"font-size:12px;font-weight:400;line-height:1.5;color:{MUTED};margin-top:10px;", esc(sec["label"]), True)
            + "</td></tr>")


def _item(it):
    return f"""
<!-- 이슈 {it['no']} -->
<tr><td class="px" style="padding:30px 36px 0;">{_badge(it['no'])}
  {_div(f"font-size:19px;font-weight:700;line-height:1.45;color:{INK};margin-top:12px;", md(it['title']), True)}
  {_tag(f"{it['no']} · {it['tag']}")}
  {_body(it['body'])}
  {_box(_div(f"font-size:14.5px;font-weight:600;line-height:1.65;color:{INK};", md(it['takeaway'], BOLD)))}
  {_sources(it['sources'])}</td></tr>"""


def _briefs(d):
    if not d["briefs"]:
        return ""
    rows = []
    for b in d["briefs"]:
        src = esc(b.get("source", ""))
        if b.get("url"):
            src = f'<a href="{esc(b["url"])}" style="color:{MUTED};text-decoration:underline;">{src}</a>'
        rows.append(
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:12px;border-bottom:1px solid {RULE};">'
            f'<tr><td style="padding:0 0 12px;">'
            + _div(f"font-size:14.5px;font-weight:700;line-height:1.55;color:{INK};", md(b["title"]))
            + _div(f"font-size:14px;font-weight:400;line-height:1.7;color:{BODY};margin-top:2px;",
                   f'{md(b["body"])} <span style="color:{MUTED};">({src})</span>')
            + "</td></tr></table>")
    return (_divider() + f'<tr><td class="px" style="padding:0 36px;">'
            + _div(f"font-size:17px;font-weight:700;line-height:1.4;color:{INK};",
                   f'짧게 볼 것 <span style="color:#C4C4C4;font-weight:400;">|</span> <span style="font-size:12px;font-weight:500;color:{MUTED};">BRIEFS</span>')
            + "".join(rows) + "</td></tr>")


def _question(d):
    q = d["question"]
    closing = md(q.get("closing", "오늘도 EDIT H가 함께할게요. — 에디터 H 드림"))
    return (_divider(30) + f'<tr><td class="px" style="padding:0 36px;">'
            + _div(f"font-size:18px;font-weight:800;line-height:1;color:{BODY};", "Q", True)
            + _div(f"font-size:21px;font-weight:700;line-height:1.5;color:{INK};margin-top:10px;", md(q["text"], BOLD, HL_B), True)
            + _box(_div(f"font-size:14.5px;font-weight:400;line-height:1.7;color:{INK};", closing, True)
                   + _div(f"font-size:13px;font-weight:400;line-height:1.7;color:{BODY};margin-top:8px;",
                          "💬 여러분의 답이 궁금해요 — 이 메일에 답장으로 보내주시면, 다음 호 '독자의 한 줄'로 소개합니다.", True))
            + "</td></tr>")


# @edit.h.kr 프로필 마크(58px) — 로고의 '마크 전용'(안경만) 버전. 이 메일은 이미지를 하나도 쓰지 않으므로
# (차단·로딩 실패 방지) PNG 대신 도형으로 그린다. VOL.092 발행 뒤 바뀐 최신 프로필 사진과 같은 구성.
_LENS = ('<div style="display:inline-block;box-sizing:border-box;width:21px;height:21px;border-radius:50%;'
         'border:3px solid #0D0C0A;background:#F5F1E8;vertical-align:middle;">'
         '<div style="width:6px;height:6px;border-radius:50%;background:#0D0C0A;margin:4px auto 0;font-size:0;line-height:0;">&nbsp;</div></div>')
AVATAR_MARK = ('<table role="presentation" width="58" height="58" cellpadding="0" cellspacing="0" border="0" '
               'style="width:58px;height:58px;border-radius:50%;background:#FF5233;"><tr>'
               '<td align="center" valign="middle" style="font-size:0;line-height:0;">' + _LENS
               + '<div style="display:inline-block;width:5px;height:3px;background:#0D0C0A;vertical-align:middle;font-size:0;line-height:0;">&nbsp;</div>'
               + _LENS + '</td></tr></table>')

def _cta(d, site, campaign, n_cards):
    stat = lambda big, small: (  # noqa: E731
        f'<td valign="top">{_div(f"font-size:16px;font-weight:700;line-height:1.2;color:#1B1B1E;", big)}'
        f'{_div(f"font-size:11.5px;font-weight:400;line-height:1.3;color:#6B6E75;margin-top:2px;", small)}</td>')
    stats = stat(f"{len(d['all_items'])}개", "이슈 전문") + (stat(f"{n_cards}장", "카드뉴스") if n_cards else "") + stat(f"{int(d['vol'])}호", "누적 발행")
    links = f'<a href="{_utm(site, "/", campaign, "cta_archive")}" style="font-family:{F};font-size:14px;color:{MUTED};text-decoration:none;">지난 호 보기&gt;</a>'
    if n_cards:
        cards = _utm(site, f"/instagram/{d['date']}/", campaign, "cardnews")
        links = (f'<a href="{cards}" style="font-family:{F};font-size:14px;color:{MUTED};text-decoration:none;">카드뉴스 보기&gt;</a>'
                 f'<span style="color:#C4C4C4;"> &nbsp;|&nbsp; </span>' + links)
    return (_divider(30) + f'<tr><td class="px" style="padding:0 36px;">'
            + _div(f"font-size:19px;font-weight:700;line-height:1.45;color:{INK};",
                   f"매일 아침 {len(d['all_items'])}가지 마케팅 이슈를<br>한 번에 정리해 드려요!", True)
            + f"""<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:16px;background:#FFFFFF;border:1px solid {RULE};border-radius:18px;box-shadow:0 2px 6px rgba(0,0,0,.08);"><tr><td style="padding:18px 16px;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
    <td valign="middle" style="width:70px;">{AVATAR_MARK}</td>
    <td valign="middle" style="padding-left:12px;">{_div(f"font-size:15px;font-weight:500;line-height:1.2;color:{INK};", "edit.h.kr")}
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:8px;"><tr>{stats}</tr></table>
    </td>
  </tr></table>
</td></tr></table>
<div style="text-align:right;margin-top:10px;">{links}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:16px;"><tr><td align="center" style="background:{CHIP_FG};border-radius:10px;"><a href="{_utm(site, "/subscribe.html", campaign, "cta_subscribe")}" style="display:block;padding:14px 10px;font-family:{F};font-size:15px;font-weight:700;color:#FFFFFF;text-decoration:none;">EDIT H 구독하기</a></td></tr></table></td></tr>""")


def _footer(site, campaign):
    ig = f"https://instagram.com/edit.h.kr?utm_source=edit_h&amp;utm_medium=email&amp;utm_campaign={campaign}&amp;utm_content=footer_instagram"
    return (f'<tr><td class="px" style="padding:34px 36px 40px;">'
            + _div(f"font-size:12px;font-weight:400;line-height:1.9;color:{MUTED};",
                   f'EDIT H · 매일 아침, 마케터의 트렌드 한 입 · 인스타그램 <a href="{ig}" style="color:{MUTED};">@edit.h.kr</a><br>'
                   f'이 메일이 유용했다면 동료에게 전달해주세요. · <a href="{site}/unsubscribe.html?email=PLACEHOLDER" style="color:{MUTED};">수신거부</a>', True)
            + "</td></tr>")


def render(d, site, n_cards):
    campaign = "daily_" + d["date"].replace("-", "")
    title = plain(d["title"])
    body = [_header(d), _divider(), _letter(d), _divider(30), _hero(d)]
    for i, sec in enumerate(d["sections"], 1):
        body.append(_divider(0))
        body.append(_section_head(i, sec))
        body.extend(_item(it) for it in sec["items"])
    body += [_briefs(d), _question(d), _cta(d, site, campaign, n_cards), _footer(site, campaign)]
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="color-scheme" content="light">
<meta name="supported-color-schemes" content="light">
<meta property="og:title" content="[EDIT H] {esc(title)}">
<meta property="og:description" content="{esc(plain(d['subtitle']))}">
<meta property="og:image" content="{site}/instagram/{d['date']}/01_edit_h_{d['date']}_cover.png">
<title>[EDIT H] {esc(title)}</title>
<style>
@media (max-width:480px){{.px{{padding-left:20px!important;padding-right:20px!important;}}.h-cover{{font-size:26px!important;}}}}
</style>
</head>
<body style="margin:0;padding:0;background:{BOX};">
<!-- 프리헤더 -->
<div style="display:none;max-height:0;overflow:hidden;">{esc(plain(d['subtitle']))}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{BOX};">
<tr><td align="center" style="padding:0;">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#FFFFFF;table-layout:fixed;">
{''.join(body)}
</table>
</td></tr>
</table>
</body>
</html>
"""
