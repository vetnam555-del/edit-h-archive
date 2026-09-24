"""content/YYYY-MM-DD.json 을 읽고 검증한 뒤, 빌드에 필요한 파생값(VOL·요일·번호 등)을 채운다.

형식 2(2026-09-28~): H PICK 심층 1 + 아이템 4 = 5가지. 최상위 `items`(4개)로 알아본다.
형식 1(~2026-09-25): 빅이슈 1 + `sections` 아이템 9 = 10가지. 지난 호 재빌드·주간 특집을 위해 그대로 읽는다.
"""
import json
import re

from .common import AUTOMATION, CONTENT_DIR, MANIFEST, ROOT, cover_photo_problem, parse_date, plain, source_label, weekday_ko

POLLS_DIR = AUTOMATION / "polls"


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
    "observation": 90,       # H의 한 줄 관찰 카드(뉴스레터와 같은 문장)
    "lead_point_title": 22,  # 뉴스레터 '오늘의 편지' 핵심 3개
    "lead_point_text": 40,
    "deep_headline": 26,     # 형식 2: H PICK 심층 카드 제목
    "deep_point": 40,        # 형식 2: 심층 카드 요점(2~3개)
    "poll_option": 14,       # 투표 선택지 A·B
    "poll_question": 34,     # 투표 질문(마무리 카드에 크게)
    "poll_comment": 70,      # 투표 결과에 붙이는 에디터 H 한마디
}
CARD_ISSUES = {1: 6, 2: 5}   # 형식별 카드 이슈 수(형식 2 는 5가지 모두 카드로)
ITEMS = {1: 9, 2: 4}         # 형식별 H PICK(빅이슈) 뒤 아이템 수


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
    """cards.issues → 카드용 이슈 목록. no 로 뉴스레터 이슈(1=빅이슈/H PICK, 2~)를 가리키고,
    tag·출처는 그 이슈에서 가져온다(카드에 따로 쓰면 그 값을 쓴다).
    형식 1: 10개 중 6개를 고른다. 형식 2: 5가지 모두(1~5)를 카드로 만들고, 1번이 H PICK(검정 반전)이다."""
    cards = data.get("cards") or {}
    issues = cards.get("issues") or []
    fmt, total = data["format"], len(data["all_items"])
    want = CARD_ISSUES[fmt]
    if len(issues) != want:
        hint = "뉴스레터 10개 중 카드로 만들 6개를 고르세요" if fmt == 1 else "5가지(no 1~5)를 한 장씩 모두 쓰세요"
        raise ContentError(f"{where}: cards.issues 는 정확히 {want}개여야 합니다(지금 {len(issues)}개) — {hint}")
    if fmt == 2:
        if sorted(int(ci.get("no", 0)) for ci in issues) != list(range(1, 6)):
            raise ContentError(f"{where}: cards.issues 의 no 는 1~5 가 한 번씩이어야 합니다(형식 2 는 5가지 모두 카드)")
        issues = sorted(issues, key=lambda ci: int(ci["no"]))
        for ci in issues:
            ci["accent"] = int(ci["no"]) == 1   # H PICK = 1번, 하루 한 장
    by_no = {int(it["no"]): it for it in data["all_items"]}
    seen, out = set(), []
    for i, ci in enumerate(issues, 1):
        w = f"{where} cards.issues[{i}]"
        no = int(_need(ci, "no", w))
        if no not in by_no:
            raise ContentError(f"{w}: no={no} 인 뉴스레터 이슈가 없습니다(1~{total})")
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


