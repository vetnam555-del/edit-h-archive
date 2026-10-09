"""manifest.json · index.html · 카드뉴스 갤러리 페이지 갱신."""
import json
import re

from .common import load_config, INDEX, MANIFEST, ROOT, esc, plain, send_time_ko
from .gift import active_gift


def update_manifest(d, site, n_cards, publish_time):
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    sources = {s["url"] for it in d["all_items"] for s in it["sources"]}
    entry = {
        "vol": d["vol"],
        "date": d["date"],
        "weekday": d["weekday"],
        "emoji": d["emoji"],
        "title": plain(d["title"]),
        "subtitle": plain(d["subtitle"]),
        "filename": f"{d['date']}.html",
        "type": "daily",
        "key_keywords": d["keywords"][:5],
        "source_count": len(sources),
        "source_mode": d.get("source_mode", "fallback"),
        # 예비 호는 원고에 실제로 만든 시각(08:05 뒤)이 있다 — manifest·RSS pubDate 도 그 시각으로(Codex 리뷰)
        "published_at_kst": d.get("published_at_kst") or f"{d['date']}T{publish_time}:00+09:00",
        "public_url": f"{site}/{d['date']}.html",
        "card_count": n_cards,
        "cards_url": f"{site}/instagram/{d['date']}/" if n_cards else None,
    }
    issues = [i for i in manifest["issues"] if i["date"] != d["date"]]
    issues.append(entry)
    issues.sort(key=lambda i: i["date"])
    manifest["issues"] = issues
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def _index_item(i):
    return (
        f'  <a href="{i["filename"]}" class="item">\n'
        f'    <div class="meta"><span class="vol">VOL.{i["vol"]}</span><span>{i["date"]} ({i["weekday"]})</span></div>\n'
        f'    <div class="title"><span class="ico">{i.get("emoji", "🧭")}</span> {esc(i["title"])}</div>\n'
        f'    <div class="subtitle">{esc(i["subtitle"])}</div>\n'
        f"  </a>\n"
    )


def regenerate_index(manifest):
    """'지난 뉴스레터' 목록만 manifest 로 다시 쓴다. 나머지(헤더·CTA·푸터)는 그대로 둔다."""
    html = INDEX.read_text(encoding="utf-8")
    start_marker = "<h2>📰 지난 뉴스레터</h2>\n"
    end_marker = '\n  <div class="footer">'
    s = html.index(start_marker) + len(start_marker)
    e = html.index(end_marker, s)
    items = "\n".join(_index_item(i) for i in reversed(manifest["issues"]))
    INDEX.write_text(html[:s] + "  \n" + items + "\n" + html[e:], encoding="utf-8")


FEED = ROOT / "feed.xml"
SITEMAP = ROOT / "sitemap.xml"
FEED_ITEMS = 30


def _pub(i):
    return i.get("published_at_kst") or f"{i['date']}T08:00:00+09:00"


def write_feeds(manifest, site):
    """feed.xml(RSS 2.0, 최근 30호)·sitemap.xml(아카이브·구독 페이지·모든 호). 빌드할 때마다 manifest 로 다시 쓴다.
    RSS 로 받아보거나 검색에 잡히게 하려는 것 — 공개 저장소에 이미 있는 제목·부제·주소만 쓴다."""
    import datetime as dt
    from email.utils import format_datetime
    issues = sorted(manifest["issues"], key=lambda i: i["date"])
    # RSS 는 실제 발행 시각 순 — 지난 날짜로 늦게 낸 예비 호도 새 글로 맨 위에(Codex 리뷰). 사이트맵은 날짜 순 그대로
    by_pub = sorted(manifest["issues"], key=lambda i: dt.datetime.fromisoformat(_pub(i)))
    now = format_datetime(dt.datetime.fromisoformat(_pub(by_pub[-1]))) if by_pub else ""
    items = []
    for i in reversed(by_pub[-FEED_ITEMS:]):
        url = i.get("public_url") or f"{site}/{i['filename']}"
        title = f"VOL.{i['vol']} {plain(i['title'])}"
        items.append(
            "  <item>\n"
            f"    <title>{esc(title)}</title>\n"
            f"    <link>{esc(url)}</link>\n"
            f"    <guid isPermaLink=\"true\">{esc(url)}</guid>\n"
            f"    <pubDate>{format_datetime(dt.datetime.fromisoformat(_pub(i)))}</pubDate>\n"
            f"    <description>{esc(plain(i.get('subtitle', '')))}</description>\n"
            "  </item>")
    FEED.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">\n<channel>\n'
        "  <title>EDIT H — 매일 아침, 트렌드 한 입</title>\n"
        f"  <link>{site}/</link>\n"
        f'  <atom:link href="{site}/feed.xml" rel="self" type="application/rss+xml"/>\n'
        "  <description>매일 아침 8시, 확인된 숫자로 읽는 트렌드 뉴스레터</description>\n"
        "  <language>ko</language>\n"
        f"  <lastBuildDate>{now}</lastBuildDate>\n"
        + "\n".join(items) + "\n</channel>\n</rss>\n", encoding="utf-8")

    urls = [(f"{site}/", issues[-1]["date"] if issues else None), (f"{site}/subscribe.html", None)]
    urls += [(i.get("public_url") or f"{site}/{i['filename']}", i["date"]) for i in reversed(issues)]
    rows = "\n".join(f"  <url><loc>{esc(u)}</loc>" + (f"<lastmod>{d}</lastmod>" if d else "") + "</url>" for u, d in urls)
    SITEMAP.write_text('<?xml version="1.0" encoding="UTF-8"?>\n'
                       '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + rows + "\n</urlset>\n",
                       encoding="utf-8")


