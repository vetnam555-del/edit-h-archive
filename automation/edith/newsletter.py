"""뉴스레터(이메일) HTML — 최신 양식(VOL.092, 2026-09-18) 기준. 형식 2(5가지 + 한 줄 뉴스, 2026-09-26~)는 아래 '형식 2' 참고.

@edit.h.kr 머리 → #호수·요일 칩 → 가운데 정렬 제목(굵게/보통 두 줄) → 오늘의 편지(세 줄 요약 + H의 한 줄 관찰)
→ 01 빅이슈(큰 숫자 박스 + '그래서 뭐가 달라져?') → #1~#N 섹션(번호 배지 · 태그 칩 · 회색 요약 박스)
→ 짧게 볼 것 → Q(오늘의 질문) → 프로필 카드·구독 버튼 → 푸터.
형식 2: 에디터 H 노트(안경 마크 + 오늘의 5가지 + H의 한 줄) → 01 H PICK 심층(무슨 일이야 → 큰 숫자 → 숫자로 보면
→ 왜 중요해 → 그래서 뭐가 달라져 → 알아두면 좋은 것) → 02~05 → 한 줄 뉴스 → (금) 투표 결과 → Q 또는 (월) 투표.
색: 글자 #282F38 · 본문 #555558 · 보조 #767676 · 칩 #FFDCCB/#B23A0F · 형광펜 #FFC9AD · 회색 박스 #F3F3F3.
VOL.092 대비 보강: 출처를 원문 링크로, '카드뉴스 보기' 링크 추가. 이메일 호환을 위해 table + 인라인 스타일만 쓴다.
"""
import json
import re

from .common import esc, load_config, md, plain, send_time_ko, send_time_on
from .content import BRIEFS_FROM, TODO_FROM, TODO_MAX, WEEK_FROM

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


def _align(align):
    """표 정렬 속성 — 왼쪽은 속성을 빼야 한다(align="left" 는 표를 띄워 다음 글이 옆으로 붙는다)."""
    return "" if align == "left" else f' align="{align}"'


def _chips(items, align="center"):
    """[(text, dark?)] → 칩 한 줄(기본 가운데 정렬, 11/19~ 새 배치는 왼쪽)."""
    tds = []
    for i, (text, dark) in enumerate(items):
        if i:
            tds.append('<td style="width:6px;font-size:0;line-height:0;">&nbsp;</td>')
        bg, fg = (DARK_CHIP, DARK_CHIP_FG) if dark else (CHIP_BG, CHIP_FG)
        tds.append(f'<td style="background:{bg};color:{fg};font-family:{F};font-size:14px;font-weight:700;line-height:1;'
                   f'padding:7px 9px;white-space:nowrap;">{esc(text)}</td>')
    return f'<table role="presentation"{_align(align)} cellpadding="0" cellspacing="0"><tr>{"".join(tds)}</tr></table>'


