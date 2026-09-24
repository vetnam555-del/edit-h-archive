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
  python3 automation/send_newsletter.py --mode schedule            # 정기 발송(config.send_time_kst, 08:00)
  python3 automation/send_newsletter.py --mode push                # 늦게 올라온 호 즉시 발송(발송 시각 이후일 때만)
  python3 automation/send_newsletter.py --date 2026-09-28 --test-to me@example.com   # 테스트(기록 안 남김)
  python3 automation/send_newsletter.py --dry-run                  # 실제 발송 없이 대상·제목만 확인
  python3 automation/send_newsletter.py --check                    # 구독자 수·SMTP 로그인만 확인(메일 안 보냄, 주소는 출력 안 함)
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


EMAIL = re.compile(r"[A-Za-z0-9._%+'-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")


def parse_recipients(raw):
    """(주소 목록, 중복 수, 주소가 없는 항목 번호). 항목은 쉼표·세미콜론·줄바꿈으로 나눈다.
    '홍길동 <a@b.com>' 이나 표에서 복사한 줄처럼 주소 앞뒤에 다른 글자가 붙어 있어도 주소만 뽑는다."""
    seen, out, dup, bad = set(), [], 0, []
    parts = [p.strip() for p in re.split(r"[,\n;]+", raw or "") if p.strip()]
    for n, part in enumerate(parts, 1):
        found = EMAIL.findall(part)
        if not found:
            bad.append(n)
        for addr in found:
            if addr.lower() in seen:
                dup += 1
            else:
                seen.add(addr.lower())
                out.append(addr)
    return out, dup, bad


def excluded(addrs):
    """수신 제외 요청이 있는 주소를 뺀다. (남은 주소, 뺀 수).
    config.email.exclude_contains 의 글자가 주소 어디든 들어 있거나, 소문자로 바꾼 주소 전체·도메인(x.co.kr)·
    도메인의 한 부분(x) 가운데 하나의 SHA-256 이 config.email.exclude_sha256 에 있으면 뺀다."""
    import hashlib
    email_cfg = load_config().get("email") or {}
    hashes = set(email_cfg.get("exclude_sha256") or [])
    contains = [c.lower() for c in email_cfg.get("exclude_contains") or [] if c.strip()]

    def hit(addr):
        a = addr.lower()
        domain = a.rsplit("@", 1)[-1]
        return (any(c in a for c in contains)
                or any(hashlib.sha256(k.encode()).hexdigest() in hashes for k in (a, domain, *domain.split("."))))

    kept = [a for a in addrs if not hit(a)]
    return kept, len(addrs) - len(kept)


def recipients(raw):
    return excluded(parse_recipients(raw)[0])[0]


def check():
    """구독자 수와 SMTP 로그인만 확인한다. 공개 저장소라 실행 로그를 누구나 볼 수 있으므로 주소는 출력하지 않는다."""
    to_list, dup, bad = parse_recipients(os.environ.get("SUBSCRIBERS"))
    to_list, n_ex = excluded(to_list)
    msg = f"SUBSCRIBERS: 발송 대상 {len(to_list)}명"
    if n_ex:
        msg += f" · 수신 제외 {n_ex}명"
    if dup:
        msg += f" · 중복 {dup}개 제외"
    if bad:
        msg += f" · 주소가 없는 항목 {len(bad)}개({', '.join(f'{n}번째' for n in bad)}) 무시"
    notice(msg)
    ok = bool(to_list)

    user, password = os.environ.get("SMTP_USER", ""), os.environ.get("SMTP_PASSWORD", "")
    if not user or not password:
        notice("SMTP_USER / SMTP_PASSWORD Secret 이 없습니다")
        return 1
    host = os.environ.get("SMTP_HOST") or "smtp.gmail.com"
    port = int(os.environ.get("SMTP_PORT") or 465)
    try:
        with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=30) as smtp:
            smtp.login(user, password)
        notice(f"SMTP 로그인 성공({host}) — 메일은 보내지 않았습니다")
    except (smtplib.SMTPException, OSError) as e:
        notice(f"SMTP 로그인 실패({host}): {type(e).__name__} {str(e)[:200]}")
        ok = False
    return 0 if ok else 1


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
    ap.add_argument("--check", action="store_true", help="구독자 수·SMTP 로그인만 확인하고 끝낸다")
    args = ap.parse_args()
    if args.check:
        return check()

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
        notice(f"{date} 호는 발송 기록(또는 발송 제외 기록)이 있어 건너뜁니다 — automation/sent/{marker.name}")
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
