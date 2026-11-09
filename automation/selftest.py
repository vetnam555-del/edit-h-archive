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
        # 메일 계정 로그인이 막히면 알림을 GitHub 이슈로 대신(2026-11-09 — 발송·실패 알림 메일이 같은 로그인 오류로 막혀 아무 알림도 안 갔다)
        import smtplib as _smtplib

        class _Refused:
            def __init__(self, *a, **k):
                raise _smtplib.SMTPServerDisconnected("Connection unexpectedly closed")

        def _fake_api(opened):
            def f(method, path, payload=None):
                calls.append((method, path, payload))
                return opened if method == "GET" else (None if opened is None else {"html_url": "https://github.com/o/r/issues/9"})
            return f
        smtp_saved = _smtplib.SMTP_SSL
        env2 = {k: os.environ.get(k) for k in ("SMTP_USER", "SMTP_PASSWORD", "GITHUB_REPOSITORY_OWNER")}
        try:
            _smtplib.SMTP_SSL = _Refused
            os.environ.update(SMTP_USER="sender@example.com", SMTP_PASSWORD="x", GITHUB_REPOSITORY_OWNER="owner1")
            alert.send_mail = saved["send_mail"]
            calls = []
            alert._api = _fake_api([{"number": 3, "title": "다른 이슈"}, {"number": 4, "title": alert.ISSUE_TITLE, "pull_request": {}}])
            with contextlib.redirect_stdout(io.StringIO()):
                ok = alert.send_mail("제목 A", "본문 A")
            new = [c for c in calls if c[0] == "POST"]
            expect(ok and len(new) == 1 and new[0][1] == "issues" and new[0][2]["title"] == alert.ISSUE_TITLE
                   and new[0][2]["body"].startswith("@owner1 ") and "본문 A" in new[0][2]["body"] and "SMTP_PASSWORD" in new[0][2]["body"],
                   f"메일을 못 보낸 알림을 GitHub 이슈로 새로 열지 않는다: {new}")
            calls = []
            alert._api = _fake_api([{"number": 5, "title": alert.ISSUE_TITLE}])
            with contextlib.redirect_stdout(io.StringIO()):
                ok = alert.send_mail("제목 B", "본문 B")
            expect(ok and [c[1] for c in calls if c[0] == "POST"] == ["issues/5/comments"], "열린 알림 이슈가 있는데 새 이슈를 또 연다(댓글로 이어야 한다)")
            alert._api = _fake_api(None)
            with contextlib.redirect_stdout(io.StringIO()):
                expect(alert.send_mail("제목 C", "본문 C") is False, "이슈로도 못 알렸는데 알린 것으로 친다(다음 점검이 다시 알려야 한다)")
        finally:
            _smtplib.SMTP_SSL = smtp_saved
            for k, v in env2.items():
                os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        wf = (ROOT / ".github" / "workflows" / "alerts.yml").read_text(encoding="utf-8")
        expect(wf.count("issues: write") >= 2 and all("issues: write" in (ROOT / ".github" / "workflows" / n).read_text(encoding="utf-8")
                                                      for n in ("rewind.yml", "codex-fallback.yml")),
               "알림을 보내는 워크플로(alerts·rewind·codex-fallback)에 issues: write 가 없다 — 메일이 막히면 이슈로도 못 알린다")
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



def t_card_marks():
    """11/03 운영자 '캐릭터 로고가 좀 이상하다' — 11/04 호부터 카드 마크는 프로필 그림(안경 + 미소), 큰 숫자 '63억$' 꼴은 막는다."""
    import copy
    from edith import cards, content
    new, old = cards.avatar(50, "2026-11-04"), cards.avatar(50, "2026-11-03")
    expect("data:image/png;base64," in new and "border-radius:50%" in new, "11/04 카드 마크가 프로필 그림이 아니다")
    expect("data:image" not in old, "지난 호 카드 마크가 바뀐다(기록)")
    src = Path(cards.__file__).read_text(encoding="utf-8")
    expect("avatar(96, d.get(\"date\"))" in src and "avatar(132, d.get('date'))" in src and "persona_pill(tag, d.get(\"date\"))" in src,
           "노트·팔로우 카드·딥다이브 이름표가 날짜를 넘기지 않는다")
    raw = json.loads((CONTENT_DIR / "2026-11-03.json").read_text(encoding="utf-8"))
    for day, bad in (("2026-11-03", False), ("2026-11-04", True)):
        d = copy.deepcopy(raw)
        d["date"] = day
        try:
            content.prepare(d, day)
            got = False
        except content.ContentError as e:
            got = "63억 달러" in str(e)
        expect(got == bad, f"{day} 카드 큰 숫자 '63억$' 검사가 {'막아야' if bad else '지나가야'} 한다")
    return "11/04~ 프로필 그림 마크 · '억$' 숫자 막음"


def t_card_takeaway_link():
    """11/03 운영자 '주식 판 돈 다음 날 입금인데 그래서 나는이 왜 금리부터 보는 거야?' — 11/04~ 카드 takeaway 가 카드에 없는 돈 이야기로 튀면 막는다."""
    import copy
    from edith import content
    raw = json.loads((CONTENT_DIR / "2026-11-03.json").read_text(encoding="utf-8"))
    t1 = raw["cards"]["issues"][0]
    expect(content.takeaway_link_problem(t1) == ["대출", "금리", "담보"], "11/03 ① '담보대출 금리' takeaway 를 못 잡는다")
    ok = [{"headline": "기준금리 동결 11월 ==인상== 전망", "body": "금통위원 7명 전원 일치.", "takeaway": "변동금리 대출 이자 변경일부터 확인하세요"},
          {"headline": "10월 분양 쏟아지는데 ==서울==은 491가구", "body": "대부분 경기·인천이에요.", "takeaway": "청약 준비 중이라면 경기·인천 일정부터 챙기세요"},
          {**t1, "takeaway": "2028년까진 이틀 뒤 입금 — 쓸 날 이틀 앞서 파세요"}]
    for it in ok:
        expect(content.takeaway_link_problem(it) is None, f"이어지는 takeaway 를 막는다: {it['takeaway']}")
    for day, bad in (("2026-11-03", False), ("2026-11-04", True)):
        d = copy.deepcopy(raw)
        d["date"] = day
        for ci in d["cards"]["issues"]:   # 큰 숫자 규칙(t_card_marks)과 따로 본다
            if "number" in ci:
                ci["number"] = re.sub(r"([만억조])\s*[$€¥]", r"\1 달러", str(ci["number"]))
        try:
            content.prepare(d, day)
            got = False
        except content.ContentError as e:
            got = "담보" in str(e) and "cards.issues[1].takeaway" in str(e)
        expect(got == bad, f"{day} 카드 takeaway 이어짐 검사가 {'막아야' if bad else '지나가야'} 한다")
    return "11/04~ 카드에 없는 돈 이야기로 튀는 '그래서 나는?' 막음"


def t_card_takeaway_topic():
    """11/05 운영자 '민주당 압승에 다우가 급등했는데 주유 전 오피넷 최저가를 비교한다던지 — 소식과 그 결과로 적합한지 검토한 거 맞아?'
    11/06~ 카드 '그래서 나는?'이 제목에 없는 소식의 기관·생활 팁(오피넷·최저가·우산…)으로 튀면 막고, 빌드가 '제목 → 그래서 나는?'을 보여 준다."""
    import copy

    from edith import content
    raw = json.loads((CONTENT_DIR / "2026-11-05.json").read_text(encoding="utf-8"))
    by_no = {int(ci["no"]): ci for ci in raw["cards"]["issues"]}
    expect([s for s, _ in content.takeaway_topic_problem(by_no[2]) or []] == ["오피넷", "최저가"],
           "11/05 ② '다우 급등 → 주유 전 오피넷 최저가' 를 못 잡는다")
    for no in (1, 3, 4, 5):
        expect(content.takeaway_topic_problem(by_no[no]) is None, f"11/05 {no}번(이어지는 카드)을 막는다: {by_no[no]['takeaway']}")
    # 지난 카드 전부(9/24~)에서 걸리는 건 11/05 ② 하나 — 늘어나면 거짓 경보부터 의심한다(낱말 목록 TAKEAWAY_TOPICS)
    hits = []
    for p in sorted(CONTENT_DIR.glob("2026-*.json")):
        if p.stem > "2026-11-05":
            break
        for ci in (json.loads(p.read_text(encoding="utf-8")).get("cards") or {}).get("issues") or []:
            if content.takeaway_topic_problem(ci):
                hits.append(f"{p.stem} {ci.get('no')}")
    expect(hits == ["2026-11-05 2"], f"지난 카드 중 걸리는 것이 11/05 ② 하나가 아니다: {hits}")
    ok = [{"headline": "휘발유값 ==19주== 연속 하락", "takeaway": "더 기다리기보다 오피넷에서 동네 최저가를 찾아요"},
          {"headline": "오늘 전국에\n==비==, 내일 추워요", "takeaway": "우산 챙기고, 내일은 패딩 꺼내 두세요"},
          {"headline": "주말 내내 비가 와요", "takeaway": "우산 챙기세요"},
          {"headline": "신제품 가격 ==20%== 인상", "takeaway": "사기 전에 최저가부터 비교해요"},   # 값이 바뀐 소식의 최저가 비교는 이어진다
          {"headline": "프리랜서 세금, 28년 만에 ==2.2%==로", "takeaway": "홈택스·손택스에서 미환급금부터 조회하세요"},
          {"headline": "1년 안에 일할 생각\n==324만명==", "takeaway": "고용센터에서 지원 대상인지 확인해요"}]
    for it in ok:
        expect(content.takeaway_topic_problem(it) is None, f"이어지는 takeaway 를 막는다: {it['headline']} → {it['takeaway']}")
    bad = [{"headline": "코스피 ==3%== 급등", "takeaway": "출근길 우산 꼭 챙기세요"},
           {"headline": "엔비디아 실적 ==사상 최대==", "takeaway": "청약홈에서 이번 주 일정을 보세요"},
           {"headline": "매출, 지난해에 ==비해== 20% 증가", "takeaway": "출근길 우산 챙기세요"},   # '비해'·'비용'은 비 소식이 아니다(Codex 리뷰)
           {"headline": "물류 비용 ==20%== 줄였다", "takeaway": "우산 챙기고 나가세요"}]
    for it in bad:
        expect(content.takeaway_topic_problem(it), f"제목과 따로 노는 takeaway 를 못 잡는다: {it['headline']} → {it['takeaway']}")
    for day, block in (("2026-11-05", False), ("2026-11-06", True)):   # 11/05 는 이미 나간 기록 — 11/06 호부터 막는다
        d = copy.deepcopy(raw)
        d["date"] = day
        try:
            out = content.prepare(d, day)
            got = False
        except content.ContentError as e:
            got = "cards.issues[2].takeaway" in str(e) and "오피넷" in str(e) and "다우" in str(e)
            out = None
        expect(got == block, f"{day} 카드 ② '오피넷' 검사가 {'막아야' if block else '지나가야'} 한다")
        if out is not None:
            expect(content.read_through(out) == [], "11/05(지난 호)에도 '이어 읽기'를 보여 준다")
    d = copy.deepcopy(raw)
    d["date"] = "2026-11-06"
    for ci in d["cards"]["issues"]:
        if int(ci["no"]) == 2:
            ci["takeaway"] = "내 미국 주식, 빅테크인지 반도체인지 확인해요"
    lines = content.read_through(content.prepare(d, "2026-11-06"))
    expect(len(lines) == 5 and lines[1] == "② 민주당 압승에 다우 3.03% 급등 → 내 미국 주식, 빅테크인지 반도체인지 확인해요",
           f"'이어 읽기' 다섯 줄이 '② 제목 → 그래서 나는?' 꼴이 아니다: {lines[:2]}")
    return "11/06~ 제목에 없는 기관·생활 팁으로 튀는 '그래서 나는?' 막음 · 이어 읽기 5줄"


def t_anjang_wait():
    """평일 07:55 전 fallback 빌드는 오늘 안장 글을 확인한 기록이 있을 때만(11/03 운영자 '안장출근길 소스가 너무 좋다' — 10/15·10/29 먼저 만들어 겹침 0~1/10)."""
    import build_issue
    import fetch_anjang
    kst = now_kst().tzinfo
    tue, sat = dt.date(2026, 11, 3), dt.date(2026, 11, 7)
    at = lambda day, h, m: dt.datetime(day.year, day.month, day.day, h, m, tzinfo=kst)   # noqa: E731
    fb = {"date": "2026-11-03", "source_mode": "fallback"}
    with tempfile.TemporaryDirectory() as tmp:
        prob = lambda d, now: build_issue.anjang_wait_problem(d, now=now, state_dir=tmp)   # noqa: E731
        os.environ.pop("EDITH_SKIP_ANJANG_WAIT", None)
        expect(prob(fb, at(tue, 7, 16)), "평일 07:16 기록 없는 fallback 빌드를 막지 않는다(10/29)")
        expect(not prob(fb, at(tue, 7, 56)), "07:55 가 지나도 막는다(안장이 쉬는 날 예비 호가 나간다)")
        expect(not prob({**fb, "source_mode": "anjang"}, at(tue, 7, 16)), "안장을 쓴 호를 막는다")
        expect(not prob({**fb, "date": "2026-11-07"}, at(sat, 7, 16)), "주말(안장 쉼) 호를 막는다")
        expect(not prob(fb, at(dt.date(2026, 11, 4), 7, 16)), "다른 날 호(다시 빌드)를 막는다")
        expect(not prob({**fb, "rewind": True}, at(tue, 7, 16)), "예비 호를 막는다")
        real_now = fetch_anjang.now_kst
        try:
            fetch_anjang.now_kst = lambda: at(tue, 7, 20)
            fetch_anjang.record_check(tue, 3, False, state_dir=tmp)     # 기다리지 않고 '글 없음'만 본 기록
            expect(prob(fb, at(tue, 7, 21)), "07:55 전 '글 없음' 기록만으로 통과한다(기다리지 않았다)")
            fetch_anjang.record_check(tue, 2, False, state_dir=tmp)     # 접속 실패
            expect(not prob(fb, at(tue, 7, 21)), "접속 실패 기록이 있는데 막는다(그날은 WebSearch 로 간다)")
            fetch_anjang.record_check(tue, 0, True, state_dir=tmp)      # 오늘 글 봄(그래도 fallback 은 편집 판단)
            expect(not prob(fb, at(tue, 7, 21)), "오늘 글을 본 기록이 있는데 막는다")
            rec = json.loads((Path(tmp) / "anjang-2026-11-03.json").read_text(encoding="utf-8"))
            expect(rec.get("code") == 0 and rec.get("found_today") is True and rec.get("checked_at", "").startswith("2026-11-03T07:20"),
                   f"안장 확인 기록 형식: {rec}")
        finally:
            fetch_anjang.now_kst = real_now
        os.environ["EDITH_SKIP_ANJANG_WAIT"] = "1"
        try:
            (Path(tmp) / "anjang-2026-11-03.json").unlink()
            expect(not prob(fb, at(tue, 7, 16)), "EDITH_SKIP_ANJANG_WAIT(다시 빌드)에도 막는다")
        finally:
            os.environ.pop("EDITH_SKIP_ANJANG_WAIT", None)
    src = Path(build_issue.__file__).read_text(encoding="utf-8")
    expect("anjang_wait_problem(d)" in src and "sys.exit(4)" in src, "build_issue 가 안장 기다리기 검사를 하지 않는다")
    expect("automation/.state/" in (ROOT / ".gitignore").read_text(encoding="utf-8"), "안장 확인 기록이 저장소에 올라간다(.gitignore)")
    return "07:16 fallback 막음 · 07:56·주말·안장 호·접속 실패·글 확인은 통과"


def t_compare_anjang():
    """안장출근길 비교(회고 잣대) — 같은 소식은 고유 낱말 2개 이상, 'AI·주문' 같은 흔한 말만 겹치면 다른 소식(10/15 오판)."""
    import compare_anjang
    content = {"title": "카톡이 결제까지", "big_issue": {"tag": "카카오 AI", "paragraphs": ["카카오톡 AI 에이전트가 메시지 답장과 생수 주문까지 한다"]},
               "items": [{"tag": "은행", "title": "은행 문, 30분 늦게", "body": "영업시간 조정"}], "briefs": []}
    items = [{"headline": '카톡에 "답장 보내줘" 말하면 AI비서가 척척', "summary": ["카카오톡이 에이전트를 품습니다"]},
             {"headline": "[단독] AI, 새책도 노리나…교보문고에 들어온 '10만권' 주문", "summary": ["AI 학습용 주문"]}]
    r = compare_anjang.compare(items, content)
    expect([h for h, _ in r["covered"]] == [items[0]["headline"]], f"안장 비교 겹침 판정: {r['covered']}")
    expect(len(r["missed"]) == 1 and len(r["ours_only"]) == 1, "안장 비교: 놓친 것·우리만")
    # 주말·fallback 호 '안장 칸 N/5' 안내 줄(RUNBOOK 1-4 의 7, 11/08 호~) — 예비 호·안장 호·규칙 전 날엔 안 낸다
    sat = {"big_issue": {"tag": "반대매매"}, "items": [{"tag": "일본 여행"}, {"tag": "테슬라"}], "source_mode": "fallback"}
    line = compare_anjang.lane_line("2026-11-08", sat)
    expect(bool(line) and "'안장 칸 N/5'" in line and "01 반대매매 · 02 일본 여행 · 03 테슬라" in line, f"fallback 호 안장 칸 안내 줄: {line}")
    expect(compare_anjang.lane_line("2026-11-08", {**sat, "rewind": True}) is None
           and compare_anjang.lane_line("2026-11-09", {**sat, "source_mode": "anjang"}) is None
           and compare_anjang.lane_line("2026-11-07", sat) is None, "예비 호·안장 호·규칙 전 날에도 안장 칸 안내 줄이 나온다")
    rb = (ROOT / "automation" / "RUNBOOK.md").read_text(encoding="utf-8")
    expect("'안장이 자주 고르는 소식' 체크리스트" in rb and "안장 칸 N/5" in rb, "RUNBOOK 1-4 에 '안장이 자주 고르는 소식' 체크리스트가 없다")
    return "같은 소식 판정 · fallback 호 안장 칸 안내 줄"


def t_send_time():
    """발송 08:30(2026-10-16~) — 그 전 호의 발행 시각은 08:00 그대로(지난 호를 다시 빌드해도, Codex 리뷰)."""
    from edith.common import send_time_on
    expect(send_time_on("2026-10-15") == "08:00", "10/15 호 발행 시각이 08:00 이 아니다")
    expect(send_time_on("2026-10-16") == load_config()["send_time_kst"] == "08:30", "10/16 부터 발송 08:30")
    return None


def t_brief_check():
    """짧게 읽는 소식(10/16~): 5개·숫자 1개·2문장 이상을 알린다 — 10/15 이전 호는 보지 않는다."""
    from edith import style
    b = lambda t, body: {"title": t, "body": body, "source": "s", "url": "u"}
    d = {"date": "2026-10-16", "briefs": [b("은행 문이 늦게 열려요", "영업시간이 바뀌어요."),
                                          b("적금 신청이 16일 마감이에요", "출생연도와 상관없어요. 14개 은행 앱에서 해요.")]}
    notes = " ".join(style.brief_check(d))
    for w in ("2개 — 5개 이상", "숫자가 없어요"):
        expect(w in notes, f"짧은 소식 점검이 '{w}' 를 못 잡는다: {notes}")
    expect("적금" not in notes, "숫자·2문장을 채운 소식을 경고했다")
    expect(not style.brief_check({**d, "date": "2026-10-15"}), "10/15 호까지 짧은 소식 점검을 했다")
    three = [b("소식 1이에요", "1개예요. 두 문장이에요."), b("소식 2예요", "2개예요. 두 문장이에요."), b("소식 3이에요", "3개예요. 두 문장이에요.")]
    expect(not style.brief_check({"date": "2026-10-17", "briefs": three}), "토요일 3개를 5개 미만으로 경고했다(주말은 3개까지)")
    expect(style.brief_check({"date": "2026-10-16", "briefs": three}), "평일 3개를 경고하지 않았다")
    one = style.brief_check({"date": "2026-10-17", "briefs": three[:2] + [b("서류 내요", "주요 14개 은행 앱에서 필요 서류 2개를 내면 돼요.")]})
    expect(any("1문장" in x for x in one), "'주요·필요'가 든 한 문장을 두 문장으로 셌다")
    title_only = style.brief_check({"date": "2026-10-17", "briefs": three[:2] + [b("14개 은행에서 신청해요", "앱에서 신청해요. 서류를 내면 돼요.")]})
    expect(any("숫자가 없어요" in x for x in title_only), "숫자가 제목에만 있는 소식을 통과시켰다")
    both = style.brief_check({"date": "2026-10-17", "briefs": three[:2] + [b("둘 다 문제예요", "숫자도 없고 한 문장이에요.")]})
    expect(any("숫자가 없어요" in x for x in both) and any("1문장" in x for x in both), "숫자·문장 수 점검이 서로를 가린다")
    four = style.brief_check({"date": "2026-10-17", "briefs": three[:2] + [b("길어요", "1개예요. 2개예요. 3개예요. 4개예요.")]})
    expect(any("4문장" in x for x in four), "4문장짜리 짧은 소식을 통과시켰다")
    marked = style.brief_check({"date": "2026-10-17", "briefs": three[:2] + [b("신청해요", "**16일까지 신청해요.** 앱에서 서류 2개를 내면 돼요."),
                                                                         b("받아요", "은행은 “16일까지 받아요.” 앱에서 서류 2개를 내면 돼요.")]})
    expect(not any("문장" in x for x in marked), f"굵게·따옴표 뒤 마침표를 문장 끝으로 못 셌다: {marked}")
    import copy
    from edith import content
    base = json.loads((AUTOMATION / "examples" / "format2.json").read_text(encoding="utf-8"))
    long_body = "가" * 60 + "1개예요. " + "나" * 50 + "예요."   # 119자 — 10/16~ 은 되고 지난 호(100자)는 안 된다
    for day, ok in (("2026-10-15", False), ("2026-10-16", True)):
        x = copy.deepcopy(base)
        x["date"], x["briefs"][0]["body"] = day, long_body
        try:
            content.prepare(x, day)
            passed = True
        except content.ContentError:
            passed = False
        expect(passed == ok, f"{day} 짧은 소식 본문 119자 검증이 {'막혔다' if ok else '통과했다'}(지난 호는 100자 한도)")
    return None


def t_strict_content():
    """2026-10-17~: 짧은 소식 부족(평일 5·주말 3)과 H PICK 과 같은 원 기사를 쓴 메인을 빌드 전에 막는다 — 사유를 적은 날·예비 호·지난 호는 통과."""
    import copy
    from edith import content
    c = json.loads((CONTENT_DIR / "2026-10-15.json").read_text(encoding="utf-8"))   # 짧은 소식 4개 + 메인 05 가 H PICK 과 같은 기사 2건
    def ok(x, day):
        try:
            content.prepare(copy.deepcopy(x), day)
            return None
        except content.ContentError as e:
            return str(e)
    expect(ok(c, "2026-10-15") is None, "지난 호(10/15)까지 새 점검으로 막았다")
    mon = {**copy.deepcopy(c), "date": "2026-10-19"}
    err = ok(mon, "2026-10-19") or ""
    expect("짧게 읽는 소식이 4개" in err, f"평일 짧은 소식 4개를 막지 않았다: {err[:80]}")
    mon["briefs_short_reason"] = "확인된 소식 부족"
    err = ok(mon, "2026-10-19") or ""
    expect("H PICK 과 같은 원 기사 2건" in err, f"H PICK 과 같은 원 기사를 쓴 메인을 막지 않았다: {err[:80]}")
    mon["items"][3]["sources"] = [mon["items"][3]["sources"][0], {"name": "다른 기사", "url": "https://example.com/other"}]
    expect(ok(mon, "2026-10-19") is None, "원 기사 1건만 겹치는 메인까지 막았다")
    sat = {**copy.deepcopy(c), "date": "2026-10-17"}
    sat["items"][3]["sources"] = mon["items"][3]["sources"]
    expect(ok(sat, "2026-10-17") is None, "토요일 짧은 소식 4개를 막았다(주말은 3개까지)")
    view = lambda n: {"name": "n", "url": f"https://www.example.co.kr/news/articleView.html?idxno={n}&utm_source=naver"}
    expect(len(content._urls({"sources": [view(1), view(2)]})) == 2 and content._urls({"sources": [view(1)]})
           == content._urls({"sources": [{"url": "https://www.example.co.kr/news/articleView.html?idxno=1"}]}),
           "쿼리가 기사 번호(idxno)인 주소를 하나로 합쳤거나 추적용 쿼리(utm_)를 남겼다")
    expect(content._urls({"sources": [{"url": "http://www.a.com/n/1"}]}) == content._urls({"sources": [{"url": "https://a.com/n/1/"}]}),
           "http/https·www 만 다른 같은 기사를 다르게 본다")
    expect(len(content._urls({"sources": [{"url": "https://a.com/v?ref_id=1"}, {"url": "https://a.com/v?ref_id=2&ref=naver"}]})) == 2,
           "'ref_id' 같은 기사 번호를 추적용 쿼리로 지웠다")
    for bad in (True, 42, ["사유"], "첫 줄\n둘째 줄", "  "):
        expect("briefs_short_reason 은 사유 한 줄" in (ok({**copy.deepcopy(c), "date": "2026-10-19", "briefs_short_reason": bad}, "2026-10-19") or ""),
               f"잘못된 briefs_short_reason({bad!r})을 사유로 받았다")
    rew = {**copy.deepcopy(c), "date": "2026-10-19", "rewind": True}
    expect(ok(rew, "2026-10-19") is None, "예비 호까지 새 점검으로 막았다")
    return None


def t_repeat_check():
    """같은 회사·주제가 두 칸에 나오면 칸 쌍마다 한 번 알린다(10/19~) — 10/16 호의 스타벅스(H PICK·08)는 잡고, 흔한 낱말·날짜('서울'·'10월'·'연휴')는 넘긴다."""
    from edith import style
    c = json.loads((CONTENT_DIR / "2026-10-16.json").read_text(encoding="utf-8"))
    c["date"] = "2026-10-19"
    notes = style.repeat_check(c)
    expect(any("'스타벅스'" in n and n.startswith("H PICK·08 ") for n in notes), f"스타벅스 중복(H PICK·짧은 소식 08)을 못 잡는다: {notes}")
    expect(not any("'서울'" in n for n in notes), f"흔한 낱말 '서울'까지 잡는다: {notes}")
    for day in ("2026-10-08", "2026-10-09", "2026-09-28", "2026-10-03"):  # 9/28 은 '10월'이 세 칸, 10/3 은 '연휴'가 두 칸에 — 다른 소식이다
        x = json.loads((CONTENT_DIR / f"{day}.json").read_text(encoding="utf-8"))
        x["date"] = "2026-10-19"
        expect(not style.repeat_check(x), f"{day} 원고에서 흔한 낱말·날짜로 잘못 잡는다: {style.repeat_check(x)}")
    expect(not style.repeat_check({**c, "date": "2026-10-16"}), "10/19 전 호까지 경고한다")
    base = {"date": "2026-10-19", "title": "커피 17잔이면?", "big_issue": {"tag": "스타벅스"}, "briefs": []}
    # 두 칸 제목에 다 나와도 한 번만, 뒤 칸을 바꾸라고
    both = style.repeat_check({**base, "items": [{"tag": "카카오 선물하기", "title": "카카오 선물하기 수수료 9%"}, {"tag": "카카오 AI", "title": "카카오, 말로 주문"}]})
    expect(both == [n for n in both if n.startswith("02·03 ")] and len(both) == 1, f"같은 칸 쌍을 두 번(거꾸로도) 알린다: {both}")
    # 제목이 태그를 풀어 써도 태그끼리 같은 회사면 잡는다
    tags = style.repeat_check({**base, "items": [{"tag": "카카오", "title": "생수도 말로 주문해요"}, {"tag": "카카오", "title": "추천하고 돈 벌어요"}]})
    expect(len(tags) == 1 and "'카카오'" in tags[0], f"태그끼리 같은 회사를 못 잡는다: {tags}")
    # 영문 약칭은 낱말 전체로만 — KT 와 KTX 는 다르다
    kt = style.repeat_check({**base, "items": [{"tag": "KT 통신", "title": "KT 요금제 1만원 내린다"}], "briefs": [{"title": "KTX 예매가 11월 1일 열려요."}]})
    expect(not kt, f"'KT'를 'KTX' 안에서 잡는다: {kt}")
    # 짧은 소식끼리도 — 태그가 없어 제목 첫 낱말(주어)로 본다
    br = style.repeat_check({**base, "big_issue": {"tag": "주담대"}, "items": [], "briefs": [{"title": "스타벅스가 새 음료를 내요."}, {"title": "스타벅스가 할인 행사를 열어요."}]})
    expect(len(br) == 1 and br[0].startswith("02·03 ") and "'스타벅스'" in br[0], f"짧은 소식끼리 같은 회사를 못 잡는다: {br}")
    # 흔한 말 주어는 조사가 붙어도 넘긴다('정부가'·'오늘은')
    gen = style.repeat_check({**base, "big_issue": {"tag": "주담대"}, "items": [], "briefs": [{"title": "정부가 새 정책을 발표해요."}, {"title": "정부가 세법을 바꿔요."}, {"title": "오늘은 금통위가 열려요."}, {"title": "오늘은 배당 기준일이에요."}]})
    expect(not gen, f"조사 붙은 흔한 주어로 잘못 잡는다: {gen}")
    # 조사처럼 끝나는 이름('11번가')도 그대로 견준다
    st = style.repeat_check({**base, "items": [{"tag": "11번가", "title": "새벽 배송 시작"}], "briefs": [{"title": "11번가가 새 할인을 시작해요."}]})
    expect(len(st) == 1 and "'11번가'" in st[0], f"'11번가'를 못 잡는다: {st}")
    return None


