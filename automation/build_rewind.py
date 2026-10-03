#!/usr/bin/env python3
"""예비 호(개선 A-2) — 제작 루틴이 멈춘 날, Claude 없이 GitHub Actions 만으로 발행할 '지난 호 다시 보기' 원고를 만든다.

07:00 제작 루틴이 사용량 한도·오류로 08:05(KST)까지 오늘 호를 올리지 못하면 rewind.yml 이 이 스크립트로
content/{날짜}.json 을 만들고 build_issue.py 로 뉴스레터·카드를 빌드한 뒤 발송·게시를 돌린다.
**새로 취재하지 않는다** — 최근 3주 안에 이미 사실 확인을 거쳐 발행한 이야기(원고 JSON)만 다시 엮는다(주간 특집과 같은 원칙).
출처 옆 날짜가 처음 실린 날이라, 에디터 H 노트에서 '다시 보기'임을 밝힌다.

  python3 automation/build_rewind.py --wait            # 새벽 예약 실행: 08:05 까지 기다린다(그 사이 오늘 호가 main 에 오면 일찍 끝냄) → go=true/false
  python3 automation/build_rewind.py --need            # 오늘 예비 호가 필요한지(발행일인데 08:05 까지 오늘 호가 없음) → need=true/false
  python3 automation/build_rewind.py [--date YYYY-MM-DD] [--dry-run]   # content/{날짜}.json 작성(드라이런은 출력만)

고르는 법: H PICK = 형식 2 호의 H PICK(심층 필드가 있어야 한다) 중 성과표 점수가 가장 높은 것, 나머지 4개 = 카드가 있던
이야기 중 태그가 겹치지 않게 점수·최신 순. '오늘·내일·어제·이번 주'처럼 시점이 지난 표현이 든 이야기와 어제 호는 되도록 뺀다.
앞선 예비 호에 이미 실린 이야기도 되도록 뺀다(사용량 한도처럼 며칠 이어지는 장애에 같은 호가 되풀이되지 않게).
"""
import argparse
import copy
import datetime as dt
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from edith.common import AUTOMATION, CONTENT_DIR, MANIFEST, ROOT, load_config, now_kst, parse_date, weekday_ko  # noqa: E402

POOL_DAYS = 21
DEADLINE = (8, 5)   # 이 시각(KST)까지 오늘 호가 없으면 예비 호를 낸다(루틴 목표 07:45 + 20분 여유)
MAX_WAIT = dt.timedelta(minutes=340)   # --wait 최대 대기(rewind.yml wait 작업 timeout 350분 안)
POLL = 300   # --wait 중 오늘 호가 올라왔는지 보는 간격(초)
_STALE = re.compile(r"오늘|내일|어제|모레|이번\s?주|다음\s?주|주말|지금 바로")


def _scores():
    """{호 날짜: 인스타 점수} — 최신 성과표 스냅숏. 없으면 {}."""
    snaps = sorted((AUTOMATION / "metrics" / "daily").glob("*.json"))
    if not snaps:
        return {}
    from collect_metrics import score
    posts = (json.loads(snaps[-1].read_text(encoding="utf-8")).get("instagram") or {}).get("posts") or {}
    return {day: score(row) or 0 for day, row in posts.items()}


def _stale(*texts):
    return any(_STALE.search(t or "") for t in texts)


def _used(date):
    """앞선 예비 호(POOL_DAYS 일 안)에 이미 실린 이야기 제목."""
    today = parse_date(date)
    used = set()
    for p in sorted(CONTENT_DIR.glob("20*.json")):
        if not 0 < (today - parse_date(p.stem)).days <= POOL_DAYS:
            continue
        c = json.loads(p.read_text(encoding="utf-8"))
        if c.get("rewind"):
            used.update(plain_title(x["title"]) for x in [c["big_issue"], *(c.get("items") or [])])
    return used


def pool(date):
    """[(이야기, 카드 스펙, 원고 날짜, 형식2 H PICK 여부, 원고)] — 오늘 이전 POOL_DAYS 일 안, 예비 호는 빼고."""
    today = parse_date(date)
    out = []
    for p in sorted(CONTENT_DIR.glob("20*.json")):
        day = p.stem
        if not 0 < (today - parse_date(day)).days <= POOL_DAYS:
            continue
        c = json.loads(p.read_text(encoding="utf-8"))
        if c.get("rewind"):
            continue
        fmt2 = "items" in c and "sections" not in c
        specs = {int(ci["no"]): ci for ci in (c.get("cards") or {}).get("issues") or []}
        items = c["items"] if fmt2 else [it for sec in c.get("sections") or [] for it in sec.get("items") or []]
        if fmt2 and 1 in specs and (c.get("cards") or {}).get("deep") and c["big_issue"].get("why"):
            out.append((c["big_issue"], specs[1], day, True, c))
        for n, it in enumerate(items, 2):
            if n in specs:
                out.append((it, specs[n], day, False, c))
    return out


