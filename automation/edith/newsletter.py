"""뉴스레터(이메일) HTML.

VOL.091(2026-09-15) 매거진 스타일(잉크 블랙·크림·레드)을 기본 골격으로 삼고 다음을 보강했다.
- 머리에 EDIT H 워드마크(이미지가 막혀도 alt 텍스트로 보임)
- 'IN THIS ISSUE' 목차: 10개를 7분 읽기 전에 훑을 수 있게
- 빅이슈를 목록에서 다시 반복하지 않음(01=빅이슈, 02~10=섹션)
- 출처를 원문 링크로(검증 가능성 = 신뢰)
- '오늘 점검할 것' 체크리스트(선택)와 카드뉴스 블록
- 작은 글씨의 레드·회색을 WCAG AA(4.5:1) 이상으로 조정
이메일 클라이언트 호환을 위해 레이아웃은 table + 인라인 스타일만 쓴다.
"""
from .common import esc, md, plain, send_time_ko

F = "'Pretendard','Apple SD Gothic Neo','Malgun Gothic',sans-serif"

INK = "#111008"
OUTER = "#EFEAE0"
PAPER = "#FFF4EE"
ALT = "#F6F3EC"
WHITE = "#FFFFFF"
ACC = "#C8300A"        # 밝은 바탕 위 작은 강조 글씨 (흰 바탕 5.4:1)
ACC_ON_DARK = "#FF5233"  # 어두운 바탕 위 강조 (5.9:1)
BTN = "#C8300A"
TEXT = "#292520"
BODY = "#4A443A"
MUTED = "#736A5C"      # 밝은 바탕 캡션 (4.8:1 이상)
MUTED_DARK = "#9A9183"  # 어두운 바탕 캡션 (6.1:1)
DARK_TEXT = "#DED7CB"
DARK_TITLE = "#FFF4EE"
DARK_PANEL = "#1C1912"
RULE = "#EAE5DA"
RULE_ALT = "#E2DACB"


def _div(style, inner):
    return f'<div style="font-family:{F};{style}word-break:keep-all;">{inner}</div>'


def _utm(site, path, campaign, content):
    sep = "&amp;" if "?" in path else "?"
    return f"{site}{path}{sep}utm_source=edit_h&amp;utm_medium=email&amp;utm_campaign={campaign}&amp;utm_content={content}"


def _sources(sources, color, link_color):
    links = "·".join(
        f'<a href="{esc(s["url"])}" style="color:{link_color};text-decoration:underline;">{esc(s["name"])}</a>'
        for s in sources
    )
    date = esc(sources[-1].get("date", ""))
    return _div(f"font-size:12.5px;line-height:1.6;color:{color};margin-top:10px;", f"출처 · {links} {date}")


def _header(d, site):
    date_txt = d["date_obj"].strftime("%Y.%m.%d")
    return f"""
<tr><td class="px" style="padding:26px 36px 22px;background:{INK};">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
<td valign="middle"><img src="{site}/assets/edit_h_wordmark_strike_cream.png" width="112" alt="EDIT H" style="display:block;border:0;width:112px;height:auto;font-family:{F};font-size:22px;font-weight:900;color:{DARK_TITLE};">
<div style="font-family:{F};font-size:11px;font-weight:800;letter-spacing:2px;color:{ACC_ON_DARK};margin-top:10px;">DAILY MARKETING BRIEF</div></td>
<td align="right" valign="top" style="font-family:{F};font-size:12px;line-height:1.6;color:{DARK_TEXT};">VOL.{esc(d['vol'])}<br>{date_txt} {d['weekday']}요일<br>읽는 시간 {d['read_minutes']}분</td>
</tr></table>
</td></tr>"""