def t_twosource():
    """숫자 2곳 대조(2026-11-05 호~, edith/twosource.py·check_sources.py·build_issue 의 막음): 11/03·11/04 호에 원 기사 한 곳에만 있는 숫자가
    2~4개씩 나갔다. 표기 차이(쉼표·띄어쓰기·%포인트·세는 말)와 어림값은 같은 값으로 보고, 한 곳뿐인 숫자는 막고, 못 읽은 기사·날짜는 경고만."""
    import check_sources
    import build_issue
    from edith import twosource as ts
    num = lambda s: ts.numbers(s)[0]   # noqa: E731
    art = lambda s: ts.article_numbers({"body": s})   # noqa: E731
    match = lambda c, a: any(ts.same(num(c), x) for x in art(a))   # noqa: E731
    expect(match("14조2209억원", "매출 14조 2,209억 원을 기록") and match("14.2조", "14조2209억원") and match("4.6조", "4조6472억원"),
           "표기·어림값이 같은 숫자를 다르다고 본다")
    expect(match("6000억원 넘게", "6423억원") and match("약 34만 원", "34만3300원") and match("3만5000여 명", "3만5200명"), "어림말이 붙은 숫자를 못 맞춘다")
    expect(not match("34만3000원", "34만3300원") and not match("10년", "12년") and not match("30%", "30년"), "다른 숫자를 같다고 본다")
    expect(match("0.25%포인트", "0.25%p") and match("광고주 1000만 곳", "광고주 1000만명"), "%포인트·세는 말 표기 차이를 못 맞춘다")
    expect(not ts.numbers("11/4 — SEC 보고서 · 2030세대 · https://x.kr/view?id=198581810 · 3분기"), "날짜 꼴·고정 표현·주소 번호·한 자리 수를 숫자로 본다")
    # 조·억·만 자리에서 자른·반올림한 값(11/05 ELS '국민은행 1723억원' = 기사 '1723억3400만원' — '어디에도 없다'고 잘못 알렸다)
    expect(match("1723억원", "과징금 1723억3400만원") and match("1724억원", "1723억 6000만 원") and match("3619억원", "3619억6000만원"),
           "조·억·만 자리에서 자르거나 반올림한 숫자를 못 맞춘다")
    expect(not match("1724억원", "1722억5000만원") and not match("1723억원", "1724억1000만원") and not match("34만원", "35만원")
           and not match("1.5억원", "1억5900만원"), "자리 맞춤이 너무 넓다")
    # 보도자료 첨부 PDF 를 하나라도 못 받으면 그 보도자료는 '못 읽음'(11/05 고용 — 두 번째 PDF 접속 끊김, 반쯤 읽은 본문으로 324만명·19.9% 를 막았다)
    import urllib.error
    import urllib.request

    import fetch_releases
    gov = "https://www.korea.kr/briefing/pressReleaseView.do?newsId=1"
    page = ("고용 동향 — 취업자 1,234만명, 5.6% 늘어 7조원\n첨부 PDF: 1.pdf\n    https://www.korea.kr/common/download.do?fileId=1\n"
            "첨부 PDF: 2.pdf\n    https://www.korea.kr/common/download.do?fileId=2")

    def half_pdf(u):
        if u.endswith("fileId=2"):
            raise ConnectionResetError("reset")
        return "1년 안에 일할 생각 324만명(19.9%)"
    real_read, real_pdf, real_open = fetch_releases.read, check_sources.pdf_text, urllib.request.urlopen
    fetch_releases.read, check_sources.pdf_text = (lambda u: page), half_pdf
    calls = []

    def flaky(req, timeout=None):
        calls.append(req.full_url)
        if "gone" in req.full_url:
            raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)
        if len(calls) == 1:
            raise ConnectionResetError("reset")
        return io.BytesIO(b"%PDF-1.4")
    try:
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stderr(io.StringIO()):
            expect(check_sources.fetch(gov, cache=tmp) is None and not check_sources.cache_path(gov, tmp).exists(),
                   "첨부 PDF 하나를 못 받은 보도자료를 읽은 것으로 본다(반쯤 읽은 본문으로 막는다)")
            check_sources.pdf_text = lambda u: "1년 안에 일할 생각 324만명(19.9%)"
            a = check_sources.fetch(gov, cache=tmp)
            expect(a and "19.9%" in a["body"] and check_sources.cache_path(gov, tmp).exists(), "첨부 PDF 를 다 받은 보도자료를 못 읽는다")
        urllib.request.urlopen = flaky
        expect(check_sources.download("https://x.kr/1.pdf", wait=0) == b"%PDF-1.4" and len(calls) == 2, "끊긴 PDF 를 다시 받지 않는다")
        calls.clear()
        try:
            check_sources.download("https://x.kr/gone.pdf", wait=0)
            expect(False, "없는 PDF(404)를 받은 것으로 본다")
        except urllib.error.HTTPError:
            expect(len(calls) == 1, f"없는 PDF(404)를 여러 번 다시 받는다: {calls}")
    finally:
        fetch_releases.read, check_sources.pdf_text, urllib.request.urlopen = real_read, real_pdf, real_open
    d = {"date": "2026-11-05", "format": 2, "card_issues": [{"tag": "가", "number": "14.2조", "body": "영업손실 6423억원"}],
         "all_items": [{"tag": "가", "body": "미국은 2024년 5월 바꿨고 매출 14조2209억원", "sources": [{"name": "A", "url": "u1"}, {"name": "B", "url": "u2"}]},
                       {"tag": "나", "body": "예약 385건, 30일부터", "sources": [{"name": "C", "url": "u3"}, {"name": "D", "url": "u4"}]}]}
    arts = {"u1": {"body": "매출 14조2209억원, 영업손실 6423억원. 미국은 2024년 5월"}, "u2": {"body": "14조2209억원 매출에 6,423억원 손실"},
            "u3": {"body": "일주일에 385건, 이달 30일부터"}, "u4": None}
    r = ts.check(d, arts)
    expect(len(r["blocked"]) == 1 and "'2024년'" in r["blocked"][0] and "A에만" in r["blocked"][0], f"한 곳에만 있는 숫자를 막지 않는다: {r['blocked']}")
    expect(any("[나]" in w and "1곳만 읽음" in w for w in r["warnings"]), "못 읽은 기사가 있는 이슈를 알리지 않는다")
    arts["u4"] = {"body": "예약 385건"}
    r = ts.check(d, arts)
    expect(any("'30일'" in w and "경고만" in w for w in r["warnings"]) and not any("30일" in b for b in r["blocked"]), "날짜(일)를 경고가 아니라 막음으로 본다")
    d["all_items"][0]["body"] += ", 점유율 7.22%"
    expect(any("'7.22%'" in w and "어디에도 없어요" in w for w in ts.check(d, arts)["warnings"]), "기사 어디에도 없는 숫자를 알리지 않는다")
    expect(check_sources.usable({"body": "2026년 10월 수출입 동향 — 첨부 PDF https://www.korea.kr/x?fileId=198581810"}) is False
           and check_sources.usable({"body": "수출 1153억 달러, 93.7% 증가, 반도체 564억 달러"}), "제목·안내문만 읽힌 보도자료를 읽은 것으로 본다")
    # 빌드 막음 — 그날(2026-11-05~) 새 호만, 읽어 둔 기사로 네트워크 없이
    kst = dt.timezone(dt.timedelta(hours=9))
    at = dt.datetime(2026, 11, 5, 7, 55, tzinfo=kst)
    saved = os.environ.pop("EDITH_SKIP_SOURCE_CHECK", None)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            single, notes = build_issue.source_check_problem(d, now=at, cache=tmp)
            expect(not single and any("check_sources.py" in n for n in notes), "읽어 둔 기사가 없을 때 막거나 알리지 않는다")
            for url, a in arts.items():
                p = check_sources.cache_path(url, tmp)
                p.write_text(json.dumps(a, ensure_ascii=False), encoding="utf-8")
            single, _ = build_issue.source_check_problem(d, now=at, cache=tmp)
            expect(len(single) == 1 and "2024년" in single[0], f"한 곳에만 있는 숫자가 있는데 빌드를 막지 않는다: {single}")
            expect(build_issue.source_check_problem({**d, "date": "2026-11-04"}, now=at.replace(day=4), cache=tmp) == ([], []),
                   "시작일(2026-11-05) 전 호를 막는다")
            expect(build_issue.source_check_problem(d, now=at.replace(day=6), cache=tmp) == ([], []), "지난 호를 다시 빌드할 때 막는다")
            expect(build_issue.source_check_problem({**d, "rewind": True}, now=at, cache=tmp) == ([], []), "예비 호를 막는다")
            os.environ["EDITH_SKIP_SOURCE_CHECK"] = "1"
            expect(build_issue.source_check_problem(d, now=at, cache=tmp) == ([], []), "EDITH_SKIP_SOURCE_CHECK(다시 빌드)에도 막는다")
    finally:
        os.environ.pop("EDITH_SKIP_SOURCE_CHECK", None)
        if saved is not None:
            os.environ["EDITH_SKIP_SOURCE_CHECK"] = saved
    return "표기·어림값 맞춤 · 한 곳뿐 막음 · 못 읽음·날짜·없는 숫자 경고 · 빌드 막음은 그날 새 호만"


def t_releases():
    """원문(보도자료) 읽기·H PICK 원문 점검(2026-10-22 운영자 '기사 소스가 부족하다' — 정규 11호 55건 중 원문 0건)."""
    import fetch_releases as fr
    from edith import style
    ex = ROOT / "automation" / "examples" / "releases"
    fsc = fr.parse_fsc((ex / "fsc_list.html").read_text(encoding="utf-8"))
    moel = fr.parse_moel((ex / "moel_list.html").read_text(encoding="utf-8"))
    korea = fr.parse_korea((ex / "korea_list.html").read_text(encoding="utf-8"))
    fss = fr.parse_fss((ex / "fss_list.html").read_text(encoding="utf-8"))
    mofe = fr.parse_mofe((ex / "mofe_list.html").read_text(encoding="utf-8"))
    expect(len(fsc) == 3 and fsc[0]["date"] == "2026-10-22" and fsc[0]["url"].startswith("https://www.fsc.go.kr/no010101/")
           and "국민성장펀드" in fsc[0]["title"], f"금융위원회 보도자료 목록을 못 읽는다: {fsc[:1]}")
    expect(len(moel) == 3 and moel[1]["title"].startswith("쿠팡 산업안전") and "news_seq=" in moel[1]["url"], f"고용노동부 목록을 못 읽는다: {moel[:2]}")
    expect(len(korea) == 3 and korea[0]["org"] == "외교부" and korea[0]["lead"], f"정책브리핑 목록(부처·요약)을 못 읽는다: {korea[:1]}")
    expect(len(fss) == 3 and fss[0]["date"] == "2026-10-22" and fss[0]["url"].endswith("view.do?nttId=243282&menuNo=200218")
           and "가짜 체인" in fss[0]["title"], f"금융감독원 목록을 못 읽는다: {fss[:1]}")
    expect(len(mofe) == 3 and mofe[1]["date"] == "2026-10-21" and mofe[1]["url"].endswith("searchNttId1=MOSF_000000000079710")
           and mofe[1]["title"].startswith("아시아·태평양"), f"재정경제부 목록을 못 읽는다: {mofe[:2]}")
    body = fr.read_page((ex / "fsc_view.html").read_text(encoding="utf-8"))
    expect("국민성장펀드" in body and "<" not in body, "금융위원회 보도자료 본문을 글자로 못 읽는다")
    body = fr.read_page((ex / "moel_view.html").read_text(encoding="utf-8"))
    expect("206건 위반" in body and "누리집" not in body and "<" not in body, "고용노동부 보도자료 본문 대신 사이트 메뉴를 읽는다")
    body = fr.read_page((ex / "korea_view.html").read_text(encoding="utf-8"))
    expect(body.startswith("김진아 외교부 2차관") and "글자크기" not in body
           and "https://www.korea.kr/common/download.do?fileId=198575699&tblKey=GMN" in body and ".hwpx" not in body,
           f"정책브리핑 본문(제목·첨부 PDF 주소)을 못 읽는다: {body[:200]}")
    body = fr.read_page((ex / "fss_view.html").read_text(encoding="utf-8"))
    expect(body.startswith("유명 가상자산거래소") and "소비자경보" in body and "<span" not in body, "금융감독원 보도자료 본문을 못 읽는다")
    body = fr.read_page((ex / "mofe_view.html").read_text(encoding="utf-8"))
    expect(body.startswith("(보도설명) 정부는 할당관세") and body.count("첨부 PDF") == 1 and "jsessionid" not in body
           and "https://www.mofe.go.kr/com/cmm/fms/FileDown.do?atchFileId=ATCH_000000000032967&fileSn=2" in body,
           f"재정경제부 보도자료(제목·첨부 PDF 주소)를 못 읽는다: {body[:300]}")
    expect([fr.is_primary(u) for u in ("https://www.fsc.go.kr/no010101/1", "https://www.korea.kr/briefing/x", "https://ecos.bok.or.kr/",
                                       "https://n.news.naver.com/mnews/article/1", "https://evil-go.kr.example.com/")] == [True, True, True, False, False],
           "원문 주소 판정이 틀렸다")
    # 쪽 넘기기·빈 목록·끊긴 응답(Codex 리뷰) — 실제 접속 없이 예시 페이지로
    page = {k: (ex / f"{k}_list.html").read_text(encoding="utf-8") for k in ("fsc", "moel", "fss", "korea")}
    calls = []

    def fake_get(url, tries=4):
        calls.append(url)
        if "fsc.go.kr" in url:
            return page["fsc"]
        if "moel.go.kr" in url:   # 2쪽은 하루 전 글
            return page["moel"].replace("2026.10.22", "2026.10.21") if "pageIndex=2" in url else page["moel"]
        if "fss.or.kr" in url:
            if "pageIndex=2" in url:
                raise OSError("끊김")   # 2쪽에서 끊겨도 1쪽 글은 남는다
            return page["fss"].replace("2026-10-21", "2026-10-22")
        if "mofe.go.kr" in url:
            return "<html>시스템 점검 중</html>"
        return page["korea"]   # 정책브리핑: 계속 같은 날짜 → 쪽 한도
    real_get = fr.get
    fr.get = fake_get
    try:
        found, failed = fr.releases(["2026-10-22"])
    finally:
        fr.get = real_get
    per = lambda host: sum(host in u for u in calls)
    expect((per("fsc.go.kr"), per("moel.go.kr"), per("fss.or.kr"), per("mofe.go.kr"), per("korea.kr")) == (1, 2, 2, 1, 8)
           and any("pageIndex=2" in u and "moel" in u for u in calls), f"쪽 넘기기가 틀렸다: {calls}")
    expect(sorted(failed) == ["금융감독원(2쪽부터 못 읽음)", "재정경제부(목록을 못 알아봄)", "정책브리핑(앞 8쪽까지만)"],
           f"끊김·빈 목록·쪽 한도를 알리지 않는다: {failed}")
    expect(sum(i["org"] == "고용노동부" for i in found) == 3 and sum(i["org"] == "금융감독원" for i in found) == 3
           and all(i["date"] == "2026-10-22" for i in found), "기간 밖 글이 섞였거나 끊기기 전 글을 잃었다")
    import http.client
    import urllib.request

    class _Resp:
        headers = type("H", (), {"get_content_charset": lambda self: "utf-8"})()
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return "본문".encode()
    tries = []

    def flaky(req, timeout=0):
        tries.append(1)
        if len(tries) == 1:
            raise http.client.IncompleteRead(b"")
        return _Resp()
    real_open, real_sleep = urllib.request.urlopen, fr.time.sleep
    urllib.request.urlopen, fr.time.sleep = flaky, (lambda s: None)
    try:
        expect(fr.get("https://www.fsc.go.kr/x") == "본문" and len(tries) == 2, "응답 도중 끊기면 다시 받지 않는다")
    finally:
        urllib.request.urlopen, fr.time.sleep = real_open, real_sleep
    c = json.loads((CONTENT_DIR / "2026-10-22.json").read_text(encoding="utf-8"))
    expect(not style.primary_check(c), "원문 점검이 시작일(10/23) 전 호까지 본다")
    c["date"] = "2026-10-23"
    expect(style.primary_check(c), "H PICK 출처가 모두 기사인데 원문 경고가 없다")
    c["big_issue"]["sources"] = c["big_issue"]["sources"] + [{"name": "금융위원회 보도자료", "url": "https://www.fsc.go.kr/no010101/87977"}]
    expect(not style.primary_check(c), "원문 출처가 있는데도 경고한다")
    return f"금융위 {len(fsc)}·고용부 {len(moel)}·금감원 {len(fss)}·재경부 {len(mofe)}·정책브리핑 {len(korea)}건(예시)"


def t_headlines():
    """큰 소식(네이버 섹션 묶음·많이 본 뉴스)·회고의 놓침 비교·성과표 출처 품질(2026-10-23 운영자 '경쟁사와 비교해도 부족함 없이')."""
    import collect_metrics
    import compare_anjang
    import fetch_headlines as fh
    from edith import style
    ex = ROOT / "automation" / "examples" / "headlines"
    sec = fh.parse_section((ex / "section_101.html").read_text(encoding="utf-8"), "경제")
    expect(len(sec) == 10 and max(c["count"] for c in sec) == 129 and sec[0]["count"] == 21 and sec[0]["press"] == "KBS" and sec[0]["url"].startswith("https://n.news.naver.com/")
           and sec[0]["cluster"].startswith("https://news.naver.com/cluster/"), f"섹션 헤드라인 묶음(숨은 뒤 절반 포함)을 못 읽는다: {sec[:1]}")
    ranked = fh.parse_ranking((ex / "ranking.html").read_text(encoding="utf-8"))
    expect(len(ranked) == 30 and "JTBC" not in {r["press"] for r in ranked}, "많이 본 뉴스를 경제·IT 매체로 거르지 못한다")
    groups = fh.popular_groups(ranked)
    expect(groups[0]["title"].startswith("[속보]AI 투자 불안에 나스닥") and len(groups[0]["presses"]) == 3,
           f"여러 매체에 함께 오른 소식이 맨 위가 아니다: {groups[:1]}")
    clu = fh.parse_cluster((ex / "cluster.html").read_text(encoding="utf-8"))
    expect(len(clu) == 5 and clu[0]["press"] == "뉴시스" and clu[0]["press"] in fh.WIRE, f"기사 묶음(언론사별)을 못 읽는다: {clu[:1]}")
    expect((ROOT / "automation" / "headlines").is_dir(), "automation/headlines/ 가 없다 — 제작 5단계 git add 가 실패한다")
    c = json.loads((CONTENT_DIR / "2026-10-22.json").read_text(encoding="utf-8"))
    snap = {"clusters": [{"section": "경제", "count": 40, "title": c["items"][0]["title"], "lede": "", "url": "u1"},
                         {"section": "사회", "count": 90, "title": "역삼동 방화범 살인미수 적용 검토", "lede": "", "url": "u2"},
                         {"section": "IT", "count": 5, "title": "작은 소식", "lede": "", "url": "u3"}],
            "popular": [{"title": "나스닥 급락 반도체주 투매", "url": "u4", "presses": ["이데일리 1위", "조선비즈 4위"]},
                        {"title": "한 곳만", "url": "u5", "presses": ["매일경제 1위"]},
                        {"title": "역삼동 방화범 살인미수 적용", "url": "u6", "presses": ["머니투데이 1위", "이데일리 2위"]}]}
    clusters, popular, other = compare_anjang.compare_big(snap, c)
    expect([w is not None for _, w in clusters] == [True] and [w for _, w in popular] == [None]
           and [x["section"] for x, _ in other] == ["사회"],
           f"큰 소식 놓침 판정(20건 미만·한 곳만·묶음과 같은 소식은 빼고, 사회·세계는 점수 밖 참고로): {clusters} {popular} {other}")
    q = style.source_quality(c)
    expect(q == {"main": 5, "primary": 0, "pick_primary": False, "outlets": 10, "wire": 20, "solo": 0}, f"출처 품질 계산: {q}")
    c2 = json.loads(json.dumps(c))
    c2["big_issue"]["sources"] = [{"name": "금융위원회 보도자료", "url": "https://www.fsc.go.kr/no010101/1"}]
    q2 = style.source_quality(c2)
    expect(q2["primary"] == 1 and q2["pick_primary"] and q2["solo"] == 1, f"원문·한 곳뿐 판정: {q2}")
    lines = "\n".join(collect_metrics.source_lines([("2026-10-22", {"src": q, "big": [3, 5, False]}), ("2026-10-20", {"src": q2, "big": [4, 4, True]})]))
    expect("| 2026-10-22 | 0/5 | × | 10 | 20% | 0 | 3/5 |" in lines and "4/4(일부 못 읽음)" in lines
           and "H PICK 원문 **1/2**" in lines and "큰 소식 다룸 3/5" in lines,
           f"성과표 출처 품질 칸: {lines}")
    expect("src" not in collect_metrics.issue_facts("2026-10-21"), "예비 호까지 출처 품질을 잰다")
    late = {**c, "date": "2999-01-01"}
    expect(not style.headlines_check(c) and not style.headlines_check({**c, "date": "2026-10-24"})
           and style.headlines_check(late) and "fetch_headlines.py --save" in style.headlines_check(late)[0],
           "큰 소식 기록이 없을 때 빌드가 알리지 않는다(시작 전·기록 있는 날은 조용히)")
    return f"묶음 {len(sec)}·많이 본 {len(ranked)}건→{len(groups)}묶음·기사 묶음 {len(clu)}건"


def t_agents_doc():
    """AGENTS.md(자비스·Codex 등 GPT 에이전트 인수인계, 2026-10-25)가 가리키는 파일·워크플로가 실제로 있는지 — 이름이 바뀌면 여기서 걸린다."""
    import re as _re
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    paths = {m for m in _re.findall(r"`((?:automation|content|instagram)/[^`{}*\s]+)`", text) if not m.endswith("/")}
    flows = set(_re.findall(r"`([a-z-]+\.yml)`", text))
    missing = sorted(x for x in paths if not (ROOT / x).exists()) + sorted(f for f in flows if not (ROOT / ".github" / "workflows" / f).exists())
    expect(paths and flows and not missing, f"AGENTS.md 가 없는 파일·워크플로를 가리킨다: {missing}")
    return f"파일 {len(paths)}개·워크플로 {len(flows)}개"


def t_codex_fallback():
    """Claude 가 멈춘 날 Codex 자동 대체(codex-fallback.yml, 2026-10-25): 시작 판단·표시·회고 판단·허용 경로·워크플로 연결."""
    import codex_fallback as cf
    from edith.common import now_kst
    t = now_kst().replace(year=2026, month=10, day=26, hour=7, minute=56, second=0, microsecond=0)
    d = "2026-10-26"
    expect(cf.produce_decision(d, t, False, set(), True)[0], "07:55 뒤 표시·오늘 호 없으면 Codex 가 시작해야 한다")
    for args, why in [((d, t, False, {"claude"}, True), "Claude 표시"), ((d, t, False, {"codex"}, True), "Codex 표시"),
                      ((d, t, True, set(), True), "오늘 호 있음"), ((d, t, False, set(), False), "키 없음"),
                      ((d, t.replace(hour=8, minute=26), False, set(), True), "08:25 뒤"),
                      ((d, t.replace(minute=40), False, set(), True), "07:55 전")]:
        expect(not cf.produce_decision(*args)[0], f"{why}인데 Codex 가 시작한다")
    ls = "a\trefs/heads/run-claim/2026-10-26-claude\nb\trefs/heads/run-claim/2026-10-25-codex\nc\trefs/heads/main\n"
    expect(cf.parse_claims(ls, d) == {"claude"} and cf.parse_claims(ls, "2026-10-25") == {"codex"}, "표시 가지를 날짜별로 못 읽는다")
    expect(cf.retro_target(t.replace(hour=3)) == ("2026-10-25", True) and cf.retro_target(t.replace(hour=22, minute=10)) == (d, False)
           and cf.retro_target(t.replace(hour=23, minute=40)) == (d, True), "회고 날짜·기다림 판단이 틀렸다")
    expect(cf.retro_done(d, f"Collect metrics\nEditor retrospective {d} (Codex 대체 회고)\n") and not cf.retro_done(d, "Editor retrospective 2026-10-25\n"),
           "회고 커밋 판단이 틀렸다")
    pats = [x.format(d=d) for x in cf.PRODUCE_PATHS]
    expect(all(cf.allowed(x, pats) for x in (f"{d}.html", f"content/{d}.json", f"instagram/{d}/01.png", "manifest.json", "assets/photos/x.jpg",
                                             f"content/weekly/{d}.json", f"instagram/{d}-weekly/01.png"))
           and not any(cf.allowed(x, pats) for x in ("automation/build_issue.py", "content/2026-10-25.json", ".github/workflows/x.yml")),
           "Codex 가 남길 수 있는 경로 판단이 틀렸다")
    # 되돌리기: 스테이징한 변경까지 HEAD 로, 허용 밖 새 파일은 인덱스·디스크에서(Codex 리뷰) — 임시 저장소에서
    import subprocess
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        tdir = Path(tmp)
        run = lambda *a: subprocess.run(["git", "-C", tmp, *a], capture_output=True, text=True, check=True)   # noqa: E731
        run("init", "-q")
        run("config", "user.email", "t@t"), run("config", "user.name", "t")
        (tdir / "code.py").write_text("ok\n")
        (tdir / "content").mkdir()
        run("add", "."), run("commit", "-q", "-m", "base")
        (tdir / "code.py").write_text("bad\n")
        (tdir / "evil.py").write_text("x\n")
        (tdir / "content" / "2026-10-26.json").write_text("{}\n")
        run("add", "code.py", "evil.py")
        real_root = cf.ROOT
        cf.ROOT = tdir
        try:
            bad = cf.restore(["content/*"])
        finally:
            cf.ROOT = real_root
        status = run("status", "--porcelain", "--untracked-files=all").stdout
        expect(sorted(bad) == ["code.py", "evil.py"] and (tdir / "code.py").read_text() == "ok\n" and not (tdir / "evil.py").exists()
               and status.strip() == "?? content/2026-10-26.json", f"허용 밖 변경(스테이징 포함)을 되돌리지 못한다: {bad} / {status!r}")
    wf = (ROOT / ".github" / "workflows" / "codex-fallback.yml").read_text(encoding="utf-8")
    expect("openai/codex-action@v1" in wf and wf.count("persist-credentials: false") == 2 and "secrets.OPENAI_API_KEY != ''" in wf
           and "restore --produce" in wf and "alert.py codex" in wf and wf.count("git reset -q") == 2 and "collect-metrics.yml" in wf
           and wf.index("wait_until_send.py schedule") < wf.index("gh workflow run send-newsletter.yml")
           and 'git add "content/weekly/$DATE.json"' in wf and "git diff --quiet HEAD --" in wf
           and not any("Codex" in ln for ln in wf.splitlines() if "git commit -m" in ln), "codex-fallback.yml 의 안전장치(토큰 없이·키 확인·되돌림·인덱스 비우기·성과표·커밋에 AI 이름 없음)가 빠졌다")
    expect("codex_fallback.py wait-codex" in (ROOT / ".github" / "workflows" / "rewind.yml").read_text(encoding="utf-8"),
           "예비 호가 Codex 제작을 기다리지 않는다")
    rb = (ROOT / "automation" / "RUNBOOK.md").read_text(encoding="utf-8")
    expect("codex_fallback.py claim claude" in rb and "origin/main:{날짜}.html" in rb, "RUNBOOK 에 제작 시작 표시·푸시 전 확인이 없다")
    return "시작 판단 7가지·표시·회고·허용 경로·워크플로 연결"


def t_poll_paused():
    """월요일 투표는 2026-10-19 부터 쉰다(세 번 모두 참여 0명) — poll_due 를 내지 않고, 원고의 poll 은 빌드가 막는다."""
    import check_today
    from edith import content
    cfg = load_config()
    expect(cfg["poll"].get("paused_from") == "2026-10-19", "config.poll.paused_from 이 없다")
    due, _ = check_today.poll_status(parse_date("2026-10-19"), "월", cfg)
    expect(not due, "10/19(월) 에 투표를 내라고 한다")
    due, _ = check_today.poll_status(parse_date("2026-10-12"), "월", {"poll": {"min_votes": 5}})
    expect(due, "쉬기 전(스위치 없음) 월요일에 투표를 안 낸다")
    c = json.loads((CONTENT_DIR / "2026-10-12.json").read_text(encoding="utf-8"))
    expect(c.get("poll"), "10/12 원고에 poll 이 없다(점검 전제)")
    content.prepare(json.loads(json.dumps(c)), "2026-10-12")   # 지난 호는 그대로 통과
    x = {**json.loads(json.dumps(c)), "date": "2026-10-19", "briefs_short_reason": "점검용"}
    try:
        content.prepare(x, "2026-10-19")
        expect(False, "10/19 원고의 poll 을 막지 않았다")
    except content.ContentError as e:
        expect("독자 투표는 2026-10-19 부터 쉽니다" in str(e), f"poll 이 아닌 다른 이유로 막혔다: {e}")
    x.pop("poll")
    try:
        content.prepare(x, "2026-10-19")
    except content.ContentError as e:
        expect("투표" not in str(e), f"poll 을 뺐는데도 투표 때문에 막혔다: {e}")
    return None


def t_todo_box():
    """오늘 챙길 것(10/16~): content.todo 가 있으면 그것, 없으면 결론 문장 앞 3개 — 10/15 호·예비 호엔 없다."""
    from edith import content, newsletter
    d = content.load("2026-10-15")
    expect(newsletter._todo(d) == "", "10/15 호에 '오늘 챙길 것'이 붙었다")
    d["date"] = "2026-10-16"
    box = newsletter._todo(d)
    expect("오늘 챙길 것" in box and box.count("☐") == 3, "10/16~ 결론 문장으로 3줄을 못 채운다")
    d["todo"] = ["청년미래적금 2차, 16일 마감 전 신청"]
    expect("16일 마감 전 신청" in newsletter._todo(d) and newsletter._todo(d).count("☐") == 1, "content.todo 를 안 쓴다")
    expect(newsletter._todo({**d, "rewind": True}) == "", "예비 호에 '오늘 챙길 것'이 붙었다")
    return None


