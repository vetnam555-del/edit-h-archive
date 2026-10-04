#!/usr/bin/env python3
"""구독 선물 페이지 — automation/gifts/{slug}.json → gift/{slug}.html (2026-10-04 주간 루틴, 실험 E5).

10/4 주간 진단: 팔로워는 한 주에 47→107 로 늘었는데 최근 14일 구독 신청은 0건이었다. 구독할 '지금 당장의 이유'를 만든다 —
발행한 호에서 원 기사로 확인한 사실만 모은 날짜별 체크리스트를 환영 메일로 보내고(sync_subscribers.welcome_message),
구독 페이지·인스타 캡션에서 알린다. 항목마다 그 호 페이지로 이어져 출처를 볼 수 있다.

  python3 automation/build_gift.py            # config.gift 의 slug 로 만든다
  python3 automation/build_gift.py 2026-q4
"""
import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from edith.common import AUTOMATION, ROOT, load_config  # noqa: E402

GIFTS = AUTOMATION / "gifts"
OUT = ROOT / "gift"


def render(data, site):
    esc = html.escape
    groups = []
    for grp in data["groups"]:
        rows = "".join(
            f'<li><label><input type="checkbox"><span class="when">{esc(it["when"])}</span>'
            f'<span class="do">{esc(it["do"])}</span></label>'
            f'<p class="detail">{esc(it["detail"])} <a href="{site}/{it["issue"]}.html">출처·원문 →</a></p></li>'
            for it in grp["items"])
        groups.append(f'<h2>{esc(grp["name"])}</h2><ul>{rows}</ul>')
    count = sum(len(grp["items"]) for grp in data["groups"])
    return f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="robots" content="noindex">
<title>{esc(data["title"])} — EDIT H</title>
<link rel="icon" href="../favicon.png">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Apple SD Gothic Neo','Pretendard','Malgun Gothic',-apple-system,sans-serif; background: #FAFAF7; color: #1A1A1A;
         line-height: 1.7; padding: 28px 16px; }}
  .card {{ max-width: 640px; margin: 0 auto; background: #FFF; padding: 40px 32px; }}
  .logo {{ font-size: 30px; font-weight: 900; letter-spacing: -1.5px; }} .logo .h {{ color: #B91C1C; }}
  .divider {{ height: 2px; background: #000; margin: 16px 0 24px; }}
  h1 {{ font-size: 25px; font-weight: 900; letter-spacing: -0.8px; line-height: 1.35; }}
  .sub {{ font-size: 15px; color: #555; margin-top: 6px; }}
  .note {{ font-size: 13px; color: #777; background: #F5F5EE; border-left: 4px solid #B91C1C; padding: 12px 16px; margin: 20px 0 8px; }}
  h2 {{ font-size: 17px; font-weight: 900; margin: 30px 0 6px; padding-bottom: 6px; border-bottom: 1px solid #DDD; }}
  ul {{ list-style: none; }}
  li {{ padding: 14px 0; border-bottom: 1px solid #EEE; }}
  label {{ display: flex; gap: 10px; align-items: baseline; cursor: pointer; }}
  input {{ width: 18px; height: 18px; flex: none; accent-color: #B91C1C; transform: translateY(3px); }}
  .when {{ flex: none; font-size: 12px; font-weight: 800; color: #B91C1C; min-width: 64px; }}
  .do {{ font-size: 16px; font-weight: 800; line-height: 1.45; }}
  label:has(input:checked) .do {{ text-decoration: line-through; color: #999; }}
  .detail {{ font-size: 14px; color: #444; margin: 6px 0 0 92px; }}
  .detail a {{ color: #B91C1C; font-weight: 700; text-decoration: none; white-space: nowrap; }}
  .foot {{ font-size: 13px; color: #888; margin-top: 28px; }}
  .foot a {{ color: #B91C1C; text-decoration: none; font-weight: 700; }}
  @media (max-width: 480px) {{ .card {{ padding: 28px 18px; }} .detail {{ margin-left: 28px; }} label {{ flex-wrap: wrap; }} .when {{ min-width: 0; }} }}
  @media print {{ body {{ background: #FFF; padding: 0; }} .card {{ padding: 0; }} .detail a {{ color: #444; }} }}
</style></head>
<body><div class="card">
  <div class="logo">EDIT<span class="h"> H</span></div>
  <div class="divider"></div>
  <h1>{esc(data["title"])}</h1>
  <p class="sub">{esc(data["subtitle"])} — {count}가지</p>
  <p class="note">EDIT H 구독자 선물이에요. 모두 뉴스레터에서 원 기사로 확인해 다룬 내용이고, 항목마다 그 호로 가면 출처가 있어요.
  {esc(data["as_of"].replace("-", "."))} 기준이라 신청 전엔 공식 사이트에서 한 번 더 확인하세요. 체크 표시는 이 화면에서만 보여요.</p>
  {''.join(groups)}
  <p class="foot">매일 아침 8시, 이런 '할 일이 있는 숫자'를 5가지씩 보내드려요 — <a href="{site}/subscribe.html?ref=gift">EDIT H 구독</a> · <a href="{site}/">지난 호 전체</a></p>
</div></body></html>
"""


def main():
    cfg = load_config()
    slug = sys.argv[1] if len(sys.argv) > 1 else (cfg.get("gift") or {}).get("slug")
    if not slug:
        sys.exit("config.gift.slug 가 없습니다")
    data = json.loads((GIFTS / f"{slug}.json").read_text(encoding="utf-8"))
    for grp in data["groups"]:
        for it in grp["items"]:
            if not (ROOT / f"{it['issue']}.html").exists():
                sys.exit(f"✗ '{it['do']}' 의 호 {it['issue']} 가 없습니다 — 발행한 호의 사실만 싣는다")
    OUT.mkdir(exist_ok=True)
    out = OUT / f"{slug}.html"
    out.write_text(render(data, cfg["site_url"].rstrip("/")), encoding="utf-8")
    print(f"✓ {out.relative_to(ROOT)} ({sum(len(g['items']) for g in data['groups'])}가지)")


if __name__ == "__main__":
    main()