def _tag(text, align="center"):
    return (f'<table role="presentation"{_align(align)} cellpadding="0" cellspacing="0" style="margin-top:10px;"><tr><td>'
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
    chips = [(f"#{d['vol']}", True), (f"{d['weekday']}요일의", False), ("트렌드", False), ("브리프", False)]
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
        check = _box(_div(f"font-size:12.5px;font-weight:700;line-height:1.3;color:{INK};", "알아두면 좋은 것") + items, mt=12)
    return f"""
<!-- 이슈 01 -->
<tr><td class="px" style="padding:0 36px;">{_badge(1)}
  {_div(f"font-size:22px;font-weight:700;line-height:1.45;color:{INK};margin-top:12px;", esc(title), True)}
  {_tag(f"01 · {b['tag']}")}
  {paras}
  <table role="presentation" align="center" cellpadding="0" cellspacing="0" style="margin-top:22px;"><tr><td class="stat" style="background:{HL};padding:4px 14px;font-family:{F};font-size:44px;font-weight:800;line-height:1.1;color:{INK};">{esc(st['value'])}<span style="font-size:24px;">{esc(st.get('unit', ''))}</span></td></tr></table>
  {_div(f"font-size:12.5px;font-weight:400;line-height:1.6;color:{MUTED};margin-top:8px;", esc(plain(st['caption'])), True)}
  {_box(_div(f"font-size:12.5px;font-weight:700;line-height:1.3;color:{INK};", "그래서 뭐가 달라져?") + _div(f"font-size:14.5px;font-weight:400;line-height:1.75;color:{BODY};margin-top:8px;", md(b['takeaway'], BOLD)), mt=18)}
  {check}
  {_sources(b['sources'])}</td></tr>"""


# 2026-11-18 운영자 '뉴스레터·카드 개선할 부분 없어? → 먼저 보여 줘 → 최종 버전으로 개선해 줘'.
# Morning Brew·1440·TLDR·어피티 머니레터·뉴닉을 휴대폰 화면으로 보고(11/17) 고른 것만 넣었다 — 다섯 곳 모두 왼쪽 정렬·본문 16px 안팎,
# 1440 은 맨 위에 '처음 받아 보셨나요'(전달받은 사람) 한 줄, 어피티는 숫자 줄로 연다. 시안에서 뺀 것: 소식마다 '전달하기' 줄(행동 요청이 8번으로 늘어
# '하나만 고르라'는 근거와 어긋남)·메일 속 그림(Gmail 은 102KB 넘는 메일을 자른다). 이 날짜 호부터 — 지난 호를 다시 빌드하면 예전 그대로(기록).
LAYOUT_V3_FROM = "2026-11-19"


def _v3(d):
    return d.get("format") == 2 and str(d.get("date", "")) >= LAYOUT_V3_FROM


def _forward_box(d, site, campaign):
    """맨 위 한 상자 — 전달받은 사람에게 구독 길, 구독자에게 전달 길(1440 방식). 행동 요청은 여기 한 번만(소식마다 넣지 않는다)."""
    link = f"color:{CHIP_FG};font-weight:700;text-decoration:underline;"
    n = len(d["all_items"]) + len(d["briefs"])
    when = send_time_ko(d.get("send_time_kst") or send_time_on(d["date"])).replace("오전", "아침")
    sub = f'{_utm(site, "/subscribe.html", campaign, "top_subscribe")}&amp;ref=letter_top'
    return (f'<tr><td class="px" style="padding:22px 36px 0;">'
            + _box(_div(f"font-size:13.5px;font-weight:400;line-height:1.7;color:{BODY};",
                        f'<b style="font-weight:700;color:{INK};">처음 받아 보셨나요?</b> 매일 {when}, 2030이 알아야 할 소식 {n}가지를 무료로 보내 드려요. '
                        f'<a href="{sub}" style="{link}">구독하기</a><br>'
                        f'<b style="font-weight:700;color:{INK};">도움이 됐다면</b> 한 명에게만 전달해 주세요. '
                        f'<a href="{share_url(d, site)}" style="{link}">카톡·링크로 전달하기</a>'), pad="14px 18px", mt=0)
            + "</td></tr>")


def share_url(d, site):
    """11/19~ '전달하기·친구에게 추천하기' — 메일 쓰기(mailto) 대신 공유 화면(share.html): 휴대폰 공유 창(카카오톡·문자 등)과 링크 복사.
    2026-11-19 운영자 '요즘 누가 메일해, 카톡 공유나 이런 걸로 — 어려우면 주소 복사해서 복사하기 방식'. 메일 안에서는 스크립트가 돌지 않아
    복사 버튼·카카오 공유를 메일에 바로 둘 수 없다 → 웹 화면 하나로 보낸다. ref=share 는 그 화면이 붙인다(구독 경로 '공유')."""
    return f"{site}/share.html?d={d['date']}"


def _toc_number(it):
    """목차 오른쪽 숫자 — 카드 '5가지 한눈에' 장과 같은 값(큰 숫자, compare 카드는 바뀐 뒤 값)."""
    return it["compare"]["to"]["value"] if it.get("compare") else it.get("number") or ""


def _note_v3(d, site=None):
    """11/19~ — 숫자 목차(깊게 5: 제목 + 그 소식의 숫자, 짧게 5: 제목) → 오늘 챙길 것 → 에디터 H 노트(편지).
    'H의 한 줄'은 편지와 같은 말이라 메일에서는 뺐다(카드 '에디터 H 노트' 장에는 그대로). 첫 화면에 10가지가 다 보인다(10/15 운영자 '왜 5개냐')."""
    rows = []
    for i, it in enumerate(d["card_issues"], 1):
        num = _toc_number(it)
        rows.append(
            f'<tr><td valign="top" style="width:28px;padding:9px 0;border-bottom:1px solid {RULE};"><div style="width:20px;height:20px;border-radius:5px;'
            f'background:{INK};color:#FFFFFF;text-align:center;font-family:{F};font-size:11px;font-weight:700;line-height:20px;">{i}</div></td>'
            f'<td valign="top" style="padding:9px 8px 9px 2px;border-bottom:1px solid {RULE};">'
            + _div(f"font-size:15px;font-weight:700;line-height:1.45;color:{INK};", esc(plain(it["headline"]).replace(chr(10), " ")))
            + f'</td><td valign="top" align="right" style="padding:9px 0;border-bottom:1px solid {RULE};white-space:nowrap;">'
            + (_div(f"font-size:15px;font-weight:800;line-height:1.45;color:{INK};",
                    f'<span style="background-color:{HL};padding:0 3px;">{esc(num)}</span>') if num else "")
            + "</td></tr>")
    for n, b in enumerate(d["briefs"], len(rows) + 1):
        rows.append(
            f'<tr><td valign="top" style="width:28px;padding:5px 0;"><div style="width:20px;height:20px;text-align:center;font-family:{F};'
            f'font-size:11px;font-weight:800;line-height:20px;color:{CHIP_FG};">{n:02d}</div></td>'
            f'<td valign="top" colspan="2" style="padding:5px 0 5px 2px;">'
            + _div(f"font-size:14px;font-weight:400;line-height:1.55;color:{BODY};", esc(plain(b["title"])))
            + "</td></tr>")
    count = (f' <span style="font-size:12.5px;font-weight:400;color:{MUTED};">· 깊게 {len(d["card_issues"])} · 짧게 {len(d["briefs"])}</span>'
             if d["briefs"] else "")
    toc = (_div(f"font-size:17px;font-weight:700;line-height:1.4;color:{INK};", f'오늘의 {len(rows)}가지{count}')
           + f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:6px;">{"".join(rows)}</table>')
    head = (f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin-top:28px;"><tr><td valign="middle">{_face(d, site, 40)}</td>'
            f'<td valign="middle" style="padding-left:10px;">'
            + _div(f"font-size:17px;font-weight:700;line-height:1.3;color:{INK};", "에디터 H 노트")
            + '</td></tr></table>')
    lead = _div(f"font-size:16px;font-weight:400;line-height:1.8;color:{BODY};margin-top:10px;", md(d["lead"], HL_B, HL_B))
    return f'\n<tr><td class="px" style="padding:0 36px;">{toc}\n  {_todo(d)}{_week(d)}\n  {head}\n  {lead}</td></tr>'


def _item_v3(it):
    """11/19~ 02–05 소식 — [번호][태그] 칩 한 줄 + 왼쪽 정렬 제목 + 본문 16px(훑어 읽기 쉽게)."""
    chip = (f'<table role="presentation" cellpadding="0" cellspacing="0"><tr>'
            f'<td style="background:{INK};color:#FFFFFF;font-family:{F};font-size:12.5px;font-weight:700;line-height:1;padding:6px 8px;">{int(it["no"]):02d}</td>'
            f'<td style="width:4px;font-size:0;line-height:0;">&nbsp;</td>'
            f'<td style="background:{CHIP_BG};color:{CHIP_FG};font-family:{F};font-size:12.5px;font-weight:700;line-height:1;padding:6px 8px;">{esc(it["tag"])}</td>'
            f'</tr></table>')
    return f"""
<!-- 이슈 {it['no']} -->
<tr><td class="px" style="padding:30px 36px 0;">{chip}
  {_div(f"font-size:20px;font-weight:700;line-height:1.45;color:{INK};margin-top:12px;", md(it['title']))}
  {_body(it['body'], "16px", "1.75", 12)}
  {_box(_div(f"font-size:12.5px;font-weight:700;line-height:1.3;color:{INK};", "그래서 뭐가 달라져?")
        + _div(f"font-size:14.5px;font-weight:600;line-height:1.65;color:{INK};margin-top:8px;", md(it['takeaway'], BOLD)))}
  {_sources(it['sources'])}</td></tr>"""


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


def _briefs(d, heading="짧게 볼 것", start=None):
    """한 줄 뉴스. start 가 있으면(형식 2: 06) 메인 5가지 뒤로 번호를 이어 '오늘의 10개 주제'가 한눈에 보이게 한다."""
    if not d["briefs"]:
        return ""
    rows = []
    for n, b in enumerate(d["briefs"], start or 0):
        src = esc(b.get("source", ""))
        if b.get("url"):
            src = f'<a href="{esc(b["url"])}" style="color:{MUTED};text-decoration:underline;">{src}</a>'
        no = f'<span style="color:{CHIP_FG};font-weight:800;">{n:02d}</span>&nbsp; ' if start else ""
        rows.append(
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:12px;border-bottom:1px solid {RULE};">'
            f'<tr><td style="padding:0 0 12px;">'
            + _div(f"font-size:14.5px;font-weight:700;line-height:1.55;color:{INK};", no + md(b["title"]))
            + _div(f"font-size:14px;font-weight:400;line-height:1.7;color:{BODY};margin-top:2px;",
                   f'{md(b["body"])} <span style="color:{MUTED};">({src})</span>')
            + "</td></tr></table>")
    return (_divider() + f'<tr><td class="px" style="padding:0 36px;">'
            + _div(f"font-size:17px;font-weight:700;line-height:1.4;color:{INK};",
                   f'{heading} <span style="color:#C4C4C4;font-weight:400;">|</span> <span style="font-size:12px;font-weight:500;color:{MUTED};">BRIEFS</span>')
            + "".join(rows) + "</td></tr>")


def closing_lines(text):
    """맺음말을 문장마다 한 줄로 — 2026-11-17 운영자 '내일 아침 8시에 또 … 이 부분은 한 칸 띄워 내려와도 되잖아'.
    문장 끝(. ! ? …) 뒤 빈칸을 줄바꿈으로 바꾸되 '— 에디터 H 드림' 서명 앞에서는 바꾸지 않는다(마지막 문장과 같은 줄)."""
    return re.sub(r"(?<=[.!?…])[ \t]+(?=[^—\s])", "\n", str(text or "")).strip()


def _question(d):
    q = d["question"]
    closing = md(closing_lines(q.get("closing", "오늘도 EDIT H가 함께할게요. — 에디터 H 드림")))
    return (_divider(30) + f'<tr><td class="px" style="padding:0 36px;">'
            + _div(f"font-size:18px;font-weight:800;line-height:1;color:{BODY};", "Q", True)
            + _div(f"font-size:21px;font-weight:700;line-height:1.5;color:{INK};margin-top:10px;", md(q["text"], BOLD, HL_B), True)
            + _box(_div(f"font-size:14.5px;font-weight:400;line-height:1.7;color:{INK};", closing, True)
                   + _div(f"font-size:13px;font-weight:400;line-height:1.7;color:{BODY};margin-top:8px;",
                          "💬 여러분의 답이 궁금해요 — 이 메일에 답장으로 들려주세요.", True))
            + "</td></tr>")


# @edit.h.kr 프로필 마크(58px) — 로고의 '마크 전용'(안경만) 버전. 이 메일은 이미지를 하나도 쓰지 않으므로
# (차단·로딩 실패 방지) PNG 대신 도형으로 그린다. VOL.092 발행 뒤 바뀐 최신 프로필 사진과 같은 구성.
_LENS = ('<div style="display:inline-block;box-sizing:border-box;width:21px;height:21px;border-radius:50%;'
         'border:3px solid #0D0C0A;background:#F5F1E8;vertical-align:middle;">'
         '<div style="width:6px;height:6px;border-radius:50%;background:#0D0C0A;margin:4px auto 0;font-size:0;line-height:0;">&nbsp;</div></div>')
AVATAR_MARK = ('<table role="presentation" aria-hidden="true" width="58" height="58" cellpadding="0" cellspacing="0" border="0" '
               'style="width:58px;height:58px;border-radius:50%;background:#FF5233;"><tr>'
               '<td align="center" valign="middle" style="font-size:0;line-height:0;">' + _LENS
               + '<div style="display:inline-block;width:5px;height:3px;background:#0D0C0A;vertical-align:middle;font-size:0;line-height:0;">&nbsp;</div>'
               + _LENS + '</td></tr></table>')

# 2026-11-01 운영자 '내 돈·일·소비 같은 문구가 촌스럽다 … 프로필 이미지도 최신본으로'(automation/reviews/2026-11-01-copy.md).
# 이날 호부터 ① 프로필·노트 마크를 마스코트 얼굴(안경 + 미소, assets/mascot/profile.png)로 ② 바닥·추천 메일 문구를 새 한 줄
# '2030의 아침을 편집합니다'로(같은 날 운영자 '직장인보다 2030 마케팅·트렌드·경제 폭넓게'로 고침). 지난 호를 다시 빌드하면 예전 그대로 나온다(기록). 마크는 11/02 호까지 도형으로 그렸다(11/03 호부터 그림 — 아래 MARK_IMG_FROM).
BRAND_V2_FROM = "2026-11-01"
BRAND_LINE_V2 = "2030의 아침을 편집합니다"   # 11/01 운영자: 직장인보다 2030 마케팅·트렌드·경제 폭넓게
# 2026-11-22 운영자 '꼭 2030이 아니더라도 다 포괄적으로' → '바쁜 아침으로 가 줘'(계정 소개 릴스 3판 첫 화면 '바쁜 아침'과 같게).
# 11/23 호부터 바닥·추천 메일 한 줄과 '2030이 알아야 할' → '꼭 알아야 할'. 그 전 호는 다시 빌드해도 예전 그대로(기록).
BRAND_V3_FROM = "2026-11-23"
BRAND_LINE = "바쁜 아침을 편집합니다"
WHO_V2, WHO_V3 = "2030이 알아야 할", "꼭 알아야 할"


def brand_line(d):
    return BRAND_LINE if str(d.get("date", "")) >= BRAND_V3_FROM else BRAND_LINE_V2


def who_line(d):
    return WHO_V3 if str(d.get("date", "")) >= BRAND_V3_FROM else WHO_V2


def _v2(d):
    return str(d.get("date", "")) >= BRAND_V2_FROM


# 2026-11-02 운영자 '메일 뉴스레터 로고가 프로필 로고랑 다른 것 같다': 도형으로 그린 얼굴(_face_mark)은 눈이 작고 눈동자가 위로 쏠려
# 프로필(assets/mascot/profile.png)과 달라 보였고, box-sizing 을 지우는 메일에선 안경이 원 밖으로 삐져나온다.
# 이날 호부터 프로필과 같은 그림(assets/mascot/avatar-192.png — build_site_assets.py 가 profile.png 로 만든 동그라미)을 싣는다.
# 그림을 막는 메일에선 칸 배경의 주황 동그라미만 보인다(alt 없음 — 장식). 지난 호를 다시 빌드하면 예전 그대로(기록).
MARK_IMG_FROM = "2026-11-03"
MARK_IMG = "assets/mascot/avatar-192.png"


def _face(d, site, px):
    """프로필·노트 마크 — 11/03 호부터 프로필과 같은 그림, 11/01~11/02 호는 도형 얼굴, 그 전은 안경만."""
    if site and str(d.get("date", "")) >= MARK_IMG_FROM:
        return (f'<table role="presentation" aria-hidden="true" width="{px}" height="{px}" cellpadding="0" cellspacing="0" border="0" '
                f'style="width:{px}px;height:{px}px;border-radius:50%;background:#FF5233;"><tr>'
                f'<td align="center" valign="middle" bgcolor="#FF5233" style="font-size:0;line-height:0;border-radius:50%;">'
                f'<img src="{site}/{MARK_IMG}" width="{px}" height="{px}" alt="" '
                f'style="display:block;width:{px}px;height:{px}px;border:0;border-radius:50%;"></td></tr></table>')
    if _v2(d):
        return _face_mark(px)
    return AVATAR_MARK if px == 58 else _mini_avatar(px)


def _face_mark(px=58):
    """마스코트 얼굴 마크 — 주황 원 + 흰 렌즈 안경 + 미소(assets/mascot/profile.png 를 도형으로). 그림 차단에도 그대로 보인다."""
    k = px / 58
    lens = (f'<div style="display:inline-block;box-sizing:border-box;width:{round(20 * k)}px;height:{round(20 * k)}px;border-radius:50%;'
            f'border:{max(2, round(3 * k))}px solid #0D0C0A;background:#FFFFFF;vertical-align:middle;">'
            f'<div style="width:{max(3, round(7 * k))}px;height:{max(3, round(7 * k))}px;border-radius:50%;background:#0D0C0A;'
            f'margin:{max(2, round(4 * k))}px auto 0;font-size:0;line-height:0;">&nbsp;</div></div>')
    bridge = (f'<div style="display:inline-block;width:{max(3, round(4 * k))}px;height:{max(2, round(3 * k))}px;background:#0D0C0A;'
              'vertical-align:middle;font-size:0;line-height:0;">&nbsp;</div>')
    smile = (f'<div style="width:{max(6, round(12 * k))}px;height:{max(3, round(5 * k))}px;margin:{max(2, round(4 * k))}px auto 0;'
             f'border-bottom:{max(2, round(3 * k))}px solid #0D0C0A;border-radius:0 0 {round(12 * k)}px {round(12 * k)}px;'
             'font-size:0;line-height:0;">&nbsp;</div>')
    return (f'<table role="presentation" aria-hidden="true" width="{px}" height="{px}" cellpadding="0" cellspacing="0" border="0" '
            f'style="width:{px}px;height:{px}px;border-radius:50%;background:#FF5233;"><tr>'
            f'<td align="center" valign="middle" style="font-size:0;line-height:0;padding-top:{round(3 * k)}px;">'
            f'<div style="white-space:nowrap;">{lens}{bridge}{lens}</div>{smile}</td></tr></table>')


# ── 형식 2 ──────────────────────────────────────────────────────────────

def _mini_avatar(px=40):
    """AVATAR_MARK(58px)를 작게 — 에디터 H 노트 머리."""
    k = px / 58
    lens = (f'<div style="display:inline-block;box-sizing:border-box;width:{round(21 * k)}px;height:{round(21 * k)}px;border-radius:50%;'
            f'border:{max(2, round(3 * k))}px solid #0D0C0A;background:#F5F1E8;vertical-align:middle;">'
            f'<div style="width:{max(3, round(6 * k))}px;height:{max(3, round(6 * k))}px;border-radius:50%;background:#0D0C0A;'
            f'margin:{max(2, round(4 * k))}px auto 0;font-size:0;line-height:0;">&nbsp;</div></div>')
    return (f'<table role="presentation" aria-hidden="true" width="{px}" height="{px}" cellpadding="0" cellspacing="0" border="0" '
            f'style="width:{px}px;height:{px}px;border-radius:50%;background:#FF5233;"><tr>'
            f'<td align="center" valign="middle" style="font-size:0;line-height:0;">{lens}'
            f'<div style="display:inline-block;width:{max(3, round(5 * k))}px;height:{max(2, round(3 * k))}px;background:#0D0C0A;'
            f'vertical-align:middle;font-size:0;line-height:0;">&nbsp;</div>{lens}</td></tr></table>')


def _label(text, mt=22):
    """심층 안의 소제목 — '무슨 일이야?', '왜 중요해?' 등."""
    return _div(f"font-size:13px;font-weight:800;line-height:1.3;color:{CHIP_FG};margin-top:{mt}px;letter-spacing:.2px;", esc(text))


def todo_lines(d):
    """오늘 챙길 것 — 원고의 todo(최대 3줄), 없으면 H PICK·메인의 '그래서 뭐가 달라져'(takeaway) 앞 3개."""
    lines = [x for x in d.get("todo") or [] if str(x).strip()]
    if not lines:
        lines = [it["takeaway"] for it in d.get("all_items") or [] if it.get("takeaway")]
    return lines[:TODO_MAX]


def _todo(d):
    """메일 첫 화면의 '오늘 챙길 것'(2026-10-16~) — 10가지 중 오늘 할 일만 체크리스트로. 안장출근길엔 없는 우리 강점(10/15 운영자 선택).
    예비 호(지난 이야기 다시 보기)는 할 일이 지났을 수 있어 싣지 않는다."""
    if d.get("format") != 2 or d.get("rewind") or str(d.get("date", "")) < TODO_FROM:
        return ""
    lines = todo_lines(d)
    if not lines:
        return ""
    rows = "".join(_div(f"font-size:14.5px;font-weight:400;line-height:1.65;color:{INK};margin-top:6px;", "☐ " + md(x)) for x in lines)
    return _box(_div(f"font-size:12.5px;font-weight:700;line-height:1.3;color:{CHIP_FG};", "오늘 챙길 것") + rows, mt=16)


def _note(d, site=None):
    """에디터 H 노트 — 고정 코너. 안경 마크 + 1인칭 편지 + 오늘의 목록(10/16~ 짧게 읽는 소식까지 10가지) + H의 한 줄."""
    head = (f'<table role="presentation" cellpadding="0" cellspacing="0"><tr><td valign="middle">{_face(d, site, 40)}</td>'
            f'<td valign="middle" style="padding-left:10px;">'
            + _div(f"font-size:17px;font-weight:700;line-height:1.3;color:{INK};",
                   '에디터 H 노트 <span style="color:#C4C4C4;font-weight:400;">|</span> '
                   f'<span style="font-size:12px;font-weight:500;color:{MUTED};">EDITOR H&#39;S NOTE</span>')
            + '</td></tr></table>')
    lead = _div(f"font-size:15.5px;font-weight:400;line-height:1.85;color:{BODY};margin-top:12px;", md(d["lead"], HL_B, HL_B))
    rows = []
    for i, it in enumerate(d["card_issues"], 1):
        pick = (f' <span style="background:{DARK_CHIP};color:{DARK_CHIP_FG};font-size:10.5px;font-weight:700;padding:2px 5px;'
                f'vertical-align:1px;">H PICK</span>') if i == 1 else ""
        rows.append(
            f'<tr><td valign="top" style="width:26px;padding:6px 0;"><div style="width:20px;height:20px;border-radius:10px;'
            f'background:{INK};color:#FFFFFF;text-align:center;font-family:{F};font-size:11px;font-weight:700;line-height:20px;">{i}</div></td>'
            f'<td valign="top" style="padding:6px 0;">'
            + _div(f"font-size:14.5px;font-weight:400;line-height:1.6;color:{BODY};",
                   f'<b style="font-weight:700;color:{INK};">{esc(plain(it["headline"]).replace(chr(10), " "))}</b>{pick}')
            + "</td></tr>")
    short = str(d.get("date", "")) >= BRIEFS_FROM and d["briefs"]
    if short:   # 2026-10-16~: 목차에 짧게 읽는 소식(06~10)까지 — 첫 화면에서 '10가지'가 보이게(10/15 운영자: '왜 5개냐')
        for n, b in enumerate(d["briefs"], len(rows) + 1):
            rows.append(
                f'<tr><td valign="top" style="width:26px;padding:4px 0;"><div style="width:20px;height:20px;text-align:center;font-family:{F};'
                f'font-size:11px;font-weight:800;line-height:20px;color:{CHIP_FG};">{n:02d}</div></td>'
                f'<td valign="top" style="padding:4px 0;">'
                + _div(f"font-size:14px;font-weight:400;line-height:1.6;color:{BODY};", esc(plain(b["title"])))
                + "</td></tr>")
    label = (f"오늘의 {len(rows)}가지 <span style=\"font-weight:400;color:{MUTED};\">· 깊게 {len(d['card_issues'])} · 짧게 {len(d['briefs'])}</span>"
             if short else f"오늘의 {len(rows)}가지")
    today = (_div(f"font-size:12.5px;font-weight:700;line-height:1.3;color:{INK};margin-top:18px;", label)
             + f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:6px;">{"".join(rows)}</table>')
    if d["briefs"] and not short:   # 메인 5가지 + 한 줄 뉴스 = 오늘 다루는 주제 전부(2026-09-26 절충안)
        first, last = len(rows) + 1, len(rows) + len(d["briefs"])
        today += _div(f"font-size:13.5px;font-weight:400;line-height:1.6;color:{MUTED};margin-top:4px;padding-left:26px;",
                      f'+ {"짧게 읽는 소식" if str(d.get("date", "")) >= BRIEFS_FROM else "한 줄 뉴스"} {len(d["briefs"])}개({first:02d}–{last:02d})는 아래에서 짧게 볼 수 있어요.')
    obs = _box(_div(f"font-size:14.5px;font-weight:400;line-height:1.7;color:{INK};",
                    f'<b style="font-weight:700;color:{INK};">H의 한 줄 ·</b> ' + md(d["observation"])), mt=14)
    todo = _todo(d)   # 없는 호(10/15 이전·예비 호)는 빈 줄도 남기지 않는다 — 지난 호를 다시 빌드해도 발행본과 같게
    return f'\n<tr><td class="px" style="padding:0 36px;">{head}\n  {lead}\n  {todo + chr(10) + "  " if todo else ""}{today}\n  {obs}</td></tr>'


def _numbers(nums):
    cells = "".join(
        (f'<td style="width:8px;font-size:0;line-height:0;">&nbsp;</td>' if i else "")
        + f'<td valign="top" style="background:{BOX};border-radius:12px;padding:14px 8px;text-align:center;">'
        + _div(f"font-size:22px;font-weight:800;line-height:1.1;color:{INK};", esc(n["value"]), True)
        + _div(f"font-size:12px;font-weight:400;line-height:1.4;color:{MUTED};margin-top:6px;", esc(n["label"]), True) + "</td>"
        for i, n in enumerate(nums))
    return f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:10px;table-layout:fixed;"><tr>{cells}</tr></table>'


NL_CHART_FROM = "2026-11-22"   # 2026-11-22 운영자 '기존 매거진 형태로, 대신 시각화할 수 있게 그래프 추가' — 이 날짜 호부터


# 2026-11-22 운영자 '1~4번 오늘부터 — 대신 처음에 「처음 받아 보셨나요?·도움이 됐다면」은 첫 단에서 방해하니 빼 줘'.
# 경쟁 비교(뉴닉·어피티 머니레터·순살브리핑·Morning Brew 같은 날 호, automation/reviews/2026-11-22-newsletter-benchmark.md)에서 고른 칸:
# 맨 위 시세판(fetch_market.py → automation/market/{날짜}.json) · 맨 끝 '좋았어요/아쉬웠어요'(메일로 세는 A 방식 — 운영자 선택).
# 구독·전달 길은 맨 아래 추천·구독 버튼에 그대로 있다. 이 날짜 호부터 — 지난 호를 다시 빌드하면 예전 그대로(기록).
NL_PLUS_FROM = "2026-11-22"
UP, DOWN = "#D93A2B", "#2F6BD8"   # 한국식 — 오르면 빨강, 내리면 파랑


def _plus(d):
    return str(d.get("date", "")) >= NL_PLUS_FROM


def _market_board(m):
    """제목 아래 시세 4칸(2×2) — 이름 · 종가 · 등락률. 기준 날짜와 출처를 아래 한 줄에."""
    def cell(r):
        pct = float(r["pct"])
        color, arrow = (DOWN, "▼") if pct < 0 else (UP, "▲") if pct > 0 else (MUTED, "")
        return (f'<td width="50%" valign="top" style="padding:10px 12px;">'
                + _div(f"font-size:12px;font-weight:500;line-height:1.3;color:{MUTED};", esc(r["name"]))
                + _div(f"font-size:17px;font-weight:800;line-height:1.35;color:{INK};margin-top:3px;",
                       f'{esc(r["value"])} <span style="font-size:13px;font-weight:700;color:{color};white-space:nowrap;">{arrow}{abs(pct):.2f}%</span>')
                + "</td>")
    r = m["rows"]
    grid = (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
            f'<tr>{cell(r[0])}{cell(r[1])}</tr>'
            f'<tr><td colspan="2" style="padding:0 12px;"><div style="border-top:1px solid #E4E4E4;font-size:0;line-height:0;">&nbsp;</div></td></tr>'
            f'<tr>{cell(r[2])}{cell(r[3])}</tr></table>')
    return (f'<tr><td class="px" style="padding:18px 36px 0;">'
            + _box(grid, pad="6px 4px", mt=0)
            + _div(f"font-size:11.5px;font-weight:400;line-height:1.5;color:{MUTED};margin-top:6px;", esc(m["asof"]), True)
            + "</td></tr>")


def rate_links(site, date):
    """평가 버튼 주소. 웹(아카이브)에서는 감사 화면(rate.html)으로 가고, 메일로 나갈 때 send_newsletter.py 가
    'mailto:발신 주소?subject=[EDIT H RATE {날짜}] 좋았어요' 로 바꾼다(투표와 같은 방식 — tally_poll.py 가 센다)."""
    return [f"{site}/rate.html?d={date}&amp;v={v}" for v in ("good", "meh")]


def _rate_block(d, site):
    good, meh = rate_links(site, d["date"])

    def btn(href, text, bg):
        return (f'<td width="50%" style="padding:0 4px;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>'
                f'<td align="center" style="background:{bg};border:1.5px solid {INK};border-radius:12px;">'
                f'<a href="{href}" style="display:block;padding:12px 8px;font-family:{F};font-size:15px;font-weight:700;color:{INK};'
                f'text-decoration:none;">{text}</a></td></tr></table></td>')
    return (f'<tr><td class="px" style="padding:26px 36px 0;">'
            + _div(f"font-size:15px;font-weight:700;line-height:1.4;color:{INK};", "오늘 레터, 어땠어요?", True)
            + f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:12px;"><tr>'
            + btn(good, "좋았어요", HL) + btn(meh, "아쉬웠어요", "#FFFFFF") + "</tr></table>"
            + _div(f"font-size:12px;font-weight:400;line-height:1.6;color:{MUTED};margin-top:8px;",
                   "누르면 평가 메일이 열려요 — 보내기만 누르면 끝." if str(d.get("date", "")) >= H_VOICE_FROM   # 11/23~ 답장 부탁은 H 질문 한 곳만
                   else "누르면 평가 메일이 열려요 — 보내기만 누르면 끝. 무엇이 좋았는지·아쉬웠는지 한 줄 덧붙여 주시면 다음 호에 반영할게요.", True)
            + "</td></tr>")


def _week(d):
    """월요일 '이번 주 일정'(2026-11-23~) — 날짜가 정해진 일 2~4줄. '오늘 챙길 것'(할 일) 바로 아래, 달력 몫."""
    week = d.get("week_ahead") or []
    if not week or str(d.get("date", "")) < WEEK_FROM:
        return ""
    rows = "".join(
        f'<tr><td valign="top" style="width:74px;padding:5px 0;white-space:nowrap;">'
        + _div(f"font-size:13.5px;font-weight:800;line-height:1.6;color:{CHIP_FG};", esc(w["day"]))
        + f'</td><td valign="top" style="padding:5px 0;">'
        + _div(f"font-size:14.5px;font-weight:400;line-height:1.6;color:{INK};", md(w["text"])) + "</td></tr>"
        for w in week)
    return _box(_div(f"font-size:12.5px;font-weight:700;line-height:1.3;color:{CHIP_FG};", "이번 주 일정")
                + f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:4px;">{rows}</table>', mt=10)


# 2026-11-22 운영자 '5번(H 말투) 진행' — 뉴닉 고슴이·순살·트렌드어워드 문문처럼 '누가 말하는지 보이게'. 디자인은 그대로,
# 맨 끝 질문·맺음말을 마스코트 H 얼굴 + 말풍선으로(말투 규칙은 RUNBOOK '에디터 H 말투'). 이 날짜 호부터 — 지난 호는 그대로.
H_VOICE_FROM = "2026-11-22"   # 운영자 11/22 새벽 '오늘부터 적용해 줘'(처음엔 11/23 로 잡았다)


def _bubble(d, site, label, inner):
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:14px;"><tr>'
            f'<td valign="top" style="width:52px;padding-top:2px;">{_face(d, site, 44)}</td>'
            f'<td valign="top"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{BOX};'
            f'border-radius:4px 16px 16px 16px;"><tr><td style="padding:12px 16px 14px;">'
            + _div(f"font-size:12px;font-weight:700;line-height:1.3;color:{CHIP_FG};", label) + inner
            + "</td></tr></table></td></tr></table>")


# 2026-11-26 운영자 '이 부분 마음에 안 들어, 뭔가 중복으로 들어가는 느낌' — 맨 끝(질문 → 맺음말 → 평가 → 숫자 카드 → 추천 → 구독 → 꼬리말)에
# H 얼굴이 세 번(질문·맺음말·숫자 카드), '전달해 주세요'가 두 번(추천 버튼·꼬리말), 숫자 카드는 맨 위와 같은 말(VOL·목차 개수)에 카드 수는 틀렸다
# (v4 9장인데 소식 장 5만 세어 '5장'). 이 날짜 호부터: H 말풍선 하나(얼굴·이름 한 번 — 질문 + 답장 안내 + 맺음말), 숫자 카드 빼고 링크 한 줄,
# 꼬리말의 '동료에게 전달' 문장 뺌. 지난 호는 그대로(기록).
TAIL_V2_FROM = "2026-11-27"


def _tail_v2(d):
    return str(d.get("date", "")) >= TAIL_V2_FROM


def _question_h(d, site):
    q = d["question"]
    closing = re.sub(r"\s*[—-]+\s*에디터 H 드림\s*$", "", closing_lines(q.get("closing", "오늘도 EDIT H가 함께할게요.")))
    if _tail_v2(d):   # 말풍선 하나: 질문(크게) → 답장 안내 → 가는 줄 → 맺음말
        one = _bubble(d, site, "에디터 H",
                      _div(f"font-size:18px;font-weight:700;line-height:1.5;color:{INK};margin-top:6px;", md(q["text"], BOLD, HL_B))
                      + _div(f"font-size:13px;font-weight:400;line-height:1.6;color:{BODY};margin-top:6px;", "이 메일에 답장으로 들려주세요.")
                      + f'<div style="border-top:1px solid {RULE};margin:14px 0 12px;font-size:0;line-height:0;">&nbsp;</div>'
                      + _div(f"font-size:15px;font-weight:400;line-height:1.7;color:{INK};", md(closing)))
        return _divider(30) + f'<tr><td class="px" style="padding:0 36px;">{one}</td></tr>'
    ask = _bubble(d, site, "에디터 H의 질문",
                  _div(f"font-size:18px;font-weight:700;line-height:1.5;color:{INK};margin-top:6px;", md(q["text"], BOLD, HL_B))
                  + _div(f"font-size:13px;font-weight:400;line-height:1.6;color:{BODY};margin-top:8px;", "이 메일에 답장으로 들려주세요."))
    bye = _bubble(d, site, "에디터 H", _div(f"font-size:15px;font-weight:400;line-height:1.7;color:{INK};margin-top:6px;", md(closing)))
    return _divider(30) + f'<tr><td class="px" style="padding:0 36px;">{ask}{bye}</td></tr>'


def repeated_numbers(d):
    """같은 숫자가 시세판·큰 숫자·'숫자로 보면'·그래프에 거듭 나오는지(11/22 운영자 '중복되는 건 없지? 소비자 입장에서도') — 빌드 경고용.
    [(그래프 칸 이름, 숫자, 이미 나온 곳)]. 그래프는 '새 비교'여야 한다 — 같은 숫자를 막대로 한 번 더 그리면 읽는 사람은 같은 말을 네 번 본다."""
    def norm(v):
        t = re.sub(r"[^0-9.]", "", str(v))
        try:
            return f"{float(t):g}" if t else ""
        except ValueError:
            return ""
    seen = {}
    b = d.get("big_issue") or {}
    st = b.get("stat") or {}
    if norm(st.get("value")):
        seen.setdefault(norm(st.get("value")), "큰 숫자")
    for n in b.get("numbers") or []:
        if norm(n.get("value")):
            seen.setdefault(norm(n.get("value")), "숫자로 보면")
    for r in (d.get("market") or {}).get("rows") or []:
        seen.setdefault(norm(r.get("value")), "시세판")
        seen.setdefault(norm(abs(float(r.get("pct", 0)))), "시세판")
    ch = ((d.get("cards") or {}).get("deep") or {}).get("chart") or {}
    out = []
    for p in ch.get("points") or []:
        k = norm(p.get("text") or p.get("value"))
        if k and k in seen:
            out.append((p.get("label"), k, seen[k]))
    return out


def todo_repeats(d):
    """'오늘 챙길 것' 줄이 같은 호의 '그래서 뭐가 달라져?'와 거의 같은 문장인지 — 빌드 경고용(운영자 '중복 없지?').
    11/21 호: todo '월요일 장 전, 내 계좌 속 반도체·미국 기술주 비중 보기' ≈ H PICK 결론. 위아래로 같은 말을 두 번 읽게 된다."""
    import difflib
    def key(t):
        return re.sub(r"[^가-힣0-9A-Za-z]", "", plain(str(t or "")))
    outs = [key(it.get("takeaway")) for it in d.get("all_items") or [] if it.get("takeaway")]
    hits = []
    for line in d.get("todo") or []:
        k = key(line)
        if not k:
            continue
        for t in outs:
            if k in t or difflib.SequenceMatcher(None, k, t[:len(k) + 10]).ratio() >= 0.6:
                hits.append(str(line))
                break
    return hits


def _quiz_block(d, site):
    """금요일 '이번 주 퀴즈'(2026-11-27~) — 메일엔 1번 문제와 보기 3개 버튼, 누르면 웹 퀴즈 화면(quiz/{날짜}.html)에서 정답·풀이·2~5번."""
    from . import quiz as quiz_mod
    q = d["quiz"]["questions"][0]
    url = quiz_mod.page_url(site, d["date"])

    def opt(i, text):
        return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:8px;"><tr>'
                f'<td style="background:#FFFFFF;border:1.5px solid {INK};border-radius:12px;">'
                f'<a href="{url}?q=1&amp;a={i}" style="display:block;padding:13px 16px;font-family:{F};font-size:15px;font-weight:700;'
                f'color:{INK};text-decoration:none;">{"①②③"[i - 1]} &nbsp;{esc(plain(text))}</a></td></tr></table>')
    day = q["date"]
    return (_divider(30) + f'<tr><td class="px" style="padding:0 36px;">'
            + _chips([("금요일 퀴즈", True), (f"이번 주 {len(d['quiz']['questions'])}문제", False)], "left")
            + _div(f"font-size:20px;font-weight:700;line-height:1.45;color:{INK};margin-top:14px;", "이번 주 소식, 얼마나 기억나요?")
            + _box(_div(f"font-size:12.5px;font-weight:700;line-height:1.3;color:{CHIP_FG};", f"Q1 · {int(day[5:7])}/{int(day[8:])} 호")
                   + _div(f"font-size:16.5px;font-weight:700;line-height:1.5;color:{INK};margin-top:6px;", esc(plain(q["q"])))
                   + "".join(opt(i, t) for i, t in enumerate(q["options"], 1)), pad="16px 16px 18px", mt=14)
            + _div(f"font-size:12.5px;font-weight:400;line-height:1.7;color:{MUTED};margin-top:10px;",
                   "누르면 정답과 풀이가 바로 나오고, 나머지 문제를 이어서 풀 수 있어요.", True)
            + "</td></tr>")


def _chart_block(ch):
    """H PICK '숫자로 보면' 아래 막대 그래프 — 카드의 cards.deep.chart 와 같은 칸(같은 잣대 확인된 숫자 3~6개)을 메일에서도 그린다.
    매거진 색 그대로: 막대 바탕 BOX, 막대 HL, 강조 칸(highlight, 기본 마지막)만 진한 주황. 메일에서 안전한 표와 div 너비로."""
    pts = ch["points"]
    top = max(float(p["value"]) for p in pts) or 1
    hi = ch.get("highlight", len(pts) - 1)
    unit = str(ch.get("unit") or "")
    rows = "".join(
        f'<tr><td valign="middle" style="width:72px;padding:6px 8px 6px 0;font-family:{F};font-size:13px;line-height:1.3;color:{INK if i == hi else MUTED};'
        f'font-weight:{700 if i == hi else 400};word-break:keep-all;">{esc(p["label"])}</td>'
        f'<td valign="middle" style="padding:6px 0;"><div style="background:{BOX};border-radius:6px;height:14px;font-size:0;line-height:0;">'
        f'<div style="background:{DARK_CHIP_FG if i == hi else HL};border-radius:6px;height:14px;width:{max(2, round(float(p["value"]) / top * 100))}%;font-size:0;line-height:0;">&nbsp;</div></div></td>'
        f'<td valign="middle" align="right" style="width:64px;padding:6px 0 6px 8px;font-family:{F};font-size:13px;font-weight:{800 if i == hi else 600};color:{INK};white-space:nowrap;">'
        f'{esc(p.get("text") or (format(p["value"], "g") + unit))}</td></tr>'
        for i, p in enumerate(pts))
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:12px;background:#FFFFFF;border:1px solid {RULE};border-radius:12px;">'
            f'<tr><td style="padding:16px 16px 12px;">'
            + _div(f"font-size:13.5px;font-weight:700;line-height:1.4;color:{INK};", esc(plain(ch["title"])))
            + f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:8px;">{rows}</table>'
            + _div(f"font-size:11.5px;font-weight:400;line-height:1.5;color:{MUTED};margin-top:8px;", "출처 · " + esc(ch.get("source", "")))
            + "</td></tr></table>")


def _fresh_checklist(b):
    """11/19~ '알아두면 좋은 것'에서 위(큰 숫자·숫자로 보면)에 이미 나온 숫자만 되풀이하는 줄을 뺀다 — 2026-11-18 운영자 분석:
    H PICK 에서 '1158억 달러·103%'가 본문·큰 숫자·숫자로 보면·알아두면 좋은 것에 네 번 나왔다. 숫자가 없는 줄(일정·대상·조건)과
    새 숫자가 하나라도 있는 줄은 남긴다. 숫자 비교는 숫자 2곳 대조와 같은 읽기(twosource.numbers — 값·단위)."""
    from .twosource import DATE_UNITS, numbers
    shown = set()
    st = b.get("stat") or {}
    for t in [f"{st.get('value', '')}{st.get('unit', '')}"] + [str(n.get("value", "")) for n in b.get("numbers") or []]:
        shown |= {(round(n[1], 6), n[2]) for n in numbers(t)}
    keep = []
    for c in b.get("checklist") or []:
        nums = {(round(n[1], 6), n[2]) for n in numbers(str(c)) if n[2] not in DATE_UNITS}   # '10월 말 기준'·'19일' 같은 날짜는 새 숫자로 치지 않는다
        if not nums or not nums <= shown:
            keep.append(c)
    return keep


def _pick(d):
    """01 H PICK 심층 — 한 이슈를 '무슨 일 → 숫자 → 왜 중요 → 그래서'로 깊게."""
    b = d["big_issue"]
    st = b["stat"]
    chart = ((d.get("cards") or {}).get("deep") or {}).get("chart") if str(d.get("date", "")) >= NL_CHART_FROM else None
    v3 = _v3(d)
    size, lh, align = ("16px", "1.8", "left") if v3 else ("15.5px", "1.85", "center")
    paras = "".join(_body(p, size, lh, 8 if i == 0 else 12) for i, p in enumerate(b["paragraphs"]))
    why = "".join(_body(p, size, lh, 8 if i == 0 else 12) for i, p in enumerate(b["why"]))
    check = ""
    checklist = _fresh_checklist(b) if v3 else (b.get("checklist") or [])
    if checklist:
        items = "".join(_div(f"font-size:14px;line-height:1.7;color:{BODY};margin-top:6px;", "☐ " + md(c)) for c in checklist)
        check = _box(_div(f"font-size:12.5px;font-weight:700;line-height:1.3;color:{INK};", "알아두면 좋은 것") + items, mt=12)
    return f"""
<!-- 01 H PICK 심층 -->
<tr><td class="px" style="padding:0 36px;">{_chips([("H PICK", True), ((d.get("series") or {}).get("label") or "오늘의 심층", False)], align)}
  {_div(f"font-size:23px;font-weight:700;line-height:1.45;color:{INK};margin-top:14px;", esc(plain(d['big_issue'].get('title') or d['title'])), not v3)}
  {_tag(f"01 · {b['tag']}", align)}
  {_label("무슨 일이야?")}
  {paras}
  <table role="presentation" align="center" cellpadding="0" cellspacing="0" style="margin-top:22px;"><tr><td class="stat" style="background:{HL};padding:4px 14px;font-family:{F};font-size:44px;font-weight:800;line-height:1.1;color:{INK};">{esc(st['value'])}<span style="font-size:24px;">{esc(st.get('unit', ''))}</span></td></tr></table>
  {_div(f"font-size:12.5px;font-weight:400;line-height:1.6;color:{MUTED};margin-top:8px;", esc(plain(st['caption'])), True)}
  {_label("숫자로 보면")}
  {_numbers(b["numbers"])}
  {_chart_block(chart) if chart else ""}
  {_label("왜 중요해?")}
  {why}
  {_box(_div(f"font-size:12.5px;font-weight:700;line-height:1.3;color:{INK};", "그래서 뭐가 달라져?") + _div(f"font-size:14.5px;font-weight:400;line-height:1.75;color:{BODY};margin-top:8px;", md(b['takeaway'], BOLD)), mt=20)}
  {check}
  {_sources(b['sources'])}</td></tr>"""


def _poll_links(site, poll):
    """투표 버튼 주소. 웹(아카이브)에서는 투표 안내 페이지로 가고, 메일로 나갈 때 send_newsletter.py 가
    'mailto:발신 주소?subject=[EDIT H 투표 {id}] A' 로 바꾼다(주소를 공개 저장소에 두지 않으려고)."""
    return [f"{site}/poll.html?id={poll['id']}&amp;v={v}" for v in "AB"]


def _poll_block(d, site):
    q = d["poll"]
    closing = md(closing_lines(d["question"].get("closing", "오늘도 EDIT H가 함께할게요. — 에디터 H 드림")))
    btn = lambda href, key, text: (  # noqa: E731
        f'<td width="50%" style="padding:0 4px;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
        f'<tr><td align="center" style="background:{"#FFFFFF" if key == "A" else HL};border:2px solid {INK};border-radius:12px;">'
        f'<a href="{href}" style="display:block;padding:14px 8px;font-family:{F};font-size:15px;font-weight:700;color:{INK};'
        f'text-decoration:none;">{key} · {esc(text)}</a></td></tr></table></td>')
    a, b = _poll_links(site, q)
    return (_divider(30) + f'<tr><td class="px" style="padding:0 36px;">'
            + _chips([("이번 주 투표", True), ("금요일에 결과 공개", False)])
            + _div(f"font-size:21px;font-weight:700;line-height:1.5;color:{INK};margin-top:14px;", md(q["question"], BOLD, HL_B), True)
            + f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:16px;"><tr>'
            + btn(a, "A", q["options"][0]) + btn(b, "B", q["options"][1]) + "</tr></table>"
            + _div(f"font-size:12.5px;font-weight:400;line-height:1.7;color:{MUTED};margin-top:10px;",
                   "버튼을 누르면 투표 메일이 열려요 — 보내기만 누르면 끝. 이 메일에 A 또는 B 로 답장해도 되고, "
                   "인스타그램 @edit.h.kr 게시물 댓글(A/B)도 함께 세요. 한 사람당 한 표, 이름·주소는 저장하지 않아요.", True)
            + _box(_div(f"font-size:14.5px;font-weight:400;line-height:1.7;color:{INK};", closing, True), mt=16)
            + "</td></tr>")


def _poll_result(d):
    r = d["poll_result"]
    t = r["tally"]
    bars = []
    lead = max(t["votes"], key=lambda k: t["votes"][k])
    for i, key in enumerate("AB"):
        pct = t["pct"].get(key, 0)
        fill = HL if key == lead else "#E4E4E4"
        bars.append(
            _div(f"font-size:14px;font-weight:700;line-height:1.4;color:{INK};margin-top:{12 if i else 14}px;",
                 f"{key} · {esc(t['options'][i])} <span style=\"float:right;\">{pct}%</span>")
            + f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:6px;background:{BOX};border-radius:8px;">'
            f'<tr><td style="width:{max(pct, 2)}%;height:14px;background:{fill};border-radius:8px;font-size:0;line-height:0;">&nbsp;</td>'
            f'<td style="font-size:0;line-height:0;">&nbsp;</td></tr></table>')
    src = f"{t['total']}명 참여 · 메일 {t['channels'].get('email', 0)} · 인스타 {t['channels'].get('instagram', 0)}"
    return (_divider(30) + f'<tr><td class="px" style="padding:0 36px;">'
            + _chips([("투표 결과", True), (f"{r['id'][5:].replace('-', '/')} 투표", False)])
            + _div(f"font-size:19px;font-weight:700;line-height:1.5;color:{INK};margin-top:14px;", md(t["question"], BOLD), True)
            + "".join(bars)
            + _div(f"font-size:12px;font-weight:400;line-height:1.5;color:{MUTED};margin-top:10px;", esc(src), True)
            + (_box(_div(f"font-size:14.5px;font-weight:400;line-height:1.7;color:{INK};",
                         f'<b style="font-weight:700;">에디터 H ·</b> ' + md(r["comment"])), mt=14) if r.get("comment") else "")
            + "</td></tr>")


def _share_mailto(d, site):
    """'친구에게 추천하기' — 받는 사람 칸만 비운 메일을 연다. 오늘 호 웹 주소 + 구독 링크(ref=share 로 추천 경로를 센다).
    구독자 개인 링크(수신 거부 등)는 넣지 않는다."""
    from urllib.parse import quote
    n = len(d["all_items"]) + (len(d["briefs"]) if d.get("format") == 2 else 0)
    when = send_time_ko(d.get('send_time_kst') or send_time_on(d['date'])).replace('오전', '아침')   # 그 호의 발송 시각(다시 빌드해도 그대로)
    if _v2(d):
        subject = f"{brand_line(d)} — EDIT H 추천해요"
        pitch = f"매일 {when}, 경제부터 트렌드까지 {who_line(d)} 소식 {n}가지를 골라 보내줘요."
    else:
        subject = "매일 아침 트렌드 한 입, EDIT H 추천해요"
        pitch = f"매일 {when}에 트렌드 {n}가지를 정리해서 보내줘요."
    body = (f"오늘 받아본 뉴스레터인데 괜찮아서 보내요.\n\n[EDIT H] {plain(d['title'])}\n{site}/{d['date']}.html\n\n"
            f"{pitch} 무료 구독: {site}/subscribe.html?ref=share\n")
    return f"mailto:?subject={quote(subject)}&amp;body={quote(body)}"


def _cta(d, site, campaign, n_cards):
    stat = lambda big, small: (  # noqa: E731
        f'<td valign="top">{_div(f"font-size:16px;font-weight:700;line-height:1.2;color:#1B1B1E;", big)}'
        f'{_div(f"font-size:11.5px;font-weight:400;line-height:1.3;color:#6B6E75;margin-top:2px;", small)}</td>')
    # 형식 2 는 메인 5가지 + 한 줄 뉴스 = 오늘 다룬 주제 수(2026-09-26 절충안)
    n_topics = len(d["all_items"]) + (len(d["briefs"]) if d.get("format") == 2 else 0)
    stats = (stat(f"{n_topics}개", "오늘의 주제" if d.get("format") == 2 else "이슈 전문")
             + (stat(f"{n_cards}장", "카드뉴스") if n_cards else "") + stat(f"{int(d['vol'])}호", "누적 발행"))
    links = f'<a href="{_utm(site, "/", campaign, "cta_archive")}" style="font-family:{F};font-size:14px;color:{MUTED};text-decoration:none;">지난 호 보기&gt;</a>'
    if n_cards:
        cards = _utm(site, f"/instagram/{d['date']}/", campaign, "cardnews")
        links = (f'<a href="{cards}" style="font-family:{F};font-size:14px;color:{MUTED};text-decoration:none;">카드뉴스 보기&gt;</a>'
                 f'<span style="color:#C4C4C4;"> &nbsp;|&nbsp; </span>' + links)
    # 11/23~ 맨 위 목차가 이미 '오늘의 10가지 · 깊게 5 · 짧게 5'를 말한다 — 끝에서 같은 말을 되풀이하지 않는다(소비자 눈 점검, 운영자 '중복 없지?')
    head_line = "" if str(d.get("date", "")) >= H_VOICE_FROM and d.get("format") == 2 else None
    if _tail_v2(d) and d.get("format") == 2:   # 숫자 카드(얼굴·VOL·개수 되풀이) 없이 링크 한 줄 + 추천 + 구독
        return (_divider(30) + f'<tr><td class="px" style="padding:0 36px;">'
                + f'<div style="text-align:center;">{links}</div>'
                + f"""<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:16px;"><tr><td align="center" bgcolor="#FFFFFF" style="background:#FFFFFF;border:1.5px solid {CHIP_FG};border-radius:10px;"><a href="{share_url(d, site)}" style="display:block;padding:13px 10px;font-family:{F};font-size:15px;font-weight:700;color:{CHIP_FG};text-decoration:none;">카톡·링크로 친구에게 추천하기</a></td></tr></table>
{_div(f"font-size:12px;font-weight:400;line-height:1.6;color:{MUTED};margin-top:6px;", "누르면 카카오톡·문자로 바로 보내거나 링크를 복사할 수 있어요.", True)}
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:10px;"><tr><td align="center" bgcolor="{CHIP_FG}" style="background:{CHIP_FG};border-radius:10px;"><a href="{_utm(site, "/subscribe.html", campaign, "cta_subscribe")}&amp;ref=letter" style="display:block;padding:14px 10px;font-family:{F};font-size:15px;font-weight:700;color:#FFFFFF;text-decoration:none;">EDIT H 구독하기</a></td></tr></table></td></tr>""")
    return (_divider(30) + f'<tr><td class="px" style="padding:0 36px;">'
            + (head_line if head_line is not None else _div(f"font-size:19px;font-weight:700;line-height:1.45;color:{INK};",
                   (f"오늘 아침 {n_topics}가지 소식을 정리했어요<br>깊게 {len(d['all_items'])} · 짧게 {len(d['briefs'])}"   # 실제 개수(주말 3개 허용 — Codex 리뷰), 조사 없이(3·6 뒤 '으로')
                    if str(d.get("date", "")) >= BRIEFS_FROM and d.get("format") == 2
                    else f"매일 아침 {n_topics}가지 트렌드 이슈를<br>한 번에 정리해 드려요!"), True))
            + f"""<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:{0 if head_line == "" else 16}px;background:#FFFFFF;border:1px solid {RULE};border-radius:18px;box-shadow:0 2px 6px rgba(0,0,0,.08);"><tr><td style="padding:18px 16px;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
    <td valign="middle" style="width:70px;">{_face(d, site, 58)}</td>
    <td valign="middle" style="padding-left:12px;">{_div(f"font-size:15px;font-weight:500;line-height:1.2;color:{INK};", "edit.h.kr")}
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:8px;"><tr>{stats}</tr></table>
    </td>
  </tr></table>
</td></tr></table>
<div style="text-align:right;margin-top:10px;">{links}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:16px;"><tr><td align="center" bgcolor="#FFFFFF" style="background:#FFFFFF;border:1.5px solid {CHIP_FG};border-radius:10px;"><a href="{share_url(d, site) if _v3(d) else _share_mailto(d, site)}" style="display:block;padding:13px 10px;font-family:{F};font-size:15px;font-weight:700;color:{CHIP_FG};text-decoration:none;">{"카톡·링크로 친구에게 추천하기" if _v3(d) else "친구에게 추천하기"}</a></td></tr></table>
{_div(f"font-size:12px;font-weight:400;line-height:1.6;color:{MUTED};margin-top:6px;", "누르면 카카오톡·문자로 바로 보내거나 링크를 복사할 수 있어요.", True) if _v3(d) else ""}
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:10px;"><tr><td align="center" bgcolor="{CHIP_FG}" style="background:{CHIP_FG};border-radius:10px;"><a href="{_utm(site, "/subscribe.html", campaign, "cta_subscribe")}&amp;ref=letter" style="display:block;padding:14px 10px;font-family:{F};font-size:15px;font-weight:700;color:#FFFFFF;text-decoration:none;">EDIT H 구독하기</a></td></tr></table>
{"" if _v3(d) else _div(f"font-size:12px;font-weight:400;line-height:1.6;color:{MUTED};margin-top:8px;", "추천하기를 누르면 오늘 호 링크가 담긴 메일이 열려요. 받는 사람만 넣어 보내면 돼요.", True)}</td></tr>""")


def _footer(site, campaign, d=None):
    ig = f"https://instagram.com/edit.h.kr?utm_source=edit_h&amp;utm_medium=email&amp;utm_campaign={campaign}&amp;utm_content=footer_instagram"
    line = brand_line(d) if d and _v2(d) else "매일 아침, 트렌드 한 입"
    return (f'<tr><td class="px" style="padding:34px 36px 40px;">'
            + _div(f"font-size:12px;font-weight:400;line-height:1.9;color:{MUTED};",
                   f'EDIT H · {line} · 인스타그램 <a href="{ig}" style="color:{MUTED};">@edit.h.kr</a><br>'
                   + ('' if d and _tail_v2(d) else '이 메일이 유용했다면 동료에게 전달해주세요. · ')   # 11/27~ 추천 버튼과 같은 말 — 한 번만
                   + f'<a href="{site}/unsubscribe.html?email=PLACEHOLDER" style="color:{MUTED};">수신거부</a>', True)
            + "</td></tr>")


def _ld_json(d, site, title, has_cards=True):
    """검색엔진용 구조화 데이터(NewsArticle) — 웹 아카이브에만 쓴다(메일로 보낼 때 send_newsletter 가 뺀다).
    2026-10-09: 호 페이지에 설명문·대표 주소·구조화 데이터가 없어 검색 결과에 제목만 나갔다.
    발행 시각은 원고에 적힌 실제 시각(예비 호는 08:05 뒤 만든 시각)이 있으면 그것, 없으면 발송 시각. 카드 없이 만든 호는 이미지를 넣지 않는다."""
    url = f"{site}/{d['date']}.html"
    when = d.get("published_at_kst") or f"{d['date']}T{send_time_on(d['date'])}:00+09:00"
    org = {"@type": "Organization", "name": "EDIT H", "url": f"{site}/"}
    data = {"@context": "https://schema.org", "@type": "NewsArticle", "headline": f"[EDIT H] {title}"[:110],
            "description": plain(d["subtitle"]), "datePublished": when, "dateModified": when, "inLanguage": "ko",
            "mainEntityOfPage": url, "url": url, "author": org, "publisher": org}
    if has_cards:
        data["image"] = [f"{site}/instagram/{d['date']}/01_edit_h_{d['date']}_cover.png"]
    body = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return f'<script type="application/ld+json">{body}</script>'


def render(d, site, n_cards):
    campaign = "daily_" + d["date"].replace("-", "")
    title = plain(d["title"])
    if d.get("format") == 2:
        v3 = _v3(d)
        top = [_market_board(d["market"])] if _plus(d) and d.get("market") else [_forward_box(d, site, campaign)] if v3 and not _plus(d) else []
        body = [_header(d)] + top + [
            _divider(), _note_v3(d, site) if v3 else _note(d, site), _divider(30), _pick(d), _divider(0),
            f'<tr><td class="px" style="padding:30px 36px 0;">{_chips([("02–05", True), ("함께 볼 4가지", False)], "left" if v3 else "center")}</td></tr>']
        body.extend((_item_v3 if v3 else _item)(it) for it in d["items"])
        body.append(_briefs(d, "짧게 읽는 소식" if str(d.get("date", "")) >= BRIEFS_FROM else "한 줄 뉴스", start=len(d["all_items"]) + 1))
        if d.get("quiz"):
            body.append(_quiz_block(d, site))
        if d.get("poll_result"):
            body.append(_poll_result(d))
        body.append(_poll_block(d, site) if d.get("poll") else _question_h(d, site) if str(d.get("date", "")) >= H_VOICE_FROM else _question(d))
        if _plus(d):
            body.append(_rate_block(d, site))
    else:
        body = [_header(d), _divider(), _letter(d), _divider(30), _hero(d)]
        for i, sec in enumerate(d["sections"], 1):
            body.append(_divider(0))
            body.append(_section_head(i, sec))
            body.extend(_item(it) for it in sec["items"])
        body += [_briefs(d), _question(d)]
    body += [_cta(d, site, campaign, n_cards), _footer(site, campaign, d)]
    # --no-cards 로 만든 호는 표지 PNG 가 없다 — 공유 미리보기는 사이트 대표 이미지로(Codex 리뷰)
    share_img = f"{site}/instagram/{d['date']}/01_edit_h_{d['date']}_cover.png" if n_cards else f"{site}/og_image.png"
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="color-scheme" content="light only">
<meta name="supported-color-schemes" content="light only">
<meta name="description" content="{esc(plain(d['subtitle']))}">
<link rel="canonical" href="{site}/{d['date']}.html">
<meta property="og:type" content="article">
<meta property="og:site_name" content="EDIT H">
<meta property="og:locale" content="ko_KR">
<meta property="og:url" content="{site}/{d['date']}.html">
<meta property="og:title" content="[EDIT H] {esc(title)}">
<meta property="og:description" content="{esc(plain(d['subtitle']))}">
<meta property="og:image" content="{share_img}">
<meta name="twitter:card" content="summary_large_image">
<title>[EDIT H] {esc(title)}</title>
{_ld_json(d, site, title, bool(n_cards))}
<style>
:root{{color-scheme:light only;supported-color-schemes:light only;}}
@media (max-width:480px){{.px{{padding-left:20px!important;padding-right:20px!important;}}.h-cover{{font-size:26px!important;}}}}
</style>
</head>
<body style="margin:0;padding:0;background:{BOX};" bgcolor="{BOX}">
<!-- 프리헤더 -->
<div style="display:none;max-height:0;overflow:hidden;">{esc(plain(d['subtitle']))}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" bgcolor="{BOX}" style="background:{BOX};">
<tr><td align="center" style="padding:0;">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" bgcolor="#FFFFFF" style="max-width:600px;width:100%;background:#FFFFFF;table-layout:fixed;">
{''.join(body)}
</table>
</td></tr>
</table>
</body>
</html>
"""
