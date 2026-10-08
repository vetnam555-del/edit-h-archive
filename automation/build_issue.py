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

from edith import cards, content, newsletter, reel_frames, site, style  # noqa: E402
from edith.common import AUTOMATION, INSTAGRAM_DIR, ROOT, load_config  # noqa: E402


def render_cards(d, out_dir):
    from edith.fonts import font_css

    page, files = cards.build(d, font_css())
    jpeg_dir = out_dir / "ig"  # 인스타그램 자동 게시용 JPEG(API 는 JPEG 만 받는다)
    jpeg_dir.mkdir(parents=True, exist_ok=True)
    for old in [*out_dir.glob(f"*_edit_h_{d['date']}_*.png"), *jpeg_dir.glob("*.jpg")]:
        old.unlink()
    with tempfile.TemporaryDirectory() as tmp:
        html_path = Path(tmp) / "cards.html"
        html_path.write_text(page, encoding="utf-8")
        proc = subprocess.run(
            ["node", str(AUTOMATION / "render_cards.cjs"), str(html_path), str(out_dir), f"--jpeg-dir={jpeg_dir}", *files],
            capture_output=True, text=True,
        )
    if proc.returncode != 0:
        raise SystemExit(f"카드 렌더링 실패:\n{proc.stderr[-2000:]}")
    report = json.loads(proc.stdout.strip().splitlines()[-1])
    missing = {"Pretendard"} - set(report["fontsLoaded"])
    if missing:
        raise SystemExit(f"폰트가 로드되지 않았습니다: {missing} — 대체 글꼴로 찍혔을 수 있으니 확인하세요")
    return files, report["cards"]


def render_reel_frames(d, out_dir):
    """세로 전용 릴스 프레임(1080×1920 JPEG) → instagram/{날짜}/reel_frames/. make_reel.py 가 있으면 이걸로 릴스를 만든다.
    형식 2(H PICK) 데일리 호만. 실패해도 발행은 막지 않는다(릴스는 예전 카드 방식으로 만들어진다)."""
    from edith.fonts import font_css

    frame_dir = out_dir / "reel_frames"
    if frame_dir.exists():
        for old in frame_dir.glob("*.jpg"):
            old.unlink()
    if d.get("format") != 2:
        return []
    frame_dir.mkdir(parents=True, exist_ok=True)
    page, files = reel_frames.build(d, font_css())
    with tempfile.TemporaryDirectory() as tmp:
        html_path = Path(tmp) / "reel.html"
        html_path.write_text(page, encoding="utf-8")
        proc = subprocess.run(
            ["node", str(AUTOMATION / "render_cards.cjs"), str(html_path), tmp, f"--jpeg-dir={frame_dir}", *files],
            capture_output=True, text=True,
        )
    if proc.returncode != 0:
        print(f"  ⚠ 세로 릴스 프레임을 만들지 못했습니다 — 릴스는 카드 방식으로 만듭니다\n{proc.stderr[-600:]}")
        for old in frame_dir.glob("*.jpg"):
            old.unlink()
        return []
    report = json.loads(proc.stdout.strip().splitlines()[-1])["cards"]
    bad = [c["file"] for c in report if c.get("overflow")]
    if bad:
        print(f"  ⚠ 세로 릴스 프레임 글자가 넘칩니다({', '.join(bad)}) — 제목·결론을 줄이거나, 릴스는 카드 방식으로 나갑니다")
        for old in frame_dir.glob("*.jpg"):
            old.unlink()
        return []
    return [f.replace(".png", ".jpg") for f in files]


