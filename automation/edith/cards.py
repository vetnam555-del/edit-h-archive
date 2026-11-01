"""카드뉴스(1080×1350, 4:5 — config.instagram.card_ratio_from 부터 1080×1440, 3:4) — VOL.092 '매거진 엔진'(로컬 templates/magazine/cards.js) 이식 + 2026-09-24 개선안(B).

Design M 카드뉴스 키트 '매거진 세트'(표지 24 → 본문 9 → 마무리 9) 규격을 재현한 것으로, 키트 원본
파일·이미지는 쓰지 않고 실측한 치수·색만 옮겼다. 키트의 핑크는 EDIT H 브랜드 버밀리언 계열로 바꿨다.

  01      표지     EDIT H. 워드마크(비스킷식) + 머리말 + 띠 제목 두 줄(뉴닉식) + 핵심어 대형 마커·다른 이슈 스티커 3개
                   또는 실사 사진 풀블리드(위·아래만 어둡게, 스티커 없음)
  02      요약     '오늘의 6가지 한눈에' — 번호·제목·숫자 목록(키트 본문 19·20 문법). 저장을 부르는 카드
  03~08   이슈 6장  말풍선 태그 → 형광 마커 숫자 → 보조 수치 상자 → 번호 배지 → 제목 → 짧은 본문 → '그래서 뭐가 달라져?' 대화
                   H PICK 1장은 검정 배경 + 윤곽 숫자 + 노란 '(H PICK · 오늘의 핵심)', compare형은 BEFORE/AFTER 상자
  09      관찰     H의 한 줄 관찰(마트 '시식후기'식 에디터 결론)
  10      마무리   오늘의 저장각 + 프로필 카드(10개 이슈 전문 · 6장 핵심 카드 · N호 누적 발행)

형식 2(5가지 + 한 줄 뉴스, 2026-09-26~): 01 표지 → 02 5가지 요약 → 03 H PICK → 04 심층 '왜 중요해?'(숫자 상자 + 요점) → 05~08 이슈 4장
  → 09 에디터 H 노트(안경 마크 + 한 줄, 금요일엔 투표 결과) → 10 마무리(월요일엔 A/B 투표)

개선안(B)을 고른 근거(A 현재·B·C 블랙 시안을 같은 내용으로 렌더링해 피드 390px·그리드 130px 크기로 측정):
표지 최대 글자가 그리드에서 10px→36px, 카드당 글자 127→90자, 피드 본문 10.5→11.9px, 출처 글자 대비 3.1→4.5:1 이상.

마크업: ==강조== = 형광 마커(검정 카드에서는 밝은 버밀리언 글자), **굵게**, \\n 줄바꿈.
넘치면 렌더러가 --k 배율로 글자를 최대 20%까지 줄인다(content.CARD_LIMITS 가 먼저 막는다).
"""
import base64
import mimetypes
import re

from .common import ROOT, card_height, dive_on, esc as _esc, load_config, send_time_ko

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


# 2026-11-01 운영자 "캐러셀 만들 때 문구만 만들지 마 — 이미지를 쓰거나 캐릭터를 쓴 이미지로. 문구만으로는 들어오고 싶은 마음이 없다".
# 사진 없는 표지(10/31 '급락'·주간 특집 'TOP5')가 글자뿐이었다 → 사진이 없으면 마스코트 H 가 반응하는 표지, 안쪽 이슈 카드엔 H 가 '그래서 뭐가 달라져?'를 묻는다.
MASCOT_CARDS_FROM = "2026-11-02"   # 11/01 호는 이 변경 머지(09:00 뒤) 전에 만들어져 08:30 에 나간다
MASCOT_DIR = ROOT / "assets" / "mascot"
_POSE_SHOCK = re.compile(r"급락|폭락|하락|떨어|빠졌|유출|해킹|사고|적자|감소|경고|위기|급등|폭등|사이드카|과징금|제재|파산|연체")
_POSE_GOOD = re.compile(r"혜택|지원금|할인|무료|환급|돌파|흑자|역대|출시|오픈|당첨|최대")
_POSE_DATE = re.compile(r"마감|시행|신청|접수|일정|D-\d|부터")


ON_DARK = "filter:" + " ".join(f"drop-shadow({x}px {y}px 0 #FFFFFF)" for x, y in ((2, 0), (-2, 0), (0, 2), (0, -2))) + ";"


def mascot_on(d):
    return str(d.get("date") or "")[:10] >= MASCOT_CARDS_FROM


def mascot_pose(text, default="thinking"):
    """소식 글자로 H 의 자세를 고른다 — 놀라운 소식 surprised, 좋은 소식 celebrate, 날짜·마감 calendar, 그 밖엔 default."""
    t = plain(str(text or ""))
    if _POSE_SHOCK.search(t):
        return "surprised"
    if _POSE_GOOD.search(t):
        return "celebrate"
    if _POSE_DATE.search(t):
        return "calendar"
    return default


def mascot_img(pose, size, style=""):
    f = MASCOT_DIR / f"h-{pose}.png"
    if not f.exists():
        f = MASCOT_DIR / "h-hello.png"
    return (f'<img src="{_photo_uri(f.relative_to(ROOT))}" alt="" '
            f'style="display:block;width:{size}px;height:{size}px;object-fit:contain;{style}">')


