#!/usr/bin/env python3
"""금요일 주간 특집 'TOP5' 빌드 — content/weekly/{금요일}.json + 이번 주 데일리 카드 이슈 → instagram/{금요일}-weekly/.

사용:
  python3 automation/build_weekly.py 2026-10-16            # 빌드
  python3 automation/build_weekly.py 2026-10-16 --check    # 검증만
  python3 automation/build_weekly.py 2026-10-16 --out /tmp/w  # 미리보기(다른 폴더에)
뉴스레터·메일·manifest 는 건드리지 않는다(인스타 전용).
"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from edith import cards, site, weekly  # noqa: E402
from edith.common import AUTOMATION, INSTAGRAM_DIR, load_config  # noqa: E402
from edith.fonts import font_css  # noqa: E402

NAMES = ["cover", "summary", "item1", "item2", "item3", "item4", "item5", "oneliner", "cta"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("date", help="금요일 YYYY-MM-DD")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--out", help="미리보기 출력 폴더")
    args = ap.parse_args()
    try:
        w = weekly.load(args.date)
    except weekly.WeeklyError as e:
        raise SystemExit(f"✗ 주간 특집 검증 실패\n{e}")
    picked = ", ".join(f"{it['day_label']} {it['tag']}" for it in w["card_issues"])
    if args.check:
        print(f"✓ 주간 특집 검증 통과 — {picked}")
        return

    ol = w["spec"]["oneliner"]
    sections = ([cards.cover(w, kicker=f"{w['week_label']} 주간 특집 | 이번 주 TOP{len(w['card_issues'])}",
                             foot=f"밀어서 {len(w['card_issues'])}가지 보기 →"),
                 cards.summary(w, period="이번 주")]
                + [cards.issue_card(it, i) for i, it in enumerate(w["card_issues"], 1)]
                + [cards.list_card("이번 주를 한 줄로", ol["title"], ol["lines"]), cards.cta(w)])
    files = [f"{i:02d}_edit_h_{w['date']}_{n}.png" for i, n in enumerate(NAMES, 1)]
    out = Path(args.out) if args.out else INSTAGRAM_DIR / w["date"]
    jpeg_dir = out / "ig"  # 인스타그램 자동 게시용 JPEG
    jpeg_dir.mkdir(parents=True, exist_ok=True)
    for old in [*out.glob("*.png"), *jpeg_dir.glob("*.jpg")]:
        old.unlink()
    page = f'<!DOCTYPE html><html lang="ko"><head><meta charset="UTF-8"><style>{font_css()}\n{cards.CSS}</style></head><body>{"".join(sections)}</body></html>'
    with tempfile.TemporaryDirectory() as tmp:
        hp = Path(tmp) / "weekly.html"
        hp.write_text(page, encoding="utf-8")
        proc = subprocess.run(["node", str(AUTOMATION / "render_cards.cjs"), str(hp), str(out), f"--jpeg-dir={jpeg_dir}", *files],
                              capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"카드 렌더링 실패:\n{proc.stderr[-2000:]}")
    report = json.loads(proc.stdout.strip().splitlines()[-1])

    cap = weekly.caption(w)
    comment = site.first_comment(w)
    (out / "caption.txt").write_text(cap + "\n", encoding="utf-8")
    (out / "first_comment.txt").write_text(comment + "\n", encoding="utf-8")
    (out / "index.html").write_text(site.gallery_page(w, load_config()["site_url"], files, cap, comment), encoding="utf-8")

    print(f"✓ 주간 특집 {w['week_label']} 빌드 완료 — {out}")
    print(f"  고른 이슈: {picked}")
    for c in report["cards"]:
        if c["overflow"]:
            print(f"✗ 넘친 카드: {c['file']} — 문장을 줄이세요")
        elif c["k"] < 1:
            print(f"  ↘ {c['file']}: 글자 {round((1 - c['k']) * 100)}% 자동 축소")
    if any(c["overflow"] for c in report["cards"]):
        sys.exit(3)


if __name__ == "__main__":
    main()