def gallery_page(d, site, card_files, caption, comment=""):
    """instagram/YYYY-MM-DD/index.html — 휴대폰에서 카드 저장·캡션 복사 후 바로 업로드할 수 있는 페이지."""
    imgs = "\n".join(
        f'<figure><a href="{f}" download><img src="{f}" alt="카드 {n:02d}/{len(card_files):02d}" loading="lazy"></a>'
        f'<figcaption>{n:02d} / {len(card_files):02d} · <a href="{f}" download>저장</a></figcaption></figure>'
        for n, f in enumerate(card_files, 1)
    )
    title = plain(d["title"])
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="robots" content="noindex">
<title>EDIT H 카드뉴스 VOL.{d['vol']}</title>
<meta property="og:title" content="[EDIT H 카드뉴스] {esc(title)}">
<meta property="og:image" content="{site}/instagram/{d['date']}/{card_files[0]}">
<style>
  :root {{ --ink:#282F38; --paper:#F3F3F3; --acc:#B23A0F; --muted:#6B6E75; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--paper); color:var(--ink); font-family:'Pretendard','Apple SD Gothic Neo','Malgun Gothic',sans-serif; }}
  main {{ max-width:560px; margin:0 auto; padding:28px 16px 60px; }}
  .kicker {{ font-size:12px; font-weight:800; letter-spacing:2px; color:var(--acc); }}
  h1 {{ font-size:24px; line-height:1.4; margin:8px 0 4px; word-break:keep-all; }}
  .meta {{ font-size:13px; color:var(--muted); }}
  figure {{ margin:22px 0 0; }}
  figure img {{ width:100%; height:auto; display:block; border-radius:4px; box-shadow:0 2px 10px rgba(0,0,0,.10); }}
  figcaption {{ font-size:12px; color:var(--muted); margin-top:6px; text-align:right; }}
  figcaption a, .links a {{ color:var(--acc); font-weight:700; }}
  .caption {{ margin-top:30px; background:#fff; border:1px solid #EAEAEA; border-radius:12px; padding:16px; }}
  .caption pre {{ white-space:pre-wrap; word-break:keep-all; font-family:inherit; font-size:14px; line-height:1.7; margin:10px 0 0; }}
  button {{ font:inherit; font-size:14px; font-weight:800; background:var(--ink); color:#fff; border:0; border-radius:100px; padding:10px 18px; cursor:pointer; }}
  button:focus-visible, a:focus-visible {{ outline:3px solid #2563EB; outline-offset:2px; }}
  .links {{ margin-top:18px; font-size:14px; }}
</style>
</head>
<body>
<main>
  <div class="kicker">EDIT H · CARD NEWS · VOL.{d['vol']}</div>
  <h1>{esc(title)}</h1>
  <div class="meta">{d['date']} ({d['weekday']}) · {len(card_files)}장 · 1080×1350</div>
  <div class="links"><a href="../../{d['date']}.html">뉴스레터 전문 읽기 →</a></div>
  {imgs}
  <section class="caption">
    <button type="button" class="copy" data-target="cap">캡션 복사</button>
    <pre id="cap">{esc(caption)}</pre>
  </section>
  <section class="caption">
    <button type="button" class="copy" data-target="cmt">첫 댓글 복사</button> <span class="meta">올린 직후 계정으로 달고 고정하세요</span>
    <pre id="cmt">{esc(comment)}</pre>
  </section>
</main>
<script>
document.querySelectorAll('button.copy').forEach((btn) => btn.addEventListener('click', async (e) => {{
  const el = document.getElementById(btn.dataset.target);
  try {{ await navigator.clipboard.writeText(el.innerText); e.target.textContent = '복사됨 ✓'; }}
  catch (_) {{ const r = document.createRange(); r.selectNodeContents(el);
    const s = getSelection(); s.removeAllRanges(); s.addRange(r); e.target.textContent = '길게 눌러 복사하세요'; }}
}}));
</script>
</body>
</html>
"""


# 캡션이 날마다 같은 틀·같은 문장이면 사람이 쓴 글로 보이지 않는다(2026-09-25 사용자 피드백: 'AI 티').
# 그래서 고정 문구는 줄이고, 남는 몇 줄은 날짜에 따라 돌려 쓴다. 이모지로 줄을 시작하는 안내 줄·권유 문구·자기 계정 태그는 쓰지 않는다.
_LIST_HEAD = ["오늘 카드에 담은 이야기", "오늘 넘겨볼 {n}가지", "오늘은 이 {n}가지를 골랐어요"]
# 계정 주제어 '경제 뉴스레터'를 문장 안에 한 번(2026-10-09 운영자 자료: 인스타 검색은 캡션 글을 읽는다 — 해시태그 대신 문장으로)
_LETTER = [
    "출처랑 더 긴 이야기는 {when} 경제 뉴스레터에 있어요. 구독은 프로필 링크에서요.",
    "{when}마다 경제 뉴스레터로도 보내드려요. 출처까지 다 담아서요. (프로필 링크)",
    "경제 뉴스레터로 받아보시면 출처와 뒷이야기까지 볼 수 있어요. 매일 {when}, 프로필 링크에서 구독할 수 있어요.",
]
# 한 줄 뉴스가 있는 날(메인 5가지 + 한 줄 뉴스 = 10개 주제)은 메일에만 있는 한 줄 뉴스를 구독 이유로 알린다.
_LETTER_GIFT = [
    "구독 선물: '{title}'({n}가지) — 프로필 링크에서 경제 뉴스레터를 구독하면 환영 메일로 보내드려요.",
    "프로필 링크에서 구독하면 '{title}'({n}가지)부터 보내드려요. 경제 뉴스레터는 매일 {when}.",
    "경제 뉴스레터 구독 선물로 '{title}'({n}가지)를 준비했어요. 프로필 링크에서요.",
]
_LETTER_BRIEFS = [
    "경제 뉴스레터로 받아보시면 한 줄 뉴스 {n}개가 더 있어요. 매일 {when}, 구독은 프로필 링크에서요.",
    "경제 뉴스레터에는 한 줄 뉴스 {n}개와 출처까지 담았어요. {when}마다 보내드려요. (프로필 링크)",
    "출처랑 한 줄 뉴스 {n}개는 {when} 경제 뉴스레터에 있어요. 구독은 프로필 링크에서요.",
]
_REEL_TAIL = ["넘겨보는 카드는 피드에 올려뒀어요.", "카드 전체는 피드 게시물에 있어요.", "자세한 숫자는 피드 카드에서 볼 수 있어요."]
# 저녁 릴스(config.instagram.reel_evening_from~): 짧은 영상 → 아침 카드 → 뉴스레터로 이어지게(머니그라피의 숏폼 → 본편 고리)
_REEL_TAIL_EVENING = ["나머지 {n}가지는 아침에 올린 카드에 있어요.", "같은 날 아침 카드 게시물에 {n}가지가 더 있어요.",
                      "아침에 올린 카드에서 나머지 {n}가지도 볼 수 있어요."]
_SERIES_LINE = ["매주 {wd}요일은 「{name}」 — 다음 편도 {wd}요일 아침에 올려요.", "「{name}」 매주 {wd}요일 연재 — 다음 편도 {wd}요일 아침에요.",
                "{wd}요일마다 「{name}」 한 편씩 — 다음 편은 다음 주 {wd}요일이에요."]
# 누구나 붙이는 넓은 태그는 스팸처럼 보여 뺀다. 주제 태그 위주로 4개 + 브랜드 태그.
_GENERIC_TAGS = {"트렌드", "트렌드뉴스", "뉴스브리핑", "경제뉴스", "소비트렌드", "카드뉴스", "뉴스", "이슈", "시사", "정보", "꿀팁",
                 "주간트렌드", "오늘의뉴스", "데일리뉴스"}


def _pick(options, d):
    """날짜마다 다른 문구를 고른다(같은 날은 늘 같은 문구)."""
    y, m, dd = (int(x) for x in d["date"][:10].split("-"))   # 주간 특집 키('…-weekly')도 날짜 부분만
    return options[(y * 372 + m * 31 + dd) % len(options)]


def _when(d):
    return send_time_ko(d["send_time_kst"]).replace("오전", "아침")   # '아침 8시'


def _tags(d, spec_tags, limit=4):
    tags, seen = [], set()
    for t in list(spec_tags or []) + list(d.get("keywords") or []):
        t = re.sub(r"\s+", "", plain(t).lstrip("#"))
        if t and t not in _GENERIC_TAGS and t.upper() != "EDITH" and t not in seen:
            seen.add(t)
            tags.append(t)
    return " ".join("#" + t for t in tags[:limit] + ["EDITH"])


# E6(2026-10-10~): 이 소식이 필요한 사람에게 보내 달라는 한 줄 — 인스타는 DM 공유(도달당 보내기)를 비팔로워 확산의 가장 큰 신호로 본다.
# 9/25~10/8 14호 내내 공유·저장 0. 누구에게 보낼지(content instagram.share_to)를 콕 집어야 '공유해 주세요' 같은 빈말이 안 된다.
_SHARE = ["{who}에게 이 글 보내 주세요.", "{who}한테 보내 주면 도움이 될 거예요.", "주변에 {who} 있으면 보내 주세요."]


def _share(d):
    who = plain((d.get("instagram") or {}).get("share_to") or "").strip()
    return [_pick(_SHARE, d).format(who=who)] if who else []


def _ask(d):
    """독자에게 건네는 질문 한 줄. 투표가 있으면 투표 안내(댓글 A/B 를 tally_poll.py 가 센다)."""
    if d.get("poll"):
        q = d["poll"]
        return [f"이번 주 투표도 있어요. {plain(q['question'])}",
                f"A. {plain(q['options'][0])}", f"B. {plain(q['options'][1])}",
                "댓글에 A나 B만 남겨주셔도 돼요. 결과는 금요일에 알려드릴게요."]
    ig = d.get("instagram") or {}
    text = plain(ig.get("ask") or (d.get("question") or {}).get("text") or "").strip()
    return [text] if text else []


def instagram_caption(d, site):
    """에디터가 직접 쓴 듯한 캡션: 훅 + 대화체 요약(content) → 오늘의 N가지 → 독자에게 한 질문 → 뉴스레터 한 줄 → 서명 → 해시태그.

    content 의 instagram.caption 에는 '첫 줄 훅 + 2~3문장 요약'만 쓴다(RUNBOOK '캡션 문체'). 나머지는 여기서 붙인다.
    """
    ig = d.get("instagram", {})
    issues = d["card_issues"]
    head = (ig.get("caption") or "").strip() or f"{plain(d['title'])}\n\n{plain(d['lead'])}"
    lines = [head, "", _pick(_LIST_HEAD, d).format(n=len(issues))]
    lines += [f"{i}. {plain(it['headline'])}" for i, it in enumerate(issues, 1)]
    ask = _ask(d) + _share(d)
    if ask:
        lines += ["", *ask]
    if dm_line():
        lines += ["", dm_line()]
    # 표지 사진·음악 출처는 캡션에 쓰지 않는다(2026-09-25 요청) — 사진 출처는 표지 카드 안에, 음악 출처는 릴스 영상 안에 있다.
    n_briefs = len(d.get("briefs") or [])
    letter = (_pick(_LETTER_BRIEFS, d).format(n=n_briefs, when=_when(d)) if n_briefs
              else _pick(_LETTER, d).format(when=_when(d)))
    gift = active_gift(d["date"])
    if gift:   # 구독 선물(E5) 기간엔 뉴스레터 한 줄 대신 선물 안내 — 구독할 '지금 당장의 이유'
        letter = _pick(_LETTER_GIFT, d).format(title=gift["title"], n=gift["count"], when=_when(d))
    if d.get("series"):   # 고정 연재 날: 다음 편 예고(같은 요일·같은 이름 — 기다릴 이유)
        lines += ["", _pick(_SERIES_LINE, d).format(wd=d["weekday"], name=d["series"]["name"])]
    lines += ["", letter, "— 에디터 H", "", _tags(d, ig.get("hashtags"))]
    return "\n".join(lines)


def _evening_reel(d):
    """이 호의 릴스를 저녁에 따로 올리는가(ig_plan.evening_reel 과 같은 기준 — 아침 카드가 먼저 올라가 있다)."""
    ig = load_config().get("instagram") or {}
    start = ig.get("reel_evening_from")
    return bool(ig.get("reel_time_kst") and start and str(d["date"])[:10] >= start and "weekly" not in str(d["date"]))


def reel_caption(d):
    """릴스 캡션(음악 출처는 게시할 때 post_instagram.py 가 해시태그 앞에 넣는다). 훅 + 요약 첫 문장 + 피드 안내."""
    ig = d.get("instagram", {})
    head = (ig.get("caption") or "").strip() or f"{plain(d['title'])}\n\n{plain(d['lead'])}"
    parts = [p.strip() for p in head.split("\n\n") if p.strip()]
    hook = parts[0].splitlines()[0]
    teaser = ""
    if len(parts) > 1:
        m = re.match(r"(.+?[.?!])(\s|$)", parts[1].replace("\n", " "))
        teaser = (m.group(1) if m else parts[1]).strip()
    tail = (_pick(_REEL_TAIL_EVENING, d).format(n=len(d["card_issues"]) - 1) if _evening_reel(d)
            else _pick(_REEL_TAIL, d))
    lines = [hook, ""] + ([teaser] if teaser else []) + [tail, *_share(d), _tags(d, ig.get("hashtags"), limit=3)]
    return "\n".join(lines)


ALT_MAX = 1000   # 인스타 API alt_text 한도


def alt_texts(report):
    """캐러셀 장마다 인스타 대체 텍스트(alt_text) {jpg 파일명: 글} — 카드에 적힌 글자 그대로(render_cards.cjs 의 text).
    화면 낭독기와 인스타 검색이 그림 속 글자를 읽게 한다. 꾸밈 글자(로고·장 번호·되풀이된 큰 숫자·줄바꿈 방지 문자)는 뺀다."""
    out = {}
    for i, c in enumerate(report, 1):
        lines = []
        for ln in (c.get("text") or "").replace("\u2060", "").splitlines():
            ln = " ".join(ln.split())
            if not ln or ln in ("EDIT H.", "“", "”") or ln.isdigit() or ln in lines:
                continue
            lines.append(ln)
        if lines and c.get("file"):
            head = f"EDIT H 경제 뉴스 카드 {i}/{len(report)} — "
            out[c["file"].replace(".png", ".jpg")] = (head + " ".join(lines))[:ALT_MAX]
    return out


def dm_line(short=False):
    """'댓글 남기면 DM' 안내. DM 자동 답장(config.instagram.dm_auto_reply)이 켜져 있을 때만 약속하고, 아니면 None."""
    ig = load_config().get("instagram") or {}
    kw = ig.get("dm_keyword")
    if not (kw and ig.get("dm_auto_reply")):
        return None
    return (f"📩 '{kw}' 댓글 남기면 뉴스레터 구독 링크를 DM으로 보내드려요" if short
            else f"📩 댓글에 '{kw}' 남기면 뉴스레터 구독 링크를 DM으로 보내드려요")


def first_comment(d):
    """올린 직후 계정으로 다는 첫 댓글 — 카드에 쓴 자료의 출처 모음(홍보 문구 대신 쓸모 있는 정보).
    주소(URL)는 인스타 댓글에서 눌리지 않아 매체 이름·날짜만 적는다. 원문 링크는 뉴스레터에 있다."""
    rows = []
    for i, it in enumerate(d.get("card_issues") or [], 1):
        src = plain(it.get("source") or "").replace("\u2060", "").strip()
        if src:
            rows.append(f"{i}. {src}")
    if not rows:
        return dm_line(short=True) or ""
    return "\n".join([_pick(["카드에 쓴 자료 출처 모아둘게요", "오늘 카드 출처예요", "출처는 여기 정리해둘게요"], d), *rows])
