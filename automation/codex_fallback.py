#!/usr/bin/env python3
"""Claude 가 멈춘 날 ChatGPT Codex 가 GitHub Actions 에서 이어서 한다(.github/workflows/codex-fallback.yml, 2026-10-25 운영자 결정).

Claude 는 사용량이 바닥나는 순간을 미리 알 수 없다. 그래서 '시작했다는 표시(claim)'로 판단한다:
  · 07:40 제작 루틴(Claude)은 시작하자마자 `python3 automation/codex_fallback.py claim claude` 로 표시를 남긴다(RUNBOOK 0단계).
    표시는 main 이 아닌 가지 `run-claim/{날짜}-claude` 라 워크플로를 깨우지 않는다.
  · 07:55 까지 Claude 표시도 오늘 호도 없으면 Codex 가 `run-claim/{날짜}-codex` 를 남기고 제작한다. 늦게 깨어난 Claude 는
    Codex 표시를 보고 손을 뗀다. 예비 호(rewind.yml, 08:35)는 Codex 표시가 있으면 09:15 까지 Codex 를 기다린다.
  · 22:00 편집 회고가 다음 날 새벽까지 없으면(커밋 'Editor retrospective {날짜}') Codex 가 learnings.md 회고를 쓴다.
OPENAI_API_KEY 시크릿이 없으면 아무것도 하지 않는다(키를 넣어야 켜진다 — API 사용료는 Codex 가 일한 날만 든다).

  python3 automation/codex_fallback.py claim claude            # 제작 루틴: 시작 표시(실패해도 제작은 계속)
  python3 automation/codex_fallback.py claims                  # 오늘 누가 표시했나
  python3 automation/codex_fallback.py wait-produce            # 워크플로: 07:55 까지 기다려 Codex 제작이 필요한지(go=true/false)
  python3 automation/codex_fallback.py wait-codex              # rewind.yml: Codex 가 제작 중이면 오늘 호가 오거나 09:15 까지 기다림
  python3 automation/codex_fallback.py need-retro              # 워크플로: 회고가 빠졌나(need=true/false, date=)
  python3 automation/codex_fallback.py restore --allow content/2026-10-26.json ...   # Codex 가 건드린 허용 밖 파일을 되돌림
  python3 automation/codex_fallback.py prune                   # 사흘 지난 표시 가지 지우기
"""
import argparse
import datetime as dt
import fnmatch
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from edith.common import ROOT, load_config, now_kst, parse_date, weekday_ko  # noqa: E402

PREFIX = "run-claim/"
START = (7, 55)          # 이때까지 Claude 표시가 없으면 Codex 가 제작한다(제작 루틴 07:40 시작)
LATEST = (8, 25)         # 이보다 늦게 깨어난 예약 실행은 제작하지 않는다 — 08:35 예비 호에 맡긴다
CODEX_WAIT_UNTIL = (9, 15)   # 예비 호가 Codex 제작을 기다리는 한도
RETRO_AFTER = (23, 30)   # 그날 22:00 회고를 이때까지 기다린 뒤에야 Codex 가 쓴다
POLL = 60
# 제작 산출물(RUNBOOK 5단계 git add 와 같은 경로) — 이 밖의 변경은 되돌린다
PRODUCE_PATHS = ["{d}.html", "content/{d}.json", "instagram/{d}/*", "manifest.json", "index.html", "feed.xml", "sitemap.xml",
                 "assets/photos/*", "automation/headlines/*"]


def _git(*args, check=False):
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=check)


def publish_day(date):
    cfg = load_config()
    if weekday_ko(parse_date(date)) not in cfg["publish_days"]:
        return False
    if cfg.get("skip_kr_public_holidays"):   # check_today.py 와 같은 기준
        import check_today
        return date not in check_today.holidays()[0]
    return True


def parse_claims(ls_remote, date):
    """git ls-remote 출력에서 그날 표시한 쪽들 {'claude', 'codex'}."""
    who = set()
    for line in ls_remote.splitlines():
        ref = line.split("\t")[-1].strip()
        name = ref.removeprefix("refs/heads/")
        if name.startswith(f"{PREFIX}{date}-"):
            who.add(name[len(f"{PREFIX}{date}-"):])
    return who


def claims(date, remote="origin"):
    r = _git("ls-remote", "--heads", remote, f"{PREFIX}*")
    return parse_claims(r.stdout, date) if r.returncode == 0 else set()


def claim(who, date, remote="origin"):
    """그날 표시 가지를 main 이 가리키는 커밋으로 만든다(새 커밋 없음, main 은 그대로)."""
    _git("fetch", "-q", remote, "main")
    r = _git("push", "-q", remote, f"refs/remotes/{remote}/main:refs/heads/{PREFIX}{date}-{who}")
    return r.returncode == 0, (r.stderr or r.stdout).strip()


