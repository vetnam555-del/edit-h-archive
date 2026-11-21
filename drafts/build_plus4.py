"""시안 '+4' — 지금 매거진 디자인은 그대로, 경쟁 비교에서 고른 4칸만 더한다(2026-11-22 운영자 '1~4번 시안').
① 맨 위 시세판 4칸 ② 그래프 매일(H PICK 막대 그래프) ③ 금요일 퀴즈(메일엔 1번 문제, 나머지는 웹) ④ 맨 끝 '좋았어요/아쉬웠어요'.
python3 build_plus4.py <repo> → drafts/2026-11-21-plus4.html
"""
import sys

REPO = sys.argv[1]
sys.path.insert(0, f"{REPO}/automation")
from edith import content, newsletter as nl  # noqa: E402
from edith.common import esc  # noqa: E402

SITE = "https://vetnam555-del.github.io/edit-h-archive"
UP, DOWN = "#D93A2B", "#2F6BD8"   # 한국식 — 오르면 빨강, 내리면 파랑

MARKET = {   # 11/20(금) 마감 — 네이버 증권(한국거래소 시세)·서울신문·Morning Brew 대조
    "asof": "11/20(금) 마감 · 나스닥은 현지 20일 종가",
    "rows": [("코스피", "4,869.96", "-5.21%"), ("코스닥", "645.68", "-5.71%"),
             ("원/달러", "1,336.2원", "+6.2원"), ("나스닥", "22,617.73", "-5.28%")],
}
QUIZ = {"week": "2026-11-20", "q": "내년 4월부터 은행 문 여는 시간은?",
        "options": ["오전 9시", "오전 9시 30분", "오전 10시"]}


def market_board(m):
    def cell(name, value, chg):
        down = chg.startswith("-")
        color, arrow = (DOWN, "▼") if down else (UP, "▲")
        return (f'<td width="50%" valign="top" style="padding:10px 12px;">'
                + nl._div(f"font-size:12px;font-weight:500;line-height:1.3;color:{nl.MUTED};", esc(name))
                + nl._div(f"font-size:17px;font-weight:800;line-height:1.35;color:{nl.INK};margin-top:3px;",
                          f'{esc(value)} <span style="font-size:13px;font-weight:700;color:{color};white-space:nowrap;">{arrow}{esc(chg.lstrip("+-"))}</span>')
                + "</td>")
    r = m["rows"]
    grid = (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
            f'<tr>{cell(*r[0])}{cell(*r[1])}</tr>'
            f'<tr><td colspan="2" style="padding:0 12px;"><div style="border-top:1px solid #E4E4E4;font-size:0;line-height:0;">&nbsp;</div></td></tr>'
            f'<tr>{cell(*r[2])}{cell(*r[3])}</tr></table>')
    return (f'<tr><td class="px" style="padding:18px 36px 0;">'
            + nl._box(grid, pad="6px 4px", mt=0)
            + nl._div(f"font-size:11.5px;font-weight:400;line-height:1.5;color:{nl.MUTED};margin-top:6px;", esc(m["asof"]), True)
            + "</td></tr>")


