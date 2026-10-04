"""구독 선물(실험 E5, 2026-10-04~) — config.gift 와 automation/gifts/{slug}.json. 페이지는 automation/build_gift.py 가 만든다."""
import json

from .common import AUTOMATION, load_config, now_kst


def active_gift(day=None, cfg=None):
    """이 날짜(기본 오늘 KST)에 나눠 주는 선물 {title, slug, url, count} — 없거나 기간 밖이면 None."""
    cfg = cfg or load_config()
    g = cfg.get("gift") or {}
    day = str(day or now_kst().date().isoformat())[:10]
    if not g.get("slug") or not (g.get("from", "") <= day <= g.get("until", "")):
        return None
    data = json.loads((AUTOMATION / "gifts" / f"{g['slug']}.json").read_text(encoding="utf-8"))
    return {"title": data["title"], "slug": g["slug"], "count": sum(len(grp["items"]) for grp in data["groups"]),
            "url": f"{cfg['site_url'].rstrip('/')}/gift/{g['slug']}.html"}