def t_commit_dates():
    """봇 기록 커밋 이름은 KST 날짜 — UTC 로 찍으면 08:00 게시 기록이 '어제' 이름으로 남는다(2026-10-11 'Record Instagram post (2026-10-10)')."""
    bad = []
    for wf in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        for ln in wf.read_text(encoding="utf-8").splitlines():
            if "git commit" in ln and "date -u" in ln:
                bad.append(wf.name)
    expect(not bad, f"커밋 이름에 UTC 날짜를 쓰는 워크플로: {', '.join(bad)}")
    # 이름은 기록 파일의 날짜 — 토큰·시험 기록(_token·trial_probe)은 날짜가 아니다(Codex 리뷰), 늦게 돈 알림은 전날 파일 이름
    staged = "automation/ig_posted/_token.json\nautomation/ig_posted/2026-10-10.json\nautomation/ig_posted/2026-10-16-weekly.json\n" \
             "automation/ig_posted/trial_probe.json\nautomation/metrics/summary.md\n"
    n = 0
    for wf in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        for ln in wf.read_text(encoding="utf-8").splitlines():
            m = re.search(r"git diff --cached --name-only -- \S+ \| (sed -nE '[^']+')", ln)
            if m:
                out = subprocess.run(["bash", "-c", m.group(1) + " | sort -u | paste -sd, -"], input=staged,
                                     capture_output=True, text=True, check=True).stdout.strip()
                expect(out == "2026-10-10,2026-10-16-weekly", f"{wf.name} 커밋 이름 키 추출: {out!r}")
                n += 1
    expect(n >= 5, f"기록 파일 날짜로 이름 짓는 워크플로가 {n}개뿐")
    return f"날짜 파일 이름 {n}개 워크플로"

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
    # 같은 이야기(태그) 되풀이 — '경기 버스 파업'이 10/24 H PICK → 10/26 예비 호 메인 → 10/28 예비 호 H PICK(2026-10-28 회고)
    recent = build_rewind._recent_tags("2026-10-28")
    expect("경기 버스 파업" in recent, f"최근 예비 호·H PICK 에 실린 태그를 못 센다: {sorted(recent)}")
    with contextlib.redirect_stdout(io.StringIO()):
        top28, items28, _ = build_rewind.pick("2026-10-28")
    again28 = [x[0]["tag"] for x in [top28, *items28] if x[0]["tag"] in recent]
    expect(not again28, f"10/28 예비 호가 5일 안에 실린 이야기를 또 고른다: {again28}")
    import inspect
    expect("내일 아침엔" not in inspect.getsource(build_rewind.build),
           "예비 호가 '내일 아침엔 새 소식으로'를 약속한다 — 사흘 연속 나가 이틀은 못 지켰다(10/28 회고, 원칙 5)")
    for past in ("2026-09-30", "2026-10-07"):   # 실제 예비 호 날 — 이틀 전 H PICK 을 다시 실었던 날(10/8 회고)
        gap = (parse_date(past) - parse_date(build_rewind.pick(past)[0][2])).days
        expect(gap > build_rewind.PICK_GAP_DAYS, f"{past} 예비 호 H PICK 이 {gap}일 전 호의 H PICK 이다")
        with contextlib.redirect_stdout(io.StringIO()):
            expect(build_rewind.cover_photo(past, ["다시 볼 이야기"]), f"{past} 예비 호 표지에 대체 사진이 안 붙는다")
    # 그날·그 연휴에만 맞는 이야기 — 10/14 예비 호가 10/3 호 '연휴 날씨'(일요일 밤부터 비)를 그대로 실었다(10/14 회고)
    with contextlib.redirect_stdout(io.StringIO()):
        tags = [x[0]["tag"] for x in build_rewind.pick("2026-10-14")[1]]
    expect("연휴 날씨" not in tags, f"10/14 예비 호가 또 '연휴 날씨'를 고른다: {tags}")
    expect(build_rewind._dated({"tag": "날씨", "title": "아침은 5도"}, {}), "'날씨' 태그를 그날 이야기로 못 본다")
    expect(build_rewind._dated({"tag": "소비", "title": "일요일 밤부터 비"}, {}), "제목의 요일을 못 본다")
    expect(not build_rewind._dated({"tag": "편의점 매출", "title": "편의점 성장률 1.5%", "body": "주말 매출이 줄었어요"}, {}),
           "본문에만 '주말'이 든 이야기까지 뺀다")
    expect(build_rewind._dated({"tag": "축제", "title": "이번 주말 축제"}, {}), "'이번 주말'을 그날 이야기로 못 본다")
    expect(build_rewind._dated({"tag": "할인", "title": "개천절 할인"}, {}), "공휴일 이름(개천절)을 그날 이야기로 못 본다")
    expect(build_rewind._live_checklist(["이번 주말에 방문하세요", "일요일까지 신청하세요", "앱에서 서류 2개를 내요"], "2026-10-03", "2026-10-10")
           == ["앱에서 서류 2개를 내요"], "체크리스트의 요일·주말 줄을 예비 호에 그대로 싣는다")
    expect(build_rewind._live_checklist(["금요일까지 신청하세요"], "2026-10-12", "2026-10-13"), "월요일 호의 '금요일까지'를 화요일에 지났다고 본다")
    expect(not build_rewind._live_checklist(["금요일까지 신청하세요"], "2026-10-12", "2026-10-17"), "지난 금요일 줄을 남긴다")
    expect(build_rewind._live_checklist(["내년 설 연휴(2월 6~9일) 캠페인 시작일을 역산해 두기"], "2026-09-24", "2026-10-10"),
           "미래 날짜가 박힌 연휴 줄('2월 6~9일')을 뺀다")
    expect(build_rewind._live_checklist(["한글날 전에 신청하세요"], "2026-10-01", "2026-10-02"), "아직 오지 않은 한글날 줄을 뺀다")
    expect(not build_rewind._live_checklist(["한글날 전에 신청하세요"], "2026-10-01", "2026-10-10"), "지난 한글날 줄을 남긴다")
    expect(build_rewind._live_checklist(["다음 금요일까지 신청하세요"], "2026-10-16", "2026-10-17"), "'다음 금요일'을 그날 금요일로 본다")
    expect(not build_rewind._live_checklist(["한글날 전에 신청하세요"], "2026-10-01", "2026-10-09"), "'한글날 전에'를 한글날 당일에도 남긴다")
    expect(not build_rewind._live_checklist(["다음 금요일까지 신청하세요"], "2026-10-10", "2026-10-17"), "토요일 호의 '다음 금요일'을 두 주 뒤로 본다")
    expect(build_rewind._live_checklist(["블랙 프라이데이 전에 신청하세요"], "2026-11-01", "2026-11-02"), "블랙프라이데이(11/27) 줄을 미리 뺀다")
    expect(build_rewind._live_checklist(["개천절 연휴에 방문하세요"], "2026-09-28", "2026-10-05"), "대체공휴일(10/5)까지 이어지는 개천절 연휴 줄을 10/3 에 끝났다고 본다")
    expect(build_rewind._live_checklist(["금요일부터 신청하세요"], "2026-10-12", "2026-10-17"), "'금요일부터'(시작일)를 마감으로 본다")
    expect(not build_rewind._live_checklist(["개천절 전에 신청하세요"], "2026-09-28", "2026-10-03"), "'개천절 전에'를 대체공휴일까지 늘린다")
    expect(build_rewind._holiday_dates("크리스마스", parse_date("2027-12-20"), period=True) == parse_date("2027-12-27"),
           "'크리스마스 연휴'가 성탄절 대체공휴일(2027-12-27)을 못 찾는다")
    expect(build_rewind._dated({"tag": "위고비", "title": "위고비, 이르면 이번 주 건강보험 신청"}, {}), "제목의 '이번 주'를 그날 이야기로 못 본다")
    for ln in ("노동절 전에 신청하세요", "석가탄신일 전에 신청하세요", "부처님 오신 날 전에 신청하세요"):   # _DATED 의 이름은 모두 날짜로 풀린다
        expect(build_rewind._live_checklist([ln], "2026-04-01", "2026-04-02"), f"아직 오지 않은 공휴일 줄을 뺀다: {ln}")
    expect(not build_rewind._live_checklist(["주말에 방문하세요"], "2026-10-03", "2026-10-10"), "맨 '주말' 줄을 주말이 지나도 남긴다")
    expect(build_rewind._dated({"tag": "디지털 효도", "title": "부모님 폰"}, {"takeaway": "이번 연휴에 같이 봐요"}),
           "카드 말풍선의 '이번 연휴에'를 못 본다")
    expect(not build_rewind._dated({"tag": "은행", "title": "은행 문 늦게 연다", "takeaway": "창구 일은 저녁·주말에"}, {}),
           "'저녁·주말에' 같은 일반 표현까지 뺀다")
    # 박힌 날짜가 지난 할 일 — 10/10 예비 호가 10/3 호 결론 '7일 전에'를 그대로 실었다(10/10 회고)
    expect(build_rewind._expired("만 19~34세라면 7일 전에 동의부터 받아 두세요", "2026-10-03", "2026-10-10"), "'7일 전에'(10/3 호)가 10/10 에 지난 줄 모른다")
    expect(not build_rewind._expired("최근 7일 도달·7일간 무료", "2026-10-03", "2026-10-10"), "기간(최근 7일·7일간)을 날짜로 읽는다")
    expect(build_rewind._live_checklist(["7일 홀수·8일 짝수, 12~16일엔 누구나", "11월 16~27일에 꼭 계좌 개설"], "2026-10-03", "2026-10-17")
           == ["11월 16~27일에 꼭 계좌 개설"], "체크리스트에서 지난 날짜 줄을 못 뺀다(범위는 끝 날짜)")
    expect(build_rewind._live_checklist(["7일 홀수·8일 짝수, 12~16일엔 누구나"], "2026-10-03", "2026-10-10"),
           "아직 남은 날짜(12~16일)가 있는 줄을 뺐다")
    expect(not build_rewind._dates("상환 정보 반영엔 영업일 2~3일이 걸려요", parse_date("2026-10-01")), "기간(영업일 2~3일)을 날짜로 읽는다")
    expect(not build_rewind._expired("2027년 5월 1일까지 신청", "2026-08-01", "2026-08-10"), "명시한 연도(2027년)를 무시한다")
    expect(build_rewind._expired("7일 전에 동의부터", "2026-10-03", "2026-10-07"), "'7일 전에'를 7일 당일엔 아직 된다고 본다")
    expect(not build_rewind._expired("16일까지 신청", "2026-10-03", "2026-10-16"), "'16일까지'를 16일 당일에 지났다고 본다")
    # 살아 있는 H PICK 이 사흘 안에 실렸어도, 결론 날짜가 지난 오래된 H PICK 보다 먼저(Codex 리뷰)
    src = ["a", "b"]
    old_pick = ({"tag": "가", "title": "가", "takeaway": "5일 전에 신청하세요", "sources": src}, {}, "2026-10-01", True, {"title": "가"})
    new_pick = ({"tag": "나", "title": "나", "takeaway": "명세서를 훑어보세요", "sources": src}, {}, "2026-10-10", True, {"title": "나"})
    filler = [({"tag": f"t{i}", "title": f"t{i}", "takeaway": "확인하세요", "sources": src}, {}, f"2026-10-0{i}", False, {"title": f"x{i}"})
              for i in range(2, 6)]
    saved = (build_rewind.pool, build_rewind._scores, build_rewind._used, build_rewind._rewind_picks)
    build_rewind.pool = lambda d: [old_pick, new_pick, *filler]
    build_rewind._scores = lambda: {}
    build_rewind._used = lambda d: set()
    build_rewind._rewind_picks = lambda d, on=None: {}
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            got = build_rewind.pick("2026-10-12")[0]
        expect(got[2] == "2026-10-10", f"살아 있는 H PICK 대신 결론 날짜가 지난 {got[2]} H PICK 을 골랐다")
    finally:
        build_rewind.pool, build_rewind._scores, build_rewind._used, build_rewind._rewind_picks = saved
    with contextlib.redirect_stdout(io.StringIO()):
        t10 = build_rewind.pick("2026-10-10")[0]
    expect(not build_rewind._expired(t10[0].get("takeaway"), t10[2], "2026-10-10"), f"10/10 예비 호 H PICK 결론 날짜가 지났다: {t10[0].get('takeaway')}")
    top, items, _ = build_rewind.pick(today)
    days = {top[2], *(x[2] for x in items)}
    expect(len(items) == 4, "예비 호 아이템 4개")
    if len(days) < 3:   # pick() 의 마지막 완화 단계(한 호에서 여러 개)는 허용된 동작 — 실패가 아니라 알림
        NOTES.append(f"예비 호가 {len(days)}개 호에서만 골랐다 — 최근 3주에 쓸 만한 호가 적다(완화 단계로 선정)")
    # 오늘 날짜로 다시 실으면 막히는 지난 카드는 고르지 않는다 — 골랐다간 예비 호 빌드(content.prepare)까지 멈춘다
    # (11/03 ① '담보대출 금리'·③ '63억$'은 11/04~, 11/05 ② '다우 급등 → 오피넷 최저가'는 11/06~ 규칙에 걸린다)
    from edith import content as content_mod
    keys = {(x[2], int(x[1]["no"])) for x in build_rewind.pool("2026-11-06")}
    expect(keys and not keys & {("2026-11-03", 1), ("2026-11-03", 3), ("2026-11-05", 2)},
           f"예비 호 후보에 오늘 규칙으로 막히는 지난 카드가 있다: {sorted(keys & {('2026-11-03', 1), ('2026-11-03', 3), ('2026-11-05', 2)})}")
    with contextlib.redirect_stdout(io.StringIO()):
        rw = build_rewind.build("2026-11-06")
    try:
        content_mod.prepare(rw, "2026-11-06")
        ok = True
    except content_mod.ContentError as e:
        ok = str(e)
    expect(ok is True, f"11/06 예비 호가 카드 글 점검에 막힌다: {ok}")
    return f"{len(days)}개 호에서 5개 · 막히는 지난 카드 안 고름"


def t_metrics():
    import collect_metrics
    snaps = sorted((AUTOMATION / "metrics" / "daily").glob("*.json"))
    expect(snaps, "성과표 스냅숏이 없다")
    md = collect_metrics.summary_md(json.loads(snaps[-1].read_text(encoding="utf-8")))
    expect(md.startswith("# EDIT H 성과표"), "성과표 머리말")
    # 2026-10-25·10-29 회고 '출처 품질 표에 같은 날짜가 두 줄씩' — 커밋된 성과표 25판에서 재현 안 됨(호별 성과 표와 한 번씩 나온다). 생기면 잡는다
    for p in snaps[-5:]:
        sec = collect_metrics.summary_md(json.loads(p.read_text(encoding="utf-8"))).split("## 출처 품질")[-1].split("\n- 최근")[0]
        days = re.findall(r"^\| (20\d\d-\d\d-\d\d) \|", sec, re.M)
        expect(len(days) == len(set(days)), f"{p.stem} 성과표 출처 품질 표에 같은 날짜가 두 줄: {sorted(d for d in days if days.count(d) > 1)}")
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
    home = (ROOT / "index.html").read_text(encoding="utf-8")
    expect(f'data-from="{g["from"]}" data-until="{g["until"]}"' in home, "index.html(첫 화면 구독) 선물 상자 날짜가 config.gift 와 다르다")
    gift = active_gift(g["from"])
    expect(gift and gift["url"].endswith(f"/gift/{g['slug']}.html"), "기간 첫날에 선물이 켜져야 한다")
    import sync_subscribers
    tz = now_kst().tzinfo
    y, m, d = map(int, g["from"].split("-"))
    msg = sync_subscribers.welcome_message("a@example.com", "b@example.com", load_config(), now=dt.datetime(y, m, d, 7, 10, tzinfo=tz))
    expect(gift["url"] in msg.get_body(preferencelist=("plain",)).get_content(), "환영 메일에 선물 링크가 없다")
    # 아직 안 지난 항목만 센다(2026-11-06~ — 11/05 구독 길 점검: 첫 화면·캡션은 '18가지'였는데 3가지는 10월에 끝났다). 그 전 날짜는 모두(지난 캡션 그대로)
    from edith import gift as gift_mod
    from edith import site as site_mod
    every = gift_mod.items(data)
    for it in every:
        expect(not it.get("until") or (re.fullmatch(r"\d{4}-\d{2}-\d{2}", it["until"]) and it["until"] <= g["until"]),
               f"선물 항목 '{it['do']}' 의 until 이 날짜(YYYY-MM-DD, 선물 기간 안)가 아니다: {it.get('until')}")
    before = (dt.date.fromisoformat(gift_mod.LIVE_FROM) - dt.timedelta(days=1)).isoformat()
    if g["from"] <= before:
        expect(active_gift(before)["count"] == len(every), "LIVE_FROM 전 날짜는 모두 세야 한다(게시된 캡션을 다시 빌드해도 같게)")
    for day in (gift_mod.LIVE_FROM, "2026-12-01", g["until"]):
        live = gift_mod.live_items(data, day)
        expect((active_gift(day) or {}).get("count") == (len(live) or None), f"{day} 선물 가짓수가 남은 항목 수({len(live)})와 다르다")
        expect(all(not it.get("until") or it["until"] >= day for it in live), f"{day}: 지난 항목을 남은 것으로 센다")
    expect(any(it.get("until") and it["until"] < gift_mod.LIVE_FROM for it in every)
           and active_gift(gift_mod.LIVE_FROM)["count"] < len(every), "10월에 끝난 항목이 LIVE_FROM 부터 빠지지 않는다")
    html_page = page.read_text(encoding="utf-8")
    expect(html_page.count("data-until=") == sum(1 for it in every if it.get("until")) and "li[data-until]" in html_page
           and '<span id="n">' in html_page, "선물 페이지가 지난 항목을 숨기지 못한다(data-until·숨김 스크립트·가짓수 칸)")
    expect(f"if (today < '{gift_mod.LIVE_FROM}') return;" in html_page,
           "선물 페이지가 가짓수 세기 시작일(LIVE_FROM) 전부터 숨긴다 — 그날 환영 메일·캡션의 'N가지'와 페이지가 어긋난다(Codex 리뷰)")
    for name, text in (("index.html", home), ("subscribe.html", sub)):
        box = re.search(r'<div class="gift" id="gift"[^>]*>(.*?)</div>', text, re.DOTALL)
        expect(box and not re.search(r"\d+\s*가지", re.sub(r"<[^>]+>", "", box.group(1))),
               f"{name} 선물 상자에 가짓수를 박아 두었다 — 항목이 지나면 틀린 숫자가 된다(가짓수는 캡션·환영 메일이 그날 센다)")
    # 릴스·웹툰 끝 '구독하면 받는 것'(PROMO_FROM~): 카드 릴스 캡션·끝 장 문구, AI 릴스·웹툰 캡션의 그 줄은 qa 숫자 대조에서 뺀다
    start = gift_mod.PROMO_FROM
    prev = (dt.date.fromisoformat(start) - dt.timedelta(days=1)).isoformat()
    from edith import content as content_mod
    d = dict(content_mod.load(daily_issues(1)[0]))
    letter = site_mod.reel_letter(start)
    expect(letter in site_mod.reel_caption(dict(d, date=start)) and site_mod.reel_letter(prev) not in site_mod.reel_caption(dict(d, date=prev)),
           "카드 릴스 캡션의 '구독하면 받는 것' 줄이 시작일부터만 붙지 않는다")
    expect(f"({active_gift(start)['count']}가지)" in letter and gift["title"] in letter, f"릴스 줄에 선물 이름·남은 가짓수가 없다: {letter}")
    expect(gift_mod.screen_line(prev) == "숫자·출처 전문은 프로필 링크 뉴스레터에서" and data.get("short", data["title"]) in gift_mod.screen_line(start)
           and not re.search(r"\d", gift_mod.screen_line(start) + gift_mod.screen_line(start, short=True)),
           "끝 장 문구가 시작일 전엔 그대로, 뒤엔 숫자 없이 선물 이름이어야 한다")
    sys.path.insert(0, str(AUTOMATION / "pilots" / "ai_reel"))
    import qa
    with tempfile.TemporaryDirectory() as tmp:
        cap = Path(tmp) / "comic_caption.txt"
        cap.write_text(f"오늘 소식\n이 그림은 AI로 만들었어요.\n{letter}\n#EDITH\n", encoding="utf-8")
        body = qa.caption_texts(cap, skip=qa.promo_lines(start))[0][0][1]
        expect(letter not in body and qa.promo_lines(prev) == [], "qa 가 '구독하면 받는 것' 줄을 숫자 대조에서 빼지 않는다(시작일 전엔 빼지 않는다)")
        cap.write_text(f"이 그림은 AI로 만들었어요.\n{letter.replace('가지)', '가지 넘게)')}\n", encoding="utf-8")
        expect("넘게" in qa.caption_texts(cap, skip=qa.promo_lines(start))[0][0][1], "손으로 바꾼 선물 줄까지 숫자 대조에서 뺀다")
    # 2026-11-09~ 그 줄은 캡션 둘째 줄(첫 줄 바로 다음) — 릴스 탭·피드는 캡션 첫 1~2줄만 보인다(11/08 주간 루틴)
    top = site_mod.LETTER_TOP_FROM
    before_top = (dt.date.fromisoformat(top) - dt.timedelta(days=1)).isoformat()
    new_lines = site_mod.reel_caption(dict(d, date=top)).splitlines()
    old_lines = site_mod.reel_caption(dict(d, date=before_top)).splitlines()
    expect(new_lines[1] == site_mod.reel_letter(top) and new_lines.count(site_mod.reel_letter(top)) == 1 and new_lines[2] == "",
           "카드 릴스 캡션의 '구독하면 받는 것' 줄이 LETTER_TOP_FROM 부터 둘째 줄(첫 줄 바로 다음)에 한 번만 오지 않는다")
    expect(before_top >= gift_mod.PROMO_FROM and old_lines[1] == "" and site_mod.reel_letter(before_top) in old_lines[2:],
           "LETTER_TOP_FROM 전 날짜 카드 릴스 캡션 순서가 바뀌었다(게시된 캡션을 다시 빌드해도 같아야 한다)")
    with tempfile.TemporaryDirectory() as tmp:
        cap = Path(tmp) / "reel_ai_caption.txt"
        top_letter = qa.promo_lines(top)[0]
        cap.write_text(f"오늘 소식 첫 줄\n{top_letter}\n\n① 소식\n이 영상은 AI로 만들었어요.\n#EDITH\n", encoding="utf-8")
        ok = qa.letter_top(cap, top)
        cap.write_text(f"오늘 소식 첫 줄\n\n① 소식\n{top_letter}\n이 영상은 AI로 만들었어요.\n#EDITH\n", encoding="utf-8")
        bad, old = qa.letter_top(cap, top), qa.letter_top(cap, before_top)
        expect(ok == [] and len(bad) == 1 and "둘째 줄" in bad[0] and old == [],
               "qa 가 AI 릴스·웹툰 캡션의 '구독하면 받는 것' 줄 자리(LETTER_TOP_FROM~ 둘째 줄)를 보지 않는다(전 날짜는 보지 않는다)")
    return (f"{gift['title']} {gift['count']}가지 · {gift_mod.LIVE_FROM}~ 남은 것 {active_gift(gift_mod.LIVE_FROM)['count']}가지 · "
            f"릴스·웹툰 구독 한 줄({top}~ 둘째 줄)")


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
    # AI 생성 사진(2026-11-01~ 힉스필드 — 10/31 회고 '대체 사진이 바닥'): 표지 출처 칸에 'AI 생성'을 밝히고, 3:4 표지도 흐리지 않게 채우고,
    # 주제어 점수가 같으면 실사 사진이 먼저다
    from edith.common import CARD_H_34, cover_photo_problem
    ai = [c for c in every if c["ai"]]
    expect(ai and all("AI 생성" in c["credit"] for c in ai), "AI 생성 사진의 출처 칸에 'AI 생성' 표기가 없다")
    blurry = [why for c in ai if (why := cover_photo_problem(c["photo"], CARD_H_34))]
    expect(not blurry, f"AI 생성 사진이 3:4 표지를 채우기에 작다: {blurry[:1]}")
    for words in ("", "저축 동전", "출근 직장인", "카드 결제"):
        cands = fetch_photo.library("2999-01-01", words)
        late = [(a["photo"], b["photo"]) for a, b in zip(cands, cands[1:]) if a["score"] == b["score"] and a["ai"] and not b["ai"]]
        expect(not late, f"'{words}': 점수가 같은데 AI 사진이 실사보다 먼저다 — {late[:1]}")
    # 주제어가 하나도 안 맞으면 중립 사진(도시·출근길)이 맨 위 — 핵심어 표지 대신 쓰는 마지막 대안(2026-10-25)
    blank = fetch_photo.library("2999-01-01", "주말 날씨 추위")
    expect(blank and blank[0]["neutral"] and not blank[0]["score"], f"맞는 주제어가 없을 때 중립 사진이 먼저가 아니다: {blank[:1]}")
    expect([c["photo"] for c in fetch_photo.library("2999-01-01", "버스 파업 출근")][:1] == ["assets/photos/lib-light-trails.jpg"],
           "'버스 파업' 이 교통 사진을 고르지 않는다")
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
            later = fetch_photo.library("2026-11-20", "돈")   # 마지막 사용(10/15)에서 RECENT_DAYS(30일)가 지난 뒤
            expect(later and later[0]["credit"] == "출처 원본", "예비 호가 쓴 사진의 출처가 일반 호의 것이 아니다")
            # 9/28 호를 10/12 에 늦게 낼 때 — 사흘 전(10/10) 예비 호 표지를 센다
            with contextlib.redirect_stdout(io.StringIO()):
                expect(not build_rewind.cover_photo("2026-09-28", ["돈"], "2026-10-12"), "지난 날짜 예비 호가 최근 쓴 표지를 또 고른다")
                expect(build_rewind.cover_photo("2026-09-28", ["돈"], "2026-11-20"), "지난 날짜 예비 호가 쓸 수 있는 표지를 못 고른다")
            # 2026-10-22 운영자 '이미지도 중복되는 거 아니야?' — 30일 안에 쓴 사진은 다시 고르지 않는다(3일 → 30일)
            expect(not fetch_photo.library("2026-11-10", "돈"), "30일 안(10/15 → 11/10)에 쓴 표지를 다시 고른다")
            expect(fetch_photo.last_used("assets/photos/x.jpg", "2026-11-10") == "2026-10-15", "표지 마지막 사용 날짜를 잘못 읽는다")
        finally:
            fetch_photo.ROOT, fetch_photo.LIBRARY = saved_root, saved_lib
    recent = {c["photo"] for c in fetch_photo.library("2026-10-09")}
    expect(not recent & {"assets/photos/2026-10-08.jpg", "assets/photos/2026-10-06.jpg"}, "사흘 안에 쓴 사진이 대체 후보에 나온다")
    # 10/19 '예금' 호 — 하나뿐인 돈 사진(10/3 동전)을 10/18 에 써서 핵심어 표지로 나갔다. 미리 검수한 아직 안 쓴 돈 사진이 이제 1순위
    top = fetch_photo.library("2026-10-19", "4% 예금 1000만원 이자")[0]
    expect(top["score"] > 0 and top["last"] is None and top["credit"] and top["photo_source"],
           f"10/19 '예금' 에 미리 검수한 돈 사진(출처 포함)이 1순위가 아니다: {top['photo']}")
    with tempfile.TemporaryDirectory() as tmp:   # 안 쓴 사진은 목록에 출처가 있을 때만, 같은 점수면 쓴 사진보다 먼저
        root = Path(tmp)
        (root / "content").mkdir()
        (root / "assets" / "photos").mkdir(parents=True)
        for f in ("old.jpg", "new.jpg", "nocredit.jpg", "nosource.jpg", "rew.jpg"):
            (root / "assets" / "photos" / f).write_bytes(b"")
        vet = {"credit": "사진 = A / Wikimedia Commons (CC0)", "photo_source": "https://x"}
        (root / "assets" / "photos" / "library.json").write_text(json.dumps({
            "assets/photos/old.jpg": {"subject": "동전", "tags": ["돈"]},
            "assets/photos/new.jpg": {"subject": "저금통", "tags": ["돈"], **vet},
            "assets/photos/nocredit.jpg": {"subject": "지갑", "tags": ["돈"]},
            "assets/photos/nosource.jpg": {"subject": "통장", "tags": ["돈"], "credit": "사진 = B / Wikimedia Commons (CC0)"},
            "assets/photos/rew.jpg": {"subject": "계산기", "tags": ["이자"], **vet, "focus": "center 40%"}}), encoding="utf-8")
        (root / "content" / "2026-10-01.json").write_text(json.dumps({"cards": {"cover": {"photo": "assets/photos/old.jpg", "credit": "출처"}}}), encoding="utf-8")
        # 미리 검수한 사진을 예비 호가 먼저 쓴 경우 — 출처는 목록에서, '최근 사용'은 그 예비 호로 센다
        (root / "content" / "2026-10-10.json").write_text(json.dumps({"rewind": True, "cards": {"cover": {"photo": "assets/photos/rew.jpg"}}}), encoding="utf-8")
        fetch_photo.ROOT, fetch_photo.LIBRARY = root, root / "assets" / "photos" / "library.json"
        try:
            got = [c["photo"] for c in fetch_photo.library("2026-11-20", "돈")]
            expect(got[:2] == ["assets/photos/new.jpg", "assets/photos/old.jpg"] and "assets/photos/nocredit.jpg" not in got
                   and "assets/photos/nosource.jpg" not in got, f"미리 검수한 사진 순서·출처(주소) 없는 사진 제외가 틀렸다: {got}")
            rew = [c for c in fetch_photo.library("2026-11-20", "이자") if c["photo"].endswith("rew.jpg")]
            expect(rew and rew[0]["credit"] == vet["credit"] and rew[0]["focus"] == "center 40%" and rew[0]["last"] == "2026-10-10",
                   f"예비 호가 먼저 쓴 미리 검수 사진이 출처를 잃는다: {rew}")
            expect(not [c for c in fetch_photo.library("2026-10-11", "이자") if c["photo"].endswith("rew.jpg")], "어제 예비 호가 쓴 미리 검수 사진이 다시 후보에 나온다")
            with contextlib.redirect_stdout(io.StringIO()) as out:
                fetch_photo.cmd_library("돈", use=1, day="2026-10-20")
            expect('"photo_source": "https://x"' in out.getvalue(), "미리 검수한 사진의 cards.cover 조각에 photo_source 가 없다")
        finally:
            fetch_photo.ROOT, fetch_photo.LIBRARY = saved_root, saved_lib
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
    # 2026-10-22 운영자: 메일에서 '부캉이' 의 따옴표가 '&#-27;' 로 보였다(메일 보안 필터가 '&#x' 를 바꾼다) — 메일 HTML 엔 16진수 문자 참조가 없어야 한다
    html_part = msg.get_body(preferencelist=("html",)).get_content()
    expect("&#x" not in html_part.lower(), "메일 HTML 에 16진수 문자 참조(&#x27; 등)가 남았다")
    sample = send_newsletter.plain_refs('<p title="a&#x27;b" class="c">흑상어 &#x27;부캉이&#x27;, 1&lt;2 &amp; &#34;인용&#34; &#39;끝&#39;</p>')
    expect(sample == '<p title="a&#39;b" class="c">흑상어 \'부캉이\', 1&lt;2 &amp; &#34;인용&#34; \'끝\'</p>', f"plain_refs 결과가 틀렸다: {sample}")
    import sync_subscribers
    welcome = sync_subscribers.welcome_message("b@example.com", "a@example.com", cfg)
    expect("&#x" not in welcome.get_body(preferencelist=("html",)).get_content().lower(), "환영 메일 HTML 에 16진수 문자 참조가 남았다")
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
    d["date"] = min(d["date"], site_mod.SHARE_UNTIL)   # 보내기 한 줄은 E6 기간(~10/20) 호에만 — 최근 호가 그 뒤여도 기간 안 날짜로 본다
    cap, reel = site_mod.instagram_caption(d, load_config()["site_url"]), site_mod.reel_caption(d)
    expect("프리랜서 친구" in cap and "프리랜서 친구" in reel, "보내기 한 줄이 캡션·릴스 캡션에 없다")
    expect(len(re.findall(r"(?<!\S)#\S+", reel)) <= 5 and reel.rstrip().splitlines()[-1].startswith("#"), "릴스 캡션 끝이 해시태그 줄이 아니다")
    # E6 판정(2026-10-20, 정규 8호 공유 0 — 되돌림): 10/21 호부터는 share_to 가 있어도 한 줄을 붙이지 않고 점검도 하지 않는다
    late = {**d, "date": "2026-10-21"}
    expect("프리랜서 친구" not in site_mod.instagram_caption(late, load_config()["site_url"]) and "프리랜서 친구" not in site_mod.reel_caption(late),
           "E6 를 끈 뒤(10/21~)에도 보내기 한 줄이 붙는다")
    for who, date, warn in (("", "2026-10-10", True), ("친구", "2026-10-10", True), ("프리랜서 친구", "2026-10-10", False), ("", "2026-10-09", False),
                            ("", "2026-10-21", False)):
        got = bool(style.share_check({"date": date, "instagram": {"share_to": who}}))
        expect(got == warn, f"share_to '{who}'({date}) 점검이 {'경고 안 함' if warn else '잘못 경고'}")
    cfg = {"reel_feed_from": "2026-10-13"}
    expect([post_instagram.reel_to_feed(cfg, k) for k in ("2026-10-12", "2026-10-13", "2026-10-16-weekly")] == [False, True, True],
           "릴스 피드 공유 시작 날짜가 틀린다")
    expect(post_instagram.reel_to_feed({"reel_share_to_feed": True}, "2026-10-01") and not post_instagram.reel_to_feed({}, "2026-12-01"),
           "reel_share_to_feed 설정을 안 따른다")
    cfg = {"reel_feed_from": "2026-10-13", "reel_feed_until": "2026-10-16"}   # E7 은 10/16 릴스까지(10/17 끔)
    expect([post_instagram.reel_to_feed(cfg, k) for k in ("2026-10-16", "2026-10-16-weekly", "2026-10-17")] == [True, True, False],
           "reel_feed_until 뒤에도 릴스를 피드에 올린다")
    expect(not post_instagram.reel_to_feed(load_config()["instagram"], "2026-10-17"), "config 의 E7 끄기(10/17~)가 적용되지 않는다")

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


