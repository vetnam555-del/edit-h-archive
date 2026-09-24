#!/usr/bin/env python3
"""인스타그램 자동 게시 — 카드 캐러셀(10장) + 음악 릴스. post-instagram.yml 이 09:00(금 주간 특집은 18:00)에 돌린다.

공식 Instagram API(Instagram 로그인 방식, graph.instagram.com)만 쓴다. 비공식 자동화는 계정 정지 위험이 있어 쓰지 않는다.
  1) 캐러셀: GitHub Pages 에 올라간 JPEG(instagram/{키}/ig/*.jpg) 10장 → 캡션(caption.txt) → 게시 → 첫 댓글(first_comment.txt)
  2) 릴스: make_reel.py 로 만든 세로 영상(음악 포함)을 재개 업로드(rupload)로 올려 게시. 음악 출처는 캡션에 자동으로 붙는다.
게시 결과는 automation/ig_posted/{키}.json 에 남겨 같은 호를 두 번 올리지 않는다(단계별로 기록 → 중간에 실패해도 이어서).

필요한 Secrets: IG_ACCESS_TOKEN(필수) · IG_APP_SECRET(권장 — 단기 토큰을 60일 토큰으로 자동 교환)
                · GH_ADMIN_TOKEN(권장 — 교환·연장한 토큰을 Secret 에 다시 저장. 없으면 60일마다 직접 새 토큰을 넣어야 함)
  python3 automation/post_instagram.py --key 2026-09-24                 # 게시
  python3 automation/post_instagram.py --key 2026-09-24 --dry-run       # 토큰·이미지·영상 확인만(게시하지 않음)
  python3 automation/post_instagram.py --check                          # 토큰이 어느 계정인지만 확인
"""
import argparse
import base64
import datetime as dt
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from edith.common import AUTOMATION, INSTAGRAM_DIR, ROOT, load_config, now_kst  # noqa: E402

LOG_DIR = AUTOMATION / "ig_posted"


class IGError(RuntimeError):
    pass


class Graph:
    def __init__(self, token, cfg):
        self.token = token
        self.version = cfg.get("api_version", "v23.0")
        self.base = f"https://graph.instagram.com/{self.version}"

    def call(self, method, path, **params):
        params["access_token"] = self.token
        url = path if path.startswith("https://") else f"{self.base}/{path.lstrip('/')}"
        data = None
        if method == "GET":
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
        else:
            data = urllib.parse.urlencode(params).encode()
        req = urllib.request.Request(url, data=data, method=method)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            try:
                err = json.loads(body).get("error", {})
                msg = err.get("error_user_msg") or err.get("message") or body
                raise IGError(f"{e.code} {err.get('type', '')} (code {err.get('code')}): {msg}") from None
            except ValueError:
                raise IGError(f"{e.code}: {body[:300]}") from None
        except urllib.error.URLError as e:
            raise IGError(f"접속 실패: {e.reason}") from None

    def wait_ready(self, container_id, what, timeout=600):
        """컨테이너 처리 완료(FINISHED)까지 기다린다. 영상은 몇 분 걸릴 수 있다."""
        start = time.time()
        while True:
            st = self.call("GET", container_id, fields="status_code,status")
            code = st.get("status_code")
            if code == "FINISHED":
                return
            if code in ("ERROR", "EXPIRED"):
                raise IGError(f"{what} 처리 실패: {st.get('status') or code}")
            if time.time() - start > timeout:
                raise IGError(f"{what} 처리가 {timeout // 60}분 안에 끝나지 않았습니다 (마지막 상태 {code})")
            time.sleep(8)


def load_log(key):
    p = LOG_DIR / f"{key}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def save_log(key, log):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    (LOG_DIR / f"{key}.json").write_text(json.dumps(log, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def wait_public(urls, timeout=900):
    """GitHub Pages 배포가 끝나 이미지가 공개 주소로 열릴 때까지 기다린다(인스타 서버가 이 주소에서 가져간다)."""
    start, pending = time.time(), list(urls)
    while pending:
        still = []
        for u in pending:
            try:
                req = urllib.request.Request(u, method="HEAD")
                with urllib.request.urlopen(req, timeout=20) as r:
                    if r.status != 200 or "jpeg" not in (r.headers.get("Content-Type") or ""):
                        still.append(u)
            except (urllib.error.URLError, OSError):
                still.append(u)
        pending = still
        if pending:
            if time.time() - start > timeout:
                raise IGError(f"공개 주소에서 이미지를 열 수 없습니다(Pages 배포 확인): {pending[0]}")
            time.sleep(20)


