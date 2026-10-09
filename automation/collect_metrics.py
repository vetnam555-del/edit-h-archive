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
FRESH_HOUR = "21"   # 이 시각(KST) 이후 스냅숏이 오늘 성과표(22:00 회고가 읽는다)
INSIGHT_METRICS = "reach,saved,shares,views"
REEL_WATCH_METRICS = "ig_reels_avg_watch_time,ig_reels_video_view_total_time"   # 밀리초 — 릴스 완주 정도를 가늠
FEED_EXTRA_METRICS = "profile_visits,follows"   # 캐러셀(피드)만 — 게시물을 보고 프로필에 오고 팔로우했나(2026-10-09~)
ACCOUNT_DAYS = 7
# 계정 단위 최근 7일(2026-10-09 진단: 팔로워 47→130 인데 캐러셀 도달 10~28 그대로 — 도달이 팔로워에게서 오는지, 새 팔로워가 보는지 가린다).
# 하나가 막혀도 나머지는 남게 지표마다 따로 부른다.
# follows_and_unfollows 의 follow_type 구분은 FOLLOWER = 새로 팔로우, NON_FOLLOWER = 언팔로우(Meta IG User Insights).
# profile_links_taps 는 연락 버튼(전화·메일 등) 탭이라 소개글 링크 유입이 아니다 — 링크 유입은 구독 페이지 ?ref=ig 로 센다(Codex 리뷰).
ACCOUNT_METRICS = (("reach", "follow_type"), ("follows_and_unfollows", "follow_type"), ("profile_views", None), ("accounts_engaged", None))


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
        # 실험 축(2026-10-02 성장 검토): 독자 축(content.audience)과 릴스 형식·게시 시각(게시 기록)
        "audience": c.get("audience") or "전체",
        "series": (c.get("series") or {}).get("name") or "없음",   # 고정 연재(수요일 'H의 장부', 2026-10-21~)
        **_reel_facts(day),
    }


def _reel_facts(day):
    """게시 기록에서 릴스 형식(세로·카드)·길이(초)·게시 시각대(아침·저녁)."""
    log_path = AUTOMATION / "ig_posted" / f"{day}.json"
    reel = (json.loads(log_path.read_text(encoding="utf-8")).get("reel") or {}) if log_path.exists() else {}
    if not reel.get("id"):
        return {"reel_style": None, "reel_seconds": None, "reel_slot": None, "reel_feed": None}
    style = reel.get("style") or ("cards" if day < "2026-10-03" else None)
    hour = int(reel["at"][11:13]) if reel.get("at") else None
    slot = None if hour is None else ("아침" if hour < 12 else "낮" if hour < 17 else "저녁")
    seconds = reel.get("seconds") or (32.3 if day < "2026-10-01" else 19.6 if day < "2026-10-03" else None)
    return {"reel_style": {"vertical": "세로", "cards": "카드"}.get(style, style), "reel_seconds": seconds, "reel_slot": slot,
            "reel_feed": bool(reel.get("feed"))}   # E7 — 피드에도 올렸나(2026-10-13~)


def _values(data):
    """인사이트 응답 → {지표: 값}. total_value 에 구분(breakdown)이 있으면 {구분값: 값}."""
    out = {}
    for d in data or []:
        if not d.get("name"):
            continue
        tv = d.get("total_value") or {}
        results = ((tv.get("breakdowns") or [{}])[0] or {}).get("results")
        if results:
            out[d["name"]] = {"/".join(r.get("dimension_values") or []) or "?": _num(r.get("value")) for r in results}
        else:
            out[d["name"]] = _num(tv.get("value", (d.get("values") or [{}])[0].get("value")))
    return out