def t_goal_line():
    """북극성(2026-11-01 운영자 '구독자 1만 명'): 성과표 한눈에 목표 줄 — 지금 숫자·7일 변화·필요한 주간 성장률·지금 속도로 닿는 날."""
    import tempfile
    import collect_metrics as cm
    from edith import common
    goal = (common.load_config().get("goal") or {})
    expect(goal.get("subscribers") == 10000 and goal.get("by"), "config.goal(1만 명·목표일)이 없다")
    with tempfile.TemporaryDirectory() as tmp:
        m = Path(tmp)
        (m / "daily").mkdir()
        (m / "daily" / "2026-11-01.json").write_text(json.dumps(
            {"collected_at": "2026-11-01T21:30:00+09:00", "subscribers": {"sending": 100}, "instagram": {"followers": 200}}), encoding="utf-8")
        snap = {"collected_at": "2026-11-08T21:30:00+09:00", "subscribers": {"sending": 110}, "instagram": {"followers": 200}}
        saved = cm.METRICS, cm.load_config
        cm.METRICS = m
        cm.load_config = lambda: {"goal": {"subscribers": 10000, "by": "2027-11-08"}}
        try:
            lines = cm._goal_lines(snap)
        finally:
            cm.METRICS, cm.load_config = saved
        # 수집이 빠져 2주 전 것만 있으면 비교하지 않는다(2주 증가를 한 주로 셈하지 않게 — 11/01 Codex)
        cm.METRICS = m
        cm.load_config = lambda: {"goal": {"subscribers": 10000, "by": "2027-11-08"}}
        try:
            gap_lines = cm._goal_lines({**snap, "collected_at": "2026-11-15T21:30:00+09:00"})
        finally:
            cm.METRICS, cm.load_config = saved
    expect("7일 전 자료 없음" in "\n".join(gap_lines) and "+10" not in "\n".join(gap_lines), f"2주 전 자료로 7일 변화를 셈했다: {gap_lines}")
    text = "\n".join(lines)
    expect("뉴스레터 **110**(7일 +10)" in text and "인스타 **200**(7일 +0)" in text, f"목표 줄 숫자가 틀린다: {text}")
    expect("뉴스레터 9.0%" in text and "인스타 닿지 않음" in text and "뉴스레터 2027-" in text, f"필요 성장률·닿는 날이 틀린다: {text}")
    return lines[0][:60]


def t_mascot_cards():
    """캐러셀이 글자만으로 나가지 않는다(2026-11-01 운영자 '문구만 만들지 마 — 이미지나 캐릭터 이미지로'): MASCOT_CARDS_FROM 부터
    사진 없는 표지는 마스코트 H + 핵심어 말풍선, 이슈 카드마다 H 가 '그래서 뭐가 달라져?'를 묻는다. 사진 표지는 사진 그대로, 지난 호는 그대로."""
    from edith import cards, content
    sig = 'alt="" style="display:block;width:'
    d = content.load("2026-10-31")   # 사진 없는 표지(급락)
    expect(not d["cards"]["cover"].get("photo"), "시험 원고(10/31)에 표지 사진이 생겼다 — 사진 없는 호로 바꾸기")
    n_issue = len(d["card_issues"])
    page_old, _ = cards.build(d, "")
    expect(sig not in page_old, "지난 호(10/31) 카드에 마스코트가 들어간다 — 기록이 바뀐다")
    page, files = cards.build({**d, "date": cards.MASCOT_CARDS_FROM}, "")
    cover = page.split('<section class="card"')[1]
    expect(sig in cover and d["cards"]["cover"]["keyword"] in cover, "사진 없는 표지에 마스코트·핵심어 말풍선이 없다")
    expect(page.count(sig) == 1 + n_issue, f"이슈 카드마다 H 가 없다({page.count(sig) - 1}/{n_issue})")
    d2 = content.load("2026-10-30")   # 사진 표지
    page2, _ = cards.build({**d2, "date": cards.MASCOT_CARDS_FROM}, "")
    cover2 = page2.split('<section class="card"')[1]
    expect("background:url(" in cover2 and sig not in cover2, "사진 표지가 마스코트 표지로 바뀌었다(사진이 먼저)")
    expect(cards.mascot_pose("코스피 3.48% 급락") == "surprised" and cards.mascot_pose("청년 지원금 환급 돌파") == "celebrate"
           and cards.mascot_pose("내일부터 신청 접수") == "calendar" and cards.mascot_pose("AI 검색") == "thinking", "H 자세 고르기가 틀린다")
    expect(all((cards.MASCOT_DIR / f"h-{x}.png").exists() for x in ("point", "surprised", "celebrate", "calendar", "thinking", "hello")),
           "마스코트 자세 그림이 없다")
    return f"{cards.MASCOT_CARDS_FROM}~ 사진 없는 표지 H·이슈 카드 {n_issue}장 H · 사진 표지·지난 호 그대로"


def t_card_ratio():
    """3:4 카드(2026-10-30 템플릿 ver.3 검토): 날짜로 1350/1440 을 나누고, 표지 사진·카드 CSS·스토리 카드 화면·갤러리가 그 크기를 따른다.
    API 가 3:4 를 받는지 확인하는 probe-ratio 는 게시(media_publish)를 부르지 않는다. 팔로우 카드는 follow_card_from 부터."""
    import post_instagram
    from edith import cards, common, content, site, story_frames
    real = common.load_config
    cfg = real()
    ig = cfg.get("instagram") or {}
    expect(ig.get("card_ratio_from") is None or str(ig["card_ratio_from"]) >= "2026-11-07",
           "card_ratio_from 이 11/07 전이다 — 지난 호 카드 크기가 바뀌거나 팔로우 카드(E11, 10/31~11/06) 표본과 겹친다(Codex 검토)")
    fake = lambda: {**cfg, "instagram": {**ig, "card_ratio_from": "2026-11-01", "follow_card_from": "2026-10-31"}}  # noqa: E731
    common.load_config = cards.load_config = fake
    try:
        expect([common.card_height(x) for x in ("2026-10-31", "2026-11-01", "2026-11-06-weekly")] == [1350, 1440, 1440],
               "카드 높이 날짜 나눔이 틀린다")
        expect(cards.height_css("2026-10-31") == "" and cards.height_css("2026-11-01") == ".card{height:1440px;}", "카드 CSS 높이가 틀린다")
        d = content.load("2026-10-29")
        d_new = {**d, "date": "2026-11-01"}
        page, _ = cards.build(d_new, "")
        expect(".card{height:1440px;}" in page and "팔로우하고 내일 아침에 받기" in page and "2030 직장인의 돈·일·소비 뉴스" in page,
               "3:4 날 카드에 1440 높이·팔로우 카드가 없다")
        page_old, _ = cards.build(d, "")
        expect(".card{height:1440px;}" not in page_old and "팔로우하고 내일 아침에 받기" not in page_old, "지난 호 카드가 바뀐다")
        page_v2, _ = cards.build({**d, "date": cards.FOLLOW_LINE_V2_FROM}, "")
        expect("2030이 알아야 할 소식" in page_v2 and "돈·일·소비 뉴스" not in page_v2,
               "E11 표본 다음 날부터 팔로우 카드 소개 줄이 새 문구(2030 폭넓게)가 아니다")
        expect(cards.follow_on({"date": "2026-10-31"}) and not cards.follow_on({"date": "2026-10-31", "poll": {"q": 1}}),
               "팔로우 카드 날짜·투표 날 예외가 틀린다")
        html_page = site.gallery_page(d_new, "https://x", ["01.png"], "caption")
        expect("1080×1440" in html_page, "갤러리가 3:4 크기를 안 적는다")
        page, files = story_frames.build_cards(Path("/x/ig"), ["01_a_cover.jpg", "02_a_pick.jpg", "04_a_summary.jpg"], True, "", 1440)
        expect("height:1333px" in page and "top:1593px" in page, "스토리 카드 화면이 3:4 카드 크기를 안 따른다")
    finally:
        common.load_config = cards.load_config = real
    expect(common.cover_photo_problem("assets/probe/ratio-3x4.jpg", 1440) is None
           and common.cover_photo_problem("assets/probe/ratio-3x4.jpg", 1600) is not None, "표지 사진 크기 검사가 카드 높이를 안 따른다")
    calls = []

    class FakeGraph:
        def call(self, method, path, **params):
            calls.append((path, params))
            return {"id": f"c{len(calls)}"}

        def wait_ready(self, *a, **k):
            pass

    saved = post_instagram.wait_public
    post_instagram.wait_public = lambda urls, **k: None
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            ok = post_instagram.probe_ratio(FakeGraph(), "u", "https://x")
    finally:
        post_instagram.wait_public = saved
    expect(ok and not any(path.endswith("media_publish") for path, _ in calls), "3:4 확인이 게시를 부른다")
    expect([p.get("is_carousel_item") for path, p in calls[:2]] == ["true", "true"] and calls[2][1].get("media_type") == "CAROUSEL"
           and calls[0][1]["image_url"].endswith(post_instagram.PROBE_IMAGE), "3:4 확인이 캐러셀 장 2개 + 캐러셀 컨테이너를 만들지 않는다")
    expect(common.image_size(ROOT / post_instagram.PROBE_IMAGE) == (1080, 1440), "시험 그림이 1080×1440 이 아니다")
    return "1350/1440 날짜 나눔·카드·표지 사진·스토리·갤러리·팔로우 카드·게시 없는 3:4 확인"


def t_story():
    """E9 아침 스토리(2026-10-10~): 날짜·데일리만, 세로 훅 화면(없으면 표지), STORIES 로 올림, 24시간 뒤엔 지난 스냅숏 값.
    2026-10-29~: 훅 뒤에 카드 화면(story/)을 잇고, 중간에 실패하면 다음 실행이 이어서 올린다."""
    import collect_metrics
    import post_instagram
    from edith import story_frames
    cfg = {"story_from": "2026-10-10"}
    expect([post_instagram.story_on(cfg, k) for k in ("2026-10-09", "2026-10-10", "2026-10-16-weekly")] == [False, True, False],
           "스토리 시작 날짜·주간 특집 제외가 틀린다")
    expect(post_instagram.story_on(cfg, "2026-10-10", "BUSINESS") and not post_instagram.story_on(cfg, "2026-10-10", "MEDIA_CREATOR"),
           "크리에이터 계정에서도 스토리를 시도한다(API 스토리는 비즈니스 계정만)")
    # '스토리는 릴스만'(2026-11-02 운영자) — 시작 날짜부터 데일리만, 아침 카드 스토리는 건너뛰고 AI 릴스가 없는 날은 릴스 실행이 대신 올린다
    ro = {"story_reel_only_from": "2026-11-03"}
    expect([post_instagram.story_reel_only(ro, k) for k in ("2026-11-02", "2026-11-03", "2026-11-06-weekly")] == [False, True, False]
           and not post_instagram.story_reel_only({}, "2026-11-03"), "스토리 릴스만 날짜·주간 특집 제외가 틀린다")
    real_cfg = json.loads((ROOT / "automation" / "config.json").read_text(encoding="utf-8"))["instagram"]
    expect(real_cfg.get("story_reel_only_from") == "2026-11-03", "config 에 story_reel_only_from 이 없다")
    # 11월 크레딧 계획의 홀수 날(AI 영상을 안 만드는 날)은 '릴스만'을 적용하지 않고 아침 카드 스토리를 올린다(11/05·11/07 회고, 11/08~)
    ev = {"story_reel_only_from": "2026-11-03", "ai_video_even_days": {"from": "2026-11-05", "until": "2026-11-30"}}
    expect([post_instagram.story_reel_only(ev, k) for k in ("2026-11-03", "2026-11-08", "2026-11-09", "2026-11-30", "2026-12-01")]
           == [True, True, False, True, True], "영상 없는 홀수 날에도 아침 카드 스토리를 건너뛴다(또는 계획 밖 날을 잘못 뺀다)")
    expect(real_cfg.get("ai_video_even_days") == {"from": "2026-11-05", "until": "2026-11-30"}, "config 에 ai_video_even_days(11월 짝수 날 계획)가 없다")
    import inspect as _inspect
    pi_src = _inspect.getsource(post_instagram.main)
    expect("and not reel_only" in pi_src and "not ai.exists()" in pi_src and "card_story()" in pi_src,
           "아침 카드 스토리를 릴스만 날에 건너뛰지 않거나, AI 릴스가 없는 날의 대신 올리기가 없다")
    # E21 판정(11/09 되돌림): story_cards_after_ai_from 부터 AI 영상 스토리 바로 뒤에 아침 카드 스토리(순서 릴스 → 카드 — 11/03 운영자)
    ca = {"story_cards_after_ai_from": "2026-11-10"}
    expect([post_instagram.cards_after_ai(ca, k) for k in ("2026-11-08", "2026-11-10", "2026-11-13-weekly")] == [False, True, False]
           and not post_instagram.cards_after_ai({}, "2026-11-10"), "AI 영상 스토리 뒤 카드 스토리 날짜·주간 특집 제외가 틀린다")
    expect(real_cfg.get("story_cards_after_ai_from") == "2026-11-10", "config 에 story_cards_after_ai_from(E21 되돌림)이 없다")
    after = pi_src.find("story_on(cfg, key) and cards_after_ai(cfg, key)")   # 이어 올리는 조건 줄(안내 문구가 아니라)
    expect(pi_src.find('log["story_ai"] = {') < after < pi_src.find("AI 릴스가 없는 날 — 아침 카드 스토리를 대신"),
           "카드 스토리 이어 올리기가 AI 영상 스토리 게시 뒤(릴스 → 카드 순서)에 있지 않다")
    expect(collect_metrics._story_cell({"story": {"reach": 20, "video": True}}) == " (스토리 영상 20)", "AI 영상 스토리 도달 표시가 틀린다")
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
            expect(post_instagram.post_story(FakeGraph(), "u", "k", folder, "https://x", False) == ["s1"], "스토리를 게시하지 않는다")
            media = [p for path, p in calls if path == "u/media"]
            expect(media and media[0].get("media_type") == "STORIES" and media[0]["image_url"].endswith("r1_hook.jpg"), "STORIES 컨테이너가 아니다")
            # 카드 화면(story/)이 있으면 훅 뒤에 잇는다 — 훅이 없는 호(예비 호)는 표지 카드 화면부터
            (folder / "story").mkdir()
            for name in ("s1_pick.jpg", "s2_summary.jpg"):
                (folder / "story" / name).write_bytes(b"")
            urls = post_instagram.story_images(folder, "k", "https://x")
            expect([u.rsplit("/", 2)[-2] + "/" + u.rsplit("/", 1)[-1] for u in urls]
                   == ["reel_frames/r1_hook.jpg", "story/s1_pick.jpg", "story/s2_summary.jpg"], f"스토리 순서가 틀린다: {urls}")
            calls.clear()
            expect(post_instagram.post_story(FakeGraph(), "u", "k", folder, "https://x", False) == ["s1"] * 3, "스토리 3장을 다 올리지 않는다")
            expect([p["image_url"].rsplit("/", 1)[-1] for path, p in calls if path == "u/media"]
                   == ["r1_hook.jpg", "s1_pick.jpg", "s2_summary.jpg"], "스토리를 순서대로 올리지 않는다")

            class Flaky(FakeGraph):   # 두 번째 장 게시에서 실패 → 첫 장 id 를 남기고, 다음 실행은 두 번째 장부터
                n = 0

                def call(self, method, path, **params):
                    if path == "u/media_publish":
                        Flaky.n += 1
                        if Flaky.n == 2:
                            raise post_instagram.IGError("500 (code 2): temporary")
                    return super().call(method, path, **params)
            try:
                post_instagram.post_story(Flaky(), "u", "k", folder, "https://x", False)
                expect(False, "스토리 게시 실패가 올라오지 않는다")
            except post_instagram.IGError as e:
                expect(getattr(e, "posted", None) == ["s1"], f"실패 전까지 올린 스토리를 남기지 않는다: {getattr(e, 'posted', None)}")
            calls.clear()
            expect(post_instagram.post_story(FakeGraph(), "u", "k", folder, "https://x", False, done=["s1"]) == ["s1"] * 3,
                   "이어 올리기가 id 목록을 잇지 않는다")
            expect([p["image_url"].rsplit("/", 1)[-1] for path, p in calls if path == "u/media"] == ["s1_pick.jpg", "s2_summary.jpg"],
                   "이어 올리기가 이미 올린 장을 다시 올린다")
            expect(post_instagram.post_story(FakeGraph(), "u", "k", folder, "https://x", True) == [], "dry-run 이 게시 기록을 남긴다")
            for f in (folder / "story").glob("*.jpg"):
                f.unlink()
            (folder / "story" / "s1_cover.jpg").write_bytes(b"")
            expect([u.rsplit("/", 1)[-1] for u in post_instagram.story_images(folder, "k", "https://x")] == ["s1_cover.jpg"],
                   "표지 화면으로 시작하는 스토리에 훅 화면을 또 붙인다")
            (folder / "story" / "s1_cover.jpg").unlink()
            (folder / "story" / "s1_hook.jpg").write_bytes(b"")
            expect([u.rsplit("/", 1)[-1] for u in post_instagram.story_images(folder, "k", "https://x")] == ["s1_hook.jpg"],
                   "훅 화면으로 시작하는 브리핑에 세로 릴스 훅을 또 붙인다")
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
    cards_ = [f"{i:02d}_edit_h_2026-10-30_{r}.jpg" for i, r in enumerate(("cover", "summary", "pick", "deep", "issue2", "cta"), 1)]
    expect(story_frames.choose(cards_, hook=True) == [cards_[2], cards_[1]], "훅 다음 카드가 H PICK → 한눈에 순서가 아니다")
    expect(story_frames.choose(cards_, hook=False)[0] == cards_[0], "훅이 없는 호가 표지부터 시작하지 않는다")
    expect(story_frames.choose([cards_[0], cards_[5]], hook=True) == [], "고를 카드가 없는데 화면을 만든다")
    page, files = story_frames.build_cards(Path("/nonexistent/ig"), cards_, True, "")
    expect(files == ["s1_pick.png", "s2_summary.png"] and page.count('class="card story"') == 2
           and page.count('class="cta"') == 1 and f"카드 {len(cards_)}장" in page, "카드 스토리 화면 HTML(장 수·마지막 장 안내)이 틀린다")
    # 브리핑(2026-10-29 ②~): H PICK 요점 → 소식 2개씩, 장마다 관련 기사, 마지막 장에만 뉴스레터 안내. 훅이 없으면 훅 화면부터
    from edith import content
    d = content.load("2026-10-29")
    page, files = story_frames.build_briefing(d, True, "")
    expect(files == ["s1_pick.png", "s2_news1.png", "s3_news2.png"], f"브리핑 장 구성이 틀린다: {files}")
    expect(page.count("관련 기사·원문 · ") == 5 and page.count("원문 링크·한 줄 뉴스는 뉴스레터에") == 1
           and all(x in page for x in ("배당소득세 15.4%", "세후 금액부터 계산해 보세요", "오늘의 소식", "/ 05")),
           "브리핑에 요점·할 일·관련 기사·마지막 장 안내가 빠졌다")
    expect(story_frames.build_briefing(d, False, "")[1][0] == "s1_hook.png", "훅이 없는 호의 브리핑이 훅 화면으로 시작하지 않는다")
    expect(story_frames.build_briefing({**d, "format": 1}, True, "") == ("", []), "형식 1 호에 브리핑을 만든다(카드 화면으로 가야 한다)")
    # 여러 장 스토리의 장별 도달 → 성과표 '(스토리 첫 장→끝 장)'
    class Reach:
        def call(self, method, path, **params):
            return {"data": [{"name": "reach", "values": [{"value": {"a": 30, "b": 24, "c": 19}[path.split("/")[0]]}]}]}
    got = collect_metrics._story_row(Reach(), "2026-10-30", {"story": {"id": "a", "ids": ["a", "b", "c"]}})
    expect(got.get("frames") == [30, 24, 19] and collect_metrics._story_cell({"story": got}) == " (스토리 30→19)",
           f"스토리 장별 도달이 안 잡힌다: {got}")
    return "날짜·훅+브리핑·카드 화면·순서·이어 올리기·장별 도달·24시간 뒤 값"


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
    # 자정 뒤 언제 시작한 사슬이든 17:30 에 본 작업이 시작되고, 본 작업(6시간 제한)이 21:30 수집까지 덮어야 한다.
    # 11/01: 04:26 에 다른 html 푸시(PR #101)로 시작한 사슬이 대기 둘(350분씩)로는 16:07 에 본 작업을 시작해
    # 21:07 에 5시간 제한으로 끊길 뻔했다(21:30 수집 빠짐 + '실패' 알림 메일).
    ev = (ROOT / ".github" / "workflows" / "evening.yml").read_text(encoding="utf-8")
    waits = re.findall(r"\n  (wait\d+):\n    needs: \[?([\w, ]+)\]?\n(?:.*\n)*?.*evening\.py sleep [^\n]*--max-min (\d+)", ev)
    anchor = sum(int(x) * f for x, f in zip(evening.ANCHOR.split(":"), (60, 1)))
    metrics = sum(int(x) * f for x, f in zip(evening.METRICS_AT.split(":"), (60, 1)))
    expect(sum(int(w[2]) for w in waits) >= anchor,
           f"대기 작업 합계 {sum(int(w[2]) for w in waits)}분 — 자정 뒤 시작한 사슬이 {evening.ANCHOR} 전에 본 작업을 시작해 21:30 전에 끊긴다")
    for prev, cur in zip(waits, waits[1:]):
        expect(prev[0] in cur[1], f"{cur[0]} 가 {prev[0]} 뒤에 돌지 않는다")
    run_job = re.search(r"\n  run:\n    needs: \[([\w, ]+)\]\n(?:.*\n)*?    timeout-minutes: (\d+)", ev)
    expect(run_job and waits and waits[-1][0] in run_job.group(1), "본 작업(run)이 마지막 대기 작업 뒤에 돌지 않는다")
    expect(run_job and int(run_job.group(2)) >= metrics - anchor + 15, "본 작업 시간 제한이 17:30→21:30 수집을 덮지 못한다")
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
            proc = subprocess.run([sys.executable, str(sbx / "automation" / "build_issue.py"), day], capture_output=True, text=True, cwd=sbx,
                                  env={**os.environ, "EDITH_SKIP_ANJANG_WAIT": "1",   # 다시 빌드는 안장 기다리기 검사 밖(11/03)
                                       "EDITH_SKIP_SOURCE_CHECK": "1"})   # 숫자 2곳 대조도 — 발행 때 이미 봤고, 지난 호는 기록(11/04)
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


def t_weekly_save():
    """금요일 주간 특집 저장각(E13, 2026-11-06~ — 2026-10-31 경쟁 비교 '두고 쓰는 자료'): 날짜는 이미 낸 호 원고에 글자로 있는 것만,
    지난·먼 날짜·아직 안 낸 호·글자 수·개수는 막고, 시작일 전 특집과 날짜 2개 미만은 예전 '한 줄로' 장, 캡션 날짜 줄, 성과표 '주간 특집' 표."""
    from edith import cards, weekly
    import collect_metrics
    fri = parse_date("2026-10-30")
    good = [{"date": "2026-11-30", "what": "SK하이닉스 배당 기준일", "todo": "주당 2만원 — 전날까지 보유", "from": "2026-10-29"},
            {"date": "2026-11-20", "what": "열하루 뒤 일정", "todo": "달력에 적기", "from": "2026-10-28"}]
    rows = weekly.dates_rows({"dates": good}, fri)
    expect([r["day"] for r in rows] == [20, 30] and rows[0]["from"] == "10/28 호에서 확인" and rows[1]["weekday"] == "월",
           f"저장각 날짜 행(날짜 순·출처 호·요일): {rows}")
    expect(weekly.dates_rows({"dates": good[:1]}, fri) == [], "날짜가 1개면 '한 줄로' 장으로 돌아가야 한다")
    bad = {"원고에 없는 날짜": {**good[0], "date": "2026-11-17"}, "지난 날짜": {**good[0], "date": "2026-10-29"},
           "60일 넘는 날짜": {**good[0], "date": "2027-01-15"}, "아직 안 낸 호": {**good[0], "from": "2026-11-02"},
           "긴 what": {**good[0], "what": "가" * 23}, "빈 todo": {**good[0], "todo": ""}}
    for why, entry in bad.items():
        try:
            weekly.dates_rows({"dates": [entry, good[1]]}, fri)
            raise AssertionError(f"저장각 날짜 검사가 '{why}'를 통과시켰다")
        except weekly.WeeklyError:
            pass
    try:
        weekly.dates_rows({"dates": good * 3}, fri)
        raise AssertionError("저장각 날짜 6개를 통과시켰다(카드는 4개까지 — 5개면 넘친다)")
    except weekly.WeeklyError:
        pass
    expect(not weekly.save_card_on("2026-10-30") and weekly.save_card_on("2026-11-06"),
           "save_card_from 이 2026-11-06 이 아니다 — 지난 특집을 다시 빌드하면 08 장이 바뀐다")
    page = cards.calendar_card("10월 5주차 저장각", "달력에 적어 둘\n==다가올 날짜==", rows)
    expect("11월" in page and ">20<" in page and ">30<" in page and "10/29 호에서 확인" in page, "날짜 카드에 월·일·출처 호가 없다")
    with tempfile.TemporaryDirectory() as tmp:
        spec = json.loads((CONTENT_DIR / "weekly" / "2026-10-30.json").read_text(encoding="utf-8"))
        Path(tmp, "2026-10-30.json").write_text(json.dumps({**spec, "dates": good}, ensure_ascii=False), encoding="utf-8")
        saved = weekly.WEEKLY_DIR, weekly.load_config
        real = weekly.load_config
        try:
            weekly.WEEKLY_DIR = Path(tmp)
            weekly.load_config = lambda: {**real(), "weekly_special": {**real()["weekly_special"], "save_card_from": "2026-10-30"}}
            w = weekly.load("2026-10-30")
            cap = weekly.caption(w)
        finally:
            weekly.WEEKLY_DIR, weekly.load_config = saved
    expect(len(w["dates"]) == 2 and "달력에 적어 둘 날짜\n· 11/20(금) 열하루 뒤 일정\n· 11/30(월) SK하이닉스 배당 기준일" in cap
           and "날짜 장은 저장해 두면" in w["cards"]["cta"]["sub"], "저장각 특집의 캡션 날짜 줄·마무리 문구")
    snap = {"collected_at": "2026-11-07T21:30+09:00", "issues": {}, "instagram": {"weekly": {"2026-11-06": {"reach": 40, "saved": 3, "shares": 1}}}}
    table = "\n".join(collect_metrics.weekly_lines(snap))
    expect("## 주간 특집" in table and "| 2026-11-06 |" in table and "| 10% |" in table, f"성과표 주간 특집 표:\n{table}")
    return f"날짜 {len(rows)}개 · 막는 경우 {len(bad) + 1}가지"