def post_carousel(g, uid, key, folder, site_url, dry):
    jpgs = sorted((folder / "ig").glob("*.jpg"))
    if not 2 <= len(jpgs) <= 10:
        raise IGError(f"캐러셀은 JPEG 2~10장이어야 합니다(지금 {len(jpgs)}장, {folder / 'ig'})")
    urls = [f"{site_url}/instagram/{key}/ig/{p.name}" for p in jpgs]
    wait_public(urls)
    children = [g.call("POST", f"{uid}/media", image_url=u, is_carousel_item="true")["id"] for u in urls]
    caption = (folder / "caption.txt").read_text(encoding="utf-8").strip()
    parent = g.call("POST", f"{uid}/media", media_type="CAROUSEL", children=",".join(children), caption=caption)["id"]
    g.wait_ready(parent, "캐러셀")
    if dry:
        print(f"  (dry-run) 캐러셀 컨테이너 준비 완료 — {len(children)}장, 게시하지 않음")
        return None
    media_id = g.call("POST", f"{uid}/media_publish", creation_id=parent)["id"]
    return media_id


def reel_caption(folder, track):
    cap = (folder / "caption.txt").read_text(encoding="utf-8").strip().splitlines()
    hook = cap[0] if cap else ""
    tags = next((line for line in reversed(cap) if line.startswith("#")), "")
    n = len(list(folder.glob("[0-9][0-9]_edit_h_*.png"))) or 10
    lines = [hook, "", f"카드 {n}장 전체는 피드 게시물에서 저장해두세요 📌",
             "📩 매일 아침 트렌드 뉴스레터는 프로필 링크에서"]
    if track:
        credit = f"🎵 {track['title']} — {track['artist']}"
        if track.get("license", "").upper() != "CC0":
            credit += f" ({track['license']}, {track.get('source_name', 'Wikimedia Commons')})"
        lines.append(credit)
    lines += ["/ 에디터. H", tags]
    return "\n".join(lines).strip()


def post_reel(g, uid, key, folder, cfg, dry, ffmpeg):
    out = folder / "reel.mp4"
    proc = subprocess.run([sys.executable, str(AUTOMATION / "make_reel.py"), key, "--out", str(out), "--ffmpeg", ffmpeg],
                          capture_output=True, text=True)
    if proc.returncode == 3:
        print("  " + proc.stdout.strip())
        return None, None
    if proc.returncode != 0:
        raise IGError(f"릴스 영상 만들기 실패: {(proc.stderr or proc.stdout)[-800:]}")
    info = json.loads(proc.stdout.strip().splitlines()[-1])
    track = info["track"]
    print(f"  릴스 영상 {out.stat().st_size // 1024}KB — 음악: {track['title']} / {track['artist']}")
    if dry:
        print("  (dry-run) 릴스는 업로드하지 않음")
        return None, track
    params = {"media_type": "REELS", "upload_type": "resumable", "caption": reel_caption(folder, track),
              "share_to_feed": "true" if cfg.get("reel_share_to_feed") else "false", "thumb_offset": "800"}
    created = g.call("POST", f"{uid}/media", **params)
    cid = created["id"]
    upload_url = created.get("uri") or f"https://rupload.facebook.com/ig-api-upload/{g.version}/{cid}"
    data = out.read_bytes()
    req = urllib.request.Request(upload_url, data=data, method="POST", headers={
        "Authorization": f"OAuth {g.token}", "offset": "0", "file_size": str(len(data))})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            r.read()
    except urllib.error.HTTPError as e:
        raise IGError(f"릴스 업로드 실패 {e.code}: {e.read().decode(errors='replace')[:300]}") from None
    g.wait_ready(cid, "릴스", timeout=900)
    return g.call("POST", f"{uid}/media_publish", creation_id=cid)["id"], track


