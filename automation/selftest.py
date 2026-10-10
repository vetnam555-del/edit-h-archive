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
import contextlib
import datetime as dt
import difflib
import io
import json
import os
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

from edith.common import CONTENT_DIR, load_config, now_kst, parse_date  # noqa: E402

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
    # 실패 알림: GitHub 서버(러너)를 못 잡아 시작도 못 한 실행(10/6 05:36 성과 수집 예약) — 끝난 일이면 조용히, 아니면 한 번 다시 실행
    no_runner = [{"conclusion": "cancelled", "steps": [], "runner_name": None}]
    broke = [{"conclusion": "success", "steps": [{"name": "a", "conclusion": "success"}], "runner_name": "r1"},
             {"conclusion": "failure", "steps": [{"name": "Send", "conclusion": "failure"}], "runner_name": "r2"}]
    expect(alert.never_started(no_runner) and not alert.never_started(broke) and not alert.never_started([]), "시작 못 한 실패 구분")
    saved = {k: getattr(alert, k) for k in ("run_jobs", "rerun", "send_mail", "already_done", "_api")}
    env = {k: os.environ.get(k) for k in ("RUN_NAME", "RUN_ATTEMPT", "RUN_ID", "RUN_EVENT", "RUN_CONCLUSION", "RUN_TRIGGERED_BY")}
    try:
        def run(jobs, attempt=1, done=False, event="schedule", by="vetnam555-del", name="Collect EDIT H metrics"):
            mails, reruns = [], []
            alert.run_jobs, alert.already_done = (lambda _id: jobs), (lambda _name: done)
            alert.rerun = lambda rid: reruns.append(rid) or True
            alert.send_mail = lambda subject, body, dry=False: mails.append(subject + "\n" + body)
            os.environ.update(RUN_NAME=name, RUN_ATTEMPT=str(attempt), RUN_ID="1", RUN_EVENT=event,
                              RUN_CONCLUSION="failure", RUN_TRIGGERED_BY=by)
            with contextlib.redirect_stdout(io.StringIO()):
                alert.failed()
            return mails, reruns
        expect(run(no_runner, done=True) == ([], []), "이미 모은 날 시작 못 한 수집 예약은 알리지도 다시 돌리지도 않는다")
        expect(run(no_runner, done=True, event="workflow_dispatch") == ([], ["1"]),
               "수동 수집이 시작 못 하면 이미 모았어도 다시 돌린다(일부러 다시 모으는 것일 수 있다)")
        expect(run(no_runner) == ([], ["1"]), "시작 못 한 실행은 메일 대신 한 번 다시 실행")
        expect(run(no_runner, attempt=2, by="github-actions[bot]") == ([], []), "자동 다시 실행의 끝 이벤트는 발행 점검 몫(겹쳐 알리지 않음)")
        mails, reruns = run(no_runner, attempt=2)
        expect(not reruns and len(mails) == 1 and "GitHub 서버" in mails[0], "사람이 다시 돌린 것도 시작 못 하면 알린다")
        mails, reruns = run(broke)
        expect(not reruns and len(mails) == 1 and "Send" in mails[0], "코드가 돌다 실패한 건 바로 알린다(실패한 단계와 함께)")
        # 어제 편집 회고가 main 에 없으면 아침 점검이 알린다(2026-10-08 회고 요청) — 오후·밤 점검이나 어제 호가 없던 날은 보지 않는다
        tz = now_kst().tzinfo
        y = "2000-01-02"   # 전날(2000-01-01) 호가 manifest 에 없는 날
        alert._api = lambda method, path: []
        expect(not alert.retro_missing(y, dt.datetime.combine(parse_date(y), dt.time(8, 40), tz)), "어제 호가 없던 날까지 회고를 찾는다")
        last = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))["issues"]
        day = (parse_date(max(i["date"] for i in last)) + dt.timedelta(days=1)).isoformat()   # 어제 = 마지막 발행일
        prev = (parse_date(day) - dt.timedelta(days=1)).isoformat()
        morning = dt.datetime.combine(parse_date(day), dt.time(8, 40), tz)
        alert._api = lambda method, path: [{"commit": {"message": "Record newsletter send"}}]
        expect(alert.retro_missing(day, morning), "어제 회고 커밋이 없는데 알리지 않는다")
        alert._api = lambda method, path: [{"commit": {"message": f"Editor retrospective {prev}"}}]
        expect(not alert.retro_missing(day, morning), "어제 회고가 있는데 알린다")
        alert._api = lambda method, path: []
        expect(not alert.retro_missing(day, morning.replace(hour=22)), "밤 점검이 어제 회고를 다시 찾는다")
        alert._api = lambda method, path: None
        expect(not alert.retro_missing(day, morning), "API 를 못 쓰는데 회고 빠짐으로 알린다")
        # 매시간 도는 구독 반영은 같은 실패를 20시간에 한 번만 알린다(2026-10-09 매시간 예비 실행)
        recent = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        alert._api = lambda method, path: {"workflow_runs": [{"id": 5, "name": "Sync EDIT H subscribers", "updated_at": recent}]}
        expect(run(broke, name="Sync EDIT H subscribers") == ([], []), "매시간 구독 반영이 같은 실패를 또 알린다")
        alert._api = lambda method, path: {"workflow_runs": [{"id": 5, "name": "Sync EDIT H subscribers", "updated_at": "2026-01-01T00:00:00Z"}]}
        expect(len(run(broke, name="Sync EDIT H subscribers")[0]) == 1, "구독 반영의 첫 실패를 알리지 않는다")
        # 자동 다시 실행이 또 실패한 건 발행 점검이 알린다 — 저녁 사슬처럼 10시간 넘게 걸리는 실행도 놓치지 않게(Codex 리뷰)
        runs = [{"id": 7, "name": "EDIT H evening chain", "run_attempt": 2, "updated_at": recent, "html_url": "u7",
                 "triggering_actor": {"login": "github-actions[bot]"}},
                {"id": 8, "name": "Send EDIT H newsletter", "run_attempt": 2, "updated_at": recent, "triggering_actor": {"login": "someone"}},
                {"id": 9, "name": "Send EDIT H newsletter", "run_attempt": 1, "updated_at": recent, "triggering_actor": {"login": "github-actions[bot]"}},
                {"id": 10, "name": "Collect EDIT H metrics", "run_attempt": 2, "updated_at": "2026-01-01T00:00:00Z",
                 "triggering_actor": {"login": "github-actions[bot]"}}]
        alert._api = lambda method, path: {"workflow_runs": runs if "status=failure" in path else []}
        got = alert.rerun_failures()
        expect([k for k, _ in got] == ["rerun:7"] and "저녁 일정" in got[0][1], "자동 다시 실행 실패만(사람 재실행·첫 시도·오래된 것 제외) 골라낸다")
    finally:
        for k, v in saved.items():
            setattr(alert, k, v)
        for k, v in env.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
    return None