def t_save_cards():
    """데일리 저장각(2026-11-14~ — 2026-10-31 경쟁 비교 후속): 노트 카드의 '오늘 챙길 것' 체크리스트, H PICK 심층 카드의 막대 차트.
    시작일 전 호·투표 결과 날은 그대로, 차트 원고 검사(점 3~6개·0 이상·출처), 시작일이 E12 표본(11/07~11/13) 뒤인지."""
    from edith import cards
    from edith import content as content_mod
    ig = load_config()["instagram"]
    for key in ("todo_card_from", "chart_card_from"):
        expect(ig.get(key) is None or str(ig[key]) >= "2026-11-14",
               f"{key} 가 11/14 전이다 — E11 팔로우 카드(10/31~11/06)·E12 3:4(11/07~11/13) 표본과 겹친다")
    day = daily_issues(1)[0]
    d = content_mod.load(day)
    d["todo"] = ["11월 3일 일정 달력에 적기", "내 계좌 비중 확인하기"]
    d["cards"]["deep"]["chart"] = {"title": "하루 낙폭, ==큰 날==", "unit": "%", "source": "가·나",
                                   "points": [{"label": "4/7", "value": 5.57}, {"label": "8/5", "value": 8.77}, {"label": "10/30", "value": 3.48}]}
    real = cards.load_config
    try:
        cards.load_config = lambda: {**real(), "instagram": {**real()["instagram"], "todo_card_from": "2999-01-01", "chart_card_from": "2999-01-01"}}
        before_note, before_deep = cards.note_card(d), cards.deep_card(d)
        cards.load_config = lambda: {**real(), "instagram": {**real()["instagram"], "todo_card_from": day, "chart_card_from": day}}
        note, deep = cards.note_card(d), cards.deep_card(d)
        poll_note = cards.note_card({**d, "poll_result": {"tally": {"votes": {"A": 1, "B": 0}, "pct": {"A": 100, "B": 0}, "total": 1,
                                                                     "options": ["가", "나"], "question": "질문"}}})
    finally:
        cards.load_config = real
    expect("오늘 챙길 것" not in before_note and "자료 ·" not in before_deep, "시작일 전 호에 체크리스트·차트가 들어갔다(지난 호가 바뀐다)")
    expect("오늘 챙길 것" in note and "일정 달력에 적기" in note and "내 계좌 비중 확인하기" in note, "노트 카드에 오늘 챙길 것이 없다")
    expect("오늘 챙길 것" not in poll_note, "투표 결과 날 노트 카드에 체크리스트가 들어갔다")
    expect("자료 · 가" in deep and "8.77%" in deep and "10/30" in deep, "심층 카드에 차트(숫자·칸 이름·자료 출처)가 없다")
    bad = {"점 2개": {"points": [{"label": "a", "value": 1}] * 2}, "음수": {"points": [{"label": "a", "value": -1}] * 3},
           "출처 없음": {"source": ""}, "긴 칸 이름": {"points": [{"label": "가나다라마바사", "value": 1}] * 3},
           "칸 번호 밖": {"highlight": 3}}
    for why, patch in bad.items():
        try:
            content_mod._chart({**d["cards"]["deep"]["chart"], **patch}, "시험")
            raise AssertionError(f"차트 검사가 '{why}'를 통과시켰다")
        except content_mod.ContentError:
            pass
    content_mod._chart(d["cards"]["deep"]["chart"], "시험")
    return f"체크리스트 {ig.get('todo_card_from')}~ · 차트 {ig.get('chart_card_from')}~ · 막는 차트 {len(bad)}가지"


