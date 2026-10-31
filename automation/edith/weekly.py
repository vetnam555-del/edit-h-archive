"""금요일 주간 특집 'TOP5' — 이번 주(월~금) 데일리 카드 이슈 중 5개를 목록형 캐러셀로 다시 엮는다.

새로 취재하지 않는다: 그 주에 이미 사실 확인을 거쳐 발행한 카드 이슈만 재편집한다(틀릴 위험이 가장 낮은 방식).
content/weekly/{금요일}.json 에 제목·한 줄 정리·(선택) 고를 이슈를 적는다. 고를 이슈를 비우면 날마다의
H PICK 을 먼저, 그다음 날짜 순으로 태그가 겹치지 않게 자동으로 고른다.

  01 표지(목록형 제목 + TOP5) → 02 이번 주 5가지 한눈에 → 03~07 항목 5장 → 08 이번 주를 한 줄로 → 09 마무리

E13 저장각(config weekly_special.save_card_from, 2026-11-06~ — 2026-10-31 경쟁 비교 '잘 되는 매체는 두고 쓰는 자료'):
08 을 '달력에 적어 둘 날짜'(cards.calendar_card)로 바꾼다. spec 의 dates 2~4개 — 다가올 날짜·마감·시행일을 **이미 발행한 호에서만**
가져온다(from = 그 호 날짜, 그 호 원고에 그 날짜가 글자로 있어야 통과). 새 취재가 아니라서 틀릴 위험이 그대로 낮다.
dates 가 2개 미만이면 예전처럼 '이번 주를 한 줄로'.
"""
import datetime as dt
import json
import re

from . import content
from .common import CONTENT_DIR, ROOT, card_height, cover_photo_problem, load_config, parse_date, plain, send_time_ko, weekday_ko
from .site import _LETTER, _pick, _tags, _when, dm_line

WEEKLY_DIR = CONTENT_DIR / "weekly"
LIMITS = {"title": 34, "keyword": 5, "line": 40, "oneliner_title": 24, "date_what": 22, "date_todo": 26, "dates_title": 24}
DATES_MIN, DATES_MAX, DATES_AHEAD = 2, 4, 60   # 저장각 날짜 수(5개면 카드가 넘친다)·금요일에서 며칠 뒤까지


def save_card_on(date_str, cfg=None):
    """이 금요일 특집이 저장각 날짜 장(E13)을 쓰는 날인지 — config weekly_special.save_card_from 이후."""
    start = ((cfg or load_config()).get("weekly_special") or {}).get("save_card_from")
    return bool(start) and str(date_str)[:10] >= str(start)


def _date_said(text, day):
    """원고 글에 그 날짜가 글자로 있는지 — '11월 30일'·'11월30일'·'11/30'·'11.30.'."""
    m, d = day.month, day.day
    return any(p in text for p in (f"{m}월 {d}일", f"{m}월{d}일", f"{m}/{d}", f"{m}.{d}."))