def print_style(d):
    """문장 점검(토스 라이팅 원칙, edith/style.py) — 경고만. 고칠지는 제작 세션이 판단한다."""
    notes = style.lint(d)
    if notes:
        print("  ↘ 문장 점검(토스 라이팅 원칙 — RUNBOOK '짧고 세게') — 고칠 수 있으면 고쳐서 다시 빌드:")
        for n in notes:
            print(f"      {n}")


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
        print_style(d)
        return

    site_url = args.site_url or cfg["site_url"]
    d["send_time_kst"] = cfg["send_time_kst"]  # 뉴스레터 푸터·카드 하단·캡션의 발송 시각 문구
    files, card_report = [], []
    if not args.no_cards:
        out_dir = INSTAGRAM_DIR / args.date
        files, card_report = render_cards(d, out_dir)
        if not d.get("rewind"):   # 예비 호는 릴스를 올리지 않는다
            frames = render_reel_frames(d, out_dir)
            if frames:
                print(f"  세로 릴스  instagram/{args.date}/reel_frames/ ({len(frames)}장)")
        caption = site.instagram_caption(d, site_url)
        (out_dir / "caption.txt").write_text(caption + "\n", encoding="utf-8")
        comment = site.first_comment(d)
        (out_dir / "first_comment.txt").write_text(comment + "\n", encoding="utf-8")
        (out_dir / "reel_caption.txt").write_text(site.reel_caption(d) + "\n", encoding="utf-8")
        (out_dir / "index.html").write_text(site.gallery_page(d, site_url, files, caption, comment), encoding="utf-8")

    # 뉴스레터 프로필의 'N장 카드뉴스'는 이슈 카드 수(표지·마무리 제외, VOL.092 와 같은 기준)
    n_issue_cards = len(d["card_issues"]) if files else 0
    (ROOT / f"{args.date}.html").write_text(newsletter.render(d, site_url, n_issue_cards), encoding="utf-8")
    manifest = site.update_manifest(d, site_url, len(files), cfg["send_time_kst"])
    site.regenerate_index(manifest)
    site.write_feeds(manifest, site_url)   # feed.xml(RSS)·sitemap.xml

    print(f"✓ VOL.{d['vol']} {args.date} 빌드 완료")
    print(f"  뉴스레터  {args.date}.html")
    if files:
        print(f"  카드뉴스  instagram/{args.date}/ ({len(files)}장)")
    overflow = [c for c in card_report if c["overflow"]]
    shrunk = [c for c in card_report if c["k"] < 1 and not c["overflow"]]
    for c in shrunk:
        print(f"  ↘ {c['file']}: 글자 {round((1 - c['k']) * 100)}% 자동 축소 — 가능하면 문장을 줄이세요")
    print_style(d)
    if d.get("format") == 2 and not d.get("rewind") and len(d["briefs"]) < content.BRIEFS_TARGET:
        # 2026-10-03 회고: '괜찮아요'라고 알려 줘서 10/2·10/3 이틀 연속 3개로 나갔다 — 원칙 1(5개)을 분명히 한다
        print(f"  ↘ 한 줄 뉴스 {len(d['briefs'])}개 — 원칙 1은 {content.BRIEFS_TARGET}개(메인 5 + 한 줄 뉴스 5 = 10개 주제)."
              " RUNBOOK 1-2 보강 소스(정부 보도자료·생활 제도 변경·교통·가격)로 한 번 더 찾고, 그래도 확인된 소식이 없으면"
              " 6단계 보고 '한 줄 뉴스:' 줄에 사유를 적으세요")
    thin = [f"{x.get('no', '?')} {str(x.get('title', ''))[:16]}" for x in d.get("all_items") or []
            if len(x.get("sources") or []) < 2]
    if d.get("format") == 2 and not d.get("rewind") and thin:
        print(f"  ↘ 출처 1건뿐인 이야기: {', '.join(thin)} — 원칙 2(원 기사 2건 이상). 두 번째 원 기사를 찾아 sources 에 더하세요")
    cover = (d.get("cards") or {}).get("cover") or {}
    if d.get("format") == 2 and not d.get("rewind") and files and not cover.get("photo"):
        # 2026-10-05 호가 이 경고에도 사진 없이 나갔다(캐러셀 도달 10, 실사 평균 14) — 바로 쓸 대체 사진을 함께 알려 준다
        import fetch_photo
        words = " ".join(str(x) for x in (d.get("title"), cover.get("title"), d.get("hero_title")) if x)
        alt = [c for c in fetch_photo.library(d["date"], words) if c["score"]][:2]
        print("  ↘ 표지 사진 없음(핵심어 표지) — 원칙 9(표지는 실사 사진). 위키미디어 검색어를 3개 이상 시도했고 그래도 없으면"
              " 지난 호에서 검수한 대체 사진을 쓰세요: python3 automation/fetch_photo.py --library \"주제어\""
              + (" — 지금 맞는 후보: " + ", ".join(f"{c['photo']}({c['subject']})" for c in alt) if alt else "")
              + ". 그래도 못 썼다면 6단계 보고 '표지:' 줄에 사유를 적으세요")
    elif d.get("format") == 2 and not d.get("rewind") and cover.get("photo"):
        import fetch_photo
        if cover["photo"] not in json.loads(fetch_photo.LIBRARY.read_text(encoding="utf-8")):
            print(f"  ↘ 새 표지 사진 {cover['photo']} — 대체 사진 목록(assets/photos/library.json)에 subject·tags 한 줄을 더해 두세요")
    if overflow:
        print("✗ 넘친 카드(20% 축소로도 안 들어감) — 해당 카드 문장을 줄인 뒤 다시 빌드하세요:")
        for c in overflow:
            print(f"    {c['file']}")
        sys.exit(3)


if __name__ == "__main__":
    main()