def t_runners():
    """워크플로 서버 고정 — ubuntu-latest 는 2026-10-19 부터 Ubuntu 26 으로 바뀐다. 08:00 발송·게시가 예고 없이 새 OS 에서 돌지 않게
    지금 검증된 ubuntu-24.04 로 고정한다(올릴 때는 PR 로 selftest 를 거쳐서)."""
    found = {}
    for wf in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        for ln in wf.read_text(encoding="utf-8").splitlines():
            if ln.strip().startswith("runs-on:"):
                found.setdefault(ln.split(":", 1)[1].strip(), []).append(wf.name)
    expect("ubuntu-latest" not in found, f"ubuntu-latest 를 쓰는 워크플로: {', '.join(sorted(set(found.get('ubuntu-latest', []))))}")
    return ", ".join(f"{k} {len(v)}개 작업" for k, v in sorted(found.items()))


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
    # 예비 호에 다시 실린 H PICK 도 '최근'으로 센다 — 예비 호가 이어질 때 같은 H PICK 반복 막기
    saved = build_rewind.CONTENT_DIR
    with tempfile.TemporaryDirectory() as tmp:
        for day, title in (("2026-10-10", "가"), ("2026-10-11", "나"), ("2026-10-12", "가")):
            Path(tmp, f"{day}.json").write_text(json.dumps({"rewind": True, "big_issue": {"title": title}}), encoding="utf-8")
        Path(tmp, "2026-09-30.json").write_text(json.dumps(   # 지난 날짜로 10/12 에 늦게 낸 예비 호
            {"rewind": True, "published_at_kst": "2026-10-12T15:00:00+09:00", "big_issue": {"title": "다"}}), encoding="utf-8")
        build_rewind.CONTENT_DIR = Path(tmp)
        try:
            expect(build_rewind._rewind_picks("2026-10-13") == {"가": "2026-10-12", "나": "2026-10-11", "다": "2026-10-12"},
                   "예비 호 H PICK 최근 날짜를 못 센다(늦게 낸 예비 호는 실제로 낸 날)")
            # 9/29 호를 10/13 에 늦게 낼 때 — 9/29 뒤에 실린 H PICK 도 센다
            expect(build_rewind._rewind_picks("2026-09-29", "2026-10-13") == {"가": "2026-10-12", "나": "2026-10-11", "다": "2026-10-12"},
                   "지난 날짜 예비 호가 그 날짜 뒤에 실린 H PICK 을 안 센다")
        finally:
            build_rewind.CONTENT_DIR = saved
    for past in ("2026-09-30", "2026-10-07"):   # 실제 예비 호 날 — 이틀 전 H PICK 을 다시 실었던 날(10/8 회고)
        gap = (parse_date(past) - parse_date(build_rewind.pick(past)[0][2])).days
        expect(gap > build_rewind.PICK_GAP_DAYS, f"{past} 예비 호 H PICK 이 {gap}일 전 호의 H PICK 이다")
        with contextlib.redirect_stdout(io.StringIO()):
            expect(build_rewind.cover_photo(past, ["다시 볼 이야기"]), f"{past} 예비 호 표지에 대체 사진이 안 붙는다")
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


