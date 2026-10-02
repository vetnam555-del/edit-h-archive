#!/usr/bin/env python3
"""EDIT H 스레드(Threads) 자동 게시 — 2026-10-02 성장 검토(국내 스레드 월 이용자 약 630만, 글 중심이라 뉴스레터와 결이 맞다).

THREADS_ACCESS_TOKEN Secret 이 없으면 아무것도 하지 않고 끝난다(사용자가 Meta 앱에서 토큰을 발급해 넣으면 그날부터 돈다 —
automation/OWNER_TODO.md). 하루 한 번, 점심(12:30 KST)에 그날 호를 올린다:

  본문(500자 안) = 질문 제목 → H PICK 숫자·결론 → 나머지 4가지 태그 → 답하기 쉬운 질문 하나(스레드는 답글이 퍼짐을 가른다)
  이미지 = 그날 카드 앞 5장(캐러셀 — 인스타 게시용 JPEG 를 GitHub Pages 공개 주소로)
  답글 1개 = 뉴스레터 구독 링크(?ref=threads — 본문에 링크를 넣지 않는다)

기록: automation/threads_posted/{날짜}.json(게시 id·시각·주소). 같은 날 두 번 올리지 않는다. 토큰 값은 절대 로그에 찍지 않는다.

  python3 automation/post_threads.py --check            # 토큰·계정 확인만
  python3 automation/post_threads.py --dry-run           # 본문·이미지 주소만 출력(게시 안 함)
  python3 automation/post_threads.py [--key 2026-10-03]  # 게시
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from edith.common import AUTOMATION, CONTENT_DIR, INSTAGRAM_DIR, load_config, now_kst  # noqa: E402

API = "https://graph.threads.net/v1.0"
LOG_DIR = AUTOMATION / "threads_posted"
TOKEN_LOG = LOG_DIR / "token.json"     # 마지막 연장 날짜만(토큰 값은 남기지 않는다)
MAX_TEXT = 500
REFRESH_DAYS = 7                       # 장기 토큰(60일)을 일주일마다 연장


class ThreadsError(Exception):
    pass


def call(method, path, token, **params):
    params["access_token"] = token
    url = path if path.startswith("https://") else f"{API}/{path.lstrip('/')}"
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
            err = json.loads(body).get("error", {})
            raise ThreadsError(f"{e.code} {err.get('type', '')} (code {err.get('code')}): {err.get('message', '')[:200]}") from None
        except (ValueError, AttributeError):
            raise ThreadsError(f"{e.code} {body[:200]}") from None
    except urllib.error.URLError as e:
        raise ThreadsError(f"접속 실패: {e.reason}") from None


def wait_ready(cid, token, what, timeout=300):
    start = time.time()
    while True:
        st = call("GET", cid, token, fields="status,error_message")
        if st.get("status") == "FINISHED":
            return
        if st.get("status") in ("ERROR", "EXPIRED"):
            raise ThreadsError(f"{what} 처리 실패: {st.get('error_message') or st.get('status')}")
        if time.time() - start > timeout:
            raise ThreadsError(f"{what} 처리가 {timeout}초 안에 끝나지 않았습니다(상태 {st.get('status')})")
        time.sleep(5)


def _plain(s):
    return re.sub(r"==|\*\*", "", str(s or "")).replace("\n", " ").strip()


def compose(c, site_url):
    """(본문, 구독 답글). 본문은 500자 안 — 넘으면 태그 줄부터 뺀다."""
    pick = (c.get("cards") or {}).get("issues", [{}])[0]
    number = (pick.get("compare") or {}).get("to", {}).get("value") or pick.get("number") or ""
    head = _plain(pick.get("headline"))
    takeaway = _plain(pick.get("takeaway") or (c.get("big_issue") or {}).get("takeaway"))
    tags = " · ".join(it["tag"] for it in c.get("items") or [])
    ask = _plain((c.get("instagram") or {}).get("ask") or (c.get("question") or {}).get("text"))
    lines = [_plain(c["title"]), "", f"{head}" + (f" — {number}" if number and number not in head else ""),
             f"그래서? {takeaway}" if takeaway else "", "", f"오늘 나머지: {tags}" if tags else "", "", ask]
    text = "\n".join(lines).strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    if len(text) > MAX_TEXT:
        text = re.sub(r"\n*오늘 나머지:[^\n]*", "", text)
    text = text[:MAX_TEXT]
    reply = f"숫자·출처 전문은 매일 아침 8시 뉴스레터로 보내드려요 → {site_url}/subscribe.html?ref=threads"
    return text, reply


def images(key, site_url, n=5):
    jpgs = sorted((INSTAGRAM_DIR / key / "ig").glob("*.jpg"))[:n]
    return [f"{site_url}/instagram/{key}/ig/{p.name}" for p in jpgs]


def maybe_refresh(token):
    """장기 토큰을 REFRESH_DAYS 마다 연장하고 GitHub Secret 을 바꾼다(GH_ADMIN_TOKEN 이 있을 때). 실패해도 게시는 계속."""
    last = None
    if TOKEN_LOG.exists():
        last = json.loads(TOKEN_LOG.read_text(encoding="utf-8")).get("refreshed")
    today = now_kst().date()
    if last and (today - dt.date.fromisoformat(last)).days < REFRESH_DAYS:
        return token
    try:
        new = call("GET", "https://graph.threads.net/refresh_access_token", token, grant_type="th_refresh_token")["access_token"]
        from post_instagram import _save_secret
        if _save_secret(new, name="THREADS_ACCESS_TOKEN"):
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            TOKEN_LOG.write_text(json.dumps({"refreshed": today.isoformat()}) + "\n", encoding="utf-8")
            print("  스레드 토큰을 연장했습니다(60일)")
            return new
        print("  ⚠ GH_ADMIN_TOKEN 이 없어 연장한 토큰을 저장하지 못했습니다 — 60일 안에 새 토큰을 넣어 주세요")
    except (ThreadsError, KeyError, OSError) as e:
        print(f"  ⚠ 스레드 토큰 연장은 다음에 다시({type(e).__name__})")
    return token


def post(key, token, uid, site_url, dry):
    c = json.loads((CONTENT_DIR / f"{key}.json").read_text(encoding="utf-8"))
    text, reply = compose(c, site_url)
    urls = images(key, site_url)
    print(f"── 본문({len(text)}자) ──\n{text}\n── 이미지 {len(urls)}장 · 답글: {reply}")
    if dry:
        return None
    if len(urls) >= 2:
        children = []
        for u in urls:
            cid = call("POST", f"{uid}/threads", token, media_type="IMAGE", image_url=u, is_carousel_item="true")["id"]
            children.append(cid)
        for cid in children:
            wait_ready(cid, token, "이미지")
        parent = call("POST", f"{uid}/threads", token, media_type="CAROUSEL", children=",".join(children), text=text)["id"]
    else:
        parent = call("POST", f"{uid}/threads", token, media_type="TEXT", text=text)["id"]
    wait_ready(parent, token, "게시물")
    media_id = call("POST", f"{uid}/threads_publish", token, creation_id=parent)["id"]
    log = {"id": media_id, "at": now_kst().isoformat(timespec="seconds"), "images": len(urls)}
    try:
        log["permalink"] = call("GET", media_id, token, fields="permalink").get("permalink")
    except ThreadsError:
        pass
    try:   # 구독 링크는 답글로(본문 링크는 퍼짐을 줄인다)
        rid = call("POST", f"{uid}/threads", token, media_type="TEXT", text=reply, reply_to_id=media_id)["id"]
        wait_ready(rid, token, "답글")
        call("POST", f"{uid}/threads_publish", token, creation_id=rid)
        log["reply"] = True
    except ThreadsError as e:
        print(f"  ⚠ 구독 링크 답글 실패: {e}")
    return log


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", help="게시할 호 YYYY-MM-DD (기본 오늘 KST)")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    token = os.environ.get("THREADS_ACCESS_TOKEN", "").strip()
    cfg = load_config()
    site_url = cfg["site_url"].rstrip("/")
    key = args.key or now_kst().date().isoformat()
    if not token:
        print("THREADS_ACCESS_TOKEN Secret 이 없어 스레드 게시는 건너뜁니다(설정: automation/OWNER_TODO.md)")
        if args.dry_run and (CONTENT_DIR / f"{key}.json").exists():
            post(key, "", "me", site_url, dry=True)
        return 0
    try:
        me = call("GET", "me", token, fields="id,username")
    except ThreadsError as e:
        sys.exit(f"✗ 스레드 토큰 확인 실패: {e} — 토큰이 만료됐으면 OWNER_TODO.md 순서로 새로 넣어 주세요")
    print(f"스레드 계정 @{me.get('username')}")
    if args.check:
        return 0
    if not (CONTENT_DIR / f"{key}.json").exists() or not (INSTAGRAM_DIR / key / "caption.txt").exists():
        print(f"{key}: 오늘 호가 없습니다 — 건너뜀")
        return 0
    if json.loads((CONTENT_DIR / f"{key}.json").read_text(encoding="utf-8")).get("rewind"):
        print(f"{key}: 예비 호(다시 보기) — 스레드에는 올리지 않습니다")
        return 0
    log_path = LOG_DIR / f"{key}.json"
    if log_path.exists() and not args.dry_run:
        print(f"{key}: 이미 올렸습니다 — 건너뜀")
        return 0
    if not args.dry_run:   # 드라이런은 출력만 — 토큰 연장(Secret 변경)·기록을 하지 않는다
        token = maybe_refresh(token)
    log = post(key, token, me["id"], site_url, args.dry_run)
    if log:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_path.write_text(json.dumps(log, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"✓ 스레드 게시 {log.get('permalink') or log['id']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
