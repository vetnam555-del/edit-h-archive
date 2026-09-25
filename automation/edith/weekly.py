"""금요일 주간 특집 'TOP5' — 이번 주(월~금) 데일리 카드 이슈 중 5개를 목록형 캐러셀로 다시 엮는다.

새로 취재하지 않는다: 그 주에 이미 사실 확인을 거쳐 발행한 카드 이슈만 재편집한다(틀릴 위험이 가장 낮은 방식).
content/weekly/{금요일}.json 에 제목·한 줄 정리·(선택) 고를 이슈를 적는다. 고를 이슈를 비우면 날마다의
H PICK 을 먼저, 그다음 날짜 순으로 태그가 겹치지 않게 자동으로 고른다.

  01 표지(목록형 제목 + TOP5) → 02 이번 주 5가지 한눈에 → 03~07 항목 5장 → 08 이번 주를 한 줄로 → 09 마무리
"""
import datetime as dt
import json
import re

from . import content
from .common import CONTENT_DIR, ROOT, cover_photo_problem, load_config, parse_date, plain, send_time_ko, weekday_ko
from .site import _LETTER, _pick, _tags, _when, dm_line

WEEKLY_DIR = CONTENT_DIR / "weekly"
LIMITS = {"title": 34, "keyword": 5, "line": 40, "oneliner_title": 24}


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
        if why := cover_photo_problem(spec["photo"]):
            raise WeeklyError(why)

    # 카드 함수가 쓰는 모양으로 맞춘다. 주간 특집에서는 H PICK 반전을 쓰지 않는다('오늘의 핵심' 문구가 맞지 않음).
    items = [{**it, "accent": False} for _, it in picks]
    return {
        "date": f"{date_str}-weekly", "friday": friday, "vol": last["vol"], "weekday": weekday_ko(friday),
        "title": plain(spec["title"]), "spec": spec, "card_issues": items, "all_items": last["all_items"],
        "hero_title": spec["title"], "week_label": week_label(friday),
        "cards": {
            "cover": {"title": spec["title"], "keyword": spec.get("keyword") or "TOP5",
                      "photo": spec.get("photo"), "credit": spec.get("credit"),
                      "focus": spec.get("focus")},
            "cta": {"kick": "이번 주 저장각", "headline": spec.get("cta_headline") or ol["title"],
                    "sub": "저장해두고 다음 주에 한 번 더 꺼내보세요.", "pill": "팔로우 + 저장해두기"},
        },
        "send_time_kst": load_config()["send_time_kst"],
    }


def caption(w):
    """데일리 캡션과 같은 문체(site.instagram_caption) — 고정 이모지 줄·권유 문구·자기 계정 태그 없이."""
    spec = w["spec"]
    lines = [spec["caption"].strip(), "", f"{w['week_label']}, 다시 볼 만한 숫자 {len(w['card_issues'])}가지"]
    lines += [f"{i}. {plain(it['headline'])} ({it['day_label']})" for i, it in enumerate(w["card_issues"], 1)]
    lines += ["", "이 중에 제일 와닿은 건 몇 번이었어요?"]
    if dm_line():
        lines += ["", dm_line()]
    lines += ["", _pick(_LETTER, w).format(when=_when(w)), "— 에디터 H", ""]
    cover = w["cards"]["cover"]
    if cover.get("photo") and cover.get("credit"):
        lines.append("표지 사진 " + cover["credit"].replace("사진 = ", "").strip())
    lines.append(_tags(w, spec.get("hashtags") or ["주간정리"]))
    return "\n".join(lines)