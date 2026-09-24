#!/usr/bin/env python3
"""주간 독자 투표 집계 — 메일(투표 버튼으로 보낸 메일·A/B 답장) + 인스타그램 댓글(A/B).

월요일(그 주 첫 호)에 content 의 `poll` 로 묻고, 금요일 호에 결과를 싣는다(RUNBOOK '독자 투표').
tally-poll.yml 이 평일 06:20(KST)에 돌려 automation/polls/{투표 날짜}.json 을 갱신한다.
공개 저장소라 **숫자만** 남긴다(주소·계정 이름은 세는 동안 메모리에서만 쓰고 저장·출력하지 않는다).
한 사람 한 표(같은 주소·같은 계정은 마지막 표만), 채널 사이 중복은 가려낼 수 없어 그대로 더한다.

  python3 automation/tally_poll.py                 # 최근 14일 안의 투표 전부
  python3 automation/tally_poll.py --id 2026-09-28 --dry-run
필요한 환경변수: SMTP_USER·SMTP_PASSWORD(Gmail 앱 비밀번호 — IMAP 으로 읽기만), IG_ACCESS_TOKEN. 없으면 그 채널만 건너뛴다.
"""
import argparse
import datetime as dt
import email
import email.header
import email.utils
import imaplib
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from edith.common import AUTOMATION, CONTENT_DIR, load_config, now_kst  # noqa: E402

POLLS_DIR = AUTOMATION / "polls"
POLL_SUBJECT = "EDIT H POLL"   # 투표 버튼 메일 제목: '[EDIT H POLL 2026-09-28] A' (send_newsletter.py)
_VOTE = re.compile(r"^\s*[\"'(\[]?\s*([AaBb])\s*(?:$|[\s.,!?)\]~·:\-ㅋㅎ]|번)")
_QUOTE_START = re.compile(r"^(>|On .+wrote:|20\d\d[.\-/년].+(작성|wrote)|-+\s*Original Message|보낸 사람:|From:)")


def vote_of(text, options=None):
    """글의 첫 줄에서 A/B 를 읽는다. 'A', 'b!', 'A 가족과 함께', '(B)' 는 표, 'Apple' 같은 낱말은 아니다.
    선택지 글자를 그대로 쓴 경우(예: '혼자 푹 쉬기')도 센다."""
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        if _QUOTE_START.match(line):
            return None
        m = _VOTE.match(line)
        if m:
            return m.group(1).upper()
        for key, opt in zip("AB", options or []):
            if opt and opt.replace(" ", "") in line.replace(" ", ""):
                return key
        return None
    return None


def _decode(value):
    parts = []
    for text, enc in email.header.decode_header(value or ""):
        parts.append(text.decode(enc or "utf-8", errors="replace") if isinstance(text, bytes) else text)
    return "".join(parts)


def _plain_body(msg):
    part = next((p for p in msg.walk() if p.get_content_type() == "text/plain" and not p.get_filename()), None)
    if part is None:
        return ""
    payload = part.get_payload(decode=True) or b""
    return payload.decode(part.get_content_charset() or "utf-8", errors="replace")


def email_votes(poll, issue_title, imap=None):
    """{보낸 주소: 표}. 투표 버튼 메일(제목에 표)과 뉴스레터에 A/B 로 답장한 메일(본문 첫 줄)을 센다."""
    user, pw = os.environ.get("SMTP_USER", ""), os.environ.get("SMTP_PASSWORD", "")
    if imap is None:
        if not user or not pw:
            print("  메일: SMTP_USER·SMTP_PASSWORD 가 없어 건너뜀")
            return None
        imap = imaplib.IMAP4_SSL(os.environ.get("IMAP_HOST") or "imap.gmail.com", 993)
        imap.login(user, pw)
    since = dt.date.fromisoformat(poll["id"]).strftime("%d-%b-%Y")
    imap.select("INBOX", readonly=True)
    ids = set()
    for crit in (f'SUBJECT "{POLL_SUBJECT} {poll["id"]}"', 'SUBJECT "[EDIT H]"'):
        typ, data = imap.search(None, f"(SINCE {since} {crit})")
        if typ == "OK" and data and data[0]:
            ids.update(data[0].split())
    votes, me = {}, user.lower()
    for mid in sorted(ids, key=int):
        typ, data = imap.fetch(mid, "(RFC822)")
        if typ != "OK" or not data or not isinstance(data[0], tuple):
            continue
        msg = email.message_from_bytes(data[0][1])
        sender = email.utils.parseaddr(msg.get("From", ""))[1].lower()
        if not sender or sender == me:
            continue
        subject = _decode(msg.get("Subject"))
        m = re.search(re.escape(POLL_SUBJECT) + r"\s+" + re.escape(poll["id"]) + r"\]?\s*([AaBb])\b", subject)
        if m:
            votes[sender] = m.group(1).upper()
        elif re.match(r"^\s*(re|답장)\s*:", subject, re.I) and issue_title and issue_title in subject:
            v = vote_of(_plain_body(msg), poll["options"])
            if v:
                votes[sender] = v
    try:
        imap.logout()
    except Exception:  # noqa: BLE001 — 집계는 끝났다
        pass
    return votes