def _mascot_hero(d, cov, l1, l2, height):
    """사진 없는 표지 — 왼쪽에 크게 H(소식에 맞는 자세), 오른쪽 위에 H 가 외치는 핵심어 말풍선."""
    kw = cov.get("keyword") or ""
    pose = cov.get("mascot") or mascot_pose(f"{kw} {l1} {l2}", "point")
    size = min(128, fit_size(kw, 860) * 600 // 860) if kw else 0   # 핵심어 5자 이하 — 말풍선이 오른쪽 절반 안에
    say = (f'<div style="position:absolute;right:0;top:10px;z-index:2;background:#FFFFFF;border:5px solid {TEXT};'
           f'border-radius:44px;padding:10px 36px 16px;font-weight:900;font-size:{size}px;line-height:1.1;letter-spacing:-3px;color:{TEXT};'
           f'white-space:nowrap;box-shadow:0 8px 0 {ACC_FILL};">{esc(kw)}'
           f'<div style="position:absolute;left:46px;bottom:-24px;width:38px;height:38px;background:#FFFFFF;'
           f'border-right:5px solid {TEXT};border-bottom:5px solid {TEXT};transform:rotate(45deg);"></div></div>') if kw else ""
    body = min(height + 40, 600)
    return (say + f'<div style="position:absolute;left:30px;bottom:-30px;z-index:1;">{mascot_img(pose, body)}</div>')


def cover(d, kicker=None, foot=None, tag=None):
    """머리말 → (딥다이브 날 이름표) → 띠 제목 두 줄 → (사진 또는 핵심어 대형 마커) + 오늘의 다른 이슈 스티커 3개."""
    cov = d["cards"]["cover"]
    photo = cov.get("photo")
    l1, *rest = str(cov.get("title") or d["hero_title"]).split("\n")
    l2 = " ".join(rest)
    issues = d["card_issues"]
    stickers = [f'{it["tag"]} {hero_value(it)}' for it in issues[1:4]]
    spots = [("left:10px;top:0;", -3), ("right:0;top:230px;", 2), ("left:40px;top:430px;", -1.5)]
    sticker_html = "".join(f'<div style="position:absolute;{pos}">{_sticker(t, r)}</div>' for t, (pos, r) in zip(stickers, spots))
    if not kicker and d.get("series"):   # 고정 연재 날(수요일 'H의 장부'): 이름·회차를 표지 머리말에 — '다음 편'을 기다리게
        kicker = f"#{d['vol']} 매주 {d['weekday']}요일 연재 · {d['series']['label']}"
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
    elif mascot_on(d):
        hero = _mascot_hero(d, cov, l1, l2, 560 + (card_height(d["date"]) - H) // 2)
        spots = [("right:10px;top:250px;", 2), ("right:60px;top:360px;", -2), ("right:0;top:470px;", 1.5)]   # H 오른쪽 아래로
        sticker_html = "".join(f'<div style="position:absolute;z-index:3;{pos}">{_sticker(t, r)}</div>' for t, (pos, r) in zip(stickers, spots))
    else:
        kw = cov["keyword"]
        size = fit_size(kw, 380)
        hero = (f'<div style="position:absolute;left:0;right:0;top:40px;text-align:center;"><span style="display:inline-block;'
                f'padding:0 .06em;font-weight:800;font-size:{fs(size)};line-height:1;letter-spacing:-{round(size / 30)}px;color:{TEXT};'
                f'background:linear-gradient(180deg,transparent 62%,{ACC_FILL} 62%);">{esc(kw)}</span></div>')
    shadow = "text-shadow:0 1px 4px rgba(0,0,0,.55);" if photo else ""
    extra = card_height(d["date"]) - H   # 3:4 카드(1440)면 늘어난 90px 을 핵심어·스티커 자리에 나눠 준다(아래가 비지 않게)
    foot_color = "#FFFFFF" if photo else MUTED
    head_color, kick_color = ("#FFFFFF", "rgba(255,255,255,.92)") if photo else (TEXT, "#5A5A5E")
    pill = f'\n  <div style="flex:none;margin-top:20px;">{persona_pill(tag)}</div>' if tag else ""   # 딥다이브 날 이름표(지난 호 HTML 은 그대로)
    credit = (f'<div style="position:absolute;right:40px;bottom:24px;font-size:19px;color:rgba(255,255,255,.85);{shadow}">'
              f'{esc(cov["credit"])}</div>') if photo and cov.get("credit") else ""
    return _frame(f"""{bg}
<div class="body" style="padding:64px 60px 0;align-items:center;text-align:center;">
  <div style="font-weight:900;font-size:34px;line-height:1;letter-spacing:-1px;color:{head_color};{shadow}">EDIT H<span style="color:{ACC};">.</span></div>
  <div style="margin-top:22px;font-weight:700;font-size:28px;color:{kick_color};{shadow}">{esc(kicker)}</div>{pill}
  <div style="flex:none;margin-top:26px;display:flex;flex-direction:column;align-items:center;gap:14px;">{_strip(l1, "#FFFFFF")}{_strip(l2, ACC_FILL)}</div>
  <div style="flex:none;position:relative;margin-top:{70 + extra // 2 - (74 if tag else 0)}px;width:100%;height:{560 + extra // 2}px;">{hero}{sticker_html}</div>
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


def dialogue(take, dark, pose=None):
    """대화 — 흰 질문 말풍선 '그래서 뭐가 달라져?' → 복숭아색 답 말풍선(이 뉴스로 바뀌는 것, 누구나 읽을 수 있게). 키트 본문 21(Q&A) 문법과도 맞다.
    답이 'A — B' 꼴이면 줄표 뒤에서 줄을 바꿔 두 마디로 읽히게 하고, 렌더러(.shrink)가 말풍선 폭을 가장 긴 줄에 맞춘다."""
    q_bg, q_fg = ("#1E1E21", "#FFFFFF") if dark else ("#FFFFFF", TEXT)
    line = "#FFFFFF" if dark else TEXT
    ask = (f'<div style="background:{q_bg};border:3px solid {line};border-radius:22px 22px 22px 6px;'
           f'padding:14px 24px;font-weight:600;font-size:{fs(28)};line-height:1.2;color:{q_fg};">그래서 뭐가 달라져?</div>')
    if pose:   # H 가 독자 대신 묻는다(11/01~) — 말풍선 왼쪽에 작은 H. 검정 카드에선 검은 팔다리가 묻히지 않게 흰 테두리
        ask = (f'<div style="align-self:flex-start;display:flex;align-items:flex-end;gap:6px;margin-left:-14px;">'
               f'{mascot_img(pose, 180, "margin:-44px 0 -16px;" + (ON_DARK if dark else ""))}{ask}</div>')
    else:
        ask = ask.replace('<div style="', '<div style="align-self:flex-start;', 1)
    return (f'<div style="flex:none;width:100%;margin-top:26px;display:flex;flex-direction:column;gap:10px;">'
            f'{ask}'
            f'<div class="bal shrink" style="align-self:flex-end;max-width:92%;background:{ACC_FILL};border:3px solid {line};'
            f'border-radius:22px 22px 6px 22px;padding:16px 26px;text-align:left;font-weight:700;font-size:{fs(31)};'
            f'line-height:1.45;color:{TEXT};">{mk(take, TEXT).replace(" — ", " —<br>")}</div></div>')


def issue_card(it, n, date=None):
    dark = bool(it.get("accent"))
    pose = (("point" if dark else mascot_pose(f'{it.get("tag", "")} {it.get("headline", "")}'))
            if mascot_on({"date": date}) else None)
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
    # 검은 H PICK 카드는 '(H PICK · …)' 줄만큼 길어 9/29~10/4 5호 중 4호가 3% 자동 축소됐다 — 간격을 줄여 원래 크기로
    pick = (f'<div style="margin-top:18px;font-weight:500;font-size:30px;line-height:1;color:#F5C84C;">'
            f'(H PICK · {esc(it.get("series_label") or "오늘의 핵심")})</div>') if dark else ""
    return _frame(f"""
<div class="body" style="padding:0 80px 190px;justify-content:flex-end;align-items:center;text-align:center;">
  {bubble(it.get("ask") or it["tag"])}
  {hero}
  {tiles}
  <div style="flex:none;height:{20 if dark else 38}px;"></div>
  {badge}
  {pick}
  <div class="bal" style="margin-top:{22 if dark else 32}px;font-weight:700;font-size:{fs(56)};line-height:1.34;letter-spacing:-1px;color:{fg};">{mk(it["headline"], fg, dark)}</div>
  <div class="bal" style="margin-top:22px;font-weight:400;font-size:{fs(33)};line-height:1.55;color:{"#BDBDBD" if dark else SUB};">{mk(it["body"], fg, dark)}</div>
  {dialogue(it["takeaway"], dark, pose)}
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


def _on(d, key):
    """config.instagram[key] 날짜부터 켜는 카드 요소인가(2026-10-31 경쟁 비교 후속 — 실험 표본이 겹치지 않게 날짜로 켠다)."""
    start = (load_config().get("instagram") or {}).get(key)
    return bool(start) and str(d["date"])[:10] >= str(start)


def chart_box(ch, bg=BOX, show_source=True, frame=""):
    """숫자 비교·추이 막대 차트 — 주장 하나, 출처는 그림 안에(Chartr·Visual Capitalist, 2026-10-31 경쟁 비교 '자기만의 재료').
    ch: {'title', 'points': [{'label', 'value', 'text'?}] 3~6개, 'unit'?, 'highlight'?(기본 마지막), 'source'}. 값은 0 이상.
    딥다이브 장은 흰 바탕·테두리(frame)로, 출처는 장 아래 '자료 ·' 한 줄에 모은다(show_source=False)."""
    pts = ch["points"]
    top = max(float(p["value"]) for p in pts) or 1
    hi = ch.get("highlight", len(pts) - 1)
    unit = ch.get("unit", "")
    shown = [p.get("text") or f"{float(p['value']):g}{unit}" for p in pts]   # 막대 위 숫자 — text 가 있으면 그대로(예: 1.2조)
    bars = "".join(
        f'<div style="flex:1;min-width:0;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;height:100%;">'
        f'<div style="font-weight:800;font-size:{fs(30)};line-height:1.1;white-space:nowrap;color:{TEXT if i == hi else SUB};">'
        f'{esc(shown[i])}</div>'
        f'<div style="margin-top:10px;width:72%;height:{max(round(float(p["value"]) / top * 100), 2)}%;border-radius:12px 12px 0 0;'
        f'background:{ACC if i == hi else "#D9D9D9"};"></div></div>'
        for i, p in enumerate(pts))
    labels = "".join(
        f'<div style="flex:1;min-width:0;text-align:center;font-weight:{700 if i == hi else 500};font-size:{fs(24)};line-height:1.25;'
        f'color:{TEXT if i == hi else SUB};">{esc(p["label"])}</div>' for i, p in enumerate(pts))
    src = (f'<div style="margin-top:14px;font-weight:500;font-size:{fs(21)};line-height:1.35;color:{SRC_LIGHT};text-align:right;">'
           f'자료 · {esc(ch["source"])}</div>') if show_source else ""
    return (f'<div style="flex:none;width:100%;margin-top:40px;background:{bg};border-radius:24px;padding:28px 28px 22px;{frame}">'
            f'<div style="font-weight:800;font-size:{fs(32)};line-height:1.3;color:{TEXT};">{mk(ch["title"])}</div>'
            f'<div style="margin-top:18px;height:250px;display:flex;gap:12px;align-items:flex-end;border-bottom:3px solid {TEXT};">{bars}</div>'
            f'<div style="margin-top:12px;display:flex;gap:12px;">{labels}</div>'
            f'{src}</div>')


def deep_card(d):
    """형식 2 — H PICK 심층 '왜 중요해?'. 검정 H PICK 카드 바로 뒤에 붙어 한 이슈를 두 장으로 읽게 한다.
    차트 날(config.instagram.chart_card_from~, cards.deep.chart 가 있을 때)은 숫자 상자 대신 막대 차트 — 카드 수(10장)는 그대로."""
    b, deep = d["big_issue"], d["cards"]["deep"]
    chart = deep.get("chart") if _on(d, "chart_card_from") else None
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
  <div style="text-align:center;">{bubble(deep.get("ask") or "왜 중요해?")}</div>
  <div class="bal" style="text-align:center;font-weight:800;font-size:{fs(74)};line-height:1.3;letter-spacing:-1.5px;color:{TEXT};">{mk(deep["headline"])}</div>
  {chart_box(chart) if chart else f'<div style="flex:none;display:flex;gap:14px;width:100%;margin-top:46px;">{tiles}</div>'}
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
        # 오늘 챙길 것(config.instagram.todo_card_from~) — 메일 첫 화면의 체크리스트를 카드에도. 저장해 두고 쓰는 장(2026-10-31 경쟁 비교)
        todo = [x for x in d.get("todo") or [] if str(x).strip()][:3] if _on(d, "todo_card_from") else []
        checks = "".join(
            f'<div style="display:flex;gap:18px;align-items:flex-start;margin-top:{0 if i == 0 else 18}px;">'
            f'<div style="flex:none;margin-top:4px;width:36px;height:36px;border:3px solid {TEXT};border-radius:8px;"></div>'
            f'<div class="bal" style="font-weight:600;font-size:{fs(36)};line-height:1.4;color:{TEXT};">{mk(x)}</div></div>'
            for i, x in enumerate(todo))
        body = (f'<div style="margin-top:{40 if todo else 50}px;font-weight:900;font-size:{120 if todo else 150}px;line-height:.7;height:{56 if todo else 70}px;color:{ACC_FILL};">“</div>'
                f'<div class="bal" style="margin-top:6px;font-weight:600;font-size:{fs(50 if todo else 60)};line-height:1.5;letter-spacing:-1.5px;color:{TEXT};">{quote}</div>'
                + (f'<div style="flex:none;margin-top:44px;padding:30px 34px;border-radius:24px;background:{BOX};">'
                   f'<div style="font-weight:800;font-size:{fs(30)};line-height:1;margin-bottom:24px;color:{ACC_INK};">오늘 챙길 것 · 저장해 두고 체크</div>'
                   f'{checks}</div>' if todo else ""))
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


def calendar_card(label, title, rows):
    """달력에 적어 둘 날짜 — 주간 특집 저장각 장(E13, 2026-11-06~). rows: [{'month', 'day', 'weekday', 'what', 'todo', 'from'}].
    날짜 칸(월·일·요일) + 무슨 날 + 할 일 + '○/○ 호' — 저장해 두었다가 그날 꺼내 보는 참고 자료(2026-10-31 경쟁 비교: 두고 쓰는 자료)."""
    items = "".join(
        f'<div style="display:flex;gap:30px;align-items:center;padding:22px 0;border-bottom:2px solid #EAEAEA;">'
        f'<div style="flex:none;width:124px;padding:14px 0 12px;border-radius:20px;background:{TEXT};color:#FFFFFF;text-align:center;">'
        f'<div style="font-weight:700;font-size:26px;line-height:1;opacity:.75;">{r["month"]}월</div>'
        f'<div style="margin-top:6px;font-weight:900;font-size:50px;line-height:1;letter-spacing:-1px;">{r["day"]}</div>'
        f'<div style="margin-top:8px;font-weight:700;font-size:24px;line-height:1;color:{ACC_ON_DARK};">{esc(r["weekday"])}</div></div>'
        f'<div style="min-width:0;">'
        f'<div class="bal" style="font-weight:800;font-size:{fs(40)};line-height:1.28;letter-spacing:-1px;color:{TEXT};">{mk(r["what"])}</div>'
        f'<div class="bal" style="margin-top:6px;font-weight:600;font-size:{fs(31)};line-height:1.38;color:{ACC_INK};">→ {esc(r["todo"])}</div>'
        f'<div style="margin-top:4px;font-weight:500;font-size:{fs(24)};line-height:1.3;color:{SRC_LIGHT};">{esc(r["from"])}</div></div></div>'
        for r in rows)
    return _frame(f"""
<div class="body" style="padding:100px 84px 90px;justify-content:center;">
  <div style="display:flex;align-items:center;gap:16px;font-weight:700;font-size:32px;color:{TEXT};">
    <div style="width:24px;height:24px;background:{ACC};"></div>{esc(label)}</div>
  <div class="bal" style="margin-top:26px;font-weight:800;font-size:{fs(60)};line-height:1.3;letter-spacing:-1.5px;color:{TEXT};">{mk(title, dark=False)}</div>
  <div style="flex:none;margin-top:30px;border-top:3px solid {TEXT};">{items}</div>
  <div style="margin-top:22px;font-weight:600;font-size:{fs(27)};line-height:1.4;color:{SUB};">저장해 두면 그날 바로 꺼내 볼 수 있어요</div>
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


def follow_on(d):
    """마지막 장을 '팔로우 카드'로 내는 날인가 — config.instagram.follow_card_from 부터(투표 날은 예전 마무리)."""
    start = (load_config().get("instagram") or {}).get("follow_card_from")
    return bool(start and str(d["date"])[:10] >= start and not d.get("poll"))


# 팔로우 카드 소개 줄 — 11/01 운영자 "꼭 직장인보다는 2030 마케팅, 트렌드, 경제 등 폭넓게"(automation/reviews/2026-11-01-copy.md).
# E11(팔로우 카드) 표본 10/31~11/06 은 예전 줄 그대로 두고 그다음 날부터 바꾼다. 지난 호 카드는 다시 만들어도 예전 그대로(기록).
FOLLOW_LINE_V2_FROM = "2026-11-07"


def follow_line(d, when, n):
    if str(d["date"])[:10] >= FOLLOW_LINE_V2_FROM:
        return f"매일 아침 {when}, 경제부터 트렌드까지 2030이 알아야 할 소식 {n}가지"
    return f"매일 아침 {when}, 2030 직장인의 돈·일·소비 뉴스 {n}가지"


def cta_follow(d):
    """마무리 — 팔로우 카드(2026-10-30 운영자 '슬라이드투티켓 템플릿 ver.3' 엔딩: 이미지·계정명 중심, '어떤 계정인지·앞으로 무엇을
    만날지' 한 문장, 팔로우 버튼). 예전 마무리는 '팔로우 + 저장해두기>'가 옅은 글자 링크라 캐러셀을 보고 팔로우 0·프로필 방문 2
    (10/29 성과표, 최근 14일 13개 게시물 합)였다 — 인스타 화면과 같은 검은 버튼으로 할 일을 하나로 또렷하게. 저장 질문(오늘의 저장각)은 위에 그대로."""
    c = d["cards"]["cta"]
    when = send_time_ko(d.get("send_time_kst") or "08:30").replace("오전 ", "")
    n = len(d["card_issues"])
    stats = [(f"{len(d['all_items'])}개", "이슈 전문"), (f"{n}장", "핵심 카드"), (f"{int(d['vol'])}호", "누적 발행")]
    stat_html = "".join(
        f'<div><div style="font-weight:700;font-size:{fs(32)};line-height:1;color:#1B1B1E;">{v}</div>'
        f'<div style="font-weight:400;font-size:{fs(22)};line-height:1;color:#6B6E75;margin-top:10px;">{lbl}</div></div>'
        for v, lbl in stats)
    tail = f"이슈 {len(d['all_items'])}개 전문＋출처는 매일 아침 뉴스레터로\n→ **프로필 링크**에서 받아보세요"
    return _frame(f"""
<div class="body" style="padding:60px 78px;justify-content:center;">
  <div style="text-align:center;font-weight:700;font-size:28px;line-height:1;color:#5A5A5E;">{esc(c["kick"])}</div>
  <div class="bal" style="margin-top:30px;text-align:center;font-weight:700;font-size:{fs(50)};line-height:1.4;letter-spacing:-1px;color:{TEXT};">{mk(c["headline"])}</div>
  <div class="bal" style="margin-top:18px;text-align:center;font-weight:400;font-size:{fs(30)};line-height:1.5;color:{SUB};">{mk(c["sub"])}</div>
  <div style="flex:none;margin-top:46px;background:#FFFFFF;border:1.5px solid #EAEAEA;border-radius:36px;box-shadow:0 6px 16px rgba(0,0,0,.10);
    padding:44px 48px 40px;display:flex;flex-direction:column;align-items:center;text-align:center;">
    {avatar(132)}
    <div style="margin-top:22px;font-weight:800;font-size:{fs(40)};line-height:1;color:{TEXT};">edit.h.kr</div>
    <div class="bal" style="margin-top:16px;font-weight:500;font-size:{fs(30)};line-height:1.45;color:{SUB};">{follow_line(d, when, n)}</div>
    <div style="flex:none;width:100%;display:grid;grid-template-columns:repeat(3,1fr);margin-top:28px;">{stat_html}</div>
    <div style="flex:none;margin-top:32px;width:100%;background:#000000;color:#FFFFFF;border-radius:999px;padding:26px 0;
      font-weight:800;font-size:{fs(36)};line-height:1;">팔로우하고 내일 아침에 받기</div>
  </div>
  <div class="bal" style="margin-top:40px;text-align:center;font-weight:400;font-size:27px;line-height:1.6;color:{SUB};">{mk(tail)}</div>
</div>""")


# ── 딥다이브 카드(config.instagram.dive_card_from~ 연재 날, content.cards.dive 가 있을 때) ─────────────────────────────
# 2026-11-01 운영자 '딥다이브 카드 지금 바로 만들어줘'. 머니그라피 인스타 딥다이브 캐러셀(reviews/2026-11-01-moneygraphy.md '인스타 화면' A)을
# 우리 숫자로 옮겼다: 표지 이름표('H가 숫자로 읽어 주는') → H PICK → 질문 장 3~5(장마다 질문 제목 + 표·선 그래프·막대·큰 숫자·요점 중 하나 +
# H 의 해석 한두 줄, 어려운 개념은 상자 하나, 다른 업종 비유 한 장) → H의 판정 → 5가지 한눈에 → 마무리.
# 16.6만 계정에서도 리캡(소식 모음)은 댓글 0·리포스트 2, 질문 하나를 이름 있는 목소리가 숫자로 푼 편은 댓글 8·리포스트 6이었다.
# 바탕은 「H의 장부」 이름에 맞춘 장부 종이(옅은 가로줄 + 왼쪽 붉은 여백선).
DIVE_BY = "H가 숫자로 읽어 주는"
LEDGER, LEDGER_RULE, LEDGER_EDGE, LEDGER_SRC, LEDGER_BOX = "#FBF8F1", "rgba(40,47,56,.07)", "#E6E0D3", "#66625B", "#F1EBDD"
DIVE_STEP_POSES = ("point", "thinking", "newspaper", "point", "thinking")   # 질문 장 H 자세(장마다 바뀌게, 원고 pose 가 먼저)
LINE_W, LINE_H, LINE_SIDE, LINE_TOP, LINE_BOTTOM, LINE_ROOM = 932, 350, 84, 78, 16, 88   # 선 그래프 그림 크기 — 글자는 HTML 로 얹어 늘어나지 않게


def persona_pill(text):
    """딥다이브 표지 이름표 — 머니그라피 '이재용 회계사가 읽어주는'. 안경 마크(에디터 H) + 글자, 어떤 사진 위에서도 읽히게 흰 상자."""
    return (f'<div style="display:inline-flex;align-items:center;gap:14px;background:#FFFFFF;border:3px solid {TEXT};border-radius:999px;'
            f'padding:8px 30px 8px 10px;box-shadow:0 5px 0 {ACC_FILL};">{avatar(50)}'
            f'<span style="font-weight:800;font-size:30px;line-height:1;letter-spacing:-.5px;color:{TEXT};white-space:nowrap;">{esc(text)}</span></div>')


def _ledger(inner, d):
    """장부 종이 카드 — 옅은 가로줄 + 왼쪽 붉은 여백선, 오른쪽 위에 연재 이름표(한 장만 공유돼도 어떤 연재인지 보이게)."""
    tag = (d.get("series") or {}).get("label") or "H PICK 딥다이브"
    paper = (f'<div style="position:absolute;inset:0;background:repeating-linear-gradient(180deg,transparent 0 63px,{LEDGER_RULE} 63px 64px);"></div>'
             f'<div style="position:absolute;top:0;bottom:0;left:38px;width:3px;background:rgba(255,82,51,.32);"></div>'
             f'<div style="position:absolute;right:56px;top:36px;z-index:2;background:{ACC_BG};color:{ACC_INK};font-weight:800;font-size:24px;'
             f'line-height:1;padding:10px 16px;border-radius:10px;white-space:nowrap;">{esc(tag)}</div>')
    return _frame(paper + inner, LEDGER)


def _panel(inner, pad="24px 30px", top=0):
    """흰 종이 상자(표·그래프·요점). class fitw — 안의 표가 옆으로 넘치면 렌더러가 글자를 줄이고, 그래도 넘치면 넘침으로 알린다."""
    return (f'<div class="fitw" style="flex:none;width:100%;margin-top:{top}px;background:#FFFFFF;border:2px solid {LEDGER_EDGE};border-radius:26px;'
            f'padding:{pad};box-shadow:0 6px 0 rgba(40,47,56,.05);">{inner}</div>')


def dive_table(tb):
    """표 하나 — 첫 열(이름)은 왼쪽, 숫자 열은 오른쪽 정렬. highlight 줄은 복숭아색(우리가 보는 회사·기간)."""
    head, rows, hi = tb["head"], tb["rows"], tb.get("highlight")
    size = {2: 48, 3: 44}.get(len(head), 38)   # 열이 많을수록 작게 — 4열 × 10자 칸도 한 줄에
    th = "".join(
        f'<th style="padding:4px 10px 16px;text-align:{"left" if j == 0 else "right"};font-weight:700;font-size:{fs(27)};line-height:1.2;'
        f'color:{SUB};white-space:nowrap;">{esc(h)}</th>' for j, h in enumerate(head))
    trs = "".join(
        f'<tr style="border-top:2px solid #ECE6D9;{f"background:{ACC_FILL};" if i == hi else ""}">' + "".join(
            f'<td style="padding:{fs(28 if len(rows) <= 3 else 24)} 10px;text-align:{"left" if j == 0 else "right"};font-weight:{800 if i == hi else (700 if j == 0 else 600)};'
            f'font-size:{fs(size - 6 if j == 0 else size)};line-height:1.2;color:{TEXT};white-space:nowrap;font-variant-numeric:tabular-nums;">{esc(str(c))}</td>'
            for j, c in enumerate(row)) + '</tr>'
        for i, row in enumerate(rows))
    return _panel(f'<table style="width:100%;border-collapse:collapse;"><thead><tr style="border-bottom:3px solid {TEXT};">{th}</tr></thead>'
                  f'<tbody>{trs}</tbody></table>', "22px 26px 10px")


def line_chart(ln):
    """선 그래프 — 꼭대기·마지막 값에 이름표(머니그라피 '136,000원 → 39,400원'). 꼭대기가 마지막이면 처음·마지막에 단다.
    이름표는 이웃 점보다 높은 점이면 위에, 낮은 점이면 아래에 — 선을 가리지 않게(가장 낮은 값 아래에 LINE_ROOM 만큼 자리를 둔다).
    두 점이면 사이를 점선으로(재지 않은 구간). 그림(SVG)은 정해진 크기로 그리고 숫자·칸 이름은 HTML 로 얹는다 — 글자가 늘어나거나 찌그러지지 않게."""
    pts = ln["points"]
    n, unit = len(pts), ln.get("unit", "")
    vals = [float(p["value"]) for p in pts]
    shown = [p.get("text") or f"{v:g}{unit}" for p, v in zip(pts, vals)]
    lo, top = min(vals), max(vals)
    base = LINE_H - LINE_BOTTOM
    y_lo = base - LINE_ROOM
    xs = [LINE_SIDE + i * (LINE_W - 2 * LINE_SIDE) / (n - 1) for i in range(n)]
    ys = [(LINE_TOP + y_lo) / 2 if top == lo else LINE_TOP + (top - v) / (top - lo) * (y_lo - LINE_TOP) for v in vals]
    peak, last = vals.index(top), n - 1
    marks = {0: "first", last: "last"} if peak == last else {peak: "peak", last: "last"}

    def above(i):
        near = [ys[j] for j in (i - 1, i + 1) if 0 <= j < n]
        return marks.get(i) == "peak" or all(ys[i] <= y + 1 for y in near)

    if peak == last - 1 and above(last) and abs(ys[peak] - ys[last]) < 64:   # 꼭대기가 바로 앞 칸이고 높이가 비슷하면 이름표가 겹친다 — 마지막만
        marks = {last: "last"}
    path = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}" for i, (x, y) in enumerate(zip(xs, ys)))
    dash = ' stroke-dasharray="22 16"' if n == 2 else ""
    dots = "".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{11 if i in marks else 7}" fill="{ACC if i == last else "#FFFFFF"}" '
        f'stroke="{"#FFFFFF" if i == last else ACC}" stroke-width="{5 if i == last else 4}"/>'
        for i, (x, y) in enumerate(zip(xs, ys)))
    svg = (f'<svg width="{LINE_W}" height="{LINE_H}" viewBox="0 0 {LINE_W} {LINE_H}" style="display:block;overflow:visible;">'
           f'<defs><linearGradient id="dive-area" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{ACC}" stop-opacity=".18"/>'
           f'<stop offset="1" stop-color="{ACC}" stop-opacity="0"/></linearGradient></defs>'
           f'<path d="{path} L{xs[-1]:.1f},{base} L{xs[0]:.1f},{base} Z" fill="url(#dive-area)"/>'
           f'<line x1="0" y1="{base}" x2="{LINE_W}" y2="{base}" stroke="{TEXT}" stroke-width="3"/>'
           f'<path d="{path}" fill="none" stroke="{ACC}" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"{dash}/>{dots}</svg>')

    def tag(i, kind):
        x_shift = "-30px" if i == 0 else ("calc(-100% + 30px)" if i == last else "-50%")
        up = above(i)
        look = (f"background:{ACC};color:#FFFFFF;border:3px solid {ACC};" if kind == "last"
                else f"background:#FFFFFF;color:{TEXT};border:3px solid {TEXT};")
        word = '<span style="font-weight:600;opacity:.7;">최고 </span>' if kind == "peak" else ""
        return (f'<div style="position:absolute;left:{xs[i]:.0f}px;top:{ys[i] + (-22 if up else 22):.0f}px;'
                f'transform:translate({x_shift},{"-100%" if up else "0"});{look}'
                f'border-radius:14px;padding:9px 15px;font-weight:800;font-size:{fs(30)};line-height:1;white-space:nowrap;">{word}{esc(shown[i])}</div>')

    labels = "".join(
        f'<div style="position:absolute;left:{x:.0f}px;top:0;transform:translateX(-50%);font-weight:{700 if i in marks else 500};'
        f'font-size:{fs(23)};line-height:1.2;color:{TEXT if i in marks else SUB};white-space:nowrap;">{esc(p["label"])}</div>'
        for i, (x, p) in enumerate(zip(xs, pts)))
    title = (f'<div style="padding:0 30px;font-weight:800;font-size:{fs(30)};line-height:1.3;color:{TEXT};margin-bottom:4px;">{mk(ln["title"])}</div>'
             if ln.get("title") else "")
    return _panel(f'{title}<div style="position:relative;width:{LINE_W}px;height:{LINE_H}px;">{svg}'
                  f'{"".join(tag(i, k) for i, k in marks.items())}</div>'
                  f'<div style="position:relative;width:{LINE_W}px;height:32px;margin-top:10px;">{labels}</div>', "22px 0 16px")


def dive_stat(stat):
    return (f'<div style="flex:none;width:100%;text-align:center;">{marked_number(stat["value"])}'
            f'<div class="bal" style="margin-top:18px;font-weight:600;font-size:{fs(33)};line-height:1.4;color:{SUB};">{mk(stat["label"])}</div></div>')


def dive_points(points):
    rows = "".join(
        f'<div style="display:flex;gap:20px;align-items:flex-start;padding:{fs(24)} 0;{"border-top:2px solid #ECE6D9;" if i > 1 else ""}">'
        f'<div style="flex:none;margin-top:4px;width:52px;height:52px;border-radius:12px;background:{TEXT};color:#FFFFFF;display:flex;align-items:center;'
        f'justify-content:center;font-weight:700;font-size:27px;">{i}</div>'
        f'<div class="bal" style="font-weight:600;font-size:{fs(40)};line-height:1.45;color:{TEXT};">{mk(pt)}</div></div>'
        for i, pt in enumerate(points, 1))
    return _panel(rows, "6px 30px")


def dive_box(box):
    """어려운 개념은 상자 하나로(머니그라피 '기업가치/현금창출능력 = 5~6')."""
    return (f'<div style="flex:none;width:100%;margin-top:24px;display:flex;gap:18px;background:{LEDGER_BOX};border-radius:20px;padding:20px 26px;">'
            f'<div style="flex:none;width:10px;border-radius:5px;background:{ACC};"></div>'
            f'<div style="min-width:0;"><div style="font-weight:800;font-size:{fs(26)};line-height:1.2;color:{ACC_INK};">{esc(box["title"])}</div>'
            f'<div class="bal" style="margin-top:8px;font-weight:600;font-size:{fs(31)};line-height:1.45;color:{TEXT};">{mk(box["text"])}</div></div></div>')


def dive_say(text, pose):
    """H 의 해석 한두 줄 — 작은 H 가 말풍선으로 읽어 준다(이름 있는 목소리)."""
    return (f'<div style="flex:none;width:100%;margin-top:28px;display:flex;align-items:flex-end;">'
            f'{mascot_img(pose, 168, "flex:none;margin:0 -10px -20px -28px;")}'
            f'<div class="bal" style="flex:1;min-width:0;background:{ACC_FILL};border:3px solid {TEXT};border-radius:26px 26px 26px 6px;'
            f'padding:18px 26px;font-weight:700;font-size:{fs(33)};line-height:1.45;color:{TEXT};">{mk(text)}</div></div>')


def dive_step(d, st, n):
    """질문 장 — 머리표(Q1·비유로 보면) + 질문 제목 → 그림 하나 → (개념 상자) → H 의 해석 → 자료 출처.
    질문은 늘 같은 자리(위) — 넘겨 볼 때 눈이 같은 곳에서 시작하게. 그림·상자·H 의 해석은 한 덩어리로 그 아래 가운데에."""
    kind = next(k for k in ("table", "line", "chart", "stat", "points") if st.get(k))
    if kind == "chart":
        visual = chart_box(st["chart"], "#FFFFFF", False, f"border:2px solid {LEDGER_EDGE};margin-top:0;")
    else:
        visual = {"table": dive_table, "line": line_chart, "stat": dive_stat, "points": dive_points}[kind](st[kind])
    label = st.get("label") or f"Q{n}"
    head = (f'<div style="flex:none;display:inline-flex;align-self:flex-start;align-items:center;height:58px;padding:0 20px;border-radius:16px;'
            f'background:{ACC};color:#FFFFFF;font-weight:900;font-size:30px;line-height:1;letter-spacing:-.5px;white-space:nowrap;">{esc(label)}</div>'
            f'<div class="bal" style="flex:none;margin-top:22px;font-weight:800;font-size:{fs(72)};line-height:1.26;letter-spacing:-2px;color:{TEXT};">{mk(st["q"])}</div>')
    pose = st.get("pose") or DIVE_STEP_POSES[(n - 1) % len(DIVE_STEP_POSES)]
    return _ledger(f"""
<div class="body" style="padding:132px 72px 116px;">
  {head}
  <div style="flex:1;display:flex;flex-direction:column;justify-content:center;padding-top:28px;">
    {visual}
    {dive_box(st["box"]) if st.get("box") else ""}
    {dive_say(st["say"], pose)}
  </div>
</div>
<div style="position:absolute;left:72px;right:72px;bottom:54px;font-size:23px;line-height:1.35;color:{LEDGER_SRC};">자료 · {esc(st["source"])}</div>""", d)


def dive_verdict(d, vd):
    """H의 판정 — 머니그라피 마지막 장(결론 + 진행자 얼굴). ' — ' 뒤 결론에 형광 마커, 오른쪽 아래 큰 H, 맨 아래 '다음 편' 예고.
    오늘 챙길 것(todo_card_from~)이 있으면 판정 아래에 체크리스트(노트 카드 대신 이 장이 H 의 마지막 말이라)."""
    text = str(vd["text"])
    h, sep, tail = text.partition(" — ")
    body = (f"{mk(h)} — <span style=\"background:linear-gradient(180deg,transparent 58%,{ACC_FILL} 58%);font-weight:800;color:{TEXT};\">{mk(tail)}</span>"
            if sep else mk(text))
    todo = [x for x in d.get("todo") or [] if str(x).strip()][:3] if _on(d, "todo_card_from") else []
    checks = "".join(
        f'<div style="display:flex;gap:16px;align-items:flex-start;margin-top:{0 if i == 0 else 14}px;">'
        f'<div style="flex:none;margin-top:4px;width:32px;height:32px;border:3px solid {TEXT};border-radius:8px;background:#FFFFFF;"></div>'
        f'<div class="bal" style="font-weight:600;font-size:{fs(32)};line-height:1.4;color:{TEXT};">{mk(x)}</div></div>'
        for i, x in enumerate(todo))
    todo_box = (f'<div style="flex:none;margin-top:34px;padding:26px 30px;border-radius:22px;background:{LEDGER_BOX};">'
                f'<div style="font-weight:800;font-size:{fs(27)};line-height:1;margin-bottom:20px;color:{ACC_INK};">오늘 챙길 것 · 저장해 두고 체크</div>'
                f'{checks}</div>') if todo else ""
    s = d.get("series") or {}
    nxt = (f'다음 편 · 다음 주 {WEEKDAY_FULL[d["weekday"]]} 「{s["name"]}」 #{int(s["no"]) + 1}'
           if s.get("name") and str(s.get("no", "")).isdigit() else "")
    size = 250 if todo else 420
    return _ledger(f"""
<div class="body" style="padding:130px 80px {150 if nxt else 110}px;justify-content:center;">
  <div style="flex:none;display:flex;align-items:center;gap:16px;font-weight:800;font-size:34px;color:{TEXT};">
    <div style="width:26px;height:26px;background:{ACC};"></div>H의 판정</div>
  <div style="flex:none;margin-top:30px;font-weight:900;font-size:140px;line-height:.7;height:64px;color:{ACC_FILL};">“</div>
  <div class="bal" style="flex:none;font-weight:700;font-size:{fs(58 if todo else 70)};line-height:1.45;letter-spacing:-1.5px;color:{TEXT};">{body}</div>
  {todo_box}
  <div style="flex:none;display:flex;align-items:flex-end;justify-content:space-between;margin-top:{20 if todo else 26}px;">
    <div style="padding-bottom:{30 if todo else 60}px;font-weight:600;font-size:30px;color:{SUB};">— 에디터 H</div>
    {mascot_img(vd.get("pose") or "point", size, "margin:0 -24px -24px 0;")}
  </div>
</div>
{f'<div style="position:absolute;left:80px;right:80px;bottom:58px;padding-top:22px;border-top:3px dashed {LEDGER_EDGE};font-weight:700;font-size:28px;line-height:1.3;color:{ACC_INK};">{esc(nxt)} →</div>' if nxt else ""}""", d)


def dive_cards(d):
    """(카드 목록, 이름 목록) — 딥다이브 날: 표지(이름표) → H PICK → 질문 장 3~5 → H의 판정 → 5가지 한눈에 → 마무리(최대 10장).
    'pick'·'summary'·'cta' 이름은 그대로라 스토리 카드 화면(story_frames.ROLES)·카드 릴스(make_reel.REEL_PARTS)가 같은 장을 고른다."""
    dv, issues = d["cards"]["dive"], d["card_issues"]
    steps = dv["steps"]
    out = ([cover(d, foot="밀어서 숫자로 읽기 →", tag=dv.get("by") or DIVE_BY), issue_card(issues[0], 1, d["date"])]
           + [dive_step(d, st, n) for n, st in enumerate(steps, 1)]
           + [dive_verdict(d, dv["verdict"]), summary(d), cta_follow(d) if follow_on(d) else cta(d)])
    return out, ["cover", "pick"] + [f"dive{n}" for n in range(1, len(steps) + 1)] + ["verdict", "summary", "cta"]


CARD_NAMES = ["cover", "summary", "issue1", "issue2", "issue3", "issue4", "issue5", "issue6", "observation", "cta"]
CARD_NAMES_2 = ["cover", "summary", "pick", "deep", "issue2", "issue3", "issue4", "issue5", "note", "cta"]
# 2026-10-06~ (성장 검토 실험 2): 두 번째 장에 가장 센 숫자(H PICK) — 2장까지 넘긴 사람은 대개 끝까지 본다.
# 요약(오늘의 5가지)은 심층 뒤로 옮겨 '나머지 4가지' 예고 역할을 한다.
PICK_FIRST_FROM = "2026-10-06"
CARD_NAMES_2B = ["cover", "pick", "deep", "summary", "issue2", "issue3", "issue4", "issue5", "note", "cta"]


def height_css(date):
    """카드 세로 길이 CSS — 3:4 날(card_ratio_from~)이면 .card 를 1440px 로. 4:5 날은 빈 문자열(CSS 의 1350 그대로)."""
    h = card_height(date)
    return f".card{{height:{h}px;}}" if h != H else ""


def build(d, font_css):
    """(html 문자열, 파일명 목록)을 돌려준다. 카드 순서 = 파일명 순서."""
    issues = d["card_issues"]
    if dive_on(d) and d["date"] >= PICK_FIRST_FROM:
        cards, names = dive_cards(d)
    elif d.get("format") == 2 and d["date"] >= PICK_FIRST_FROM and not d.get("rewind"):
        cards = ([cover(d), issue_card(issues[0], 1, d["date"]), deep_card(d), summary(d)]
                 + [issue_card(it, i, d["date"]) for i, it in enumerate(issues[1:], 2)] + [note_card(d), cta_follow(d) if follow_on(d) else cta(d)])
        names = CARD_NAMES_2B
    elif d.get("format") == 2:
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
{CSS}
{height_css(d["date"])}</style></head><body>
{''.join(sections)}
</body></html>"""
    return page, files
