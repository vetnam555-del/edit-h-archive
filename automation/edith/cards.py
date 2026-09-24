"""카드뉴스(1080×1350, 4:5) — VOL.092 '매거진 엔진'(로컬 templates/magazine/cards.js) 이식 + 2026-09-24 개선안(B).

Design M 카드뉴스 키트 '매거진 세트'(표지 24 → 본문 9 → 마무리 9) 규격을 재현한 것으로, 키트 원본
파일·이미지는 쓰지 않고 실측한 치수·색만 옮겼다. 키트의 핑크는 EDIT H 브랜드 버밀리언 계열로 바꿨다.

  01      표지     EDIT H. 워드마크(비스킷식) + 머리말 + 띠 제목 두 줄(뉴닉식) + 핵심어 대형 마커·다른 이슈 스티커 3개
                   또는 실사 사진 풀블리드(위·아래만 어둡게, 스티커 없음)
  02      요약     '오늘의 6가지 한눈에' — 번호·제목·숫자 목록(키트 본문 19·20 문법). 저장을 부르는 카드
  03~08   이슈 6장  말풍선 태그 → 형광 마커 숫자 → 보조 수치 상자 → 번호 배지 → 제목 → 짧은 본문 → '그래서 뭐가 달라져?' 대화
                   H PICK 1장은 검정 배경 + 윤곽 숫자 + 노란 '(H PICK · 오늘의 핵심)', compare형은 BEFORE/AFTER 상자
  09      관찰     H의 한 줄 관찰(마트 '시식후기'식 에디터 결론)
  10      마무리   오늘의 저장각 + 프로필 카드(10개 이슈 전문 · 6장 핵심 카드 · N호 누적 발행)

형식 2(5가지, 2026-09-28~): 01 표지 → 02 5가지 요약 → 03 H PICK → 04 심층 '왜 중요해?'(숫자 상자 + 요점) → 05~08 이슈 4장
  → 09 에디터 H 노트(안경 마크 + 한 줄, 금요일엔 투표 결과) → 10 마무리(월요일엔 A/B 투표)

개선안(B)을 고른 근거(A 현재·B·C 블랙 시안을 같은 내용으로 렌더링해 피드 390px·그리드 130px 크기로 측정):
표지 최대 글자가 그리드에서 10px→36px, 카드당 글자 127→90자, 피드 본문 10.5→11.9px, 출처 글자 대비 3.1→4.5:1 이상.

마크업: ==강조== = 형광 마커(검정 카드에서는 밝은 버밀리언 글자), **굵게**, \\n 줄바꿈.
넘치면 렌더러가 --k 배율로 글자를 최대 20%까지 줄인다(content.CARD_LIMITS 가 먼저 막는다).
"""
import base64
import mimetypes
import re

from .common import ROOT, esc as _esc

W, H = 1080, 1350
TEXT, SUB, MUTED = "#282F38", "#555558", "#939393"
SRC_LIGHT = "#767676"  # 흰 배경 위 작은 글자 — WCAG AA 4.5:1 (#939393 은 3.1:1 이라 미달)
ACC_BG, ACC_INK, ACC_ON_DARK, ACC_FILL = "#FFDCCB", "#B23A0F", "#FF9466", "#FFC9AD"
CHIP_DARK, BOX = "#363636", "#F3F3F3"
INK, PAPER, ACC = "#0D0C0A", "#F5F1E8", "#FF5233"  # 브랜드 원색(프로필 마크)
SANS = "'Pretendard','Noto Sans KR',sans-serif"
WEEKDAY_FULL = {"월": "월요일", "화": "화요일", "수": "수요일", "목": "목요일", "금": "금요일", "토": "토요일", "일": "일요일"}

CSS = """
*{margin:0;padding:0;box-sizing:border-box;}
body{background:#777;width:1080px;}
.card{position:relative;width:1080px;height:1350px;overflow:hidden;font-family:%(sans)s;word-break:keep-all;
  -webkit-font-smoothing:antialiased;--k:1;}
.bal{text-wrap:balance;}
.body{position:absolute;inset:0;display:flex;flex-direction:column;overflow:hidden;}
""" % {"sans": SANS}

_BOLD = re.compile(r"\*\*(.+?)\*\*")
_MARK = re.compile(r"==(.+?)==")
# 따옴표로 묶은 짧은 말('이동 시간 대비 만족'을)은 중간에서 줄이 갈리면 뜻이 끊겨 보이므로 한 덩어리로 둔다
_QUOTE = re.compile(r"(?:&#x27;|&quot;|[‘“])[^<>*=\n]{1,14}?(?:&#x27;|&quot;|[’”])[가-힣]{0,2}")