def t_photo_library():
    """대체 표지 사진(fetch_photo --library): 목록의 사진이 모두 있고 지난 호의 출처가 붙는지, 주제어 순위·최근 사용 제외가 맞는지."""
    import build_rewind
    import fetch_photo
    lib = {k for k in json.loads(fetch_photo.LIBRARY.read_text(encoding="utf-8")) if not k.startswith("_")}
    bad = sorted(p for p in lib if not fetch_photo.registered(p))
    expect(not bad, f"대체 사진 목록에 subject·tags 가 빠진 줄: {', '.join(bad)}")
    every = fetch_photo.library("2999-01-01")
    missing = lib - {c["photo"] for c in every}
    expect(not missing, f"대체 사진 목록에 있지만 파일이나 출처(발행한 호의 credit)가 없다: {', '.join(sorted(missing))}")
    top = fetch_photo.library("2999-01-01", "카드 공제 체크카드")[0]
    expect(top["photo"].endswith("2026-10-04.jpg") and top["score"] > 0, "주제어 '카드' 가 카드 결제 사진을 1순위로 고르지 않는다")
    for words in ("ai", "AI가 바꾼 세상", "IT업계 변화"):
        top = fetch_photo.library("2999-01-01", words)[0]
        expect(top["score"] > 0 and top["photo"].endswith(("2026-10-01.jpg", "2026-10-06.jpg")), f"'{words}' 가 AI·IT 태그에 맞지 않는다")
    for words, photo in (("내일부터 달라지는 제도", "2026-10-02.jpg"), ("시설 점검", "2026-09-25.jpg"), ("mail 정리", "2026-10-01.jpg")):
        hit = [c for c in fetch_photo.library("2999-01-01", words) if c["photo"].endswith(photo)]
        expect(hit and hit[0]["score"] == 0, f"한 글자 태그가 '{words}' 에 걸려 {photo} 를 맞는 후보로 올린다")
    with contextlib.redirect_stdout(io.StringIO()):
        expect(fetch_photo.cmd_library("카드", use=0, day="2999-01-01") == 2, "--use 0 이 마지막 후보를 고른다")
    # 예비 호가 쓴 표지도 '최근 사용'에 든다 — 예비 호가 연달아 같은 사진을 고르지 않게(출처는 일반 호에서)
    saved_root, saved_lib = fetch_photo.ROOT, fetch_photo.LIBRARY
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "content").mkdir()
        (root / "assets" / "photos").mkdir(parents=True)
        (root / "assets" / "photos" / "x.jpg").write_bytes(b"")
        (root / "assets" / "photos" / "library.json").write_text(
            json.dumps({"assets/photos/x.jpg": {"subject": "동전", "tags": ["돈"]}}), encoding="utf-8")
        for day, rewind in (("2026-10-03", False), ("2026-10-10", True)):
            cov = {"photo": "assets/photos/x.jpg", "credit": "출처 원본" if not rewind else "예비 호"}
            (root / "content" / f"{day}.json").write_text(json.dumps({"rewind": rewind, "cards": {"cover": cov}}), encoding="utf-8")
        # 지난 날짜(9/30)로 10/15 에 늦게 낸 예비 호 — 쓴 날은 10/15 로 센다
        (root / "content" / "2026-09-30.json").write_text(json.dumps(
            {"rewind": True, "published_at_kst": "2026-10-15T15:00:00+09:00", "cards": {"cover": {"photo": "assets/photos/x.jpg"}}}), encoding="utf-8")
        fetch_photo.ROOT, fetch_photo.LIBRARY = root, root / "assets" / "photos" / "library.json"
        try:
            expect(not fetch_photo.library("2026-10-11", "돈"), "어제 예비 호가 쓴 표지가 다시 후보에 나온다")
            expect(not fetch_photo.library("2026-10-16", "돈"), "지난 날짜로 늦게 낸 예비 호의 표지를 다음 날 다시 고른다")
            expect(not fetch_photo.library("2026-10-15", "돈"), "같은 날 늦게 낸 예비 호의 표지를 그날 일반 호가 또 고른다")
            later = fetch_photo.library("2026-10-20", "돈")
            expect(later and later[0]["credit"] == "출처 원본", "예비 호가 쓴 사진의 출처가 일반 호의 것이 아니다")
            # 9/28 호를 10/12 에 늦게 낼 때 — 사흘 전(10/10) 예비 호 표지를 센다
            with contextlib.redirect_stdout(io.StringIO()):
                expect(not build_rewind.cover_photo("2026-09-28", ["돈"], "2026-10-12"), "지난 날짜 예비 호가 최근 쓴 표지를 또 고른다")
                expect(build_rewind.cover_photo("2026-09-28", ["돈"], "2026-10-20"), "지난 날짜 예비 호가 쓸 수 있는 표지를 못 고른다")
        finally:
            fetch_photo.ROOT, fetch_photo.LIBRARY = saved_root, saved_lib
    recent = {c["photo"] for c in fetch_photo.library("2026-10-09")}
    expect(not recent & {"assets/photos/2026-10-08.jpg", "assets/photos/2026-10-06.jpg"}, "사흘 안에 쓴 사진이 대체 후보에 나온다")
    return f"{len(every)}장"


