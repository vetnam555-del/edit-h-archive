"""세로 전용 릴스 프레임(1080×1920) — 2026-10-02 성장 검토(automation/reviews/2026-10-02-growth-review.md, Codex 지침).

4:5 카드를 흐린 배경에 얹던 슬라이드쇼는 첫 화면이 작은 글자 카드라 평균 시청이 1.5~3.8초에 그쳤다.
그래서 릴스만을 위한 세로 화면 4장을 따로 만든다 — 소리 없이도 읽히는 큰 글자, 장마다 한 메시지:

  1 hook    질문 제목(표지 제목 두 줄)을 화면 가득 — 0초부터 보인다(릴스 커버도 이 장: thumb_offset 0.8초)
  2 number  H PICK 의 핵심 숫자(이전→이후 비교면 둘 다)와 한 줄 설명
  3 answer  '그래서 뭐가 달라져?' — H PICK 카드의 결론 한 줄
  4 cta     에디터 H(안경 마크)와 '매일 아침 8시, 트렌드 5가지' — 팔로우·프로필 링크

안전 영역: 인스타 릴스는 위쪽(약 220px)에 상단 표시, 아래쪽(약 420px)에 캡션·버튼, 오른쪽 아래에 좋아요·댓글 단추가 덮는다.
글자는 세로 260~1480px, 가로 가운데 860px 안에 둔다. make_reel.py 가 이 JPEG 들로 약 10초 영상을 만든다.
"""
from .cards import (ACC, ACC_FILL, CSS, INK, PAPER, TEXT, _MARK, _photo_uri, avatar, esc, fs, hero_value, mk, plain)

W, H = 1080, 1920
REEL_FRAMES = ["hook", "number", "answer", "cta"]
SAFE_TOP, SAFE_BOTTOM, TEXT_W = 260, 440, 860

FRAME_CSS = """
.reel{height:1920px;}
.reel .body{padding:%(top)dpx 110px %(bottom)dpx;}
""" % {"top": SAFE_TOP, "bottom": SAFE_BOTTOM}


def _units(text):
    """대략적인 글자 폭(em). 한글·한자 1, 그 밖(숫자·영문·기호·공백) 0.58."""
    return sum(1.0 if ord(ch) >= 0x1100 else 0.58 for ch in text)


def _rewrap(lines, max_units=9.0):
    """제목을 짧은 줄로 다시 나눈다 — 줄이 짧을수록 글자를 크게 쓸 수 있다(첫 화면은 글자 크기가 곧 훅).
    편집자가 나눈 줄은 그대로 두고, 너무 긴 줄만 가운데에 가까운 띄어쓰기에서 둘로 나눈다(뜻이 끊기지 않게).
    ==강조== 안의 띄어쓰기에서는 나누지 않는다."""
    out = []
    for line in lines:
        out.extend(_split(line.strip(), max_units))
    return out


def _split(line, max_units):
    if _units(plain(line)) <= max_units:
        return [line]
    best = None
    for i, ch in enumerate(line):
        if ch != " " or line[:i].count("==") % 2:
            continue
        left, right = line[:i].strip(), line[i + 1:].strip()
        worst = max(_units(plain(left)), _units(plain(right)))
        if best is None or worst < best[0]:
            best = (worst, left, right)
    if best is None:
        return [line]
    return _split(best[1], max_units) + _split(best[2], max_units)


def _fit(lines, max_px, width=TEXT_W, floor=56):
    """가장 긴 줄이 width 안에 들어가는 글자 크기(px)."""
    widest = max((_units(plain(line)) for line in lines if line.strip()), default=1)
    return max(floor, min(max_px, int(width / max(widest, 1) / 1.02)))


def _wordmark(color):
    return (f'<div style="position:absolute;left:0;right:0;top:{SAFE_TOP - 70}px;text-align:center;font-weight:900;font-size:40px;'
            f'line-height:1;letter-spacing:-1px;color:{color};">EDIT H<span style="color:{ACC};">.</span></div>')


def _frame(inner, bg):
    return f'<section class="card reel" style="background:{bg};">{inner}</section>'


def _title_lines(d):
    """표지 제목 두 줄. 같은 문장이면 ==강조== 가 있는 hero_title 을 쓴다(핵심 숫자를 형광으로)."""
    cov = d["cards"]["cover"]
    title = str(cov.get("title") or d["hero_title"])
    if plain(d["hero_title"]).replace("\n", " ") == plain(title).replace("\n", " "):
        title = d["hero_title"]
    return [line for line in title.split("\n") if line.strip()]


def hook(d):
    """질문 제목을 크게. 표지 사진이 있으면 어둡게 깔고, 없으면 먹색 바탕."""
    cov = d["cards"]["cover"]
    lines = _rewrap(_title_lines(d))
    size = _fit(lines, 132, width=900)
    title = "<br>".join(_mark_on_dark(line) for line in lines)
    bg_layer = ""
    if cov.get("photo"):
        bg_layer = (f'<div style="position:absolute;inset:0;background:url(\'{_photo_uri(cov["photo"])}\') '
                    f'{cov.get("focus") or "center"}/cover no-repeat;"></div>'
                    '<div style="position:absolute;inset:0;background:rgba(13,12,10,.74);"></div>')
    kicker = (f"매주 {d['weekday']}요일 연재 · {d['series']['label']}" if d.get("series")
              else f"오늘의 트렌드 {len(d['card_issues'])}가지 · {d['weekday']}요일 아침")
    return _frame(f"""{bg_layer}{_wordmark("#FFFFFF")}
<div class="body" style="justify-content:center;align-items:center;text-align:center;">
  <div style="font-weight:700;font-size:38px;line-height:1;color:rgba(255,255,255,.9);">{esc(kicker)}</div>
  <div class="bal" style="margin-top:56px;font-weight:900;font-size:{fs(size)};line-height:1.22;letter-spacing:-3px;color:#FFFFFF;text-shadow:0 4px 18px rgba(0,0,0,.55);">{title}</div>
</div>""", INK)