def _save_secret(new_token):
    """GitHub Secret IG_ACCESS_TOKEN 을 새 토큰으로 바꾼다(GH_ADMIN_TOKEN 필요). 토큰 값은 절대 로그에 찍지 않는다."""
    admin, repo = os.environ.get("GH_ADMIN_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    if not (admin and repo):
        return False
    from nacl import encoding, public  # pip install pynacl (워크플로에서 설치)
    api = f"https://api.github.com/repos/{repo}/actions/secrets"
    hdr = {"Authorization": f"Bearer {admin}", "Accept": "application/vnd.github+json"}
    with urllib.request.urlopen(urllib.request.Request(f"{api}/public-key", headers=hdr), timeout=30) as r:
        pk = json.loads(r.read())
    box = public.SealedBox(public.PublicKey(pk["key"].encode(), encoding.Base64Encoder()))
    body = json.dumps({"encrypted_value": base64.b64encode(box.encrypt(new_token.encode())).decode(),
                       "key_id": pk["key_id"]}).encode()
    req = urllib.request.Request(f"{api}/IG_ACCESS_TOKEN", data=body, method="PUT",
                                 headers={**hdr, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30):
        pass
    return True


def _token_call(url, params):
    try:
        with urllib.request.urlopen(url + "?" + urllib.parse.urlencode(params), timeout=30) as r:
            return json.loads(r.read())["access_token"]
    except urllib.error.HTTPError as e:
        raise IGError(f"{e.code} {e.read().decode(errors='replace')[:200]}") from None


def maintain_token(token):
    """토큰 관리. 돌려준 토큰으로 이번 실행을 한다.
    1) IG_APP_SECRET 이 있고 아직 확인 전이면 단기 토큰(1~2시간)을 60일 장기 토큰으로 바꿔 Secret 에 저장한다.
    2) 장기 토큰은 7일마다 연장(60일 재시작)해 Secret 에 저장한다 — 사람이 60일마다 새로 넣지 않아도 되게."""
    state_path = LOG_DIR / "_token.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    today = now_kst().date()

    def save_state():
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state) + "\n", encoding="utf-8")

    app_secret = os.environ.get("IG_APP_SECRET", "").strip()
    if app_secret and not state.get("long_lived"):
        try:
            new = _token_call("https://graph.instagram.com/access_token",
                              {"grant_type": "ig_exchange_token", "client_secret": app_secret, "access_token": token})
            if _save_secret(new):
                print("  ✓ 단기 토큰을 60일 장기 토큰으로 바꿔 Secret 에 저장했습니다")
            else:
                print("  ⚠ 장기 토큰으로 바꿨지만 GH_ADMIN_TOKEN 이 없어 저장하지 못했습니다 — 다음 실행 때 토큰이 만료될 수 있습니다")
            token = new
            state.update(long_lived=True, refreshed=today.isoformat())
            save_state()
            return token
        except IGError:
            state["long_lived"] = True  # 교환이 거절되면 이미 장기 토큰이다
            save_state()

    last = dt.date.fromisoformat(state["refreshed"]) if state.get("refreshed") else None
    if last and (today - last).days < 7:
        return token
    if not (os.environ.get("GH_ADMIN_TOKEN") and os.environ.get("GITHUB_REPOSITORY")):
        print("  ⚠ GH_ADMIN_TOKEN 이 없어 토큰 자동 연장을 건너뜀 — 60일마다 IG_ACCESS_TOKEN 을 새로 넣어야 합니다")
        return token
    try:
        new = _token_call("https://graph.instagram.com/refresh_access_token",
                          {"grant_type": "ig_refresh_token", "access_token": token})
        _save_secret(new)
        state.update(long_lived=True, refreshed=today.isoformat())
        save_state()
        print("  ✓ 인스타 토큰을 60일 연장하고 Secret 을 갱신했습니다")
        return new
    except Exception as e:  # 연장 실패(발급 24시간 안 된 토큰 등)는 게시를 막지 않는다
        print(f"  ⚠ 토큰 연장은 다음에 다시 시도합니다({type(e).__name__})")
        return token


