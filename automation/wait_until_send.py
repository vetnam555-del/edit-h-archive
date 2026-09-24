#!/usr/bin/env python3
"""발송 시각(config.send_time_kst)까지 기다린다. send-newsletter.yml 에서 발송 직전에 돈다.

GitHub 예약 실행은 정각에 몰려 수~수십 분 늦게 시작되곤 해서, 예약은 몇 분 일찍 걸어 두고
여기서 정확한 시각까지 기다린다. 루틴이 발송 시각 전에 푸시해도(push 트리거) 여기서 기다렸다 보낸다.

사용: python3 automation/wait_until_send.py <event>   # schedule | push | workflow_dispatch
"""
import datetime as dt
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from edith.common import ROOT, load_config, now_kst  # noqa: E402

MAX_WAIT = dt.timedelta(minutes=90)


def main():
    event = sys.argv[1] if len(sys.argv) > 1 else "manual"
    if event not in ("schedule", "push"):
        print(f"{event}: 기다리지 않고 바로 진행")
        return
    now = now_kst()
    today = now.date().isoformat()
    if event == "push" and not (ROOT / f"{today}.html").exists():
        print("오늘 호가 아닌 push — 기다리지 않음")
        return
    hh, mm = map(int, load_config()["send_time_kst"].split(":"))
    target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    wait = target - now
    if dt.timedelta(0) < wait <= MAX_WAIT:
        print(f"발송 시각 {target:%H:%M} KST 까지 {int(wait.total_seconds())}초 대기")
        time.sleep(wait.total_seconds())
    else:
        print(f"대기 없음 (지금 {now:%H:%M} KST, 발송 시각 {target:%H:%M})")


if __name__ == "__main__":
    main()