def instagram_votes(poll, graph=None):
    """{계정: 표}. 그날 올린 캐러셀·릴스의 댓글에서 A/B 를 센다(우리 계정 댓글은 뺀다)."""
    log_path = AUTOMATION / "ig_posted" / f"{poll['id']}.json"
    if not log_path.exists():
        print("  인스타: 그날 게시 기록이 없어 건너뜀")
        return None
    log = json.loads(log_path.read_text(encoding="utf-8"))
    media = [log[k]["id"] for k in ("carousel", "reel") if (log.get(k) or {}).get("id")]
    if graph is None:
        token = os.environ.get("IG_ACCESS_TOKEN", "").strip()
        if not token:
            print("  인스타: IG_ACCESS_TOKEN 이 없어 건너뜀")
            return None
        from post_instagram import Graph
        graph = Graph(token, load_config().get("instagram") or {})
    me = (graph.call("GET", "me", fields="username").get("username") or "").lower()
    votes = {}
    for media_id in media:
        page = graph.call("GET", f"{media_id}/comments", fields="text,username,timestamp", limit=100)
        while True:
            for c in sorted(page.get("data", []), key=lambda c: c.get("timestamp", "")):
                who = (c.get("username") or "").lower()
                v = vote_of(c.get("text"), poll["options"])
                if who and who != me and v:
                    votes[who] = v
            nxt = (page.get("paging") or {}).get("next")
            if not nxt:
                break
            page = graph.call("GET", nxt)
    return votes


def open_polls(days=14, only=None):
    """최근 days 일 안의 투표 [(poll, 그 호 제목)]."""
    today = now_kst().date()
    out = []
    for p in sorted(CONTENT_DIR.glob("20*.json")):
        day = dt.date.fromisoformat(p.stem)
        if only and p.stem != only:
            continue
        if not only and not 0 <= (today - day).days <= days:
            continue
        c = json.loads(p.read_text(encoding="utf-8"))
        if c.get("poll"):
            out.append(({**c["poll"], "id": p.stem}, re.sub(r"[=*]", "", c.get("title", ""))))
    return out


def tally(poll, issue_title, imap=None, graph=None):
    counts = {"A": 0, "B": 0}
    channels = {}
    for name, fn in (("email", lambda: email_votes(poll, issue_title, imap)), ("instagram", lambda: instagram_votes(poll, graph))):
        try:
            got = fn()
        except Exception as e:  # noqa: BLE001 — 한 채널이 막혀도 다른 채널은 센다
            print(f"  {name}: 집계 실패({type(e).__name__}) — 이 채널은 이번에 빼고 저장")
            got = None
        if got is None:
            continue
        channels[name] = len(got)
        for v in got.values():
            counts[v] += 1
    return {"id": poll["id"], "question": poll["question"], "options": poll["options"], "votes": counts,
            "channels": channels, "updated_at": now_kst().isoformat(timespec="seconds")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", help="투표 날짜(YYYY-MM-DD). 비우면 최근 14일 안의 투표 전부")
    ap.add_argument("--dry-run", action="store_true", help="세기만 하고 파일은 쓰지 않음")
    args = ap.parse_args()
    polls = open_polls(only=args.id)
    if not polls:
        print("집계할 투표가 없습니다(최근 14일 안에 poll 이 있는 호 없음)")
        return
    for poll, title in polls:
        print(f"■ {poll['id']} 투표 — {poll['question']}")
        res = tally(poll, title)
        total = sum(res["votes"].values())
        print(f"  A {res['votes']['A']} · B {res['votes']['B']} (총 {total}명, 채널별 {res['channels']})")
        if not args.dry_run:
            POLLS_DIR.mkdir(parents=True, exist_ok=True)
            (POLLS_DIR / f"{poll['id']}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
