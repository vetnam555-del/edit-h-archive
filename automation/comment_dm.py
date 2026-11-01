#!/usr/bin/env python3
"""댓글 키워드 → 구독 링크 DM (2026-11-02, 운영자 '그냥 모든 걸 다 너가 알아서' — 댓글이 좋아요의 2배 가까이 달린 '댓글 남기면 DM' 게시물 참고).

최근 7일 게시물(캐러셀·릴스)의 댓글 중 짧은 댓글에 키워드(config.instagram.dm_keyword + comment_dm.keywords)가 있으면
  1) 그 댓글에 '비공개 답장'(Instagram 공식 API — 댓글 단 사람에게 DM 한 통)으로 구독 링크를 보내고
  2) 댓글에 짧은 공개 답글('DM 보내드렸어요')을 단다.
DM 권한(instagram_business_manage_messages)이 없거나 막히면 공개 답글로 '프로필 링크에서 구독'을 안내한다(댓글 권한만으로 된다).
공식 API(graph.instagram.com, 게시와 같은 IG_ACCESS_TOKEN)만 쓴다. 인스타 페이지를 긁지 않는다.

기록: automation/comment_dm/state.json — 댓글·사람은 해시(앞 16자리)로만, 날짜별 숫자만. 아이디·이름·댓글 글은 저장하지 않는다.
캡션의 'DM 약속'(site.dm_line)은 실제로 DM 이 한 번 나간 뒤 config.instagram.dm_auto_reply_from 날짜를 넣어 켠다(지키지 못할 약속 금지).

  python3 automation/comment_dm.py              # 처리(워크플로가 낮 동안 20분마다)
  python3 automation/comment_dm.py --dry-run    # 무엇을 할지 보여 주기만(보내지 않음·기록 안 함)
  python3 automation/comment_dm.py --probe      # 토큰 계정·댓글 읽기·메시지 권한 확인(기록에 결과 숫자만)
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from edith.common import AUTOMATION, load_config, now_kst  # noqa: E402

STATE = AUTOMATION / "comment_dm" / "state.json"
KST = dt.timezone(dt.timedelta(hours=9))
SALT = "edith-comment-dm:"
DEFAULTS = {"enabled": True, "keywords": ["구독"], "max_chars": 20, "lookback_days": 7, "max_per_run": 20, "max_per_day": 80,
            "public_reply": True, "fallback_reply": True, "link_ref": "ig-dm", "repeat_days": 30}
TOKEN_CODES = {190}                          # 토큰 만료·무효 — 이번 실행을 멈춘다
RATE_CODES = {4, 17, 32, 613}                # 호출 한도 — 이번 실행을 멈추고 다음 실행에 이어서
PERMISSION_CODES = {3, 10} | set(range(200, 300))   # 앱 권한·기능 없음 — DM 만 막힌 것으로 보고 공개 답글로
# 같은 code 10 이어도 하위 코드가 있으면 그 댓글 사정(창 7일 지남·이미 답장함 등)이라 권한 문제로 보지 않는다.


class ApiError(RuntimeError):
    def __init__(self, status, code=None, subcode=None, message=""):
        super().__init__(f"{status} (code {code}{'/' + str(subcode) if subcode else ''}): {message}")
        self.code, self.subcode = code, subcode


class Api:
    """graph.instagram.com 최소 호출기 — 오류의 code·하위 코드(subcode)를 그대로 넘긴다(권한 문제와 댓글 사정을 가르려고)."""

    def __init__(self, token, version="v23.0"):
        self.token, self.base = token, f"https://graph.instagram.com/{version}"

    def call(self, method, path, **params):
        params["access_token"] = self.token
        url = path if path.startswith("https://") else f"{self.base}/{path.lstrip('/')}"
        data = None
        if method == "GET":
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
        else:
            data = urllib.parse.urlencode(params).encode()
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=data, method=method), timeout=60) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            try:
                err = json.loads(body).get("error") or {}
            except ValueError:
                raise ApiError(e.code, message=body[:200]) from None
            raise ApiError(e.code, err.get("code"), err.get("error_subcode"),
                           err.get("error_user_msg") or err.get("message") or "") from None
        except urllib.error.URLError as e:
            raise ApiError("접속 실패", message=str(e.reason)) from None


def kind_of(e):
    """'token'·'rate'·'permission'·'comment'(그 댓글만의 사정)."""
    code, sub = getattr(e, "code", None), getattr(e, "subcode", None)
    if code in TOKEN_CODES:
        return "token"
    if code in RATE_CODES:
        return "rate"
    if code in PERMISSION_CODES and not sub:
        return "permission"
    return "comment"


def settings(cfg=None):
    cfg = cfg or load_config()
    ig = cfg.get("instagram") or {}
    s = dict(DEFAULTS, **(ig.get("comment_dm") or {}))
    kws = [ig.get("dm_keyword")] + list(s.get("keywords") or [])
    s["keywords"] = [k for k in dict.fromkeys(norm(k) for k in kws if k) if k]
    s["site_url"] = cfg["site_url"].rstrip("/")
    s["send_time"] = cfg.get("send_time_kst", "08:30")
    return s


def norm(text):
    """띄어쓰기·문장부호·이모지를 지운 소문자 — '에디트!!', '구 독' 도 잡는다."""
    return re.sub(r"[^0-9a-z가-힣]", "", (text or "").lower())


def matches(text, s):
    """짧은 댓글(max_chars 이하)에 키워드가 있으면 True. 긴 댓글은 대화라 사람이 읽는다."""
    t = norm(text)
    return bool(t) and len(t) <= s["max_chars"] and any(k in t for k in s["keywords"])


def h(kind, value):
    return hashlib.sha256(f"{SALT}{kind}:{value}".encode()).hexdigest()[:16]


def subscribe_url(s):
    return f"{s['site_url']}/subscribe.html?ref={s['link_ref']}"


def dm_text(s, day=None):
    """비공개 답장(DM) 글 — 링크는 DM 에서만 눌린다. 선물 기간이면 한 줄 더."""
    hh, mm = s["send_time"].split(":")
    when = f"{int(hh)}시" + (f" {int(mm)}분" if int(mm) else "")
    lines = ["안녕하세요, EDIT H예요 📮",
             f"2030이 알아야 할 경제·트렌드·마케팅·테크 소식을 골라 매일 아침 {when}에 메일로 보내드려요. 구독은 무료예요.",
             "", f"구독 신청 👉 {subscribe_url(s)}"]
    try:
        from edith.gift import active_gift
        g = active_gift(day)
    except Exception:  # noqa: BLE001 — 선물 줄은 없어도 된다
        g = None
    if g:
        lines += ["", f"지금 신청하면 「{g['title']}」도 함께 보내드려요 🎁"]
    lines += ["", "메일 맨 아래 '수신 거부'로 언제든 바로 끊을 수 있어요."]
    return "\n".join(lines)


REPLY_SENT = ["DM 보내드렸어요 📩", "DM 확인해 주세요 📩", "구독 링크 DM으로 보냈어요 📩"]
REPLY_FALLBACK = ["프로필 링크에서 바로 구독할 수 있어요 🙌", "프로필 맨 위 링크에서 구독할 수 있어요 🙌", "프로필 링크 누르면 바로 구독돼요 🙌"]
REPLY_REPEAT = ["지난번 DM에 보내드린 링크로 구독할 수 있어요 📩", "앞서 보낸 DM에 구독 링크 있어요 📩"]


def pick(options, key):
    return options[int(key[:4], 16) % len(options)]


def load_state(path=STATE):
    try:
        st = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        st = {}
    st.setdefault("handled", {})
    st.setdefault("users", {})
    st.setdefault("dm", {"ok": None})
    st.setdefault("daily", {})
    return st


def prune(st, today, s):
    """창(lookback_days) 밖 댓글 기록·repeat_days 지난 사람·60일 지난 날짜 숫자는 지운다."""
    def older(d, days):
        return d < (today - dt.timedelta(days=days)).isoformat()
    st["handled"] = {k: v for k, v in st["handled"].items() if not older(v.get("d", ""), s["lookback_days"] + 1)}
    st["users"] = {k: v for k, v in st["users"].items() if not older(v, s["repeat_days"])}
    st["daily"] = {k: v for k, v in st["daily"].items() if not older(k, 60)}


def parse_time(s):
    return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%S%z")


def short_err(e):
    return re.sub(r"\s+", " ", str(e))[:160]


def get_all(g, path, pages=4, **params):
    out, url = [], path
    for _ in range(pages):
        r = g.call("GET", url, **params)
        out += r.get("data") or []
        url = (r.get("paging") or {}).get("next")
        if not url:
            break
        params = {}
    return out


def recent_media(g, uid, now, s):
    """댓글이 달린 게시물 — 게시는 2배 창(14일)까지 본다. 지난주 글에 오늘 달린 댓글도 7일 안이면 답장할 수 있다."""
    since = now - dt.timedelta(days=s["lookback_days"] * 2)
    rows = g.call("GET", f"{uid}/media", fields="id,timestamp,comments_count,media_product_type", limit=30).get("data") or []
    return [m for m in rows if parse_time(m["timestamp"]) >= since and (m.get("comments_count") or 0) > 0]


def our_reply(c, me):
    return any(((r.get("from") or {}).get("id") == me["id"] or r.get("username") == me["username"])
               for r in ((c.get("replies") or {}).get("data") or []))


def candidates(g, me, now, s):
    """키워드가 있고, 댓글이 창(7일) 안이고, 우리 계정 댓글이 아닌 것만. 순서는 오래된 것부터."""
    since = now - dt.timedelta(days=s["lookback_days"])
    out = []
    for m in recent_media(g, me["id"], now, s):
        for c in get_all(g, f"{m['id']}/comments", fields="id,text,timestamp,from,username,replies{id,from,username}", limit=50):
            who = c.get("from") or {}
            if who.get("id") == me["id"] or c.get("username") == me["username"]:
                continue
            if parse_time(c["timestamp"]) < since or not matches(c.get("text"), s):
                continue
            out.append(c)
    return sorted(out, key=lambda c: c["timestamp"])


def process(g, me, now, st, s, dry=False, log=print):
    """키워드 댓글마다 DM(+공개 답글) 또는 공개 답글. 처리한 댓글 수를 돌려준다."""
    today = now.astimezone(KST).date()
    prune(st, today, s)
    zero = {"matched": 0, "dm": 0, "reply": 0, "failed": 0}
    day = st["daily"].setdefault(today.isoformat(), dict(zero))
    done, dm_blocked = 0, False
    for c in candidates(g, me, now, s):
        ck = h("c", c["id"])
        if ck in st["handled"]:
            continue
        if done >= s["max_per_run"] or day["dm"] + day["reply"] >= s["max_per_day"]:
            log(f"  · 한 번에 {s['max_per_run']}건·하루 {s['max_per_day']}건까지 — 나머지는 다음 실행")
            break
        uk = h("u", (c.get("from") or {}).get("id") or c.get("username") or c["id"])
        repeat = uk in st["users"]
        if dry:
            log(f"  · (시험) 키워드 댓글 {ck} → {'이미 DM 받은 사람이라 공개 답글만' if repeat else 'DM + 공개 답글'}")
            done += 1
            continue
        rec = {"d": today.isoformat(), "dm": False, "reply": False}
        sent = False
        if repeat:
            rec["repeat"] = True            # repeat_days 안에 이미 DM 을 받은 사람 — 공개 답글만
        elif not dm_blocked:
            try:
                g.call("POST", f"{me['id']}/messages", recipient=json.dumps({"comment_id": c["id"]}),
                       message=json.dumps({"text": dm_text(s, today.isoformat())}, ensure_ascii=False))
                sent = rec["dm"] = True
                st["users"][uk] = today.isoformat()
                day["dm"] += 1
                if st["dm"].get("ok") is not True:
                    st["dm"] = {"ok": True, "checked": today.isoformat(), "first_sent": st["dm"].get("first_sent") or today.isoformat()}
                log(f"  ✓ DM 보냄 {ck}")
            except Exception as e:  # noqa: BLE001 — 권한·창·사람 사정은 댓글마다 다르다
                k = kind_of(e)
                if k in ("token", "rate"):
                    log(f"  ✗ {'토큰 문제' if k == 'token' else '호출 한도'} — 이번 실행은 여기까지 ({short_err(e)})")
                    if k == "token":
                        raise
                    break
                if k == "permission":
                    dm_blocked = True
                    st["dm"] = {"ok": False, "checked": today.isoformat(), "error": short_err(e),
                                **({"first_sent": st["dm"]["first_sent"]} if st["dm"].get("first_sent") else {})}
                    log(f"  ✗ DM 권한 없음 — 공개 답글로 안내 ({short_err(e)})")
                else:
                    day["failed"] += 1
                    rec["dm_error"] = getattr(e, "code", None) or "?"
                    log(f"  ✗ DM 실패 {ck}: {short_err(e)}")
        day["matched"] += 1
        done += 1
        if (sent and s["public_reply"]) or (not sent and s["fallback_reply"]):
            if our_reply(c, me):
                rec["reply"] = True
            else:
                options = REPLY_SENT if sent else (REPLY_REPEAT if repeat else REPLY_FALLBACK)
                try:
                    g.call("POST", f"{c['id']}/replies", message=pick(options, ck))
                    rec["reply"] = True
                    day["reply"] += 1
                    log(f"  ✓ 공개 답글 {ck}")
                except Exception as e:  # noqa: BLE001
                    if kind_of(e) == "token":
                        raise
                    day["failed"] += 1
                    log(f"  ✗ 공개 답글 실패 {ck}: {short_err(e)}")
        st["handled"][ck] = rec
    if day == zero:                          # 숫자 칸만 새로 생긴 거면 지운다(20분마다 커밋하지 않게)
        st["daily"].pop(today.isoformat(), None)
    return done


def probe(g, me, now, st, s, log=print):
    """토큰 계정·최근 댓글 읽기·메시지 권한(대화 목록 읽기)만 본다. 보내지 않는다."""
    media = recent_media(g, me["id"], now, s)
    n = sum(len(get_all(g, f"{m['id']}/comments", pages=1, fields="id,timestamp", limit=50)) for m in media)
    log(f"  ✓ 계정 @{me['username']} · 최근 {s['lookback_days']}일 댓글 있는 게시물 {len(media)}개 · 읽은 댓글 {n}개")
    try:
        g.call("GET", f"{me['id']}/conversations", platform="instagram", limit=1)
        msg = {"ok": True}
        log("  ✓ 메시지 권한 있음(대화 목록 읽기) — 실제 DM 은 키워드 댓글이 달리면 시험된다")
    except Exception as e:  # noqa: BLE001
        if kind_of(e) == "token":
            raise
        msg = {"ok": False, "error": short_err(e)}
        log(f"  ✗ 메시지 권한 없음 — {short_err(e)}")
    st["probe"] = {"d": now.astimezone(KST).date().isoformat(), "media": len(media), "comments": n, "messages": msg}


def save_state(st, path=STATE):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(st, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--probe", action="store_true")
    args = ap.parse_args(argv)
    s = settings()
    token = os.environ.get("IG_ACCESS_TOKEN", "").strip()
    if not s["enabled"]:
        print("댓글 DM 꺼짐(config.instagram.comment_dm.enabled=false)")
        return 0
    if not token:
        print("IG_ACCESS_TOKEN 이 없어 건너뜀")
        return 0
    g = Api(token, (load_config().get("instagram") or {}).get("api_version", "v23.0"))
    now = now_kst()
    try:
        me = g.call("GET", "me", fields="user_id,username")
    except ApiError as e:
        print(f"✗ 토큰으로 계정을 못 읽음 — {short_err(e)}")
        return 1
    me = {"id": str(me.get("user_id") or me.get("id")), "username": me.get("username")}
    st = load_state()
    before = json.dumps(st, sort_keys=True, ensure_ascii=False)
    print(f"댓글 DM — 키워드 {', '.join(s['keywords'])} · 최근 {s['lookback_days']}일")
    code = 0
    try:
        if args.probe:
            probe(g, me, now, st, s)
        else:
            n = process(g, me, now, st, s, dry=args.dry_run)
            print(f"  키워드 댓글 {n}건 처리" if n else "  새 키워드 댓글 없음")
    except ApiError as e:
        print(f"✗ 멈춤 — {short_err(e)}")
        code = 1
    finally:            # 멈춰도 처리한 것까지는 기록한다(같은 댓글에 두 번 보내지 않게)
        if not args.dry_run and json.dumps(st, sort_keys=True, ensure_ascii=False) != before:
            save_state(st)
            print(f"  기록 → {STATE.relative_to(AUTOMATION.parent)}")
    return code


if __name__ == "__main__":
    sys.exit(main())