def published(date, remote="origin"):
    _git("fetch", "-q", remote, "main")
    return _git("cat-file", "-e", f"{remote}/main:{date}.html").returncode == 0


def produce_decision(date, now, has_issue, who, key_set):
    """(Codex 가 제작할까, 이유) — 시각 판단은 wait 가 끝난 뒤(START 이후) 한 번."""
    if not key_set:
        return False, "OPENAI_API_KEY 시크릿이 없어 꺼져 있음"
    if not publish_day(date):
        return False, "발행일이 아님"
    if has_issue:
        return False, "오늘 호가 이미 main 에 있음"
    if "claude" in who:
        return False, "Claude 제작 루틴이 시작했음(표시 있음)"
    if "codex" in who:
        return False, "Codex 가 이미 맡았음"
    if (now.hour, now.minute) >= LATEST:
        return False, f"{LATEST[0]:02d}:{LATEST[1]:02d} 이후 — 예비 호(08:35)에 맡김"
    if (now.hour, now.minute) < START:
        return False, f"아직 {START[0]:02d}:{START[1]:02d} 전"
    return True, f"{START[0]:02d}:{START[1]:02d} 까지 Claude 표시도 오늘 호도 없음"


def wait_produce(date, key_set):
    now = now_kst()
    target = now.replace(hour=START[0], minute=START[1], second=0, microsecond=0)
    if target - now > dt.timedelta(minutes=330):
        return False, "아직 너무 이른 시각 — 뒤 예약 실행에 맡김"
    while True:
        if not key_set:
            return produce_decision(date, now_kst(), False, set(), key_set)
        if published(date):
            return False, "오늘 호가 main 에 있음"
        if "claude" in claims(date):
            return False, "Claude 제작 루틴이 시작했음(표시 있음)"
        left = (target - now_kst()).total_seconds()
        if left <= 0:
            return produce_decision(date, now_kst(), published(date), claims(date), key_set)
        time.sleep(min(POLL, left))


def wait_codex(date):
    """예비 호가 기다릴까 — Codex 표시가 있고 오늘 호가 아직 없으면 CODEX_WAIT_UNTIL 까지 지켜본다."""
    while "codex" in claims(date) and not published(date):
        now = now_kst()
        if (now.hour, now.minute) >= CODEX_WAIT_UNTIL:
            return f"{CODEX_WAIT_UNTIL[0]:02d}:{CODEX_WAIT_UNTIL[1]:02d} 까지 Codex 제작이 끝나지 않음 — 예비 호 판단으로"
        time.sleep(POLL)
    return "Codex 제작 없음" if "codex" not in claims(date) else "Codex 가 오늘 호를 올림"


def retro_target(now):
    """회고를 볼 날짜 — 정오 전이면 어제 호, 아니면 오늘 호(RETRO_AFTER 전이면 아직 이르다)."""
    d = now.date() if now.hour >= 12 else now.date() - dt.timedelta(days=1)
    ready = now.hour < 12 or (now.hour, now.minute) >= RETRO_AFTER
    return d.isoformat(), ready


def retro_done(date, log_text):
    return any(line.startswith(f"Editor retrospective {date}") for line in log_text.splitlines())


def need_retro(key_set, now=None):
    now = now or now_kst()
    date, ready = retro_target(now)
    if not key_set:
        return False, date, "OPENAI_API_KEY 시크릿이 없어 꺼져 있음"
    if not ready:
        return False, date, f"아직 {RETRO_AFTER[0]:02d}:{RETRO_AFTER[1]:02d} 전 — Claude 회고(22:00)를 기다림"
    _git("fetch", "-q", "origin", "main")
    if _git("cat-file", "-e", f"origin/main:content/{date}.json").returncode != 0:
        return False, date, "그날 호가 없음"
    log = _git("log", "origin/main", f"--since={date}T11:00:00Z", "--format=%s").stdout
    if retro_done(date, log):
        return False, date, "회고가 이미 있음"
    return True, date, "그날 회고 커밋이 없음"


def allowed(path, patterns):
    return any(fnmatch.fnmatch(path, p) for p in patterns)


def _changed():
    """바뀐 경로(작업 트리·인덱스 모두, 이름 바꿈은 옛·새 이름 둘 다)."""
    out = []
    for ln in _git("status", "--porcelain", "--untracked-files=all").stdout.splitlines():
        if ln.strip():
            out += [x.strip().strip('"') for x in ln[3:].split(" -> ")]
    return out


