#!/usr/bin/env python3
"""운영 알림 — 문제가 생기면 운영자 메일(SMTP_USER)로 바로 알린다(.github/workflows/alerts.yml).

  python3 automation/alert.py failed    # 다른 워크플로가 실패로 끝났을 때(workflow_run — 예약 실행과 달리 늦지 않는다)
  python3 automation/alert.py watch     # 발행 감시(매일 08:40·09:40 KST): 오늘 호·메일 발송·인스타 게시·웹 페이지·성과 수집·토큰
  python3 automation/alert.py test      # 알림 메일이 오는지 시험 한 통
  python3 automation/alert.py watch --dry-run [--date YYYY-MM-DD]   # 보내지 않고 무엇을 알릴지만 출력

제작 루틴이 사용량 한도·오류로 원고를 못 올린 날은 발송·게시 워크플로가 '실패'하지 않고 조용히 끝나서 watch 로만 잡힌다.
같은 날 같은 알림은 한 번만 보낸다(automation/alerts/{날짜}.json 에 알림 종류만 남긴다).
공개 저장소·공개 로그라 주소·토큰은 출력하지도 저장하지도 않는다.
필요한 환경변수: SMTP_USER·SMTP_PASSWORD(없으면 로그에만 남긴다). failed 는 GITHUB_TOKEN·RUN_* 도.
"""
import argparse
import datetime as dt
import json
import os
import re
import smtplib
import ssl
import sys
import urllib.error
import urllib.request
from email.message import EmailMessage
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from edith.common import AUTOMATION, MANIFEST, ROOT, load_config, now_kst, parse_date, weekday_ko  # noqa: E402

ALERTS_DIR = AUTOMATION / "alerts"
SUBJECT = "EDIT H 운영 알림"  # '[EDIT H]' 로 시작하지 않게 — 답장·투표 집계(IMAP 제목 검색)와 섞이지 않도록

# 워크플로 이름 → (무슨 일, 다음에 무슨 일이 일어나는지 / 할 일)
WHAT = {
    "Send EDIT H newsletter": (
        "뉴스레터 메일 발송",
        "08:05 예비 실행과 08:20 점검 루틴이 한 번 더 시도합니다. 같은 알림이 또 오면 Gmail 앱 비밀번호가 바뀌지 않았는지 보고, "
        "바뀌었다면 GitHub → Settings → Secrets 의 SMTP_PASSWORD 를 새로 넣어 주세요."),
    "Post EDIT H to Instagram": (
        "인스타그램 게시(캐러셀·릴스)",
        "릴스만 실패했다면 영상과 캡션이 이 메일함으로 따로 와 있으니 휴대폰에서 올리면 됩니다. "
        "캐러셀까지 실패가 이어지면 인스타 토큰(IG_ACCESS_TOKEN)이 만료됐을 수 있어요."),
    "Sync EDIT H subscribers": (
        "구독 신청·수신 거부 반영",
        "내일 07:10 실행이 밀린 신청까지 다시 반영합니다. 그 사이 수신 거부한 분에게 한 번 더 발송될 수 있어요."),
    "Tally EDIT H poll": ("독자 투표 집계", "내일 06:20 에 다시 셉니다. 결과 공개일(금)에 실패하면 그날은 결과 없이 발행됩니다."),
    "Collect EDIT H metrics": ("성과 수집", "회고·제작은 직전 성과표로 진행하고, 다음 수집 때 따라잡습니다."),
    "Fetch reel music": ("릴스 음원 받기", "기존 음원으로 릴스를 만듭니다. 급하지 않아요."),
}


HEADLINE = {"issue": "오늘 호 미발행", "send": "메일 미발송", "send_partial": "메일 일부 실패", "carousel": "인스타 카드뉴스 미게시",
            "reel": "릴스 미게시", "reel_manual": "릴스 직접 올려 주세요", "web": "웹 페이지 안 열림",
            "metrics": "성과 수집 멈춤", "token": "인스타 토큰 연장 안 됨"}


def send_mail(subject, body, dry=False):
    user, pw = os.environ.get("SMTP_USER", ""), os.environ.get("SMTP_PASSWORD", "")
    print(f"── {subject}\n{body}")
    if dry:
        print("(dry-run — 보내지 않음)")
        return True
    if not user or not pw:
        print("::warning::SMTP_USER·SMTP_PASSWORD 가 없어 알림 메일을 보내지 못했습니다")
        return False
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = msg["To"] = user
    msg.set_content(body + "\n\n— EDIT H 자동 알림 (automation/alert.py)\n")
    with smtplib.SMTP_SSL(os.environ.get("SMTP_HOST") or "smtp.gmail.com", int(os.environ.get("SMTP_PORT") or 465),
                          context=ssl.create_default_context(), timeout=30) as smtp:
        smtp.login(user, pw)
        smtp.send_message(msg)
    print("알림 메일 보냄(SMTP_USER)")
    return True