def account_week(g, now=None):
    """최근 7일 계정 단위 — 도달(팔로워/비팔로워)·팔로우/언팔로우·프로필 조회·반응한 계정. 실패한 지표는 errors 에."""
    from post_instagram import IGError
    now = now or now_kst()
    span = {"since": int((now - dt.timedelta(days=ACCOUNT_DAYS)).timestamp()), "until": int(now.timestamp()) - 300}
    out = {"days": ACCOUNT_DAYS}
    for metric, breakdown in ACCOUNT_METRICS:
        params = {"metric": metric, "period": "day", "metric_type": "total_value", **span}
        if breakdown:
            params["breakdown"] = breakdown
        try:
            out.update(_values(g.call("GET", "me/insights", **params).get("data")))
        except IGError as e:
            out.setdefault("errors", {})[metric] = str(e)[:120]
    return out


def _media_row(g, media_id, own_comments, out):
    """게시물 하나의 좋아요·댓글(+ 권한이 있으면 도달·저장·공유·조회)."""
    from post_instagram import IGError
    m = g.call("GET", media_id, fields="like_count,comments_count")
    row = {"likes": _num(m.get("like_count")), "comments": max((_num(m.get("comments_count")) or 0) - own_comments, 0)}
    if out["insights"] is not False:
        try:
            data = g.call("GET", f"{media_id}/insights", metric=INSIGHT_METRICS).get("data", [])
            for d in data:
                vals = d.get("values") or [{}]
                row[d["name"]] = _num(d.get("total_value", {}).get("value", vals[0].get("value")))
            out["insights"] = True
        except IGError as e:
            out["insights"] = False
            out["insights_error"] = str(e)[:160]
    return row


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
        own = 1 if (log.get("carousel") or {}).get("first_comment") else 0   # 우리 계정이 단 첫 댓글은 뺀다
        row = _media_row(g, cid, own, out)
        if out["insights"]:
            try:   # 프로필 방문·팔로우 — 지원 안 되면 이 두 칸만 빠진다
                row.update(_values(g.call("GET", f"{cid}/insights", metric=FEED_EXTRA_METRICS).get("data")))
            except Exception as e:  # noqa: BLE001 — 덤 지표가 이상해도 그 게시물의 기본 성과는 남긴다
                row["extra_error"] = (str(e) if isinstance(e, IGError) else type(e).__name__)[:120]
        rid = (log.get("reel") or {}).get("id")
        if rid:   # 릴스는 피드 격자에 안 올려(릴스 탭 전용) 도달이 따로 잡힌다 — 호 점수에는 둘을 합친다
            try:
                row["reel"] = _media_row(g, rid, 0, out)
                row["reel"]["seconds"] = _reel_facts(day)["reel_seconds"]   # 시청 비율(평균 시청 ÷ 길이)용
            except IGError as e:
                row["reel_error"] = str(e)[:120]
            if row.get("reel"):
                try:   # 릴스 도달을 가르는 건 시청 시간 — 평균 시청 시간(초)을 함께 본다(2026-10-01~)
                    data = g.call("GET", f"{rid}/insights", metric=REEL_WATCH_METRICS).get("data", [])
                    ms = {d["name"]: _num(d.get("total_value", {}).get("value", (d.get("values") or [{}])[0].get("value"))) for d in data}
                    if ms.get("ig_reels_avg_watch_time") is not None:
                        row["reel"]["avg_watch_s"] = round(ms["ig_reels_avg_watch_time"] / 1000, 1)
                except IGError as e:
                    row["reel"]["watch_error"] = str(e)[:120]
        out["posts"][day] = row
    try:   # 게시물 인사이트와 따로 — 게시가 쉬었거나 게시물 지표가 막혀도 계정 지표는 모은다(Codex 리뷰)
        out["account"] = account_week(g)
    except Exception as e:  # noqa: BLE001 — 계정 지표가 이상해도 게시물 성과는 남긴다
        out["account"] = {"errors": {"account": type(e).__name__}}
    return out


def _subject(msg):
    return str(email.header.make_header(email.header.decode_header(msg.get("Subject", ""))))


