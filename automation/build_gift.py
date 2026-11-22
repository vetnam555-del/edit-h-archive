#!/usr/bin/env python3
"""구독 선물 페이지 — automation/gifts/{slug}.json → gift/{slug}.html (2026-10-04 주간 루틴, 실험 E5).

10/4 주간 진단: 팔로워는 한 주에 47→107 로 늘었는데 최근 14일 구독 신청은 0건이었다. 구독할 '지금 당장의 이유'를 만든다 —
발행한 호에서 원 기사로 확인한 사실만 모은 날짜별 체크리스트를 환영 메일로 보내고(sync_subscribers.welcome_message),
구독 페이지·인스타 캡션에서 알린다. 항목마다 그 호 페이지로 이어져 출처를 볼 수 있다.

  python3 automation/build_gift.py            # config.gift 의 slug 로 만든다
  python3 automation/build_gift.py 2026-q4
"""
import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from edith.common import AUTOMATION, ROOT, load_config, send_time_ko  # noqa: E402
from edith.gift import LIVE_FROM  # noqa: E402

GIFTS = AUTOMATION / "gifts"
OUT = ROOT / "gift"
CALC_JS = GIFTS / "card_calc.js"   # 선물 데이터에 "tool": "card-calc" 면 맨 위에 계산기(2026-11-22 운영자 '메리트 있게끔')


def until_attr(it):
    """항목의 마지막 날 → li 속성(브라우저가 그날이 지나면 숨긴다 — 페이지를 날마다 다시 만들지 않아도 지난 항목이 안 보이게)."""
    return f' data-until="{html.escape(it["until"])}"' if it.get("until") else ""


# 지난 항목 숨기기 — 한국 시각 날짜가 data-until 을 넘으면 숨기고, 'N가지'를 남은 수로, 빈 묶음은 제목째 숨긴다(2026-11-05 구독 길 점검:
# 4분기 선물 18가지 중 3가지가 10월에 끝났는데 그대로 보였다). 가짓수 세기와 같은 날(gift.LIVE_FROM)부터 — 그 전엔 환영 메일·캡션이
# 모두 센 수를 말하니 페이지도 모두 보인다(Codex 리뷰). 자바스크립트가 꺼져 있으면 전부 보인다.
HIDE_PAST = """<script>
(function () {
  var today = new Date(Date.now() + 9 * 3600 * 1000).toISOString().slice(0, 10), hidden = 0;
  if (today < '__LIVE_FROM__') return;
  document.querySelectorAll('li[data-until]').forEach(function (li) {
    if (li.getAttribute('data-until') < today) { li.hidden = true; hidden++; }
  });
  document.querySelectorAll('section').forEach(function (s) {
    if (!s.querySelector('li:not([hidden])')) s.hidden = true;
  });
  var n = document.getElementById('n');
  if (n && hidden) n.textContent = String(Number(n.textContent) - hidden);
})();
</script>""".replace("__LIVE_FROM__", LIVE_FROM)