def _dive_sample(steps=4, worst=False, day=None):
    """딥다이브 시험 원고 — 최근 데일리 원고를 연재 날(config.instagram.dive_card_from)로 옮기고 cards.dive 를 붙인다.
    worst=True 면 모든 칸을 글자 한도까지 채운다(카드가 넘치지 않는지 렌더링으로 본다)."""
    from edith import content as content_mod
    ig = load_config()["instagram"]
    day = day or str(ig.get("dive_card_from") or "2026-11-04")
    data = json.loads((CONTENT_DIR / f"{daily_issues(1)[0]}.json").read_text(encoding="utf-8"))
    data.update({"date": day, "series": {"name": "H의 장부"}, "briefs_short_reason": "자동 점검용 원고"})
    data.pop("vol", None)
    for ci in (data.get("cards") or {}).get("issues") or []:   # 지난 호 원고의 '63억$' 꼴은 11/04~ content 가 막는다 — 옮겨 쓸 때 새 규칙대로
        if isinstance(ci.get("number"), str):
            ci["number"] = re.sub(r"([만억조])\s*[$€¥]", r"\1 달러", ci["number"])
        if content_mod.takeaway_link_problem(ci):   # 11/03 ① '담보대출 금리' 꼴도 11/04~ 막힌다 — 옮겨 쓸 때 이어지는 말로
            ci["takeaway"] = "이 소식이 내 돈에 닿는 날부터 챙겨 두세요"
    lim = content_mod.CARD_LIMITS

    def fill(n, words="매출 이익 가격 점유율 회원 객단가 영업이익 이익률 커피 한 잔 남는 돈"):
        out = ""
        while len(out) < n:
            out += (" " if out else "") + words.split()[len(out) % len(words.split())]
        return out[:n].rstrip() if worst else out[: max(4, n // 2)].rstrip()

    box = {"title": fill(lim["dive_box_title"]), "text": fill(lim["dive_box_text"])}
    kinds = [
        {"table": {"head": ["회사", "2025년 매출", "영업이익", "이익률"][: 4 if worst else 3],
                   "rows": [["가나다라마", "1,234,567대", "12조3456억", "12.34%"][: 4 if worst else 3]] * (4 if worst else 2), "highlight": 0}},
        {"line": {"title": fill(22), "points": [{"label": f"{20 + i}년", "value": v, "text": f"{v:,}원"[:9]}
                                                for i, v in enumerate([136000, 98000, 120000, 70000, 52000, 41000, 39400][: 7 if worst else 4])]}},
        {"chart": {"title": fill(22), "unit": "%", "points": [{"label": f"{2020 + i}년", "value": 10 + i * 3} for i in range(6 if worst else 3)]}},
        {"points": [fill(lim["dive_point"])] * (3 if worst else 2), "label": "다른 업종 비유"[: lim["dive_label"]]},
        {"stat": {"value": "1조2345억원", "label": fill(lim["dive_stat_label"])}},
    ]
    poses = ["point", "thinking", "newspaper", "surprised", "celebrate"]
    data["cards"]["dive"] = {
        "by": "H가 숫자로 읽어 주는",
        "steps": [{**kinds[i % len(kinds)], "q": "얼마나 ==" + fill(lim["dive_q"] - 5) + "==?", "say": fill(lim["dive_say"]),
                   "source": f"자료{i + 1}·자료{i + 2}", "pose": poses[i % len(poses)], **({"box": box} if worst else {})}
                  for i in range(steps)],
        "verdict": {"text": fill(lim["dive_verdict"] // 2) + " — " + fill(lim["dive_verdict"] - lim["dive_verdict"] // 2 - 3)},
    }
    data["todo"] = [fill(lim["todo"])] * 3
    data["cards"]["issues"][0]["ask"] = "얼마나 팔렸나?"
    data["cards"]["deep"]["ask"] = "왜 잘 팔릴까?"
    return data


def t_dive_cards():
    """딥다이브 카드(2026-11-01 운영자 '딥다이브 카드 지금 바로' — 머니그라피 딥다이브 문법, E4 「H의 장부」 11/04~):
    연재 날에만, 표지 이름표 → H PICK → 질문 장 3~5 → H의 판정 → 5가지 한눈에 → 마무리(10장 안), 지난 호·다른 날은 그대로,
    원고 검사(그림 하나·출처·글자 수·질문 말풍선), 첫 댓글 출처, 스토리·카드 릴스가 고르는 장 이름."""
    import copy
    import make_reel
    from edith import cards, common, content as content_mod, site, story_frames
    ig = load_config()["instagram"]
    start = ig.get("dive_card_from")
    expect(start is None or str(start) >= "2026-11-04", "dive_card_from 이 11/04 전이다 — 지난 호 카드가 바뀐다(E4 첫 편이 11/04)")
    base = _dive_sample(4)
    d = content_mod.prepare(copy.deepcopy(base), base["date"])
    page, files = cards.build(d, "")
    names = [f.rsplit("_", 1)[-1][:-4] for f in files]
    expect(names == ["cover", "pick", "dive1", "dive2", "dive3", "dive4", "verdict", "summary", "cta"], f"딥다이브 날 카드 순서가 틀린다: {names}")
    expect(page.count('<section class="card"') == len(files), "카드 수와 파일 수가 다르다")
    for want in ("H가 숫자로 읽어 주는", "H의 판정", "다음 편 · 다음 주 수요일", "「H의 장부」 #2", "얼마나 팔렸나?", "최고 ", "자료 · 자료1", "밀어서 숫자로 읽기"):
        expect(want in page, f"딥다이브 카드에 '{want}' 가 없다")
    expect("Q1" in page and "Q3" in page and "다른 업종 비유" in page, "질문 장 머리표(Q1·비유)가 없다")
    five = content_mod.prepare(_dive_sample(5), base["date"])
    expect(len(cards.build(five, "")[1]) == 10, "질문 장 5개면 10장(인스타 캐러셀 한도)이어야 한다")
    # 장 이름 — 스토리 카드 화면은 pick·summary, 카드 릴스는 cover·pick·cta 를 그대로 고른다
    expect([story_frames.role(f) for f in story_frames.choose(files, True)] == ["pick", "summary"], "스토리 카드 화면이 딥다이브 날 장을 못 고른다")
    expect([make_reel.reel_cards([Path(f) for f in files])[i].stem.rsplit("_", 1)[-1] for i in range(3)] == ["cover", "pick", "cta"],
           "카드 릴스가 딥다이브 날 장을 못 고른다")
    comment = site.first_comment(d)
    expect("딥다이브 장 · 자료1·자료2" in comment.splitlines()[2], f"첫 댓글에 질문 장 출처가 없다: {comment[:120]}")
    # 시작일 전·연재 아닌 날·원고에 dive 가 없는 날은 예전 10장 그대로
    real = common.load_config
    try:
        common.load_config = lambda: {**real(), "instagram": {**real()["instagram"], "dive_card_from": "2999-01-01"}}
        off = cards.build(content_mod.prepare(copy.deepcopy(base), base["date"]), "")[1]
    finally:
        common.load_config = real
    expect([f.rsplit("_", 1)[-1][:-4] for f in off] == cards.CARD_NAMES_2B, "시작일 전인데 딥다이브 카드가 나간다")
    plain_day = copy.deepcopy(base)
    plain_day["cards"].pop("dive")
    expect([f.rsplit("_", 1)[-1][:-4] for f in cards.build(content_mod.prepare(plain_day, base["date"]), "")[1]] == cards.CARD_NAMES_2B,
           "원고에 dive 가 없는데 카드 순서가 바뀐다")
    no_series = copy.deepcopy(base)
    no_series.pop("series")
    bad = {"연재 아닌 날": no_series}

    def patched(fn):
        x = copy.deepcopy(base)
        fn(x["cards"]["dive"])
        return x

    bad.update({
        "질문 장 2개": patched(lambda v: v.update(steps=v["steps"][:2])),
        "질문 장 6개": patched(lambda v: v.update(steps=v["steps"] * 2)),
        "그림 둘": patched(lambda v: v["steps"][0].update(stat={"value": "1", "label": "가"})),
        "그림 없음": patched(lambda v: v["steps"][0].pop("table")),
        "표 칸 수": patched(lambda v: v["steps"][0]["table"]["rows"].append(["가"])),
        "표 칸 글자": patched(lambda v: v["steps"][0]["table"]["rows"][0].__setitem__(1, "가" * 11)),
        "선 점 하나": patched(lambda v: v["steps"][1]["line"].update(points=v["steps"][1]["line"]["points"][:1])),
        "선 값 글자": patched(lambda v: v["steps"][1]["line"]["points"][0].update(value="많음")),
        "막대 음수": patched(lambda v: v["steps"][2]["chart"]["points"][0].update(value=-1)),
        "출처 없음": patched(lambda v: v["steps"][3].pop("source")),
        "자세 이름": patched(lambda v: v["steps"][0].update(pose="dance")),
        "판정 없음": patched(lambda v: v.pop("verdict")),
        "질문 글자 수": patched(lambda v: v["steps"][0].update(q="가" * 30)),
        "판정 글자 수": patched(lambda v: v["verdict"].update(text="가 " * 40)),
    })
    no_q = copy.deepcopy(base)
    no_q["cards"]["deep"]["ask"] = "왜 중요해"
    bad["말풍선 물음표"] = no_q
    for why, x in bad.items():
        try:
            content_mod.prepare(x, base["date"])
            raise AssertionError(f"딥다이브 원고 검사가 '{why}'를 통과시켰다")
        except content_mod.ContentError:
            pass
    return f"{start}~ 연재 날 · 9~10장 · 막는 원고 {len(bad)}가지 · 지난 호·dive 없는 날 그대로"


def t_dive_render():
    """딥다이브 카드가 글자 한도를 꽉 채워도 넘치지 않는다 — 4:5(체크리스트 있음·없음)·3:4 를 실제로 렌더링(node·Playwright)."""
    import copy
    from edith import cards, common, content as content_mod
    from edith.fonts import font_css
    real = common.load_config
    cfg = real()
    combos = {"4:5": (None, None), "4:5 + 체크리스트": (None, "2026-11-04"), "3:4 + 체크리스트": ("2026-11-04", "2026-11-04")}
    out = []
    for name, (ratio, todo) in combos.items():
        fake = lambda: {**cfg, "instagram": {**cfg["instagram"], "card_ratio_from": ratio, "todo_card_from": todo,  # noqa: E731
                                              "dive_card_from": "2026-11-04"}}
        common.load_config = cards.load_config = fake
        try:
            data = _dive_sample(5, worst=True, day="2026-11-04")
            data["cards"]["cover"].pop("photo", None)   # 사진 크기 검사와 상관없이(3:4 는 1440px 사진이 필요) 마스코트 표지로
            d = content_mod.prepare(copy.deepcopy(data), "2026-11-04")
            page, files = cards.build(d, font_css())
        finally:
            common.load_config = real
            cards.load_config = real
        # 옆으로 넘치는 상자(.fitw)를 렌더러가 넘침으로 잡는지 — 일부러 넓은 한 장을 끝에 붙인다
        page = page.replace("</body>", '<section class="card"><div class="body"><div class="fitw" style="width:400px;margin-top:200px;">'
                                       '<div style="width:700px;height:20px;"></div></div></div></section></body>')
        files = [*files, "zz_wide.png"]
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "c.html").write_text(page, encoding="utf-8")
            proc = subprocess.run(["node", str(AUTOMATION / "render_cards.cjs"), str(Path(tmp) / "c.html"), tmp, *files],
                                  capture_output=True, text=True)
        expect(proc.returncode == 0, f"{name} 렌더링 실패: {proc.stderr[-300:]}")
        rep = json.loads(proc.stdout.strip().splitlines()[-1])["cards"]
        expect(rep[-1]["overflow"], "옆으로 넘치는 상자(.fitw)를 렌더러가 못 잡는다")
        rep = rep[:-1]
        bad = [c["file"].rsplit("_", 1)[-1] for c in rep if c["overflow"]]
        expect(not bad, f"{name}: 글자 한도를 채우면 넘치는 장 — {bad}")
        out.append(f"{name} 최소 배율 {min(c['k'] for c in rep)}")
    return " · ".join(out)


def t_webtoon():
    """5가지 웹툰(2026-11-02~, 운영자 '캐러셀을 H 극장처럼 웹툰으로' → '텍스트가 기존보다 부족하다'): card=N 컷은 그날 카드의
    제목·본문·'그래서 나는?'·출처를 그대로 가져오고, summary 장은 컷 순서대로 5가지를 싣는다. 지난 만화 설정(card 없음)은 그대로."""
    sys.path.insert(0, str(AUTOMATION / "pilots" / "ai_reel"))
    import comic
    from edith import content as content_mod
    day = daily_issues(1)[0]
    issues = content_mod.load(day)["card_issues"]
    cfg = {"panels": [{"t": 1, "card": 2}, {"t": 2, "card": 1, "bubble": "직접 쓴 말풍선"}], "summary": True}
    picked = comic.from_cards(cfg, day)
    first, second = cfg["panels"]
    expect(re.sub(r"<[^>]+>", "", first["bubble"]).replace("<br>", "") and first["take"] and first["body"] and first["src"],
           "card 컷에 제목·본문·'그래서 나는?'·출처가 다 들어오지 않는다")
    expect(comic.plain(first["take"]) == comic.plain(comic._md(issues[1]["takeaway"])), "'그래서 나는?'이 카드 takeaway 와 다르다")
    expect("\u2060" not in first["src"], "출처에 줄바꿈 방지 문자가 남았다")
    expect(second["bubble"] == "직접 쓴 말풍선", "직접 쓴 말풍선을 카드 글이 덮어썼다")
    expect([it["headline"] for it in picked] == [issues[1]["headline"], issues[0]["headline"]], "요약 장 순서가 컷 순서가 아니다")
    # 컷에서 바꾼 숫자(한 매체에만 있던 카드 숫자 → 두 매체 공통 사실, 2026-11-04 카톡 '12년 만' → '처음')는 표지 목차·'한눈에'에도 — 카드 원본은 그대로
    fixed = comic.from_cards({"panels": [{"t": 1, "card": 1, "number": "처음"}, {"t": 2, "card": 2}], "summary": True}, day)
    expect([it.get("number") for it in fixed] == ["처음", issues[1].get("number")], "컷에서 바꾼 숫자가 표지 목차·요약 장에 안 들어간다")
    expect(content_mod.load(day)["card_issues"][0].get("number") == issues[0].get("number"), "컷 숫자 바꾸기가 content 카드를 덮어썼다")
    expect(len(comic.from_cards({"panels": [{"t": 1}], "summary": True}, day)) == len(issues), "card 없는 요약 장이 카드 전부를 싣지 않는다")
    old = {"panels": [{"t": 1, "bubble": "옛 만화", "box": "설명"}]}
    expect(comic.from_cards(old, day) == [] and "take" not in old["panels"][0], "card 없는 지난 만화 설정이 바뀐다")
    expect("<span class='hl'>" in comic._md("==28%== 폭락") and "<br>" in comic._md("가\n나") and "&lt;" in comic._md("<b>"),
           "카드 글 → 말풍선 HTML 바꾸기가 틀린다")
    # 웹툰 3판(두 컷 한 장, 2026-11-01 운영자 '이게 최선이야?'): 위 컷 → 내레이션 → 본문 → 말풍선 → 아래 컷 순서로 한 세로 칸(.duo.fit)에,
    # 숫자 스티커·말풍선 쪽·꼬리 자리는 설정대로(그림을 보고 인물을 덮지 않는 쪽으로 고른다)
    img = ROOT / "assets" / "mascot" / "h-hello.png"
    p = {"bubble": "인텔 하루<br><span class='hl'>28.58%</span> 폭락", "body": "본문", "take": "그래서", "number": "28.58%", "tag": "반도체", "src": "가·나"}
    h = comic.duo_slide({}, 2, dict(p), img, img)
    order = [h.find(k) for k in ("class='duo fit'", "class='fr'", "class='num'>1<", "class='stk'>28.58%<", "class='narr'",
                                   "class='body3'", "class='say l'", "class='fr b'", "class='src'")]
    expect(-1 not in order and order == sorted(order), f"두 컷 장의 칸 순서가 틀리다: {order}")
    expect("인텔 하루 <span class='hl'>28.58%</span> 폭락" in h, "내레이션 상자에 카드 제목이 한 줄로 들어가지 않는다")
    h2 = comic.duo_slide({}, 3, {**p, "say_side": "right", "tail": "out", "stk_side": "left"}, img, img)
    h3 = comic.duo_slide({}, 3, {**p, "stk_side": "none"}, img, img)
    expect("class='say r out'" in h2 and "class='stk l'" in h2 and "class='stk" not in h3, "말풍선 쪽·꼬리·스티커 자리 설정이 안 먹는다")
    cov = comic.duo_cover({"title": "제목"}, [{"tag": "반도체", "number": "28.58%"}, {"tag": "BYD", "number": "2만137대"}], img, "50% 50%")
    expect("class='cov fit'" in cov and "<b>2</b>BYD<i>2만137대</i>" in cov and "넘겨서 2가지 보기" in cov, "두 컷 웹툰 표지 목차가 틀리다")
    return f"{day} 카드 {len(picked)}장 → 컷·요약 · 지난 만화 설정 그대로 · 두 컷 장 칸 순서"


def t_comic_only():
    """웹툰만 만든 날 검수(qa --comic — 11월 크레딧 계획: 홀수 날은 AI 영상·목소리 없이 5가지 웹툰만, 19:30 저녁 사슬이 올린다):
    영상·목소리·릴스 캡션이 없어도 통과하고, 만화 장수·크기·캡션('AI로 만들'·해시태그)·content 에 없는 숫자·'출처:' 칸은 그대로 막는다."""
    sys.path.insert(0, str(AUTOMATION / "pilots" / "ai_reel"))
    import qa
    from edith import content as content_mod
    day = daily_issues(1)[0]
    raw = json.loads((ROOT / "content" / f"{day}.json").read_text(encoding="utf-8"))
    corpus = json.dumps(raw, ensure_ascii=False)
    picked = [(n, it) for n, it in enumerate(content_mod.load(day)["card_issues"], 1)
              if len({s.get("name") for s in (qa.covered_item({"item": it["tag"]}, raw) or {}).get("sources") or []}) >= 2][:3]
    expect(len(picked) >= 2, f"{day} 호에 출처 2곳인 카드가 2장 미만이다")
    cells = ["·".join(sorted({s["name"] for s in qa.covered_item({"item": it["tag"]}, raw)["sources"]})[:2]) for _, it in picked]

    def brief():
        return {"date": day, "items": [it["tag"] for _, it in picked],
                "comic": {"series": "오늘 아침", "layout": "duo", "title": "오늘 아침 소식", "cover": {"img": "cover.png"}, "summary": True,
                          "panels": [{"card": n, "img_a": "a.png", "img_b": "b.png"} for n, _ in picked],
                          "end": {"title": "오늘 아침 소식,<br>매일 8시 30분", "sub": "경제부터 트렌드까지"}}}

    def jpeg(w, h):   # SOF0 머리만 있는 JPEG — 검수는 크기만 읽는다(ffprobe 없이)
        return (b"\xff\xd8\xff\xe0" + (16).to_bytes(2, "big") + b"JFIF\x00" + b"\x00" * 9 + b"\xff\xc0" + (17).to_bytes(2, "big")
                + b"\x08" + h.to_bytes(2, "big") + w.to_bytes(2, "big") + b"\x03" + b"\x00" * 9 + b"\xff\xd9")

    letters = qa.promo_lines(day)   # 11/06~ '구독하면 받는 것' 한 줄 — 11/09~ 둘째 줄(qa.letter_top, 11/08 주간 루틴)
    good_cap = ("오늘 아침 소식 넘겨서 보기\n" + "".join(f"{x}\n" for x in letters[:1])
                + "\n이 그림은 AI로 만들었어요. 숫자는 기사 2곳 이상에서 확인했어요.\n"
                f"출처: {' / '.join(cells)}\n#경제뉴스 #EDITH")
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        (folder / "comic").mkdir()

        def run(pages=4, size=(1080, 1350), cap=good_cap, ep=None):
            for old in (folder / "comic").glob("*.jpg"):
                old.unlink()
            for i in range(1, pages + 1):
                (folder / "comic" / f"c{i}.jpg").write_bytes(jpeg(*(size if i == pages else (1080, 1350))))
            (folder / "comic_caption.txt").write_text(cap, encoding="utf-8")
            return qa.comic_only(ep or brief(), folder, raw, corpus)

        ok = run()
        expect(ok == [], f"영상·목소리 없는 웹툰만 설정이 통과하지 못한다: {ok}")
        expect(qa.jpeg_size(folder / "comic" / "c1.jpg") == (1080, 1350), "JPEG 머리에서 크기를 읽지 못한다")
        expect(any("2장" in f for f in run(pages=2)), "만화 2장을 통과시켰다")
        expect(any("1080×1920" in f for f in run(size=(1080, 1920))), "1080×1350 이 아닌 장을 통과시켰다")
        expect(any("AI로 만들" in f for f in run(cap=good_cap.replace("이 그림은 AI로 만들었어요. ", ""))), "'AI로 만들' 줄 없는 캡션을 통과시켰다")
        expect(any("해시태그 6개" in f for f in run(cap=good_cap + " #a #b #c #d")), "해시태그 6개를 통과시켰다")
        expect(any("content 에 없는 숫자" in f for f in run(cap=good_cap.replace("넘겨서 보기", "987654명이 봤어요"))),
               "content 에 없는 숫자를 통과시켰다")
        swapped = good_cap.replace(f"출처: {' / '.join(cells)}", f"출처: {' / '.join(reversed(cells))}")
        expect(any("출처" in f for f in run(cap=swapped)), "'출처:' 칸 순서가 바뀐 캡션을 통과시켰다")
        expect(any('"comic"' in f for f in run(ep={"date": day, "items": brief()["items"]})), "comic 설정 없는 brief 를 통과시켰다")
        from edith import site as site_mod
        if letters and day >= site_mod.LETTER_TOP_FROM:
            moved = good_cap.replace(f"\n{letters[0]}\n", "\n").replace("\n출처:", f"\n{letters[0]}\n출처:")
            expect(any("둘째 줄" in f for f in run(cap=moved)), "'구독하면 받는 것' 줄이 둘째 줄이 아닌 웹툰 캡션을 통과시켰다(11/09~)")
    return f"{day} 카드 {len(picked)}장 웹툰만 — 통과 · 장수·크기·AI 줄·해시태그·숫자·출처 칸·구독 줄 자리는 막음"


def t_webtoon_render():
    """웹툰 3판 두 컷 장이 카드 글자 한도(제목 26·본문 80·'그래서' 60·숫자 9)를 꽉 채워도 넘치지 않고(두 컷이 같이 줄어든다),
    한도를 크게 넘긴 글은 렌더러가 넘침으로 잡아 실패한다(반쯤 잘린 장을 올리지 않게) — 실제로 렌더링(node·Playwright)."""
    sys.path.insert(0, str(AUTOMATION / "pilots" / "ai_reel"))
    import comic
    from edith.content import CARD_LIMITS as L
    from edith.fonts import font_css
    img = ROOT / "assets" / "mascot" / "h-hello.png"

    def fill(n, words="반도체 지수 하락 투자자 비중부터 점검 월요일 시장 금리 환율 수입차 점유율"):   # 띄어쓰기 있는 실제 같은 글
        out = ""
        while len(out) < n:
            out += (" " if out else "") + words.split()[len(out) % len(words.split())]
        return out[:n].rstrip()

    head = fill(L["headline"] - 8) + " ==1,234억원=="   # 표시 글자 수 ≈ 한도
    worst = {"bubble": comic._md(head), "body": comic._md(fill(L["body"] - 6) + " 12.3%"),
             "take": comic._md(fill(L["takeaway"])), "number": "9" * L["number"], "tag": "반도체 급락", "src": "가·나·다 10.31"}
    fonts = font_css()
    with tempfile.TemporaryDirectory() as tmp:
        comic.shot(comic.page(fonts, comic.duo_slide({}, 2, worst, img, img)), Path(tmp) / "worst.jpg")
        expect((Path(tmp) / "worst.jpg").stat().st_size > 20000, "한도를 채운 두 컷 장이 비어 있다")
        try:
            comic.shot(comic.page(fonts, comic.duo_slide({}, 2, {**worst, "body": "라" * 600}, img, img)), Path(tmp) / "over.jpg")
            caught = False
        except SystemExit as e:
            caught = "넘쳤" in str(e)
        expect(caught, "한도를 크게 넘긴 두 컷 장을 넘침으로 잡지 못한다")
        # 한 묶음 전체(표지·두 컷·요약·끝 장) — card 없는 컷이 끼어도 컷마다 제 카드 글이 들어가고, 그림이 없으면 아무것도 지우기 전에 멈춘다
        from edith import content as content_mod
        day = daily_issues(1)[0]
        issues = content_mod.load(day)["card_issues"]
        ep = {"date": day, "comic": {"series": "오늘 아침 5가지", "layout": "duo", "title": "제목<br>둘째 줄", "cover": {"img": str(img)},
                                     "summary": True, "sources": "장마다 표시", "end": {"title": "끝", "sub": "끝"},
                                     "panels": [{"card": 2, "img_a": str(img), "img_b": str(img)},
                                                {"bubble": "직접 쓴 제목", "body": "본문", "take": "그래서", "img_a": str(img), "img_b": str(img)},
                                                {"card": 1, "img_a": str(img), "img_b": str(img), "stk_side": "none"}]}}
        out = Path(tmp) / "set"
        n = comic.build(json.loads(json.dumps(ep)), None, out, alt_path=Path(tmp) / "alt.json")
        alts = json.loads((Path(tmp) / "alt.json").read_text(encoding="utf-8"))
        expect(n == 6 and sorted(f.name for f in out.glob("c*.jpg")) == [f"c{i}.jpg" for i in range(1, 7)] and sorted(alts) == sorted(f"c{i}.jpg" for i in range(1, 7)),
               f"두 컷 웹툰 묶음이 표지·컷 3·요약·끝 장 6장이 아니다: {n}")
        head = lambda k: comic.plain(comic._md(issues[k]["headline"]))  # noqa: E731
        expect(head(1) in alts["c2.jpg"] and "직접 쓴 제목" in alts["c3.jpg"] and head(0) in alts["c4.jpg"],
               "card 없는 컷이 끼면 뒤 컷의 카드 글이 어긋난다")
        bad = json.loads(json.dumps(ep))
        bad["comic"]["panels"][1]["img_b"] = str(Path(tmp) / "없는 그림.png")
        try:
            comic.build(bad, None, out, alt_path=Path(tmp) / "alt.json")
            stopped = False
        except SystemExit as e:
            stopped = "그림이 없어요" in str(e)
        expect(stopped and len(list(out.glob("c*.jpg"))) == 6, "그림이 없는데 멈추지 않거나 지난 장을 지웠다")
    return "한도 꽉 채움 통과 · 넘침 잡음 · 묶음 6장(카드 없는 컷 섞임) · 그림 없으면 멈춤"


def t_mascot():
    """마스코트(2026-11-01 운영자 '마스코트 캐릭터 만들어 줘'): 자세 9장이 512×512 투명 PNG 로 있고, 설정 문서가 파일마다 쓰임을 적었다."""
    from edith.common import image_size
    folder = ROOT / "assets" / "mascot"
    poses = ["hello", "point", "newspaper", "surprised", "thinking", "celebrate", "checklist", "calendar", "coffee"]
    readme = (folder / "README.md").read_text(encoding="utf-8")
    for p in poses:
        f = folder / f"h-{p}.png"
        expect(f.exists(), f"마스코트 {f.name} 가 없다")
        expect(image_size(f) == (512, 512), f"마스코트 {f.name} 가 512×512 가 아니다: {image_size(f)}")
        expect(f.read_bytes()[25] == 6, f"마스코트 {f.name} 가 투명 배경(RGBA) PNG 가 아니다")   # IHDR 색 형식 6 = RGBA
        expect(f"`h-{p}.png`" in readme, f"마스코트 설정 문서에 {f.name} 쓰임이 없다")
    return f"자세 {len(poses)}장"


def t_indexnow():
    """검색 알림(IndexNow, 2026-10-31 경쟁 비교 — 배포 길 넓히기): 키 파일이 키와 같고, 푸시에서 맨 위 호 페이지만 골라,
    모든 주소가 키 파일 폴더 아래에 있고(IndexNow 규칙 — 하위 경로 사이트), 시험 실행은 네트워크를 쓰지 않는다."""
    import indexnow
    site, key, key_url = indexnow.settings()
    kf = ROOT / f"{key}.txt"
    expect(kf.exists() and kf.read_text(encoding="utf-8").strip() == key, f"키 파일 {kf.name} 이 없거나 내용이 키와 다르다")
    commits = json.dumps([{"added": ["2026-11-01.html", "instagram/2026-11-01/index.html", "content/2026-11-01.json"],
                           "modified": ["index.html", "2026-10-31.html"], "removed": ["2026-10-01.html"]},
                          {"added": [], "modified": ["2026-11-01.html"]}])
    dates = indexnow.dates_from_commits(commits)
    expect(dates == ["2026-11-01", "2026-10-31"], f"푸시에서 고른 호: {dates}")
    expect(indexnow.dates_from_commits("null") == [] and indexnow.dates_from_commits("") == [], "commits 가 없을 때 빈 목록이 아니다")
    urls = indexnow.urls_for(dates, site)
    expect(urls == [f"{site}/2026-11-01.html", f"{site}/2026-10-31.html", f"{site}/"], f"알릴 주소: {urls}")
    folder = key_url.rsplit("/", 1)[0] + "/"
    expect(all(u.startswith(folder) for u in urls), "키 파일 폴더 밖 주소를 알린다(IndexNow 가 거절한다)")
    body = indexnow.payload(urls, site, key, key_url)
    expect(body["host"] == "vetnam555-del.github.io" and body["keyLocation"] == key_url and body["key"] == key, f"보낼 내용: {body}")
    saved = indexnow.submit, indexnow.wait_live, sys.argv
    indexnow.submit = indexnow.wait_live = lambda *a, **k: (_ for _ in ()).throw(AssertionError("시험 실행이 네트워크를 썼다"))
    try:
        sys.argv = ["indexnow.py", "--date", "2026-10-31", "--dry-run"]
        with contextlib.redirect_stdout(io.StringIO()):
            expect(indexnow.main() == 0, "시험 실행이 0 으로 끝나지 않았다")
    finally:
        indexnow.submit, indexnow.wait_live, sys.argv = saved
    wf = (ROOT / ".github" / "workflows" / "indexnow.yml").read_text(encoding="utf-8")
    expect('paths: ["20*.html"]' in wf and "indexnow.py --commits" in wf, "검색 알림 워크플로가 호 페이지 푸시에 걸려 있지 않다")
    return f"{len(urls)}개 주소 · 키 파일 {kf.name[:8]}…"


def t_home():
    """첫 화면 구독(2026-11-01 운영자 '첫 화면에서 바로 구독 신청 — 구독 수를 높이게'): index.html 구독 칸이 subscribe.html 과 같은
    Formspree 주소·칸(email·동의·ref)을 쓰고, 생성 표시(LATEST·ISSUES·호 수)가 있으며, regenerate_index 가 달 머리·예비 호 표시·
    최근 호(예비 호 제외)·호 수(가장 큰 VOL)를 바르게 쓰고 두 번 돌려도 같다. 공유 미리보기·아이콘이 제 크기다."""
    import struct
    from edith import site as site_mod
    home = (ROOT / "index.html").read_text(encoding="utf-8")
    sub = (ROOT / "subscribe.html").read_text(encoding="utf-8")
    action = re.search(r'<form id="subscribeForm" action="([^"]+)"', sub).group(1)
    expect(f'id="subscribeForm" action="{action}" method="POST"' in home, "첫 화면 구독 칸이 구독 페이지와 다른 주소로 보낸다")
    for need in ('name="email"', 'name="consent_marketing" value="yes" required', 'name="ref" id="ref"', 'name="subscribed_at"',
                 "<!-- LATEST:START -->", "<!-- LATEST:END -->", "<!-- ISSUES:START -->", "<!-- ISSUES:END -->", "<span data-issue-count>",
                 'id="privacy"', 'href="#privacy"', "og_image.png", "assets/mascot/avatar-96.png"):
        expect(need in home, f"첫 화면에 {need} 가 없다")
    expect("-home" in home and "utm_source" in home, "첫 화면 구독 경로(ref …-home, utm_source=ig)를 남기지 않는다")
    # 2026-11-01 운영자: 문의 주소는 makefair@naver.com (예전 주소가 공개 페이지에 남지 않게)
    for name in ("index.html", "subscribe.html", "unsubscribe.html"):
        page = (ROOT / name).read_text(encoding="utf-8")
        expect("makefair@naver.com" in page and "hll.kr" not in page, f"{name} 의 문의 주소가 makefair@naver.com 이 아니다")
    manifest = {"issues": [
        {"vol": "098", "date": "2026-09-29", "weekday": "화", "emoji": "📈", "title": "구월 호", "subtitle": "s", "filename": "2026-09-29.html", "key_keywords": ["금리"]},
        {"vol": "099", "date": "2026-10-01", "weekday": "목", "emoji": "🧭", "title": "시월 호", "subtitle": "s", "filename": "2026-10-01.html", "key_keywords": ["연말정산", "청약"]},
        {"vol": "100", "date": "2026-10-02", "weekday": "금", "emoji": "🔁", "title": "다시 보기 호", "subtitle": "s", "filename": "2026-10-02.html", "source_mode": "rewind"}]}
    with tempfile.TemporaryDirectory() as tmp:
        saved = site_mod.INDEX
        site_mod.INDEX = Path(tmp, "index.html")
        try:
            site_mod.INDEX.write_text(home, encoding="utf-8")
            site_mod.regenerate_index(manifest)
            once = site_mod.INDEX.read_text(encoding="utf-8")
            site_mod.regenerate_index(manifest)
            twice = site_mod.INDEX.read_text(encoding="utf-8")
        finally:
            site_mod.INDEX = saved
    expect(once == twice, "regenerate_index 를 두 번 돌리면 첫 화면이 달라진다")
    issues = once[once.index("<!-- ISSUES:START -->"):once.index("<!-- ISSUES:END -->")]
    latest = once[once.index("<!-- LATEST:START -->"):once.index("<!-- LATEST:END -->")]
    expect(issues.index("2026년 10월") < issues.index("다시 보기 호") < issues.index("2026년 9월") and issues.count('class="item"') == 3,
           "지난 호 목록이 최신순·달 머리로 나뉘지 않았다")
    expect('<span class="badge">다시 보기</span>' in issues and "시월 호" in latest and "다시 보기 호" not in latest
           and "<span>연말정산</span>" in latest, "최근 호 카드가 예비 호를 고르거나 키워드가 없다")
    expect("<span data-issue-count>100</span>" in once, "호 수가 가장 큰 VOL 이 아니다")
    expect(home == open(ROOT / "index.html", encoding="utf-8").read(), "시험이 진짜 index.html 을 바꿨다")

    def png_size(path):
        with open(path, "rb") as f:
            head = f.read(24)
        return struct.unpack(">II", head[16:24])
    for name, size in (("og_image.png", (1200, 630)), ("favicon.png", (64, 64)), ("apple-touch-icon.png", (180, 180)),
                       ("assets/mascot/avatar-96.png", (96, 96)), ("assets/mascot/avatar-192.png", (192, 192))):
        expect((ROOT / name).exists() and png_size(ROOT / name) == size, f"{name} 이 없거나 {size} 가 아니다(build_site_assets.py)")
    expect((ROOT / "og_image.png").stat().st_size > 40_000, "og_image.png 가 너무 작다 — 한글이 □ 로 깨졌던 옛 그림일 수 있다")
    return f"구독 칸 → {action.rsplit('/', 1)[-1]} · 생성 표시 3곳"


def t_brand_v2():
    """문구·마크 2판(2026-11-01 운영자 '내 돈·일·소비 같은 문구가 촌스럽다', automation/reviews/2026-11-01-copy.md):
    11/01 호부터 메일 바닥·추천 메일이 대표 한 줄(BRAND_LINE — 같은 날 운영자 '직장인보다 2030 마케팅·트렌드·경제 폭넓게'로
    '2030의 아침을 편집합니다'), 프로필 카드·노트 마크가 마스코트 얼굴(미소)이고,
    그 전 호는 예전 그대로(지난 호 다시 빌드가 발행본과 같아야 한다). 사이트·구독 페이지·RSS 에 옛 문구가 남지 않았다."""
    import copy as copy_mod
    import inspect
    from edith import newsletter
    from edith import content as content_mod
    from edith import site as site_mod
    site = load_config()["site_url"].rstrip("/")
    d = content_mod.load(daily_issues(1)[0])
    old = copy_mod.deepcopy(d)
    old["date"] = "2026-10-31"
    new = copy_mod.deepcopy(d)
    new["date"] = newsletter.BRAND_V2_FROM
    a, b = newsletter.render(old, site, 10), newsletter.render(new, site, 10)
    expect("트렌드 한 입" in a and newsletter.BRAND_LINE not in a, "11/01 전 호의 바닥 문구가 바뀌었다(지난 호는 기록)")
    expect(newsletter.BRAND_LINE in b and "트렌드 한 입" not in b, "11/01 호 메일에 옛 문구('트렌드 한 입')가 남았다")
    expect("border-radius:0 0" in b and "border-radius:0 0" not in a, "11/01 호 프로필·노트 마크가 마스코트 얼굴(미소)이 아니다")
    for name in ("index.html", "subscribe.html"):
        page = (ROOT / name).read_text(encoding="utf-8")
        expect("2030이 알아야 할 것만" in page and "직장인 버전" not in page and "돈·일·소비에" not in page
               and "트렌드 한 입" not in page and "TREND BRIEF" not in page,
               f"{name} 에 옛 문구가 남았거나 새 대표 문구가 없다")
    expect("트렌드 한 입" not in inspect.getsource(site_mod.write_feeds), "RSS 제목이 옛 문구다")
    # 11/03 호부터 프로필·노트 마크는 프로필과 같은 그림(2026-11-02 운영자 '메일 로고가 프로필 로고랑 다르다') — 11/02 호까지는 도형 그대로
    img = f'<img src="{site}/{newsletter.MARK_IMG}"'
    last_shape = copy_mod.deepcopy(d)
    last_shape["date"] = "2026-11-02"
    first_img = copy_mod.deepcopy(d)
    first_img["date"] = newsletter.MARK_IMG_FROM
    c, e = newsletter.render(last_shape, site, 10), newsletter.render(first_img, site, 10)
    expect(img not in c and "border-radius:0 0" in c, "11/02 호까지의 마크가 바뀌었다(지난 호는 기록)")
    expect(e.count(img) == 2 and 'width="58" height="58" alt=""' in e and 'width="40" height="40" alt=""' in e,
           f"{newsletter.MARK_IMG_FROM} 호 프로필 카드·노트 마크가 프로필 그림({newsletter.MARK_IMG})이 아니다")
    expect('bgcolor="#FF5233"' in e and "border-radius:0 0" not in e, "그림을 막는 메일에서 볼 주황 동그라미 바탕이 없거나 도형 얼굴이 남았다")
    expect((ROOT / newsletter.MARK_IMG).exists(), f"{newsletter.MARK_IMG} 가 없다(build_site_assets.py)")
    return f"{newsletter.BRAND_V2_FROM} 호부터 · '{newsletter.BRAND_LINE}' · 마크 그림 {newsletter.MARK_IMG_FROM}~"


def t_ai_reel():
    """AI 영상 릴스(2026-11-01 운영자 '바로 올려줘 … 스토리에도'): instagram/{키}/reel_ai.mp4 가 있으면 make_reel 로 만들지 않고
    그 영상을 형식 'ai' 로 쓰고, 캡션은 reel_ai_caption.txt, 소리는 영상 안에 있어 출처 댓글이 필요 없다(CC0 취급)."""
    import inspect
    import tempfile
    import post_instagram as pi
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        (folder / "reel_caption.txt").write_text("보통 릴스 캡션", encoding="utf-8")
        (folder / "reel_ai_caption.txt").write_text("AI 릴스 캡션", encoding="utf-8")
        (folder / pi.AI_REEL).write_bytes(b"\x00" * 2048)
        out, track = pi.build_reel("2026-11-01", folder, "ffmpeg")
        expect(out == folder / pi.AI_REEL and track["style"] == "ai" and track["credit_in_video"], "reel_ai.mp4 를 쓰지 않는다")
        expect(track["license"].upper() == "CC0", "AI 영상에 음악 출처 댓글이 붙는다")
        expect(pi.reel_caption(folder, track).startswith("AI 릴스 캡션") and pi.AI_NOTE_KEY in pi.reel_caption(folder, track)
               and pi.reel_caption(folder, {"style": "vertical"}) == "보통 릴스 캡션", "AI 릴스 캡션 파일을 고르지 못한다")
        (folder / "reel_ai_caption.txt").unlink()   # AI 전용 캡션이 없어도 AI 제작 표시는 남는다
        expect(pi.AI_NOTE_KEY in pi.reel_caption(folder, track), "AI 전용 캡션이 없을 때 AI 표시가 빠진다")
    src = inspect.getsource(pi.main)
    expect("reel_ai" in src and "story_ai" in src and "post_story_video" in src, "AI 영상 릴스·스토리 게시 단계가 없다")

    class G:  # 라벨 값을 안 받는 계정이면 라벨 없이 다시 만들고 기록한다
        def __init__(self, accept):
            self.accept, self.calls = accept, []

        def call(self, method, path, **params):
            self.calls.append(params)
            if "is_ai_generated" in params and not self.accept:
                raise pi.IGError("400 OAuthException (code 100): Invalid parameter is_ai_generated")
            return {"id": "c1"}
    info = {}
    g = G(True)
    expect(pi.create_with_ai_label(g, "u", {"media_type": "REELS"}, info) == "c1" and info["ai_label"] is True
           and g.calls[0].get("is_ai_generated") == "true", "AI 라벨을 붙여 만들지 않는다")
    info = {}
    g = G(False)
    expect(pi.create_with_ai_label(g, "u", {"media_type": "REELS"}, info) == "c1" and info["ai_label"] is False
           and len(g.calls) == 2 and "is_ai_generated" not in g.calls[1], "라벨을 안 받을 때 라벨 없이 다시 만들지 않는다")
    g = G(False)
    try:   # 스토리는 캡션이 없어 라벨이 필수 — 못 붙이면 올리지 않는다
        pi.post_story_video(g, "u", "https://x/v.mp4", False, {})
        expect(False, "AI 라벨 없는 스토리 영상을 올린다")
    except pi.IGError:
        expect(len(g.calls) == 1, "라벨을 거절당한 뒤 라벨 없는 스토리 컨테이너를 만든다")
    expect("want_reel" in src.split("AI_REEL")[1][:400], "AI 릴스가 릴스 게시 설정(reel=false)을 무시한다")
    expect("AI_REEL" in inspect.getsource(pi.prune), "오래된 AI 릴스 영상을 정리하지 않는다")
    # 'H 극장' 만화 캐러셀: 08:30 캐러셀 실행(only=carousel)에선 안 올리고, 라벨·AI 한 줄·정리 대상
    expect("post_comic" in src and "COMIC_DIR" in inspect.getsource(pi.prune), "만화 캐러셀 게시·정리 단계가 없다")
    expect('args.only != "carousel"' in src.split("H 극장 만화")[0][-600:], "만화 캐러셀이 08:30 캐러셀 실행에서 올라갈 수 있다")
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        (folder / pi.COMIC_DIR).mkdir()
        for i in (1, 2, 3):
            (folder / pi.COMIC_DIR / f"c{i}.jpg").write_bytes(b"x")
        (folder / "comic_caption.txt").write_text("만화 캡션", encoding="utf-8")
        g = G(True)
        saved_wp, saved_wr, saved_pub = pi.wait_public, getattr(G, "wait_ready", None), pi.publish
        pi.wait_public = lambda urls, **k: None
        G.wait_ready = lambda self, cid, what, timeout=600: None
        pi.publish = lambda g_, uid, cid, what, tries=6: "m1"
        try:
            mid, info = pi.post_comic(g, "u", "2026-11-01", folder, "https://x", False)
        finally:
            pi.wait_public, pi.publish = saved_wp, saved_pub
        parent = g.calls[-1]
        expect(mid == "m1" and info.get("ai_label") is True and parent.get("is_ai_generated") == "true"
               and pi.AI_NOTE_KEY in parent.get("caption", "") and parent.get("media_type") == "CAROUSEL", "만화 캐러셀에 AI 라벨·AI 한 줄이 없다")

    # 메인 2~5번 AI 영상(운영자 앱 제작, 11/01~) — instagram/{키}/extra/N/ 를 AI 라벨 릴스로, 검수한 캡션 없으면 안 올림
    expect("--extra" in inspect.getsource(pi.main) and "EXTRA_DIR" in inspect.getsource(pi.prune), "메인 2~5번 AI 영상 게시·정리 단계가 없다")
    wf = (ROOT / ".github" / "workflows" / "post-instagram.yml").read_text(encoding="utf-8")
    expect("IN_EXTRA" in wf and "--extra $IN_EXTRA" in wf, "post-instagram.yml 에 extra 입력이 없다")
    xsrc = inspect.getsource(pi.main).split("if args.extra:", 1)[-1].split("post_extra(", 1)[0]
    expect('cfg.get("reel", True)' in xsrc and 'cfg.get("weekly_reel", True)' in xsrc,
           "메인 AI 릴스가 릴스 게시 설정(config.instagram.reel·weekly_reel)을 보지 않는다(11/01 Codex)")
    with tempfile.TemporaryDirectory() as tmp:
        saved = pi.INSTAGRAM_DIR, pi.publish_video, pi.wait_public, pi.publish
        pi.INSTAGRAM_DIR = Path(tmp)
        xdir = Path(tmp) / "2026-11-01" / pi.EXTRA_DIR / "3"
        xdir.mkdir(parents=True)
        (xdir / pi.AI_REEL).write_bytes(b"x")
        pi.publish_video = lambda out, key: None
        pi.wait_public = lambda urls, **k: None
        pi.publish = lambda g_, uid, cid, what, tries=6: "x3"
        G.wait_ready = lambda self, cid, what, timeout=600: None
        try:
            g = G(True)
            no_cap = None
            try:
                pi.post_extra(g, "u", "2026-11-01", 3, {}, False, "ffmpeg", "https://x")
            except pi.IGError as e:
                no_cap = str(e)
            (xdir / "reel_ai_caption.txt").write_text("메인 3번 캡션 #EDITH", encoding="utf-8")
            mid, info = pi.post_extra(g, "u", "2026-11-01", 3, {}, False, "ffmpeg", "https://x")
        finally:
            pi.INSTAGRAM_DIR, pi.publish_video, pi.wait_public, pi.publish = saved
        reel = g.calls[-1]
        expect(no_cap and "reel_ai_caption" in no_cap, "검수한 캡션 없이 메인 AI 릴스를 올리려 했다")
        expect(mid == "x3" and reel.get("is_ai_generated") == "true" and reel.get("media_type") == "REELS"
               and reel.get("video_url", "").endswith("/instagram/2026-11-01/extra/3/reel_ai.mp4")
               and "메인 3번 캡션" in reel.get("caption", "") and pi.AI_NOTE_KEY in reel.get("caption", ""),
               f"메인 AI 릴스 게시 값이 틀린다: {reel}")

    # 게시 전 숫자 검수 — 큰 금액은 한 덩어리로 대조한다(11/01 Codex: '1조6000억원'이 '1조5000억원과 6000억원'에서 통과하면 안 된다)
    sys.path.insert(0, str(ROOT / "automation" / "pilots" / "ai_reel"))
    import qa
    expect(qa.check_numbers([("t", "1조6000억원")], "1조5000억원과 6000억원"), "쪼갠 금액 조각으로 '1조6000억원'이 통과했다")
    expect(qa.check_numbers([("t", "1조7000억원")], "1조6000억원") and qa.check_numbers([("t", "12거래일")], "11거래일, 12.64"),
           "content 에 없는 숫자가 통과했다")
    expect(not qa.check_numbers([("t", "1조6000억원 넘게 · 3.48% · 장중 5599 · 3만 명")], "1조 6000억원 순매도 3.48% 5599.42 3만 명"),
           "content 에 있는 숫자를 막았다")
    # 같은 틀 반복 금지(2026-11-02~) — 11/01 운영자 "패턴이 똑같네? 헉으로 시작하고 멘트가 비슷하다"
    with tempfile.TemporaryDirectory() as tmp:
        def ep_at(day, name, word, hook, kick, bye):
            d = Path(tmp) / day; d.mkdir(exist_ok=True)
            e = {"date": day, "hook": hook, "voices": [{"text": f"{word} 시작 대사"}, {"text": bye}],
                 "captions": [{"html": f'<div class="kick">{kick}</div><div class="main">x</div>'}]}
            (d / name).write_text(json.dumps(e, ensure_ascii=False), encoding="utf-8")
            return d / name, e
        ep_at("2026-11-01", "episode.json", "헉…", None, "그래서 나는?", "내일 아침 여덟 시 반에 또 만나요!")
        ep_at("2026-11-02", "episode.json", "28.58%.", "숫자 먼저", "오늘 할 일", "팔로우하면 내일 아침에도 알려 줄게!")
        same = qa.pattern_repeats(*ep_at("2026-11-02", "extra2.json", "헉…", "숫자 먼저", "오늘 할 일", "팔로우하면 내일 아침에도 알려 줄게!"))
        fresh = qa.pattern_repeats(*ep_at("2026-11-02", "extra3.json", "버스가", "질문", "기억할 것", "저장해 두고, 필요할 때 꺼내 봐!"))
        old = qa.pattern_repeats(*ep_at("2026-11-01", "extra2.json", "헉…", None, "그래서 나는?", "내일 아침 여덟 시 반에 또 만나요!"))
    expect(len(same) == 4 and any("첫 마디 '헉'" in f for f in same) and any("훅 종류" in f for f in same)
           and any("머리말" in f for f in same) and any("끝인사" in f for f in same), f"같은 틀 반복을 못 잡았다: {same}")
    expect(fresh == [] and old == [], f"다른 틀·11/01 기록을 막았다: {fresh} {old}")
    # 기사·출처 맞춤(2026-11-02~) — 11/01 운영자 "기사 및 소스에 맞춰서 진행해 달라", Codex: 그 이슈의 sources 안에서만
    content_src = {"big_issue": {"tag": "BYD", "sources": [{"name": "서울경제"}, {"name": "TV조선"}]},
                   "items": [{"tag": "반도체 급락", "sources": [{"name": "전자신문"}, {"name": "헤럴드경제"}]},
                             {"tag": "샘 올트먼", "sources": [{"name": "서울경제"}, {"name": "MBC"}]}]}
    ok_ep = {"date": "2026-11-02", "item": "반도체 급락", "sources": ["전자신문", "헤럴드경제"],
             "end_card": {"note": "숫자는 기사 2곳 이상에서 확인했어요<br>(전자신문·헤럴드경제 보도 기준)"}}
    ok_cap = "본문\n출처: 전자신문·헤럴드경제(10.31)\n이 영상과 목소리는 AI로 만들었어요."
    wrong = {**ok_ep, "sources": ["서울경제", "MBC"], "end_card": {"note": "(서울경제·MBC 보도 기준)"}}
    expect(qa.source_gaps(ok_ep, content_src, ok_cap) == [], "출처를 다 적은 릴스를 막았다")
    expect(qa.source_gaps(wrong, content_src, "출처: 서울경제·MBC"), "다른 이슈(올트먼)의 매체를 적은 인텔 릴스가 통과했다")
    expect(qa.source_gaps({**ok_ep, "sources": ["전자신문"]}, content_src, ok_cap), "출처 1곳만 적은 릴스가 통과했다")
    expect(qa.source_gaps({**ok_ep, "item": "없는 이슈"}, content_src, ok_cap), "content 에 없는 이슈를 적은 릴스가 통과했다")
    expect(qa.source_gaps(ok_ep, content_src, "본문만"), "캡션에 출처 줄이 없는데 통과했다")
    expect(qa.source_gaps({**ok_ep, "item": "BYD", "sources": ["서울경제", "TV조선"], "end_card": {"note": "서울경제·TV조선"}},
                          content_src, "출처: 서울경제·TV조선") == [], "H PICK(big_issue) 출처를 막았다")
    expect(qa.source_gaps({"date": "2026-11-01"}, content_src, "") == [], "11/01 기록 회차를 출처 규칙으로 막았다")
    # '오늘 아침 5가지' 브리핑(2026-11-01 운영자 "메인 5개를 20초 한 편에") — 이슈마다 매체 2곳이 캡션 '출처:' 줄 한 칸에
    brief = {"date": "2026-11-02", "items": ["BYD", "반도체 급락", "샘 올트먼"], "end_card": {"note": "숫자는 기사 2곳 이상에서 확인했어요<br>(출처는 캡션에)"}}
    brief_cap = "출처: BYD 서울경제·TV조선 / 인텔 전자신문·헤럴드경제 / 올트먼 서울경제·MBC"
    expect(qa.source_gaps(brief, content_src, brief_cap) == [], "출처를 다 적은 5가지 브리핑을 막았다")
    expect(qa.source_gaps(brief, content_src, "출처: BYD 서울경제·TV조선 / 인텔 전자신문·헤럴드경제"),
           "한 이슈(올트먼)의 출처를 빼먹은 브리핑이 통과했다")
    expect(qa.source_gaps(brief, content_src, "출처: BYD 서울경제·MBC / 인텔 전자신문·헤럴드경제 / 올트먼 TV조선"),
           "출처 매체를 이슈끼리 섞어 적은 브리핑이 통과했다")
    expect(qa.source_gaps({**brief, "end_card": {"note": "숫자는 기사 2곳 이상에서 확인했어요"}}, content_src, brief_cap),
           "끝 화면에 출처 안내가 없는 브리핑이 통과했다")
    expect(qa.source_gaps({**brief, "items": ["BYD", "없는 이슈"]}, content_src, brief_cap), "content 에 없는 이슈를 담은 브리핑이 통과했다")
    # Codex: 두 이슈의 매체 묶음을 통째로 바꿔 적으면(인텔 칸에 올트먼 매체) 막아야 한다 — 칸은 영상 순서대로 이슈와 짝
    expect(qa.source_gaps(brief, content_src, "출처: BYD 서울경제·TV조선 / 인텔 서울경제·MBC / 올트먼 전자신문·헤럴드경제"),
           "두 이슈의 출처 묶음을 바꿔 적은 브리핑이 통과했다")
    expect(qa.source_gaps(brief, content_src, "출처: BYD 서울경제·TV조선 / 인텔 전자신문·헤럴드경제·MBC / 올트먼 서울경제·MBC"),
           "한 칸에 다른 이슈의 매체를 섞은 브리핑이 통과했다")
    expect(qa.source_gaps(brief, content_src, "출처: BYD 서울경제·TV조선 / 인텔 전자신문·헤럴드경제 / 올트먼 서울경제·MBC / 덤 MBC·TV조선"),
           "이슈 수와 칸 수가 다른 브리핑이 통과했다")
    # 11/06 — 이 이슈의 '연합뉴스TV' 칸 속 '연합뉴스'(다른 이슈 매체)는 섞인 게 아니다. 정말 '연합뉴스'를 덧붙이면 막는다
    c_yna = {"big_issue": {"tag": "가", "sources": [{"name": "세계일보", "url": "u1"}, {"name": "연합뉴스TV", "url": "u2"}]},
             "items": [{"tag": "나", "sources": [{"name": "연합뉴스", "url": "u3"}, {"name": "농민신문", "url": "u4"}]}]}
    b_yna = {"date": "2026-11-06", "items": ["가", "나"], "end_card": {"note": "숫자는 기사 2곳 이상에서 확인했어요<br>(출처는 캡션에)"}}
    expect(qa.source_gaps(b_yna, c_yna, "출처: 세계일보·연합뉴스TV / 연합뉴스·농민신문") == []
           and qa.source_gaps(b_yna, c_yna, "출처: 세계일보·연합뉴스TV·연합뉴스 / 연합뉴스·농민신문")
           and qa.source_gaps(b_yna, c_yna, "출처: 세계일보·연합뉴스TV / 연합뉴스TV·농민신문"),   # Codex — 거꾸로 '연합뉴스' 이슈 칸의 '연합뉴스TV'
           "'연합뉴스TV' 칸의 '연합뉴스'를 다른 이슈 매체로 막거나, 정말 덧붙인 '연합뉴스'·'연합뉴스' 이슈 칸의 '연합뉴스TV'를 놓친다")
    # Codex: brief.json 도 같은 틀 반복 검사 대상(전날 브리핑과 같은 첫 마디)
    with tempfile.TemporaryDirectory() as tmp:
        for day, name, word in (("2026-11-02", "brief.json", "오늘"), ("2026-11-03", "brief.json", "오늘")):
            d = Path(tmp) / day
            d.mkdir(exist_ok=True)
            (d / name).write_text(json.dumps({"date": day, "hook": "숫자 먼저", "voices": [{"text": f"{word} 아침 다섯 가지"}, {"text": "끝"}],
                                              "captions": [{"html": '<div class="kick">x</div>'}]}, ensure_ascii=False), encoding="utf-8")
        again = qa.pattern_repeats(Path(tmp) / "2026-11-03" / "brief.json", json.loads((Path(tmp) / "2026-11-03" / "brief.json").read_text(encoding="utf-8")))
    expect(any("첫 마디 '오늘'" in f for f in again), f"전날 brief.json 과 같은 첫 마디를 못 잡았다: {again}")
    screen_ok, spoken_ok = qa.brief_series(brief)
    expect(qa.check_numbers([("t", "오늘 아침 3가지")], "숫자 없음", allow=screen_ok) == []
           and qa.check_numbers([("t", "오늘 아침 4가지")], "숫자 없음", allow=screen_ok)
           and qa.check_spoken([(3.0, "가지", "")], "오늘 아침 세 가지", allow=spoken_ok)[1] == [],
           "브리핑 개수 표현('3가지')을 content 숫자로 막았거나, 다른 개수를 통과시켰다")
    # 검은 화면·어둡게 번쩍이는 프레임(11/01 운영자 "영상 중간중간에 검은색으로 끊기는 것 같다") — 끝 화면 페이드 인이 2프레임 검게 튀었다
    expect(qa.parse_blackdetect("[blackdetect @ 0x1] black_start:14.6333 black_end:14.7 black_duration:0.0666667") == [(14.6333, 14.7)],
           "blackdetect 출력을 못 읽는다")
    ts30 = [i / 30 for i in range(60)]
    old_fade = [110.0] * 30 + [16.0, 40.7] + [230.0] * 28     # 본편 → 검게 튄 2프레임 → 끝 화면(옛 페이드 인)
    crossfade = [110.0] * 30 + [150.0, 190.0] + [230.0] * 28  # 겹쳐 넘기기
    night_cut = [110.0] * 30 + [20.0] * 30                    # 밤 장면으로 바뀌는 컷은 번쩍임이 아니다
    expect([h[0] for h in qa.flash_frames(ts30, old_fade)] == [1.0, 1.033], "끝 화면 앞 검은 2프레임을 못 잡는다")
    expect(qa.flash_frames(ts30, crossfade) == [] and qa.flash_frames(ts30, night_cut) == [], "겹쳐 넘기기·밤 장면 컷을 번쩍임으로 잡았다")
    # 꽉 찬 화면(11/01 운영자 'H PICK 처럼 꽉 차게') — 위아래 흐린 띠(가로 띠 영상)는 막고, 얕은 초점으로 바닥이 흐린 장면 몇 개는 통과
    expect(qa.letterboxed([0.11] * 30 + [0.4] * 5) and not qa.letterboxed([0.35] * 20 + [0.12] * 10) and not qa.letterboxed([]),
           "흐린 위아래 띠(가로 띠 영상) 판정이 틀린다")
    # 멈춘 듯한 구간(11/02 운영자 '영상 중간에 끊기는 부분 없는지') — 1초 넘게 거의 안 움직이면 막고 0.8초는 통과, 천천히 다가가기(push)로 푼다
    still = [(round(i * 0.2, 1), 3.0) for i in range(10)] + [(round(2.0 + i * 0.2, 1), 0.2) for i in range(5)] + [(3.0, 25.0)]
    short = [(round(i * 0.2, 1), 3.0) for i in range(10)] + [(round(2.0 + i * 0.2, 1), 0.2) for i in range(4)] + [(2.8, 25.0)]
    expect(qa.stalls(still) == [(2.0, 3.0)] and qa.stalls(short) == [] and qa.stalls([(0.0, 0.1)] * 1) == [],
           "멈춘 듯한 구간(1초 이상) 판정이 틀린다")
    expect("stalls(motion_windows(video" in inspect.getsource(qa.main), "검수가 멈춘 듯한 구간을 보지 않는다")
    import episode as ep_mod
    pf = ep_mod.push_filter({"push": [[12.75, 13.96]]}, 24)
    expect("zoompan=" in pf and "between(it\\,12.75\\,13.96)" in pf and "fps=24" in pf and ep_mod.push_filter({}, 24) == "",
           "push(천천히 다가가기) 필터가 틀린다")
    expect(ep_mod.out_rate({"date": "2026-11-02"}, "없는파일.mp4") == 30 and ep_mod.out_rate({"date": "2026-11-03"}, "없는파일.mp4") == 30,
           "11/02 까지 설정의 fps 가 30 이 아니거나, 원본을 못 읽을 때 30 으로 돌아가지 않는다")
    # 대사 속 긴 쉼·소리 구멍(11/07~) — 11/06 운영자 "릴스 보니까 중간에 목소리 끊기는 것 같은데": 코인 줄 '코인 세금,' 뒤 0.54초 쉼이
    # 영상 한가운데(11.35초)에서 말소리보다 19dB 꺼졌다. 0.25초 넘는 쉼은 0.2초로 줄이고, 완성본에서 0.25초 넘게 12dB 꺼지면 막는다.
    speech, gap = [-12.0] * 50, [-80.0] * 54
    expect(ep_mod.pause_cuts(speech + gap + speech) == [(0.6, 0.94)]
           and ep_mod.pause_cuts(speech + [-80.0] * 20 + speech) == []
           and ep_mod.pause_cuts([-80.0] * 30 + speech + [-80.0] * 30) == [],
           "대사 속 쉼 줄이기가 틀린다 — 0.54초 쉼은 0.2초만 남기고, 0.2초 쉼·앞뒤 무음은 그대로 둬야 한다")
    expect(not ep_mod.pause_cap_on({"date": "2026-11-06"}) and ep_mod.pause_cap_on({"date": "2026-11-07"})
           and ep_mod.pause_cap_on({"date": "2026-11-06", "pause_cap": True}) and not ep_mod.pause_cap_on({"date": "2026-11-08", "pause_cap": False})
           and "cap_pauses(" in inspect.getsource(ep_mod.compose)
           and "pause_cap_on(ep)" in inspect.getsource(qa.voice_spans) and "cap_pauses(" in inspect.getsource(qa.voice_spans),
           "쉼 줄이기가 11/07 회차부터 렌더(episode.compose)와 검수 목소리 구간(qa.voice_spans)에 함께 걸리지 않는다")
    hole_db = [-12.0] * 20 + [-32.0] * 8 + [-12.0] * 32          # 3초 줄의 1.0~1.4초가 20dB 꺼짐
    expect(qa.hole_runs(hole_db, [(0.0, 3.0)]) == [(1.0, 0.4, 20.0)]
           and qa.hole_runs([-12.0] * 20 + [-32.0] * 4 + [-12.0] * 36, [(0.0, 3.0)]) == []
           and qa.hole_runs([-12.0] * 20 + [-20.0] * 8 + [-12.0] * 32, [(0.0, 3.0)]) == []
           and qa.hole_runs(hole_db, [(1.5, 3.0)]) == []
           and "voice_holes(video, spans)" in inspect.getsource(qa.main),
           "대사 도중 소리 구멍 검사가 틀린다 — 0.4초 20dB 구멍은 막고, 0.2초·8dB·그 줄 밖은 지나가야 한다")
    two = {"captions": [{"start": 0, "end": 3.15, "html": "<div class='main'>나스닥 폭락</div>"},
                        {"start": 3.15, "end": 6.2, "html": "<div class='main'>버거 돌파</div>"}],
           "voices": [{"text": "나스닥 폭락입니다"}, {"text": "버거 돌파래요"}]}
    over = [(0.1, 3.2), (3.1, 6.0)]
    expect(any("겹친다" in f for f in qa.sync_gaps({**two, "date": "2026-11-07"}, over))
           and not qa.sync_gaps({**two, "date": "2026-11-07"}, [(0.1, 3.05), (3.15, 6.0)])
           and not any("겹친다" in f for f in qa.sync_gaps({**two, "date": "2026-11-06"}, over)),
           "앞 줄 목소리가 다음 줄과 겹치는 것을 11/07 회차부터 막지 않는다")
    import importlib.util
    if shutil.which("ffmpeg") and importlib.util.find_spec("numpy"):   # 렌더하는 세션에만 있다(CI 는 건너뛴다)
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "gap.wav"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=f=440:d=0.5", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono:d=0.54",
                            "-f", "lavfi", "-i", "sine=f=440:d=0.5", "-filter_complex", "[0:a][1:a][2:a]concat=n=3:v=0:a=1", "-ar", "48000", str(src)],
                           check=True)
            dst, cut = ep_mod.cap_pauses(src, Path(tmp) / "cap.wav")
            dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(dst)],
                                       capture_output=True, text=True).stdout)
        expect(0.3 <= cut <= 0.38 and 1.15 <= dur <= 1.25, f"쉼 줄이기 파일이 틀린다 — 0.54초 쉼을 {cut}초 줄여 {dur:.2f}초(1.2초 안팎이어야)")
    ep_src = (ROOT / "automation" / "pilots" / "ai_reel" / "episode.py").read_text(encoding="utf-8")
    expect("xfade=" in ep_src and "fade=t=in:st=0:d=0.25[ve]" not in ep_src, "끝 화면을 검은색에서 밝아지게 넣는다(검은 2프레임) — 겹쳐 넘겨야 한다")
    expect("black_frames(video)" in inspect.getsource(qa.main) and "dark_flashes(video)" in inspect.getsource(qa.main), "검수가 검은 화면을 보지 않는다")
    # 어림 '여'(3만5000여 명·50여 명) — 대사·받아쓰기·화면 모두 단위까지 읽는다(11/01 서울마라톤·올트먼 편: 대사 숫자가 검사에서 빠졌다)
    approx = "3만5000여 명이 참가, 사장단 50여 명과"
    expect(qa.spoken_numbers("삼만 오천여 명이 달립니다") == [(35000.0, "명", "")] and qa.spoken_numbers("35,000여 명") == [(35000.0, "명", "")]
           and qa.spoken_numbers("오십여 명을") == [(50.0, "명", "")] and qa.spoken_numbers("이 여자") == [], "어림 '여'가 붙은 숫자를 못 읽는다")
    # 자막 한 장은 2초 이상(11/03 운영자 "1번 주제 문구가 2번 확확 바뀐다" — 11/04 부터)
    def _caps(day, spans):
        return {"date": day, "captions": [{"start": s, "end": e, "html": f'<div class="main">자막 {k}</div>'} for k, (s, e) in enumerate(spans)]}
    expect(len(qa.short_captions(_caps("2026-11-04", [(0, 1.3), (1.3, 3.0), (3.0, 7.0)]))) == 2
           and not qa.short_captions(_caps("2026-11-04", [(0, 3.2), (3.2, 7.0), (7.0, 9.0)]))
           and not qa.short_captions(_caps("2026-11-03", [(0, 1.3), (1.3, 3.0)]))
           and "short_captions(ep)" in inspect.getsource(qa.main),
           "2초도 안 떠 있는 자막을 검수가 막지 않는다(11/04~)")
    # 싱크·발음(11/04~) — 11/03 운영자 "자막이나 목소리 입힐 때 싱크 맞추고 발음도 똑바로"
    expect([qa.read_ko(x) for x in ("63억 달러", "1만원", "93.7%", "10월 수출", "G마켓", "Z세대", "T+1", "2만개", "[excited] 1억")]
           == ["육십삼억달러", "만원", "구십삼점칠퍼센트", "시월수출", "지마켓", "제트세대", "티플러스일", "이만개", "일억"],
           "받아쓴 숫자·영문을 소리 나는 대로 읽지 못한다")
    expect(qa.heard_ratio("바이낸스, 약 육십삼억 달러가 털렸습니다!", "바이낸스 약 63억 달러가 털렸습니다") == 1.0
           and qa.heard_ratio("일본 제트 세대, 대화에 한국어를 섞어요!", "일본 제2세대 대화에 한국어를 섞어요.") < qa.STEM_MIN
           and qa.heard_ratio("메타 광고 매출, 이십육 퍼센트 뛰었대요!", "메타 광고 매출 26% 띄었대요.") < qa.STEM_MIN
           and qa.heard_ratio("팔로우하면 내일 아침에도 알려 줄게요!", "팔로우 하면 매일 아침에도 알려줄게요") < qa.STEM_MIN
           and qa.heard_ratio("지마켓 유출 고객", "지마켓 유출 고객 바이낸스", recall=True) == 1.0,
           "11/02·11/03 잘못 들린 줄('제2세대'·'띄었대요'·'매일')을 받아쓰기 비교가 못 잡거나, 맞게 들린 줄을 막는다")
    tts_ep = lambda day, *vs: {"date": day, "voices": [dict(v) for v in vs]}   # noqa: E731
    expect(not qa.tts_gaps(tts_ep("2026-11-04", {"text": "바이낸스, 약 63억 달러!", "tts": "[excited] 바이낸스, 약 육십삼억 달러!"},
                                  {"text": "주식 판 돈, 하루 일찍 받게 돼요!"}))
           and qa.tts_gaps(tts_ep("2026-11-04", {"text": "메타 광고 매출, 26% 뛰었대요!"}))
           and qa.tts_gaps(tts_ep("2026-11-04", {"text": "G마켓 만 원", "tts": "G마켓 만 원"}))
           and qa.tts_gaps(tts_ep("2026-11-04", {"text": "약 63억 달러!", "tts": "약 육십사억 달러!"}))
           and qa.tts_gaps(tts_ep("2026-11-04", {"text": "시월 수출", "tts": "시월 수출 — 받아쓰기가 '10월'로 적어"}))
           and not qa.tts_gaps(tts_ep("2026-11-03", {"text": "메타 광고 매출, 26% 뛰었대요!"})),
           "녹음 원고 검사(숫자·영문은 tts 한글 읽기로·숫자 같게·메모 금지, 11/04~)가 틀린다")
    # 11/03 Codex — ① tts '시월·유월'을 월 숫자로 ② tts 가 대사와 다른 말이면 막기 ③ 받아쓰기 '2곳'은 원고 '두 곳'과 같다
    expect(not qa.tts_gaps(tts_ep("2026-11-04", {"text": "6월 수출이 늘었어요.", "tts": "유월 수출이 늘었어요."},
                                  {"text": "10월 수출, 93.7% 늘었대요.", "tts": "시월 수출, 구십삼 점 칠 퍼센트 늘었대요."},
                                  {"text": "숫자는 기사 2곳 이상에서 확인해요!", "tts": "숫자는 기사 두 곳 이상에서 확인해요!"},
                                  {"text": "2030이 알아야 할 것만", "tts": "이공삼공이 알아야 할 것만"},
                                  {"text": "T+1 결제, 2028년부터!", "tts": "티 플러스 원 결제, 이천이십팔 년부터!"},
                                  {"text": "스타벅스 굿즈, 12일까지 9잔이면 돼요!", "tts": "스타벅스 굿즈, 십이 일까지 아홉 잔이면 돼요!"}))   # 11/06 '9잔' = '아홉 잔'
           and qa.tts_gaps(tts_ep("2026-11-04", {"text": "자이 사는 분, 비밀번호부터 바꾸세요.", "tts": "팔로우하면 내일 아침에도 알려 줄게요!"}))
           and qa.tts_gaps(tts_ep("2026-11-04", {"text": "6월 수출", "tts": "칠월 수출"}))
           and qa.heard_ratio("숫자는 기사 두 곳 이상에서 확인해요!", "숫자는 기사 2곳 이상에서 확인해요!") == 1.0
           and qa.heard_ratio("매일 아침 여덟 시 반!", "매일 아침 8시 반!") == 1.0,
           "tts 의 '시월·유월'·고유어 수사('두 곳')·한 자씩 읽기('이공삼공')를 숫자로 못 맞추거나, 대사와 다른 말을 녹음한 tts 가 통과한다")
    expect(qa.spoken_numbers("이 잔 주세요") == [] and qa.spoken_numbers("커피 3잔") == [(3.0, "잔", "")],
           "'잔' 읽기가 틀린다 — 숫자 뒤 '9잔'은 9 잔, '이 잔'(this cup)은 숫자가 아니다")
    b03 = json.loads((ROOT / "automation" / "pilots" / "ai_reel" / "2026-11-03" / "brief.json").read_text(encoding="utf-8"))
    spans03 = [(0.10, 2.69), (3.12, 6.87), (7.06, 10.01), (10.20, 13.41), (14.08, 17.35), (17.60, 20.63)]   # 11/03 녹음을 잰 값
    got03 = qa.sync_gaps({**b03, "date": "2026-11-04"}, spans03)
    caps_ok = [dict(c) for c in b03["captions"]]
    caps_ok[0]["end"], caps_ok[1]["start"] = 3.0, 3.0   # 후킹이 첫 줄 내내 — 1/5 자막은 빼고
    del caps_ok[1]
    caps_ok[3]["end"] = 14.04
    del caps_ok[4]                                      # 4번 장면 자막을 중간에 옮기지 않는다
    fixed = {**b03, "date": "2026-11-04", "captions": caps_ok}
    late = {**fixed, "captions": [dict(c, start=3.6) if i == 1 else c for i, c in enumerate(caps_ok)]}
    short = {**fixed, "captions": [dict(c, end=6.4) if i == 1 else c for i, c in enumerate(caps_ok)]}
    other = {**fixed, "captions": [dict(c, html="<div class='main'>전혀 다른 말</div>") if i == 2 else c for i, c in enumerate(caps_ok)]}
    expect(len(got03) == 2 and all("자막이" in f and "바뀐다" in f for f in got03) and not qa.sync_gaps(fixed, spans03)
           and any("먼저 나온다" in f for f in qa.sync_gaps(late, spans03))
           and any("끝난 뒤" in f for f in qa.sync_gaps(short, spans03))
           and any("같은 낱말이 없다" in f for f in qa.sync_gaps(other, spans03))
           and not qa.sync_gaps(b03, spans03)
           and all(x in inspect.getsource(qa.main) for x in ("tts_gaps(ep)", "sync_gaps(ep, spans)", "stem_heard(", "mix_heard(")),
           "자막↔목소리 맞춤 검사(한 줄에 자막 한 장·같이 뜨기·끝까지 남기·같은 소식, 11/04~)가 틀린다")
    # '달러'는 '달'(개월)이 아니다(11/03 바이낸스 '약 63억 달러' — 단위가 '달'로 읽혀 content 의 '63억 달러'와 못 맞췄다)
    expect(qa.spoken_numbers("바이낸스, 약 육십삼억 달러가 털렸습니다") == [(6300000000.0, "달러", "")]
           and qa.spoken_numbers("약 63억 달러가") == [(6300000000.0, "달러", "")] and qa.spoken_numbers("석 달 만에") == [(3.0, "달", "")],
           "대사의 '달러'를 단위 '달'로 읽는다")
    expect(not qa.check_numbers([("t", "3만5000여 명 · 50여 명")], approx) and qa.check_numbers([("t", "60여 명")], approx),
           "어림 '여'가 붙은 화면 숫자 대조가 틀린다")
    # 등락 부호 — '+7.08%'는 '-7.08%'로 통과 못 하고, '-3.02%'는 '3.02% 내린'으로 통과한다(11/01 Codex)
    signed = "2026-11-01 SK하이닉스 -7.08%, 삼성전자는 3.02% 내린 22만5000원, 생산이 3.0% 늘어"
    expect(qa.check_numbers([("t", "SK하이닉스 +7.08%")], signed) and qa.check_numbers([("t", "+3.02%")], signed)
           and qa.check_numbers([("t", "-3.0%")], signed), "등락 부호가 뒤집힌 숫자가 통과했다")
    expect(not qa.check_numbers([("t", "SK하이닉스 -7.08% · 삼성전자 -3.02% · 생산 +3.0% · 2026-11-01")], signed),
           "content 와 같은 방향의 등락 숫자를 막았다")
    # 끝 화면 문구 — 고정 문구(8시 30분·2030)는 통과, 그 밖의 숫자는 content 와 대조(11/01 Codex)
    expect(not qa.check_numbers([("끝", "내일 아침 8시 30분에 또 만나요! 2030의 아침을 편집합니다")], "3.48%", allow=qa.BRAND_TOKENS)
           and qa.check_numbers([("끝", "코스피 99.99% 하락")], "3.48%", allow=qa.BRAND_TOKENS), "끝 화면 숫자 검수가 틀린다")
    expect('"끝 화면 {k}"' in inspect.getsource(qa.main) or "끝 화면" in inspect.getsource(qa.main), "qa.main 이 끝 화면 문구를 보지 않는다")
    # 목소리 숫자 — 대사 원고(한글 읽기)는 content 와, 들린 숫자는 대사와 같은 값이어야 한다(11/01 Codex: 자막이 맞아도 '일조 칠천억'을 말하면 막는다)
    script = qa.spoken_numbers("외국인이 하루 만에 일조 육천억 원 넘게 팔았대! 프로그램 매도 오 분간 멈춥니다. 삼 점 사팔 퍼센트")
    expect([x[:2] for x in script] == [(1.6e12, "원"), (5.0, "분"), (3.48, "%")], f"한글 숫자 읽기가 틀린다: {script}")
    expect(all(x[:2] in qa.BRAND_SPOKEN for x in qa.spoken_numbers("사이드카가 하루 만에 울렸대, 삼성 이 회사, 내일 아침 여덟 시 반, 네, 한국 대해")),
           f"숫자가 아닌 말을 숫자로 읽었다: {qa.spoken_numbers('사이드카가 하루 만에 울렸대, 삼성 이 회사, 내일 아침 여덟 시 반, 네, 한국 대해')}")
    # 세는 말 단위('대'·'종목' …) — '이만 백삼십칠 대' = content '2만137대', 받아쓰기 '2만 137대'(11/01 BYD 편)
    cars = qa.spoken_numbers("비와이디가 올해 구월까지 이만 백삼십칠 대나 팔렸대!")
    expect([x[:2] for x in cars] == [(9.0, "월"), (20137.0, "대")] and not qa.check_spoken(cars, "BYD가 올해 9월까지 2만 137대나 팔렸대")[1]
           and all(any(qa._num_match(x, c, strict=True) for c in qa.content_values("올해 1~9월 국내에서 2만137대 신규 등록")) for x in cars),
           f"차 대수(대) 읽기가 틀린다: {cars}")
    # 고유어 수사 — '두 종목'을 '세 종목'으로 말하면 막는다, '두 종목'은 content 와 대조(11/01 Codex)
    two = qa.spoken_numbers("내 계좌가 반도체 두 종목에 얼마나 몰렸는지")
    expect([x[:2] for x in two] == [(2.0, "종목")] and qa.check_spoken(two, "내 계좌가 반도체 세 종목에 얼마나")[1]
           and not qa.check_spoken(two, "내 계좌가 반도체 두 종목에 얼마나")[1], f"고유어 수사 검사가 틀린다: {two}")
    expect(any(qa._num_match(two[0], c) for c in qa.content_values("반도체 두 종목에 얼마나 몰려 있는지")), "content 의 '두 종목'을 못 읽는다")
    # 단위가 있으면 content 도 같은 단위 — 날짜(2026-10-31)의 31 로 '31%'가 통과하면 안 된다, 화면의 '세 종목'·'3종목'도 대조(11/01 Codex)
    dated = '{"date": "2026-10-31", "t": "코스피 3.48% 내린 5730.74, 반도체 두 종목"}'
    expect(qa.check_numbers([("t", "코스피 31% 하락")], dated) and qa.check_numbers([("t", "반도체 세 종목")], dated)
           and qa.check_numbers([("t", "반도체 3종목")], dated), "단위 없는 날짜 숫자나 다른 수량으로 화면 숫자가 통과했다")
    expect(not qa.check_numbers([("t", "코스피 3.48% · 5730 · 반도체 두 종목 · 한 번 더 · 2종목 · 숫자는 기사 2곳 이상에서 확인했어요")], dated),
           "content 와 같은 화면 숫자(또는 고정 확인 문구)를 막았다")
    # 백 단위 금액·화면 등락 말 — '3백억원' ↔ '4백억원', '3.48% 상승' ↔ content '3.48% 하락'은 막는다(11/01 Codex)
    expect(qa.check_numbers([("t", "3백억원")], "4백억원") and not qa.check_numbers([("t", "5천6백만 원 · 3백억원")], "5600만원, 300억원"),
           "백 단위 금액 검사가 틀린다")
    expect(qa.check_numbers([("t", "코스피 3.48% 상승")], "코스피 3.48% 하락") and not qa.check_numbers([("t", "코스피 3.48% 빠졌다고?! 장중 5599까지 밀렸어요")], "3.48% 내린 5730.74, 장중 5599.42"),
           "화면의 등락 말을 content 방향과 대조하지 않는다(또는 지수 수준을 잘못 막았다)")
    # 퍼센트 ≠ 퍼센트포인트 — '2.1%' ↔ '2.1%p'는 어느 쪽으로도 통과 못 한다(11/01 Codex)
    expect(qa.check_numbers([("t", "기준금리 2.1%")], "금리 2.1%p 우대") and qa.check_numbers([("t", "2.1%p 우대")], "기준금리 2.1%")
           and not qa.check_numbers([("t", "2.1%p 우대")], "금리 2.1%p 우대"), "퍼센트와 퍼센트포인트를 같은 단위로 봤다")
    expect([x[:2] for x in qa.spoken_numbers("이 점 일 퍼센트 포인트 우대")] == [(2.1, "%p")], "말로 한 퍼센트포인트를 못 읽는다")
    # 천 단위 금액 — '3천억원'은 '4천억원'으로 통과 못 하고 '3000억원'과는 같은 값(11/01 Codex)
    expect(qa.check_numbers([("t", "3천억원")], "4천억원") and not qa.check_numbers([("t", "3천억원 · 5천만원 · 2만5천명")], "3000억원, 5000만원, 2만5000명"),
           "천 단위 금액 검사가 틀린다")
    day = lambda t: [x[:2] for x in qa.spoken_numbers(t)]  # noqa: E731
    expect(day("11월 30일") == [(11.0, "월"), (30.0, "일")] and day("삼십 일 동안") == [(30.0, "일")]
           and day("삼십일 일") == [(31.0, "일")], f"날짜·기간의 '일'을 숫자로 삼켰다: {day('11월 30일')}")
    # 등락 방향 — 목소리가 '플러스'로, 또는 '올랐대'로 뒤집어 말하면 막는다(11/01 Codex)
    _, flip = qa.check_spoken(qa.spoken_numbers("마이너스 칠 점 영팔 퍼센트"), "플러스 칠 점 영팔 퍼센트")
    expect(flip, "목소리가 등락 부호를 뒤집어 말해도 통과했다")
    cv7 = qa.content_values("SK하이닉스 -7.08%, 삼성전자는 3.02% 내린")
    expect(not any(qa._num_match(x, c) for x in qa.spoken_numbers("칠 점 영팔 퍼센트 올랐대") for c in cv7)
           and all(any(qa._num_match(x, c) for c in cv7) for x in qa.spoken_numbers("칠 점 영팔 퍼센트 빠졌대, 삼 점 영이 퍼센트 내렸어")),
           "대사의 등락 방향을 content 와 대조하지 않는다")
    _, bad_day = qa.check_spoken(qa.spoken_numbers("삼십 일 동안"), "31일 동안")
    expect(bad_day, "30일을 31일로 말해도 통과했다")
    cv = qa.content_values("외국인이 1조6000억원 넘게 팔았고 5분간 멈췄다, 3.48% 내린")
    expect(all(any(qa._num_match(x, c) for c in cv) for x in script), "content 와 같은 대사 숫자를 막았다")
    expect(not any(qa._num_match((1.7e12, "원"), c) for c in cv), "content 에 없는 대사 금액이 통과했다")
    _, bad = qa.check_spoken(script, "외국인이 하루 만에 1조 7천억 원 넘게 팔았대 프로그램 매도 5분간 멈춥니다 3.48%")
    expect(any("1.7e+12" in b for b in bad) and any("1.6e+12" in b for b in bad), f"목소리가 틀린 금액을 말해도 통과했다: {bad}")
    _, ok = qa.check_spoken(script, "외국인이 하루 만에 1조 6천억 원 넘게 팔았대 프로그램 매도 5분간 멈춥니다 3.48% 내일 아침 8시 반에")
    expect(not ok, f"맞게 말한 숫자를 막았다: {ok}")
    # 받아쓰기가 숫자로 적은 대사 낱말(11/04 '일주일에 삼백팔십오 건' → '1주일에 385건')은 숫자가 아니다 — 대사에 그 낱말이 그대로 있을 때만
    week = qa.spoken_numbers("헤드스파 예약, 일주일에 385건!")
    tts = "헤드스파 예약, 일주일에 삼백팔십오 건!"
    expect(not qa.check_spoken(week, "헤드스파 예약 1주일에 385건", script=tts)[1], "'일주일'을 '1주일'로 받아 적은 것을 다른 숫자로 막았다")
    expect(qa.check_spoken(week, "헤드스파 예약 1주일에 385건")[1], "대사 원고 없이도 '1'을 낱말로 넘겼다(예전 동작이 바뀌었다)")
    expect(qa.check_spoken(week, "헤드스파 예약 2주일에 385건", script=tts)[1], "'일주일'을 '이주일'로 말해도 통과했다")
    expect(qa.check_spoken(week, "헤드스파 예약 1주일에 386건", script=tts)[1], "385건을 386건으로 말해도 통과했다")
    expect(qa.check_spoken([], "결승은 2개 도시에서", script="결승은 미시간이 개최해요")[1], "낱말 머리가 아닌 글자('미시간이 개최'의 '이개')로 '2개'를 넘겼다")
    # 만화 10장 순서 — 사전순이면 c10(끝 장)이 두 번째로 올라간다
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        (folder / pi.COMIC_DIR).mkdir()
        for i in range(1, 11):
            (folder / pi.COMIC_DIR / f"c{i}.jpg").write_bytes(b"x")
        (folder / "comic_caption.txt").write_text("만화 캡션", encoding="utf-8")
        g = G(True)
        saved_wp, saved_pub = pi.wait_public, pi.publish
        pi.wait_public = lambda urls, **k: None
        pi.publish = lambda g_, uid, cid, what, tries=6: "m1"
        try:
            pi.post_comic(g, "u", "2026-11-01", folder, "https://x", False)
        finally:
            pi.wait_public, pi.publish = saved_wp, saved_pub
        order = [c["image_url"].rsplit("/", 1)[1] for c in g.calls if c.get("is_carousel_item")]
        expect(order == [f"c{i}.jpg" for i in range(1, 11)], f"만화 순서가 틀렸다: {order}")

    # 만화·AI 릴스 성과는 각자 게시 시각에서 24시간 뒤 스냅숏으로 잰다(캐러셀 시각으로 고르면 늦게 올린 만화가 빠진다 — 11/01 Codex)
    import collect_metrics as cm
    with tempfile.TemporaryDirectory() as tmp:
        auto = Path(tmp)
        (auto / "ig_posted").mkdir()
        (auto / "metrics" / "daily").mkdir(parents=True)
        (auto / "ig_posted" / "2026-11-01.json").write_text(json.dumps(
            {"carousel": {"at": "2026-11-01T08:30:00+09:00"}, "comic": {"at": "2026-11-02T10:00:00+09:00"}}), encoding="utf-8")
        snaps = [("2026-11-02T21:00:00+09:00", 1), ("2026-11-03T21:00:00+09:00", 2)]
        for at, n in snaps:
            (auto / "metrics" / "daily" / f"{at[:10]}.json").write_text(json.dumps(
                {"collected_at": at, "instagram": {"posts": {"2026-11-01": {"reach": 100 * n, "comic": {"reach": 10 * n}}}}}), encoding="utf-8")
        saved = cm.AUTOMATION, cm.METRICS
        cm.AUTOMATION, cm.METRICS = auto, auto / "metrics"
        try:
            main_row = cm._at_age("2026-11-01", {})
            comic_row = cm._at_age("2026-11-01", {}, kind="comic")
            none_row = cm._at_age("2026-11-01", {}, kind="reel_ai")
        finally:
            cm.AUTOMATION, cm.METRICS = saved
        expect(main_row.get("reach") == 100 and comic_row == {"reach": 20} and none_row == {},
               f"만화 24시간 스냅숏을 캐러셀 시각으로 골랐다({main_row}, {comic_row}, {none_row})")
    return "reel_ai.mp4 → 형식 ai · 캡션 따로 · 스토리 영상 · AI 정보 라벨 · H 극장 만화 캐러셀 · 숫자 검수 · 각자 24시간 성과"