def _signup_ref(imap, mid):
    """구독 신청 알림 본문의 'ref' 칸(subscribe.html 숨은 칸) — 없으면 'direct'. 인코딩(base64·QP)은 email 모듈로 푼다."""
    typ, got = imap.fetch(mid, "(BODY.PEEK[])")
    if typ != "OK" or not got or not isinstance(got[0], tuple):
        return "direct"
    msg = email.message_from_bytes(got[0][1])
    part = next((p for p in msg.walk() if p.get_content_type() == "text/plain"), None)
    text = (part.get_payload(decode=True) or b"").decode(part.get_content_charset() or "utf-8", "replace") if part else ""
    m = re.search(r"(?im)^\s*ref\s*[:：]?\s*\n?\s*([a-z0-9_-]{1,20})\s*$", text)
    return m.group(1).lower() if m else "direct"


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
        refs = {}   # 구독 경로별 신청 수(subscribe.html 의 숨은 칸 ref) — 숫자만
        for mid in ids:
            typ, got = imap.fetch(mid, "(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM)])")
            if typ != "OK" or not got or not isinstance(got[0], tuple):
                continue
            msg = email.message_from_bytes(got[0][1])
            subj = _subject(msg)
            sender = email.utils.parseaddr(msg.get("From", ""))[1].lower()
            if "신규 구독 신청" in subj:
                signups += 1
                ref = _signup_ref(imap, mid)
                refs[ref] = refs.get(ref, 0) + 1
            elif "수신 거부 신청" in subj:
                unsubs += 1
            elif re.match(r"^\s*(re|답장)\s*:", subj, re.I) and sender and sender != user.lower():
                for d, t in titles.items():
                    if t and t in subj:
                        senders[d].add(sender)
        for d in days:
            replies[d] = len(senders[d])
        return {"replies": replies, "signups_14d": signups, "unsubs_14d": unsubs, "signup_refs_14d": refs}
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
    """비교용 한 숫자. 저장·공유는 '다시 볼 가치'라 무겁게, 댓글은 대화라 좋아요보다 무겁게. 릴스 반응도 더한다."""
    if not row:
        return None
    s = (row.get("likes") or 0) + 2 * (row.get("comments") or 0) + 3 * (row.get("saved") or 0) + 3 * (row.get("shares") or 0)
    return s + (score(row["reel"]) or 0 if row.get("reel") else 0)


def _reel_cell(p):
    """'조회 120·도달 80 · 평균 6.2초 (반응 2)' — 릴스 기록이 없으면 '–'. 좋아요·댓글·저장은 점수에 합쳐지고 여기엔 반응이 있을 때만 붙인다."""
    r = p.get("reel") or {}
    if not r:
        return "–"
    cell = f"{r.get('views', '–')}·{r.get('reach', '–')}"
    if r.get("avg_watch_s") is not None:
        cell += f" · 평균 {r['avg_watch_s']}초"
        if r.get("seconds"):
            cell += f"/{r['seconds']:g}초({round(100 * r['avg_watch_s'] / r['seconds'])}%)"
    extra = (r.get("likes") or 0) + (r.get("comments") or 0) + (r.get("saved") or 0) + (r.get("shares") or 0)
    return cell + (f" (반응 {extra})" if extra else "")


def _at_age(day, snap, hours=24):
    """그 호 캐러셀의 '게시 hours 시간 뒤 첫 스냅숏' 숫자({reach, views, …}). 아직 그만큼 안 지났으면 {}.
    스냅숏은 하루 1~2번이라 실제 나이는 24~48시간 사이 — 누적 숫자를 그대로 비교하는 것보다 공정하다."""
    log = AUTOMATION / "ig_posted" / f"{day}.json"
    at = ((json.loads(log.read_text(encoding="utf-8")).get("carousel") or {}).get("at") if log.exists() else None) or f"{day}T08:00:00+09:00"
    due = dt.datetime.fromisoformat(at) + dt.timedelta(hours=hours)
    snaps = [json.loads(q.read_text(encoding="utf-8")) for q in sorted((METRICS / "daily").glob("*.json"))] + [snap]
    for s in sorted(snaps, key=lambda s: s.get("collected_at") or ""):
        row = ((s.get("instagram") or {}).get("posts") or {}).get(day)
        if row and s.get("collected_at") and dt.datetime.fromisoformat(s["collected_at"]) >= due:
            return row
    return {}