def _lead(d):
    rows = "".join(
        _div(f"font-size:14.5px;line-height:1.75;color:{TEXT};margin-top:{10 if i == 0 else 6}px;",
             f'<b style="color:{ACC};">{esc(t["label"])}</b> · {md(t["text"], f"color:{INK};")}')
        for i, t in enumerate(d["three_lines"])
    )
    return f"""
<tr><td class="px" style="padding:26px 36px 6px;">
{_div(f"font-size:15.5px;line-height:1.8;color:{TEXT};", md(d['lead'], f"color:{ACC};", f"color:{ACC};font-weight:700;"))}
</td></tr>
<tr><td class="px" style="padding:20px 36px 0;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{ALT};border-radius:14px;"><tr><td style="padding:22px 24px;">
{_div(f"font-size:13px;font-weight:800;letter-spacing:1px;color:{MUTED};", "오늘의 세 줄")}
{rows}
</td></tr></table>
</td></tr>
<tr><td class="px" style="padding:22px 36px 0;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
<td width="4" style="background:{ACC};"></td>
<td style="padding:2px 0 2px 16px;">
{_div(f"font-size:13px;font-weight:800;letter-spacing:1px;color:{MUTED};", "H의 한 줄 관찰")}
{_div(f"font-size:15.5px;font-weight:700;line-height:1.6;color:{INK};margin-top:4px;", '"' + md(d['observation']) + '"')}
</td>
</tr></table>
</td></tr>"""


def _contents(d):
    rows = []
    for it in d["all_items"]:
        title = it.get("title", d["title"])
        rows.append(
            f'<tr><td valign="top" style="width:30px;padding:5px 0;font-family:{F};font-size:13px;font-weight:800;color:{ACC};">{it["no"]}</td>'
            f'<td valign="top" style="padding:5px 0;font-family:{F};font-size:14px;line-height:1.5;color:{TEXT};word-break:keep-all;">'
            f'{esc(plain(title))} <span style="color:{MUTED};font-size:12.5px;">· {esc(it["tag"])}</span></td></tr>'
        )
    return f"""
<tr><td class="px" style="padding:26px 36px 30px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-top:2px solid {INK};border-bottom:1px solid {RULE};"><tr><td style="padding:16px 0 12px;">
{_div(f"font-size:12px;font-weight:800;letter-spacing:2px;color:{MUTED};", "IN THIS ISSUE · 오늘의 10가지")}
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:8px;">{''.join(rows)}</table>
</td></tr></table>
</td></tr>"""


def _checklist(items, dark):
    if not items:
        return ""
    fg = DARK_TEXT if dark else TEXT
    lines = "".join(_div(f"font-size:14px;line-height:1.7;color:{fg};margin-top:6px;", "☐ " + md(x)) for x in items)
    return f"""
<tr><td class="px" style="padding:16px 36px 0;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border:1px solid {'#3A342A' if dark else RULE};border-radius:14px;"><tr><td style="padding:18px 22px;">
{_div(f"font-size:13px;font-weight:800;color:{ACC_ON_DARK if dark else ACC};", "✅ 오늘 점검할 것")}
{lines}
</td></tr></table>
</td></tr>"""


def _big_issue(d):
    b = d["big_issue"]
    paras = "".join(
        _div(f"font-size:15.5px;line-height:1.85;color:{DARK_TEXT};{'margin-top:14px;' if i else ''}",
             md(p, f"color:{DARK_TITLE};", f"color:{ACC_ON_DARK};font-weight:700;"))
        for i, p in enumerate(b["paragraphs"])
    )
    st = b["stat"]
    return f"""
<tr><td style="padding:34px 0 0;background:{INK};">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0">
<tr><td class="px" style="padding:0 36px;">
{_div(f"font-size:12px;font-weight:800;letter-spacing:2px;color:{ACC_ON_DARK};", f"01 · TODAY'S BIG ISSUE · {esc(b['tag'])}")}
<div class="hero-title" style="font-family:{F};font-size:30px;font-weight:900;line-height:1.35;color:{DARK_TITLE};margin-top:12px;word-break:keep-all;">{md(d['hero_title'], '', f'color:{ACC_ON_DARK};')}</div>
</td></tr>
<tr><td class="px" style="padding:20px 36px 0;">{paras}</td></tr>
<tr><td class="px" style="padding:30px 36px 0;">
<div class="stat" style="font-family:{F};font-size:64px;font-weight:900;color:{ACC_ON_DARK};line-height:1;">{esc(st['value'])}<span style="font-size:34px;">{esc(st.get('unit', ''))}</span></div>
{_div(f"font-size:13px;line-height:1.6;color:{MUTED_DARK};margin-top:8px;", esc(st['caption']))}
</td></tr>
<tr><td class="px" style="padding:28px 36px 0;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{DARK_PANEL};border-radius:14px;"><tr><td style="padding:22px 24px;">
{_div(f"font-size:13px;font-weight:800;color:{ACC_ON_DARK};", "🧭 마케터의 한 줄")}
{_div(f"font-size:14.5px;line-height:1.75;color:{DARK_TEXT};margin-top:8px;", md(b['takeaway'], f"color:{DARK_TITLE};"))}
</td></tr></table>
</td></tr>
{_checklist(b.get('checklist'), dark=True)}
<tr><td class="px" style="padding:6px 36px 32px;">{_sources(b['sources'], MUTED_DARK, MUTED_DARK)}</td></tr>
</table>
</td></tr>"""