def dates_rows(spec, friday):
    """spec['dates'] 검사 → 카드·캡션용 행. 문제가 있으면 WeeklyError. 2개 미만이면 [](예전 '한 줄로' 장)."""
    raw = spec.get("dates") or []
    if len(raw) < DATES_MIN:
        return []
    if len(raw) > DATES_MAX:
        raise WeeklyError(f"dates 는 {DATES_MAX}개까지입니다")
    rows, problems = [], []
    for i, e in enumerate(raw, 1):
        try:
            day, src = parse_date(e["date"]), parse_date(e["from"])
        except (KeyError, TypeError, ValueError):
            problems.append(f"dates[{i}]: date·from 은 YYYY-MM-DD 여야 합니다")
            continue
        if not friday < day <= friday + dt.timedelta(days=DATES_AHEAD):
            problems.append(f"dates[{i}] {e['date']}: 특집 다음 날부터 {DATES_AHEAD}일 안의 날짜만(지난 날짜·먼 날짜는 저장각이 아니다)")
        path = CONTENT_DIR / f"{src.isoformat()}.json"
        if src > friday or not path.exists():
            problems.append(f"dates[{i}] from {e['from']}: 이미 발행한 호(이번 주 또는 그 전)여야 합니다")
        elif not _date_said(path.read_text(encoding="utf-8"), day):
            problems.append(f"dates[{i}]: {e['from']} 호 원고에 '{day.month}월 {day.day}일'이 없습니다 — 이미 확인해 낸 날짜만 씁니다(새 취재 금지)")
        for key, lim in (("what", LIMITS["date_what"]), ("todo", LIMITS["date_todo"])):
            if not plain(e.get(key) or ""):
                problems.append(f"dates[{i}]: '{key}' 가 비어 있습니다")
            elif len(plain(e[key])) > lim:
                problems.append(f"dates[{i}].{key}: {len(plain(e[key]))}자 → {lim}자 이하")
        if not problems:
            rows.append({"date": day, "month": day.month, "day": day.day, "weekday": weekday_ko(day),
                         "what": e["what"], "todo": plain(e["todo"]), "from": f"{src.month}/{src.day} 호에서 확인"})
    title = spec.get("dates_title") or "달력에 적어 둘\n==다가올 날짜=="
    if len(plain(title)) > LIMITS["dates_title"]:
        problems.append(f"dates_title: {len(plain(title))}자 → {LIMITS['dates_title']}자 이하")
    if problems:
        raise WeeklyError("저장각 날짜(dates):\n  - " + "\n  - ".join(problems))
    return sorted(rows, key=lambda r: r["date"])


class WeeklyError(ValueError):
    pass


def week_label(d):
    """'10월 3주차' — 월요일 시작 주 기준."""
    first = d.replace(day=1)
    return f"{d.month}월 {(d.day + first.weekday() - 1) // 7 + 1}주차"


def week_issues(friday):
    """이번 주 월~금 데일리 카드 이슈. [(날짜, 카드 이슈)]"""
    monday = friday - dt.timedelta(days=friday.weekday())
    out, last = [], None
    for i in range(friday.weekday() + 1):
        day = monday + dt.timedelta(days=i)
        path = CONTENT_DIR / f"{day.isoformat()}.json"
        if not path.exists():
            continue
        last = content.load(day.isoformat())
        for it in last["card_issues"]:
            out.append((day, {**it, "day_label": f"{day.month}/{day.day} {weekday_ko(day)}"}))
    return out, last


def auto_pick(pool, n):
    """날마다의 H PICK 먼저, 다음은 날짜·카드 순. 같은 태그는 한 번만."""
    ordered = [x for x in pool if x[1].get("accent")] + [x for x in pool if not x[1].get("accent")]
    picks, tags = [], set()
    for day, it in ordered:
        if it["tag"] in tags:
            continue
        picks.append((day, it))
        tags.add(it["tag"])
        if len(picks) == n:
            break
    return sorted(picks, key=lambda x: (x[0], pool.index(x)))