def t_seo():
    """호 페이지 검색 노출(2026-10-09): 설명문·canonical·NewsArticle 구조화 데이터가 웹 페이지엔 있고, 메일엔 스크립트가 빠진다."""
    import send_newsletter
    from edith import newsletter
    from edith import content as content_mod
    day = daily_issues(1)[0]
    site = load_config()["site_url"].rstrip("/")
    page = newsletter.render(content_mod.load(day), site, 8)
    for tag in ('<meta name="description"', f'<link rel="canonical" href="{site}/{day}.html">', 'application/ld+json'):
        expect(tag in page, f"호 페이지에 {tag} 가 없다")
    ld = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', page, re.S).group(1))
    expect(ld["@type"] == "NewsArticle" and ld["datePublished"].startswith(day) and ld.get("image"), "구조화 데이터가 NewsArticle·발행일·이미지가 아니다")
    import inspect
    from edith import site as site_mod
    # 지난 날짜로 늦게 낸 예비 호가 RSS 맨 위·lastBuildDate 가 되는지(실제 발행 시각 순)
    with tempfile.TemporaryDirectory() as tmp:
        saved = site_mod.FEED, site_mod.SITEMAP
        site_mod.FEED, site_mod.SITEMAP = Path(tmp, "feed.xml"), Path(tmp, "sitemap.xml")
        try:
            site_mod.write_feeds({"issues": [
                {"date": "2026-10-09", "vol": "2", "title": "새 호", "filename": "2026-10-09.html"},
                {"date": "2026-10-07", "vol": "1", "title": "늦게 낸 예비 호", "filename": "2026-10-07.html",
                 "published_at_kst": "2026-10-09T15:00:00+09:00"}]}, "https://x")
            feed = site_mod.FEED.read_text(encoding="utf-8")
        finally:
            site_mod.FEED, site_mod.SITEMAP = saved
    expect(feed.index("늦게 낸 예비 호") < feed.index("새 호") and "15:00:00 +0900</lastBuildDate>" in feed,
           "RSS 가 실제 발행 시각 순이 아니다")
    expect('d.get("published_at_kst")' in inspect.getsource(site_mod.update_manifest), "manifest 가 예비 호의 실제 발행 시각을 쓰지 않는다")
    bare = newsletter.render(content_mod.load(day), site, 0)   # --no-cards — 없는 표지 이미지를 알리지 않는다
    expect('"image"' not in re.search(r'<script type="application/ld\+json">(.*?)</script>', bare, re.S).group(1), "카드 없는 호가 표지 이미지를 알린다")
    expect(f'<meta property="og:image" content="{site}/og_image.png">' in bare and "_cover.png" not in bare,
           "카드 없는 호의 공유 미리보기가 없는 표지 이미지를 가리킨다")
    expect((ROOT / "og_image.png").exists(), "사이트 대표 이미지 og_image.png 가 없다")
    cfg = load_config()
    msg = send_newsletter.build_message({"title": "t", "filename": f"{day}.html"}, page, "a@example.com", cfg, "b@example.com")
    expect("application/ld+json" not in msg.get_body(preferencelist=("html",)).get_content(), "메일 본문에 구조화 데이터 스크립트가 남았다")
    return None