def t_competitors_ig():
    """경쟁 매체 인스타(2026-11-01 운영자 '경쟁사도 못 보면 개선에 영향'): 공식 비즈니스 탐색 API 만 쓰고, 토큰이 없으면 네트워크 없이
    0 으로 끝나며, 응답에서 최근 14일 통계(게시 수·평균·참여율·형식·시각·대표 게시물)를 바르게 계산하고, 실패 계정은 따로 적는다."""
    import competitors_ig as ci
    accounts, limit, version = ci.settings()
    handles = [a["handle"] for a in accounts]
    expect(len(handles) == len(set(handles)) and sum(a["self"] for a in accounts) == 1, f"대상 계정이 겹치거나 우리 계정이 하나가 아니다: {handles}")
    expect(ci.fields_for("newneek.official", 25) == "business_discovery.username(newneek.official){username,name,profile_picture_url,"
           "followers_count,follows_count,media_count,media.limit(25){" + ci.MEDIA_FIELDS + "}}", "비즈니스 탐색 필드 식이 틀렸다")
    expect(ci.GRAPH == "https://graph.facebook.com", "비즈니스 탐색은 페이스북 로그인 방식(graph.facebook.com)에만 있다")
    now = ci.parse_time("2026-11-01T03:00:00+0000")
    media = {"data": [
        {"timestamp": "2026-10-31T23:30:00+0000", "like_count": 120, "comments_count": 8, "media_type": "CAROUSEL_ALBUM",
         "media_product_type": "FEED", "permalink": "https://www.instagram.com/p/A/", "caption": "\n첫 줄 제목\n둘째 줄"},
        {"timestamp": "2026-10-30T09:10:00+0000", "like_count": 300, "comments_count": 20, "media_type": "VIDEO",
         "media_product_type": "REELS", "permalink": "https://www.instagram.com/reel/B/", "caption": "릴스"},
        {"timestamp": "2026-10-29T23:40:00+0000", "comments_count": 2, "media_type": "IMAGE", "media_product_type": "FEED"},
        {"timestamp": "2026-10-01T00:00:00+0000", "like_count": 999, "comments_count": 99, "media_type": "IMAGE"}]}
    rec = ci.summarize({"username": "x", "followers_count": 10000, "media_count": 500, "media": media}, now)
    s = rec["stats"]
    expect(s["posts"] == 3 and s["avg_likes"] == 210.0 and s["avg_comments"] == 10.0, f"14일 통계: {s}")
    expect(s["engagement_pct"] == 2.2, f"참여율(게시물당 (좋아요+댓글)÷팔로워): {s['engagement_pct']}")
    expect(s["formats"] == {"캐러셀": 33, "릴스": 33, "사진": 33} and s["top_hour_kst"] == 8, f"형식·시각(KST): {s['formats']} {s['top_hour_kst']}")
    expect(s["top_post"]["permalink"].endswith("/reel/B/") and rec["posts"][0]["caption"] == "첫 줄 제목", f"대표 게시물·캡션: {s['top_post']}")
    expect(all("_t" not in p for p in rec["posts"]), "저장 기록에 내부 시각 값이 남았다")

    def fake(handle):
        if handle == "uppity.official":
            raise RuntimeError(ci.describe_error({"code": 190, "message": "expired"}))
        return {"username": handle, "followers_count": 100, "media": media}
    rows = ci.collect([{"handle": "edit.h.kr", "name": "우리", "self": True}, {"handle": "uppity.official", "name": "어피티", "self": False}],
                      fake, now)
    expect([r["ok"] for r in rows] == [True, False] and "토큰 만료" in rows[1]["error"], f"실패 계정 처리: {rows}")
    md = ci.render(rows, {"edit.h.kr": 90}, "2026-10-25", now)
    expect("| **우리** (@edit.h.kr) | 100 | +10 | 3 |" in md and "못 가져온 계정" in md, "요약표(우리 줄·지난 대비·실패 계정)")
    groups = [dict(rows[0], group="경제·뉴스 브리핑"), dict(rows[0], handle="careet.official", name="캐릿", self=False, group="트렌드 미디어")]
    md2 = ci.render(groups, {}, None, now)
    expect(md2.index("### 경제·뉴스 브리핑") < md2.index("### 트렌드 미디어") and md2.count("| 매체 |") == 2, "무리(group)마다 표가 나뉘지 않는다")
    expect(len({a["group"] for a in accounts}) >= 2 and all(a["group"] for a in accounts), "config 계정마다 무리(group)가 있어야 한다")
    saved = ci.fetch, dict(os.environ)
    ci.fetch = lambda *a, **k: (_ for _ in ()).throw(AssertionError("토큰 없이 네트워크를 썼다"))
    try:
        os.environ.pop("IG_FB_TOKEN", None)
        os.environ.pop("IG_FB_USER_ID", None)
        with contextlib.redirect_stdout(io.StringIO()):
            expect(ci.main([]) == 0, "토큰이 없을 때 0 으로 끝나지 않았다")
    finally:
        ci.fetch = saved[0]
        os.environ.clear()
        os.environ.update(saved[1])
    wf = (ROOT / ".github" / "workflows" / "competitors-ig.yml").read_text(encoding="utf-8")
    expect("secrets.IG_FB_TOKEN" in wf and "secrets.IG_ACCESS_TOKEN" not in wf, "경쟁 매체 워크플로가 게시 토큰을 쓴다")
    return f"{len(accounts)}개 계정 · API {version}"


