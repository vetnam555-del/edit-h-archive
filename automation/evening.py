#!/usr/bin/env python3
"""저녁 일정 사슬 — 낮·저녁 GitHub 예약 실행이 3~6시간씩 늦어서(2026-10-05 매일 개선 루틴 실측) 시각이 중요한 저녁 일을
아침에 제시간에 오는 이벤트(오늘 호 push, 07:20 안팎)에서 출발해 기다렸다가 workflow_dispatch 로 바로 실행한다(.github/workflows/evening.yml).

  18:00  금요일 주간 특집 게시(config.weekly_special — 시작일 이후 그 요일)   → post-instagram.yml mode=post key={날짜}-weekly
  19:30  릴스 저녁 게시(config.instagram.reel_time_kst, reel_evening_from 이후)  → post-instagram.yml mode=post key={날짜} only=reel
  20:45  저녁 운영 점검(릴스 게시 + 70분 뒤)                                    → alerts.yml mode=watch date={날짜}
  21:30  성과 수집(22:00 회고 전에)                                            → collect-metrics.yml

예약(cron) 실행은 그대로 둬서 이 사슬이 끊겨도 늦게나마 돈다(같은 게시·알림은 기록을 보고 건너뛴다).

  python3 automation/evening.py plan                 # GITHUB_OUTPUT: go·date (오늘 할 저녁 일이 있는가)
  python3 automation/evening.py sleep --until 17:30  # 그 시각까지(최대 --max-min 분) 기다린다 — 작업 하나 6시간 제한 때문에 나눠 기다린다
  python3 automation/evening.py run --date D         # 위 일정을 시각마다 실행(GH_TOKEN 필요) · --dry-run 은 출력만
"""
import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from edith.common import AUTOMATION, CONTENT_DIR, ROOT, load_config, now_kst, parse_date, weekday_ko  # noqa: E402

REPO = os.environ.get("GITHUB_REPOSITORY", "vetnam555-del/edit-h-archive")
ANCHOR = "17:30"   # 사슬의 대기 작업들이 모이는 시각 — 여기서부터 마지막 작업 하나(6시간 안)가 저녁 일정을 돈다
CHECK_AFTER = 75   # 릴스 게시 뒤 이만큼(분) 지나 저녁 점검(alert._reel_due 의 70분 + 여유)
METRICS_AT = "21:30"


def _at(day, hhmm):
    hh, mm = map(int, hhmm.split(":"))
    return dt.datetime.combine(parse_date(day), dt.time(hh, mm), tzinfo=now_kst().tzinfo)


def schedule(day, cfg=None):
    """[(시각, 이름, 워크플로, 입력)] — 이 날짜에 할 저녁 일. 예비 호 날·호가 없는 날은 게시를 빼고 수집만."""
    cfg = cfg or load_config()
    out = []
    has_issue = (ROOT / f"{day}.html").exists()
    content = CONTENT_DIR / f"{day}.json"
    rewind = has_issue and content.exists() and bool(json.loads(content.read_text(encoding="utf-8")).get("rewind"))
    ig = cfg.get("instagram") or {}
    auto = ig.get("auto_post", True)   # 인스타 자동 게시를 끈 동안엔 사슬도 게시하지 않는다(수동 key 실행과 구분)
    ws = cfg.get("weekly_special") or {}
    if (auto and ws.get("enabled_from") and day >= ws["enabled_from"] and weekday_ko(parse_date(day)) == ws.get("weekday", "금")
            and (CONTENT_DIR / "weekly" / f"{day}.json").exists()):   # 07:00 루틴이 주간 특집 원고를 올린 날만
        out.append((_at(day, "18:00"), "주간 특집", "post-instagram.yml", {"mode": "post", "key": f"{day}-weekly", "only": "both"}))
    if auto and has_issue and not rewind and ig.get("reel_time_kst") and ig.get("reel_evening_from") and day >= ig["reel_evening_from"]:
        reel = _at(day, ig["reel_time_kst"])
        out.append((reel, "저녁 릴스", "post-instagram.yml", {"mode": "post", "key": day, "only": "reel"}))
        out.append((reel + dt.timedelta(minutes=CHECK_AFTER), "저녁 점검", "alerts.yml", {"mode": "watch", "date": day}))
    out.append((_at(day, METRICS_AT), "성과 수집", "collect-metrics.yml", {"skip_if_fresh": "true"}))   # 예약이 제때 모았으면 건너뜀
    return sorted(out, key=lambda x: x[0])


def _done(day, name):
    """이미 끝난 일인가(main 기록 기준) — 다시 dispatch 하지 않는다. 게시·수집 스크립트도 스스로 건너뛰지만 실행 낭비를 줄인다."""
    log = AUTOMATION / "ig_posted" / f"{day}.json"
    if name == "저녁 릴스" and log.exists():
        return bool((json.loads(log.read_text(encoding="utf-8")).get("reel") or {}).get("id"))
    if name == "주간 특집":
        wlog = AUTOMATION / "ig_posted" / f"{day}-weekly.json"
        return wlog.exists() and bool((json.loads(wlog.read_text(encoding="utf-8")).get("carousel") or {}).get("id"))
    return False


def dispatch(workflow, inputs, dry=False):
    args = ["gh", "api", "-X", "POST", f"repos/{REPO}/actions/workflows/{workflow}/dispatches", "-f", "ref=main"]
    for k, v in inputs.items():
        args += ["-f", f"inputs[{k}]={v}"]
    if dry:
        print("    (드라이런) " + " ".join(args[3:]))
        return True
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode:
        print(f"    ✗ dispatch 실패: {(r.stderr or r.stdout).strip()[:200]}")
    return r.returncode == 0


def _sleep_until(target, max_min=None):
    wait = (target - now_kst()).total_seconds()
    if max_min is not None:
        wait = min(wait, max_min * 60)
    if wait > 0:
        print(f"  {target:%H:%M} KST 까지 {int(wait)}초 대기")
        time.sleep(wait)


def cmd_plan():
    day = now_kst().date().isoformat()
    items = [x for x in schedule(day) if not _done(day, x[1])]
    go = bool(items)   # 성과 수집은 매일 있으니 보통 true
    print(f"{day} 저녁 일정: " + (", ".join(f"{t:%H:%M} {n}" for t, n, _, _ in items) or "없음"))
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
            f.write(f"go={'true' if go else 'false'}\ndate={day}\n")


def cmd_run(day, dry=False):
    failed = 0
    for at, name, wf, inputs in schedule(day):
        if not dry:
            _sleep_until(at)
        subprocess.run(["git", "pull", "-q", "--ff-only", "origin", "main"], capture_output=True)   # 그사이 올라온 게시 기록
        if _done(day, name):
            print(f"  {at:%H:%M} {name}: 이미 했다 — 건너뜀")
            continue
        print(f"  {at:%H:%M} {name} → {wf} {inputs}")
        failed += not dispatch(wf, inputs, dry)
    return 1 if failed else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["plan", "sleep", "run"])
    ap.add_argument("--until", default=ANCHOR)
    ap.add_argument("--max-min", type=int, default=350)
    ap.add_argument("--date")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if a.cmd == "plan":
        return cmd_plan()
    day = a.date or now_kst().date().isoformat()
    if a.cmd == "sleep":
        return _sleep_until(_at(day, a.until), a.max_min)
    return cmd_run(day, a.dry_run)


if __name__ == "__main__":
    sys.exit(main())
