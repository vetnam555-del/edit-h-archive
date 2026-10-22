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
  · 큰 소식 놓침(2026-10-23~): 제작 때 저장한 네이버 '여러 언론이 함께 다룬 소식'(관련 기사 BIG 건 이상)과
    '경제·IT 매체 여러 곳에서 많이 읽힌 소식' 중 우리 호에 없는 것 — 주말·공휴일(안장 없음)에도 본다
종료 코드: 0 = 비교함, 3 = 그날 안장 글도 큰 소식 기록도 없음, 2 = 접속 실패.
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
BIG = 20   # 관련 기사 이만큼이면 '큰 소식'(fetch_headlines 도 쓴다)
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


def _match(it, m):
    """안장 소식 it 과 우리 소식 m 이 같은 이야기인가 — 안장 제목 ↔ 우리 제목·본문 앞부분, 안장 제목·요약 ↔ 우리 제목.
    '겹침'과 '우리만'이 같은 판정을 쓰게 한 곳에 둔다(한 소식이 두 칸에 동시에 들어가지 않게 — Codex 리뷰)."""
    text = it["headline"] + " " + " ".join(it.get("summary") or [])[:200]
    return _same(it["headline"], m[1] + " " + m[2][:200]) or _same(text, m[1])


def compare(anjang_items, content):
    mine = ours(content)
    covered, missed = [], []
    for it in anjang_items:
        hit = next((m for m in mine if _match(it, m)), None)
        (covered if hit else missed).append((it["headline"], hit[0] if hit else None))
    ours_only = [m for m in mine if not any(_match(it, m) for it in anjang_items)]
    main_text = " ".join(m[2] for m in mine if m[0] != "한 줄")
    return {"covered": covered, "missed": missed, "ours_only": ours_only,
            "numbers": len(_NUM.findall(main_text)), "source_mode": content.get("source_mode")}


def compare_big(snapshot, content, big=BIG):
    """[(큰 소식, 우리 쪽 구분 또는 None)], [(많이 본 소식 묶음, 우리 쪽 구분 또는 None)] — 많이 본 것은 두 곳 이상에 오른 것만.
    같은 소식이 묶음과 많이 본 목록에 함께 오르면 한 번만 센다(Codex 리뷰 — 분모가 부풀지 않게)."""
    mine = ours(content)

    def where(title, lede=""):
        it = {"headline": title, "summary": [lede] if lede else []}
        return next((m[0] for m in mine if _match(it, m)), None)
    clusters = []
    for c in snapshot.get("clusters") or []:
        if c.get("count", 0) >= big and not any(_same(c["title"], x["title"]) for x, _ in clusters):
            clusters.append((c, where(c["title"], c.get("lede", ""))))
    popular = [(g, where(g["title"])) for g in snapshot.get("popular") or []
               if len(g.get("presses") or []) >= 2 and not any(_same(g["title"], c["title"]) for c, _ in clusters)]
    return clusters, popular


def big_report(day, content):
    """제작 때 저장한 큰 소식 기록(automation/headlines/{날짜}.json)과 견준다. 기록이 없으면 False."""
    path = AUTOMATION / "headlines" / f"{day}.json"
    if not path.exists():
        print(f"… {day} 큰 소식 기록(automation/headlines/{day}.json)이 없어 견주지 않습니다 — 제작 1-1c 에서 --save 를 빠뜨렸나 확인")
        return False
    snap = json.loads(path.read_text(encoding="utf-8"))
    clusters, popular = compare_big(snap, content)
    hit = sum(1 for _, w in clusters + popular if w)
    print(f"■ {day} 큰 소식 비교 — 다룸 {hit}/{len(clusters) + len(popular)} (여러 언론 {BIG}건+ {len(clusters)}개 · 경제·IT 매체 많이 본 {len(popular)}개)"
          + (f" — 일부 못 읽은 기록({', '.join(snap['failed'])}): 분모가 작을 수 있다" if snap.get("failed") else ""))
    for c, w in clusters:
        print(f"  {'=' if w else '-'} [{c['section']} {c['count']}] {c['title']}" + (f"  ← 우리 {w}" if w else ""))
    for g, w in popular:
        print(f"  {'=' if w else '-'} [많이 본 {len(g['presses'])}곳] {g['title']}" + (f"  ← 우리 {w}" if w else ""))
    print("회고 기록 한 줄: '큰 소식: 다룸 N/M · 놓친 것 중 우리 독자(2030 돈·일·소비)에게 맞았던 것 …' (사건·정치는 놓쳐도 된다)")
    return True


def anjang_report(day, content):
    """안장출근길과 견준다. 0 = 견줌, 3 = 그날 글 없음, 2 = 접속 실패."""
    r = subprocess.run([sys.executable, str(AUTOMATION / "fetch_anjang.py"), "--date", day, "--json"], capture_output=True, text=True)
    if r.returncode != 0:
        print(f"… {day} 안장출근길 글이 없어 비교하지 않습니다(코드 {r.returncode}) — 주말·공휴일이면 정상")
        return r.returncode
    posts = [p for p in json.loads(r.stdout) if p["date"] == day]
    if not posts:
        print(f"… {day} 안장출근길 글이 없습니다")
        return 3
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
    return 0


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
    code = anjang_report(day, content)
    print()
    sys.exit(0 if big_report(day, content) or code == 0 else code)


if __name__ == "__main__":
    main()