def _solid(story):
    """원칙 2(원 기사 2건 이상)를 채운 이야기인가."""
    return len(story.get("sources") or []) >= 2


def pick(date):
    """(H PICK 후보, [아이템 4], 반응 근거가 있는가) — 모자라면 ValueError.
    2026-10-03 회고: 9/30 예비 호가 이틀 전 한 호의 5개를 그대로 다시 실었고, 출처 1건짜리도 섞였다.
    그래서 ① 출처 2건 이상을 먼저 ② 한 호에서 1개씩(모자라면 2개까지) 섞어 고르고, 둘 다 안 되면 조건을 하나씩 푼다."""
    scores = _scores()
    yesterday = (parse_date(date) - dt.timedelta(days=1)).isoformat()
    cands = pool(date)
    used = _used(date)

    def rank(x):
        story, spec, day, is_pick, c = x
        stale = _stale(story.get("title"), story.get("body"), story.get("takeaway"), spec.get("headline"), spec.get("body"),
                       " ".join(story.get("paragraphs") or []))
        fresh = plain_title(c["title"] if is_pick else story["title"]) not in used
        return (fresh, _solid(story), not stale, day != yesterday, scores.get(day, 0), day)

    # H PICK 은 출처 2건 이상을 먼저(지난 예비 호에 실렸어도) — 출처 기준이 '안 겹치기'보다 앞선다
    picks = sorted((x for x in cands if x[3]), key=lambda x: (_solid(x[0]), rank(x)), reverse=True)
    if not picks:
        raise ValueError("H PICK 으로 쓸 형식 2 호(심층 포함)가 최근 3주 안에 없습니다")
    top = picks[0]
    ranked = sorted((x for x in cands if not x[3]), key=rank, reverse=True)
    for per_issue, need_solid in ((1, True), (2, True), (2, False), (4, False)):
        items, tags, per_day = [], {top[0]["tag"]}, {top[2]: 1}
        for x in ranked:
            if (x[0]["tag"] in tags or any(x[0]["title"] == y[0]["title"] for y in items)
                    or per_day.get(x[2], 0) >= per_issue or (need_solid and not _solid(x[0]))):
                continue
            items.append(x)
            tags.add(x[0]["tag"])
            per_day[x[2]] = per_day.get(x[2], 0) + 1
            if len(items) == 4:
                break
        if len(items) == 4:
            if not need_solid:
                print("  ⚠ 예비 호: 출처 2건 이상인 이야기가 모자라 1건짜리를 섞었습니다")
            break
    if len(items) < 4:
        raise ValueError(f"다시 엮을 이야기가 모자랍니다(아이템 {len(items)}/4)")
    # '반응이 좋았던'은 고른 다섯 이야기의 호 모두에 실제 반응(점수 > 0)이 있을 때만 쓴다(9/30: 모두 0인데 그렇게 썼다)
    liked = all(scores.get(x[2], 0) > 0 for x in [top, *items])
    return top, items, liked


def build(date):
    top, items, by_score = pick(date)
    big = copy.deepcopy(top[0])
    big["title"] = top[4]["title"]   # H PICK 제목은 원래 호의 제목(예비 호 자체 제목은 '다시 볼 만한 5가지')
    content_items, card_issues = [], []
    spec = copy.deepcopy(top[1])
    spec["no"] = 1
    card_issues.append(spec)
    for n, (story, sp, _, _, _) in enumerate(items, 2):
        content_items.append({k: copy.deepcopy(story[k]) for k in ("tag", "title", "body", "takeaway", "sources")})
        sp = copy.deepcopy(sp)
        sp["no"] = n
        sp.pop("accent", None)
        card_issues.append(sp)
    what = "반응이 좋았던" if by_score else "다시 볼 만한"
    titles = [plain_title(top[4]["title"])] + [plain_title(s[0]["title"]) for s in items]
    return {
        "date": date,
        "rewind": True,   # 예비 호 표시 — 성과표·회고가 구분한다
        "emoji": "🔁",
        "title": "놓쳤다면, 다시 볼 만한 5가지",
        "hero_title": "놓쳤다면,\n다시 볼 만한 ==5가지==",
        "subtitle": "지난 호 다시 보기 — " + " · ".join(titles),
        "keywords": [big["tag"]] + [it["tag"] for it in content_items],
        "source_mode": "rewind",
        "lead": (f"오늘은 새 소식을 준비하지 못해, 지난 호에서 {what} 이야기 다섯 가지를 다시 골랐어요. "
                 "출처 옆 날짜가 처음 실린 날이에요. 내일 아침엔 새 소식으로 돌아올게요."),
        "observation": "새 소식이 없는 날엔 다시 볼 이야기를 — 지난 숫자에도 오늘 쓸모가 남아 있어요.",
        "big_issue": big,
        "items": content_items,
        "briefs": [],
        "question": {"text": "지난 이야기 중\n==더 알고 싶은 주제==가 있나요?",
                     "closing": "내일 아침엔 새 소식으로 찾아갈게요. — 에디터 H 드림"},
        "cards": {
            "cover": {"title": "놓쳤다면,\n다시 볼 만한 ==5가지==", "keyword": "다시보기"},
            "issues": card_issues,
            "deep": copy.deepcopy(top[4]["cards"]["deep"]),
        },
        "instagram": {
            "caption": ("오늘은 새 소식 대신, 지난 이야기 중 다시 볼 만한 다섯 가지를 골랐어요.\n\n"
                        "놓쳤던 이야기가 있다면 넘겨보세요. 내일 아침엔 새 소식으로 돌아올게요."),
            "ask": "이 중에 더 자세히 알고 싶은 이야기가 있어요?",
            "hashtags": [big["tag"]] + [it["tag"] for it in content_items[:3]],
        },
    }


