#!/usr/bin/env python3
"""EDIT H 자동 점검 — 코드를 바꾼 뒤(매일 개선 루틴·주간 개선·사람 손) 08:00 발행 흐름이 깨지지 않았는지 한 번에 본다.

  python3 automation/selftest.py            # 전체(최근 호 2개 다시 빌드 포함 — node·Playwright 필요, 1~2분)
  python3 automation/selftest.py --quick    # 빌드 없이 빠른 점검만(수 초)
  python3 automation/selftest.py --strict   # 다시 빌드한 결과가 발행본과 다르면 실패로

점검:
  1. 모든 파이썬 파일 컴파일
  2. 발행 흐름의 판단 함수 — 게시 계획(ig_plan), 알림 날짜·시각(alert), 오늘 할 일(check_today), 연재 회차, 문장 점검,
     예비 호 고르기(build_rewind), 성과표 만들기(collect_metrics), 스레드 본문(post_threads)
  3. 최근 데일리 호 2개를 임시 복사본에서 다시 빌드 — 빌드 실패·카드 넘침은 실패, 뉴스레터·캡션 글이 발행본과 다르면 알려 준다
     (의도한 변경이면 PR 설명에 적는다. --strict 면 실패)

저장소 파일은 바꾸지 않는다(빌드는 임시 폴더에서). 끝에 '✓ 자동 점검 통과' 또는 실패 목록을 찍고, 실패가 있으면 1 로 끝난다.
"""
import argparse
import datetime as dt
import difflib
import json
import py_compile
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

AUTOMATION = Path(__file__).resolve().parent
ROOT = AUTOMATION.parent
sys.path.insert(0, str(AUTOMATION))

from edith.common import CONTENT_DIR, load_config, now_kst  # noqa: E402

FAILS, NOTES = [], []
TEXT_OUTPUTS = ["{d}.html", "instagram/{d}/caption.txt", "instagram/{d}/reel_caption.txt", "instagram/{d}/first_comment.txt"]


def check(name, fn):
    try:
        msg = fn()
        print(f"  ✓ {name}" + (f" — {msg}" if msg else ""))
    except Exception as e:  # noqa: BLE001 — 무엇이 깨졌는지 모아서 보여 준다
        FAILS.append(f"{name}: {type(e).__name__}: {e}")
        print(f"  ✗ {name} — {type(e).__name__}: {e}")


def expect(cond, msg):
    if not cond:
        raise AssertionError(msg)


def compile_all():
    files = sorted(AUTOMATION.glob("*.py")) + sorted((AUTOMATION / "edith").glob("*.py"))
    for f in files:
        py_compile.compile(str(f), doraise=True)
    return f"{len(files)}개"


def daily_issues(n):
    """최근 데일리 호(형식 2, 예비 호 아님, 발행본 있음) n 개 날짜."""
    out = []
    for p in sorted(CONTENT_DIR.glob("20*.json"), reverse=True):
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", p.stem):
            continue
        c = json.loads(p.read_text(encoding="utf-8"))
        if c.get("rewind") or "items" not in c or not (ROOT / f"{p.stem}.html").exists():
            continue
        out.append(p.stem)
        if len(out) == n:
            break
    return out


def t_ig_plan():
    import ig_plan
    start = (load_config().get("instagram") or {}).get("reel_evening_from")
    before = "2026-10-01"
    after = start or "2999-01-01"
    expect(ig_plan.plan("schedule", "0 23 * * *", before)["only"] == "", "저녁 게시 전엔 아침에 둘 다")
    expect(ig_plan.plan("schedule", ig_plan.EVENING_CRONS[0], before)["skip"] == "true", "저녁 게시 전엔 저녁 실행을 건너뜀")
    expect(ig_plan.plan("schedule", ig_plan.WEEKLY_CRON, before)["kind"] == "weekly", "금요일 주간 특집")
    if start:
        expect(ig_plan.plan("schedule", "0 23 * * *", after)["only"] == "carousel", "저녁 게시 날 아침엔 캐러셀만")
        p = ig_plan.plan("schedule", ig_plan.EVENING_CRONS[0], after)
        expect(p["only"] == "reel" and p["at"], "저녁 게시 날 저녁엔 릴스만")
        expect(ig_plan.plan("workflow_dispatch", "", after)["only"] == "", "수동 실행은 입력값을 따른다")
    return f"저녁 게시 시작 {start or '없음'}"


