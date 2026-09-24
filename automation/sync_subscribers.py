#!/usr/bin/env python3
"""구독 신청·수신 거부 자동 반영 — Formspree 알림 메일(Gmail IMAP, 읽기 전용) → GitHub Secret SUBSCRIBERS.

subscribe.html·unsubscribe.html 은 Formspree 로 보내고, Formspree 는 폼 주인 메일로
'[EDIT H] 신규 구독 신청' / '[EDIT H] 수신 거부 신청' 알림을 보낸다(Reply-To = 신청한 주소).
sync-subscribers.yml 이 매일 07:10(KST, 발송 20분 전)에 이 알림을 읽어 목록을 고치고, 새 구독자에게 환영 메일을 보낸다.

안전장치(목록은 공개 저장소에 둘 수 없어 Secret 에만 있고, Secret 은 되읽을 수 없다):
- 지금 SUBSCRIBERS 가 비었거나 읽을 수 없으면 아무것도 쓰지 않는다.
- 바꾸기 전 값을 SUBSCRIBERS_BACKUP 에 먼저 저장한다(되돌리기: 그 값을 SUBSCRIBERS 에 붙여넣기).
- 수신 거부로 빠진 주소 말고는 기존 항목이 하나라도 사라지면 쓰지 않는다. 기존 항목은 적힌 그대로 둔다('이름 <주소>' 포함).
- 공개 저장소·공개 로그라 주소는 저장·출력하지 않는다. 어디까지 읽었는지(IMAP UID)만 automation/subscribers_sync.json 에 남긴다.

  python3 automation/sync_subscribers.py --dry-run   # 읽기만: 몇 건 추가·제거될지 숫자로
  python3 automation/sync_subscribers.py             # 반영(+ 환영 메일)
  python3 automation/sync_subscribers.py --since 2026-09-20   # 처음 한 번: 이 날짜 뒤 알림까지 거슬러 반영
처음 실행(상태 파일 없음)은 --since 가 없으면 지금 시점을 기준점으로만 잡는다 — 예전 신청을 다시 처리해
이미 손으로 정리한 목록을 흔들거나 옛 신청자에게 환영 메일을 보내지 않으려고.
필요한 환경변수: SMTP_USER·SMTP_PASSWORD(Gmail 앱 비밀번호), SUBSCRIBERS, GH_ADMIN_TOKEN, GITHUB_REPOSITORY
"""
import argparse
import email
import email.header
import email.utils
import imaplib
import json
import os
import re
import smtplib
import ssl
import sys
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from edith.common import AUTOMATION, MANIFEST, load_config, now_kst, send_time_ko  # noqa: E402
from send_newsletter import EMAIL, notice  # noqa: E402

STATE = AUTOMATION / "subscribers_sync.json"
SUB_SUBJECT, UNSUB_SUBJECT = "신규 구독 신청", "수신 거부 신청"
_SKIP_DOMAINS = ("formspree.io",)


def _addr(entry):
    m = EMAIL.search(entry or "")
    return m.group(0).lower() if m else None


def split_entries(raw):
    """SUBSCRIBERS 원문 → 항목 목록(쉼표·세미콜론·줄바꿈). 항목은 적힌 그대로 둔다."""
    return [p.strip() for p in re.split(r"[,\n;]+", raw or "") if p.strip()]


def submitted_address(msg, me):
    """알림 메일에서 신청한 주소: Reply-To(Formspree 가 email 칸으로 채움) → 본문 'email' 칸 → 본문의 첫 외부 주소."""
    for header in ("Reply-To",):
        a = email.utils.parseaddr(msg.get(header, ""))[1].lower()
        if a and not a.endswith(_SKIP_DOMAINS) and a != me:
            return a
    body = ""
    for part in msg.walk():
        if part.get_content_type() == "text/plain":
            body = (part.get_payload(decode=True) or b"").decode(part.get_content_charset() or "utf-8", errors="replace")
            break
    m = re.search(r"(?im)^\s*email\s*[:：]?\s*\n?\s*(" + EMAIL.pattern + ")", body)
    if m:
        return m.group(1).lower()
    for a in EMAIL.findall(body):
        a = a.lower()
        if not a.endswith(_SKIP_DOMAINS) and a != me:
            return a
    return None