def t_ig_seo():
    """인스타 검색 노출(2026-10-09 운영자 자료): 해시태그 5개 이하·캡션 첫 화면 핵심어·'경제 뉴스레터' 한 줄·카드 대체 텍스트."""
    import build_rewind
    import post_instagram
    from edith import content as content_mod
    from edith import site as site_mod
    from edith import style
    day = daily_issues(1)[0]
    d = content_mod.load(day)
    d["send_time_kst"] = load_config()["send_time_kst"]
    cap = site_mod.instagram_caption(d, load_config()["site_url"])
    for name, text in (("캡션", cap), ("릴스 캡션", site_mod.reel_caption(d)),
                       ("태그 9개 넣은 캡션", site_mod._tags({"keywords": [f"k{i}" for i in range(9)]}, [f"t{i}" for i in range(9)]))):
        n = len(re.findall(r"(?<!\S)#\S+", text))
        expect(n <= 5, f"{name} 해시태그 {n}개 — 인스타는 게시물당 5개까지(2025-12~)")
    expect("경제 뉴스레터" in cap, "캡션 뉴스레터 한 줄에 계정 주제어 '경제 뉴스레터'가 없다")
    expect(not style.caption_keyword({"instagram": {"hashtags": ["치킨값"], "caption": "치킨 한 마리 3만원 시대예요."}}),
           "첫 줄에 핵심어가 있는데 경고한다")
    expect(style.caption_keyword({"instagram": {"hashtags": ["치킨값"], "caption": "요즘 다들 어떠세요? " * 12 + "치킨"}}),
           "첫 화면에 핵심어가 없는데 경고가 없다")
    with contextlib.redirect_stdout(io.StringIO()):
        rw = build_rewind.build(now_kst().date().isoformat())
    expect(not style.caption_keyword(rw), f"예비 호 캡션 첫 화면에 주제어가 없다: {rw['instagram']['caption'][:60]}")
    alts = site_mod.alt_texts([{"file": "01_x_cover.png", "text": "EDIT H.\n호프집\n1894\u2060곳\n1894\u2060곳\n1\n사라졌다"},
                               {"file": "02_x_cta.png", "text": ""}])
    expect(alts == {"01_x_cover.jpg": "EDIT H 경제 뉴스 카드 1/2 — 호프집 1894곳 사라졌다"}, f"대체 텍스트가 이상하다: {alts}")

    class FakeGraph:   # 인스타 API 대신 — 요청만 적어 둔다(reject: alt_text 를 거절하는 경우)
        def __init__(self, reject):
            self.calls, self.reject = [], reject

        def call(self, method, path, **params):
            self.calls.append(params)
            if self.reject and "alt_text" in params:
                raise post_instagram.IGError("400 OAuthException (code 100): Invalid parameter")
            return {"id": str(len(self.calls))}

        def wait_ready(self, *a, **k):
            pass

    saved = post_instagram.wait_public
    post_instagram.wait_public = lambda urls, **k: None
    try:
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            folder = Path(tmp)
            (folder / "ig").mkdir()
            for n in ("01_a.jpg", "02_b.jpg"):
                (folder / "ig" / n).write_bytes(b"")
            (folder / "caption.txt").write_text("c", encoding="utf-8")
            (folder / "alt_text.json").write_text(json.dumps({"01_a.jpg": "가", "02_b.jpg": "나"}), encoding="utf-8")
            ok, bad = FakeGraph(False), FakeGraph(True)
            post_instagram.post_carousel(ok, "u", "k", folder, "https://x", True)
            post_instagram.post_carousel(bad, "u", "k", folder, "https://x", True)
    finally:
        post_instagram.wait_public = saved
    expect([c.get("alt_text") for c in ok.calls if c.get("is_carousel_item")] == ["가", "나"], "캐러셀 장에 대체 텍스트가 안 붙는다")
    expect(["alt_text" in c for c in bad.calls if c.get("is_carousel_item")] == [True, False, False],
           "대체 텍스트가 거절되면 빼고 다시 올리지 않는다")
    built = ROOT / "instagram" / day / "alt_text.json"
    return f"{day} 해시태그·첫 화면 핵심어·대체 텍스트" + ("" if built.exists() else " (발행본 alt_text.json 은 다음 빌드부터)")


