"""manifest.json · index.html · 카드뉴스 갤러리 페이지 갱신."""
import json
import re

from .common import INDEX, MANIFEST, esc, plain, send_time_ko


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


def gallery_page(d, site, card_files, caption):
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
    <button type="button" id="copy">캡션 복사</button>
    <pre id="cap">{esc(caption)}</pre>
  </section>
</main>
<script>
document.getElementById('copy').addEventListener('click', async (e) => {{
  const t = document.getElementById('cap').innerText;
  try {{ await navigator.clipboard.writeText(t); e.target.textContent = '복사됨 ✓'; }}
  catch (_) {{ const r = document.createRange(); r.selectNodeContents(document.getElementById('cap'));
    const s = getSelection(); s.removeAllRanges(); s.addRange(r); e.target.textContent = '길게 눌러 복사하세요'; }}
}});
</script>
</body>
</html>
"""


def instagram_caption(d, site):
    ig = d.get("instagram", {})
    if ig.get("caption"):
        body = ig["caption"].strip()
    else:
        lines = [plain(d["title"]), "", plain(d["lead"]), ""]
        lines += [f"{it['no']} {plain(it.get('title', d['title']))}" for it in d["all_items"]]
        body = "\n".join(lines)
    tags = ig.get("hashtags") or ["마케팅", "마케팅트렌드", "마케터", "브랜드마케팅", "카드뉴스", "EDITH"]
    tags = " ".join("#" + re.sub(r"\s+", "", t.lstrip("#")) for t in tags)
    when = send_time_ko(d["send_time_kst"]).replace("오전", "아침")
    return f"{body}\n\n📩 매 영업일 {when}, 뉴스레터로 받아보세요 — 프로필 링크\n{tags}"
