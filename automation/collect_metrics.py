#!/usr/bin/env python3
"""매일 성과 수집 — '매일 발전하는 시스템'의 재료. collect-metrics.yml 이 매일 21:30(KST)에 돌린다.

모으는 것(공개 저장소라 **숫자만**, 주소·계정 이름은 저장·출력하지 않는다):
- 인스타그램: 팔로워 수, 최근 14일 캐러셀마다 좋아요·댓글(기본 권한). 도달·저장·공유·조회는 인사이트 권한
  (instagram_business_manage_insights)이 있을 때만 — 없으면 'insights: false' 로 적고 넘어간다.
- 메일: 발송 대상 수(SUBSCRIBERS − 수신 제외), 호마다 받은 답장 수, 최근 14일 구독 신청·수신 거부 알림 수(Gmail IMAP 읽기 전용).
- 투표: automation/polls/ 의 참여 수.
- 콘텐츠: 호마다 H PICK 태그·제목 유형(질문형/숫자형)·표지(사진/핵심어)·요일.

결과: automation/metrics/daily/{날짜}.json(그날 스냅숏) + automation/metrics/summary.md(최근 14호 성과표·순위).
07:00 제작 루틴과 22:00 편집 회고가 summary.md 를 읽는다(RUNBOOK 0단계, automation/learnings.md).

  python3 automation/collect_metrics.py            # 수집 + 저장
  python3 automation/collect_metrics.py --dry-run  # 수집만(파일 안 씀)
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
from edith.common import AUTOMATION, CONTENT_DIR, load_config, now_kst, weekday_ko  # noqa: E402

METRICS = AUTOMATION / "metrics"
DAYS = 14
INSIGHT_METRICS = "reach,saved,shares,views"


def _num(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def issue_facts(day):
    """content 에서 성과와 비교할 특징만 뽑는다."""
    p = CONTENT_DIR / f"{day}.json"
    if not p.exists():
        return None
    c = json.loads(p.read_text(encoding="utf-8"))
    title = re.sub(r"[=*]", "", c.get("title", ""))
    cover = (c.get("cards") or {}).get("cover") or {}
    return {
        "title": title,
        "format": 2 if "items" in c and "sections" not in c else 1,
        "pick_tag": (c.get("big_issue") or {}).get("tag"),
        "title_style": "질문형" if title.rstrip().endswith("?") else ("숫자형" if re.search(r"\d", title) else "서술형"),
        "cover": "사진" if cover.get("photo") else "핵심어",
        "weekday": weekday_ko(dt.date.fromisoformat(day)),
        "poll": bool(c.get("poll")),
        "source_mode": c.get("source_mode"),
    }


def instagram(days):
    """{'followers': n, 'insights': bool, 'posts': {날짜: {...}}} 또는 None(토큰 없음)."""
    token = os.environ.get("IG_ACCESS_TOKEN", "").strip()
    if not token:
        print("  인스타: IG_ACCESS_TOKEN 이 없어 건너뜀")
        return None
    from post_instagram import Graph, IGError
    g = Graph(token, load_config().get("instagram") or {})
    me = g.call("GET", "me", fields="followers_count,media_count")
    out = {"followers": _num(me.get("followers_count")), "media": _num(me.get("media_count")), "insights": None, "posts": {}}
    for day in days:
        log_path = AUTOMATION / "ig_posted" / f"{day}.json"
        if not log_path.exists():
            continue
        log = json.loads(log_path.read_text(encoding="utf-8"))
        cid = (log.get("carousel") or {}).get("id")
        if not cid:
            continue
        m = g.call("GET", cid, fields="like_count,comments_count")
        own = 1 if (log.get("carousel") or {}).get("first_comment") else 0   # 우리 계정이 단 첫 댓글은 뺀다
        row = {"likes": _num(m.get("like_count")), "comments": max((_num(m.get("comments_count")) or 0) - own, 0)}
        if out["insights"] is not False:
            try:
                data = g.call("GET", f"{cid}/insights", metric=INSIGHT_METRICS).get("data", [])
                for d in data:
                    vals = d.get("values") or [{}]
                    row[d["name"]] = _num(d.get("total_value", {}).get("value", vals[0].get("value")))
                out["insights"] = True
            except IGError as e:
                out["insights"] = False
                out["insights_error"] = str(e)[:160]
        out["posts"][day] = row
    return out


def _subject(msg):
    return str(email.header.make_header(email.header.decode_header(msg.get("Subject", ""))))


def mailbox(days, titles):
    """{'replies': {날짜: n}, 'signups': n, 'unsubs': n} — 최근 DAYS 일. 주소는 세기만 한다."""
    user, pw = os.environ.get("SMTP_USER", ""), os.environ.get("SMTP_PASSWORD", "")
    if not user or not pw:
        print("  메일: SMTP_USER·SMTP_PASSWORD 가 없어 건너뜀")
        return None
    imap = imaplib.IMAP4_SSL(os.environ.get("IMAP_HOST") or "imap.gmail.com", 993)
    imap.login(user, pw)
    try:
        imap.select("INBOX", readonly=True)
        since = (now_kst().date() - dt.timedelta(days=DAYS)).strftime("%d-%b-%Y")
        typ, data = imap.search(None, f'(SINCE {since} SUBJECT "[EDIT H]")')
        ids = data[0].split() if typ == "OK" and data and data[0] else []
        replies, senders, signups, unsubs = {d: 0 for d in days}, {d: set() for d in days}, 0, 0
        for mid in ids:
            typ, got = imap.fetch(mid, "(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM)])")
            if typ != "OK" or not got or not isinstance(got[0], tuple):
                continue
            msg = email.message_from_bytes(got[0][1])
            subj = _subject(msg)
            sender = email.utils.parseaddr(msg.get("From", ""))[1].lower()
            if "신규 구독 신청" in subj:
                signups += 1
            elif "수신 거부 신청" in subj:
                unsubs += 1
            elif re.match(r"^\s*(re|답장)\s*:", subj, re.I) and sender and sender != user.lower():
                for d, t in titles.items():
                    if t and t in subj:
                        senders[d].add(sender)
        for d in days:
            replies[d] = len(senders[d])
        return {"replies": replies, "signups_14d": signups, "unsubs_14d": unsubs}
    finally:
        try:
            imap.logout()
        except Exception:  # noqa: BLE001
            pass


def subscribers():
    raw = os.environ.get("SUBSCRIBERS")
    if not raw:
        return None
    from send_newsletter import excluded, parse_recipients
    addrs = parse_recipients(raw)[0]
    kept, n_ex = excluded(addrs)
    return {"listed": len(addrs), "sending": len(kept), "excluded": n_ex}


def score(row):
    """비교용 한 숫자. 저장·공유는 '다시 볼 가치'라 무겁게, 댓글은 대화라 좋아요보다 무겁게."""
    if not row:
        return None
    s = (row.get("likes") or 0) + 2 * (row.get("comments") or 0) + 3 * (row.get("saved") or 0) + 3 * (row.get("shares") or 0)
    return s


def summary_md(snap):
    ig = snap.get("instagram") or {}
    posts = ig.get("posts") or {}
    mb = snap.get("mail") or {}
    rows = []
    for day, f in sorted(snap["issues"].items(), reverse=True):
        p = posts.get(day) or {}
        rows.append((day, f, p, score(p)))
    lines = [f"# EDIT H 성과표 (최근 {DAYS}일, {snap['collected_at']} 수집)", "",
             "자동 생성 — automation/collect_metrics.py. 숫자만 있고 개인 정보는 없다. 07:00 제작·22:00 회고가 읽는다.", ""]
    sub = snap.get("subscribers") or {}
    lines += ["## 한눈에", "",
              f"- 인스타 팔로워 **{ig.get('followers', '–')}** · 게시물 {ig.get('media', '–')}"
              + ("" if ig.get("insights") else " · 도달·저장 인사이트 권한 없음(좋아요·댓글만)"),
              f"- 메일 발송 대상 **{sub.get('sending', '–')}**명 (명단 {sub.get('listed', '–')} · 수신 제외 {sub.get('excluded', '–')})"
              f" · 최근 {DAYS}일 구독 신청 {mb.get('signups_14d', '–')} · 수신 거부 {mb.get('unsubs_14d', '–')}", ""]
    lines += ["## 호별 성과", "",
              "| 날짜 | 요일 | 제목 | 유형 | 표지 | H PICK | 좋아요 | 댓글 | 저장 | 공유 | 도달 | 답장 | 점수 |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for day, f, p, sc in rows:
        rep = (mb.get("replies") or {}).get(day, "–")
        lines.append(f"| {day} | {f['weekday']} | {f['title'][:28]} | {f['title_style']} | {f['cover']} | {f['pick_tag'] or '–'} | "
                     f"{p.get('likes', '–')} | {p.get('comments', '–')} | {p.get('saved', '–')} | {p.get('shares', '–')} | "
                     f"{p.get('reach', '–')} | {rep} | {sc if sc is not None else '–'} |")
    scored = [(d, f, sc) for d, f, p, sc in rows if sc is not None]
    if len(scored) >= 3:
        def avg_by(key):
            groups = {}
            for d, f, sc in scored:
                groups.setdefault(f[key], []).append(sc)
            return ", ".join(f"{k} {sum(v) / len(v):.1f}({len(v)}호)" for k, v in sorted(groups.items(), key=lambda kv: -sum(kv[1]) / len(kv[1])))
        best = max(scored, key=lambda x: x[2])
        worst = min(scored, key=lambda x: x[2])
        lines += ["", "## 비교 (평균 점수, 호 수)", "",
                  f"- 제목 유형: {avg_by('title_style')}",
                  f"- 표지: {avg_by('cover')}",
                  f"- 요일: {avg_by('weekday')}",
                  f"- 가장 좋았던 호: {best[0]} 「{best[1]['title']}」 {best[2]}점 · 가장 약했던 호: {worst[0]} 「{worst[1]['title']}」 {worst[2]}점",
                  "", "※ 호 수가 적을 때의 차이는 우연일 수 있다. 원칙은 같은 방향의 근거가 3호 이상 쌓였을 때만 바꾼다."]
    else:
        lines += ["", "(비교는 인스타 성과가 3호 이상 쌓이면 나온다)"]
    polls = snap.get("polls") or {}
    if polls:
        lines += ["", "## 투표 참여", ""] + [f"- {k}: {v}명" for k, v in sorted(polls.items())]
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    today = now_kst().date()
    days = [(today - dt.timedelta(days=i)).isoformat() for i in range(DAYS)]
    issues = {d: f for d in days if (f := issue_facts(d))}
    snap = {"collected_at": now_kst().isoformat(timespec="minutes"), "issues": issues}
    for name, fn in (("instagram", lambda: instagram(sorted(issues))),
                     ("mail", lambda: mailbox(sorted(issues), {d: f["title"] for d, f in issues.items()})),
                     ("subscribers", subscribers)):
        try:
            snap[name] = fn()
        except Exception as e:  # noqa: BLE001 — 한 곳이 막혀도 나머지는 모은다
            print(f"  {name}: 수집 실패({type(e).__name__}) — 이번엔 빼고 저장")
            snap[name] = None
    polls = {}
    for p in sorted((AUTOMATION / "polls").glob("20*.json")):
        t = json.loads(p.read_text(encoding="utf-8"))
        polls[p.stem] = sum(t["votes"].values())
    snap["polls"] = polls
    ig = snap.get("instagram") or {}
    print(f"호 {len(issues)}개 · 인스타 {len(ig.get('posts') or {})}개 게시물(인사이트 {ig.get('insights')}) · "
          f"팔로워 {ig.get('followers')} · 발송 대상 {(snap.get('subscribers') or {}).get('sending')}")
    if args.dry_run:
        print(summary_md(snap))
        return
    (METRICS / "daily").mkdir(parents=True, exist_ok=True)
    (METRICS / "daily" / f"{today.isoformat()}.json").write_text(json.dumps(snap, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (METRICS / "summary.md").write_text(summary_md(snap), encoding="utf-8")


if __name__ == "__main__":
    main()
