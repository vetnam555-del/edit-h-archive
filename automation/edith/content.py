"""content/YYYY-MM-DD.json 을 읽고 검증한 뒤, 빌드에 필요한 파생값(VOL·요일·번호 등)을 채운다."""
import json
import re

from .common import CONTENT_DIR, MANIFEST, ROOT, parse_date, plain, source_label, weekday_ko


class ContentError(ValueError):
    pass


# 카드 한 장에 들어가는 글자 수 상한(공백·마크업 제외). 넘치면 렌더러가 폰트를 줄이는데,
# 그 전에 여기서 먼저 막아 '글이 빽빽한 카드'를 원천적으로 줄인다. 기준은 VOL.092 카드 + 개선안(B) 실측.
CARD_LIMITS = {
    "cover_title": 34,       # 표지 두 줄 제목 합계
    "number": 9,             # 이슈 카드의 큰 숫자 (예: 300억원, 8.9조원, 82%)
    "headline": 26,          # 이슈 카드 제목 (두 줄)
    "body": 80,              # 이슈 카드 본문 — 1~2문장 (키트 본문 9 권장은 1문장)
    "keyword": 5,            # 표지 대형 핵심어 (예: 8월, 새벽배송, 82%)
    "metric_value": 8,       # 보조 수치 상자 값 (예: 11.9%)
    "metric_label": 16,      # 보조 수치 상자 설명
    "takeaway": 60,          # 인사이트 상자
    "cta_headline": 34,      # 마무리 카드 질문
    "lead_point_title": 22,  # 뉴스레터 '오늘의 편지' 핵심 3개
    "lead_point_text": 40,
}
CARD_ISSUES = 6


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


def _card_issues(data, where):
    """cards.issues(정확히 6개) → 카드용 이슈 목록. no 로 뉴스레터 이슈(1=빅이슈, 2~10)를 가리키고,
    tag·출처는 그 이슈에서 가져온다(카드에 따로 쓰면 그 값을 쓴다)."""
    cards = data.get("cards") or {}
    issues = cards.get("issues") or []
    if len(issues) != CARD_ISSUES:
        raise ContentError(f"{where}: cards.issues 는 정확히 {CARD_ISSUES}개여야 합니다(지금 {len(issues)}개) — "
                           "뉴스레터 10개 중 카드로 만들 6개를 고르세요")
    by_no = {int(it["no"]): it for it in data["all_items"]}
    seen, out = set(), []
    for i, ci in enumerate(issues, 1):
        w = f"{where} cards.issues[{i}]"
        no = int(_need(ci, "no", w))
        if no not in by_no:
            raise ContentError(f"{w}: no={no} 인 뉴스레터 이슈가 없습니다(1~10)")
        if no in seen:
            raise ContentError(f"{w}: no={no} 이슈가 두 번 들어갔습니다")
        seen.add(no)
        for key in ("headline", "body", "takeaway"):
            _need(ci, key, w)
        cmp = ci.get("compare")
        if cmp:
            for side in ("from", "to"):
                if not (cmp.get(side) or {}).get("value") or not cmp[side].get("label"):
                    raise ContentError(f"{w}: compare.{side} 에 value·label 이 모두 필요합니다")
        else:
            _need(ci, "number", w)
        metrics = ci.get("metrics") or []
        if len(metrics) > 3:
            raise ContentError(f"{w}: metrics 는 3개 이하로 쓰세요(큰 숫자와 같은 값을 빼고 최대 2개가 상자로 나갑니다)")
        for m in metrics:
            if not m.get("value") or not m.get("label"):
                raise ContentError(f"{w}: metrics 의 각 항목에 value·label 이 모두 필요합니다")
        src = by_no[no]
        out.append({**ci, "no": no, "tag": ci.get("tag") or src["tag"],
                    "source": ci.get("source") or source_label(src["sources"])})
    if sum(1 for it in out if it.get("accent")) > 1:
        raise ContentError(f"{where}: accent(H PICK)는 한 장에만 쓰세요")
    return out


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

    data["card_issues"] = _card_issues(data, where)
    cards = data["cards"]
    cards.setdefault("cover", {})
    cards["cover"].setdefault("title", data["hero_title"])
    if not cards["cover"].get("keyword"):
        # 표지 핵심어 기본값: hero_title 의 ==강조== 첫 단어, 없으면 첫 카드의 큰 숫자
        m = re.search(r"==(.+?)==", data["hero_title"])
        first = data["card_issues"][0]
        cards["cover"]["keyword"] = m.group(1) if m else (first.get("number") or first["compare"]["to"]["value"])
    if cards["cover"].get("photo") and not (ROOT / cards["cover"]["photo"]).exists():
        raise ContentError(f"{where}: cards.cover.photo 파일이 없습니다 ({cards['cover']['photo']})")
    if cards["cover"].get("photo") and not cards["cover"].get("credit"):
        raise ContentError(f"{where}: 표지 사진을 쓰면 cards.cover.credit(출처·라이선스)이 필요합니다")
    cta = cards.setdefault("cta", {})
    cta.setdefault("kick", "오늘의 저장각")
    cta.setdefault("headline", data["question"]["text"])
    cta.setdefault("sub", "하나만 골라도 회의가 달라져요.")
    cta.setdefault("pill", "팔로우 + 저장해두기")

    problems = []
    _len_check(cards["cover"]["title"], CARD_LIMITS["cover_title"], "cards.cover.title(없으면 hero_title)", problems)
    _len_check(cards["cover"]["keyword"], CARD_LIMITS["keyword"], "cards.cover.keyword(없으면 hero_title 의 ==강조==)", problems)
    for i, it in enumerate(data["card_issues"], 1):
        w = f"cards.issues[{i}]"
        if "number" in it:
            _len_check(it["number"], CARD_LIMITS["number"], f"{w}.number", problems)
        _len_check(it["headline"], CARD_LIMITS["headline"], f"{w}.headline", problems)
        _len_check(it["body"], CARD_LIMITS["body"], f"{w}.body", problems)
        _len_check(it["takeaway"], CARD_LIMITS["takeaway"], f"{w}.takeaway", problems)
        for j, m in enumerate(it.get("metrics") or [], 1):
            _len_check(m["value"], CARD_LIMITS["metric_value"], f"{w}.metrics[{j}].value", problems)
            _len_check(m["label"], CARD_LIMITS["metric_label"], f"{w}.metrics[{j}].label", problems)
    _len_check(cta["headline"], CARD_LIMITS["cta_headline"], "cards.cta.headline(없으면 question.text)", problems)
    for i, p in enumerate(data.get("lead_points") or [], 1):
        _len_check(p["title"], CARD_LIMITS["lead_point_title"], f"lead_points[{i}].title", problems)
        _len_check(p["text"], CARD_LIMITS["lead_point_text"], f"lead_points[{i}].text", problems)
    if problems:
        raise ContentError("글자 수 초과:\n  - " + "\n  - ".join(problems))
    return data