def esc(s):
    # 가운뎃점(·) 앞뒤에서 줄이 끊기면 다음 줄이 '·'로 시작하므로 단어 결합자(U+2060)로 묶는다
    # '60.8%가'처럼 숫자·% 뒤 조사가 다음 줄로 떨어지지 않게도 묶는다
    s = re.sub(r"(?<=\S)·(?=\S)", "⁠·⁠", _esc(s))
    return re.sub(r"(?<=[%0-9])(?=[가-힣])", "⁠", s)


def plain(s):
    return esc(_MARK.sub(r"\1", _BOLD.sub(r"\1", str(s or ""))))


def mk(s, strong=TEXT, dark=False):
    hi = (f'<span style="color:{ACC_FILL};">\\1</span>' if dark
          else f'<span style="background:linear-gradient(180deg,transparent 58%,{ACC_FILL} 58%);">\\1</span>')
    out = _QUOTE.sub(lambda m: f'<span style="white-space:nowrap;">{m.group(0)}</span>', esc(s or ""))
    out = _BOLD.sub(f'<b style="font-weight:700;color:{strong};">\\1</b>', out)
    return _MARK.sub(hi, out).replace("\n", "<br>")


def fs(px):
    return f"calc({px}px*var(--k))"


def fit_size(text, max_px):
    units = sum(1 if re.match(r"[가-힣]", ch) else 0.62 if ch.isdigit() else 0.86 if ch == "%"
                else 1 if ch in "→←↑↓" else 0.6 for ch in str(text))
    return min(max_px, int(860 // max(units, 1)))


def chip_row(items, size=36):
    cells = "".join(
        f'<div style="height:{round(size * 1.85)}px;padding:0 {round(size * 0.45)}px;display:flex;align-items:center;'
        f'background:{CHIP_DARK if dark else ACC_BG};color:{ACC_ON_DARK if dark else ACC_INK};font-weight:700;'
        f'font-size:{size}px;line-height:1;letter-spacing:-0.5px;white-space:nowrap;box-shadow:0 2px 5px rgba(0,0,0,.14);">'
        f'{esc(text)}</div>'
        for text, dark in items)
    return f'<div style="display:flex;justify-content:center;gap:12px;">{cells}</div>'


def bubble(text):
    """표지 18 말풍선 — 이슈 태그."""
    return (f'<div style="position:relative;display:inline-block;margin-bottom:38px;">'
            f'<div style="background:#FFFFFF;border:2px solid #000000;border-radius:50%;padding:22px 40px;font-weight:500;'
            f'font-size:{fs(30)};line-height:1;color:#111111;white-space:nowrap;">{esc(text)}</div>'
            f'<svg width="30" height="26" viewBox="0 0 30 26" style="position:absolute;right:22%;bottom:-21px;overflow:visible;">'
            f'<path d="M2 -4 L24 22 L18 -4 Z" fill="#FFFFFF"/>'
            f'<path d="M2 -1 L24 22 L18 -1" fill="none" stroke="#000000" stroke-width="2" stroke-linejoin="round"/></svg></div>')


def marked_number(text):
    """본문 10 — 진한 숫자 + 버밀리언 형광 마커."""
    size = fit_size(text, 150)
    return (f'<div style="display:inline-block;padding:0 .08em;font-weight:800;font-size:{fs(size)};line-height:1.08;'
            f'letter-spacing:-3px;color:{TEXT};white-space:nowrap;'
            f'background:linear-gradient(180deg,transparent 60%,{ACC_FILL} 60%);">{esc(text)}</div>')


def outlined(text, line="#FFFFFF"):
    """표지 18 색 채움 + 윤곽 글자 — H PICK 한 장에만."""
    size = fit_size(text, 172)
    stroke = max(10, round(size / 12))
    base = f"font-weight:800;font-size:{fs(size)};line-height:1.1;letter-spacing:-2px;white-space:nowrap;"
    return (f'<div style="position:relative;display:inline-block;">'
            f'<div style="{base}color:{line};-webkit-text-stroke:{stroke}px {line};">{esc(text)}</div>'
            f'<div style="{base}position:absolute;left:0;top:0;color:{ACC_FILL};">{esc(text)}</div></div>')


def compare_box(cmp, dark):
    """compare형 — 이전/이후를 한 덩어리 숫자로 뭉개지 않고 2단 상자로 나눈다."""
    arrow = ACC_ON_DARK if dark else ACC_INK

    def box(label, value, sub, accent):
        bg = ACC_FILL if accent else ("#1E1E21" if dark else BOX)
        return (f'<div style="flex:1;min-width:0;background:{bg};border-radius:26px;padding:26px 24px;text-align:left;">'
                f'<div style="font-weight:700;font-size:19px;letter-spacing:2px;color:{ACC_INK if accent else MUTED};">{label}</div>'
                f'<div style="font-weight:800;font-size:{fs(40)};line-height:1.15;letter-spacing:-1px;'
                f'color:{TEXT if accent or not dark else "#FFFFFF"};margin-top:8px;">{esc(value)}</div>'
                f'<div style="font-weight:400;font-size:{fs(20)};line-height:1.35;'
                f'color:{"#5A2A10" if accent else ("#BDBDBD" if dark else SUB)};margin-top:6px;">{esc(sub)}</div></div>')

    return (f'<div style="display:flex;align-items:stretch;gap:14px;width:100%;">'
            f'{box("BEFORE", cmp["from"]["value"], cmp["from"]["label"], False)}'
            f'<div style="flex:none;display:flex;align-items:center;font-weight:800;font-size:34px;color:{arrow};">→</div>'
            f'{box("AFTER", cmp["to"]["value"], cmp["to"]["label"], True)}</div>')


def _frame(inner, bg="#FFFFFF", mark=True):
    """카드 한 장. 표지 밖의 모든 장에 작은 EDIT H. 워드마크를 단다(마트식 — 한 장만 캡처돼 공유돼도 브랜드가 보이게)."""
    wm = ""
    if mark:
        fg = "#FFFFFF" if bg == "#000000" else TEXT
        wm = (f'<div style="position:absolute;left:56px;top:46px;z-index:2;font-weight:900;font-size:26px;line-height:1;'
              f'letter-spacing:-.5px;color:{fg};">EDIT H<span style="color:{ACC};">.</span></div>')
    return f'<section class="card" style="background:{bg};">{wm}{inner}</section>'


def _photo_uri(path):
    p = ROOT / path
    mime = mimetypes.guess_type(p.name)[0] or "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(p.read_bytes()).decode()}"


def _strip(text, bg, size=74):
    """뉴닉식 띠 제목 — 줄마다 테두리 상자. 그리드 썸네일에서도 제목이 읽히게 한다."""
    return (f'<div style="display:inline-block;background:{bg};border:4px solid {TEXT};padding:10px 22px 12px;'
            f'font-weight:800;font-size:{fs(size)};line-height:1.15;letter-spacing:-1.5px;color:{TEXT};white-space:nowrap;">{plain(text)}</div>')


def _sticker(text, rotate):
    return (f'<div style="display:inline-block;transform:rotate({rotate}deg);background:#FFFFFF;border:3px solid {TEXT};'
            f'padding:10px 18px;font-weight:700;font-size:30px;line-height:1;color:{TEXT};white-space:nowrap;'
            f'box-shadow:0 3px 8px rgba(0,0,0,.14);">{esc(text)}</div>')


def cover(d, kicker=None, foot=None):
    """머리말 → 띠 제목 두 줄 → (사진 또는 핵심어 대형 마커) + 오늘의 다른 이슈 스티커 3개."""
    cov = d["cards"]["cover"]
    photo = cov.get("photo")
    l1, *rest = str(cov.get("title") or d["hero_title"]).split("\n")
    l2 = " ".join(rest)
    issues = d["card_issues"]
    stickers = [f'{it["tag"]} {hero_value(it)}' for it in issues[1:4]]
    spots = [("left:10px;top:0;", -3), ("right:0;top:230px;", 2), ("left:40px;top:430px;", -1.5)]
    sticker_html = "".join(f'<div style="position:absolute;{pos}">{_sticker(t, r)}</div>' for t, (pos, r) in zip(stickers, spots))
    kicker = kicker or f"#{d['vol']} {WEEKDAY_FULL[d['weekday']]}의 트렌드 브리프 | 오늘의 {len(issues)}가지"
    foot = foot or f"밀어서 {len(issues)}가지 보기 →"
    bg = ""
    if photo:
        # 뉴닉식 풀블리드: 사진을 끝까지 보여주고, 위(워드마크·머리말)와 아래(넘김 안내)만 어둡게 받친다.
        # 띠 제목은 자체 상자라 어떤 사진 위에서도 읽힌다. 스티커는 사진을 가리므로 사진 표지에서는 뺀다.
        bg = (f'<div style="position:absolute;inset:0;background:url(\'{_photo_uri(photo)}\') {cov.get("focus") or "center"}/cover no-repeat;"></div>'
              '<div style="position:absolute;inset:0;background:linear-gradient(180deg,rgba(0,0,0,.62) 0%,rgba(0,0,0,.35) 22%,'
              'rgba(0,0,0,0) 42%,rgba(0,0,0,0) 72%,rgba(0,0,0,.55) 100%);"></div>')
        hero, sticker_html = "", ""
    else:
        kw = cov["keyword"]
        size = fit_size(kw, 380)
        hero = (f'<div style="position:absolute;left:0;right:0;top:40px;text-align:center;"><span style="display:inline-block;'
                f'padding:0 .06em;font-weight:800;font-size:{fs(size)};line-height:1;letter-spacing:-{round(size / 30)}px;color:{TEXT};'
                f'background:linear-gradient(180deg,transparent 62%,{ACC_FILL} 62%);">{esc(kw)}</span></div>')
    shadow = "text-shadow:0 1px 4px rgba(0,0,0,.55);" if photo else ""
    foot_color = "#FFFFFF" if photo else MUTED
    head_color, kick_color = ("#FFFFFF", "rgba(255,255,255,.92)") if photo else (TEXT, "#5A5A5E")
    credit = (f'<div style="position:absolute;right:40px;bottom:24px;font-size:19px;color:rgba(255,255,255,.85);{shadow}">'
              f'{esc(cov["credit"])}</div>') if photo and cov.get("credit") else ""
    return _frame(f"""{bg}
<div class="body" style="padding:64px 60px 0;align-items:center;text-align:center;">
  <div style="font-weight:900;font-size:34px;line-height:1;letter-spacing:-1px;color:{head_color};{shadow}">EDIT H<span style="color:{ACC};">.</span></div>
  <div style="margin-top:22px;font-weight:700;font-size:28px;color:{kick_color};{shadow}">{esc(kicker)}</div>
  <div style="flex:none;margin-top:26px;display:flex;flex-direction:column;align-items:center;gap:14px;">{_strip(l1, "#FFFFFF")}{_strip(l2, ACC_FILL)}</div>
  <div style="flex:none;position:relative;margin-top:70px;width:100%;height:560px;">{hero}{sticker_html}</div>
</div>
<div style="position:absolute;left:0;right:0;bottom:60px;text-align:center;font-weight:700;font-size:26px;color:{foot_color};{shadow}">{esc(foot)}</div>{credit}""", mark=False)


def hero_value(it):
    return it["compare"]["to"]["value"] if it.get("compare") else it["number"]


def summary(d, period="오늘의"):
    """키트 본문 19·20(번호 목록) 문법 — 오늘의 6가지를 한 장에. 저장해두고 다시 볼 이유를 만든다."""
    rows = "".join(
        f'<div style="display:flex;align-items:center;gap:26px;padding:31px 0;border-bottom:2px solid #EAEAEA;">'
        f'<div style="flex:none;width:58px;height:58px;border-radius:13px;background:{"#000000" if it.get("accent") else TEXT};color:#FFFFFF;'
        f'display:flex;align-items:center;justify-content:center;font-weight:600;font-size:30px;">{i}</div>'
        f'<div style="flex:1;min-width:0;font-weight:700;font-size:{fs(39)};line-height:1.3;color:{TEXT};">{plain(it["headline"])}</div>'
        f'<div style="flex:none;font-weight:800;font-size:{fs(38)};color:{TEXT};white-space:nowrap;'
        f'background:linear-gradient(180deg,transparent 58%,{ACC_FILL} 58%);">{esc(hero_value(it))}</div></div>'
        for i, it in enumerate(d["card_issues"], 1))
    n = len(d["card_issues"])
    return _frame(f"""
<div class="body" style="padding:110px 76px 100px;justify-content:center;">
  <div style="text-align:center;font-weight:700;font-size:30px;color:#5A5A5E;">저장해두고 두고두고 보세요</div>
  <div style="text-align:center;margin-top:22px;font-weight:700;font-size:{fs(72)};letter-spacing:-1px;color:{TEXT};">{period} <span style="background:linear-gradient(180deg,transparent 58%,{ACC_FILL} 58%);">{n}가지</span> 한눈에</div>
  <div style="flex:none;margin-top:52px;border-top:3px solid {TEXT};">{rows}</div>
</div>""")


def stat_tiles(metrics, dark):
    """큰 숫자를 받쳐주는 보조 수치(최대 2개) — compare 상자와 같은 회색 상자 문법."""
    tiles = "".join(
        f'<div style="flex:1;min-width:0;background:{"#1E1E21" if dark else BOX};border-radius:24px;padding:22px 20px;text-align:center;">'
        f'<div style="font-weight:800;font-size:{fs(46)};line-height:1.1;letter-spacing:-1px;color:{"#FFFFFF" if dark else TEXT};white-space:nowrap;">{esc(m["value"])}</div>'
        f'<div style="font-weight:500;font-size:{fs(22)};line-height:1.35;margin-top:8px;color:{"#BDBDBD" if dark else SUB};">{esc(m["label"])}</div></div>'
        for m in metrics)
    return f'<div style="flex:none;display:flex;gap:14px;width:100%;margin-top:30px;">{tiles}</div>'


def dialogue(take, dark):
    """대화 — 흰 질문 말풍선 '그래서 뭐가 달라져?' → 복숭아색 답 말풍선(이 뉴스로 바뀌는 것, 누구나 읽을 수 있게). 키트 본문 21(Q&A) 문법과도 맞다.
    답이 'A — B' 꼴이면 줄표 뒤에서 줄을 바꿔 두 마디로 읽히게 하고, 렌더러(.shrink)가 말풍선 폭을 가장 긴 줄에 맞춘다."""
    q_bg, q_fg = ("#1E1E21", "#FFFFFF") if dark else ("#FFFFFF", TEXT)
    line = "#FFFFFF" if dark else TEXT
    return (f'<div style="flex:none;width:100%;margin-top:26px;display:flex;flex-direction:column;gap:10px;">'
            f'<div style="align-self:flex-start;background:{q_bg};border:3px solid {line};border-radius:22px 22px 22px 6px;'
            f'padding:14px 24px;font-weight:600;font-size:{fs(28)};line-height:1.2;color:{q_fg};">그래서 뭐가 달라져?</div>'
            f'<div class="bal shrink" style="align-self:flex-end;max-width:92%;background:{ACC_FILL};border:3px solid {line};'
            f'border-radius:22px 22px 6px 22px;padding:16px 26px;text-align:left;font-weight:700;font-size:{fs(31)};'
            f'line-height:1.45;color:{TEXT};">{mk(take, TEXT).replace(" — ", " —<br>")}</div></div>')


def issue_card(it, n):
    dark = bool(it.get("accent"))
    fg = "#FFFFFF" if dark else TEXT
    cmp = it.get("compare")
    if cmp:
        hero = compare_box(cmp, dark)
    elif dark:
        hero = outlined(it["number"])
    else:
        hero = marked_number(it["number"])
    side = [m for m in it.get("metrics") or [] if m["value"] != hero_value(it)][:2]
    tiles = stat_tiles(side, dark) if side else ""
    badge = (f'<div style="flex:none;width:60px;height:60px;border-radius:14px;background:{"#FFFFFF" if dark else TEXT};'
             f'color:{"#000000" if dark else "#FFFFFF"};display:flex;align-items:center;justify-content:center;'
             f'font-weight:600;font-size:32px;line-height:1;">{n}</div>')
    pick = (f'<div style="margin-top:26px;font-weight:500;font-size:30px;line-height:1;color:#F5C84C;">'
            f'(H PICK · 오늘의 핵심)</div>') if dark else ""
    return _frame(f"""
<div class="body" style="padding:0 80px 190px;justify-content:flex-end;align-items:center;text-align:center;">
  {bubble(it["tag"])}
  {hero}
  {tiles}
  <div style="flex:none;height:38px;"></div>
  {badge}
  {pick}
  <div class="bal" style="margin-top:{22 if dark else 32}px;font-weight:700;font-size:{fs(56)};line-height:1.34;letter-spacing:-1px;color:{fg};">{mk(it["headline"], fg, dark)}</div>
  <div class="bal" style="margin-top:22px;font-weight:400;font-size:{fs(33)};line-height:1.55;color:{"#BDBDBD" if dark else SUB};">{mk(it["body"], fg, dark)}</div>
  {dialogue(it["takeaway"], dark)}
</div>
<div style="position:absolute;left:60px;right:60px;bottom:80px;text-align:center;font-size:24px;line-height:1.4;color:{MUTED if dark else SRC_LIGHT};">출처 · {esc(it["source"])}</div>""",
                  "#000000" if dark else "#FFFFFF")


def observation(d):
    """마트 '시식후기'식 마무리 전 장 — 오늘 6가지를 한 줄로 꿰는 에디터 H 의 관찰(뉴스레터 'H의 한 줄 관찰'과 같은 문장).
    ' — ' 뒤의 결론 부분에 형광 마커를 칠한다."""
    text = str(d["observation"])
    head, sep, tail = text.partition(" — ")
    body = f"{mk(head)} — <span style=\"background:linear-gradient(180deg,transparent 58%,{ACC_FILL} 58%);font-weight:800;color:{TEXT};\">{mk(tail)}</span>" if sep else mk(text)
    return _frame(f"""
<div class="body" style="padding:110px 90px 110px;justify-content:center;">
  <div style="display:flex;align-items:center;gap:16px;font-weight:700;font-size:32px;color:{TEXT};">
    <div style="width:24px;height:24px;background:{ACC};"></div>H의 한 줄 관찰</div>
  <div style="margin-top:34px;font-weight:900;font-size:150px;line-height:.7;height:70px;color:{ACC_FILL};">“</div>
  <div class="bal" style="margin-top:6px;font-weight:600;font-size:{fs(62)};line-height:1.55;letter-spacing:-1.5px;color:{TEXT};">{body}</div>
  <div style="margin-top:56px;text-align:right;font-weight:500;font-size:30px;color:{SUB};">— 에디터 H</div>
</div>""")


def deep_card(d):
    """형식 2 — H PICK 심층 '왜 중요해?'. 검정 H PICK 카드 바로 뒤에 붙어 한 이슈를 두 장으로 읽게 한다."""
    b, deep = d["big_issue"], d["cards"]["deep"]
    tiles = "".join(
        f'<div style="flex:1;min-width:0;background:{BOX};border-radius:24px;padding:24px 14px;text-align:center;">'
        f'<div style="font-weight:800;font-size:{fs(54)};line-height:1.1;letter-spacing:-1px;color:{TEXT};white-space:nowrap;">{esc(n["value"])}</div>'
        f'<div style="font-weight:500;font-size:{fs(24)};line-height:1.35;margin-top:10px;color:{SUB};">{esc(n["label"])}</div></div>'
        for n in b["numbers"])
    points = "".join(
        f'<div style="display:flex;gap:22px;align-items:flex-start;padding:32px 0;border-bottom:2px solid #EAEAEA;">'
        f'<div style="flex:none;width:54px;height:54px;border-radius:12px;background:{TEXT};color:#FFFFFF;display:flex;'
        f'align-items:center;justify-content:center;font-weight:700;font-size:28px;">{i}</div>'
        f'<div class="bal" style="font-weight:600;font-size:{fs(40)};line-height:1.45;color:{TEXT};padding-top:1px;text-align:left;">{mk(pt)}</div></div>'
        for i, pt in enumerate(deep["points"], 1))
    src = d["card_issues"][0]["source"]
    return _frame(f"""
<div class="body" style="padding:110px 70px 140px;justify-content:center;">
  <div style="text-align:center;">{bubble("왜 중요해?")}</div>
  <div class="bal" style="text-align:center;font-weight:800;font-size:{fs(74)};line-height:1.3;letter-spacing:-1.5px;color:{TEXT};">{mk(deep["headline"])}</div>
  <div style="flex:none;display:flex;gap:14px;width:100%;margin-top:46px;">{tiles}</div>
  <div style="flex:none;margin-top:40px;border-top:3px solid {TEXT};">{points}</div>
</div>
<div style="position:absolute;left:60px;right:60px;bottom:70px;text-align:center;font-size:24px;line-height:1.4;color:{SRC_LIGHT};">H PICK 심층 · 출처 · {esc(src)}</div>""")


def note_card(d):
    """형식 2 — 에디터 H 노트(고정 코너). 안경 마크로 에디터를 캐릭터로 세운다. 투표 결과가 있는 날은 결과를 싣는다."""
    head = (f'<div style="display:flex;align-items:center;gap:22px;">{avatar(96)}'
            f'<div><div style="font-weight:800;font-size:38px;line-height:1.1;color:{TEXT};">에디터 H 노트</div>'
            f'<div style="font-weight:500;font-size:24px;line-height:1;margin-top:10px;color:{SUB};letter-spacing:1px;">EDITOR H&#39;S NOTE</div></div></div>')
    r = d.get("poll_result")
    if r:
        t = r["tally"]
        lead = max(t["votes"], key=lambda k: t["votes"][k])
        bars = "".join(
            f'<div style="margin-top:{34 if i else 40}px;">'
            f'<div style="display:flex;justify-content:space-between;font-weight:700;font-size:{fs(36)};color:{TEXT};">'
            f'<span>{key} · {esc(t["options"][i])}</span><span>{t["pct"].get(key, 0)}%</span></div>'
            f'<div style="margin-top:14px;height:34px;border-radius:17px;background:{BOX};overflow:hidden;">'
            f'<div style="width:{max(t["pct"].get(key, 0), 3)}%;height:100%;border-radius:17px;background:{ACC_FILL if key == lead else "#D9D9D9"};"></div></div></div>'
            for i, key in enumerate("AB"))
        body = (f'<div style="margin-top:56px;display:inline-block;align-self:flex-start;background:{CHIP_DARK};color:{ACC_ON_DARK};'
                f'font-weight:700;font-size:28px;padding:12px 18px;">지난 투표 결과 · {t["total"]}명 참여</div>'
                f'<div class="bal" style="margin-top:28px;font-weight:800;font-size:{fs(54)};line-height:1.35;letter-spacing:-1px;color:{TEXT};">{mk(t["question"])}</div>'
                f'{bars}'
                + (f'<div class="bal" style="margin-top:48px;font-weight:500;font-size:{fs(34)};line-height:1.55;color:{SUB};">{mk(r["comment"])}</div>'
                   if r.get("comment") else ""))
    else:
        text = str(d["observation"])
        h, sep, tail = text.partition(" — ")
        quote = (f"{mk(h)} — <span style=\"background:linear-gradient(180deg,transparent 58%,{ACC_FILL} 58%);font-weight:800;color:{TEXT};\">{mk(tail)}</span>"
                 if sep else mk(text))
        body = (f'<div style="margin-top:50px;font-weight:900;font-size:150px;line-height:.7;height:70px;color:{ACC_FILL};">“</div>'
                f'<div class="bal" style="margin-top:6px;font-weight:600;font-size:{fs(60)};line-height:1.55;letter-spacing:-1.5px;color:{TEXT};">{quote}</div>')
    return _frame(f"""
<div class="body" style="padding:120px 90px 110px;justify-content:center;">
  {head}
  {body}
  <div style="margin-top:56px;text-align:right;font-weight:500;font-size:30px;color:{SUB};">— 에디터 H</div>
</div>""")


def list_card(label, title, rows):
    """라벨 + 굵은 제목 + 번호 목록 — 주간 특집 '이번 주를 한 줄로' 등."""
    items = "".join(
        f'<div style="display:flex;gap:24px;align-items:flex-start;padding:36px 0;border-bottom:2px solid #EAEAEA;">'
        f'<div style="flex:none;width:58px;height:58px;border-radius:13px;background:{TEXT};color:#FFFFFF;display:flex;'
        f'align-items:center;justify-content:center;font-weight:700;font-size:30px;">{i}</div>'
        f'<div class="bal" style="font-weight:500;font-size:{fs(40)};line-height:1.45;color:{TEXT};padding-top:2px;">{mk(r)}</div></div>'
        for i, r in enumerate(rows, 1))
    return _frame(f"""
<div class="body" style="padding:110px 84px 110px;justify-content:center;">
  <div style="display:flex;align-items:center;gap:16px;font-weight:700;font-size:32px;color:{TEXT};">
    <div style="width:24px;height:24px;background:{ACC};"></div>{esc(label)}</div>
  <div class="bal" style="margin-top:34px;font-weight:800;font-size:{fs(68)};line-height:1.3;letter-spacing:-1.5px;color:{TEXT};">{mk(title, dark=False)}</div>
  <div style="flex:none;margin-top:44px;border-top:3px solid {TEXT};">{items}</div>
</div>""")


def avatar(size=148):
    """@edit.h.kr 프로필 마크 — 버밀리언 원 + 안경(렌즈 2개). 뉴스레터 58px 마크를 같은 비율로 키웠다."""
    s = size / 58
    lens = (f'<div style="width:{round(21 * s)}px;height:{round(21 * s)}px;border-radius:50%;border:{round(3 * s)}px solid {INK};'
            f'background:{PAPER};display:flex;justify-content:center;">'
            f'<div style="width:{round(6 * s)}px;height:{round(6 * s)}px;border-radius:50%;background:{INK};margin-top:{round(4 * s)}px;"></div></div>')
    bridge = f'<div style="width:{round(5 * s)}px;height:{round(3 * s)}px;background:{INK};"></div>'
    return (f'<div style="flex:none;width:{size}px;height:{size}px;border-radius:50%;background:{ACC};display:flex;'
            f'align-items:center;justify-content:center;">{lens}{bridge}{lens}</div>')


def cta(d):
    c = d["cards"]["cta"]
    poll = d.get("poll")
    stats = [(f"{len(d['all_items'])}개", "이슈 전문"), (f"{len(d['card_issues'])}장", "핵심 카드"), (f"{int(d['vol'])}호", "누적 발행")]
    stat_html = "".join(
        f'<div><div style="font-weight:700;font-size:36px;line-height:1;color:#1B1B1E;">{v}</div>'
        f'<div style="font-weight:400;font-size:25px;line-height:1;color:#6B6E75;margin-top:12px;">{lbl}</div></div>'
        for v, lbl in stats)
    link = re.sub(r"^[^0-9A-Za-z가-힣]+\s*", "", c.get("pill", "팔로우 + 저장해두기"))
    tail = f"이슈 {len(d['all_items'])}개 전문＋출처는 매일 아침 뉴스레터로\n→ **프로필 링크**에서 받아보세요"
    if poll:
        # 월요일 투표 — 댓글 A/B 로 받는다(tally_poll.py 가 세고, 금요일 호에 결과를 싣는다)
        pill = lambda key, text, bg: (  # noqa: E731
            f'<div style="flex:1;min-width:0;background:{bg};border:4px solid {TEXT};border-radius:26px;padding:26px 18px;text-align:center;">'
            f'<div style="font-weight:900;font-size:56px;line-height:1;color:{TEXT};">{key}</div>'
            f'<div class="bal" style="margin-top:14px;font-weight:700;font-size:{fs(34)};line-height:1.3;color:{TEXT};">{esc(text)}</div></div>')
        top = (f'<div style="text-align:center;font-weight:700;font-size:28px;line-height:1;color:#5A5A5E;">이번 주 투표 · 금요일에 결과 공개</div>'
               f'<div class="bal" style="margin-top:30px;text-align:center;font-weight:800;font-size:{fs(54)};line-height:1.35;letter-spacing:-1px;color:{TEXT};">{mk(poll["question"])}</div>'
               f'<div style="flex:none;margin-top:36px;display:flex;gap:18px;">{pill("A", poll["options"][0], "#FFFFFF")}{pill("B", poll["options"][1], ACC_FILL)}</div>'
               f'<div style="margin-top:24px;text-align:center;font-weight:700;font-size:{fs(32)};color:{ACC_INK};">댓글로 A 또는 B 남겨주세요</div>')
    else:
        top = (f'<div style="text-align:center;font-weight:700;font-size:28px;line-height:1;color:#5A5A5E;">{esc(c["kick"])}</div>'
               f'<div class="bal" style="margin-top:34px;text-align:center;font-weight:700;font-size:{fs(52)};line-height:1.4;letter-spacing:-1px;color:{TEXT};">{mk(c["headline"])}</div>'
               f'<div class="bal" style="margin-top:22px;text-align:center;font-weight:400;font-size:{fs(32)};line-height:1.5;color:{SUB};">{mk(c["sub"])}</div>')
    return _frame(f"""
<div class="body" style="padding:60px 78px;justify-content:center;">
  {top}
  <div style="flex:none;margin-top:{40 if poll else 50}px;background:#FFFFFF;border:1.5px solid #EAEAEA;border-radius:34px;box-shadow:0 4px 10px rgba(0,0,0,.10);padding:36px 40px;display:flex;align-items:center;gap:40px;">
    {avatar()}
    <div style="flex:1;">
      <div style="font-weight:500;font-size:31px;line-height:1;color:{TEXT};">edit.h.kr</div>
      <div style="display:grid;grid-template-columns:repeat(3,1fr);margin-top:26px;">{stat_html}</div>
    </div>
  </div>
  <div style="margin-top:26px;text-align:right;font-weight:400;font-size:30px;line-height:1;color:{SRC_LIGHT};">{esc(link)}&gt;</div>
  <div class="bal" style="margin-top:{40 if poll else 64}px;text-align:center;font-weight:400;font-size:27px;line-height:1.6;color:{SUB};">{mk(tail)}</div>
</div>""")


CARD_NAMES = ["cover", "summary", "issue1", "issue2", "issue3", "issue4", "issue5", "issue6", "observation", "cta"]
CARD_NAMES_2 = ["cover", "summary", "pick", "deep", "issue2", "issue3", "issue4", "issue5", "note", "cta"]


def build(d, font_css):
    """(html 문자열, 파일명 목록)을 돌려준다. 카드 순서 = 파일명 순서."""
    issues = d["card_issues"]
    if d.get("format") == 2:
        cards = ([cover(d), summary(d), issue_card(issues[0], 1), deep_card(d)]
                 + [issue_card(it, i) for i, it in enumerate(issues[1:], 2)] + [note_card(d), cta(d)])
        names = CARD_NAMES_2
    else:
        cards = [cover(d), summary(d)] + [issue_card(it, i) for i, it in enumerate(issues, 1)] + [observation(d), cta(d)]
        names = CARD_NAMES
    sections = cards
    files = [f"{i:02d}_edit_h_{d['date']}_{name}.png" for i, name in enumerate(names, 1)]
    page = f"""<!DOCTYPE html><html lang="ko"><head><meta charset="UTF-8">
<style>{font_css}
{CSS}</style></head><body>
{''.join(sections)}
</body></html>"""
    return page, files