def prune(days):
    """게시가 끝난 지 오래된 호의 게시용 JPEG(ig/)는 지운다 — Pages 용량(1GB) 관리. 카드 PNG·갤러리는 그대로 둔다."""
    cutoff = now_kst().date() - dt.timedelta(days=days)
    for d in INSTAGRAM_DIR.glob("*/ig"):
        m = re.match(r"(\d{4}-\d{2}-\d{2})", d.parent.name)
        if m and dt.date.fromisoformat(m.group(1)) < cutoff and (LOG_DIR / f"{d.parent.name}.json").exists():
            for f in d.glob("*.jpg"):
                f.unlink()
            d.rmdir()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", help="instagram/ 폴더 이름 — YYYY-MM-DD 또는 YYYY-MM-DD-weekly (기본: 오늘 KST)")
    ap.add_argument("--kind", choices=["daily", "weekly"], default="daily")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--only", choices=["carousel", "reel"])
    ap.add_argument("--ffmpeg", default="ffmpeg")
    args = ap.parse_args()

    cfg_all = load_config()
    cfg = cfg_all.get("instagram") or {}
    token = os.environ.get("IG_ACCESS_TOKEN", "").strip()
    if not token:
        print("✗ IG_ACCESS_TOKEN Secret 이 없습니다 — automation/README.md '인스타그램 자동 게시' 설정을 먼저 하세요. 건너뜁니다.")
        return
    g = Graph(token, cfg)
    try:
        me = g.call("GET", "me", fields="user_id,username")
    except IGError as e:
        hint = ("graph.instagram.com 에 접속하지 못했습니다(네트워크)" if str(e).startswith("접속 실패")
                else "토큰이 만료됐거나 잘못됐습니다. README 의 순서로 새 토큰을 받아 IG_ACCESS_TOKEN 에 넣으세요")
        sys.exit(f"✗ 토큰 확인 실패: {e}\n  {hint}.")
    uid = me.get("user_id") or me.get("id")
    print(f"인스타 계정 @{me.get('username')} (id {uid})")
    if args.check:
        return
    if not cfg.get("auto_post", True) and not args.key:
        print("config.instagram.auto_post 가 꺼져 있어 예약 게시를 건너뜁니다")
        return
    token = maintain_token(token)
    g.token = token

    key = args.key or now_kst().date().isoformat() + ("-weekly" if args.kind == "weekly" else "")
    folder = INSTAGRAM_DIR / key
    if not (folder / "caption.txt").exists():
        print(f"{key}: 게시할 카드가 없습니다(발행하지 않은 날) — 건너뜀")
        return
    log = load_log(key)
    site_url = cfg_all["site_url"].rstrip("/")
    failures = []

    if args.only != "reel" and not log.get("carousel"):
        try:
            print("캐러셀 게시 중…")
            media_id = post_carousel(g, uid, key, folder, site_url, args.dry_run)
            if media_id:
                log["carousel"] = {"id": media_id, "at": now_kst().isoformat(timespec="seconds")}
                save_log(key, log)
                try:
                    link = g.call("GET", media_id, fields="permalink").get("permalink")
                    log["carousel"]["permalink"] = link
                    save_log(key, log)
                    print(f"  ✓ 캐러셀 게시 {link}")
                except IGError:
                    print(f"  ✓ 캐러셀 게시 (id {media_id})")
                comment = (folder / "first_comment.txt")
                if comment.exists() and comment.read_text(encoding="utf-8").strip():
                    try:
                        g.call("POST", f"{media_id}/comments", message=comment.read_text(encoding="utf-8").strip())
                        log["carousel"]["first_comment"] = True
                        save_log(key, log)
                        print("  ✓ 첫 댓글")
                    except IGError as e:
                        print(f"  ⚠ 첫 댓글 실패: {e}")
        except IGError as e:
            failures.append(f"캐러셀: {e}")
    elif log.get("carousel"):
        print(f"캐러셀은 이미 게시됨 ({log['carousel'].get('permalink') or log['carousel']['id']})")

    want_reel = cfg.get("reel", True) and (args.kind == "daily" or cfg.get("weekly_reel", True))
    if args.only != "carousel" and want_reel and not log.get("reel"):
        try:
            print("릴스 준비 중…")
            media_id, track = post_reel(g, uid, key, folder, cfg, args.dry_run, args.ffmpeg)
            if media_id:
                log["reel"] = {"id": media_id, "at": now_kst().isoformat(timespec="seconds"), "track": track["title"]}
                save_log(key, log)
                try:
                    log["reel"]["permalink"] = g.call("GET", media_id, fields="permalink").get("permalink")
                    save_log(key, log)
                except IGError:
                    pass
                print(f"  ✓ 릴스 게시 {log['reel'].get('permalink') or media_id}")
        except IGError as e:
            failures.append(f"릴스: {e}")
        finally:
            (folder / "reel.mp4").unlink(missing_ok=True)  # 영상은 저장소에 두지 않는다
    elif log.get("reel"):
        print("릴스는 이미 게시됨")

    if not args.dry_run:
        prune(int(cfg.get("keep_jpeg_days", 14)))
    if failures:
        sys.exit("✗ 일부 실패:\n  - " + "\n  - ".join(failures))


if __name__ == "__main__":
    main()
