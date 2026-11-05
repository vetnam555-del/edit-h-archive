"""구독 선물(실험 E5, 2026-10-04~) — config.gift 와 automation/gifts/{slug}.json. 페이지는 automation/build_gift.py 가 만든다.

항목에 until(YYYY-MM-DD)이 있으면 그날까지만 '챙길 것'이다. LIVE_FROM 부터는 세는 수(첫 화면·캡션·환영 메일의 'N가지')도
아직 안 지난 항목만 센다 — 2026-11-05 구독 길 점검: 4분기 선물 18가지 중 4가지(청년미래적금 2차 신청 10/7~16 등)가 10월에 끝났는데
인스타 캡션은 날마다 '18가지'라고 했다. 그 전 날짜는 예전처럼 모두 센다(지난 호를 다시 빌드해도 게시된 캡션과 같게).
"""
import json

from .common import AUTOMATION, load_config, now_kst

LIVE_FROM = "2026-11-06"
# 릴스·웹툰 끝에 '구독하면 받는 것' 한 줄(2026-11-05 구독 길 점검 — 릴스는 비팔로워에게 주 2,800번 닿는데 끝 화면·캡션엔
# '숫자·출처 전문은 프로필 링크 뉴스레터에서'뿐이었고 14일 신청 0). 이 날짜 호부터 — 지난 호를 다시 만들어도 그대로이게.
PROMO_FROM = "2026-11-06"


def items(data):
    return [it for grp in data["groups"] for it in grp["items"]]


def live_items(data, day):
    """그 날짜에 아직 챙길 수 있는 항목 — until 이 지난 항목은 뺀다(until 이 없으면 선물 기간 내내)."""
    return [it for it in items(data) if not it.get("until") or str(day)[:10] <= it["until"]]


def active_gift(day=None, cfg=None):
    """이 날짜(기본 오늘 KST)에 나눠 주는 선물 {title, slug, url, count} — 없거나 기간 밖이면, 남은 항목이 없으면 None."""
    cfg = cfg or load_config()
    g = cfg.get("gift") or {}
    day = str(day or now_kst().date().isoformat())[:10]
    if not g.get("slug") or not (g.get("from", "") <= day <= g.get("until", "")):
        return None
    data = json.loads((AUTOMATION / "gifts" / f"{g['slug']}.json").read_text(encoding="utf-8"))
    count = len(live_items(data, day)) if day >= LIVE_FROM else len(items(data))
    if not count:
        return None
    return {"title": data["title"], "short": data.get("short") or data["title"], "slug": g["slug"], "count": count,
            "url": f"{cfg['site_url'].rstrip('/')}/gift/{g['slug']}.html"}


def screen_line(day, short=False):
    """그림 속 끝 문구(웹툰 끝 장·카드 릴스 끝 장, short 는 AI 릴스 끝 화면 큰 줄) — 숫자 없이 선물 이름만
    (화면 글 숫자 검사·글자 넘침을 피해서). PROMO_FROM 전 날짜나 선물이 없으면 예전 문구."""
    gift = active_gift(day) if str(day)[:10] >= PROMO_FROM else None
    if not gift:
        return "더 자세한 건 프로필 링크 뉴스레터에서!" if short else "숫자·출처 전문은 프로필 링크 뉴스레터에서"
    return f"구독하면 '{gift['short']}' 선물부터!" if short else f"프로필 링크에서 구독하면 '{gift['short']}' 선물부터"