def _poll(data, where):
    """투표(형식 2, 주 첫 호) 와 투표 결과(주 마지막 호) 검증. 결과 숫자는 사람이 적지 않고
    automation/polls/{id}.json(tally_poll.py 가 메일·인스타 댓글로 집계)에서 읽는다."""
    poll = data.get("poll")
    if poll:
        if data["format"] != 2:
            raise ContentError(f"{where}: poll 은 형식 2(5가지) 호에서만 씁니다")
        _need(poll, "question", f"{where} poll")
        opts = _need(poll, "options", f"{where} poll")
        if len(opts) != 2 or any(not str(o).strip() for o in opts):
            raise ContentError(f"{where} poll: options 는 정확히 2개(A·B)여야 합니다")
        poll["id"] = data["date"]
    res = data.get("poll_result")
    if res:
        pid = _need(res, "id", f"{where} poll_result")
        path = POLLS_DIR / f"{pid}.json"
        if not path.exists():
            raise ContentError(f"{where} poll_result: {path.relative_to(ROOT)} 집계 파일이 없습니다 — "
                               "check_today.py 의 poll_result 가 있을 때만 결과를 싣습니다")
        tally = json.loads(path.read_text(encoding="utf-8"))
        total = sum(tally["votes"].values())
        res["tally"] = {**tally, "total": total,
                        "pct": {k: round(v * 100 / total) if total else 0 for k, v in tally["votes"].items()}}


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
    fmt = 2 if "items" in data and "sections" not in data else 1
    data["format"] = fmt
    for key in ("title", "subtitle", "lead", "observation", "big_issue", "question", "sections" if fmt == 1 else "items"):
        _need(data, key, where)

    if fmt == 1:
        three = _need(data, "three_lines", where)
        if len(three) != 3:
            raise ContentError(f"{where}: three_lines 는 정확히 3개여야 합니다")

    big = data["big_issue"]
    for key in ("tag", "paragraphs", "stat", "takeaway") + (("why", "numbers") if fmt == 2 else ()):
        _need(big, key, f"{where} big_issue")
    _check_sources(big.get("sources"), f"{where} big_issue")
    if fmt == 2:
        if isinstance(big["why"], str):
            big["why"] = [big["why"]]
        if not 2 <= len(big["numbers"]) <= 3 or any(not n.get("value") or not n.get("label") for n in big["numbers"]):
            raise ContentError(f"{where} big_issue: numbers 는 value·label 을 갖춘 2~3개여야 합니다('숫자로 보면')")

    def _item_ok(it, w):
        for key in ("tag", "title", "body", "takeaway"):
            _need(it, key, w)
        _check_sources(it.get("sources"), w)

    items = []
    if fmt == 1:
        for si, sec in enumerate(data["sections"], 1):
            _need(sec, "label", f"{where} sections[{si}]")
            _need(sec, "title", f"{where} sections[{si}]")
            for it in _need(sec, "items", f"{where} sections[{si}]"):
                _item_ok(it, f"{where} sections[{si}] '{it.get('title', '?')}'")
                items.append(it)
    else:
        for it in data["items"]:
            _item_ok(it, f"{where} items '{it.get('title', '?')}'")
            items.append(it)
    if len(items) != ITEMS[fmt]:
        what = "섹션 아이템은 모두 9개(빅이슈 01 + 02~10)" if fmt == 1 else "items 는 정확히 4개(H PICK 01 + 02~05)"
        raise ContentError(f"{where}: {what}여야 합니다. 지금 {len(items)}개")
    if fmt == 2 and len(data.get("briefs") or []) > 2:
        raise ContentError(f"{where}: briefs(한 줄 뉴스)는 2개 이하로 — 형식 2 는 '한 입' 분량이 원칙입니다")

    # 번호: 빅이슈(H PICK)가 01, 나머지가 02~ (빅이슈를 목록에서 다시 반복하지 않는다)
    big["no"] = "01"
    for n, it in enumerate(items, 2):
        it["no"] = f"{n:02d}"

    data["vol"] = data.get("vol") or next_vol(date_str)
    data["weekday"] = weekday_ko(d)
    data["date_obj"] = d
    data.setdefault("read_minutes", 7 if fmt == 1 else 4)
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
    if fmt == 2:
        deep = cards.get("deep") or {}
        _need(deep, "headline", f"{where} cards.deep")
        pts = _need(deep, "points", f"{where} cards.deep")
        if not 2 <= len(pts) <= 3:
            raise ContentError(f"{where} cards.deep: points 는 2~3개여야 합니다('왜 중요해?' 요점)")
    _poll(data, where)
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
    if cards["cover"].get("photo") and (why := cover_photo_problem(cards["cover"]["photo"])):
        raise ContentError(f"{where}: {why}")
    cta = cards.setdefault("cta", {})
    cta.setdefault("kick", "오늘의 저장각")
    cta.setdefault("headline", data["question"]["text"])
    cta.setdefault("sub", "하나만 알아둬도 대화가 달라져요.")
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
    _len_check(data["observation"], CARD_LIMITS["observation"], "observation(관찰 카드)", problems)
    if fmt == 2:
        _len_check(cards["deep"]["headline"], CARD_LIMITS["deep_headline"], "cards.deep.headline", problems)
        for i, pt in enumerate(cards["deep"]["points"], 1):
            _len_check(pt, CARD_LIMITS["deep_point"], f"cards.deep.points[{i}]", problems)
        for j, n in enumerate(big["numbers"], 1):
            _len_check(n["value"], CARD_LIMITS["metric_value"], f"big_issue.numbers[{j}].value", problems)
            _len_check(n["label"], CARD_LIMITS["metric_label"], f"big_issue.numbers[{j}].label", problems)
    if data.get("poll"):
        _len_check(data["poll"]["question"], CARD_LIMITS["poll_question"], "poll.question", problems)
        for j, o in enumerate(data["poll"]["options"], 1):
            _len_check(o, CARD_LIMITS["poll_option"], f"poll.options[{j}]", problems)
    if data.get("poll_result"):
        _len_check(data["poll_result"].get("comment", ""), CARD_LIMITS["poll_comment"], "poll_result.comment", problems)
    for i, p in enumerate(data.get("lead_points") or [], 1):
        _len_check(p["title"], CARD_LIMITS["lead_point_title"], f"lead_points[{i}].title", problems)
        _len_check(p["text"], CARD_LIMITS["lead_point_text"], f"lead_points[{i}].text", problems)
    if problems:
        raise ContentError("글자 수 초과:\n  - " + "\n  - ".join(problems))
    return data