CALC_CSS = """<style>
  .calc { margin: 26px 0 8px; padding: 22px 20px; background: #FFF6F1; border: 2px solid #B91C1C; }
  .calc h2 { margin: 0 0 6px; border: 0; padding: 0; font-size: 19px; }
  .calc .tag { font-size: 12px; color: #FFF; background: #B91C1C; padding: 2px 8px; vertical-align: 2px; margin-left: 4px; }
  .calc .hint { font-size: 13px; color: #666; margin: 4px 0 12px; }
  .calc .grid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 12px 14px; }
  .calc label.f { min-width: 0; display: grid; grid-template-columns: minmax(0, 1fr); gap: 4px; cursor: auto; font-size: 14px; font-weight: 800; }
  .calc .in { display: flex; align-items: center; gap: 6px; }
  .calc .in input, .calc .in select { flex: 1 1 auto; width: auto; min-width: 0; font: inherit; font-size: 17px; font-weight: 800; padding: 9px 10px; border: 1px solid #CCC;
    background: #FFF; color: #1A1A1A; accent-color: auto; transform: none; height: auto; }
  .calc .in i { white-space: nowrap; font-style: normal; font-size: 13px; color: #666; flex: none; }
  .calc small { font-size: 12px; font-weight: 400; color: #777; line-height: 1.45; }
  .calc details { margin: 14px 0 0; font-size: 14px; }
  .calc summary { cursor: pointer; font-weight: 800; color: #B91C1C; }
  .calc details .grid { margin-top: 8px; }
  .calc .out { margin: 18px 0 0; padding: 16px; background: #FFF; border-left: 4px solid #B91C1C; }
  .calc .out .big { font-size: 18px; font-weight: 800; line-height: 1.5; }
  .calc .out .big b { color: #B91C1C; }
  .calc .out ul { margin: 10px 0 0; } .calc .out li { padding: 4px 0; border: 0; font-size: 14px; color: #333; }
  .calc .share { display: flex; flex-wrap: wrap; gap: 10px 16px; align-items: center; margin: 14px 0 0; font-size: 14px; }
  .calc .share button { font: inherit; font-weight: 800; color: #FFF; background: #B91C1C; border: 0; padding: 10px 14px; cursor: pointer; }
  .calc .share a { color: #B91C1C; font-weight: 800; text-decoration: none; }
  .calc .tips { margin: 14px 0 0; padding-left: 18px; list-style: disc; } .calc .tips li { padding: 2px 0; border: 0; font-size: 13px; color: #555; }
  .calc .fine { font-size: 12px; color: #888; margin: 12px 0 0; line-height: 1.6; }
  .part { font-size: 19px; font-weight: 900; margin: 34px 0 0; }
  @media (max-width: 480px) { .calc { padding: 18px 14px; } .calc .grid { grid-template-columns: minmax(0, 1fr); } }
  @media print { .calc { display: none; } }
</style>"""

CALC_HTML = """<section class="calc" id="calc">
  <h2>① 내 카드 공제 계산기 <span class="tag">1분</span></h2>
  <p class="hint">연봉과 올해 쓴 카드 금액만 넣으면 남은 12월에 어떤 카드를 써야 얼마 더 돌려받는지 나와요.
  숫자는 이 화면 안에서만 계산하고 어디로도 보내지 않아요.</p>
  <div class="grid">
    <label class="f"><span>올해 총급여(세전 연봉)</span><span class="in"><input id="c-pay" inputmode="numeric" placeholder="4000"><i>만원</i></span>
      <small>식대 같은 비과세는 빼요. 모르면 연봉 그대로.</small></label>
    <label class="f"><span>기본공제 받는 자녀·손자녀</span><span class="in"><select id="c-kids"><option value="0">없음</option><option value="1">1명</option><option value="2">2명 이상</option></select></span>
      <small>자녀가 있으면 공제 한도가 늘어요.</small></label>
    <label class="f"><span>1월~지금 신용카드</span><span class="in"><input id="c-credit" inputmode="numeric" placeholder="1200"><i>만원</i></span>
      <small>카드 앱의 '소득공제 사용액'이나 홈택스 '연말정산 미리보기'.</small></label>
    <label class="f"><span>1월~지금 체크카드·현금영수증</span><span class="in"><input id="c-debit" inputmode="numeric" placeholder="300"><i>만원</i></span>
      <small>체크카드·페이 충전 결제·현금영수증을 합쳐요.</small></label>
    <label class="f"><span>12월 31일까지 더 쓸 돈(예상)</span><span class="in"><input id="c-rest" inputmode="numeric" value="100"><i>만원</i></span>
      <small>남은 생활비 대략.</small></label>
  </div>
  <details><summary>더 정확하게(선택) — 전통시장·대중교통·문화</summary>
  <p class="hint">아래에 넣은 금액은 위 신용·체크 칸에서 빼고 넣어요(홈택스 미리보기에도 따로 나와요).</p>
  <div class="grid">
    <label class="f"><span>전통시장</span><span class="in"><input id="c-market" inputmode="numeric" placeholder="0"><i>만원</i></span><small>공제율 40%</small></label>
    <label class="f"><span>대중교통</span><span class="in"><input id="c-transit" inputmode="numeric" placeholder="0"><i>만원</i></span><small>공제율 40%</small></label>
    <label class="f"><span>도서·신문·공연·박물관·영화·헬스장·수영장</span><span class="in"><input id="c-culture" inputmode="numeric" placeholder="0"><i>만원</i></span>
      <small>총급여 7천만원 이하만 30% — 넘으면 신용카드로 셈해요.</small></label>
  </div></details>
  <div class="out" id="c-out" aria-live="polite"><p class="big">총급여를 넣으면 바로 계산해요.</p></div>
  <div class="share"><button type="button" id="c-share">친구에게 이 계산기 보내기</button>
    <a href="__SITE__/subscribe.html?ref=calc">매일 아침, 이런 '내 돈 되는 숫자'를 골라 드려요 → 무료 구독</a></div>
  <ul class="tips">
    <li>소득 없는 배우자·부모님·자녀(기본공제 대상)가 쓴 카드도 합칠 수 있어요.</li>
    <li>해외에서 쓴 돈, 자동차 구입(중고차 일부 빼고), 회사 경비는 빠져요.</li>
    <li>홈택스 '연말정산 미리보기'에는 1~9월 사용액이 들어 있어요. 10~12월분은 카드 앱에서 더하세요.</li>
  </ul>
  <p class="fine">예상치예요. 조세특례제한법 제126조의2(2026.9.18 시행본 — 문턱 총급여 25%, 신용 15%·체크 30%·전통시장·대중교통 40%, 한도 250~400만원과 추가 한도)와
  소득세법 세율·근로소득세액공제로 계산했고, '돌려받는 돈'은 본인·자녀 기본공제와 4대보험(총급여의 약 9.4%)만 있다고 보고 지방소득세까지 더한 대략이에요.
  정확한 금액은 홈택스 '연말정산 미리보기'에서 확인하세요.</p>
</section>"""