def _mark_on_dark(text):
    """==강조== 를 어두운 바탕용 형광(주황 바탕 + 먹색 글자)으로."""
    out = esc(_strip_bold(text))
    return _MARK.sub(f'<span style="background:{ACC};color:{INK};padding:0 .12em;border-radius:.08em;">\\1</span>', out)


def _strip_bold(text):
    return str(text or "").replace("**", "")


def number(d):
    """H PICK 의 핵심 숫자. 비교(이전→이후)면 둘 다, 아니면 숫자 하나를 크게."""
    it = d["card_issues"][0]
    head_lines = [line for line in str(it.get("headline") or "").split("\n") if line.strip()]
    head = "<br>".join(mk(line) for line in head_lines)
    if it.get("compare"):
        a, b = it["compare"]["from"], it["compare"]["to"]
        big = _fit([b["value"]], 300, width=760, floor=120)
        small = min(150, max(90, int(big * 0.5)))
        hero = (f'<div style="font-weight:800;font-size:{fs(small)};line-height:1;color:#9A9AA0;text-decoration:line-through;'
                f'text-decoration-thickness:6px;">{esc(a["value"])}</div>'
                f'<div style="margin-top:6px;font-size:{fs(64)};line-height:1;color:{ACC};">↓</div>'
                f'<div style="margin-top:10px;display:inline-block;font-weight:900;font-size:{fs(big)};line-height:1;letter-spacing:-6px;'
                f'color:{TEXT};background:linear-gradient(180deg,transparent 64%,{ACC_FILL} 64%);padding:0 .06em;">{esc(b["value"])}</div>'
                f'<div style="margin-top:22px;font-weight:700;font-size:{fs(36)};color:#55555A;">{esc(a["label"])} → {esc(b["label"])}</div>')
    else:
        val = hero_value(it)
        big = _fit([val], 320, width=820, floor=120)
        hero = (f'<div style="display:inline-block;font-weight:900;font-size:{fs(big)};line-height:1;letter-spacing:-6px;color:{TEXT};'
                f'background:linear-gradient(180deg,transparent 64%,{ACC_FILL} 64%);padding:0 .06em;">{esc(val)}</div>')
    return _frame(f"""{_wordmark(TEXT)}
<div class="body" style="justify-content:center;align-items:center;text-align:center;">
  <div style="font-weight:700;font-size:36px;line-height:1;color:{ACC};">H PICK · {esc(d['big_issue']['tag'])}</div>
  <div style="margin-top:48px;">{hero}</div>
  <div class="bal" style="margin-top:64px;font-weight:800;font-size:{fs(62)};line-height:1.3;letter-spacing:-1.5px;color:{TEXT};">{head}</div>
</div>""", PAPER)


def answer(d):
    """'그래서 뭐가 달라져?' — H PICK 카드의 결론 한 줄을 크게."""
    it = d["card_issues"][0]
    text = it.get("takeaway") or plain(d["big_issue"].get("takeaway"))
    size = 86 if len(text) <= 30 else 76 if len(text) <= 44 else 66
    return _frame(f"""{_wordmark("#FFFFFF")}
<div class="body" style="justify-content:center;align-items:center;text-align:center;">
  <div style="display:inline-block;background:{ACC};color:{INK};font-weight:800;font-size:40px;line-height:1;padding:18px 30px;border-radius:999px;">그래서 뭐가 달라져?</div>
  <div class="bal" style="margin-top:64px;font-weight:800;font-size:{fs(size)};line-height:1.4;letter-spacing:-1.5px;color:#FFFFFF;">{esc(_strip_bold(plain_marks(text)))}</div>
</div>""", INK)


def plain_marks(text):
    return _MARK.sub(r"\1", str(text or ""))


def cta(d):
    """에디터 H(안경 마크) — 누가 매일 말하는지 보이게. 팔로우·프로필 링크로."""
    send = d.get("send_time_kst") or "08:00"
    hour = int(send.split(":")[0])
    return _frame(f"""
<div class="body" style="justify-content:center;align-items:center;text-align:center;">
  {avatar(260)}
  <div style="margin-top:44px;font-weight:900;font-size:72px;line-height:1;letter-spacing:-2px;color:{TEXT};">에디터 H</div>
  <div class="bal" style="margin-top:36px;font-weight:700;font-size:{fs(50)};line-height:1.4;color:{TEXT};">매일 아침 {hour}시,<br>트렌드 {len(d['card_issues'])}가지를 넘겨드려요</div>
  <div style="margin-top:56px;display:inline-block;background:{TEXT};color:#FFFFFF;font-weight:800;font-size:42px;line-height:1;padding:26px 44px;border-radius:999px;">팔로우하고 내일 아침에 받기</div>
  <div style="margin-top:34px;font-weight:500;font-size:32px;line-height:1.5;color:#55555A;">숫자·출처 전문은 프로필 링크 뉴스레터에서</div>
</div>""", "#FFFFFF")


def build(d, font_css):
    """(html, 파일명 목록). 형식 2(H PICK 이 있는) 데일리 호에서만 쓴다."""
    frames = [hook(d), number(d), answer(d), cta(d)]
    files = [f"r{i}_{name}.png" for i, name in enumerate(REEL_FRAMES, 1)]
    page = f"""<!DOCTYPE html><html lang="ko"><head><meta charset="UTF-8">
<style>{font_css}
{CSS}
{FRAME_CSS}</style></head><body>
{''.join(frames)}
</body></html>"""
    return page, files