def load(date_str):
    cfg = load_config().get("weekly_special") or {}
    n = int(cfg.get("count", 5))
    friday = parse_date(date_str)
    spec_path = WEEKLY_DIR / f"{date_str}.json"
    if not spec_path.exists():
        raise WeeklyError(f"{spec_path} 가 없습니다 — 제목·한 줄 정리를 먼저 쓰세요(RUNBOOK '금요일 주간 특집')")
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    pool, last = week_issues(friday)
    if len(pool) < n:
        raise WeeklyError(f"이번 주 카드 이슈가 {len(pool)}개뿐이라 {n}개를 고를 수 없습니다 — 이번 주는 특집을 건너뛰세요")

    if spec.get("picks"):
        by_key = {(day.isoformat(), int(it["no"])): (day, it) for day, it in pool}
        try:
            picks = [by_key[(p["date"], int(p["no"]))] for p in spec["picks"]]
        except KeyError as e:
            raise WeeklyError(f"picks 의 {e} 가 이번 주 카드 이슈에 없습니다(date·no 는 데일리 content 의 cards.issues 기준)")
        if len(picks) != n:
            raise WeeklyError(f"picks 는 정확히 {n}개여야 합니다")
    else:
        picks = auto_pick(pool, n)

    for key in ("title", "oneliner", "caption"):
        if not spec.get(key):
            raise WeeklyError(f"content/weekly/{date_str}.json: '{key}' 가 비어 있습니다")
    ol = spec["oneliner"]
    if not ol.get("title") or len(ol.get("lines") or []) != 3:
        raise WeeklyError("oneliner 에는 title 과 lines 3개가 필요합니다")
    problems = []
    for text, lim, where in [(spec["title"], LIMITS["title"], "title"), (spec.get("keyword", "TOP5"), LIMITS["keyword"], "keyword"),
                             (ol["title"], LIMITS["oneliner_title"], "oneliner.title")] + \
            [(line, LIMITS["line"], f"oneliner.lines[{i}]") for i, line in enumerate(ol["lines"], 1)]:
        if len(plain(text)) > lim:
            problems.append(f"{where}: {len(plain(text))}자 → {lim}자 이하")
    if problems:
        raise WeeklyError("글자 수 초과:\n  - " + "\n  - ".join(problems))
    if spec.get("photo"):
        if not (ROOT / spec["photo"]).exists() or not spec.get("credit"):
            raise WeeklyError("photo 를 쓰면 파일이 있어야 하고 credit(출처·라이선스)도 적어야 합니다")
        if why := cover_photo_problem(spec["photo"], card_height(date_str)):
            raise WeeklyError(why)

    dates = dates_rows(spec, friday) if save_card_on(date_str) else []

    # 카드 함수가 쓰는 모양으로 맞춘다. 주간 특집에서는 H PICK 반전을 쓰지 않는다('오늘의 핵심' 문구가 맞지 않음).
    items = [{**it, "accent": False} for _, it in picks]
    return {
        "dates": dates, "dates_title": spec.get("dates_title") or "달력에 적어 둘\n==다가올 날짜==",
        "date": f"{date_str}-weekly", "friday": friday, "vol": last["vol"], "weekday": weekday_ko(friday),
        "title": plain(spec["title"]), "spec": spec, "card_issues": items, "all_items": last["all_items"],
        "hero_title": spec["title"], "week_label": week_label(friday),
        "cards": {
            "cover": {"title": spec["title"], "keyword": spec.get("keyword") or "TOP5",
                      "photo": spec.get("photo"), "credit": spec.get("credit"),
                      "focus": spec.get("focus")},
            "cta": {"kick": "이번 주 저장각", "headline": spec.get("cta_headline") or ol["title"],
                    "sub": ("날짜 장은 저장해 두면 그날 바로 꺼내 볼 수 있어요." if dates else "저장해두고 다음 주에 한 번 더 꺼내보세요."),
                    "pill": "팔로우 + 저장해두기"},
        },
        "send_time_kst": load_config()["send_time_kst"],
    }


def caption(w):
    """데일리 캡션과 같은 문체(site.instagram_caption) — 고정 이모지 줄·권유 문구·자기 계정 태그 없이."""
    spec = w["spec"]
    lines = [spec["caption"].strip(), "", f"{w['week_label']}, 다시 볼 만한 숫자 {len(w['card_issues'])}가지"]
    lines += [f"{i}. {plain(it['headline'])} ({it['day_label']})" for i, it in enumerate(w["card_issues"], 1)]
    if w.get("dates"):   # 저장각(E13) — 캡션에도 날짜를 글로 남긴다(검색·저장)
        lines += ["", "달력에 적어 둘 날짜"]
        lines += [f"· {r['month']}/{r['day']}({r['weekday']}) {plain(r['what'])}" for r in w["dates"]]
    lines += ["", "이 중에 제일 와닿은 건 몇 번이었어요?"]
    if dm_line():
        lines += ["", dm_line()]
    lines += ["", _pick(_LETTER, w).format(when=_when(w)), "— 에디터 H", "", _tags(w, spec.get("hashtags") or ["주간정리"])]
    return "\n".join(lines)