def t_alert():
    import alert
    tz = now_kst().tzinfo
    expect(alert.watch_date(dt.datetime(2026, 10, 3, 3, 32, tzinfo=tz)) == "2026-10-02", "자정 넘긴 22:25 실행은 어제를 본다")
    expect(alert.watch_date(dt.datetime(2026, 10, 3, 8, 40, tzinfo=tz)) == "2026-10-03", "08:40 점검은 오늘을 본다")
    return None


def t_check_today():
    out = subprocess.run([sys.executable, str(AUTOMATION / "check_today.py")], capture_output=True, text=True, check=True).stdout
    d = json.loads(out)
    for key in ("publish", "next_vol", "recent_item_titles", "series_due", "poll_due", "weekly_special_due"):
        expect(key in d, f"check_today 출력에 {key} 가 없다")
    return f"{d['date']} publish={d['publish']} VOL.{d['next_vol']}"


def t_series_and_style():
    from edith import content, style
    expect(content.series_no("없는 연재", "2999-01-01") == 1, "연재 첫 회는 1")
    fake = {"format": 2, "date": "2999-01-01", "title": "x", "lead": "이용자가 늘어난 것으로 나타났습니다.",
            "items": [{"title": "y", "body": "DSR 이 바뀌었어요.", "takeaway": "반드시 확인하세요"}]}
    notes = " ".join(style.lint(fake))
    for word in ("기사 요약체", "해요체", "DSR", "강요"):
        expect(word in notes, f"문장 점검이 '{word}' 를 못 잡는다")
    return None


def t_rewind():
    import build_rewind
    today = now_kst().date().isoformat()
    top, items, _ = build_rewind.pick(today)
    days = {top[2], *(x[2] for x in items)}
    expect(len(items) == 4, "예비 호 아이템 4개")
    if len(days) < 3:   # pick() 의 마지막 완화 단계(한 호에서 여러 개)는 허용된 동작 — 실패가 아니라 알림
        NOTES.append(f"예비 호가 {len(days)}개 호에서만 골랐다 — 최근 3주에 쓸 만한 호가 적다(완화 단계로 선정)")
    return f"{len(days)}개 호에서 5개"


def t_metrics():
    import collect_metrics
    snaps = sorted((AUTOMATION / "metrics" / "daily").glob("*.json"))
    expect(snaps, "성과표 스냅숏이 없다")
    md = collect_metrics.summary_md(json.loads(snaps[-1].read_text(encoding="utf-8")))
    expect(md.startswith("# EDIT H 성과표"), "성과표 머리말")
    return f"{snaps[-1].stem} 스냅숏으로 {len(md.splitlines())}줄"


def t_threads():
    import post_threads
    day = daily_issues(1)
    expect(day, "데일리 호가 없다")
    c = json.loads((CONTENT_DIR / f"{day[0]}.json").read_text(encoding="utf-8"))
    text, reply = post_threads.compose(c, load_config()["site_url"].rstrip("/"))
    expect(0 < len(text) <= post_threads.MAX_TEXT, f"스레드 본문 {len(text)}자")
    expect("ref=threads" in reply, "구독 링크 답글")
    return f"{day[0]} 본문 {len(text)}자"


def t_gift():
    """구독 선물(E5): 페이지가 데이터와 맞고(build_gift.py 를 다시 돌렸는지), 기간 안의 환영 메일에 링크가 들어가는지."""
    import build_gift
    from edith.gift import active_gift
    g = (load_config().get("gift") or {})
    if not g.get("slug"):
        return "선물 없음"
    data = json.loads((AUTOMATION / "gifts" / f"{g['slug']}.json").read_text(encoding="utf-8"))
    page = ROOT / "gift" / f"{g['slug']}.html"
    expect(page.exists() and page.read_text(encoding="utf-8") == build_gift.render(data, load_config()["site_url"].rstrip("/")),
           f"gift/{g['slug']}.html 이 데이터와 다르다 — python3 automation/build_gift.py 를 다시 돌리세요")
    for grp in data["groups"]:
        for it in grp["items"]:
            expect((ROOT / f"{it['issue']}.html").exists(), f"선물 항목 '{it['do']}' 의 호 {it['issue']} 가 없다")
    sub = (ROOT / "subscribe.html").read_text(encoding="utf-8")
    expect(f'data-from="{g["from"]}" data-until="{g["until"]}"' in sub, "subscribe.html 선물 상자 날짜가 config.gift 와 다르다")
    gift = active_gift(g["from"])
    expect(gift and gift["url"].endswith(f"/gift/{g['slug']}.html"), "기간 첫날에 선물이 켜져야 한다")
    import sync_subscribers
    tz = now_kst().tzinfo
    y, m, d = map(int, g["from"].split("-"))
    msg = sync_subscribers.welcome_message("a@example.com", "b@example.com", load_config(), now=dt.datetime(y, m, d, 7, 10, tzinfo=tz))
    expect(gift["url"] in msg.get_body(preferencelist=("plain",)).get_content(), "환영 메일에 선물 링크가 없다")
    return f"{gift['title']} {gift['count']}가지"


