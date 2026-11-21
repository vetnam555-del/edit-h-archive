"""금요일 '이번 주 퀴즈'(2026-11-27 호~) — 월~금 호에서 다룬 소식으로 3지선다 5문제.

2026-11-22 운영자 '1~4번 진행'(경쟁 비교: 뉴닉 '금요일엔 뉴닉퀴즈'·어피티 '머니퀴즈 오답노트'가 둘 다 금요일에 한 주를 정리한다).
메일엔 1번 문제만 보기 3개 버튼으로 싣고, 누르면 웹 화면(quiz/{날짜}.html)에서 정답·풀이가 바로 나오고 2~5번을 이어서 푼다.
시안: drafts/quiz-2026-11-20.html. 참여 수는 아직 세지 않는다(웹 페이지는 저장소에 쓰지 못한다) — 세려면 운영자 결정이 필요하다.
"""
import json
import re

from .common import esc, plain

QUIZ_FROM = "2026-11-27"
QUIZ_N, QUIZ_OPTIONS = 5, 3
QUIZ_Q, QUIZ_OPT, QUIZ_WHY = 34, 16, 110
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def check(quiz, date_str, where, dates_ok):
    """content.quiz 검증 → 문제 목록. dates_ok(날짜) 는 그 호가 있는지. 틀리면 ValueError(사유)."""
    if date_str < QUIZ_FROM:
        raise ValueError(f"quiz(금요일 퀴즈)는 {QUIZ_FROM} 호부터 씁니다")
    qs = quiz.get("questions") if isinstance(quiz, dict) else None
    if not isinstance(qs, list) or len(qs) != QUIZ_N:
        raise ValueError(f'quiz 는 {{"questions": [...{QUIZ_N}문제]}} — 지금 {len(qs) if isinstance(qs, list) else 0}문제')
    for i, q in enumerate(qs, 1):
        w = f"{where} quiz[{i}]"
        if not str(q.get("q", "")).strip() or len(plain(q["q"])) > QUIZ_Q:
            raise ValueError(f"{w}: q(질문)는 1~{QUIZ_Q}자")
        opts = q.get("options")
        if not isinstance(opts, list) or len(opts) != QUIZ_OPTIONS or any(not str(o).strip() or len(plain(o)) > QUIZ_OPT for o in opts):
            raise ValueError(f"{w}: options 는 보기 {QUIZ_OPTIONS}개(각 1~{QUIZ_OPT}자)")
        if q.get("answer") not in (1, 2, 3):
            raise ValueError(f"{w}: answer 는 정답 보기 번호 1~3")
        if not str(q.get("why", "")).strip() or len(plain(q["why"])) > QUIZ_WHY:
            raise ValueError(f"{w}: why(풀이)는 1~{QUIZ_WHY}자 — 그 호에 실린 사실만")
        day = str(q.get("date", ""))
        if not _DATE.match(day) or not day < date_str or not dates_ok(day):
            raise ValueError(f"{w}: date 는 문제가 나온 지난 호 날짜(YYYY-MM-DD, 이번 주·발행된 호)")
    return qs


def page_url(site, date_str):
    return f"{site}/quiz/{date_str}.html"


def page(d, site):
    """퀴즈 웹 화면 — 정답·풀이·다음 문제·결과(점수는 이 브라우저에서만 센다)."""
    date_str = d["date"]
    data = [{"d": q["date"], "q": plain(q["q"]), "o": [plain(o) for o in q["options"]], "a": q["answer"], "why": plain(q["why"])}
            for q in d["quiz"]["questions"]]
    first, last = data[0]["d"], max(x["d"] for x in data)
    span = f"{int(first[5:7])}/{int(first[8:])}~{int(last[5:7])}/{int(last[8:])} 소식"
    js_data = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>EDIT H — 이번 주 퀴즈 ({esc(date_str)})</title>
