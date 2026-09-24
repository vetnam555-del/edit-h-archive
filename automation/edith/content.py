"""content/YYYY-MM-DD.json 을 읽고 검증한 뒤, 빌드에 필요한 파생값(VOL·요일·번호 등)을 채운다."""
import json
import re

from .common import CONTENT_DIR, MANIFEST, parse_date, plain, weekday_ko


class ContentError(ValueError):
    pass


# 카드 한 장에 들어가는 글자 수 상한(공백 포함). 넘치면 렌더러가 폰트를 줄이는데,
# 그 전에 여기서 먼저 막아 '글이 빽빽한 카드'를 원천적으로 줄인다.
CARD_LIMITS = {
    "cover_title": 34,
    "feature_text": 150,
    "pick_text": 130,
    "takeaway": 110,
    "lead_point_title": 22,
    "lead_point_text": 40,
}


def _need(obj, key, where):
    if key not in obj or obj[key] in (None, "", []):
        raise ContentError(f"{where}: '{key}' 필드가 비어 있습니다")
    return obj[key]


def _check_sources(sources, where):
    if not sources:
        raise ContentError(f"{where}: sources 가 비어 있습니다 — 사실마다 원문 링크가 필요합니다")
    for s in sources:
        _need(s, "name", where)
        url = _need(s, "url", where)
        if not re.match(r"^https?://", url):
            raise ContentError(f"{where}: 출처 URL 형식이 이상합니다 ({url})")


def _len_check(text, limit, where, problems):
    n = len(plain(text))
    if n > limit:
        problems.append(f"{where}: {n}자 → {limit}자 이하로 줄여주세요")


def next_vol(date_str):
    """manifest 기준 다음 VOL. 같은 날짜가 이미 있으면 그 VOL 을 그대로 쓴다(재빌드)."""
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for issue in manifest["issues"]:
        if issue["date"] == date_str:
            return issue["vol"]
    last = max(int(i["vol"]) for i in manifest["issues"])
    return f"{last + 1:03d}"


def load(date_str):
    path = CONTENT_DIR / f"{date_str}.json"
    if not path.exists():
        raise ContentError(f"{path} 가 없습니다")
    data = json.loads(path.read_text(encoding="utf-8"))
    return prepare(data, date_str)


def prepare(data, date_str):
    where = f"content/{date_str}.json"
    if data.get("date") != date_str:
        raise ContentError(f"{where}: date 필드({data.get('date')})가 파일명과 다릅니다")
    d = parse_date(date_str)
    for key in ("title", "subtitle", "lead", "observation", "big_issue", "sections", "question"):
        _need(data, key, where)

    three = _need(data, "three_lines", where)
    if len(three) != 3:
        raise ContentError(f"{where}: three_lines 는 정확히 3개여야 합니다")

    big = data["big_issue"]
    for key in ("tag", "paragraphs", "stat", "takeaway"):
        _need(big, key, f"{where} big_issue")
    _check_sources(big.get("sources"), f"{where} big_issue")

    items = []
    for si, sec in enumerate(data["sections"], 1):
        _need(sec, "label", f"{where} sections[{si}]")
        _need(sec, "title", f"{where} sections[{si}]")
        for it in _need(sec, "items", f"{where} sections[{si}]"):
            w = f"{where} sections[{si}] '{it.get('title', '?')}'"
            for key in ("tag", "title", "body", "takeaway"):
                _need(it, key, w)
            _check_sources(it.get("sources"), w)
            items.append(it)
    if len(items) != 9:
        raise ContentError(f"{where}: 섹션 아이템은 모두 9개여야 합니다(빅이슈 01 + 02~10). 지금 {len(items)}개")

    # 번호: 빅이슈가 01, 섹션 아이템이 02~10 (빅이슈를 목록에서 다시 반복하지 않는다)
    big["no"] = "01"
    for n, it in enumerate(items, 2):
        it["no"] = f"{n:02d}"

    data["vol"] = data.get("vol") or next_vol(date_str)
    data["weekday"] = weekday_ko(d)
    data["date_obj"] = d
    data.setdefault("read_minutes", 7)
    data.setdefault("emoji", "🧭")
    data.setdefault("briefs", [])
    data.setdefault("keywords", [big["tag"]] + [it["tag"] for it in items[:4]])
    if "hero_title" not in data:
        # '토스가 이번엔, 새벽배송을 품었다고?' → 쉼표 뒤에서 줄바꿈
        t = data["title"]
        data["hero_title"] = t.replace(", ", ",\n", 1) if ", " in t else t
    data["items"] = items
    data["all_items"] = [big] + items

    # 카드뉴스 픽: 지정이 없으면 섹션마다 첫 아이템
    picks = data.get("card_picks")
    if picks:
        by_no = {int(it["no"]): it for it in items}
        try:
            data["pick_items"] = [by_no[int(p)] for p in picks]
        except KeyError as e:
            raise ContentError(f"{where}: card_picks 의 번호 {e} 가 02~10 범위를 벗어났습니다")
    else:
        # 섹션마다 첫 아이템, 섹션이 3개보다 적으면 남은 아이템으로 채운다
        picks = [sec["items"][0] for sec in data["sections"]][:3]
        for it in items:
            if len(picks) >= 3:
                break
            if it not in picks:
                picks.append(it)
        data["pick_items"] = picks

    problems = []
    _len_check(data.get("cover_title", data["hero_title"]), CARD_LIMITS["cover_title"], "cover_title(또는 hero_title)", problems)
    _len_check(big.get("card_text", big["paragraphs"][0]), CARD_LIMITS["feature_text"], "big_issue.card_text(없으면 첫 문단)", problems)
    _len_check(big["takeaway"], CARD_LIMITS["takeaway"] * 2, "big_issue.takeaway", problems)
    for it in data["pick_items"]:
        card = it.get("card", {})
        _len_check(card.get("text", it["body"]), CARD_LIMITS["pick_text"], f"{it['no']} card.text(없으면 body)", problems)
        _len_check(card.get("takeaway", it["takeaway"]), CARD_LIMITS["takeaway"], f"{it['no']} card.takeaway(없으면 takeaway)", problems)
    for i, p in enumerate(data.get("lead_points") or [], 1):
        _len_check(p["title"], CARD_LIMITS["lead_point_title"], f"lead_points[{i}].title(표지 카드)", problems)
        _len_check(p["text"], CARD_LIMITS["lead_point_text"], f"lead_points[{i}].text(표지 카드)", problems)
    if problems:
        raise ContentError("카드 글자 수 초과:\n  - " + "\n  - ".join(problems))
    return data