def _item(it, rule, last):
    border = "" if last else f"border-bottom:1px solid {rule};"
    return f"""
  <!-- 이슈 {it['no']} -->
  <tr><td class="px" style="padding:{22 if it.get('_first') else 24}px 36px 0;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="{border}"><tr><td style="padding:0 0 {34 if last else 24}px;">
    {_div(f"font-size:13px;font-weight:800;color:{ACC};", f"{it['no']} · {esc(it['tag'])}")}
    {_div(f"font-size:19px;font-weight:800;line-height:1.45;color:{INK};margin-top:6px;", md(it['title']))}
    {_div(f"font-size:15px;line-height:1.75;color:{BODY};margin-top:10px;", md(it['body'], f"color:{ACC};", f"color:{ACC};font-weight:700;"))}
    {_div(f"font-size:14px;line-height:1.65;color:{INK};margin-top:10px;", f'<b style="color:{ACC};">→</b> ' + md(it['takeaway']))}
    {_sources(it['sources'], MUTED, MUTED)}
  </td></tr></table></td></tr>"""


def _sections(d):
    out = []
    for si, sec in enumerate(d["sections"], 1):
        bg = WHITE if si % 2 else ALT
        rule = RULE if si % 2 else RULE_ALT
        items = sec["items"]
        body = "".join(
            _item(dict(it, _first=(i == 0)), rule, last=(i == len(items) - 1)) for i, it in enumerate(items)
        )
        out.append(f"""
  <tr><td style="background:{bg};">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
  <tr><td class="px" style="padding:36px 36px 0;">
    {_div(f"font-size:12px;font-weight:800;letter-spacing:2px;color:{MUTED};", f"SECTION {si} · {esc(sec['label'])}")}
    {_div(f"font-size:22px;font-weight:900;color:{INK};margin-top:6px;", md(sec['title']))}
  </td></tr>
  {body}
  </table>
  </td></tr>""")
    return "".join(out)


def _cards_block(d, site, campaign, n_cards):
    if not n_cards:
        return ""
    date = d["date"]
    link = _utm(site, f"/instagram/{date}/", campaign, "cardnews")
    cover = f"{site}/instagram/{date}/01_edit_h_{date}_cover.png"
    return f"""
<tr><td style="background:{WHITE};"><table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td class="px" align="center" style="padding:34px 36px 34px;border-top:1px solid {RULE};">
{_div(f"font-size:12px;font-weight:800;letter-spacing:2px;color:{MUTED};text-align:center;", "CARD NEWS · 오늘의 카드뉴스")}
{_div(f"font-size:18px;font-weight:800;line-height:1.5;color:{INK};margin-top:6px;text-align:center;", f"바쁜 날엔, {n_cards}장으로 넘겨보세요")}
<a href="{link}" style="display:block;margin-top:16px;text-decoration:none;"><img src="{cover}" width="240" alt="EDIT H VOL.{esc(d['vol'])} 카드뉴스 표지 — {esc(plain(d['title']))}" style="display:block;margin:0 auto;border:0;width:240px;height:auto;border-radius:6px;box-shadow:0 2px 8px rgba(0,0,0,.12);font-family:{F};font-size:13px;color:{MUTED};"></a>
{_div(f"font-size:13.5px;font-weight:700;margin-top:14px;text-align:center;", f'<a href="{link}" style="color:{ACC};text-decoration:none;">카드뉴스 {n_cards}장 보기 →</a>')}
</td></tr></table></td></tr>"""


