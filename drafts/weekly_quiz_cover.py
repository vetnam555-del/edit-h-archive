#!/usr/bin/env python3
"""금요일 주간 특집 표지 시안(2026-11-22 운영자 '전혀 클릭하고 싶지 않게 보인다 — 너 같으면 보고 싶어?').
11/20 특집(조회 11) 내용 그대로 두 방향 표지 + '문제 5개' 장을 그린다. 시안이라 게시 경로와 무관하다.

  python3 drafts/weekly_quiz_cover.py OUT_DIR
A 퀴즈형: 답을 빈칸(??)으로 숨기고 '몇 개 맞힐까요?' — 넘겨야 답이 나온다.
B 한 방형: 가장 내 일인 소식 하나(안 찾아간 실손보험금 1조원)를 '내 것도?'로 — 손해·궁금증.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "automation"))
from edith import cards  # noqa: E402
from edith.cards import ACC, ACC_FILL, TEXT, MUTED, _frame, _strip, _sticker, esc, mascot_img  # noqa: E402
from edith.fonts import font_css  # noqa: E402

DATE = "2026-11-20"
KICK = "11월 4주차"


def bubble(text, size):
    return (f'<div style="position:absolute;right:0;top:10px;z-index:2;background:#FFFFFF;border:5px solid {TEXT};'
            f'border-radius:44px;padding:10px 36px 16px;font-weight:900;font-size:{size}px;line-height:1.1;letter-spacing:-3px;color:{TEXT};'
            f'white-space:nowrap;box-shadow:0 8px 0 {ACC_FILL};">{text}'
            f'<div style="position:absolute;left:46px;bottom:-24px;width:38px;height:38px;background:#FFFFFF;'
            f'border-right:5px solid {TEXT};border-bottom:5px solid {TEXT};transform:rotate(45deg);"></div></div>')


def blank(text):
    """빈칸 스티커 — '??' 만 주황 칸으로."""
    html = esc(text).replace("??", f'<span style="background:{ACC_FILL};padding:0 8px;color:{TEXT};">??</span>')
    return (f'<div style="display:inline-block;background:#FFFFFF;border:3px solid {TEXT};padding:10px 18px;font-weight:700;'
            f'font-size:38px;line-height:1;color:{TEXT};white-space:nowrap;box-shadow:0 3px 8px rgba(0,0,0,.14);">{html}</div>')


def big(text):
    return blank(text)


def cover(kicker, l1, l2, say, say_size, pose, stickers, foot):
    spots = [("right:0;top:260px;", 2), ("right:30px;top:385px;", -2), ("right:0;top:510px;", 1.5)]
    st = "".join(f'<div style="position:absolute;z-index:3;{pos}transform:rotate({r}deg);">{s}</div>' for s, (pos, r) in zip(stickers, spots))
    hero = bubble(say, say_size) + f'<div style="position:absolute;left:30px;bottom:-30px;z-index:1;">{mascot_img(pose, 640)}</div>'
    return _frame(f"""
<div class="body" style="padding:64px 60px 0;align-items:center;text-align:center;">
  <div style="font-weight:900;font-size:34px;line-height:1;letter-spacing:-1px;color:{TEXT};">EDIT H<span style="color:{ACC};">.</span></div>
  <div style="margin-top:22px;font-weight:700;font-size:28px;color:#5A5A5E;">{esc(kicker)}</div>
  <div style="flex:none;margin-top:26px;display:flex;flex-direction:column;align-items:center;gap:14px;">{_strip(l1, "#FFFFFF")}{_strip(l2, ACC_FILL)}</div>
  <div style="flex:none;position:relative;margin-top:70px;width:100%;height:680px;">{hero}{st}</div>