def _reel_compare(scored):
    """릴스 형식(세로·카드)·게시 시각대별 — 게시 24시간 뒤 도달, 평균 시청 시간과 길이 대비 비율(2026-10-02 실험 축)."""
    groups = {}
    for d, f, sc, a in scored:
        r = a.get("reel") or {}
        if not f.get("reel_style") or r.get("reach") is None:
            continue
        key = f["reel_style"] + (f"·{f['reel_slot']}" if f.get("reel_slot") else "") + ("·피드" if f.get("reel_feed") else "")
        groups.setdefault(key, []).append((r.get("reach"), r.get("avg_watch_s"), f.get("reel_seconds")))
    if not groups:
        return []
    parts = []
    for k, v in sorted(groups.items()):
        reach = sum(x[0] for x in v) / len(v)
        watch = [x[1] for x in v if x[1] is not None]
        ratio = [x[1] / x[2] for x in v if x[1] is not None and x[2]]
        part = f"{k} 도달 {round(reach)}"
        if watch:
            part += f"·평균 시청 {sum(watch) / len(watch):.1f}초"
        if ratio:
            part += f"(길이의 {round(100 * sum(ratio) / len(ratio))}%)"
        parts.append(part + f"({len(v)}호)")
    return ["- 릴스 형식: " + ", ".join(parts)]


def _series_compare(snap):
    """고정 연재(E4, 수요일 'H의 장부') — 14일 창과 상관없이 config.series.from 부터 모든 호를 '게시 24시간 뒤' 숫자로 비교한다.
    연재는 주 1편이라 14일 창에는 2편만 들어간다 — 4편을 다 내고 판정하려면 창 밖의 편도 지난 스냅숏에서 읽어야 한다."""
    start = (load_config().get("series") or {}).get("from")
    if not start:
        return []
    groups = {}
    for p in sorted(CONTENT_DIR.glob("*.json")):
        day = p.stem
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day) or day < start:
            continue
        f = issue_facts(day)
        if not f or f.get("source_mode") == "rewind":
            continue
        a = _at_age(day, snap)
        if a:
            groups.setdefault(f["series"], []).append((score(a), a.get("reach"), a.get("views")))
    if len(groups) < 2:
        return []

    def avg(vals, nd=0):
        vals = [v for v in vals if v is not None]
        return "–" if not vals else f"{sum(vals) / len(vals):.{nd}f}"

    parts = [f"{k} 점수 {avg([x[0] for x in v], 1)}·도달 {avg([x[1] for x in v])}·조회 {avg([x[2] for x in v])}({len(v)}호)"
             for k, v in sorted(groups.items(), key=lambda kv: kv[0] == "없음")]
    return [f"- 연재({start}부터 모든 호, 게시 24시간 뒤): " + ", ".join(parts)]


