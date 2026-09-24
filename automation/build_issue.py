#!/usr/bin/env python3
"""content/YYYY-MM-DD.json → 뉴스레터·카드뉴스·manifest·index 한 번에 생성.

사용:
  python3 automation/build_issue.py 2026-09-24            # 전체 빌드
  python3 automation/build_issue.py 2026-09-24 --check    # 검증만(파일 안 씀)
  python3 automation/build_issue.py 2026-09-24 --no-cards # 카드 없이 뉴스레터만

실패하면 0이 아닌 코드로 끝나고, 무엇을 고쳐야 하는지 한국어로 알려준다.
"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from edith import cards, content, newsletter, site  # noqa: E402
from edith.common import AUTOMATION, INSTAGRAM_DIR, ROOT, load_config  # noqa: E402


def render_cards(d, out_dir):
    from edith.fonts import font_css

    page, files = cards.build(d, font_css())
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob(f"*_edit_h_{d['date']}_*.png"):
        old.unlink()
    with tempfile.TemporaryDirectory() as tmp:
        html_path = Path(tmp) / "cards.html"
        html_path.write_text(page, encoding="utf-8")
        proc = subprocess.run(
            ["node", str(AUTOMATION / "render_cards.cjs"), str(html_path), str(out_dir), *files],
            capture_output=True, text=True,
        )
    if proc.returncode != 0:
        raise SystemExit(f"카드 렌더링 실패:\n{proc.stderr[-2000:]}")
    report = json.loads(proc.stdout.strip().splitlines()[-1])
    missing = {"Pretendard", "Noto Serif KR"} - set(report["fontsLoaded"])
    if missing:
        raise SystemExit(f"폰트가 로드되지 않았습니다: {missing} — 대체 글꼴로 찍혔을 수 있으니 확인하세요")
    return files, report["cards"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("date", help="YYYY-MM-DD (KST)")
    ap.add_argument("--check", action="store_true", help="검증만 하고 파일은 쓰지 않음")
    ap.add_argument("--no-cards", action="store_true")
    ap.add_argument("--site-url", help="미리보기 전용: 이미지·링크 기준 URL 덮어쓰기(커밋할 빌드에는 쓰지 않는다)")
    args = ap.parse_args()

    cfg = load_config()
    try:
        d = content.load(args.date)
    except content.ContentError as e:
        raise SystemExit(f"✗ 콘텐츠 검증 실패\n{e}")
    if args.check:
        print(f"✓ content/{args.date}.json 검증 통과 (VOL.{d['vol']}, 아이템 {len(d['all_items'])}개)")
        return

    site_url = args.site_url or cfg["site_url"]
    d["send_time_kst"] = cfg["send_time_kst"]  # 뉴스레터 푸터·카드 하단·캡션의 발송 시각 문구
    files, card_report = [], []
    if not args.no_cards:
        out_dir = INSTAGRAM_DIR / args.date
        files, card_report = render_cards(d, out_dir)
        caption = site.instagram_caption(d, site_url)
        (out_dir / "caption.txt").write_text(caption + "\n", encoding="utf-8")
        (out_dir / "index.html").write_text(site.gallery_page(d, site_url, files, caption), encoding="utf-8")

    (ROOT / f"{args.date}.html").write_text(newsletter.render(d, site_url, len(files)), encoding="utf-8")
    manifest = site.update_manifest(d, site_url, len(files), cfg["send_time_kst"])
    site.regenerate_index(manifest)

    print(f"✓ VOL.{d['vol']} {args.date} 빌드 완료")
    print(f"  뉴스레터  {args.date}.html")
    if files:
        print(f"  카드뉴스  instagram/{args.date}/ ({len(files)}장)")
    overflow = [c for c in card_report if c["overflow"]]
    shrunk = [c for c in card_report if c["k"] < 1 and not c["overflow"]]
    for c in shrunk:
        print(f"  ↘ {c['file']}: 글자 {round((1 - c['k']) * 100)}% 자동 축소 — 가능하면 문장을 줄이세요")
    if overflow:
        print("✗ 넘친 카드(20% 축소로도 안 들어감) — 해당 카드 문장을 줄인 뒤 다시 빌드하세요:")
        for c in overflow:
            print(f"    {c['file']}")
        sys.exit(3)


if __name__ == "__main__":
    main()