</div>
<div style="position:absolute;left:0;right:0;bottom:60px;text-align:center;font-weight:700;font-size:30px;color:{TEXT};">{esc(foot)}</div>""", mark=False)


QS = [   # 11/20 특집 5개 — content 숫자 그대로(정답은 다음 장들, 기존 소식 카드)
    ("최근 3년 안 찾아간 실손보험금은?", ["1000억원", "1조원", "10조원"]),
    ("내년 4월부터 은행 문 여는 시각은?", ["9시", "9시 30분", "10시"]),
    ("엔비디아 매출, 1년 전보다?", ["50%↑", "103%↑", "3배↑"]),
    ("또 최대 찍은 가계빚은?", ["1030조원", "2030조원", "3030조원"]),
    ("AI로 일하는 직장인은?", ["3명 중 1명", "3명 중 2명", "10명 중 9명"]),
]


def questions():
    rows = "".join(
        f'<div style="padding:30px 0;border-bottom:2px solid #EAEAEA;">'
        f'<div style="display:flex;align-items:center;gap:20px;">'
        f'<div style="flex:none;width:58px;height:58px;border-radius:13px;background:{TEXT};color:#FFFFFF;display:flex;align-items:center;'
        f'justify-content:center;font-weight:700;font-size:28px;">Q{i}</div>'
        f'<div style="font-weight:800;font-size:42px;line-height:1.25;color:{TEXT};">{esc(q)}</div></div>'
        f'<div style="margin:14px 0 0 78px;display:flex;gap:12px;">'
        + "".join(f'<div style="border:2.5px solid {TEXT};border-radius:30px;padding:8px 22px;font-weight:700;font-size:31px;color:{TEXT};">'
                  f'{"①②③"[k]} {esc(o)}</div>' for k, o in enumerate(opts))
        + '</div></div>' for i, (q, opts) in enumerate(QS, 1))
    return _frame(f"""
<div class="body" style="padding:120px 60px 0;">
  <div style="font-weight:700;font-size:28px;color:{ACC};">{KICK} 주말 퀴즈</div>
  <div style="margin-top:12px;font-weight:800;font-size:56px;line-height:1.2;letter-spacing:-1.5px;color:{TEXT};">먼저 풀어 보세요 — 정답은 다음 장부터</div>
  <div style="margin-top:18px;">{rows}</div>
</div>
<div style="position:absolute;left:0;right:0;bottom:60px;text-align:center;font-weight:700;font-size:28px;color:{MUTED};">몇 개 맞혔는지 댓글로 남겨 주세요 · 밀어서 정답 →</div>""")


def main():
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    a = cover(f"{KICK} 주말 퀴즈 · 5문제", "이번 주 뉴스,", "몇 개 맞힐까요?", "?", 150, "thinking",
              [blank("은행 문 여는 시각 ??:??"), blank("안 찾은 실손보험금 ??조원"), blank("AI로 일하는 직장인 ??%")],
              "밀어서 문제 풀기 →")
    b = cover(f"{KICK} 주말 정리 · 내 돈에 닿은 5가지", "안 찾아간 실손보험금", "1조원, 내 것도?", "3년 지나면 끝!", 92, "surprised",
              [big("은행 30분 늦게 연다"), big("카드값 또 최대"), big("직장인 3명 중 2명 AI")],
              "밀어서 내 것인지 확인하기 →")
    page = (f'<!DOCTYPE html><html lang="ko"><head><meta charset="UTF-8"><style>{font_css()}\n{cards.CSS}\n'
            f'{cards.height_css(DATE)}</style></head><body>{a}{b}{questions()}</body></html>')
    files = ["A_quiz_cover.png", "B_hook_cover.png", "A_questions.png"]
    with tempfile.TemporaryDirectory() as tmp:
        hp = Path(tmp) / "draft.html"
        hp.write_text(page, encoding="utf-8")
        jp = Path(tmp) / "jpg"
        jp.mkdir()
        subprocess.run(["node", str(ROOT / "automation" / "render_cards.cjs"), str(hp), str(out), f"--jpeg-dir={jp}", *files], check=True,
                       capture_output=True, text=True)
    print("✓", out)


if __name__ == "__main__":
    main()
