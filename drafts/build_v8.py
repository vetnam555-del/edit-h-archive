"""뉴스레터 시안 v8 — 따뜻한 바탕 위 둥근 흰 종이 한 장 + 힉스필드 H 그림(맨 위 큰 그림·소식마다 작은 그림·끝인사), 모서리 둥글게.
글자 위계는 v6·v7(에디토리얼)을 잇는다. 메일에서 안전한 표(table)·인라인 스타일.
python3 build_v8.py <content.json> <out.html> <그림 주소 앞부분(예: https://…/drafts/2026-11-21-v8- 또는 로컬 경로)>
"""
import datetime as dt
import html
import json
import re
import sys

c = json.load(open(sys.argv[1], encoding="utf-8"))
IMG = sys.argv[3]
SITE = "https://vetnam555-del.github.io/edit-h-archive"
F = "'Pretendard','Apple SD Gothic Neo','Malgun Gothic',sans-serif"
INK, BODY, SUB, RULE = "#16191D", "#3B4046", "#8A8F96", "#EFEAE4"
ACC, ACC_T, SOFT, PAGE = "#FF5233", "#C2410C", "#FFF3EB", "#F6F1EA"
EN = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"]


def esc(s):
    return html.escape(str(s or ""), quote=True)


def md(s):
    return re.sub(r"\*\*(.+?)\*\*", rf'<b style="color:{INK};">\1</b>', esc(s))


def clean(s):
    return re.sub(r"==|\*\*", "", str(s or "")).replace("\n", " ")


def div(style, inner=""):
    return f'<div style="font-family:{F};word-break:keep-all;{style}">{inner}</div>'


def rule(mt=0, color=RULE):
    return f'<div style="margin-top:{mt}px;border-top:1px solid {color};font-size:0;line-height:0;">&nbsp;</div>'


def label(text, mt=48):
    return div(f"margin-top:{mt}px;font-size:12px;font-weight:800;letter-spacing:1.4px;color:{ACC_T};", esc(text))


def img(name, w, radius, alt=""):
    return (f'<img src="{IMG}{name}.jpg" width="{w}" alt="{esc(alt)}" '
            f'style="display:block;width:100%;max-width:{w}px;height:auto;border:0;border-radius:{radius}px;">')


def src(sources):
    return div(f"margin-top:12px;font-size:12px;color:{SUB};",
               "출처 &nbsp;" + " · ".join(f'<a href="{esc(s.get("url"))}" style="color:{SUB};text-decoration:none;">{esc(s.get("name"))}</a>' for s in sources))


y, m, d = (int(x) for x in c["date"].split("-"))
wdi = (dt.date(y, m, d).weekday() + 1) % 7
vol = c.get("vol") or 150
bi, issues, items = c["big_issue"], c["cards"]["issues"], c["items"]

# ── 머리 + 큰 그림 + 제목
mast = (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>'
        f'<td valign="middle" style="font-family:{F};font-size:21px;font-weight:900;letter-spacing:-.7px;color:{INK};">EDIT H<span style="color:{ACC};">.</span></td>'
        f'<td valign="middle" align="right" style="font-family:{F};font-size:11.5px;font-weight:700;letter-spacing:1.2px;color:{SUB};">NO.{vol} · {m}.{d} {EN[wdi]}</td></tr></table>')
sents = re.split(r"(?<=[.?!])\s+", (c.get("lead") or "").strip())
hero = (div("margin-top:18px;", img("hero", 516, 18, "오늘의 H"))
        + div(f"margin-top:26px;font-size:12px;font-weight:800;letter-spacing:1.4px;color:{ACC_T};", "오늘의 브리프")
        + div(f"margin-top:10px;font-size:29px;line-height:1.3;font-weight:850;letter-spacing:-1.1px;color:{INK};", esc(c["cards"]["cover"]["title"]).replace("\n", "<br>"))
        + div(f"margin-top:14px;font-size:15.5px;line-height:1.75;color:{BODY};", esc(" ".join(sents[:2])) + f'<span style="color:{SUB};"> — 에디터 H</span>'))

mk = c.get("market") or []
mk_td = "".join(
    f'<td valign="top" width="{100 // len(mk)}%" style="padding:14px 6px;text-align:center;font-family:{F};">'
    f'<div style="font-size:11.5px;color:{SUB};">{esc(x["name"])}</div>'
    f'<div style="font-size:16px;font-weight:800;color:{INK};margin-top:4px;letter-spacing:-.3px;">{esc(x["value"])}</div>'
    f'<div style="font-size:12.5px;font-weight:700;color:{ACC_T};margin-top:2px;">{esc(x["chg"].replace("-", "−"))}</div></td>'
    for x in mk)