def t_views_diag():
    """조회수 저조 진단(2026-10-09): E6 보내기 한 줄·share_to 점검, E7 릴스 피드 공유 날짜, 계정 7일 지표 해석(한 지표가 막혀도 나머지 유지)."""
    import collect_metrics
    import post_instagram
    from edith import content as content_mod
    from edith import site as site_mod
    from edith import style
    day = daily_issues(1)[0]
    d = content_mod.load(day)
    d["send_time_kst"] = load_config()["send_time_kst"]
    d.setdefault("instagram", {}).pop("share_to", None)
    plain_cap = site_mod.instagram_caption(d, load_config()["site_url"])
    expect("보내 주" not in plain_cap, "share_to 가 없는데 보내기 한 줄이 붙는다")
    d["instagram"]["share_to"] = "프리랜서 친구"
    cap, reel = site_mod.instagram_caption(d, load_config()["site_url"]), site_mod.reel_caption(d)
    expect("프리랜서 친구" in cap and "프리랜서 친구" in reel, "보내기 한 줄이 캡션·릴스 캡션에 없다")
    expect(len(re.findall(r"(?<!\S)#\S+", reel)) <= 5 and reel.rstrip().splitlines()[-1].startswith("#"), "릴스 캡션 끝이 해시태그 줄이 아니다")
    for who, date, warn in (("", "2026-10-10", True), ("친구", "2026-10-10", True), ("프리랜서 친구", "2026-10-10", False), ("", "2026-10-09", False)):
        got = bool(style.share_check({"date": date, "instagram": {"share_to": who}}))
        expect(got == warn, f"share_to '{who}'({date}) 점검이 {'경고 안 함' if warn else '잘못 경고'}")
    cfg = {"reel_feed_from": "2026-10-13"}
    expect([post_instagram.reel_to_feed(cfg, k) for k in ("2026-10-12", "2026-10-13", "2026-10-16-weekly")] == [False, True, True],
           "릴스 피드 공유 시작 날짜가 틀린다")
    expect(post_instagram.reel_to_feed({"reel_share_to_feed": True}, "2026-10-01") and not post_instagram.reel_to_feed({}, "2026-12-01"),
           "reel_share_to_feed 설정을 안 따른다")

    class FakeGraph:   # 계정 인사이트 응답 흉내 — follows_and_unfollows 는 막힌 경우
        def call(self, method, path, **params):
            m = params["metric"]
            if m == "follows_and_unfollows":
                raise post_instagram.IGError("400 (code 100): unsupported")
            if m == "reach":
                return {"data": [{"name": "reach", "total_value": {"value": 305, "breakdowns": [{"results": [
                    {"dimension_values": ["FOLLOWER"], "value": 40}, {"dimension_values": ["NON_FOLLOWER"], "value": 260},
                    {"dimension_values": ["UNKNOWN"], "value": 5}]}]}}]}
            return {"data": [{"name": m, "total_value": {"value": 3}}, {"total_value": {"value": 9}}]}

    acc = collect_metrics.account_week(FakeGraph(), now=now_kst())
    expect(acc.get("reach") == {"FOLLOWER": 40, "NON_FOLLOWER": 260, "UNKNOWN": 5} and acc.get("accounts_engaged") == 3
           and "follows_and_unfollows" in acc.get("errors", {}), f"계정 7일 지표 해석이 틀린다: {acc}")
    expect("profile_views" not in {m for m, _ in collect_metrics.ACCOUNT_METRICS}, "v21 에 없어진 profile_views 를 요청한다")
    lines = collect_metrics._account_lines({"account": acc}, {"2026-10-09": {"profile_visits": 2, "follows": 1}})
    expect(lines and "팔로워 40" in lines[0] and "비팔로워 260(미분류 5)" in lines[0] and "반응한 계정 3" in lines[0]
           and "프로필 방문 2" in lines[-1], f"성과표 계정 줄: {lines}")
    # 게시물이 없어도(게시 쉼) 계정 지표는 모은다
    saved_env = os.environ.get("IG_ACCESS_TOKEN")
    saved_graph = post_instagram.Graph
    os.environ["IG_ACCESS_TOKEN"] = "x"

    class FakeMe(FakeGraph):
        def __init__(self, *a):
            pass

        def call(self, method, path, **params):
            return {"followers_count": 1, "media_count": 1} if path == "me" else super().call(method, path, **params)

    post_instagram.Graph = FakeMe
    try:
        got = collect_metrics.instagram([])
    finally:
        post_instagram.Graph = saved_graph
        if saved_env is None:
            os.environ.pop("IG_ACCESS_TOKEN", None)
        else:
            os.environ["IG_ACCESS_TOKEN"] = saved_env
    expect((got.get("account") or {}).get("accounts_engaged") == 3, f"게시물이 없을 때 계정 지표를 안 모은다: {got}")
    head = collect_metrics.summary_md({"collected_at": "x", "issues": {}, "instagram": got})
    expect("권한 없음" not in head, "살펴본 게시물이 없을 뿐인데 '인사이트 권한 없음'이라고 쓴다")
    return "보내기 한 줄·피드 공유 날짜·계정 지표"


