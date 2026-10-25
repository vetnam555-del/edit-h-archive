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
    return None


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
    expect(all(cf.allowed(x, pats) for x in (f"{d}.html", f"content/{d}.json", f"instagram/{d}/01.png", "manifest.json", "assets/photos/x.jpg"))
           and not any(cf.allowed(x, pats) for x in ("automation/build_issue.py", "content/2026-10-25.json", ".github/workflows/x.yml")),
           "Codex 가 남길 수 있는 경로 판단이 틀렸다")
    wf = (ROOT / ".github" / "workflows" / "codex-fallback.yml").read_text(encoding="utf-8")
    expect("openai/codex-action@v1" in wf and wf.count("persist-credentials: false") == 2 and "secrets.OPENAI_API_KEY != ''" in wf
           and "restore --produce" in wf and "alert.py codex" in wf, "codex-fallback.yml 의 안전장치(토큰 없이·키 확인·되돌림·알림)가 빠졌다")
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
    check("봇 커밋 이름은 KST 날짜", t_commit_dates)
    check("안장출근길 비교(회고 잣대)", t_compare_anjang)
    check("발송 시각(지난 호는 08:00)", t_send_time)
    check("짧게 읽는 소식 점검", t_brief_check)
    check("새 호 막는 점검(짧은 소식 개수·H PICK 중복)", t_strict_content)
    check("월요일 투표 쉼(2026-10-19~)", t_poll_paused)
    check("원문(보도자료)·H PICK 원문 점검(2026-10-23~)", t_releases)
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