def t_competitors_web():
    """경쟁 매체 웹 추적기(2026-11-01 운영자 '모든 걸 알아서'·'지금 바로 웹 추적기'): 네트워크 없이 — RSS·Atom·글 목록·사이트맵을 읽고,
    robots 가 막은 매체는 그 매체만 건너뛰며, 우리와 겹친 말·여러 매체가 다룬 말을 고르고, 말끝(같지·영원할)·불용어·숫자를 뺀다."""
    import urllib.robotparser
    import competitors_web as cw
    sources = cw.settings()
    expect(len(sources) >= 3 and len({s["name"] for s in sources}) == len(sources), f"웹 추적 대상: {[s['name'] for s in sources]}")
    rss = ('<?xml version="1.0"?><rss version="2.0"><channel>'
           '<item><title>SK하이닉스 100조 주주환원</title><link>https://a.example/1</link><pubDate>Thu, 30 Oct 2026 09:00:00 +0900</pubDate></item>'
           '<item><title>오래된 글</title><link>https://a.example/0</link><pubDate>Mon, 01 Sep 2026 09:00:00 +0900</pubDate></item></channel></rss>')
    items = cw.parse_rss(rss)
    expect(items[0] == {"title": "SK하이닉스 100조 주주환원", "link": "https://a.example/1", "date": "2026-10-30"}, f"RSS: {items}")
    atom = ('<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>코스피 급락</title><link href="https://b.example/x"/>'
            '<updated>2026-10-31T01:00:00Z</updated></entry></feed>')
    expect(cw.parse_rss(atom) == [{"title": "코스피 급락", "link": "https://b.example/x", "date": "2026-10-31"}], "Atom")
    page = ('<a href="/2017" class="x"><b>요즘 뜨는 밈</b> 야르 vs 쌰갈</a><a href="/about">소개 페이지</a>'
            '<a href="https://maily.so/t/posts/abcdef1"><h3>[#646] 나이별 반응</h3><p>26.10.30 (금) 용례</p></a>')
    links = cw.parse_links(page, r"^/\d{3,5}$|/posts/[a-z0-9]{6,}$", "https://www.careet.net/")
    expect([x["link"] for x in links] == ["https://www.careet.net/2017", "https://maily.so/t/posts/abcdef1"]
           and links[0]["date"] is None and links[1]["date"] == "2026-10-30", f"글 목록: {links}")
    sm = ("<urlset><url><loc>https://n.example/@newneek/article/2</loc><lastmod>2026-10-30T01:00:00Z</lastmod></url>"
          "<url><loc>https://n.example/@other/article/3</loc><lastmod>2026-10-31T01:00:00Z</lastmod></url>"
          "<url><loc>https://n.example/@newneek/article/1</loc><lastmod>2026-10-01T01:00:00Z</lastmod></url></urlset>")
    expect(cw.parse_sitemap(sm, r"@newneek/article/\d+$", 1) == [("https://n.example/@newneek/article/2", "2026-10-30")], "사이트맵")
    kw = cw.keywords("나 왜 유행 밈 소개가 영원할 거 같지? SK하이닉스가 꺼낸 100조 원의 주주환원 카드")
    expect({"유행", "sk하이닉스", "주주환원", "카드", "소개"} <= kw and not ({"영원할", "같지", "100조"} & kw), f"말 고르기: {kw}")
    results = [{"name": "A", "ok": True, "items": [{"title": "금리 인하 SK하이닉스", "link": "1", "date": "2026-10-30", "recent": True}]},
               {"name": "B", "ok": True, "items": [{"title": "금리 동결 영향", "link": "2", "date": None, "recent": True},
                                                   {"title": "지난 금리 이야기", "link": "3", "date": None, "recent": False}]},
               {"name": "C", "ok": False, "items": [], "error": "x"}]
    gaps = cw.compare(results, {"sk하이닉스", "코스피"})
    expect(gaps == [("금리", ["A", "B"])] and results[0]["items"][0]["overlap"] == ["sk하이닉스"], f"겹친 말·놓친 말: {gaps}")

    def fake(url):
        if "blocked" in url:
            raise RuntimeError("사이트가 자동 접속을 막음(robots.txt 403): " + url)
        return rss
    now = cw.parse_when("2026-11-01T12:00:00+09:00")
    res = cw.collect([{"name": "막힘", "kind": "rss", "url": "https://blocked.example/feed"},
                      {"name": "열림", "kind": "rss", "url": "https://open.example/feed"},
                      {"name": "목록", "kind": "links", "url": "https://www.careet.net/", "match": r"^/\d{3,5}$"}],
                     lambda u: page if "careet" in u else fake(u), now, {"목록": {"https://www.careet.net/2017"}})
    expect(not res[0]["ok"] and [i["recent"] for i in res[1]["items"]] == [True, False]
           and [i["recent"] for i in res[2]["items"]] == [False], f"robots 막힘·7일 창·날짜 없는 목록의 새 글: {res}")
    rp = urllib.robotparser.RobotFileParser()
    rp.parse(["User-agent: *", "Disallow: /"])
    f = cw.Fetcher(delay=0)
    f.robots["https://x.example"] = rp
    try:
        f.get("https://x.example/a")
        expect(False, "robots.txt 가 막은 주소를 열었다")
    except RuntimeError as e:
        expect("robots" in str(e), f"robots 거부 문구: {e}")
    with contextlib.redirect_stdout(io.StringIO()):
        expect(cw.main(["--dry-run"], fetch=lambda u: rss) == 0, "시험 실행이 0 으로 끝나지 않았다")
    wf = (ROOT / ".github" / "workflows" / "competitors-web.yml").read_text(encoding="utf-8")
    expect("competitors_web.py" in wf and "secrets." not in wf, "웹 추적 워크플로가 없거나 비밀값을 쓴다")
    return f"{len(sources)}곳 · robots 지킴"


def t_comment_dm():
    """댓글 키워드 → 구독 링크 DM(2026-11-02): 짧은 키워드 댓글만 잡고, 우리 댓글·7일 지난 댓글은 건너뛰고, DM(비공개 답장)+공개 답글을
    한 번만 하고, 같은 사람은 공개 답글만, DM 권한이 없으면 공개 답글로 안내하고, 댓글 사정 오류·호출 한도를 가르고,
    기록에는 해시·숫자만 남기고(아이디·이름·댓글 글 없음), 토큰이 없으면 네트워크 없이 0. 캡션 DM 약속은 켠 날짜 이후 호에만."""
    import datetime as _dt
    import comment_dm as cd
    from edith import site as _site
    s = cd.settings()
    expect({"에디트", "구독"} <= set(s["keywords"]), f"키워드: {s['keywords']}")
    url = cd.subscribe_url(s)
    expect(url.endswith("/subscribe.html?ref=ig-dm") and re.fullmatch(r"[a-z0-9_-]{1,14}", s["link_ref"]), f"구독 링크·경로 이름: {url}")
    for t, want in [("에디트!!", True), ("구 독 해요🙏", True), ("에디트", True), ("좋아요", False), ("", False),
                    ("에디트 매일 아침 잘 보고 있어요 오늘 내용 특히 좋았습니다", False)]:
        expect(cd.matches(t, s) is want, f"키워드 판정 {t!r} → {not want}")
    text = cd.dm_text(s, "2026-11-02")
    expect(url in text and "8시 30분" in text and "무료" in text and "수신 거부" in text, f"DM 글: {text}")
    KST = _dt.timezone(_dt.timedelta(hours=9))
    now = _dt.datetime(2026, 11, 2, 12, 0, tzinfo=KST)
    me = {"id": "900", "username": "edit.h.kr"}

    def ts(days_ago):
        return (now - _dt.timedelta(days=days_ago)).astimezone(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+0000")

    comments = {"m1": [
        {"id": "c-own", "text": "에디트", "timestamp": ts(1), "from": {"id": "900", "username": "edit.h.kr"}},
        {"id": "c-a1", "text": "에디트!", "timestamp": ts(1), "from": {"id": "u-a", "username": "user_a"}},
        {"id": "c-a2", "text": "구독", "timestamp": ts(0.5), "from": {"id": "u-a", "username": "user_a"}},
        {"id": "c-old", "text": "에디트", "timestamp": ts(8), "from": {"id": "u-b", "username": "user_b"}},
        {"id": "c-chat", "text": "오늘 카드 좋네요", "timestamp": ts(1), "from": {"id": "u-c", "username": "user_c"}},
        {"id": "c-d", "text": "구독이요", "timestamp": ts(0.2), "from": {"id": "u-d", "username": "user_d"},
         "replies": {"data": [{"id": "r1", "from": {"id": "900", "username": "edit.h.kr"}}]}}]}

    class Fake:
        def __init__(self, dm_error=None):
            self.calls, self.dm_error = [], dm_error

        def call(self, method, path, **params):
            self.calls.append((method, path, params))
            if path == "900/media":
                return {"data": [{"id": "m1", "timestamp": ts(1), "comments_count": 6},
                                 {"id": "m-old", "timestamp": ts(15), "comments_count": 3}]}
            if path.endswith("/comments"):
                expect(path == "m1/comments", f"창 밖 게시물 댓글을 읽었다: {path}")
                return {"data": comments["m1"]}
            if path == "900/messages":
                if self.dm_error:
                    raise self.dm_error
                return {"recipient_id": "x", "message_id": "y"}
            if path.endswith("/replies"):
                return {"id": "r"}
            raise AssertionError(f"모르는 호출 {method} {path}")

    def run(fake, st):
        with contextlib.redirect_stdout(io.StringIO()):
            return cd.process(fake, me, now, st, s, log=lambda *_: None)

    st = cd.load_state(Path("/nonexistent/state.json"))
    f = Fake()
    expect(run(f, st) == 3, "키워드 댓글 3건(a1·a2·d)을 처리해야 한다")
    dms = [c for c in f.calls if c[1] == "900/messages"]
    expect([json.loads(c[2]["recipient"])["comment_id"] for c in dms] == ["c-a1", "c-d"], f"DM 대상: {dms}")
    expect(url in json.loads(dms[0][2]["message"])["text"], "DM 에 구독 링크가 없다")
    replies = [(c[1], c[2]["message"]) for c in f.calls if c[1].endswith("/replies")]
    expect([r[0] for r in replies] == ["c-a1/replies", "c-a2/replies"], f"공개 답글(우리 답글 있는 c-d 는 건너뜀): {replies}")
    expect(replies[0][1] in cd.REPLY_SENT and replies[1][1] in cd.REPLY_REPEAT, f"답글 문구: {replies}")
    expect(st["dm"]["ok"] is True and st["daily"]["2026-11-02"] == {"matched": 3, "dm": 2, "reply": 2, "failed": 0}, f"기록: {st['dm']} {st['daily']}")
    dump = json.dumps(st, ensure_ascii=False)
    expect(not any(x in dump for x in ("user_a", "u-a", "c-a1", "에디트", "구독")), "기록에 아이디·이름·댓글 글이 남았다")
    f2 = Fake()
    expect(run(f2, st) == 0 and not [c for c in f2.calls if c[0] == "POST"], "같은 댓글을 두 번 처리했다")

    st = cd.load_state(Path("/nonexistent/state.json"))
    f = Fake(cd.ApiError(403, 10, None, "Application does not have permission for this action"))
    run(f, st)
    expect(len([c for c in f.calls if c[1] == "900/messages"]) == 1, "권한이 없으면 DM 을 한 번만 시도해야 한다")
    fb = [c[2]["message"] for c in f.calls if c[1].endswith("/replies")]
    expect(len(fb) == 2 and all(m in cd.REPLY_FALLBACK for m in fb), f"권한 없을 때 공개 답글 안내: {fb}")
    expect(st["dm"]["ok"] is False and not st["users"], f"권한 없음 기록: {st['dm']}")

    st = cd.load_state(Path("/nonexistent/state.json"))
    f = Fake(cd.ApiError(400, 10, 2534022, "outside of allowed window"))
    run(f, st)
    expect(st["dm"]["ok"] is None and st["daily"]["2026-11-02"]["failed"] == 3, f"댓글 사정 오류를 권한 문제로 봤다: {st['dm']} {st['daily']}")
    expect(cd.kind_of(cd.ApiError(400, 4)) == "retry" and cd.kind_of(cd.ApiError(400, 190)) == "token"
           and cd.kind_of(cd.ApiError("접속 실패", transient=True)) == "retry" and cd.kind_of(cd.ApiError(503)) == "retry"
           and cd.kind_of(cd.ApiError(500, 2)) == "retry" and cd.kind_of(cd.ApiError(400, 100, 2018001)) == "comment", "오류 종류")
    st = cd.load_state(Path("/nonexistent/state.json"))
    run(Fake(cd.ApiError("접속 실패", message="DNS", transient=True)), st)
    expect(not st["handled"] and "2026-11-02" not in st["daily"], "접속 실패면 처리 표시 없이 다음 실행으로 넘겨야 한다(Codex 리뷰)")
    st = cd.load_state(Path("/nonexistent/state.json"))
    run(Fake(cd.ApiError(400, 4, None, "limit")), st)
    expect(not st["handled"] and "2026-11-02" not in st["daily"], "호출 한도면 처리 표시 없이 다음 실행으로 넘겨야 한다")

    class ReplyLimited(Fake):       # DM 권한 없음 + 공개 답글도 호출 한도 → 다음 실행에 다시(Codex 리뷰)
        def call(self, method, path, **params):
            if path.endswith("/replies") and self.dm_error:
                self.calls.append((method, path, params))
                raise cd.ApiError(400, 4, None, "limit")
            return super().call(method, path, **params)
    st = cd.load_state(Path("/nonexistent/state.json"))
    run(ReplyLimited(cd.ApiError(403, 10, None, "no permission")), st)
    expect(not st["handled"] and "2026-11-02" not in st["daily"], f"공개 답글이 호출 한도면 다음 실행에 다시 해야 한다: {st}")
    f = Fake()
    run(f, st)
    expect(len([c for c in f.calls if c[0] == "POST"]) == 4, "호출 한도 뒤 다음 실행에서 처리하지 않았다")

    class SentThenLimited(Fake):    # DM 은 나갔는데 공개 답글이 호출 한도 → DM 은 기록(두 번 보내지 않게)
        def call(self, method, path, **params):
            if path.endswith("/replies"):
                raise cd.ApiError(400, 4, None, "limit")
            return super().call(method, path, **params)
    st = cd.load_state(Path("/nonexistent/state.json"))
    run(SentThenLimited(), st)
    expect([v["dm"] for v in st["handled"].values()] == [True] and st["daily"]["2026-11-02"]["dm"] == 1, f"보낸 DM 기록: {st}")

    cpages = {f"https://next/c{i}": {"data": [{"id": f"x{i}-{j}", "text": "좋아요", "timestamp": ts(1), "from": {"id": f"v{i}{j}"}}
                                          for j in range(50)], "paging": {"next": f"https://next/c{i + 1}"}} for i in range(1, 5)}
    cpages["https://next/c5"] = {"data": [{"id": "late", "text": "에디트", "timestamp": ts(0.1), "from": {"id": "u-late"}}]}

    class ManyComments(Fake):       # 앞 네 장은 일반 댓글, 다섯째 장에 키워드 댓글(Codex 리뷰)
        def call(self, method, path, **params):
            if path == "m1/comments":
                self.calls.append((method, path, params))
                return {"data": [], "paging": {"next": "https://next/c1"}}
            if path in cpages:
                return cpages[path]
            return super().call(method, path, **params)
    f = ManyComments()
    run(f, cd.load_state(Path("/nonexistent/state.json")))
    expect([json.loads(c[2]["recipient"])["comment_id"] for c in f.calls if c[1] == "900/messages"] == ["late"],
           "다섯째 장 이후 키워드 댓글을 못 읽었다")

    pages = {"900/media": {"data": [{"id": f"p{i}", "timestamp": ts(i * 0.4), "comments_count": 1} for i in range(30)],
                           "paging": {"next": "https://graph.instagram.com/v23.0/next1"}},
             "https://graph.instagram.com/v23.0/next1": {"data": [{"id": "p30", "timestamp": ts(13), "comments_count": 2},
                                                                  {"id": "p31", "timestamp": ts(15), "comments_count": 2}],
                                                         "paging": {"next": "https://graph.instagram.com/v23.0/next2"}}}

    class Paged:
        def call(self, method, path, **params):
            expect(path in pages, f"창 밖까지 다음 장을 읽었다: {path}")
            return pages[path]
    ids = [m["id"] for m in cd.recent_media(Paged(), "900", now, s)]
    expect(len(ids) == 31 and ids[-1] == "p30", f"14일 안 게시물을 다음 장까지 모두 읽어야 한다: {len(ids)} {ids[-2:]}")

    st = {"handled": {"a": {"d": "2026-10-20"}, "b": {"d": "2026-11-01"}}, "users": {"x": "2026-09-01", "y": "2026-10-30"},
          "dm": {"ok": None}, "daily": {"2026-08-01": {}, "2026-11-01": {}}}
    cd.prune(st, _dt.date(2026, 11, 2), s)
    expect(list(st["handled"]) == ["b"] and list(st["users"]) == ["y"] and list(st["daily"]) == ["2026-11-01"], f"오래된 기록 정리: {st}")

    saved = cd.Api.call, dict(os.environ)
    cd.Api.call = lambda *a, **k: (_ for _ in ()).throw(AssertionError("토큰 없이 네트워크를 썼다"))
    try:
        os.environ.pop("IG_ACCESS_TOKEN", None)
        with contextlib.redirect_stdout(io.StringIO()):
            expect(cd.main([]) == 0, "토큰이 없을 때 0 으로 끝나지 않았다")
    finally:
        cd.Api.call = saved[0]
        os.environ.clear()
        os.environ.update(saved[1])

    cfg = load_config()
    expect(cfg["instagram"].get("dm_auto_reply_from") is None or _site.dm_line(cfg["instagram"]["dm_auto_reply_from"]),
           "dm_auto_reply_from 날짜 호에 DM 약속이 없다")
    real = _site.load_config
    try:
        _site.load_config = lambda: {**cfg, "instagram": {**cfg["instagram"], "dm_auto_reply_from": "2026-11-05"}}
        expect(_site.dm_line("2026-11-04") is None and "'에디트'" in (_site.dm_line("2026-11-05") or "")
               and _site.dm_line("2026-11-06-weekly", short=True), "DM 약속은 켠 날짜 이후 호에만")
        _site.load_config = lambda: {**cfg, "instagram": {**cfg["instagram"], "dm_auto_reply_from": None}}
        expect(_site.dm_line("2026-12-01") is None, "날짜가 없으면 약속하지 않는다")
        _site.load_config = lambda: {**cfg, "instagram": {**cfg["instagram"], "dm_auto_reply_from": "2026-11-05",
                                                          "dm_auto_reply_until": "2026-11-20"}}
        expect(_site.dm_line("2026-11-20") and _site.dm_line("2026-11-21") is None, "끈 날짜(until) 뒤 호에는 약속하지 않는다")
    finally:
        _site.load_config = real
    igc = cfg["instagram"]
    expect(igc.get("comment_dm", {}).get("enabled", True) or not igc.get("dm_auto_reply_from") or igc.get("dm_auto_reply_until"),
           "자동 답장을 껐는데(comment_dm.enabled=false) DM 약속이 끝나지 않는다 — dm_auto_reply_until 에 마지막 날짜를 넣을 것")
    wf = (ROOT / ".github" / "workflows" / "comment-dm.yml").read_text(encoding="utf-8")
    expect("secrets.IG_ACCESS_TOKEN" in wf and "git add automation/comment_dm" in wf and "if: always()" in wf, "댓글 DM 워크플로")
    import collect_metrics as _cm
    expect("ig-dm" in Path(_cm.__file__).read_text(encoding="utf-8"), "성과표 구독 경로 이름에 ig-dm 이 없다")
    # probe 진단(2026-11-02 '댓글 있는 게시물 16개·읽은 댓글 0개') — 게시물마다 댓글 수·두 가지 읽기 개수·응답 칸 이름만, 아이디는 기록에 없다
    class Blind:
        def call(self, method, path, **params):
            if path == "900/media":
                return {"data": [{"id": "m1", "timestamp": ts(1), "comments_count": 4, "media_product_type": "REELS"}]}
            if path == "m1/comments":
                return {"data": []}
            if path == "m1":
                return {"id": "m1", "comments_count": 4}
            if path == "900/conversations":
                return {"data": []}
            raise AssertionError(f"probe 가 모르는 호출 {method} {path}")
    st_p = cd.load_state(Path("/nonexistent/state.json"))
    logs = []
    acct = cd.account({"id": "app-scoped-1", "user_id": "900", "username": "edit.h.kr"})   # main() 이 GET me 응답을 바꾸는 그대로(Codex 리뷰)
    expect(acct["id"] == "900" and acct["raw_id"] == "app-scoped-1" and acct["user_id"] == "900"
           and cd.account({"id": "900", "username": "x"})["id"] == "900", f"GET me 응답 정리가 틀린다: {acct}")
    import inspect as _inspect
    expect("me = account(me)" in _inspect.getsource(cd.main), "main() 이 account() 로 계정 정보를 만들지 않는다")
    cd.probe(Blind(), acct, now, st_p, s, log=logs.append)
    pr = st_p["probe"]
    expect(pr["blind"] and pr["comments"] == 0 and pr["rows"] == [{"type": "REELS", "count": 4, "read": 0, "keys": ["data"],
                                                                   "alt": 0, "alt_keys": ["comments_count"]}]
           and pr["messages"] == {"ok": True} and pr["ids"] == {"has_user_id": True, "same": False}, f"probe 진단 기록이 틀린다: {pr}")
    expect("m1" not in json.dumps(pr) and any("하나도 못 읽는다" in x for x in logs), "probe 기록에 게시물 아이디가 남았거나 원인 안내가 없다")
    return f"키워드 {', '.join(s['keywords'])} · 링크 ref={s['link_ref']}"


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
    check("봇 커밋 이름은 KST 날짜", t_commit_dates)
    check("안장출근길 비교(회고 잣대)", t_compare_anjang)
    check("평일 안장 글 기다리기(07:55 전 fallback 빌드 막음)", t_anjang_wait)
    check("카드 마크·큰 숫자 단위(11/04~)", t_card_marks)
    check("카드 '그래서 나는?' 이어짐(11/04~)", t_card_takeaway_link)
    check("카드 '그래서 나는?' 제목 소식 맞춤·이어 읽기(11/06~)", t_card_takeaway_topic)
    check("발송 시각(지난 호는 08:00)", t_send_time)
    check("짧게 읽는 소식 점검", t_brief_check)
    check("새 호 막는 점검(짧은 소식 개수·H PICK 중복)", t_strict_content)
    check("월요일 투표 쉼(2026-10-19~)", t_poll_paused)
    check("원문(보도자료)·H PICK 원문 점검(2026-10-23~)", t_releases)
    check("숫자 2곳 대조(2026-11-05 호~, 한 곳뿐 막음)", t_twosource)
    check("큰 소식·놓침 비교·출처 품질(2026-10-23~)", t_headlines)
    check("AGENTS.md(GPT 인수인계)가 가리키는 파일", t_agents_doc)
    check("Codex 자동 대체(Claude 가 멈춘 날)", t_codex_fallback)
    check("같은 회사·주제 두 칸(2026-10-19~)", t_repeat_check)
    check("오늘 챙길 것", t_todo_box)
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
    check("3:4 카드·팔로우 카드(템플릿 ver.3)", t_card_ratio)
    check("검색 알림(IndexNow)", t_indexnow)
    check("주간 특집 저장각(E13)", t_weekly_save)
    check("데일리 저장각(체크리스트·차트)", t_save_cards)
    check("딥다이브 카드(「H의 장부」 연재 날)", t_dive_cards)
    check("5가지 웹툰(카드 글 그대로·요약 장)", t_webtoon)
    check("웹툰만 검수(qa --comic — 11월 홀수 날)", t_comic_only)
    check("마스코트(안경 동그라미 H)", t_mascot)
    check("첫 화면 구독·사이트 그림(index.html)", t_home)
    check("문구·마크 2판(2030 대표 한 줄·마스코트 얼굴)", t_brand_v2)
    check("AI 영상 릴스·스토리(reel_ai.mp4)", t_ai_reel)
    check("캐러셀 이미지(마스코트 H)", t_mascot_cards)
    check("구독자 1만 목표 줄", t_goal_line)
    check("경쟁 매체 인스타(비즈니스 탐색)", t_competitors_ig)
    check("경쟁 매체 웹(토큰 없이·robots 지킴)", t_competitors_web)
    check("댓글 키워드 → 구독 링크 DM", t_comment_dm)
    if not args.quick:
        check("딥다이브 카드 글자 한도 렌더링(넘침 없음)", t_dive_render)
        check("웹툰 두 컷 장 글자 한도 렌더링(넘침 없음·넘침 잡음)", t_webtoon_render)
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