CALC_UI = """<script>
(function () {
  var C = window.CardCalc, $ = function (id) { return document.getElementById(id); }, KEY = 'edith-card-calc', MAN = 10000;
  var ids = ['pay', 'kids', 'credit', 'debit', 'rest', 'market', 'transit', 'culture'];
  function num(id) { var v = String($('c-' + id).value).replace(/[^0-9.]/g, ''); return v ? Number(v) * MAN : 0; }
  function man(n) { return (Math.round(n / MAN * 10) / 10).toLocaleString('ko-KR') + '만원'; }
  function won(n) { n = Math.max(0, Math.round(n / 100) * 100); return n.toLocaleString('ko-KR') + '원'; }
  function save() { try { var o = {}; ids.forEach(function (k) { o[k] = $('c-' + k).value; }); localStorage.setItem(KEY, JSON.stringify(o)); } catch (e) {} }
  function load() { try { var o = JSON.parse(localStorage.getItem(KEY) || '{}'); ids.forEach(function (k) { if (o[k] != null && o[k] !== '') $('c-' + k).value = o[k]; }); } catch (e) {} }
  function run() {
    var s = {pay: num('pay'), kids: Number($('c-kids').value), credit: num('credit'), debit: num('debit'), rest: num('rest'),
             market: num('market'), transit: num('transit'), culture: num('culture')}, out = $('c-out');
    save();
    if (s.pay < 500 * MAN) { out.innerHTML = '<p class="big">총급여를 넣으면 바로 계산해요.</p>'; return; }
    var p = C.plan(s), n = p.now, d = p.byDebit, c = p.byCredit, rest = man(s.rest), head, lines = [];
    lines.push(n.gap > 0 ? '공제 문턱(총급여의 25%) <b>' + man(n.floor) + '</b>까지 <b>' + man(n.gap) + '</b> 남았어요.'
                         : '공제 문턱(총급여의 25%) <b>' + man(n.floor) + '</b>을 <b>' + man(n.used - n.floor) + '</b> 넘었어요.');
    if (!s.rest) head = '남은 12월 지출을 넣으면 어떤 카드가 나은지 알려 드려요.';
    else if (d.deduction <= 0) head = '12월까지 써도 문턱을 못 넘어요. 올해 카드 공제는 0원이라, <b>포인트·할인 큰 카드</b>로 쓰세요.';
    else if (c.capped && d.capped) head = '이미 공제 한도(' + man(n.limit + n.extra) + ')를 다 채웠어요. 남은 ' + rest + '은 <b>포인트·할인 큰 카드</b>로 쓰세요.';
    else if (p.gain >= 1000) head = '남은 ' + rest + '은 <b>체크카드</b>로 — 신용카드보다 세금 <b>약 ' + won(p.gain) + '</b> 더 돌려받아요.';
    else head = '어느 카드로 써도 차이가 1천원이 안 돼요. <b>포인트·할인 큰 카드</b>로 쓰세요.';
    if (n.deduction > 0) lines.push('지금까지 쓴 것만으로 카드 공제 <b>' + man(n.deduction) + '</b> → 세금 약 <b>' + won(p.refundNow) + '</b> 덜 내요.');
    if (s.rest && d.deduction > 0) lines.push('12월 ' + rest + '을 체크카드로 쓰면 공제 ' + man(d.deduction) + '(세금 약 ' + won(p.refundDebit) + ' ↓), 신용카드로 쓰면 ' +
                           man(c.deduction) + '(약 ' + won(p.refundCredit) + ' ↓).');
    if (d.capped) lines.push('공제 한도는 ' + man(n.limit) + (n.extra ? ' + 전통시장·대중교통 등 추가 ' + man(d.extra) : '') + '이에요.');
    out.innerHTML = '<p class="big">' + head + '</p><ul>' + lines.map(function (l) { return '<li>' + l + '</li>'; }).join('') + '</ul>';
  }
  load();
  ids.forEach(function (k) { $('c-' + k).addEventListener('input', run); $('c-' + k).addEventListener('change', run); });
  $('c-share').addEventListener('click', function () {
    var url = location.href.split('#')[0].split('?')[0] + '?ref=share', b = this;
    var done = function () { b.textContent = '링크 복사됨'; setTimeout(function () { b.textContent = '친구에게 이 계산기 보내기'; }, 1600); };
    if (navigator.share) { navigator.share({title: document.title, url: url}).catch(function () {}); return; }
    try { navigator.clipboard.writeText(url).then(done, function () { prompt('이 링크를 복사하세요', url); }); } catch (e) { prompt('이 링크를 복사하세요', url); }
  });
  run();
})();
</script>"""