<meta name="description" content="EDIT H 이번 주 퀴즈 — {esc(span)}으로 5문제">
<meta property="og:title" content="EDIT H — 이번 주 퀴즈">
<meta property="og:image" content="{site}/og_image.png">
<link rel="icon" type="image/png" href="{site}/favicon.png">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Pretendard','Apple SD Gothic Neo','Malgun Gothic',-apple-system,sans-serif; background: #FFFFFF; color: #282F38;
    line-height: 1.7; word-break: keep-all; padding: 28px 18px 48px; }}
  .wrap {{ max-width: 520px; margin: 0 auto; }}
  .top {{ font-size: 13px; font-weight: 700; color: #5A5A5E; text-align: center; }}
  .chips {{ display: flex; gap: 6px; margin-top: 22px; flex-wrap: wrap; }}
  .chip {{ font-size: 13px; font-weight: 700; padding: 4px 10px; border-radius: 4px; background: #FFDCCB; color: #B23A0F; }}
  .chip.dark {{ background: #363636; color: #FF9466; }}
  .bar {{ height: 6px; background: #F3F3F3; border-radius: 3px; margin-top: 18px; overflow: hidden; }}
  .bar i {{ display: block; height: 100%; background: #FF9466; border-radius: 3px; }}
  .from {{ font-size: 12.5px; font-weight: 700; color: #B23A0F; margin-top: 20px; }}
  h1 {{ font-size: 21px; font-weight: 700; line-height: 1.45; margin-top: 6px; }}
  .opts {{ display: grid; gap: 8px; margin-top: 16px; }}
  .opt {{ display: block; padding: 13px 16px; border: 1.5px solid #282F38; border-radius: 12px; font-size: 15.5px; font-weight: 700;
    color: #282F38; text-decoration: none; background: #FFFFFF; }}
  .opt.right {{ background: #FFC9AD; }}
  .opt.wrong {{ border-color: #C9C9C9; color: #9A9A9A; text-decoration: line-through; }}
  .opt.dim {{ border-color: #E4E4E4; color: #9A9A9A; }}
  .result {{ margin-top: 18px; background: #F3F3F3; border-radius: 16px; padding: 16px 18px; }}
  .result b {{ font-size: 16px; }}
  .result p {{ font-size: 14.5px; color: #555558; margin-top: 6px; }}
  .result a {{ color: #B23A0F; font-weight: 700; }}
  .next {{ display: block; text-align: center; margin-top: 16px; padding: 14px; border-radius: 10px; background: #B23A0F; color: #FFFFFF;
    font-weight: 700; text-decoration: none; }}
  .sub {{ display: block; text-align: center; margin-top: 10px; padding: 13px; border-radius: 10px; border: 1.5px solid #B23A0F; color: #B23A0F;
    font-weight: 700; text-decoration: none; }}
  .score {{ font-size: 44px; font-weight: 800; margin-top: 14px; }}
  .score span {{ background: #FFC9AD; padding: 0 10px; }}
</style>
</head>
<body>
<div class="wrap">
  <div class="top">@edit.h.kr</div>
  <div class="chips"><span class="chip dark">금요일 퀴즈</span><span class="chip">{esc(span)}</span></div>
  <div class="bar"><i id="bar"></i></div>
  <div id="app"></div>
</div>
<script>
const SITE = {json.dumps(site)}, DAY = {json.dumps(date_str)};
const QS = {js_data};
const p = new URLSearchParams(location.search);
const qn = Math.min(Math.max(parseInt(p.get("q") || "1", 10) || 1, 1), QS.length + 1);
const ans = parseInt(p.get("a") || "0", 10) || 0;
const KEY = "edith-quiz-" + DAY;
const store = {{ get() {{ try {{ return JSON.parse(sessionStorage.getItem(KEY) || "{{}}"); }} catch (e) {{ return {{}}; }} }},
                set(v) {{ try {{ sessionStorage.setItem(KEY, JSON.stringify(v)); }} catch (e) {{}} }} }};
const app = document.getElementById("app");
document.getElementById("bar").style.width = Math.round(Math.min(qn - (ans ? 0 : 1), QS.length) / QS.length * 100) + "%";
const esc = s => String(s).replace(/[&<>"]/g, c => ({{ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }}[c]));
const md = d => `${{+d.slice(5, 7)}}/${{+d.slice(8)}}`;
if (qn > QS.length) {{
  const s = store.get(); const n = Object.values(s).filter(Boolean).length;
  app.innerHTML = `<h1 style="margin-top:20px">이번 주 퀴즈 끝!</h1><div class="score"><span>${{n}} / ${{QS.length}}</span></div>
    <p style="margin-top:12px;color:#555558">${{n >= 4 ? "이번 주 소식, 거의 다 챙기셨네요." : "놓친 소식은 지난 호에서 다시 볼 수 있어요."}}</p>
    <a class="next" href="${{SITE}}/share.html?d=${{DAY}}">친구에게 퀴즈 보내기</a>
    <a class="sub" href="${{SITE}}/subscribe.html?ref=quiz">매일 아침 받아 보기</a>`;
}} else {{
  const Q = QS[qn - 1];
  let html = `<div class="from">Q${{qn}} · ${{md(Q.d)}} 호</div><h1>${{esc(Q.q)}}</h1><div class="opts">`;
  Q.o.forEach((t, i) => {{
    const k = i + 1; let cls = "opt";
    if (ans) cls += k === Q.a ? " right" : (k === ans ? " wrong" : " dim");
    html += `<a class="${{cls}}" href="?q=${{qn}}&a=${{k}}">${{"①②③"[i]}} &nbsp;${{esc(t)}}</a>`;
  }});
  html += `</div>`;
  if (ans) {{
    const ok = ans === Q.a; const s = store.get(); if (!(qn in s)) {{ s[qn] = ok; store.set(s); }}
    html += `<div class="result"><b>${{ok ? "정답이에요!" : "아쉬워요, 정답은 " + "①②③"[Q.a - 1] + "번"}}</b>
      <p>${{esc(Q.why)}}</p><p><a href="${{SITE}}/${{Q.d}}.html">${{md(Q.d)}} 호에서 자세히 보기 ›</a></p></div>
      <a class="next" href="?q=${{qn + 1}}">${{qn < QS.length ? "다음 문제" : "결과 보기"}}</a>`;
  }}
  app.innerHTML = html;
}}
</script>
</body>
</html>
"""
