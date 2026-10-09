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
        def run(jobs, attempt=1, done=False, event="schedule", by="vetnam555-del"):
            mails, reruns = [], []
            alert.run_jobs, alert.already_done = (lambda _id: jobs), (lambda _name: done)
            alert.rerun = lambda rid: reruns.append(rid) or True
            alert.send_mail = lambda subject, body, dry=False: mails.append(subject + "\n" + body)
            os.environ.update(RUN_NAME="Collect EDIT H metrics", RUN_ATTEMPT=str(attempt), RUN_ID="1", RUN_EVENT=event,
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
        # 자동 다시 실행이 또 실패한 건 발행 점검이 알린다 — 저녁 사슬처럼 10시간 넘게 걸리는 실행도 놓치지 않게(Codex 리뷰)
        recent = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
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
    cfg = load_config()
    msg = send_newsletter.build_message({"title": "t", "filename": f"{day}.html"}, page, "a@example.com", cfg, "b@example.com")
    expect("application/ld+json" not in msg.get_body(preferencelist=("html",)).get_content(), "메일 본문에 구조화 데이터 스크립트가 남았다")
    return None


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
