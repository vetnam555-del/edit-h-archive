"""아침 스토리 화면(1080×1920) — 2026-10-29 운영자: '스토리에 릴스 첫 장 하나만 올라가니 아무 내용이 없다, 눌러도 반응 없는 껍데기'.

앱에서 피드 게시물을 스토리에 붙이면(게시물 스티커) 누를 때 그 게시물로 가지만, 인스타그램 API(STORIES)는 이미지·영상만 받고
게시물·링크 스티커를 붙일 수 없다. 그래서 캐러셀 카드 자체를 스토리 여러 장으로 올려 스토리만 넘겨도 오늘 내용이 보이게 한다:

  (세로 릴스 첫 장 r1_hook — post_instagram 이 맨 앞에 붙인다. 없으면 표지 카드 s1)
  → H PICK 카드 → 오늘의 N가지 한눈에 카드 + '전체 카드·출처는 왼쪽 위 프로필 → 오늘 게시물'

카드(1080×1350)는 브랜드 먹색(INK) 바탕에 1000px 폭으로 얹는다(카드를 흐리게 깐 바탕은 검은 카드에서 얼룩져 보였다).
인스타 스토리는 위(약 220px)에 진행 막대·계정 이름, 아래(약 200px)에 답장 칸이 덮으므로 카드와 안내 글은 그 사이에 둔다.
"""
import html
from pathlib import Path

from .cards import CSS, INK

W, H = 1080, 1920
CARD_W = 1000
CARD_H = CARD_W * 1350 // 1080   # 1250
ROLES = ("pick", "summary")       # 훅 다음에 보여 줄 카드(있는 것만, 이 순서로)

FRAME_CSS = """
.story{height:1920px;background:%(ink)s;}
.story .shot{position:absolute;left:%(left)dpx;width:%(w)dpx;height:%(h)dpx;border-radius:28px;overflow:hidden;
  border:2px solid rgba(255,255,255,.16);}
.story .shot img{display:block;width:100%%;height:100%%;}
.story .cta{position:absolute;left:60px;right:60px;top:1530px;text-align:center;color:#FFFFFF;}
""" % {"ink": INK, "left": (W - CARD_W) // 2, "w": CARD_W, "h": CARD_H}


def role(name):
    """'02_edit_h_2026-10-29_pick.jpg' → 'pick'."""
    return Path(name).stem.rsplit("_", 1)[-1]


def choose(card_files, hook):
    """스토리에 쓸 카드 파일 — 훅(세로 릴스 첫 장)이 없으면 표지부터. 고를 카드가 하나도 없으면 빈 목록."""
    by = {}
    for f in card_files:
        by.setdefault(role(f), f)
    picked = ([] if hook else [by.get("cover")]) + [by.get(r) for r in ROLES]
    return list(dict.fromkeys(f for f in picked if f))


def _frame(src, n_cards, last):
    top = 250 if last else (H - CARD_H) // 2
    cta = (f'<div class="cta"><div style="font-weight:800;font-size:46px;line-height:1.3;letter-spacing:-1px;">'
           f'카드 {n_cards}장 전체와 출처는 피드에</div>'
           f'<div style="margin-top:16px;font-weight:500;font-size:34px;line-height:1.4;opacity:.85;">'
           f'왼쪽 위 프로필을 눌러 오늘 게시물을 보세요</div></div>') if last else ""
    src = html.escape(src, quote=True)
    return (f'<section class="card story">'
            f'<div class="shot" style="top:{top}px;"><img src="{src}" alt=""></div>{cta}</section>')


def build(card_dir, card_files, hook, font_css):
    """(html, 파일명 목록). card_dir 의 게시용 JPEG(ig/) 중 고른 카드를 세로 화면으로. 고를 카드가 없으면 ("", [])."""
    chosen = choose(card_files, hook)
    if not chosen:
        return "", []
    frames = [_frame(Path(card_dir).resolve().joinpath(f).as_uri(), len(card_files), i == len(chosen) - 1)
              for i, f in enumerate(chosen)]
    files = [f"s{i}_{role(f)}.png" for i, f in enumerate(chosen, 1)]
    page = f"""<!DOCTYPE html><html lang="ko"><head><meta charset="UTF-8">
<style>{font_css}
{CSS}
{FRAME_CSS}</style></head><body>
{''.join(frames)}
</body></html>"""
    return page, files