def calc_block(data, site):
    """선물 데이터에 tool 이 있으면 계산기 칸(그 전 판 — 2026-q4 — 엔 없다, 페이지 그대로)."""
    if data.get("tool") != "card-calc":
        return ""
    return CALC_CSS + CALC_HTML.replace("__SITE__", site) + '<p class="part">② 12월 31일 전에 챙길 것</p>'



def calc_script(data):
    if data.get("tool") != "card-calc":
        return ""
    return "<script>\n" + CALC_JS.read_text(encoding="utf-8") + "</script>\n" + CALC_UI


def render(data, site):
    esc = html.escape
    groups = []
    for grp in data["groups"]:
        rows = "".join(
            f'<li{until_attr(it)}><label><input type="checkbox"><span class="when">{esc(it["when"])}</span>'
            f'<span class="do">{esc(it["do"])}</span></label>'
            f'<p class="detail">{esc(it["detail"])} <a href="{site}/{it["issue"]}.html">출처·원문 →</a></p></li>'
            for it in grp["items"])
        groups.append(f'<section><h2>{esc(grp["name"])}</h2><ul>{rows}</ul></section>')
    count = sum(len(grp["items"]) for grp in data["groups"])
    return f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="robots" content="noindex">
<title>{esc(data["title"])} — EDIT H</title>
<link rel="icon" href="../favicon.png">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Apple SD Gothic Neo','Pretendard','Malgun Gothic',-apple-system,sans-serif; background: #FAFAF7; color: #1A1A1A;
         line-height: 1.7; padding: 28px 16px; }}
  .card {{ max-width: 640px; margin: 0 auto; background: #FFF; padding: 40px 32px; }}
  .logo {{ font-size: 30px; font-weight: 900; letter-spacing: -1.5px; }} .logo .h {{ color: #B91C1C; }}
  .divider {{ height: 2px; background: #000; margin: 16px 0 24px; }}
  h1 {{ font-size: 25px; font-weight: 900; letter-spacing: -0.8px; line-height: 1.35; }}
  .sub {{ font-size: 15px; color: #555; margin-top: 6px; }}
  .note {{ font-size: 13px; color: #777; background: #F5F5EE; border-left: 4px solid #B91C1C; padding: 12px 16px; margin: 20px 0 8px; }}
  h2 {{ font-size: 17px; font-weight: 900; margin: 30px 0 6px; padding-bottom: 6px; border-bottom: 1px solid #DDD; }}
  ul {{ list-style: none; }}
  li {{ padding: 14px 0; border-bottom: 1px solid #EEE; }}
  label {{ display: flex; gap: 10px; align-items: baseline; cursor: pointer; }}
  input {{ width: 18px; height: 18px; flex: none; accent-color: #B91C1C; transform: translateY(3px); }}
  .when {{ flex: none; font-size: 12px; font-weight: 800; color: #B91C1C; min-width: 64px; }}
  .do {{ font-size: 16px; font-weight: 800; line-height: 1.45; }}
  label:has(input:checked) .do {{ text-decoration: line-through; color: #999; }}
  .detail {{ font-size: 14px; color: #444; margin: 6px 0 0 92px; }}
  .detail a {{ color: #B91C1C; font-weight: 700; text-decoration: none; white-space: nowrap; }}
  .foot {{ font-size: 13px; color: #888; margin-top: 28px; }}
  .foot a {{ color: #B91C1C; text-decoration: none; font-weight: 700; }}
  @media (max-width: 480px) {{ .card {{ padding: 28px 18px; }} .detail {{ margin-left: 28px; }} label {{ flex-wrap: wrap; }} .when {{ min-width: 0; }} }}
  @media print {{ body {{ background: #FFF; padding: 0; }} .card {{ padding: 0; }} .detail a {{ color: #444; }} }}
</style></head>
<body><div class="card">
  <div class="logo">EDIT<span class="h"> H</span></div>
  <div class="divider"></div>
  <h1>{esc(data["title"])}</h1>
  <p class="sub">{esc(data["subtitle"])} — <span id="n">{count}</span>가지</p>
  <p class="note">EDIT H 구독자 선물이에요. 모두 뉴스레터에서 원 기사로 확인해 다룬 내용이고, 항목마다 그 호로 가면 출처가 있어요.
  {esc(data["as_of"].replace("-", "."))} 기준이라 신청 전엔 공식 사이트에서 한 번 더 확인하세요. 날짜가 지난 항목은 이 화면에서 저절로 빠지고, 체크 표시는 이 화면에서만 보여요.</p>
  {calc_block(data, site)}{''.join(groups)}
  <p class="foot">매일 {send_time_ko(load_config()["send_time_kst"]).replace("오전", "아침")}, 이런 '할 일이 있는 숫자'를 5가지씩 보내드려요 — <a href="{site}/subscribe.html?ref=gift">EDIT H 구독</a> · <a href="{site}/">지난 호 전체</a></p>
</div>
{HIDE_PAST}
{calc_script(data)}</body></html>
"""


def main():
    cfg = load_config()
    slug = sys.argv[1] if len(sys.argv) > 1 else (cfg.get("gift") or {}).get("slug")
    if not slug:
        sys.exit("config.gift.slug 가 없습니다")
    data = json.loads((GIFTS / f"{slug}.json").read_text(encoding="utf-8"))
    for grp in data["groups"]:
        for it in grp["items"]:
            if not (ROOT / f"{it['issue']}.html").exists():
                sys.exit(f"✗ '{it['do']}' 의 호 {it['issue']} 가 없습니다 — 발행한 호의 사실만 싣는다")
    OUT.mkdir(exist_ok=True)
    out = OUT / f"{slug}.html"
    out.write_text(render(data, cfg["site_url"].rstrip("/")), encoding="utf-8")
    print(f"✓ {out.relative_to(ROOT)} ({sum(len(g['items']) for g in data['groups'])}가지)")


if __name__ == "__main__":
    main()
