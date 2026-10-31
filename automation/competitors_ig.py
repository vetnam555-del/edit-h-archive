#!/usr/bin/env python3
"""경쟁 매체 인스타그램 공개 지표 — 메타 공식 '비즈니스 탐색(Business Discovery)' API 로 주 1회 모은다.

2026-11-01 운영자 "인스타 왜 막혀있는거야? 보게끔해줘 경쟁사도 못보면 개선하는데 영향이 있잖아".
인스타 화면은 로그인하지 않은 자동 접속에 거의 보이지 않고, 약관이 허락 없는 자동 수집을 막는다 — 그래서 페이지를 긁지 않고 공식 API 만 쓴다.
비즈니스 탐색은 '페이스북 로그인 방식'(graph.facebook.com)에만 있다. 게시에 쓰는 IG_ACCESS_TOKEN(인스타그램 로그인 방식,
graph.instagram.com)으로는 안 된다 — 운영자가 따로 만든 IG_FB_TOKEN·IG_FB_USER_ID(GitHub Secrets)가 필요하다(OWNER_TODO 맨 위).
토큰이 없으면 아무것도 하지 않고 0 으로 끝난다(워크플로가 실패로 보이지 않게).

대상: config competitors_ig.accounts — 공식 사이트·뉴스레터에서 확인한 계정. 프로 계정(비즈니스·크리에이터)만 보인다.
공개 저장소라 공개 숫자와 게시물 주소만 남긴다(캡션은 첫 줄 앞부분만, 프로필 사진은 파일로 받지 않고 임시 주소만):
  automation/competitors/ig/{날짜}.json — 계정별 팔로워·게시물 수·프로필 사진 주소·최근 게시물 지표
  automation/competitors/ig/summary.md — 최근 14일 게시 수·게시물당 좋아요·댓글·참여율·형식 비율·주로 올리는 시각, 지난 수집 대비 팔로워

  python3 automation/competitors_ig.py             # 모아 저장(오늘 이미 모았으면 건너뜀)
  python3 automation/competitors_ig.py --dry-run   # 모아서 요약만 출력, 저장 안 함
  python3 automation/competitors_ig.py --force     # 오늘 이미 모았어도 다시
종료 코드: 0 = 저장했거나 토큰 없음·오늘 이미 모음, 1 = 모든 계정 실패(토큰 만료 등 — 사유를 출력).
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from edith.common import KST, ROOT, load_config, now_kst  # noqa: E402

OUT = ROOT / "automation" / "competitors" / "ig"
GRAPH = "https://graph.facebook.com"
HANDLE_RE = re.compile(r"^[A-Za-z0-9._]{1,30}$")
DAY_FILE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.json$")
WINDOW_DAYS = 14
MEDIA_FIELDS = "id,timestamp,like_count,comments_count,media_type,media_product_type,permalink,caption"
UA = "EDIT-H-competitors/1.0 (+https://github.com/vetnam555-del/edit-h-archive)"


def settings(cfg=None):
    """([{handle, name, self}], 계정당 게시물 수, API 버전). 계정 이름 형식이 틀리면 ValueError."""
    cfg = cfg or load_config()
    c = cfg.get("competitors_ig") or {}
    accounts = []
    for a in c.get("accounts") or []:
        handle = str(a.get("handle") or "")
        if not HANDLE_RE.match(handle):
            raise ValueError(f"인스타 계정 이름 형식이 아니다: {handle!r}")
        accounts.append({"handle": handle, "name": str(a.get("name") or handle), "self": bool(a.get("self"))})
    version = (cfg.get("instagram") or {}).get("api_version") or "v23.0"
    return accounts, int(c.get("media_limit") or 25), version


def fields_for(handle, limit):
    """business_discovery 필드 식 — 프로필 숫자 + 최근 게시물 limit 개."""
    return (f"business_discovery.username({handle})"
            f"{{username,name,profile_picture_url,followers_count,follows_count,media_count,"
            f"media.limit({limit}){{{MEDIA_FIELDS}}}}}")


def describe_error(err, status=None):
    """그래프 API 오류를 운영 문장으로(토큰은 넣지 않는다)."""
    code = err.get("code")
    if code == 190:
        return "토큰 만료·무효(190) — OWNER_TODO '경쟁 매체 인스타 토큰'대로 다시 만든다"
    if code in (4, 17, 32, 613):
        return f"호출 한도({code}) — 다음 수집 때 다시"
    if code in (10, 200):
        return f"권한 부족({code}) — instagram_basic·pages_show_list·pages_read_engagement 권한을 확인한다"
    message = re.sub(r"\s+", " ", str(err.get("message") or ""))[:140]
    return f"API 오류 {code or status}: {message}".rstrip(": ")


def fetch(handle, limit, version, user_id, token):
    """한 계정의 business_discovery 응답(dict). 실패하면 RuntimeError(메시지에 토큰·주소를 넣지 않는다)."""
    query = urllib.parse.urlencode({"fields": fields_for(handle, limit), "access_token": token})
    req = urllib.request.Request(f"{GRAPH}/{version}/{user_id}?{query}", headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read().decode("utf-8")).get("error") or {}
        except (ValueError, OSError):
            err = {}
        raise RuntimeError(describe_error(err, e.code)) from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise RuntimeError(f"접속 실패: {type(getattr(e, 'reason', e)).__name__}") from None
    found = data.get("business_discovery")
    if not found:
        raise RuntimeError("응답에 business_discovery 가 없다")
    return found


def media_format(m):
    if (m.get("media_product_type") or "").upper() == "REELS":
        return "릴스"
    return {"CAROUSEL_ALBUM": "캐러셀", "IMAGE": "사진", "VIDEO": "영상"}.get((m.get("media_type") or "").upper(), "기타")


def first_line(text, n=60):
    line = next((s.strip() for s in str(text or "").splitlines() if s.strip()), "")
    return line if len(line) <= n else line[: n - 1] + "…"


def parse_time(s):
    try:
        return datetime.strptime(str(s), "%Y-%m-%dT%H:%M:%S%z").astimezone(KST)
    except ValueError:
        return None


def _mean(values):
    values = [v for v in values if isinstance(v, (int, float))]
    return round(sum(values) / len(values), 1) if values else None


def summarize(found, now):
    """business_discovery 응답 → 저장할 계정 기록(최근 WINDOW_DAYS 일 통계 포함)."""
    posts = []
    for m in (found.get("media") or {}).get("data") or []:
        t = parse_time(m.get("timestamp"))
        if not t:
            continue
        posts.append({"time": t.strftime("%Y-%m-%d %H:%M"), "format": media_format(m),
                      "likes": m.get("like_count"), "comments": m.get("comments_count"),
                      "permalink": m.get("permalink"), "caption": first_line(m.get("caption")), "_t": t})
    since = now - timedelta(days=WINDOW_DAYS)
    recent = [p for p in posts if p["_t"] >= since]
    followers = found.get("followers_count")
    likes, comments = _mean(p["likes"] for p in recent), _mean(p["comments"] for p in recent)
    engagement = None
    if followers and likes is not None:
        engagement = round((likes + (comments or 0)) / followers * 100, 2)
    formats = Counter(p["format"] for p in recent)
    hours = Counter(p["_t"].hour for p in (recent or posts))
    top = max(recent, key=lambda p: (p["likes"] or 0) + (p["comments"] or 0), default=None)
    stats = {
        "window_days": WINDOW_DAYS,
        "posts": len(recent),
        "avg_likes": likes,
        "avg_comments": comments,
        "engagement_pct": engagement,
        "formats": {k: round(v / len(recent) * 100) for k, v in formats.most_common()} if recent else {},
        "top_hour_kst": hours.most_common(1)[0][0] if hours else None,
        "top_post": {k: top[k] for k in ("time", "format", "likes", "comments", "permalink", "caption")} if top else None,
    }
    for p in posts:
        p.pop("_t")
    return {"username": found.get("username"), "followers": followers, "follows": found.get("follows_count"),
            "media_count": found.get("media_count"), "profile_picture_url": found.get("profile_picture_url"),
            "stats": stats, "posts": posts}


def collect(accounts, get, now):
    """계정마다 get(handle) → 기록. 한 계정이 실패해도 나머지는 모은다."""
    out = []
    for a in accounts:
        row = {"handle": a["handle"], "name": a["name"], "self": a["self"]}
        try:
            row.update(ok=True, **summarize(get(a["handle"]), now))
        except RuntimeError as e:
            row.update(ok=False, error=str(e))
        out.append(row)
    return out


def previous_followers(day, folder=OUT):
    """오늘보다 앞선 마지막 수집의 {handle: 팔로워} (없으면 {})."""
    names = [DAY_FILE.match(f.name) for f in folder.glob("*.json")] if folder.exists() else []
    days = sorted(m.group(1) for m in names if m and m.group(1) < day)
    if not days:
        return {}, None
    data = json.loads((folder / f"{days[-1]}.json").read_text(encoding="utf-8"))
    return {r["handle"]: r.get("followers") for r in data.get("accounts") or [] if r.get("ok")}, days[-1]


def _num(v, unit=""):
    if v is None:
        return "–"
    if isinstance(v, float) and not v.is_integer():
        return f"{v:,.1f}{unit}"
    return f"{int(v):,}{unit}"


def render(results, prev, prev_day, now):
    """요약표(마크다운). 우리 계정이 맨 위, 나머지는 팔로워 많은 순."""
    ok = [r for r in results if r["ok"]]
    ok.sort(key=lambda r: (not r["self"], -(r.get("followers") or 0)))
    lines = [f"# 경쟁 매체 인스타 — 공식 '비즈니스 탐색' API ({now:%Y-%m-%d %H:%M} KST 자동 생성)", "",
             f"최근 {WINDOW_DAYS}일 게시물 기준. 참여율 = 게시물당 (좋아요+댓글) ÷ 팔로워. 좋아요를 숨긴 계정은 '–'.",
             f"지난 수집: {prev_day or '없음(첫 수집)'}. 만든 곳: `automation/competitors_ig.py`(주 1회, `.github/workflows/competitors-ig.yml`).", "",
             f"| 매체 | 팔로워 | 지난 수집 대비 | {WINDOW_DAYS}일 게시 | 게시물당 좋아요 | 댓글 | 참여율 | 형식 | 주로 올리는 시각 |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in ok:
        s = r["stats"]
        before = prev.get(r["handle"])
        delta = "–" if before is None or r.get("followers") is None else f"{r['followers'] - before:+,}"
        fmt = " · ".join(f"{k} {v}%" for k, v in s["formats"].items()) or "–"
        hour = "–" if s["top_hour_kst"] is None else f"{s['top_hour_kst']:02d}시"
        name = f"**{r['name']}**" if r["self"] else r["name"]
        lines.append(f"| {name} (@{r['handle']}) | {_num(r.get('followers'))} | {delta} | {s['posts']} | "
                     f"{_num(s['avg_likes'])} | {_num(s['avg_comments'])} | {_num(s['engagement_pct'], '%')} | {fmt} | {hour} |")
    tops = [r for r in ok if r["stats"]["top_post"] and not r["self"]]
    if tops:
        lines += ["", f"## {WINDOW_DAYS}일 동안 반응이 가장 컸던 게시물", ""]
        for r in tops:
            t = r["stats"]["top_post"]
            lines.append(f"- {r['name']}: {t['format']} · 좋아요 {_num(t['likes'])} · 댓글 {_num(t['comments'])} · {t['time']} — "
                         f"「{t['caption'] or '(캡션 없음)'}」 {t['permalink'] or ''}".rstrip())
    failed = [r for r in results if not r["ok"]]
    if failed:
        lines += ["", "## 못 가져온 계정", ""]
        lines += [f"- {r['name']} (@{r['handle']}): {r['error']}" for r in failed]
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true", help="모아서 요약만 출력, 저장 안 함")
    ap.add_argument("--force", action="store_true", help="오늘 이미 모았어도 다시")
    args = ap.parse_args(argv)
    token = os.environ.get("IG_FB_TOKEN", "").strip()
    user_id = os.environ.get("IG_FB_USER_ID", "").strip()
    if not token or not user_id:
        print("IG_FB_TOKEN·IG_FB_USER_ID 가 없어 건너뜀 — 경쟁 매체 인스타 수집은 운영자가 토큰을 넣은 뒤부터(OWNER_TODO 맨 위)")
        return 0
    if not user_id.isdigit():
        print("IG_FB_USER_ID 는 숫자로 된 인스타 비즈니스 계정 ID 여야 한다(OWNER_TODO 맨 위 3단계)")
        return 1
    accounts, limit, version = settings()
    now = now_kst()
    day = now.strftime("%Y-%m-%d")
    path = OUT / f"{day}.json"
    if path.exists() and not (args.force or args.dry_run):
        print(f"오늘({day}) 이미 모았다 — 건너뜀(다시 모으려면 --force)")
        return 0
    results = collect(accounts, lambda h: fetch(h, limit, version, user_id, token), now)
    prev, prev_day = previous_followers(day)
    md = render(results, prev, prev_day, now)
    good = sum(r["ok"] for r in results)
    if args.dry_run:
        print(md)
    else:
        OUT.mkdir(parents=True, exist_ok=True)
        record = {"collected_at": now.strftime("%Y-%m-%d %H:%M KST"), "api_version": version,
                  "window_days": WINDOW_DAYS, "accounts": results}
        path.write_text(json.dumps(record, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        (OUT / "summary.md").write_text(md, encoding="utf-8")
        print(f"✓ 경쟁 매체 {good}/{len(results)}개 계정 — {path.relative_to(ROOT)}")
    for r in results:
        if not r["ok"]:
            print(f"  ✗ {r['name']} (@{r['handle']}): {r['error']}")
    return 0 if good else 1


if __name__ == "__main__":
    sys.exit(main())
