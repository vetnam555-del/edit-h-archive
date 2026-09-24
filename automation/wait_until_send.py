#!/usr/bin/env python3
"""발송 시각(config.send_time_kst)까지 기다린다. send-newsletter.yml 에서 발송 직전에 돈다.

GitHub 예약 실행은 정각에 몰려 수~수십 분 늦게 시작되거나 아예 빠지기도 해서(2026-09-25 첫 08:00 예약이
07:30·08:05 둘 다 돌지 않음), 오늘 호가 푸시되면 push 트리거가 여기서 발송 시각까지 기다렸다 보낸다.
새벽에 미리 올린 호도 보내지도록 최대 5시간 50분까지 기다린다(워크플로 timeout 370분, 공개 저장소라 Actions 무료).

사용: python3 automation/wait_until_send.py <event> [--at HH:MM] [--need 파일]   # event: schedule | push | workflow_dispatch
  --at   기다릴 시각(기본 config.send_time_kst). 인스타 주간 특집은 18:00.
  --need push 로 시작됐을 때 오늘 호가 있는지 볼 파일({date} 자리에 오늘 날짜, 기본 {date}.html).
"""
import datetime as dt
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from edith.common import ROOT, load_config, now_kst  # noqa: E402

MAX_WAIT = dt.timedelta(minutes=350)


def main():
    args = sys.argv[1:]
    event = args[0] if args and not args[0].startswith("--") else "manual"
    opt = {args[i]: args[i + 1] for i in range(len(args) - 1) if args[i].startswith("--")}
    if event not in ("schedule", "push"):
        print(f"{event}: 기다리지 않고 바로 진행")
        return
    now = now_kst()
    today = now.date().isoformat()
    if event == "push" and not (ROOT / opt.get("--need", "{date}.html").format(date=today)).exists():
        print("오늘 호가 아닌 push — 기다리지 않음")
        return
    hh, mm = map(int, opt.get("--at", load_config()["send_time_kst"]).split(":"))
    target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    wait = target - now
    if dt.timedelta(0) < wait <= MAX_WAIT:
        print(f"발송 시각 {target:%H:%M} KST 까지 {int(wait.total_seconds())}초 대기")
        time.sleep(wait.total_seconds())
    else:
        print(f"대기 없음 (지금 {now:%H:%M} KST, 발송 시각 {target:%H:%M})")


if __name__ == "__main__":
    main()