def t_first_issue():
    """구독 즉시 첫 메일(2026-10-09): 이미 발송된 가장 최근 호를 바로, 오늘 호가 곧 나갈 참이면 안 보냄(두 번 받지 않게), 맨 위 안내·제목."""
    import sync_subscribers as ss
    tz = now_kst().tzinfo
    saved = ss.MANIFEST, ss.SENT_DIR, ss.ROOT
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "sent").mkdir()
        page = ('<html><body><table role="presentation" width="100%"><tr><td>'
                '<table role="presentation" width="600" cellpadding="0" cellspacing="0"><tr><td>본문 email=PLACEHOLDER</td></tr></table>'
                '</td></tr></table></body></html>')
        issues = [{"date": d, "vol": v, "title": f"{d} 호", "filename": f"{d}.html"} for d, v in (("2026-10-08", "107"), ("2026-10-09", "108"))]
        for i in issues:
            (root / i["filename"]).write_text(page, encoding="utf-8")
        (root / "manifest.json").write_text(json.dumps({"issues": issues}), encoding="utf-8")
        (root / "sent" / "2026-10-08.json").write_text(json.dumps({"sent": 11}), encoding="utf-8")
        ss.MANIFEST, ss.SENT_DIR, ss.ROOT = root / "manifest.json", root / "sent", root
        try:
            expect(ss.first_issue(dt.datetime(2026, 10, 9, 7, 30, tzinfo=tz)) is None,
                   "오늘 호가 올라왔고 아직 안 나갔는데 지난 호를 바로 보낸다(곧 두 번째 메일이 간다)")
            expect((ss.first_issue(dt.datetime(2026, 10, 10, 6, 0, tzinfo=tz)) or {}).get("date") == "2026-10-08",
                   "발송된 적 없는 호를 첫 메일로 보낸다")
            (root / "sent" / "2026-10-09.json").write_text(json.dumps({"sent": 11}), encoding="utf-8")
            first = ss.first_issue(dt.datetime(2026, 10, 9, 9, 0, tzinfo=tz))
            expect((first or {}).get("date") == "2026-10-09", "오늘 호가 나간 뒤엔 오늘 호를 바로 보내야 한다")
            msg = ss.first_issue_message("a@example.com", "new@example.com", load_config(), first)
            body = msg.get_body(preferencelist=("html",)).get_content()
            expect("첫 메일" in msg["Subject"] and msg["To"] == "new@example.com" and "가장 최근 호(10/9)" in body
                   and "email=new%40example.com" in body, "첫 메일 제목·받는 사람·맨 위 안내·수신 거부 주소가 이상하다")
            w = ss.welcome_message("a@example.com", "new@example.com", load_config(), now=dt.datetime(2026, 10, 9, 9, 0, tzinfo=tz), first=first)
            expect("바로 보내드려요" in w.get_body(preferencelist=("plain",)).get_content(), "환영 메일이 최근 호를 바로 보낸다고 알리지 않는다")
        finally:
            ss.MANIFEST, ss.SENT_DIR, ss.ROOT = saved
    sub = (ROOT / "subscribe.html").read_text(encoding="utf-8")
    expect(sub.index('id="successMsg"') > sub.index("</form>"), "구독 완료 문구가 폼 안에 있다 — 폼을 숨기면 같이 숨는다")
    expect(sub.index('id="email"') < sub.index('class="features"'), "이메일 칸이 기능 소개보다 아래 있다(작은 화면에서 안 보임)")
    relay = (AUTOMATION / "relay" / "subscribe_relay.gs").read_text(encoding="utf-8")
    expect("sync-subscribers.yml" in relay and "dry_run: 'false'" in relay and "ghp_" not in relay and "github_pat_" not in relay,
           "구독 즉시 반영 스크립트가 다른 작업을 부르거나 토큰이 들어 있다")
    return "최근 발송 호 바로 보내기·중복 방지·구독 페이지"


def t_reel_hook():
    """E8 릴스 첫 장 훅(2026-10-13~): 날짜부터 켜지고, 첫 장만 크게 시작해 제자리로(위쪽 고정 — 워드마크가 음악 출처 띠와 안 겹치게)."""
    import make_reel
    ig = {"reel_hook_from": "2026-10-13"}
    expect([make_reel.hook_on(ig, k) for k in ("2026-10-12", "2026-10-13", "2026-10-16-weekly")] == [False, True, True],
           "릴스 첫 장 훅 시작 날짜가 틀린다")
    got = {}
    saved = make_reel.subprocess.run
    make_reel.subprocess.run = lambda cmd, check=True: got.setdefault("cmd", cmd)
    try:
        timing = {**make_reel.VERTICAL_TIMING, **load_config()["instagram"]["reel_hook_timing"]}
        total = make_reel.build([Path(f"r{i}.jpg") for i in range(4)], Path("out.mp4"), {"file": "x.m4a"}, "ffmpeg", timing, None, True)
    finally:
        make_reel.subprocess.run = saved
    graph = got["cmd"][got["cmd"].index("-filter_complex") + 1]
    first, rest = graph.split("[v0]", 1)
    expect("max(0,1-t/0.5)" in first and "(ih-1920)*0.1" in first and "max(0" not in rest, "확 다가오기가 첫 장에만 걸리지 않는다")
    expect(total < 9, f"훅 릴스가 {total:.1f}초 — 첫 장을 줄인 길이(약 8초)가 아니다")
    return f"첫 장 {timing['first']}초 · {total:.1f}초"


