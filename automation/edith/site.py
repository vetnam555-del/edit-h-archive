"""manifest.json · index.html · 카드뉴스 갤러리 페이지 갱신."""
import json
import re

from .common import load_config, INDEX, MANIFEST, esc, plain, send_time_ko


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
        "published_at_kst": f"{d['date']}T{publish_time}:00+09:00",
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


def instagram_caption(d, site):
    """뉴닉식 캡션: 질문형 첫 줄 + 대화체 요약 → 오늘의 N가지 목록 → 저장·댓글 유도 → 구독 안내 → 해시태그.

    content 의 instagram.caption 에는 '첫 줄 훅 + 2~3문장 요약'만 쓴다. 나머지는 여기서 붙인다.
    """
    ig = d.get("instagram", {})
    issues = d["card_issues"]
    head = (ig.get("caption") or "").strip() or f"{plain(d['title'])}\n\n{plain(d['lead'])}"
    lines = [head, "", f"{d['weekday']}요일의 마케팅 브리프 {len(issues)}가지 👇"]
    lines += [f"{'❶❷❸❹❺❻❼❽❾❿'[i]} {plain(it['headline'])}" for i, it in enumerate(issues)]
    lines += ["", "📌 저장해두고 회의 전에 꺼내보세요", f"💬 {plain(d['question']['text'])} 댓글로 알려주세요", ""]
    cov = (d.get("cards") or {}).get("cover") or {}
    if cov.get("photo") and cov.get("credit"):
        lines.append(f"📷 표지 사진 출처: {cov['credit'].replace('사진 = ', '')}")
    kw = (load_config().get("instagram") or {}).get("dm_keyword")
    if kw:
        lines.append(f"📩 댓글에 '{kw}' 남기면 뉴스레터 구독 링크를 DM으로 보내드려요")
    when = send_time_ko(d["send_time_kst"]).replace("오전", "아침")
    lines.append(f"매 영업일 {when}, {len(d['all_items'])}가지 전문과 출처는 뉴스레터로 — 프로필 링크")
    lines.append("EDIT H · 매일 아침, 마케터의 트렌드 한 입 (@edit.h.kr)")
    lines.append("/ 에디터. H")
    tags = ig.get("hashtags") or ["마케팅", "마케팅트렌드", "마케터", "브랜드마케팅", "카드뉴스", "EDITH"]
    lines.append(" ".join("#" + re.sub(r"\s+", "", t.lstrip("#")) for t in tags))
    return "\n".join(lines)


def first_comment(d):
    """올린 직후 계정으로 달아 고정할 첫 댓글(마트식 팔로우 안내)."""
    kw = (load_config().get("instagram") or {}).get("dm_keyword")
    lines = ["매일 아침, 마케터의 트렌드 한 입 — EDIT H @edit.h.kr 팔로우하고 저장해 두세요 🧡"]
    if kw:
        lines.append(f"📩 '{kw}' 댓글 남기면 뉴스레터 구독 링크를 DM으로 보내드려요")
    return "\n".join(lines)