def rebuild(days, strict):
    """임시 복사본에서 다시 빌드해 글 결과물을 발행본과 비교한다."""
    with tempfile.TemporaryDirectory() as tmp:
        sbx = Path(tmp) / "repo"
        shutil.copytree(ROOT, sbx, ignore=shutil.ignore_patterns(".git", "node_modules", "*.mp4"))
        if (ROOT / "node_modules").exists():
            (sbx / "node_modules").symlink_to(ROOT / "node_modules")
        for day in days:
            for pat in TEXT_OUTPUTS:   # 복사해 온 발행본을 지워야 '빌드가 이 파일을 안 만든' 회귀를 잡는다
                (sbx / pat.format(d=day)).unlink(missing_ok=True)
            proc = subprocess.run([sys.executable, str(sbx / "automation" / "build_issue.py"), day], capture_output=True, text=True, cwd=sbx)
            name = f"다시 빌드 {day}"
            if proc.returncode != 0:
                FAILS.append(f"{name}: 종료 코드 {proc.returncode}\n{(proc.stdout + proc.stderr)[-800:]}")
                print(f"  ✗ {name} — 종료 코드 {proc.returncode}")
                continue
            changed, missing = [], False
            for pat in TEXT_OUTPUTS:
                a, b = ROOT / pat.format(d=day), sbx / pat.format(d=day)
                if not a.exists():
                    continue
                if not b.exists():
                    FAILS.append(f"{name}: {pat.format(d=day)} 를 만들지 않았다")
                    changed.append(f"{pat.format(d=day)} (없음)")
                    missing = True
                    continue
                old, new = a.read_text(encoding="utf-8"), b.read_text(encoding="utf-8")
                if old != new:
                    diff = [ln for ln in difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm="", n=0)
                            if ln[:1] in "+-" and not ln.startswith(("+++", "---"))]
                    changed.append(f"{pat.format(d=day)} ({len(diff)}줄)")
                    NOTES.append(f"{pat.format(d=day)}:\n" + "\n".join(f"      {ln[:140]}" for ln in diff[:8]))
            warn = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip().startswith(("↘", "⚠"))]
            if changed:
                msg = f"발행본과 다름: {', '.join(changed)}"
                if strict and not missing:
                    FAILS.append(f"{name}: {msg}")
                print(f"  {'✗' if strict or missing else '△'} {name} — {msg}")
            else:
                print(f"  ✓ {name} — 뉴스레터·캡션이 발행본과 같음" + (f" (빌드 경고 {len(warn)}줄)" if warn else ""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="다시 빌드 생략")
    ap.add_argument("--strict", action="store_true", help="다시 빌드 결과가 발행본과 다르면 실패")
    ap.add_argument("--issues", type=int, default=2, help="다시 빌드할 최근 호 수")
    args = ap.parse_args()
    print("EDIT H 자동 점검")
    check("파이썬 컴파일", compile_all)
    check("인스타 게시 계획(ig_plan)", t_ig_plan)
    check("알림 날짜(alert)", t_alert)
    check("오늘 할 일(check_today)", t_check_today)
    check("연재 회차·문장 점검", t_series_and_style)
    check("예비 호 고르기(build_rewind)", t_rewind)
    check("성과표(collect_metrics)", t_metrics)
    check("스레드 본문(post_threads)", t_threads)
    check("구독 선물(gift)", t_gift)
    if not args.quick:
        rebuild(daily_issues(args.issues), args.strict)
    if NOTES:
        print("\n달라진 글(의도한 변경인지 확인):")
        for n in NOTES:
            print(f"  {n}")
    if FAILS:
        print(f"\n✗ 자동 점검 실패 {len(FAILS)}건")
        for f in FAILS:
            print(f"  - {f}")
        return 1
    print("\n✓ 자동 점검 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
