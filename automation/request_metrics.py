#!/usr/bin/env python3
"""편집 회고(22:00) 전에 성과표를 새로 받는다 — GitHub 예약 수집(21:30)은 자주 늦거나 빠진다(2026-09-25 22:14 에도 미실행).

성과표(automation/metrics/summary.md) 첫 줄의 수집 시각이 기준보다 오래됐으면 automation/metrics/request.txt 를 커밋·푸시해
collect-metrics.yml(push 트리거)을 돌리고, 새 성과표가 main 에 올라올 때까지 기다린다.
루틴 컨테이너에는 GitHub API 도구가 없을 수 있어 git 만 쓴다. 성과표는 숫자만 있다(개인 정보 없음).

  python3 automation/request_metrics.py              # 필요할 때만 요청하고 기다림(최대 540초 — Bash timeout 600000 으로 돌린다)
  python3 automation/request_metrics.py --check      # 신선한지 보기만
종료 코드: 0 = 성과표가 신선함(main 도 최신으로 받음) · 2 = 기다려도 안 옴(기존 성과표로 진행) · 1 = git 오류
"""
import argparse
import datetime as dt
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from edith.common import AUTOMATION, ROOT, now_kst  # noqa: E402

SUMMARY = "automation/metrics/summary.md"
REQUEST = AUTOMATION / "metrics" / "request.txt"
_WHEN = re.compile(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?[+-]\d{2}:\d{2}) 수집")


def git(*args, check=False):
    r = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True)
    if check and r.returncode:
        raise RuntimeError(f"git {' '.join(args[:2])}: {r.stderr.strip()[:200]}")
    return r


def collected_at(text):
    m = _WHEN.search(text[:400] if text else "")
    return dt.datetime.fromisoformat(m.group(1)) if m else None


def threshold(now, after):
    """이 시각 이후에 모은 성과표면 신선하다. 22:00 회고라면 오늘 21:00, 그보다 이른 시각에 돌리면 3시간 전."""
    hh, mm = map(int, after.split(":"))
    t = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    return t if now >= t else now - dt.timedelta(hours=3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--after", default="21:00", help="오늘 이 시각(KST) 이후 수집이면 신선함")
    ap.add_argument("--wait", type=int, default=540, help="새 성과표를 기다릴 최대 초")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    now = now_kst()
    need = threshold(now, args.after)
    path = ROOT / SUMMARY
    have = collected_at(path.read_text(encoding="utf-8")) if path.exists() else None
    print(f"성과표 수집 시각: {have.isoformat(timespec='minutes') if have else '없음'} · 기준: {need.isoformat(timespec='minutes')} 이후")
    if have and have >= need:
        print("✓ 신선함 — 요청하지 않음")
        return 0
    if args.check:
        print("✗ 오래됨")
        return 2

    try:
        REQUEST.write_text(f"{now.isoformat(timespec='seconds')}\n", encoding="utf-8")
        git("add", str(REQUEST.relative_to(ROOT)), check=True)
        git("commit", "-m", f"Request metrics collection ({now:%Y-%m-%d %H:%M} KST)", "--", str(REQUEST.relative_to(ROOT)), check=True)
        for i in range(4):
            if git("push", "origin", "HEAD:main").returncode == 0:
                break
            git("pull", "--rebase", "--autostash", "origin", "main")
            time.sleep(3 * (i + 1))
        else:
            raise RuntimeError("push 실패")
    except RuntimeError as e:
        print(f"✗ 수집 요청을 올리지 못함: {e}")
        return 1
    print("→ 수집 요청을 올림(collect-metrics.yml push 트리거). 새 성과표를 기다리는 중…")

    since = now - dt.timedelta(minutes=1)
    deadline = time.monotonic() + args.wait
    while time.monotonic() < deadline:
        time.sleep(20)
        if git("fetch", "-q", "origin", "main").returncode:
            continue
        got = collected_at(git("show", f"origin/main:{SUMMARY}").stdout)
        if got and got >= since:
            r = git("pull", "--rebase", "--autostash", "origin", "main")
            print(f"✓ 새 성과표({got.isoformat(timespec='minutes')} 수집)를 받음" + ("" if r.returncode == 0 else f" — pull 확인 필요: {r.stderr.strip()[:120]}"))
            return 0 if r.returncode == 0 else 1
    print(f"✗ {args.wait}초 안에 새 성과표가 오지 않음 — 기존 성과표로 진행(회고에 '성과표 지연' 한 줄)")
    return 2


if __name__ == "__main__":
    sys.exit(main())