def quiz_block(q):
    def opt(i, text):
        href = f"{SITE}/drafts/quiz-{q['week']}.html?q=1&amp;a={i}"
        return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:8px;"><tr>'
                f'<td style="background:#FFFFFF;border:1.5px solid {nl.INK};border-radius:12px;">'
                f'<a href="{href}" style="display:block;padding:13px 16px;font-family:{nl.F};font-size:15px;font-weight:700;'
                f'color:{nl.INK};text-decoration:none;">{"①②③"[i - 1]} &nbsp;{esc(text)}</a></td></tr></table>')
    return (nl._divider(30) + f'<tr><td class="px" style="padding:0 36px;">'
            + nl._chips([("금요일 퀴즈", True), ("이번 주 5문제", False)], "left")
            + nl._div(f"font-size:20px;font-weight:700;line-height:1.45;color:{nl.INK};margin-top:14px;", "이번 주 소식, 얼마나 기억나요?")
            + nl._div(f"font-size:14px;font-weight:400;line-height:1.7;color:{nl.BODY};margin-top:6px;",
                      "월~금 EDIT H에서 다룬 소식으로 5문제를 냈어요. 1번은 여기서 바로 골라 보세요.")
            + nl._box(nl._div(f"font-size:12.5px;font-weight:700;line-height:1.3;color:{nl.CHIP_FG};", "Q1 · 11/16 호")
                      + nl._div(f"font-size:16.5px;font-weight:700;line-height:1.5;color:{nl.INK};margin-top:6px;", esc(q["q"]))
                      + "".join(opt(i, t) for i, t in enumerate(q["options"], 1)), pad="16px 16px 18px", mt=14)
            + nl._div(f"font-size:12.5px;font-weight:400;line-height:1.7;color:{nl.MUTED};margin-top:10px;",
                      "누르면 정답과 풀이가 바로 나오고, 2~5번을 이어서 풀 수 있어요. 다음 금요일엔 가장 많이 틀린 문제를 풀어 드려요.", True)
            + "</td></tr>")


def rate_block(date):
    def btn(v, text, bg):
        href = f"{SITE}/drafts/rate.html?d={date}&amp;v={v}"
        return (f'<td width="50%" style="padding:0 4px;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>'
                f'<td align="center" style="background:{bg};border:1.5px solid {nl.INK};border-radius:12px;">'
                f'<a href="{href}" style="display:block;padding:12px 8px;font-family:{nl.F};font-size:15px;font-weight:700;color:{nl.INK};'
                f'text-decoration:none;">{text}</a></td></tr></table></td>')
    return (f'<tr><td class="px" style="padding:26px 36px 0;">'
            + nl._div(f"font-size:15px;font-weight:700;line-height:1.4;color:{nl.INK};", "오늘 레터, 어땠어요?", True)
            + f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:12px;"><tr>'
            + btn("good", "좋았어요", nl.HL) + btn("meh", "아쉬웠어요", "#FFFFFF") + "</tr></table>"
            + nl._div(f"font-size:12px;font-weight:400;line-height:1.6;color:{nl.MUTED};margin-top:8px;",
                      "한 번 누르면 끝이에요. 무엇이 좋았는지·아쉬웠는지는 답장으로 한 줄 남겨 주시면 다음 호에 반영할게요.", True)
            + "</td></tr>")


# 끼워 넣기 — 렌더 함수는 그대로 두고 앞뒤에만 붙인다(지금 매거진 디자인 유지)
_header, _question, _poll_block = nl._header, nl._question, nl._poll_block
nl._header = lambda d: _header(d) + market_board(MARKET)
nl._question = lambda d: quiz_block(QUIZ) + _question(d) + rate_block(d["date"])
nl._poll_block = lambda d, site: quiz_block(QUIZ) + _poll_block(d, site) + rate_block(d["date"])
nl.NL_CHART_FROM = "2026-11-01"   # 시안만 — 실제로는 11/22 호부터

d = content.load("2026-11-21")
d["cards"]["deep"]["chart"] = {"title": "20일 하루, ==반도체가 더 크게== 빠졌다", "unit": "%",
                               "points": [{"label": "코스피", "value": 5.21}, {"label": "코스닥", "value": 5.71},
                                          {"label": "SK하이닉스", "value": 5.92}, {"label": "삼성전자", "value": 7.01}],
                               "highlight": 3, "source": "서울신문·디지털데일리·헤럴드경제"}
content._chart(d["cards"]["deep"]["chart"], "preview")
html = nl.render(d, SITE, 10)
out = f"{REPO}/drafts/2026-11-21-plus4.html"
open(out, "w", encoding="utf-8").write(html)
print(out, len(html.encode()))
