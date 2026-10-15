#!/usr/bin/env python3
"""그날 호를 안장출근길(1순위 소스·운영자가 보는 기준선)과 나란히 본다 — 22:00 편집 회고가 회고 기록에 한 줄로 남긴다.

2026-10-15 운영자: '안장출근길 소스보다 부족해 보인다, 매일 발전하는 거 맞나?' — 매일 같은 잣대로 재야 나아지는지 안다.

  python3 automation/compare_anjang.py                 # 오늘(KST)
  python3 automation/compare_anjang.py --date 2026-10-15

보는 것(자동 추정 — 회고가 눈으로 확인해 고친다):
  · 겹침: 안장 헤드라인 10개 중 우리 호(H PICK·메인·한 줄 뉴스)와 같은 소식으로 보이는 것
  · 놓친 것: 안장에만 있는 헤드라인(우리 독자에게 맞았는데 빠진 게 있는지 회고가 고른다)
  · 우리만: 우리 호에만 있는 주제
  · 숫자: 우리 메인 본문에 나온 숫자 개수(안장 요약은 소식마다 숫자 2~4개)
종료 코드: 0 = 비교함, 3 = 그날 안장 글 없음(주말 등), 2 = 접속 실패.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from edith.common import CONTENT_DIR, now_kst, plain  # noqa: E402

AUTOMATION = Path(__file__).resolve().parent
_NUM = re.compile(r"\d[\d,.]*\s*(?:%|원|만|억|조|명|곳|개|배|건|kL|p)?")
_WORD = re.compile(r"[가-힣A-Za-z0-9]{2,}")
_STOP = {"그래서", "이번", "오늘", "지난", "올해", "내년", "있어요", "이라고", "라고", "이다", "한다", "단독",
         # 어디에나 나오는 말 — 이것만 겹쳐서는 같은 소식이 아니다(10/15 'AI·주문'으로 교보문고와 카톡 AI 를 묶은 오판)
         "AI", "주문", "출시", "업계", "시장", "정부", "소비자", "서비스", "이용자", "기업", "국내", "증가", "감소", "확대",
         "고객", "혜택", "가격", "금리", "매출", "투자", "결제", "신청"}
_TAIL = re.compile(r"(?:으로|에서|까지|부터|이라|에게|이|가|을|를|은|는|에|의|도|로|와|과|만)$")


def _words(text):
    out = set()
    for w in _WORD.findall(plain(text or "")):
        w = _TAIL.sub("", w) if len(w) > 2 else w   # '카톡에'·'카톡이' → '카톡'
        if len(w) >= 2 and w not in _STOP:
            out.add(w)
    return out


def _same(a, b):
    """두 소식이 같은 이야기로 보이나 — 2글자 이상 낱말이 2개 이상 겹치면(고유명사·숫자가 대개 겹친다)."""
    return len(_words(a) & _words(b)) >= 2


def ours(content):
    """[(구분, 제목, 본문)] — H PICK·메인·한 줄 뉴스."""
    b = content["big_issue"]
    out = [("H PICK", plain(content.get("title", "")) + " " + b.get("tag", ""), " ".join(b.get("paragraphs") or []))]
    out += [("메인", plain(it.get("title", "")) + " " + it.get("tag", ""), it.get("body", "")) for it in content.get("items") or []]
    out += [("한 줄", plain(x.get("title", "")), x.get("body", "")) for x in content.get("briefs") or []]
    return out


def compare(anjang_items, content):
    mine = ours(content)
    covered, missed = [], []
    for it in anjang_items:
        text = it["headline"] + " " + " ".join(it.get("summary") or [])[:200]
        hit = next((m for m in mine if _same(it["headline"], m[1] + " " + m[2][:200]) or _same(text, m[1])), None)
        (covered if hit else missed).append((it["headline"], hit[0] if hit else None))
    ours_only = [m for m in mine if not any(_same(m[1] + " " + m[2][:200], it["headline"]) for it in anjang_items)]
    main_text = " ".join(m[2] for m in mine if m[0] != "한 줄")
    return {"covered": covered, "missed": missed, "ours_only": ours_only,
            "numbers": len(_NUM.findall(main_text)), "source_mode": content.get("source_mode")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date")
    args = ap.parse_args()
    day = args.date or now_kst().date().isoformat()
    path = CONTENT_DIR / f"{day}.json"
    if not path.exists():
        print(f"✗ {day} 호가 없습니다")
        sys.exit(2)
    content = json.loads(path.read_text(encoding="utf-8"))
    r = subprocess.run([sys.executable, str(AUTOMATION / "fetch_anjang.py"), "--date", day, "--json"], capture_output=True, text=True)
    if r.returncode != 0:
        print(f"… {day} 안장출근길 글이 없어 비교하지 않습니다(코드 {r.returncode}) — 주말·공휴일이면 정상")
        sys.exit(r.returncode)
    posts = [p for p in json.loads(r.stdout) if p["date"] == day]
    if not posts:
        print(f"… {day} 안장출근길 글이 없습니다")
        sys.exit(3)
    res = compare(posts[0]["items"], content)
    n = len(posts[0]["items"])
    print(f"■ {day} 안장출근길 비교 (소스 모드: {res['source_mode']}{' · 예비 호' if content.get('rewind') else ''})")
    print(f"  겹침 {len(res['covered'])}/{n} · 우리만 {len(res['ours_only'])}개 · 우리 메인 본문 숫자 {res['numbers']}개")
    for h, where in res["covered"]:
        print(f"  = {h}  ← 우리 {where}")
    for h, _ in res["missed"]:
        print(f"  - (안장만) {h}")
    for kind, title, _ in res["ours_only"]:
        print(f"  + (우리만·{kind}) {title.strip()}")
    print("회고 기록 한 줄: '안장 비교: 겹침 N/10 · 우리만 M · 놓친 것 중 우리 독자에게 맞았던 것 …' (자동 추정이니 눈으로 고친다)")


if __name__ == "__main__":
    main()