def t_story():
    """E9 아침 스토리(2026-10-10~): 날짜·데일리만, 세로 훅 화면(없으면 표지), STORIES 로 올림, 24시간 뒤엔 지난 스냅숏 값."""
    import collect_metrics
    import post_instagram
    cfg = {"story_from": "2026-10-10"}
    expect([post_instagram.story_on(cfg, k) for k in ("2026-10-09", "2026-10-10", "2026-10-16-weekly")] == [False, True, False],
           "스토리 시작 날짜·주간 특집 제외가 틀린다")
    expect(post_instagram.story_on(cfg, "2026-10-10", "BUSINESS") and not post_instagram.story_on(cfg, "2026-10-10", "MEDIA_CREATOR"),
           "크리에이터 계정에서도 스토리를 시도한다(API 스토리는 비즈니스 계정만)")
    calls = []

    class FakeGraph:
        def call(self, method, path, **params):
            calls.append((path, params))
            if path.endswith("/insights"):
                raise post_instagram.IGError("400 (code 10): insights expired")
            return {"id": "s1"}

        def wait_ready(self, *a, **k):
            pass

    saved_wait, saved_metrics = post_instagram.wait_public, collect_metrics.METRICS
    post_instagram.wait_public = lambda urls, **k: None
    try:
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            folder = Path(tmp) / "k"
            (folder / "ig").mkdir(parents=True)
            (folder / "ig" / "01_cover.jpg").write_bytes(b"")
            expect(post_instagram.story_image(folder, "k", "https://x").endswith("/ig/01_cover.jpg"), "훅 화면이 없을 때 표지로 안 간다")
            (folder / "reel_frames").mkdir()
            (folder / "reel_frames" / "r1_hook.jpg").write_bytes(b"")
            expect(post_instagram.story_image(folder, "k", "https://x").endswith("/reel_frames/r1_hook.jpg"), "스토리가 세로 훅 화면을 안 쓴다")
            expect(post_instagram.post_story(FakeGraph(), "u", "k", folder, "https://x", False) == "s1", "스토리를 게시하지 않는다")
            media = [p for path, p in calls if path == "u/media"]
            expect(media and media[0].get("media_type") == "STORIES" and media[0]["image_url"].endswith("r1_hook.jpg"), "STORIES 컨테이너가 아니다")
            # 24시간이 지나 인사이트가 닫히면 지난 스냅숏의 스토리 값을 그대로 쓴다
            daily = Path(tmp) / "m" / "daily"
            daily.mkdir(parents=True)
            (daily / "2026-10-10.json").write_text(json.dumps({"instagram": {"posts": {"2026-10-10": {"story": {"reach": 31}}}}}), encoding="utf-8")
            collect_metrics.METRICS = Path(tmp) / "m"
            got = collect_metrics._story_row(FakeGraph(), "2026-10-10", {"story": {"id": "s1"}})
            expect(got == {"reach": 31}, f"닫힌 스토리 인사이트를 지난 스냅숏에서 못 가져온다: {got}")
    finally:
        post_instagram.wait_public, collect_metrics.METRICS = saved_wait, saved_metrics
    expect(collect_metrics._story_cell({"story": {"reach": 31}}) == " (스토리 31)", "성과표에 스토리 도달이 안 붙는다")
    return "날짜·이미지·게시·24시간 뒤 값"


def t_evening():
    """저녁 일정 사슬(evening.py): 매일 21:30 수집, 저녁 릴스 기간이면 19:30 릴스·20:45 점검. dispatch 대상 워크플로에 workflow_dispatch 가 있는지."""
    import evening
    day = daily_issues(1)[0]
    items = {name: (t.strftime("%H:%M"), wf) for t, name, wf, _ in evening.schedule(day)}
    expect(items.get("성과 수집", ("",))[0] == evening.METRICS_AT, "성과 수집이 21:30 일정에 없다")
    ig = load_config().get("instagram") or {}
    if ig.get("reel_evening_from") and day >= ig["reel_evening_from"]:
        expect(items.get("저녁 릴스", ("",))[0] == ig.get("reel_time_kst"), "저녁 릴스가 reel_time_kst 일정에 없다")
    for _, wf in items.values():
        text = (ROOT / ".github" / "workflows" / wf).read_text(encoding="utf-8")
        expect("workflow_dispatch:" in text, f"{wf} 에 workflow_dispatch 가 없어 사슬이 실행할 수 없다")
    # 예비 호는 GITHUB_TOKEN 으로 푸시해 push 로는 사슬이 안 뜬다 — rewind.yml 이 직접 띄워야 21:30 수집이 제때 돈다(10/7)
    rewind = (ROOT / ".github" / "workflows" / "rewind.yml").read_text(encoding="utf-8")
    expect("gh workflow run evening.yml" in rewind, "예비 호(rewind.yml)가 저녁 일정 사슬을 띄우지 않는다")
    return f"{day}: " + ", ".join(f"{t} {n}" for n, (t, _) in sorted(items.items(), key=lambda kv: kv[1][0]))


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
    check("알림(alert) — 날짜·시작 못 한 실패", t_alert)
    check("워크플로 서버 고정", t_runners)
    check("오늘 할 일(check_today)", t_check_today)
    check("연재 회차·문장 점검", t_series_and_style)
    check("예비 호 고르기(build_rewind)", t_rewind)
    check("성과표(collect_metrics)", t_metrics)
    check("스레드 본문(post_threads)", t_threads)
    check("구독 선물(gift)", t_gift)
    check("대체 표지 사진(fetch_photo --library)", t_photo_library)
    check("검색 노출(호 페이지 SEO)", t_seo)
    check("저녁 일정 사슬(evening)", t_evening)
    check("인스타 검색 노출(해시태그·키워드·대체 텍스트)", t_ig_seo)
    check("조회수 진단(보내기 한 줄·릴스 피드·계정 지표)", t_views_diag)
    check("구독 즉시 첫 메일(sync_subscribers)", t_first_issue)
    check("릴스 첫 장 훅(E8)", t_reel_hook)
    check("아침 스토리(E9)", t_story)
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