def restore(patterns):
    """허용 밖 변경을 HEAD 로 되돌린다 — 작업 트리와 인덱스 모두(스테이징한 변경도, Codex 리뷰). 허용 밖 새 파일은 인덱스에서 빼고 지운다.
    Codex 가 코드·설정을 고쳐 빌드나 커밋을 바꾸지 못하게."""
    bad = [p for p in _changed() if not allowed(p, patterns)]
    for p in bad:
        if _git("cat-file", "-e", f"HEAD:{p}").returncode == 0:
            _git("restore", "--source=HEAD", "--staged", "--worktree", "--", p)
        else:
            _git("rm", "-q", "--cached", "--ignore-unmatch", "--", p)
            (ROOT / p).unlink(missing_ok=True)
    return bad


def prune(today, keep_days=3, remote="origin"):
    r = _git("ls-remote", "--heads", remote, f"{PREFIX}*")
    old = []
    for line in r.stdout.splitlines():
        name = line.split("\t")[-1].removeprefix("refs/heads/")
        try:
            d = dt.date.fromisoformat(name[len(PREFIX):len(PREFIX) + 10])
        except ValueError:
            continue
        if (today - d).days > keep_days:
            old.append(name)
    for name in old:
        _git("push", "-q", remote, "--delete", name)
    return old


def _out(**kv):
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
            for k, v in kv.items():
                f.write(f"{k}={v}\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["claim", "claims", "wait-produce", "wait-codex", "need-retro", "restore", "prune"])
    ap.add_argument("who", nargs="?", choices=["claude", "codex"])
    ap.add_argument("--date", default="")
    ap.add_argument("--allow", nargs="*", default=[], help="restore: 남길 경로(글롭)")
    ap.add_argument("--produce", action="store_true", help="restore: 제작 산출물 경로를 남김")
    args = ap.parse_args()
    date = args.date or now_kst().date().isoformat()
    key_set = bool(os.environ.get("OPENAI_API_KEY_SET"))
    if args.cmd == "claim":
        if not args.who:
            ap.error("claim 에는 claude 또는 codex 가 필요합니다")
        other = claims(date) - {args.who}
        if "codex" in other and args.who == "claude":
            print(f"■ Codex 가 오늘({date}) 제작을 맡았습니다 — 이 세션은 제작하지 말고 그대로 보고하고 끝내세요")
            return 3
        if args.who == "codex" and ("claude" in other or published(date)):
            # 07:55 판단 뒤 이 작업이 시작되기 전에 Claude 가 늦게 시작했거나 오늘 호가 올라왔다(Codex 리뷰) — 제작하지 않는다
            print(f"■ 오늘({date}) 이미 {'Claude 가 제작을 시작했다' if 'claude' in other else '오늘 호가 올라왔다'} — Codex 는 제작하지 않습니다")
            return 3
        ok, msg = claim(args.who, date)
        print(f"{'✓' if ok else '… 표시 실패(제작은 계속)'} {PREFIX}{date}-{args.who}" + ("" if ok else f" — {msg[:200]}"))
        if ok and args.who == "codex" and "claude" in claims(date):   # 거의 동시에 Claude 도 표시했다 — 물러난다
            _git("push", "-q", "origin", "--delete", f"{PREFIX}{date}-codex")
            print("■ 거의 동시에 Claude 도 시작했다 — Codex 표시를 거두고 제작하지 않습니다")
            return 3
        return 0
    if args.cmd == "claims":
        print(", ".join(sorted(claims(date))) or "없음")
        return 0
    if args.cmd == "wait-produce":
        ok, why = wait_produce(date, key_set)
        print(f"{date}: Codex 제작 {'시작' if ok else '안 함'} — {why}")
        _out(go="true" if ok else "false", date=date)
        return 0
    if args.cmd == "wait-codex":
        print(f"{date}: {wait_codex(date)}")
        return 0
    if args.cmd == "need-retro":
        ok, d, why = need_retro(key_set)
        print(f"{d}: Codex 회고 {'필요' if ok else '불필요'} — {why}")
        _out(need="true" if ok else "false", go="true" if ok else "false", date=d)
        return 0
    if args.cmd == "restore":
        pats = list(args.allow) + ([p.format(d=date) for p in PRODUCE_PATHS] if args.produce else [])
        bad = restore(pats)
        print("되돌린 파일(허용 밖): " + (", ".join(bad) if bad else "없음"))
        return 0
    if args.cmd == "prune":
        print("지운 표시: " + (", ".join(prune(now_kst().date())) or "없음"))
        return 0


if __name__ == "__main__":
    sys.exit(main())