def plain_title(t):
    return re.sub(r"==|\*\*", "", t).replace("\n", " ")


def published(date):
    """오늘 호가 main 에 올라왔는가 — 기다리는 동안 작업 트리는 그대로라 origin/main 을 본다."""
    subprocess.run(["git", "-C", str(ROOT), "fetch", "-q", "origin", "main"], capture_output=True)
    r = subprocess.run(["git", "-C", str(ROOT), "cat-file", "-e", f"origin/main:{date}.html"], capture_output=True)
    return r.returncode == 0


def wait(date):
    """(계속할까, 이유) — 새벽 예약 실행이 08:05 까지 기다린다. GitHub 예약은 2~3시간 늦기 일쑤라(2026-09-30 08:07 예약이
    11:03 에 돌아 예비 호가 3시간 늦음) 새벽에 미리 시작해 두고 제시간에 판단한다. 기다리는 사이 오늘 호가 오면 일찍 끝낸다."""
    wd = weekday_ko(parse_date(date))
    if wd not in load_config()["publish_days"]:
        return False, f"{wd}요일은 발행일이 아님"
    now = now_kst()
    target = now.replace(hour=DEADLINE[0], minute=DEADLINE[1], second=30, microsecond=0)
    if target - now > MAX_WAIT:
        return False, f"아직 너무 이른 시각({now:%H:%M} KST) — 뒤 예약 실행에 맡김"
    while True:
        if published(date):
            return False, "오늘 호가 main 에 있음"
        left = (target - now_kst()).total_seconds()
        if left <= 0:
            return True, f"{DEADLINE[0]:02d}:{DEADLINE[1]:02d} 까지 오늘 호가 없음"
        time.sleep(min(POLL, left))


def need(date, now=None, respect_deadline=True):
    """(필요한가, 이유)."""
    cfg = load_config()
    now = now or now_kst()
    wd = weekday_ko(parse_date(date))
    if wd not in cfg["publish_days"]:
        return False, f"{wd}요일은 발행일이 아님"
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if (ROOT / f"{date}.html").exists() or any(i["date"] == date for i in manifest["issues"]):
        return False, "오늘 호가 이미 있음"
    if respect_deadline and date == now.date().isoformat() and (now.hour, now.minute) < DEADLINE:
        return False, f"아직 {DEADLINE[0]:02d}:{DEADLINE[1]:02d} 전 — 제작 루틴을 기다림"
    return True, "오늘 호가 없음"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="")
    ap.add_argument("--wait", action="store_true", help="08:05 까지 기다린 뒤 이어갈지(GITHUB_OUTPUT 에 go=true/false)")
    ap.add_argument("--need", action="store_true", help="예비 호가 필요한지만 판단(GITHUB_OUTPUT 에 need=true/false)")
    ap.add_argument("--no-deadline", action="store_true", help="수동 실행: 08:05 기준을 보지 않음")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    date = args.date or now_kst().date().isoformat()
    if args.wait:
        print(f"{date}: {DEADLINE[0]:02d}:{DEADLINE[1]:02d} KST 까지 기다리며 오늘 호를 지켜봄")
        ok, why = wait(date)
        print(f"{date}: {'예비 호 판단으로 이어감' if ok else '끝냄'} — {why}")
        if os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
                f.write(f"go={'true' if ok else 'false'}\n")
        return 0
    if args.need:
        ok, why = need(date, respect_deadline=not args.no_deadline)
        print(f"{date}: 예비 호 {'필요' if ok else '불필요'} — {why}")
        if os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
                f.write(f"need={'true' if ok else 'false'}\ndate={date}\n")
        return 0
    try:
        data = build(date)
    except ValueError as e:
        print(f"✗ 예비 호를 만들 수 없습니다: {e}")
        return 2
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    print(f"예비 호 {date}: H PICK '{plain_title(data['big_issue']['title'])}' + 4가지 — " + " / ".join(
        [data["big_issue"]["tag"]] + [it["tag"] for it in data["items"]]))
    if args.dry_run:
        print(text[:1500])
        return 0
    (CONTENT_DIR / f"{date}.json").write_text(text, encoding="utf-8")
    print(f"✓ content/{date}.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