market = (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:24px;background:{SOFT};border-radius:16px;"><tr>{mk_td}</tr></table>'
          + div(f"margin-top:6px;font-size:11px;color:{SUB};text-align:center;", esc(c.get("market_note", "")))) if mk else ""

toc = "".join(
    f'<tr><td valign="top" style="width:28px;padding:12px 0;{"border-top:1px solid " + RULE + ";" if k else ""}font-family:{F};font-size:13px;font-weight:800;color:{ACC_T};">{it["no"]}</td>'
    f'<td valign="top" style="padding:12px 8px 12px 0;{"border-top:1px solid " + RULE + ";" if k else ""}font-family:{F};font-size:15.5px;line-height:1.45;font-weight:600;color:{INK};word-break:keep-all;">{esc(clean(it["headline"]))}</td>'
    f'<td valign="top" align="right" style="padding:12px 0;{"border-top:1px solid " + RULE + ";" if k else ""}font-family:{F};font-size:13px;font-weight:700;color:{SUB};white-space:nowrap;">{esc(it["number"])}</td></tr>'
    for k, it in enumerate(issues))
todo = "".join(
    f'<tr><td valign="top" style="width:20px;padding:7px 0;"><div style="width:8px;height:8px;border-radius:50%;background:{ACC};margin-top:7px;"></div></td>'
    f'<td style="padding:7px 0;font-family:{F};font-size:15px;line-height:1.6;color:{BODY};word-break:keep-all;">{esc(x)}</td></tr>' for x in c.get("todo") or [])
