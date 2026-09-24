#!/usr/bin/env python3
"""발행된 호를 구독자에게 메일로 보낸다. GitHub Actions(.github/workflows/send-newsletter.yml)에서 돈다.

클라우드 루틴 컨테이너는 SMTP 가 막혀 있고, 구독자 주소를 공개 저장소에 둘 수도 없어서
발송만 GitHub Actions + 저장소 Secrets 로 분리했다.

환경변수(저장소 Settings → Secrets and variables → Actions)
  SMTP_USER        보내는 계정 (예: Gmail 주소)
  SMTP_PASSWORD    Gmail 앱 비밀번호(16자리)
  SUBSCRIBERS      받는 사람 목록. 쉼표·줄바꿈 구분
  SMTP_HOST/PORT   선택. 기본 smtp.gmail.com / 465
  MAIL_FROM        선택. 기본 SMTP_USER

사용
  python3 automation/send_newsletter.py --mode schedule            # 08:30 정기 발송
  python3 automation/send_newsletter.py --mode push                # 늦게 올라온 호 즉시 발송(08:30 이후일 때만)
  python3 automation/send_newsletter.py --date 2026-09-28 --test-to me@example.com   # 테스트(기록 안 남김)
  python3 automation/send_newsletter.py --dry-run                  # 실제 발송 없이 대상·제목만 확인
"""
import argparse
import html
import json
import os
import re
import smtplib
import ssl
import sys
import time
import urllib.parse
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from edith.common import AUTOMATION, MANIFEST, ROOT, load_config, now_kst  # noqa: E402

SENT_DIR = AUTOMATION / "sent"


def notice(msg):
    # GitHub Actions 요약에 보이도록
    print(f"::notice::{msg}" if os.environ.get("GITHUB_ACTIONS") else msg)


def recipients(raw):
    seen, out = set(), []
    for addr in re.split(r"[,\n;]+", raw or ""):
        addr = addr.strip()
        if addr and re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", addr) and addr.lower() not in seen:
            seen.add(addr.lower())
            out.append(addr)
    return out


def html_to_text(src):
    body = re.sub(r"(?is)<(style|head)[^>]*>.*?</\1>", "", src)
    body = re.sub(r"(?i)<br\s*/?>|</(div|p|tr|h\d)>", "\n", body)
    body = re.sub(r"<[^>]+>", "", body)
    lines = [html.unescape(l).strip() for l in body.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def build_message(issue, page, to_addr, cfg, sender):
    site = cfg["site_url"]
    q = urllib.parse.quote(to_addr)
    unsub = f"{site}/unsubscribe.html?email={q}"
    body = page.replace("email=PLACEHOLDER", f"email={q}")
    msg = EmailMessage()
    msg["Subject"] = f"{cfg['email']['subject_prefix']} {issue['title']}"
    msg["From"] = formataddr((cfg["email"]["from_name"], sender))
    msg["To"] = to_addr
    msg["Message-ID"] = make_msgid(domain=sender.split("@")[-1])
    msg["List-Unsubscribe"] = f"<mailto:{sender}?subject=unsubscribe>, <{unsub}>"
    web = issue.get("public_url", f"{site}/{issue['filename']}")
    msg.set_content(f"웹에서 보기: {web}\n\n{html_to_text(body)}\n\n수신거부: {unsub}\n")
    msg.add_alternative(body, subtype="html")
    return msg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="manual", help="schedule | push | workflow_dispatch | manual")
    ap.add_argument("--date", default="", help="YYYY-MM-DD (비우면 오늘 KST)")
    ap.add_argument("--test-to", default="", help="이 주소로만 보내고 발송 기록은 남기지 않음")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cfg = load_config()
    now = now_kst()
    date = args.date or now.date().isoformat()
    page_path = ROOT / f"{date}.html"
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    issue = next((i for i in manifest["issues"] if i["date"] == date), None)

    if not page_path.exists() or not issue:
        notice(f"{date} 호가 아직 없습니다 — 발송하지 않습니다(휴일이거나 루틴이 늦어지는 중). 호가 올라오면 push 트리거가 발송합니다.")
        return 0

    marker = SENT_DIR / f"{date}.json"
    if marker.exists() and not args.test_to:
        notice(f"{date} 호는 이미 발송됐습니다({marker.name}) — 건너뜁니다")
        return 0

    if args.mode == "push" and not args.test_to:
        hh, mm = map(int, cfg["send_time_kst"].split(":"))
        if (now.hour, now.minute) < (hh, mm) or now.date().isoformat() != date:
            notice(f"push 로 올라온 {date} 호: 정기 발송 시각({cfg['send_time_kst']}) 전이거나 오늘 호가 아니라 정기 발송에 맡깁니다")
            return 0

    to_list = recipients(args.test_to) if args.test_to else recipients(os.environ.get("SUBSCRIBERS"))
    if not to_list:
        notice("받는 사람이 없습니다 — 저장소 Secret SUBSCRIBERS 를 설정하세요")
        return 0 if args.dry_run else 1

    user = os.environ.get("SMTP_USER", "")
    sender = os.environ.get("MAIL_FROM") or user
    page = page_path.read_text(encoding="utf-8")
    if args.dry_run:
        print(f"[dry-run] VOL.{issue['vol']} '{issue['title']}' → {len(to_list)}명")
        return 0
    if not user or not os.environ.get("SMTP_PASSWORD"):
        notice("SMTP_USER / SMTP_PASSWORD Secret 이 없습니다 — 발송하지 못했습니다")
        return 1

    host = os.environ.get("SMTP_HOST") or "smtp.gmail.com"
    port = int(os.environ.get("SMTP_PORT") or 465)
    sent, failed = 0, []
    with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context()) as smtp:
        smtp.login(user, os.environ["SMTP_PASSWORD"])
        for addr in to_list:
            try:
                smtp.send_message(build_message(issue, page, addr, cfg, sender))
                sent += 1
            except smtplib.SMTPException as e:
                failed.append({"to_domain": addr.split("@")[-1], "error": str(e)[:200]})
            time.sleep(1)  # Gmail 발송 속도 제한 여유

    print(f"VOL.{issue['vol']} {date}: {sent}/{len(to_list)}명 발송")
    if not args.test_to and sent:
        SENT_DIR.mkdir(exist_ok=True)
        # 공개 저장소이므로 주소는 남기지 않고 숫자만 기록한다
        marker.write_text(json.dumps({
            "date": date, "vol": issue["vol"], "sent_at_kst": now_kst().isoformat(timespec="seconds"),
            "trigger": args.mode, "sent": sent, "failed": len(failed), "failures": failed,
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if sent else 1


if __name__ == "__main__":
    sys.exit(main())