def _briefs(d):
    if not d["briefs"]:
        return ""
    rows = []
    for b in d["briefs"]:
        src = esc(b.get("source", ""))
        if b.get("url"):
            src = f'<a href="{esc(b["url"])}" style="color:{MUTED};text-decoration:underline;">{src}</a>'
        rows.append(
            f'<div style="margin-top:14px;"><b style="color:{INK};">· {md(b["title"])}</b><br>'
            f'<span style="color:{BODY};">{md(b["body"])}</span> <span style="color:{MUTED};">({src})</span></div>'
        )
    return f"""
<tr><td style="background:{ALT};"><table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td class="px" style="padding:30px 36px 34px;">
{_div(f"font-size:13px;font-weight:800;letter-spacing:1px;color:{MUTED};", "☕ 짧게 볼 것")}
{_div(f"font-size:14px;line-height:1.7;color:{TEXT};", ''.join(rows))}
</td></tr></table></td></tr>"""


def _closing(d, site, campaign):
    q = d["question"]
    sub = _utm(site, "/subscribe.html", campaign, "cta_subscribe")
    arc = _utm(site, "/", campaign, "cta_archive")
    ig = f"https://instagram.com/edit.h.kr?utm_source=edit_h&amp;utm_medium=email&amp;utm_campaign={campaign}&amp;utm_content=footer_instagram"
    return f"""
<tr><td style="padding:36px 0;background:{INK};"><table role="presentation" width="100%" cellpadding="0" cellspacing="0">
<tr><td class="px" align="center" style="padding:0 36px;">
{_div(f"font-size:13px;font-weight:800;letter-spacing:2px;color:{ACC_ON_DARK};text-align:center;", "오늘의 질문")}
{_div(f"font-size:26px;font-weight:900;line-height:1.4;color:{DARK_TITLE};margin-top:10px;text-align:center;", md(q['text'], '', f'color:{ACC_ON_DARK};'))}
{_div(f"font-size:14.5px;line-height:1.7;color:{DARK_TEXT};margin-top:16px;text-align:center;", md(q.get('closing', '오늘도 EDIT H가 함께할게요. — 에디터 H 드림')))}
{_div(f"font-size:13px;line-height:1.7;color:{MUTED_DARK};margin-top:18px;text-align:center;", "💬 여러분의 답이 궁금해요 — 이 메일에 답장으로 보내주시면, 다음 호 '독자의 한 줄'로 소개합니다.")}
</td></tr>
<tr><td align="center" style="padding:26px 36px 0;">
<table role="presentation" cellpadding="0" cellspacing="0"><tr>
<td style="border-radius:100px;background:{BTN};"><a href="{sub}" style="display:inline-block;padding:14px 30px;font-family:{F};font-size:15px;font-weight:800;color:#FFFFFF;text-decoration:none;">EDIT H 구독하기</a></td>
<td style="width:12px;"></td>
<td style="border:1px solid #4A443A;border-radius:100px;"><a href="{arc}" style="display:inline-block;padding:14px 30px;font-family:{F};font-size:15px;font-weight:800;color:#F1EBDF;text-decoration:none;">지난 호 보기</a></td>
</tr></table>
</td></tr>
<tr><td align="center" style="padding:30px 36px 36px;">
{_div(f"font-size:12px;line-height:1.9;color:{MUTED_DARK};text-align:center;", f'EDIT H · 매 영업일 {send_time_ko(d["send_time_kst"])}, 마케터의 트렌드 한 입 · 인스타그램 <a href="{ig}" style="color:{MUTED_DARK};">@edit.h.kr</a><br>이 메일이 유용했다면 동료에게 전달해주세요. · <a href="{site}/unsubscribe.html?email=PLACEHOLDER" style="color:{MUTED_DARK};">수신거부</a>')}
</td></tr>
</table>
</td></tr>"""


def render(d, site, n_cards):
    campaign = "daily_" + d["date"].replace("-", "")
    title = plain(d["title"])
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
@media (max-width:480px){{.px{{padding-left:22px!important;padding-right:22px!important;}}.hero-title{{font-size:26px!important;}}.stat{{font-size:54px!important;}}}}
</style>
</head>
<body style="margin:0;padding:0;background:{OUTER};">
<!-- 프리헤더 -->
<div style="display:none;max-height:0;overflow:hidden;">{esc(plain(d['subtitle']))}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{OUTER};">
<tr><td align="center">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:{PAPER};">
{_header(d, site)}
{_lead(d)}
{_contents(d)}
{_big_issue(d)}
{_sections(d)}
{_cards_block(d, site, campaign, n_cards)}
{_briefs(d)}
{_closing(d, site, campaign)}
</table>
</td></tr>
</table>
</body>
</html>
"""