contents = (label("오늘의 5가지", 40)
            + f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:6px;">{toc}</table>'
            + f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:20px;background:{SOFT};border-radius:16px;"><tr><td style="padding:16px 18px;">'
            + div(f"font-size:13px;font-weight:800;color:{INK};", "오늘 챙길 것")
            + f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:4px;">{todo}</table></td></tr></table>')

# ── H PICK
chart = bi.get("chart")
chart_html = ""
if chart:
    top = max(v for _, v in chart["bars"])
    chart_html = (div(f"margin-top:24px;font-size:13px;font-weight:800;color:{INK};", esc(chart["title"]))
                  + '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:8px;">'
                  + "".join(f'<tr><td style="width:96px;padding:6px 0;font-family:{F};font-size:13.5px;color:{BODY};">{esc(n)}</td>'
                            f'<td style="padding:6px 10px;"><div style="height:10px;border-radius:5px;background:#F2EDE7;"><div style="height:10px;border-radius:5px;width:{round(v / top * 100)}%;background:{ACC if i == 0 else "#FFA585"};"></div></div></td>'
                            f'<td align="right" style="width:56px;padding:6px 0;font-family:{F};font-size:13.5px;font-weight:700;color:{INK};">−{v:.2f}%</td></tr>'
                            for i, (n, v) in enumerate(chart["bars"]))
                  + "</table>" + div(f"margin-top:6px;font-size:11px;color:{SUB};", esc(chart["note"])))
pick = (rule(44) + label("H PICK · 오늘 하나만 깊게", 30)
        + div(f"margin-top:12px;font-size:24px;line-height:1.35;font-weight:850;letter-spacing:-.9px;color:{INK};", esc(clean(c["cards"].get("deep", {}).get("headline") or bi["tag"])))
        + "".join(div(f"margin-top:14px;font-size:16px;line-height:1.8;color:{BODY};", md(x)) for x in bi["paragraphs"])
        + chart_html
        + div(f"margin-top:26px;font-size:13px;font-weight:800;color:{INK};", esc(c["cards"].get("deep", {}).get("ask") or "왜 중요해?"))
        + "".join(div(f"margin-top:8px;font-size:16px;line-height:1.8;color:{BODY};", md(x)) for x in bi.get("why") or [])
        + f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:24px;background:{SOFT};border-radius:16px;"><tr><td style="padding:18px 20px;font-family:{F};word-break:keep-all;">'
          f'<div style="font-size:12px;font-weight:800;letter-spacing:1px;color:{ACC_T};">그래서 나는?</div>'
          f'<div style="margin-top:6px;font-size:16.5px;line-height:1.65;font-weight:700;color:{INK};">{esc(bi["takeaway"])}</div></td></tr></table>'
        + src(bi.get("sources") or []))

# ── 함께 볼 4가지 — 소식마다 작은 H 그림
SPOT = c.get("spots") or {}
four = rule(44) + label("함께 볼 4가지", 30)
for k, (it, ci) in enumerate(zip(items, issues[1:])):
    spot = SPOT.get(it["tag"])
    head = (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:{22 if k == 0 else 32}px;"><tr>'
            + (f'<td valign="top" width="84" style="width:84px;padding-right:14px;">{img(spot, 84, 16, it["tag"])}</td>' if spot else "")
            + f'<td valign="middle" style="font-family:{F};word-break:keep-all;">'
              f'<div style="font-size:12px;font-weight:700;color:{SUB};">0{ci["no"]} · {esc(it["tag"])}</div>'
              f'<div style="margin-top:5px;font-size:17.5px;line-height:1.42;font-weight:800;letter-spacing:-.5px;color:{INK};">{esc(it["title"])}</div></td></tr></table>')
    four += (head
             + div(f"margin-top:12px;font-size:15.5px;line-height:1.75;color:{BODY};", md(ci["body"]))
             + div(f"margin-top:10px;font-size:15px;line-height:1.6;font-weight:700;color:{INK};", f'<span style="color:{ACC};">→</span>&nbsp; {esc(ci["takeaway"])}')
             + src(it.get("sources") or []))

# ── 짧게 5
br = "".join(
    f'<tr><td valign="top" style="width:28px;padding:11px 0;{"border-top:1px solid " + RULE + ";" if i else ""}font-family:{F};font-size:12.5px;font-weight:800;color:{SUB};">{i + 6:02d}</td>'
    f'<td style="padding:11px 0;{"border-top:1px solid " + RULE + ";" if i else ""}font-family:{F};font-size:15px;line-height:1.55;color:{INK};word-break:keep-all;">'
    f'{esc(b["title"])} <a href="{esc(b.get("url"))}" style="font-size:12px;color:{SUB};text-decoration:none;">{esc(b.get("source"))} ›</a></td></tr>'
    for i, b in enumerate(c.get("briefs") or []))
briefs = rule(44) + label("짧게 읽는 소식", 30) + f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:6px;">{br}</table>'

# ── 끝 — 손 흔드는 H
q = c["question"]
closing = re.split(r"(?<=[.,요])\s+(?=내일|—)", q.get("closing", ""))
end = (rule(44)
       + f'<table role="presentation" align="center" cellpadding="0" cellspacing="0" style="margin-top:30px;"><tr><td width="132" style="width:132px;">{img(c.get("bye_img", "bye"), 132, 66, "에디터 H")}</td></tr></table>'
       + div(f"margin-top:18px;font-size:12px;font-weight:800;letter-spacing:1.4px;color:{ACC_T};text-align:center;", "오늘의 질문")
       + div(f"margin-top:10px;font-size:20px;line-height:1.5;font-weight:800;letter-spacing:-.6px;color:{INK};text-align:center;", esc(re.sub("==|\\*\\*", "", q["text"])).replace("\n", "<br>"))
       + div(f"margin-top:8px;font-size:14px;color:{SUB};text-align:center;", "이 메일에 답장으로 들려주세요.")
       + div(f"margin-top:20px;font-size:14px;line-height:1.75;color:{BODY};text-align:center;", "<br>".join(esc(x.strip()) for x in closing))
       + f'<table role="presentation" align="center" cellpadding="0" cellspacing="0" style="margin-top:24px;"><tr>'
         f'<td style="background:{ACC_T};border-radius:999px;"><a href="{SITE}/share.html?d={c["date"]}" style="display:inline-block;padding:15px 30px;font-family:{F};font-size:15px;font-weight:800;color:#fff;text-decoration:none;">친구에게 EDIT H 보내기</a></td></tr></table>')
foot = div(f"margin-top:22px;font-size:11.5px;line-height:1.8;color:{SUB};text-align:center;",
           f'EDIT H — 2030의 아침을 편집합니다<br><a href="{SITE}/{c["date"]}.html" style="color:{SUB};">웹에서 보기</a> · '
           f'<a href="{SITE}/" style="color:{SUB};">지난 호</a> · 인스타그램 @edit.h.kr · 수신거부')

pre = esc(" · ".join(clean(i["headline"]) for i in issues[:3]))
out = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light only"><title>EDIT H NO.{vol}</title></head>
<body style="margin:0;padding:0;background:{PAGE};">
<div style="display:none;max-height:0;overflow:hidden;">{pre}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{PAGE};"><tr><td align="center" style="padding:20px 12px 28px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:580px;background:#FFFFFF;border-radius:24px;"><tr><td style="padding:24px 22px 34px;">
{mast}{hero}{market}{contents}{pick}{four}{briefs}{end}
</td></tr></table>{foot}</td></tr></table></body></html>"""
open(sys.argv[2], "w", encoding="utf-8").write(out)
print("ok", len(out))