def _subject(msg):
    return str(email.header.make_header(email.header.decode_header(msg.get("Subject", ""))))


def read_events(imap, me, state, since=None):
    """마지막으로 읽은 UID 뒤의 알림을 시간순 [(uid, 'sub'|'unsub', 주소)]과 새 상태.
    상태가 없고 since 도 없으면(첫 실행) 지금의 마지막 UID 를 기준점으로만 잡고 아무것도 처리하지 않는다."""
    imap.select("INBOX", readonly=True)
    typ, uv = imap.response("UIDVALIDITY")
    uidvalidity = int(uv[0]) if uv and uv[0] else 0
    typ, allu = imap.uid("SEARCH", None, "ALL")
    max_uid = max([0] + [int(u) for u in (allu[0].split() if typ == "OK" and allu and allu[0] else [])])
    if state.get("uidvalidity") == uidvalidity:
        last = state.get("last_uid", 0)
    elif since:
        last = 0
    else:
        return [], {"uidvalidity": uidvalidity, "last_uid": max_uid}
    crit = f'(UID {last + 1}:* SUBJECT "[EDIT H]"' + (f' SINCE {since:%d-%b-%Y})' if since else ")")
    typ, data = imap.uid("SEARCH", None, crit)
    uids = [int(u) for u in (data[0].split() if typ == "OK" and data and data[0] else []) if int(u) > last]
    events = []
    for uid in sorted(uids):
        typ, got = imap.uid("FETCH", str(uid), "(BODY.PEEK[HEADER.FIELDS (SUBJECT)])")
        if typ != "OK" or not got or not isinstance(got[0], tuple):
            continue
        subject = _subject(email.message_from_bytes(got[0][1]))
        kind = "sub" if SUB_SUBJECT in subject else "unsub" if UNSUB_SUBJECT in subject else None
        if not kind or re.match(r"^\s*(re|fwd?|답장|전달)\s*:", subject, re.I):
            continue
        typ, got = imap.uid("FETCH", str(uid), "(BODY.PEEK[])")
        if typ != "OK" or not got or not isinstance(got[0], tuple):
            continue
        a = submitted_address(email.message_from_bytes(got[0][1]), me)
        if a:
            events.append((uid, kind, a))
    return events, {"uidvalidity": uidvalidity, "last_uid": max([last, max_uid] + uids)}


def apply_events(entries, events):
    """(새 항목 목록, 추가된 주소, 제거된 주소). 같은 주소는 마지막 알림이 이긴다."""
    final = {}
    for _, kind, a in events:
        final[a] = kind
    present = {_addr(e) for e in entries}
    removes = {a for a, k in final.items() if k == "unsub" and a in present}
    adds = [a for a, k in final.items() if k == "sub" and a not in present]
    kept = [e for e in entries if _addr(e) not in removes]
    return kept + adds, adds, sorted(removes)


def check_safe(old_entries, new_entries, removes):
    """기존 항목이 수신 거부 말고 사라지면 안전하지 않다. (괜찮은가, 사유)."""
    if not old_entries:
        return False, "지금 SUBSCRIBERS 가 비어 있거나 읽을 수 없습니다 — 아무것도 쓰지 않습니다"
    lost = [e for e in old_entries if e not in new_entries and _addr(e) not in set(removes)]
    if lost:
        return False, f"수신 거부가 아닌 기존 항목 {len(lost)}개가 사라지려 합니다 — 쓰지 않습니다"
    return True, ""