def failed_steps(run_id):
    """실패한 작업·단계 이름. 권한이 없거나 막히면 빈 목록."""
    repo, token = os.environ.get("GITHUB_REPOSITORY", ""), os.environ.get("GITHUB_TOKEN", "")
    if not (repo and token and run_id):
        return []
    req = urllib.request.Request(f"https://api.github.com/repos/{repo}/actions/runs/{run_id}/jobs",
                                 headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            jobs = json.loads(r.read()).get("jobs", [])
    except (urllib.error.URLError, OSError, ValueError):
        return []
    return [s["name"] for j in jobs for s in j.get("steps", []) if s.get("conclusion") in ("failure", "timed_out")]


def busy():
    """지금 돌고 있는(대기 포함) 워크플로 이름. 발송·게시가 아직 진행 중이면 '빠졌다'고 잘못 알리지 않으려고."""
    repo, token = os.environ.get("GITHUB_REPOSITORY", ""), os.environ.get("GITHUB_TOKEN", "")
    if not (repo and token):
        return set()
    names = set()
    for status in ("in_progress", "queued"):
        req = urllib.request.Request(f"https://api.github.com/repos/{repo}/actions/runs?status={status}&per_page=50",
                                     headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                names |= {w.get("name") for w in json.loads(r.read()).get("workflow_runs", [])}
        except (urllib.error.URLError, OSError, ValueError):
            pass
    return names


def failed():
    name = os.environ.get("RUN_NAME", "(알 수 없는 작업)")
    what, todo = WHAT.get(name, (name, "GitHub Actions 에서 실행 기록을 확인해 주세요."))
    started = os.environ.get("RUN_STARTED", "")
    try:
        started = dt.datetime.fromisoformat(started.replace("Z", "+00:00")).astimezone(now_kst().tzinfo).strftime("%m/%d %H:%M")
    except ValueError:
        pass
    how = {"schedule": "예약 실행", "push": "원고 푸시", "workflow_dispatch": "수동·점검 실행"}.get(os.environ.get("RUN_EVENT", ""), "")
    steps = failed_steps(os.environ.get("RUN_ID", ""))
    conclusion = {"timed_out": "시간 초과", "startup_failure": "시작 실패"}.get(os.environ.get("RUN_CONCLUSION", ""), "실패")
    lines = [f"[{what}] 작업이 {conclusion}로 끝났습니다.", "",
             f"· 작업: {name}" + (f" ({how})" if how else "")]
    if started:
        lines.append(f"· 시작: {started} (KST)")
    if steps:
        lines.append(f"· 실패한 단계: {', '.join(steps)}")
    lines += [f"· 실행 기록: {os.environ.get('RUN_URL', '')}", "", f"다음에 일어나는 일 / 할 일: {todo}"]
    send_mail(f"{SUBJECT} · {what} {conclusion}", "\n".join(lines))
    return 0


def _json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _site_ok(url):
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "edit-h-alert"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status == 200
    except (urllib.error.URLError, OSError):
        return False


def problems(date, cfg, check_web=True):
    """[(알림 종류, 한 줄 설명)] — 오늘 발행 흐름에서 빠진 것."""
    out = []
    d = parse_date(date)
    wd = weekday_ko(d)
    hol = {}
    for k, v in (_json(AUTOMATION / "holidays_kr.json") or {}).items():
        if not k.startswith("_"):
            hol.update(v)
    publish_day = wd in cfg["publish_days"] and not (cfg.get("skip_kr_public_holidays") and date in hol)

    manifest = _json(MANIFEST) or {"issues": []}
    issue = next((i for i in manifest["issues"] if i["date"] == date), None)
    if publish_day and not ((ROOT / f"{date}.html").exists() and issue):
        out.append(("issue", f"오늘({date} {wd}) 호가 올라오지 않았습니다 — 07:00 제작 루틴이 원고를 못 올렸어요"
                             "(Claude 사용량 한도·오류 가능). 08:20 점검 루틴이 원인을 확인해 알려드려요."))
    if issue:
        sent = _json(AUTOMATION / "sent" / f"{date}.json")
        if sent is None:
            out.append(("send", f"VOL.{issue['vol']} 은 올라왔지만 메일 발송 기록이 없습니다 — 발송 워크플로가 아직 안 돌았거나 실패했어요."))
        elif sent.get("failed"):
            out.append(("send_partial", f"VOL.{issue['vol']} 메일이 {sent['failed']}명에게 가지 않았습니다(발송 {sent.get('sent', 0)}명)."))

        ig_cfg = cfg.get("instagram") or {}
        if ig_cfg.get("auto_post", True) and (ROOT / "instagram" / date / "caption.txt").exists():
            log = _json(AUTOMATION / "ig_posted" / f"{date}.json") or {}
            if not (log.get("carousel") or {}).get("id"):
                out.append(("carousel", "인스타 카드뉴스(캐러셀)가 게시되지 않았습니다."))
            if ig_cfg.get("reel", True) and not (log.get("reel") or {}).get("id"):
                if log.get("reel_emailed"):
                    out.append(("reel_manual", "릴스 자동 게시가 안 돼 영상·캡션을 이 메일함으로 보냈습니다 — 휴대폰에서 올려 주세요."))
                else:
                    out.append(("reel", "인스타 릴스가 게시되지 않았습니다."))
        if check_web and not _site_ok(f"{cfg['site_url']}/{date}.html"):
            out.append(("web", "웹 아카이브에 오늘 호 페이지가 열리지 않습니다 — GitHub Pages 배포가 늦거나 실패했어요."))

    # 성과표 첫 줄의 수집 시각('2026-09-25T21:31+09:00 수집')으로 본다(체크아웃은 파일 시각을 새로 쓴다)
    summary = AUTOMATION / "metrics" / "summary.md"
    m = re.search(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}[+-]\d{2}:\d{2}) 수집", summary.read_text(encoding="utf-8")[:300]) \
        if summary.exists() else None
    if m:
        age = (now_kst() - dt.datetime.fromisoformat(m.group(1))).total_seconds() / 3600
        if age > 36:
            out.append(("metrics", f"성과 수집이 {int(age)}시간째 멈춰 있습니다 — 회고·제작이 오래된 숫자로 판단하고 있어요."))

    token = _json(AUTOMATION / "ig_posted" / "_token.json") or {}
    if token.get("refreshed"):
        days = (d - parse_date(token["refreshed"])).days
        if days > 14:
            out.append(("token", f"인스타 토큰이 {days}일째 연장되지 않았습니다(7일마다 자동 연장) — 60일이 지나면 게시가 멈춰요. "
                                 "GH_ADMIN_TOKEN·IG_APP_SECRET 이 그대로인지 확인해 주세요."))
    return out


def watch(date, dry=False):
    cfg = load_config()
    found = problems(date, cfg)
    running = busy()
    skip = {k for k, name in (("send", "Send EDIT H newsletter"), ("carousel", "Post EDIT H to Instagram"),
                              ("reel", "Post EDIT H to Instagram"), ("reel_manual", "Post EDIT H to Instagram"))
            if name in running}
    if skip:
        print(f"  아직 진행 중인 실행이 있어 다음 점검으로 미룸: {', '.join(sorted(skip))}")
        found = [(k, t) for k, t in found if k not in skip]
    if not found:
        print(f"{date}: 이상 없음")
        return 0
    rec_path = ALERTS_DIR / f"{date}.json"
    rec = _json(rec_path) or {"date": date, "sent": []}
    new = [(k, t) for k, t in found if k not in rec["sent"]]
    for k, t in found:
        print(f"  {'(이미 알림)' if k in rec['sent'] else '•'} {t}")
    if not new:
        return 0
    body = "\n".join(f"• {t}" for _, t in new)
    body += (f"\n\n발행 흐름 확인: {now_kst():%m/%d %H:%M} (KST)"
             f"\n실행 기록: https://github.com/{os.environ.get('GITHUB_REPOSITORY', 'vetnam555-del/edit-h-archive')}/actions")
    head = f"{date[5:].replace('-', '/')} {HEADLINE.get(new[0][0], new[0][0])}"
    if send_mail(f"{SUBJECT} · {head}" + (f" 외 {len(new) - 1}건" if len(new) > 1 else ""), body, dry) and not dry:
        rec["sent"] += [k for k, _ in new]
        ALERTS_DIR.mkdir(parents=True, exist_ok=True)
        rec_path.write_text(json.dumps(rec, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["failed", "watch", "test"])
    ap.add_argument("--date", default="", help="watch: 확인할 날짜(비우면 오늘 KST)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if args.mode == "failed":
        return failed()
    if args.mode == "test":
        send_mail(f"{SUBJECT} · 시험 메일",
                  "EDIT H 운영 알림이 이 메일함으로 옵니다.\n"
                  "발송·게시·집계가 실패하면 곧바로, 오늘 호·발송·게시가 빠지면 08:40(KST) 감시에서 알려드려요.", args.dry_run)
        return 0
    return watch(args.date or now_kst().date().isoformat(), args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