def _account_lines(ig, posts):
    """한눈에: 최근 7일 계정 도달의 팔로워/비팔로워·팔로우 증감·프로필 조회, 14일 캐러셀 프로필 방문·팔로우 합."""
    acc = ig.get("account") or {}
    out = []
    reach, fol = acc.get("reach"), acc.get("follows_and_unfollows")
    if isinstance(reach, dict) or isinstance(fol, dict) or acc.get("profile_views") is not None:
        reach = reach if isinstance(reach, dict) else {}
        fol = fol if isinstance(fol, dict) else {}

        def other(buckets):   # FOLLOWER·NON_FOLLOWER 밖의 구분(UNKNOWN 등)도 버리지 않고 보인다(Codex 리뷰)
            rest = sum(v or 0 for k, v in buckets.items() if k not in ("FOLLOWER", "NON_FOLLOWER"))
            return f"(미분류 {rest})" if rest else ""

        out.append(f"- 최근 {acc.get('days', ACCOUNT_DAYS)}일 계정: 도달 팔로워 {reach.get('FOLLOWER', '–')} · 비팔로워 {reach.get('NON_FOLLOWER', '–')}{other(reach)}"
                   f" · 팔로우 +{fol.get('FOLLOWER', '–')} / 언팔로우 −{fol.get('NON_FOLLOWER', '–')}{other(fol)}"
                   f" · 프로필 조회 {acc.get('profile_views', '–')} · 반응한 계정 {acc.get('accounts_engaged', '–')}")
    visits = [p.get("profile_visits") for p in posts.values() if p.get("profile_visits") is not None]
    follows = [p.get("follows") for p in posts.values() if p.get("follows") is not None]
    if visits or follows:
        out.append(f"- 캐러셀 보고 프로필 방문 {sum(visits)} · 팔로우 {sum(follows)} (최근 {DAYS}일 {len(visits)}개 게시물 누적)")
    return out


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
              f" · 최근 {DAYS}일 구독 신청 {mb.get('signups_14d', '–')} · 수신 거부 {mb.get('unsubs_14d', '–')}"]
    lines += _account_lines(ig, posts)
    refs = mb.get("signup_refs_14d") or {}
    if refs:
        names = {"share": "추천 메일", "letter": "뉴스레터 속 버튼", "web": "웹 아카이브", "ig": "인스타", "threads": "스레드", "direct": "직접·알 수 없음"}
        lines.append("- 구독 경로(최근 %d일): " % DAYS + " · ".join(
            f"{names.get(k, k)} {v}" for k, v in sorted(refs.items(), key=lambda kv: -kv[1])))
    lines.append("")
    lines += ["## 호별 성과", "",
              "| 날짜 | 요일 | 제목 | 유형 | 표지 | H PICK | 좋아요 | 댓글 | 저장 | 공유 | 도달 | 릴스 조회·도달 | 답장 | 점수 |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for day, f, p, sc in rows:
        rep = (mb.get("replies") or {}).get(day, "–")
        lines.append(f"| {day} | {f['weekday']} | {f['title'][:28]} | {f['title_style']} | {f['cover']} | {f['pick_tag'] or '–'} | "
                     f"{p.get('likes', '–')} | {p.get('comments', '–')} | {p.get('saved', '–')} | {p.get('shares', '–')} | "
                     f"{p.get('reach', '–')} | {_reel_cell(p)} | {rep} | {sc if sc is not None else '–'} |")
    # 예비 호(다시 보기)는 편집 선택이 아니라 비교에서 뺀다. 좋아요·저장이 아직 0 인 날이 많아 캐러셀 도달·조회도 함께 보되,
    # 누적 숫자는 오래된 게시물일수록 커지므로 '게시 24시간 뒤 첫 스냅숏'의 값으로 나이를 맞춘다(없으면 그 호는 도달 비교에서 빠진다).
    scored = [(d, f, sc, _at_age(d, snap)) for d, f, p, sc in rows if sc is not None and f.get("source_mode") != "rewind"]
    if len(scored) >= 3:
        def _mean(vals):
            vals = [v for v in vals if v is not None]
            return (sum(vals) / len(vals), len(vals)) if vals else (None, 0)

        def avg_by(key):
            groups = {}
            for d, f, sc, a in scored:
                groups.setdefault(f[key], []).append((sc, a.get("reach"), a.get("views")))
            out = []
            for k, v in groups.items():
                (sc, _), (r, nr), (vw, _) = _mean([x[0] for x in v]), _mean([x[1] for x in v]), _mean([x[2] for x in v])
                out.append((k, sc, r, vw, len(v), nr))
            out.sort(key=lambda x: (-x[1], -(x[2] or 0)))
            return ", ".join(f"{k} {sc:.1f}점({n}호)·도달 {'–' if r is None else round(r)}·조회 {'–' if vw is None else round(vw)}({nr}호)"
                             for k, sc, r, vw, n, nr in out)
        measured = [x for x in scored if x[3].get("reach") is not None] or scored
        rank = lambda x: (x[2], x[3].get("reach") or 0)  # noqa: E731 — 점수가 같으면 24시간 도달로 가린다(도달을 잰 호끼리만)
        best = max(measured, key=rank)
        worst = min(measured, key=rank)
        lines += ["", "## 비교 (평균 점수(호 수) · 게시 24시간 뒤 캐러셀 도달·조회(잰 호 수) — 예비 호 제외)", "",
                  f"- 제목 유형: {avg_by('title_style')}",
                  f"- 표지: {avg_by('cover')}",
                  f"- 요일: {avg_by('weekday')}",
                  *([f"- 독자 축: {avg_by('audience')}"] if len({f.get('audience') for _, f, _, _ in scored}) > 1 else []),
                  *_series_compare(snap),
                  *_reel_compare(scored),
                  f"- 가장 좋았던 호: {best[0]} 「{best[1]['title']}」 {best[2]}점·도달 {best[3].get('reach', '–')}"
                  f" · 가장 약했던 호: {worst[0]} 「{worst[1]['title']}」 {worst[2]}점·도달 {worst[3].get('reach', '–')}",
                  "", "※ 호 수가 적을 때의 차이는 우연일 수 있다. 원칙은 같은 방향의 근거가 3호 이상 쌓였을 때만 바꾼다."]
    else:
        lines += ["", "(비교는 인스타 성과가 3호 이상 쌓이면 나온다)"]
    polls = snap.get("polls") or {}
    if polls:
        lines += ["", "## 투표 참여", ""] + [f"- {k}: {v}명" for k, v in sorted(polls.items())]
    return "\n".join(lines) + "\n"


def latest_fresh(now=None):
    """(collected_at, failed) — 가장 최근 '21:00(KST) 경계' 뒤에 모은 스냅숏이 있으면. 없으면 None.
    자정을 넘겨 도는 늦은 예약 실행도 전날 밤 수집을 알아보게 날짜 파일이 아니라 수집 시각으로 본다(10/4 01:54 중복 수집)."""
    now = now or now_kst()
    edge = now.replace(hour=int(FRESH_HOUR), minute=0, second=0, microsecond=0)
    if now < edge:
        edge -= dt.timedelta(days=1)
    for p in sorted((METRICS / "daily").glob("*.json"), reverse=True)[:3]:
        snap = json.loads(p.read_text(encoding="utf-8"))
        at = snap.get("collected_at") or ""
        if at and dt.datetime.fromisoformat(at) >= edge:
            return at, snap.get("failed") or []
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-if-fresh", action="store_true",
                    help="마지막 21:00(KST) 이후 스냅숏이 이미 있으면 건너뛴다 — 늦게 도는 예약 실행이 겹칠 때")
    args = ap.parse_args()
    today = now_kst().date()
    if args.skip_if_fresh and (fresh := latest_fresh()):
        at, failed = fresh
        if not failed:
            print(f"{at[5:16]} 에 이미 모았습니다(마지막 21:00 이후) — 건너뜀")
            return
        print(f"{at[5:16]} 수집에서 {', '.join(failed)} 이(가) 실패했었습니다 — 다시 모읍니다")
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
            snap.setdefault("failed", []).append(name)   # 다음 예약 실행·회고 수집 요청이 다시 모으게
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