def welcome(smtp, sender, to_addr, cfg):
    site = cfg["site_url"]
    latest = json.loads(MANIFEST.read_text(encoding="utf-8"))["issues"][-1]
    unsub = f"{site}/unsubscribe.html?email={to_addr}"
    msg = EmailMessage()
    msg["Subject"] = f"{cfg['email']['subject_prefix']} 구독을 환영해요 — 다음 영업일 아침에 만나요"
    msg["From"] = formataddr((cfg["email"]["from_name"], sender))
    msg["To"] = to_addr
    msg["List-Unsubscribe"] = f"<{unsub}>"
    msg.set_content(
        "EDIT H를 구독해 주셔서 고마워요.\n\n"
        f"매 영업일 {send_time_ko(cfg['send_time_kst']).replace('오전', '아침')}, 오늘 꼭 알아둘 트렌드 5가지를 보내드려요. 하나는 H PICK으로 깊게 풀어드리고,\n"
        "월요일엔 독자 투표를 열어 금요일에 결과를 알려드려요.\n\n"
        f"최근 호 먼저 읽어보기: {site}/{latest['filename']}\n"
        "메일이 스팸함으로 가지 않게, 이 메일에 한 줄 답장해 주시거나 주소록에 추가해 주세요.\n\n"
        f"신청하지 않으셨다면 여기서 바로 수신을 거부할 수 있어요: {unsub}\n\n— 에디터 H 드림\n")
    smtp.send_message(msg)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="읽기만 하고 Secret·상태 파일은 바꾸지 않음")
    ap.add_argument("--since", help="YYYY-MM-DD — 처음 한 번 이 날짜 뒤 알림까지 거슬러 반영(기본: 기준점만 잡음)")
    args = ap.parse_args()
    cfg = load_config()
    user, pw = os.environ.get("SMTP_USER", ""), os.environ.get("SMTP_PASSWORD", "")
    if not user or not pw:
        notice("SMTP_USER·SMTP_PASSWORD 가 없어 건너뜁니다")
        return 0
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    imap = imaplib.IMAP4_SSL(os.environ.get("IMAP_HOST") or "imap.gmail.com", 993)
    imap.login(user, pw)
    try:
        import datetime as dt
        since = dt.date.fromisoformat(args.since) if args.since else None
        events, new_state = read_events(imap, user.lower(), {} if since else state, since)
    finally:
        imap.logout()
    n_sub = sum(1 for _, k, _ in events if k == "sub")
    if not state and not args.since:
        notice("첫 실행 — 지금 시점을 기준점으로 잡았습니다(이후 들어오는 신청부터 자동 반영)")
    notice(f"새 알림: 구독 신청 {n_sub}건 · 수신 거부 {len(events) - n_sub}건")
    if not events:
        if not args.dry_run and new_state != state:
            STATE.write_text(json.dumps(new_state) + "\n", encoding="utf-8")
        return 0

    old = split_entries(os.environ.get("SUBSCRIBERS"))
    new, adds, removes = apply_events(old, events)
    ok, why = check_safe(old, new, removes)
    notice(f"SUBSCRIBERS: {len(old)}개 → {len(new)}개 (추가 {len(adds)} · 제거 {len(removes)})")
    if not ok:
        notice(why)
        return 1
    if args.dry_run:
        notice("dry-run — Secret 과 상태 파일은 바꾸지 않았습니다")
        return 0
    if adds or removes:
        from post_instagram import _save_secret
        if not _save_secret(os.environ.get("SUBSCRIBERS", ""), "SUBSCRIBERS_BACKUP"):
            notice("GH_ADMIN_TOKEN 이 없어 Secret 을 바꿀 수 없습니다 — 새 신청은 다음 실행에서 다시 읽습니다")
            return 1
        _save_secret(",\n".join(new), "SUBSCRIBERS")
        notice("SUBSCRIBERS 갱신 완료(이전 값은 SUBSCRIBERS_BACKUP)")
    STATE.write_text(json.dumps(new_state) + "\n", encoding="utf-8")

    if adds and cfg.get("email", {}).get("welcome", True):
        sent = 0
        with smtplib.SMTP_SSL(os.environ.get("SMTP_HOST") or "smtp.gmail.com", int(os.environ.get("SMTP_PORT") or 465),
                              context=ssl.create_default_context()) as smtp:
            smtp.login(user, pw)
            for a in adds:
                try:
                    welcome(smtp, os.environ.get("MAIL_FROM") or user, a, cfg)
                    sent += 1
                except smtplib.SMTPException:
                    pass
        notice(f"환영 메일 {sent}/{len(adds)}건 발송 ({now_kst():%H:%M} KST)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
